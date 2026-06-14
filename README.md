# homelab-infra

GitOps for self-hosted services managed by [Komodo](https://komo.do). Each service is a Docker
Compose **Stack** with **pinned** image versions, updated automatically via
[Renovate](https://docs.renovatebot.com) pull requests.

## Layout

```
.
├── stacks/<service>/compose.yaml   # one folder per service: pinned image, /srv binds, host port
├── komodo/sync.toml                # Komodo Resource Sync + redeploy Procedure (IaC)
├── renovate.json                   # Renovate config (auto-detects stacks/*/compose.yaml)
└── docs/                           # conventions, ports, workflow, migration runbook
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| [wallos](./stacks/wallos) | 20000 | Subscription tracker |
| [calibre-web-automated](./stacks/calibre-web-automated) | 20001 | Ebook library (CWA) |
| [deeix-chat](./stacks/deeix-chat) | 20002 | AI chat (app + Postgres + Redis) |
| [drizzle-gateway](./stacks/drizzle-gateway) | 20003 | Drizzle Gateway (DB studio) |
| [cloudreve](./stacks/cloudreve) | 20004 | Cloudreve cloud storage (+ Postgres + Redis) |
| [koito](./stacks/koito) | 20005 / 20006 | Koito scrobble server + multi-scrobbler |
| [new-api](./stacks/new-api) | 20007 | LLM API gateway (app + Postgres + Redis) |
| [opengist](./stacks/opengist) | 20008 | Git-powered pastebin |
| [mastodon](./stacks/mastodon) | 20009 / 20010 | Fediverse server (web + streaming + sidekiq + Postgres/Redis/ES) |
| [beszel](./stacks/beszel) | 20011 | Server monitoring (hub + agent) |
| [immich](./stacks/immich) | 20012 | Photo/video backup (server + ML + Postgres/Valkey) |
| [karakeep](./stacks/karakeep) | 20013 | Bookmarks (web + Chrome + Meilisearch) |
| [clouddrive2](./stacks/clouddrive2) | host | Cloud storage → FUSE mount (host net) |
| [n8n](./stacks/n8n) | 20014 | Workflow automation (+ dedicated Postgres) |
| [memos](./stacks/memos) | 20015 | Notes (+ dedicated Postgres) |

## Docs

- [Conventions](./docs/conventions.md) — file layout, `/srv` data, ports, networks, env vars, volumes
- [Port registry](./docs/ports.md)
- [Update & deploy workflow](./docs/workflow.md) — Komodo sync + redeploy procedure + Renovate
- [Migrating a service](./docs/migration.md) — runbook for moving an existing `/opt` service in

## Add a service

1. Create `stacks/<service>/compose.yaml` — pin the image, put volumes under `/srv/<service>/…`,
   take the next free port from [docs/ports.md](./docs/ports.md).
2. Add a `[[stack]]` block to [`komodo/sync.toml`](./komodo/sync.toml) and record the port.
3. Commit & push — the `homelab` sync creates the stack definition and `Redeploy On Push` deploys
   it (and later version bumps). If a brand-new stack doesn't come up on the first push, deploy it
   once from the Komodo UI — see [workflow.md](./docs/workflow.md).
