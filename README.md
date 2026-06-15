# homelab-infra

GitOps for self-hosted services managed by [Komodo](https://komo.do). Each service is a Docker
Compose **Stack** with **pinned** image versions, updated automatically via
[Renovate](https://docs.renovatebot.com) pull requests.

## Layout

```
.
├── stacks/<service>/compose.yaml   # one folder per service: pinned image, /srv binds, host port
├── komodo/sync.toml                # Komodo Resource Sync + redeploy Procedure (IaC)
├── bootstrap/komodo/               # Komodo itself (Core/Periphery/Mongo): deployed by hand
├── renovate.json                   # Renovate config (auto-detects stacks/*/compose.yaml)
└── docs/                           # conventions, ports, workflow, migration, backup runbooks
```

## Services

| Service | URL | Port | Description |
|---------|-----|------|-------------|
| [wallos](./stacks/wallos) | [wallos.lkwplus.com](https://wallos.lkwplus.com) | 20000 | Subscription tracker |
| [calibre-web-automated](./stacks/calibre-web-automated) | [calibre.lkwplus.com](https://calibre.lkwplus.com) | 20001 | Ebook library (CWA) |
| [deeix-chat](./stacks/deeix-chat) | [ai.lkwplus.com](https://ai.lkwplus.com) | 20002 | AI chat (app + Postgres + Redis) |
| [drizzle-gateway](./stacks/drizzle-gateway) | [db.lkwplus.com](https://db.lkwplus.com) | 20003 | Drizzle Gateway (DB studio) |
| [cloudreve](./stacks/cloudreve) | [cloud.lkwplus.com](https://cloud.lkwplus.com) | 20004 | Cloudreve cloud storage (+ Postgres + Redis) |
| [koito](./stacks/koito) | [music.lkwplus.com](https://music.lkwplus.com) | 20005 / 20006 | Koito scrobble server + multi-scrobbler |
| [new-api](./stacks/new-api) | [api.lkwplus.com](https://api.lkwplus.com) | 20007 | LLM API gateway (app + Postgres + Redis) |
| [opengist](./stacks/opengist) | [gist.lkwplus.com](https://gist.lkwplus.com) | 20008 | Git-powered pastebin |
| [mastodon](./stacks/mastodon) | [mastodon.lkwplus.com](https://mastodon.lkwplus.com) | 20009 / 20010 | Fediverse server (web + streaming + sidekiq + Postgres/Redis/ES) |
| [beszel](./stacks/beszel) | [beszel.lkwplus.com](https://beszel.lkwplus.com) | 20011 | Server monitoring (hub + agent) |
| [immich](./stacks/immich) | [immich.lkwplus.com](https://immich.lkwplus.com) | 20012 | Photo/video backup (server + ML + Postgres/Valkey) |
| [karakeep](./stacks/karakeep) | [karakeep.lkwplus.com](https://karakeep.lkwplus.com) | 20013 | Bookmarks (web + Chrome + Meilisearch) |
| [clouddrive2](./stacks/clouddrive2) | [cd.lkwplus.com](https://cd.lkwplus.com) | host | Cloud storage → FUSE mount (host net) |
| [n8n](./stacks/n8n) | [n8n.lkwplus.com](https://n8n.lkwplus.com) | 20014 | Workflow automation (+ dedicated Postgres) |
| [memos](./stacks/memos) | [memos.lkwplus.com](https://memos.lkwplus.com) | 20015 | Notes (+ dedicated Postgres) |
| [seerr](./stacks/seerr) | [seerr.lkwplus.com](https://seerr.lkwplus.com) | 20016 | Media requests (+ dedicated Postgres) |
| [openwebui](./stacks/openwebui) | [chat.lkwplus.com](https://chat.lkwplus.com) | 20017 | LLM chat UI (+ dedicated Postgres) |
| [gitea](./stacks/gitea) | [git.lkwplus.com](https://git.lkwplus.com) | 20018 | Git hosting (+ dedicated Postgres; SSH on 222) |
| [torrent](./stacks/torrent) | [qbit.lkwplus.com](https://qbit.lkwplus.com) | 20019 / 20020 | qBittorrent + qui WebUI manager (BT on 65231) |

## Docs

- [Conventions](./docs/conventions.md) — file layout, `/srv` data, ports, networks, env vars, volumes
- [Port registry](./docs/ports.md)
- [Update & deploy workflow](./docs/workflow.md) — Komodo sync + redeploy procedure + Renovate
- [Migrating a service](./docs/migration.md) — runbook for moving an existing `/opt` service in
- [Backup & restore](./docs/backup-restore.md) — the three data layers, Komodo's built-in DB backup, `/srv` + off-site, restore runbooks

## Add a service

1. Create `stacks/<service>/compose.yaml` — pin the image, put volumes under `/srv/<service>/…`,
   take the next free port from [docs/ports.md](./docs/ports.md).
2. Add a `[[stack]]` block to [`komodo/sync.toml`](./komodo/sync.toml) and record the port.
3. Commit & push — the `Redeploy On Push` procedure runs the `homelab` sync (creates the stack
   definition) and then deploys what changed, all in one ordered run. A brand-new stack comes up on
   its first push (and later version bumps redeploy automatically) — see [workflow.md](./docs/workflow.md).

## License

[MIT](./LICENSE)
