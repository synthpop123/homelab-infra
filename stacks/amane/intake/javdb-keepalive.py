"""Keep Amane's JavDB login alive: one logged-in request a week, the renewed cookies written back.

Runs as the one-shot `javdb-keepalive` service (see ../compose.yaml), started weekly by Komodo's
"JavDB Keepalive" procedure. Amane sends the cookie from its config as-is and never stores what JavDB
sends back, so the `_jdb_session` it holds only ages. A logged-in request (the cookie carries
`remember_me_token`) gets a fresh `_jdb_session` (15 days, sliding) — and a rotated `remember_me_token`
if JavDB ever sends one — which this job PATCHes into Amane's config.

It cannot log in by itself: JavDB's login form has a captcha. When the cookie no longer opens the
profile page it sends a Telegram message instead — log in on javdb.com with 「记住我」 ticked and paste the
cookies into Amane (javdb site settings → cookie). The message and the log never carry cookie values.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("AMANE_API", "http://amane:8000/api")
TOKEN_FILE = "/token"
PROFILE = "https://javdb.com/users/profile"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
# Cookies worth carrying back; JavDB also sets UI ones (theme, list_mode) the scraper has no use for.
KEEP = {"_jdb_session", "remember_me_token"}


def say(*parts):
    print(time.strftime("%F %T"), *parts, flush=True)


def api(method, path, body=None):
    with open(TOKEN_FILE) as f:
        token = f.read().strip()
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as f:
        return json.loads(f.read() or "null")


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        say("telegram: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set")
        return
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=json.dumps({"chat_id": chat, "text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).close()
    except OSError as err:  # never print the URL: it holds the bot token
        say("telegram:", type(err).__name__, getattr(err, "code", ""))


def fail(why, relogin=True):
    say("FAIL:", why)
    text = f"⚠️ Amane JavDB cookie：{why}"
    if relogin:
        text += ("\n在 javdb.com 勾选「记住我」登录，把 cookie 填回 Amane（设置里 javdb 站点的 cookie）。"
                 "失效期间 FC2 详情页刮不到，会退到 airav/freejavbt。")
    telegram(text)
    sys.exit(1)


def main():
    scraping = api("GET", "/config")["scraping"]
    cookie = dict(scraping["site_config"]["javdb"].get("cookie") or {})
    if "remember_me_token" not in cookie:
        fail("cookie 里没有 remember_me_token（登录时没勾「记住我」？）")
    req = urllib.request.Request(PROFILE, headers={"User-Agent": UA,
                                                   "Cookie": "; ".join(f"{k}={v}" for k, v in cookie.items())})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            final, headers = f.url, f.headers
    except urllib.error.HTTPError as err:  # 403 is usually Cloudflare, not the login
        fail(f"javdb.com 返回 HTTP {err.code}，没能核验登录状态（403 多半是 Cloudflare，cookie 未必失效）",
             relogin=False)
    except OSError as err:
        say("javdb.com unreachable:", type(err).__name__, err)
        sys.exit(1)
    if "/login" in final:
        fail("已失效（访问个人页被跳到登录页）")
    renewed = {}
    for header in headers.get_all("Set-Cookie") or []:
        name, _, value = header.split(";", 1)[0].partition("=")
        if name in KEEP and value and cookie.get(name) != value:
            renewed[name] = value
    if not renewed:
        say("logged in; JavDB sent no new session cookie, nothing to write")
        return
    cookie.update(renewed)
    scraping["site_config"]["javdb"]["cookie"] = cookie
    api("PATCH", "/config", {"scraping": scraping})
    say("logged in; renewed in Amane:", ", ".join(sorted(renewed)))


if __name__ == "__main__":
    main()
