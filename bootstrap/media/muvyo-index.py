#!/usr/bin/env python3
"""Keep Muvyo's 115 file index (file_info) current for the Amane trees /Porn and /Japan.

Muvyo's life-event rules /Japan, /Porn map a 115 delete event to a path through that index; a folder
it has never indexed (Amane's organizes add the file, not its folder) is silently ignored, so deleting
a film folder in the 115 app would leave its STRM. Full-sync is incremental: it exports the tree once
(cookie) and only resolves folders missing from the index (~1.5 s each, Muvyo-throttled).
Runs daily via muvyo-index.timer (09:30, after the 08:30 Media Intake). Log: /srv/amane/muvyo-index.log

No secrets in this file: the Muvyo API key is read from KEY_FILE, a root-only file on the host.
"""
import json, sys, time, urllib.error, urllib.request

ROOTS = sys.argv[1:] or ["/Porn", "/Japan"]
MUVYO = "http://localhost:20038/api/v1"
KEY_FILE = "/root/.muvyo.api"
LOG = "/srv/amane/muvyo-index.log"


def mv(method, path, body=None):
    """One Muvyo API call, as parsed JSON (an error reply included); None when there is none (Muvyo restarting)."""
    with open(KEY_FILE) as f:
        key = "".join(f.read().split())
    req = urllib.request.Request(MUVYO + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        try:
            with urllib.request.urlopen(req, timeout=120) as f:
                raw = f.read()
        except urllib.error.HTTPError as err:
            raw = err.read()
        return json.loads(raw or "null")
    except (OSError, ValueError):
        return None


def log(**kw):
    kw["ts"] = time.strftime("%F %T")
    open(LOG, "a").write(json.dumps(kw, ensure_ascii=False) + "\n")


def status():
    return (mv("GET", "/files/info/full-sync/status?storage=115-1") or {}).get("data") or {}


if __name__ == "__main__":
    for root in ROOTS:
        while status().get("running"):  # one sync at a time; never attach to someone else's
            time.sleep(30)
        r = mv("POST", "/files/info/full-sync", {"paths": [root], "overwrite": False, "sync_non_media": True,
                                                 "dry_run": False, "storage": "115-1"})
        log(root=root, start=(r or {}).get("message"))
        time.sleep(15)
        while (s := status()).get("running"):
            time.sleep(30)
        log(root=root, result=s.get("message"), errors=s.get("errors"), new=s.get("new_files"))
