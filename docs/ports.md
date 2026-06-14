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

**Next free: `20003`**

> Only the published service consumes a number. deeix-chat's bundled Postgres and Redis are
> internal-only (no host port).
