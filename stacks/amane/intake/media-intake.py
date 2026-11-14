"""JAV / Porn intake: move new videos from the 115 inboxes into the Amane libraries, scrape and organize them.

Runs as the one-shot `amane-intake` service (see ../compose.yaml): Komodo's "Media Intake" procedure starts it
daily at 08:30, and the same procedure can be run by hand. Everything goes through the clouddrive2 mount,
whose open115 quota Muvyo shares, so it stays small: one listing per inbox, one move per file, ~1 op/s.

  115 /Others/待整理/JAV   -> /Japan/_inbox -> Amane library 1 -> /Japan/<type>/<prefix>/<number>/
  115 /Others/待整理/Porn  -> /Porn/_inbox  -> Amane library 2 -> /Porn/<PREFIX>/<Studio.YY.MM.DD>/

Organize writes the STRM + NFO + images under /data/{Japan,Western}; Plex picks them up by itself.
A file Amane cannot scrape stays in the library's _inbox (Amane UI: status pending) and is retried next run.

The report (every original name -> number, with suspect matches marked) goes to the container log and to
Telegram. A run with nothing to report stays silent.
"""
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = os.environ.get("AMANE_API", "http://amane:8000/api")
VIDEO = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg", ".vob", ".iso", ".rmvb", ".flv"}
# (name, inbox on 115, Amane library id, library root, minimum size, content_type override)
INBOXES = [
    ("JAV", "/media/115/Others/待整理/JAV", 1, "/media/115/Japan", 200 << 20, None),
    ("Porn", "/media/115/Others/待整理/Porn", 2, "/media/115/Porn", 30 << 20, "western"),
]
# Below min_size a file is left where it is. Ads sit far under this; anything above it may be the film.
WORTH_REPORTING = 30 << 20
# A download folder holding nothing of that size is what the film left behind (ads, covers, links). It is
# removed once nothing in it has changed for this long, so a folder still being uploaded is never taken.
JUNK_AGE = 24 * 3600

TG_TEXT_LIMIT = 3800
TG_MAX_LIST_MESSAGES = 3  # a longer list goes out as a .txt attachment
TG_SEND_INTERVAL = 3.1  # Telegram allows about 20 messages a minute to one chat
DATE_CONFLICT_DAYS = 365

# Site-name prefixes ("hhd800.com@ABC-123"): their digits and TLDs are what Amane misreads as a number.
# The TLD ends at anything but a letter, so a prefix glued straight onto the number ("4k2.me390JNT-120")
# is stripped too; \b would not end "me" before "390" and the name then reads as ME-390.
DOMAIN = re.compile(r"[a-z0-9-]+\.(?:com|net|org|xyz|me|cc|tv|la|fun|top|vip|info|io|co|site|club|live)(?![a-z])", re.I)
NUMBER_LIKE = re.compile(r"(?<![A-Za-z0-9])(\d{0,4}[A-Za-z]{2,8})[-_ ]?(\d{2,6})(?!\d)")
NOT_A_NUMBER = {"CD", "PART", "HD", "FHD", "MP", "AV", "HEVC", "AAC", "VR"}


def api(method, path, body=None):
    with open("/config/token") as f:
        token = f.read().strip()
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


def run(task):
    """Submit an Amane task and wait for it (and its children) to finish."""
    tid = api("POST", "/tasks", task)["id"]
    while True:
        t = api("GET", f"/tasks/{tid}")
        cs = t.get("child_status") or {}
        if t["status"] in ("done", "failed", "cancelled") and not cs.get("queued") and not cs.get("running"):
            return t
        time.sleep(2)


def say(*parts):
    print(time.strftime("%F %T"), *parts, flush=True)


def western_number(stem):
    """Studio.YY.MM.DD, the form ThePornDB matches on (studio + date); scene-release and "site - yy.mm.dd - title"."""
    base = re.sub(r"\s*-\s*cd\d+$", "", stem, flags=re.I)
    m = re.match(r"^(.+?)(?: - |\.)(\d{2}|\d{4})\.(\d\d)\.(\d\d)(?!\d)", base)
    if not m:
        return None
    site = "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", m.group(1)) if w)
    return f"{site}.{m.group(2)[-2:]}.{m.group(3)}.{m.group(4)}"


def rows_under(lib, prefix):
    out, off = [], 0
    while True:
        page = api("GET", f"/media?library_id={lib}&limit=200&offset={off}&search=" + urllib.parse.quote(prefix))
        out += [r for r in page["items"] if r["path"].startswith(prefix)]
        off += 200
        if off >= page["total"]:
            return out


