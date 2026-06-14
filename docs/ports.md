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

**Next free: `20011`**

> Only the published service consumes a number. Bundled databases/caches/search behind a stack
> (Postgres, Redis, Elasticsearch for deeix-chat, cloudreve, new-api, mastodon) are internal-only
> (no host port).
