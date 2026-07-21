# letterboxd-plex-sync, patched for Letterboxd's Cloudflare wall.
#
# Since ~2026-02 Letterboxd fronts /user/login.do and /data/export with Cloudflare TLS-
# fingerprint checks (upstream issue #18). The stock image's cloudscraper session gets a
# hard 403 ("Just a moment..."), while curl_cffi impersonating a real browser's TLS
# fingerprint passes cleanly (verified from this host: login -> {"result":"success"},
# export -> zip).
#
# The impersonation target is a moving one: `chrome` passed from 2026-02 until ~2026-07-14,
# then Cloudflare started 403'ing every chrome* profile too (broke the 2026-07-20 weekly
# run). `safari184` and `firefox135` still pass (probed in-container 2026-07-22); safari184
# is what ships below. If a weekly run dies again with JSONDecodeError on login, probe the
# other curl_cffi targets and swap.
#
# So: take the upstream image (pinned by digest — Renovate bumps it via this FROM line;
# after merging such a bump, deploy the plex stack manually so `--build` picks it up, see
# AGENTS.md), install curl_cffi, and swap letterboxd_stats' session for a browser-
# impersonating one. The patch asserts on the exact upstream source lines, so if a digest
# bump reworks web_scraper.py the build fails loudly instead of silently regressing.
FROM treysu/letterboxd-plex-sync:latest@sha256:67a8b5dbe9b54a3a3261a93d367fc9a98abec1fb3efdf48f36b831d38080e6d1

RUN pip install --no-cache-dir curl_cffi==0.15.0

RUN python - <<'PY'
from pathlib import Path

p = Path("/usr/local/lib/python3.10/site-packages/letterboxd_stats/web_scraper.py")
src = p.read_text()
subs = [
    (
        "import cloudscraper",
        "from curl_cffi import requests as curl_requests",
    ),
    (
        "self.session = cloudscraper.create_scraper()",
        'self.session = curl_requests.Session(impersonate="safari184")',
    ),
]
for old, new in subs:
    assert src.count(old) == 1, f"patch target not found exactly once: {old!r}"
    src = src.replace(old, new)
p.write_text(src)
print("patched web_scraper.py: cloudscraper -> curl_cffi")
PY