def number_candidates(stem, number):
    """Other number-shaped tokens in a file name, ignoring site-name prefixes."""
    found = set()
    for prefix, digits in NUMBER_LIKE.findall(DOMAIN.sub(" ", stem)):
        cand = f"{prefix}-{digits}".upper()
        if prefix.upper() not in NOT_A_NUMBER and prefix.upper() != number.split("-")[0].upper() and int(digits):
            found.add(cand)
    return sorted(found)


def number_in_name(stem, number):
    """Whether the number is a contiguous piece of the name (ABC-123, abc123, abc00123), not assembled across junk."""
    m = re.match(r"(.+?)-(.+)$", number)
    if not m:
        return True
    pattern = rf"(?<![A-Za-z0-9]){re.escape(m.group(1))}(?:[-_]?PPV)?[-_]?0*{re.escape(m.group(2).lstrip('0'))}(?!\d)"
    return re.search(pattern, DOMAIN.sub(" ", stem), re.I) is not None


def date_conflict(raw):
    """JavDB and JavBus disagreeing by years means they hold different films under one number."""
    try:
        a, b = (datetime.date.fromisoformat((raw[s].get("release") or "")[:10]) for s in ("javdb", "javbus"))
    except (KeyError, ValueError):
        return None
    return f"JavDB {a} 与 JavBus {b} 发行日不符，可能是同番号的另一部" if abs((a - b).days) > DATE_CONFLICT_DAYS else None


def suspects(stem, number, folder, raw):
    """(strong, weak) reasons to doubt a match. Only for name-derived numbers: Porn's are built from the name."""
    from amane.parsing.file_info import extract_number

    strong, weak = [], []
    if not number_in_name(stem, number):
        strong.append(f"{number} 不是原名中的连续片段")
    others = number_candidates(stem, number)
    if others:
        strong.append("原名里还有 " + "、".join(others))
    from_folder = extract_number(folder) if folder else None
    if from_folder and re.sub(r"^\d+", "", from_folder) != re.sub(r"^\d+", "", number):
        strong.append(f"文件夹名是 {from_folder}")
    conflict = date_conflict(raw)
    if conflict:
        strong.append(conflict)
    if len(raw) == 1:
        weak.append(f"只有 {next(iter(raw))} 一个来源")
    return strong, weak


def drop_junk_folders(name, inbox):
    """Remove the download folders a film has left: every file under WORTH_REPORTING, none touched for JUNK_AGE.
    Only folders: a loose file in the inbox itself is never deleted."""
    try:
        tops = sorted(os.listdir(inbox))
    except OSError as err:
        say(name, "junk folders not checked:", type(err).__name__, err)
        return
    for top in tops:
        path = os.path.join(inbox, top)
        if not os.path.isdir(path):
            continue
        try:
            tree = list(os.walk(path, topdown=False))  # children first, the folder itself last
            files = [os.path.join(d, f) for d, _, fs in tree for f in fs]
            sizes = [os.path.getsize(f) for f in files]
            newest = max(os.path.getmtime(p) for p in files + [d for d, _, _ in tree])
            if not files or max(sizes) >= WORTH_REPORTING or time.time() - newest < JUNK_AGE:
                continue
            for p in files:
                os.remove(p)
                time.sleep(1.1)
            for d, _, _ in tree:
                os.rmdir(d)
                time.sleep(1.1)
            say(name, f"junk folder removed: {top} ({len(files)} files, {sum(sizes) / (1 << 20):.0f} MB)")
        except OSError as err:  # housekeeping only: the intake itself goes on
            say(name, "junk folder kept:", top, type(err).__name__, err)


