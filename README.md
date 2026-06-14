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
└── docs/                           # conventions, port registry, workflow
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| [wallos](./stacks/wallos) | 20000 | Subscription tracker |
| [calibre-web-automated](./stacks/calibre-web-automated) | 20001 | Ebook library (CWA) |

## Docs

- [Conventions](./docs/conventions.md) — file layout, `/srv` data, ports, networks, env vars, volumes
- [Port registry](./docs/ports.md)
- [Update & deploy workflow](./docs/workflow.md) — Komodo sync + redeploy procedure + Renovate

## Add a service

1. Create `stacks/<service>/compose.yaml` — pin the image, put volumes under `/srv/<service>/…`,
   take the next free port from [docs/ports.md](./docs/ports.md).
2. Add a `[[stack]]` block to [`komodo/sync.toml`](./komodo/sync.toml) and record the port.
3. Commit & push — the `homelab` sync creates and deploys it; `Redeploy On Push` rolls out later
   version bumps.
