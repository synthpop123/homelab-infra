# letterboxd-plex-sync, patched for Letterboxd's Cloudflare wall.
#
# Since ~2026-02 Letterboxd fronts /user/login.do and /data/export with Cloudflare TLS-
# fingerprint checks (upstream issue #18). The stock image's cloudscraper session gets a
# hard 403 ("Just a moment..."), while curl_cffi impersonating a real browser's TLS
# fingerprint passes cleanly (verified from this host: login -> {"result":"success"},
# export -> zip).
#
# The impersonation target is a moving one: Cloudflare keeps retiring older browser
# fingerprints. `chrome` passed 2026-02 → ~07-14, `safari184` 07-22 → ~10-12; by 2026-11-04
# only the newest profiles of curl_cffi 0.17 (chrome152 / safari2601 / firefox154) got through
# /data/export from this host. So the target is no longer baked in here: the patched Connector
# walks LB_IMPERSONATE (comma-separated, set in compose.yaml) and keeps the first profile whose
# home page and /data/export both answer 200 without a challenge. When every profile fails the
# run dies with "Cloudflare challenged every LB_IMPERSONATE target" — let Renovate bump
# CURL_CFFI_VERSION (compose build arg) for newer profiles, then refresh LB_IMPERSONATE.
#
# So: take the upstream image (pinned by digest — Renovate bumps it via this FROM line;
# after merging such a bump, deploy the plex stack manually so `--build` picks it up, see
# AGENTS.md), install curl_cffi, and swap letterboxd_stats' session for a browser-
# impersonating one. The patch asserts on the exact upstream source lines, so if a digest
# bump reworks web_scraper.py the build fails loudly instead of silently regressing.
FROM treysu/letterboxd-plex-sync:latest@sha256:67a8b5dbe9b54a3a3261a93d367fc9a98abec1fb3efdf48f36b831d38080e6d1

# Version pinned in compose.yaml (build.args), where Renovate tracks it.
ARG CURL_CFFI_VERSION
RUN pip install --no-cache-dir "curl_cffi==${CURL_CFFI_VERSION}"

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
        "self.session = _impersonating_session()",
    ),
]
for old, new in subs:
    assert src.count(old) == 1, f"patch target not found exactly once: {old!r}"
    src = src.replace(old, new)
src += '''

def _impersonating_session():
    """First LB_IMPERSONATE profile Cloudflare lets through (patched in by the Dockerfile)."""
    targets = [t.strip() for t in os.environ.get("LB_IMPERSONATE", "chrome").split(",") if t.strip()]
    for target in targets:
        session = curl_requests.Session(impersonate=target)
        statuses = []
        for url in (URL, DATA_PAGE):
            res = session.get(url)
            statuses.append(res.status_code if not res.headers.get("cf-mitigated") else f"{res.status_code}/challenge")
        if statuses == [200, 200] and session.cookies.get("com.xk72.webparts.csrf"):
            print(f"letterboxd: curl_cffi impersonate={target}")
            return session
        print(f"letterboxd: impersonate={target} rejected {statuses}")
    raise ConnectionError(f"Cloudflare challenged every LB_IMPERSONATE target: {targets}")
'''
p.write_text(src)
print("patched web_scraper.py: cloudscraper -> curl_cffi (LB_IMPERSONATE fallback)")
PY
