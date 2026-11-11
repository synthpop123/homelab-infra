#!/usr/bin/env python3
"""Nightly cleanup of the Amane-organized STRM trees (Japan, Western). Local only: no 115/CD2 calls.

  A. a film folder with no .strm left (Muvyo's 115 life events removed it) -> its NFO/images/json
  B. a .strm no Amane row points at (deleted in Amane, or a stray) -> the .strm and its same-stem sidecars
  C. an organized Amane row whose .strm is gone -> the index row (database only)

Nothing is deleted outright: files move to /srv/emby/data/.trash/<date>/ (purged after 14 days).

Safety stops (change nothing in that tree): tree missing/empty, Amane unreachable, Amane rows < 90 % of
the organized STRMs, or more than MAX_ACTIONS changes in one tree (a mass "orphaning" means something
else broke). A stop is reported to Telegram and fails the unit, so it shows in `systemctl --failed`.

A STRM under <tree>/_inbox with no Amane row is not counted against those limits: Muvyo's life events
write one for every file the intake stages there, and it is left behind once Amane organizes the file
away. A big intake leaves hundreds at once, and Plex ignores _inbox, so trashing them is always safe.

  orphan-cleanup.py          # dry run, prints the plan
  orphan-cleanup.py --apply  # do it (systemd timer)
  orphan-cleanup.py --apply --only Japan   # one tree; skips the in-flight check (that guards Western's organize run)

No secrets in this file: the Amane token is read from Amane's data dir, the Plex token from Plex's own
Preferences.xml, and the Telegram pair from the unit's EnvironmentFile (unset: no notification).
"""
import json, os, re, shutil, sys, time, urllib.parse, urllib.request

DATA, TRASH = "/srv/emby/data", "/srv/emby/data/.trash"
AMANE, AMANE_TOKEN = "http://localhost:20041/api", "/srv/amane/data/token"
PLEX = "http://localhost:20031"
PLEX_PREFS = "/srv/plex/config/Library/Application Support/Plex Media Server/Preferences.xml"
# (local tree, Amane library, cloud root, depth of an organized file: <type>/<prefix>/<number>/f or <prefix>/<number>/f)
TREES = [("Japan", 1, "/media/115/Japan/", 4), ("Western", 2, "/media/115/Porn/", 3)]
MAX_ACTIONS = int(os.environ.get("ORPHAN_MAX_ACTIONS", 40))  # raise for one reviewed run, never in the unit
TRASH_DAYS = 14
APPLY = "--apply" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
SIDE = re.compile(r"(\.nfo|-mediainfo\.json|-poster\.jpg|-thumb\.jpg|-fanart\.jpg)$")
INBOX_IGNORE = "# Amane intake staging: Muvyo life events scan this folder by itself, so the root .plexignore is not enough\n*\n"


