"""JAV / Porn intake: move new videos from the 115 inboxes into the Amane libraries, scrape and organize them.

Runs as the one-shot `amane-intake` service (see ../compose.yaml): Komodo's "Media Intake" procedure starts it
daily at 08:30, and the same procedure can be run by hand. Everything goes through the clouddrive2 mount,
whose open115 quota Muvyo shares, so it stays small: one listing per inbox, one move per file, ~1 op/s.

  115 /Others/待整理/JAV   -> /Japan/_inbox -> Amane library 1 -> /Japan/<type>/<prefix>/<number>/
  115 /Others/待整理/Porn  -> /Porn/_inbox  -> Amane library 2 -> /Porn/<PREFIX>/<Studio.YY.MM.DD>/

Organize writes the STRM + NFO + images under /data/{Japan,Western}; Plex picks them up by itself.
A file Amane cannot scrape stays in the library's _inbox (Amane UI: status pending) and is retried next run.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API = os.environ.get("AMANE_API", "http://amane:8000/api")
TOKEN = open("/config/token").read().strip()
VIDEO = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg", ".vob", ".iso", ".rmvb", ".flv"}
# (name, inbox on 115, Amane library id, library root, minimum size, content_type override)
INBOXES = [
    ("JAV", "/media/115/Others/待整理/JAV", 1, "/media/115/Japan", 200 << 20, None),
    ("Porn", "/media/115/Others/待整理/Porn", 2, "/media/115/Porn", 50 << 20, "western"),
]
TPDB_NUMBERS = "/config/plugins/sources/local.tpdbid/numbers.json"


def api(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
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


def western_number(stem, known):
    """Studio.YY.MM.DD, the form ThePornDB matches on (studio + date); scene-release and "site - yy.mm.dd - title"."""
    base = re.sub(r"\s*-\s*cd\d+$", "", stem, flags=re.I)
    if base in known:
        return known[base]
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


def intake(name, inbox, lib, root, min_size, content_type):
    stage = f"{root}/_inbox"
    moved = 0
    if os.path.isdir(inbox):
        for d, _, files in os.walk(inbox):
            for f in sorted(files):
                src = os.path.join(d, f)
                if os.path.splitext(f)[1].lower() not in VIDEO or os.path.getsize(src) < min_size:
                    continue
                os.makedirs(stage, exist_ok=True)
                dst = os.path.join(stage, f)
                if os.path.exists(dst):
                    say(name, "skip (already in _inbox):", f)
                    continue
                os.rename(src, dst)
                moved += 1
                time.sleep(1.1)
        for d, sub, files in sorted(os.walk(inbox), key=lambda w: -len(w[0])):  # drop emptied download folders
            if d != inbox and not os.listdir(d):
                os.rmdir(d)
                time.sleep(1.1)
    if not moved and not os.path.isdir(stage):
        say(name, "nothing new")
        return [], []
    run({"type": "refresh", "library_id": lib, "path": stage, "recursive": False, "scrape": []})
    known = json.load(open(TPDB_NUMBERS)) if content_type == "western" and os.path.exists(TPDB_NUMBERS) else {}
    known = {stem: number for number, stem in known.items()}
    done, failed = [], []
    for r in rows_under(lib, stage + "/"):
        stem = r["path"].rsplit("/", 1)[1].rsplit(".", 1)[0]
        task = {"type": "scrape", "media_id": r["id"]}
        if content_type == "western":
            number = western_number(stem, known)
            if not number:
                failed.append(f"{stem}: no Studio.YY.MM.DD in the name")
                continue
            task.update(number=number, content_type="western")
        t = run(task)
        if t["status"] != "done":
            failed.append(f"{stem}: scrape {t.get('error') or t['status']}")
            continue
        run({"type": "organize", "library_id": lib, "media_file_ids": [r["id"]]})
        try:
            path = api("GET", f"/media/{r['id']}")["path"]
        except Exception:
            path = stage  # row dropped on a failed stat: re-registered from _inbox next run
        if path.startswith(stage):
            failed.append(f"{stem}: organize failed")
        else:
            done.append(path.removeprefix(root + "/"))
        time.sleep(3)
    return done, failed


if __name__ == "__main__":
    bad = False
    for box in INBOXES:
        try:
            done, failed = intake(*box)
        except Exception as e:  # one inbox failing must not stop the other
            bad = True
            say(box[0], "ERROR", type(e).__name__, e)
            continue
        for p in done:
            say(box[0], "in:", p)
        for p in failed:
            say(box[0], "left in _inbox:", p)
        if done or failed:
            say(box[0], f"{len(done)} added, {len(failed)} left in _inbox")
    sys.exit(1 if bad else 0)
