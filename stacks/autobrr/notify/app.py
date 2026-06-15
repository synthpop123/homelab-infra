"""autobrr -> Telegram movie-release notifier.

A small standalone service so autobrr can keep its stock image (no in-container
Python). Instead of an Exec action running a script inside the autobrr container,
an autobrr "Webhook" action POSTs the matched release here; we enrich it with TMDB
metadata and post a rich MarkdownV2 card (poster + inline links) to a Telegram channel.

Endpoints:
  POST /notify   autobrr webhook target. Replies 200 immediately and does the TMDB
                 lookup + Telegram send in the background, so autobrr never blocks.
  GET  /healthz  liveness + config sanity for container / uptime checks.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

import requests
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel
from requests.adapters import HTTPAdapter
from tmdbv3api import Movie, Search, TMDb
from urllib3.util.retry import Retry

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("autobrr-notify")

TELEGRAM_API = "https://api.telegram.org"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/original"


@dataclass
class Config:
    """Runtime configuration, sourced from the environment (Komodo Variables)."""

    tmdb_api_key: str = field(default_factory=lambda: os.getenv("TMDB_API_KEY", ""))
    tmdb_language: str = field(default_factory=lambda: os.getenv("TMDB_LANGUAGE", "zh-CN"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_channel_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHANNEL_ID", ""))

    def missing(self) -> list[str]:
        """Required keys that are still unset (used by /healthz and startup)."""
        required = {
            "TMDB_API_KEY": self.tmdb_api_key,
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "TELEGRAM_CHANNEL_ID": self.telegram_channel_id,
        }
        return [name for name, value in required.items() if not value]


class Release(BaseModel):
    """Payload from an autobrr Webhook action (one matched release).

    Field names mirror the macros wired in the action's Data box, e.g.:
      {"torrent_name":"{{ .TorrentName | js }}","indexer_name":"{{ .FilterName | js }}",
       "group_name":"{{ .Group | js }}","release_year":"{{ .Year }}",
       "parsed_title":"{{ .Title | js }}","file_size":{{ .Size }}}
    Only torrent_name + parsed_title are required; everything else is best-effort.
    """

    torrent_name: str
    parsed_title: str
    indexer_name: str = ""
    group_name: str = ""
    release_year: str = ""
    file_size: int = 0
    meta_imdb: Optional[str] = None


def _retrying_session() -> requests.Session:
    """A requests session that retries transient TMDB/Telegram 5xx errors."""
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class MovieClient:
    """TMDB lookups: resolve a release to a TMDB id, then fetch localized details."""

    def __init__(self, config: Config):
        self.config = config
        self.tmdb = TMDb()
        self.tmdb.api_key = config.tmdb_api_key
        self.tmdb.language = config.tmdb_language
        self.movie = Movie()
        self.search = Search()
        self.session = _retrying_session()
        self.movie.session = self.session
        self.search.session = self.session

    @lru_cache(maxsize=256)
    def search_movie(self, title: str, year: Optional[str]) -> list[Any]:
        return self.search.movies(title, year=year) if year else self.search.movies(title)

    @lru_cache(maxsize=256)
    def find_by_imdb(self, imdb_id: str) -> Optional[dict]:
        resp = self.session.get(
            f"https://api.themoviedb.org/3/find/{imdb_id}",
            params={"api_key": self.config.tmdb_api_key, "external_source": "imdb_id"},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("movie_results") or []
        return results[0] if results else None

    @lru_cache(maxsize=256)
    def details(self, tmdb_id: int, language: Optional[str] = None) -> Any:
        """Movie details with credits + images, optionally in another language."""
        if language and language != self.tmdb.language:
            previous, self.tmdb.language = self.tmdb.language, language
            try:
                return self.movie.details(tmdb_id, append_to_response="credits,images")
            finally:
                self.tmdb.language = previous
        return self.movie.details(tmdb_id, append_to_response="credits,images")

    def resolve_id(self, release: Release) -> Optional[int]:
        """Find a TMDB id from the IMDB id (if present) or a title+year search."""
        if release.meta_imdb:
            hit = self.find_by_imdb(release.meta_imdb)
            if hit:
                return hit["id"]
            log.warning("IMDB id %s not found; falling back to title/year", release.meta_imdb)
        results = self.search_movie(release.parsed_title, release.release_year or None)
        return results[0].id if results else None


class MessageFormatter:
    """Render the Telegram MarkdownV2 message body."""

    # Characters that MarkdownV2 requires to be backslash-escaped.
    SPECIAL = "_*[]()~`>#+-=|{}.!"

    @classmethod
    def escape(cls, text: str) -> str:
        text = str(text)
        for char in cls.SPECIAL:
            text = text.replace(char, f"\\{char}")
        return text

    @staticmethod
    def names(people: list[Any], max_count: int = 3, job: Optional[str] = None) -> str:
        """Up to `max_count` person names; if `job` is given, only matching crew."""
        out: list[str] = []
        for person in people:
            if len(out) >= max_count:
                break
            if job and getattr(person, "job", None) != job:
                continue
            out.append(person.name)
        return ", ".join(out)

    @staticmethod
    def file_info(file_size: int, runtime: Optional[int]) -> tuple[str, str, str]:
        """Human-readable size / duration / bitrate (bitrate needs a runtime)."""
        size = f"{file_size / 1024 ** 3:.2f} GiB" if file_size else "未知"
        if file_size and runtime:
            duration = f"{runtime} 分钟"
            bitrate = f"{file_size * 8 / (runtime * 60) / 1_000_000:.2f} Mbps"
        else:
            duration = f"{runtime} 分钟" if runtime else "未知"
            bitrate = "未知"
        return size, duration, bitrate

    def rich(self, data: dict[str, Any]) -> str:
        """Full card: TMDB metadata, poster preview, overview."""
        esc = self.escape
        info = f"{esc(data['size'])} / {esc(data['duration'])} / {esc(data['bitrate'])}"
        if data["poster_url"]:
            # A zero-width char carrying a hidden link makes Telegram show the poster.
            info += f"[\u200b]({data['poster_url']})"
        rows = [
            ("*名称*：", f"{esc(data['title'])} \\({esc(data['year'])}\\)"),
            ("*导演*：", esc(data["director"])),
            ("*演员*：", esc(data["starring"])),
            ("*类型*：", esc(", ".join(data["genres"]))),
            ("*标题*：", f"__{esc(data['torrent_name'])}__"),
            ("*信息*：", info),
        ]
        body = f"\\#{esc(data['indexer'])} \\#{esc(data['group'])}\n"
        body += "\n".join(f"{label}{content}" for label, content in rows)
        if data["overview"]:
            body += f"\n\n> {esc(data['overview'])}"
        return body

    def plain(self, release: Release) -> str:
        """Fallback when TMDB has no match — still notify, just without metadata."""
        esc = self.escape
        size = f"{release.file_size / 1024 ** 3:.2f} GiB" if release.file_size else "未知"
        return (
            f"\\#{esc(release.indexer_name)} \\#{esc(release.group_name)}\n"
            f"*标题*：__{esc(release.torrent_name)}__\n"
            f"*信息*：{esc(size)}"
        )


class TelegramNotifier:
    """Post messages to a Telegram channel via the Bot API."""

    def __init__(self, config: Config):
        self.config = config
        self.session = _retrying_session()

    def send(self, text: str, links: Optional[dict[str, str]] = None) -> None:
        payload: dict[str, Any] = {
            "chat_id": self.config.telegram_channel_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "link_preview_options": {
                "is_disabled": False,
                "prefer_large_media": True,
                "show_above_text": True,
            },
        }
        if links:
            buttons = [{"text": name, "url": url} for name, url in links.items() if url]
            if buttons:
                payload["reply_markup"] = {"inline_keyboard": [buttons]}
        resp = self.session.post(
            f"{TELEGRAM_API}/bot{self.config.telegram_bot_token}/sendMessage",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()


CONFIG = Config()
MOVIES = MovieClient(CONFIG)
FORMATTER = MessageFormatter()
NOTIFIER = TelegramNotifier(CONFIG)


def process_release(release: Release) -> None:
    """Enrich a release with TMDB data and notify; degrade to a plain card on any failure."""
    missing = CONFIG.missing()
    if missing:
        log.error("cannot notify, missing config: %s", ", ".join(missing))
        return
    try:
        tmdb_id = MOVIES.resolve_id(release)
        if tmdb_id is None:
            log.warning("no TMDB match for %r (%s); sending plain card",
                        release.parsed_title, release.release_year)
            NOTIFIER.send(FORMATTER.plain(release))
            return

        localized = MOVIES.details(tmdb_id)
        english = MOVIES.details(tmdb_id, language="en-US")
        credits = localized.credits
        size, duration, bitrate = FORMATTER.file_info(
            release.file_size, getattr(localized, "runtime", 0)
        )
        backdrop = getattr(english, "backdrop_path", None) or getattr(english, "poster_path", None)
        imdb_id = getattr(localized, "imdb_id", None)
        data = {
            "title": localized.title,
            "year": (getattr(localized, "release_date", "") or "").split("-")[0] or release.release_year,
            "overview": localized.overview or getattr(english, "overview", ""),
            "genres": [genre.name for genre in localized.genres],
            "director": FORMATTER.names(credits.crew, job="Director"),
            "starring": FORMATTER.names(credits.cast),
            "size": size,
            "duration": duration,
            "bitrate": bitrate,
            "indexer": release.indexer_name,
            "group": release.group_name,
            "torrent_name": release.torrent_name,
            "poster_url": f"{TMDB_IMAGE_BASE}{backdrop}" if backdrop else "",
        }
        links = {
            "TMDB": f"https://www.themoviedb.org/movie/{tmdb_id}",
            "IMDB": f"https://www.imdb.com/title/{imdb_id}" if imdb_id else "",
            "Letterboxd": f"https://letterboxd.com/imdb/{imdb_id}/" if imdb_id else "",
            "Douban": f"https://search.douban.com/movie/subject_search?search_text={imdb_id}" if imdb_id else "",
        }
        NOTIFIER.send(FORMATTER.rich(data), links)
        log.info("notified: %s (%s)", data["title"], data["year"])
    except Exception:
        log.exception("notify failed for %r; attempting plain fallback", release.torrent_name)
        try:
            NOTIFIER.send(FORMATTER.plain(release))
        except Exception:
            log.exception("plain fallback also failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = CONFIG.missing()
    if missing:
        log.warning("starting with INCOMPLETE config (missing: %s)", ", ".join(missing))
    else:
        log.info("autobrr-notify ready (tmdb language=%s)", CONFIG.tmdb_language)
    yield


app = FastAPI(title="autobrr-notify", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "config_complete": not CONFIG.missing()}


@app.post("/notify")
def notify(release: Release, background: BackgroundTasks) -> dict[str, Any]:
    log.info("queued: %s", release.torrent_name)
    background.add_task(process_release, release)
    return {"accepted": True}