def intake(name, inbox, lib, root, min_size, content_type):
    """Returns (entries, skipped): one entry per file handled, skipped = (name, why) left in the inbox."""
    stage = f"{root}/_inbox"
    moved = 0
    folders, skipped = {}, []
    if os.path.isdir(inbox):
        for d, _, files in os.walk(inbox):
            for f in sorted(files):
                src = os.path.join(d, f)
                if os.path.splitext(f)[1].lower() not in VIDEO:
                    continue
                size = os.path.getsize(src)
                if size < min_size:
                    if size >= WORTH_REPORTING:
                        skipped.append((os.path.relpath(src, inbox), f"{size >> 20} MB，小于阈值"))
                    continue
                os.makedirs(stage, exist_ok=True)
                # Amane only reads "-cd1" as a part; "name - cd1.mp4" would be a separate whole film
                dst = os.path.join(stage, re.sub(r"\s+-\s+cd(\d+)(?=\.[^.]+$)", r"-cd\1", f, flags=re.I))
                if os.path.exists(dst):
                    skipped.append((os.path.relpath(src, inbox), "_inbox 里已有同名文件"))
                    continue
                os.rename(src, dst)
                moved += 1
                # The move flattens the download folder away, and with it Amane's fallback on the folder name
                if d != inbox:
                    folders[os.path.basename(dst)] = os.path.basename(d)
                time.sleep(1.1)
        for d, sub, files in sorted(os.walk(inbox), key=lambda w: -len(w[0])):  # drop emptied download folders
            if d != inbox and not os.listdir(d):
                os.rmdir(d)
                time.sleep(1.1)
        drop_junk_folders(name, inbox)
    if not moved and not os.path.isdir(stage):
        say(name, "nothing new")
        return [], skipped
    run({"type": "refresh", "library_id": lib, "path": stage, "recursive": False, "scrape": []})
    entries = []
    for r in rows_under(lib, stage + "/"):
        fname = r["path"].rsplit("/", 1)[1]
        stem = fname.rsplit(".", 1)[0]
        if not os.path.exists(r["path"]):
            # Deleted or renamed in the 115 app. Organize drops a row whose file is gone; refresh's "remove" scan
            # would not do: it compares the whole library against the one folder it just walked.
            run({"type": "organize", "library_id": lib, "media_file_ids": [r["id"]]})
            say(name, "dropped (file gone):", fname)
            continue
        entry = {"name": fname, "number": None, "path": None, "error": None, "strong": [], "weak": []}
        entries.append(entry)
        metadata_id = r.get("metadata_id")
        if not metadata_id:  # otherwise already scraped by hand ("指定番号刮削"): the file name must not undo that
            task = {"type": "scrape", "media_id": r["id"]}
            if content_type == "western":
                number = western_number(stem)
                if not number:
                    entry["error"] = "原名里没有 Studio.YY.MM.DD"
                    continue
                task.update(number=number, content_type="western")
            t = run(task)
            entry["number"] = (t.get("payload") or {}).get("number")
            if t["status"] != "done":
                entry["error"] = t.get("error") or t["status"]
                if not content_type and entry["number"]:
                    entry["strong"] = suspects(stem, entry["number"], folders.get(fname), {})[0]
                continue
            metadata_id = (t.get("result") or {}).get("metadata_id")
        meta = api("GET", f"/metadata/{metadata_id}")["metadata"]
        entry["number"] = meta["number"]
        if not content_type and not r.get("metadata_id"):
            entry["strong"], entry["weak"] = suspects(stem, meta["number"], folders.get(fname), meta.get("raw") or {})
        organized = run({"type": "organize", "library_id": lib, "media_file_ids": [r["id"]]})
        try:
            path = api("GET", f"/media/{r['id']}")["path"]
        except Exception:
            path = stage  # row dropped on a failed stat: re-registered from _inbox next run
        if not path.startswith(stage):
            entry["path"] = path.removeprefix(root + "/")
        elif (organized.get("result") or {}).get("conflicted"):
            entry["error"] = f"目标已存在，{meta['number']} 重复了"
        else:
            entry["error"] = "整理失败"
        time.sleep(3)
    return entries, skipped


# --- report ---------------------------------------------------------------------------------------------------


def clip(text, width=70):
    return text if len(text) <= width else text[:width - 21] + "…" + text[-20:]


def e(text):
    return html.escape(str(text), quote=False)


def build_messages(results):
    """Telegram HTML messages (headline + what needs attention) and the full original-name list, in pages."""
    now = time.strftime("%m-%d %H:%M")
    head = [f"🎬 <b>Media Intake</b> {now}"]
    attention, listing = [], []
    for name, entries, skipped, error in results:
        added = [x for x in entries if x["path"]]
        strong = [x for x in added if x["strong"]]
        left = [x for x in entries if not x["path"]]
        counts = [f"新增 {len(added)}"]
        if strong:
            counts.append(f"🔴 {len(strong)}")
        if left:
            counts.append(f"❌ {len(left)}")
        if skipped:
            counts.append(f"⚠️ 跳过 {len(skipped)}")
        if error:
            counts.append("💥 出错")
        if entries or skipped or error:
            head.append(f"{name}：" + " · ".join(counts))
        if error:
            attention.append(f"💥 <b>{name} 中断</b>\n{e(error)}")
        if strong:
            attention.append(f"🔴 <b>{name} 可疑，已入库，请核对</b>\n" + "\n".join(
                f"• {e(clip(x['name']))} → <b>{e(x['number'])}</b>\n  {e('；'.join(x['strong']))}" for x in strong))
        if left:
            attention.append(f"❌ <b>{name} 未入库，留在 _inbox</b>\n" + "\n".join(
                f"• {e(clip(x['name']))}\n  {e(x['error'])}"
                + (f"\n  {e('；'.join(x['strong']))}" if x["strong"] else "") for x in left))
        if skipped:
            attention.append(f"⚠️ <b>{name} 未处理，还在待整理</b>\n" + "\n".join(
                f"• {e(clip(n))}（{e(why)}）" for n, why in skipped))
        for x in sorted(entries, key=lambda x: x["name"].lower()):
            mark = "❌" if not x["path"] else "🔴" if x["strong"] else "✓"
            listing.append((mark, x["name"], x["number"] or "—"))
    return "\n".join(head), attention, listing


