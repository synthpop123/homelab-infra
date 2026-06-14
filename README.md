# homelab-infra

GitOps repository for self-hosted services managed by [Komodo](https://komo.do).
Each service is a Docker Compose **Stack**; image versions are **pinned** and updated
automatically via [Renovate](https://docs.renovatebot.com) pull requests.

## Repository layout

```
.
├── stacks/                 # one folder per service
│   └── <service>/
│       └── compose.yaml    # pinned image, /srv bind mounts, allocated host port
├── komodo/
│   └── sync.toml           # Komodo Resource Sync — declares every stack (IaC)
├── renovate.json           # Renovate config (auto-detects stacks/*/compose.yaml)
└── PORTS.md                # host port registry
```

## Conventions

### File organization
- **In this repo:** exactly one stack per `stacks/<service>/compose.yaml`.
  Multi-file stacks just add more files in the same folder.
- **On the VPS:** Komodo clones this repo under `/etc/komodo/repos/`. Persistent
  **data lives under `/srv/<service>/`** via *absolute* bind mounts, so data is never
  written inside the git clone and survives re-clones and redeploys.
- **Secrets:** never commit secrets. Put them in the Stack's `environment` field in the
  Komodo UI (stored in Komodo), or in an env file referenced via `additional_env_files`.
  `.env` files are git-ignored.
- Legacy services still live under `/opt/<service>/` and are intentionally left untouched;
  they are migrated into this repo one at a time.

### Ports
See [PORTS.md](./PORTS.md). Host ports are allocated **sequentially from `20000`**, one per
published service, recorded in the registry in the same commit that adds the service.

### Versioning & updates (Renovate + Komodo)
1. Every image is pinned to an explicit version — `image: org/name:1.2.3`, never `:latest`.
2. Renovate watches every `compose.yaml` and opens a PR when a newer version is released.
3. Merging the PR to `main` triggers two repo webhooks:
   - the **Resource Sync** (`homelab`) reconciles stack *definitions* (creates newly-added stacks), and
   - the **redeploy-on-push** Procedure redeploys only the stacks whose compose *content*
     changed, via `BatchDeployStackIfChanged` — this is what rolls out the new image.

A Resource Sync alone does **not** redeploy on a compose content change (it only reconciles
definitions), which is why the Procedure exists. One webhook per resource keeps us well under
GitHub's limit of 20 webhooks per repo, so this scales to many services.

## Adding a new service

1. Create `stacks/<service>/compose.yaml`:
   - pin the image to a version,
   - put volumes under `/srv/<service>/...` (absolute paths),
   - allocate the next host port from [PORTS.md](./PORTS.md).
2. Add a `[[stack]]` block to [`komodo/sync.toml`](./komodo/sync.toml).
3. Record the port in [PORTS.md](./PORTS.md).
4. Commit & push — the Komodo Resource Sync (re)creates and deploys the stack.
