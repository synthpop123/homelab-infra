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