def cut_line(line):
    """A line longer than a page, in page-sized pieces, none ending inside an HTML entity or tag."""
    pieces = []
    while len(line) > TG_TEXT_LIMIT:
        piece = re.sub(r"(?:&[a-z]*|</?[a-z]*)$", "", line[:TG_TEXT_LIMIT]) or line[:TG_TEXT_LIMIT]
        pieces.append(piece)
        line = line[len(piece):]
    return pieces + [line]


def paginate(blocks, sep="\n"):
    """Join blocks into pages under Telegram's limit, sep between blocks; a block longer than a page is split on its
    lines, which stay together with a plain newline, and a line longer than a page is cut."""
    pages, cur = [], ""
    for block in blocks:
        pieces = [block] if len(block) <= TG_TEXT_LIMIT else [p for line in block.split("\n") for p in cut_line(line)]
        for i, piece in enumerate(pieces):
            joiner = "\n" if i else sep
            if cur and len(cur) + len(joiner) + len(piece) > TG_TEXT_LIMIT:
                pages.append(cur)
                cur = ""
            cur = f"{cur}{joiner}{piece}" if cur else piece
    return pages + [cur] if cur else pages


def telegram(method, fields, attachment=None):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        say("telegram: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set, report only in this log")
        return
    fields = {"chat_id": chat, **fields}
    if attachment:
        filename, content = attachment
        boundary = uuid.uuid4().hex
        body = b"".join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in fields.items())
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                 "Content-Type: text/plain; charset=utf-8\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        ctype = f"multipart/form-data; boundary={boundary}"
    else:
        body, ctype = json.dumps(fields).encode(), "application/json"
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=body,
                                 headers={"Content-Type": ctype})
    for attempt in (1, 2, 3):
        wait = 5
        try:
            with urllib.request.urlopen(req, timeout=60):
                time.sleep(TG_SEND_INTERVAL)
                return
        except urllib.error.HTTPError as err:  # the message never carries the URL, so the token stays out of the log
            reply = err.read().decode(errors="replace")
            say("telegram:", method, err.code, reply[:300])
            if err.code == 429:
                try:
                    wait = int(json.loads(reply)["parameters"]["retry_after"]) + 1
                except (ValueError, KeyError, TypeError):
                    wait = 60
        except OSError as err:
            say("telegram:", method, type(err).__name__, err)
        if attempt < 3:
            time.sleep(wait)


def send_report(results):
    head, attention, listing = build_messages(results)
    if len(head.split("\n")) == 1:  # nothing happened in any inbox
        return
    send = lambda text: telegram("sendMessage", {"text": text, "parse_mode": "HTML"})
    for page in paginate([head, *attention], sep="\n\n"):
        send(page)
    if not listing:
        return
    rows = [f"{mark} {e(clip(name))} → <b>{e(number)}</b>" for mark, name, number in listing]
    list_pages = paginate(["📋 <b>原名 → 番号</b>\n" + rows[0], *rows[1:]])
    if len(list_pages) <= TG_MAX_LIST_MESSAGES:
        for page in list_pages:
            send(page)
    else:
        text = "\n".join(f"{mark} {name} -> {number}" for mark, name, number in listing)
        telegram("sendDocument", {"caption": f"📋 原名 → 番号，共 {len(listing)} 条"},
                 (f"media-intake-{time.strftime('%Y%m%d-%H%M')}.txt", text.encode()))


if __name__ == "__main__":
    bad = False
    results = []
    for box in INBOXES:
        try:
            entries, skipped = intake(*box)
            results.append((box[0], entries, skipped, None))
        except Exception as err:  # one inbox failing must not stop the other
            bad = True
            say(box[0], "ERROR", type(err).__name__, err)
            results.append((box[0], [], [], f"{type(err).__name__}: {err}"))
            continue
        for x in entries:
            if x["path"]:
                mark = "SUSPECT " if x["strong"] else "weak " if x["weak"] else ""
                say(box[0], f"{mark}in:", x["name"], "->", x["number"], "->", x["path"], *x["strong"], *x["weak"])
            else:
                say(box[0], "left in _inbox:", x["name"], "->", x["number"], ":", x["error"], *x["strong"])
        for n, why in skipped:
            say(box[0], f"left in place: {n} ({why})")
        if entries:
            added = sum(1 for x in entries if x["path"])
            say(box[0], f"{added} added, {len(entries) - added} left in _inbox")
    try:
        send_report(results)
    except Exception as err:  # the intake itself is done; the log still has the report
        say("telegram: report failed", type(err).__name__, err)
    sys.exit(1 if bad else 0)