def api(method, path, body=None):
    with open(AMANE_TOKEN) as f:
        token = f.read().strip()
    req = urllib.request.Request(AMANE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as f:
        raw = f.read()
        return json.loads(raw) if raw else None


def rows(lib):
    out, off = [], 0
    while True:
        page = api("GET", f"/media?library_id={lib}&limit=200&offset={off}")
        out += page["items"]; off += 200
        if off >= page["total"]: return out


def trash(path, tree):
    dst = os.path.join(TRASH, time.strftime("%F"), tree, os.path.relpath(path, f"{DATA}/{tree}"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(path, dst)


def plex_section(tree):
    tok = re.search(r'PlexOnlineToken="([^"]+)"', open(PLEX_PREFS).read()).group(1)
    req = urllib.request.Request(PLEX + "/library/sections", headers={"Accept": "application/json", "X-Plex-Token": tok})
    for s in json.load(urllib.request.urlopen(req, timeout=30))["MediaContainer"].get("Directory", []):
        if any(l.get("path") == f"/data/{tree}" for l in s.get("Location", [])):
            return s["key"], tok
    return None, tok


def notify(stops):
    """Tell Telegram a tree was skipped. The error text never carries the URL, so the token stays out of the log."""
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set"
    text = "🧹 orphan-cleanup 停手，该目录未做任何改动\n" + "\n".join(f"• {s}" for s in stops) + \
           "\n\n查看：journalctl -u orphan-cleanup -n 20"
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60):
            return "sent"
    except Exception as e:
        return f"failed: {type(e).__name__}"


def main():
    logfile = open("/srv/amane/orphan-cleanup.log", "a")
    stops = []

    def log(**kw):
        kw.update(ts=time.strftime("%F %T"), apply=APPLY)
        line = json.dumps(kw, ensure_ascii=False); logfile.write(line + "\n"); logfile.flush(); print(line)

    def stop(tree, why):
        stops.append(f"{tree}: {why}"); log(tree=tree, stop=why)

    # Muvyo life events ask Plex to scan _inbox by itself, and such a partial scan skips the tree-root .plexignore:
    # keep one inside _inbox too (a 115 delete of _inbox would take the local folder with it).
    for tree, *_ in TREES:
        ign = f"{DATA}/{tree}/_inbox/.plexignore"
        if not os.path.exists(ign):
            os.makedirs(os.path.dirname(ign), exist_ok=True)
            open(ign, "w").write(INBOX_IGNORE)
            for x in (os.path.dirname(ign), ign): os.chown(x, 1000, 1000)
            log(tree=tree, restored=ign)

    # An organize in flight has moved the file but not yet written the STRM: never judge mid-task.
    try:
        recent = api("GET", "/tasks?limit=30")
    except Exception as e:
        stop("*", f"amane unreachable: {e}"); recent = None
    if recent is not None:
        recent = recent.get("items", recent) if isinstance(recent, dict) else recent
        if ONLY is None and any(t["status"] in ("queued", "running", "pending") for t in recent):
            log(stop="amane tasks in flight"); return 0  # routine, tomorrow's run picks it up: no alert

    for tree, lib, cloud, depth in TREES if recent is not None else []:
        if ONLY and tree != ONLY:
            continue
        root = f"{DATA}/{tree}"
        inbox = f"{root}/_inbox"
        strms, dirs = set(), {}
        for d, sub, fs in os.walk(root):
            if sub == [] or fs:
                dirs[d] = fs
            strms.update(os.path.join(d, f) for f in fs if f.endswith(".strm"))
        if not strms:
            stop(tree, "tree missing or has no STRM"); continue
        try:
            rs = rows(lib)
        except Exception as e:
            stop(tree, f"amane unreachable: {e}"); continue
        organized_strms = sum(1 for s in strms if not s.startswith(inbox + "/"))
        if len(rs) < 0.9 * organized_strms:
            stop(tree, f"amane rows {len(rs)} < 90% of STRMs {organized_strms}"); continue
        want = {}
        for r in rs:
            if r["path"].startswith(cloud):
                want[f"{root}/{r['path'][len(cloud):].rsplit('.', 1)[0]}.strm"] = r
        # a film folder: has an NFO / json / poster (extrafanart/ subfolders hold only stills and are skipped)
        a = [d for d, fs in dirs.items() if fs and d not in (root, inbox) and os.path.basename(d) != "extrafanart"
             and not any(f.endswith(".strm") for f in fs)
             and any(f.endswith((".nfo", "-mediainfo.json")) or f == "poster.jpg" for f in fs)
             and all(SIDE.search(f) or f.endswith((".jpg", ".srt", ".ass")) for f in fs)]
        b = sorted(s for s in strms if s not in want)
        staged = sum(1 for s in b if s.startswith(inbox + "/"))  # expected leftovers, see the docstring
        def organized(r):  # no flag in the API: an organized file sits at template depth in a folder named after it
            rel = r["path"][len(cloud):].split("/")
            return len(rel) == depth and rel[-1].upper().startswith(rel[-2].upper())
        c = [r for s, r in want.items() if s not in strms and organized(r)]
        total = len(a) + len(b) + len(c)
        log(tree=tree, strms=len(strms), rows=len(rs), orphan_dirs=len(a), stray_strms=len(b) - staged,
            inbox_strms=staged, dead_rows=len(c),
            sample=[x.replace(root + "/", "") for x in (a + b)[:5]] + [r["path"][-60:] for r in c[:3]])
        if total - staged > MAX_ACTIONS:
            stop(tree, f"{total - staged} actions > {MAX_ACTIONS}: needs a human look"); continue
        if not APPLY or not total:
            continue
        touched = set()
        for d in a:
            trash(d, tree); touched.add(os.path.dirname(d))
        for s in b:
            stem = s[:-5]
            for f in os.listdir(os.path.dirname(s)):
                p = os.path.join(os.path.dirname(s), f)
                if p == s or (p.startswith(stem) and SIDE.search(p)):
                    trash(p, tree)
            d = os.path.dirname(s)
            left = os.listdir(d) if os.path.isdir(d) else []
            if left and not any(f.endswith(".strm") for f in left) and all(f.endswith(".jpg") or f == "extrafanart" for f in left):
                for f in left:  # last part gone: the folder's images go too (one by one: the trash dir exists)
                    trash(os.path.join(d, f), tree)
            touched.add(d)
        for d in sorted(touched, key=len, reverse=True):  # drop folders the moves left empty (film, then prefix)
            while d != root and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d); d = os.path.dirname(d)
        for r in c:
            api("DELETE", f"/media/{r['id']}")
        log(tree=tree, done=total, items=[x.replace(root + "/", "") for x in a + b] + [r["path"] for r in c])
        key, tok = plex_section(tree)
        if key:
            scan = set()
            for d in touched:  # the emptied folders are gone: scan the nearest folder still there
                while not os.path.isdir(d): d = os.path.dirname(d)
                scan.add(d)
            for d in sorted(scan):
                urllib.request.urlopen(urllib.request.Request(
                    f"{PLEX}/library/sections/{key}/refresh?path=" + urllib.parse.quote(d.replace(DATA, "/data")),
                    headers={"X-Plex-Token": tok}), timeout=30)

    # purge trash older than TRASH_DAYS
    if APPLY and os.path.isdir(TRASH):
        for day in os.listdir(TRASH):
            if re.match(r"\d{4}-\d\d-\d\d$", day) and time.time() - time.mktime(time.strptime(day, "%Y-%m-%d")) > TRASH_DAYS * 86400:
                shutil.rmtree(os.path.join(TRASH, day)); log(purged=day)

    if stops:
        if APPLY:
            log(notify=notify(stops))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
