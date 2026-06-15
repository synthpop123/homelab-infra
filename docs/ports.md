# Port Registry

Single source of truth for **host** port allocation across Komodo-managed stacks.

## Scheme

- Host ports are allocated **sequentially from a base**, one number per published service.
- **Base: `20000`**, incrementing by 1 → `20000`, `20001`, `20002`, …
- The range **`20000–20999`** is reserved for this scheme (1000 slots) and is currently
  free of conflicts with the legacy services still running under `/opt`
  (those use an ad-hoc `13xxx` / `1<port>` convention and are left untouched for now).
- Only **published** services (those exposing a host port) consume a number.
  Internal-only containers (databases, redis, etc.) get no host port.
- When adding a service: take the next free number, **record it here in the same commit**,
  and use it in that stack's `compose.yaml`.

## Allocations

| Port  | Service               | Container port | Notes                       |
|-------|-----------------------|----------------|-----------------------------|
| 20000 | wallos                | 80             | Subscription tracker        |
| 20001 | calibre-web-automated | 8083           | Calibre-Web-Automated (CWA) |
| 20002 | deeix-chat            | 8080           | DEEIX Chat (AI chat)        |
| 20003 | drizzle-gateway       | 4983           | Drizzle Gateway (DB studio) |
| 20004 | cloudreve             | 5212           | Cloudreve (cloud storage)   |
| 20005 | koito                 | 4110           | Koito (music scrobble svr)  |
| 20006 | multi-scrobbler       | 9078           | multi-scrobbler -> koito    |
| 20007 | new-api               | 3000           | new-api (LLM gateway)       |
| 20008 | opengist              | 6157           | Opengist (git pastebin)     |
| 20009 | mastodon (web)        | 3000           | Mastodon web/API            |
| 20010 | mastodon (streaming)  | 4000           | Mastodon streaming API      |
| 20011 | beszel                | 8090           | Beszel monitoring hub       |
| 20012 | immich                | 2283           | Immich photo backup         |
| 20013 | karakeep              | 3000           | Karakeep bookmarks          |
| 20014 | n8n                   | 5678           | n8n workflow automation     |
| 20015 | memos                 | 5230           | Memos notes                 |
| 20016 | seerr                 | 5055           | Seerr media requests        |
| 20017 | openwebui             | 8080           | Open WebUI (LLM chat)       |
| 20018 | gitea                 | 3000           | Gitea (HTTP)                |
| 20019 | qbittorrent           | 8081           | qBittorrent WebUI (torrent) |
| 20020 | qui                   | 7476           | qui — qBittorrent manager   |
| 20021 | emby                  | 8096           | Emby media server           |

**Next free: `20022`**

> Only the published service consumes a number. Bundled databases/caches/search/ML behind a stack
> (Postgres, Redis/Valkey, Elasticsearch, immich ML, karakeep meilisearch/chrome) are internal-only
> (no host port).
>
> **Outside the scheme** (host-networked; ports fixed by the app, not the registry):
> - `beszel-agent` listens on host port **45876**.
> - `clouddrive2` runs with `network_mode: host` (web UI on its built-in port, FUSE mounts under `/mnt`).
> - `gitea` SSH stays on host port **222** (clone URLs), separate from its HTTP port above.
> - `qbittorrent` BitTorrent listen port stays on host port **65231** (tcp + udp), separate from its WebUI above.
