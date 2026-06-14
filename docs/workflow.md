# Update & deploy workflow

How a change flows from git to a running container.

## Components (defined as code in [`komodo/sync.toml`](../komodo/sync.toml))
- **Resource Sync `homelab`** — reads `komodo/sync.toml` and reconciles resource *definitions*
  (creates/updates Stacks). Every stack is `deploy = false`, so the sync **never deploys** — that
  keeps it from racing the procedure for a stack's deploy lock (the "Resource is busy" error).
- **Procedure `Redeploy On Push`** — the **sole deployer**: runs `BatchDeployStackIfChanged` with
  pattern `*`, deploying only the stacks whose compose content actually changed.

## Webhooks (on the GitHub repo)
Two `push` webhooks, each with content-type `application/json` and the `KOMODO_WEBHOOK_SECRET`:

1. Resource Sync → `…/listener/github/sync/homelab/sync`
2. Procedure → `…/listener/github/procedure/<id-or-name>/main`

Copy the exact URL from each resource's page in the Komodo UI (it handles the id/encoding). Two
webhooks is well under GitHub's limit of 20 per repo, and one procedure covers every stack — so
this scales to many services.

## How Renovate detects new versions
- Renovate is **not** built into GitHub and needs **no CI / GitHub Actions** in this repo. Install
  the **Mend-hosted Renovate App** from the GitHub Marketplace and grant it access to this (private) repo.
- Mend's own infrastructure then runs Renovate on a schedule (~hourly): it temporarily clones the
  repo, the **docker-compose manager** parses every `image: name:tag`, queries the upstream registry
  (Docker Hub / GHCR) for newer tags, and opens a PR bumping the tag. It does not retain your code.
- The first run opens a "Configure Renovate" onboarding PR; after you merge it, Renovate creates a
  **Dependency Dashboard** issue and starts proposing updates.
- Self-hosting (npm package / Docker image / GitHub Action on an hourly cron) is the alternative —
  that one *would* need CI. The hosted app is simpler and is what this repo assumes.

## End-to-end

```
Renovate opens PR (bump image tag)
        │  review + merge to main
        ▼
GitHub push webhooks ──► Resource Sync `homelab`        (reconciles stack definitions; never deploys)
                   └───► Procedure `Redeploy On Push` ──► BatchDeployStackIfChanged
                                                          └─► deploys only the changed stacks
```

> **New stacks:** the sync only *defines* a new stack; the procedure deploys it. The two webhooks
> run in parallel, so the procedure can fire before the definition exists — a brand-new stack may
> therefore not come up on its very first push. If that happens, deploy it once from the Komodo UI;
> every later push redeploys it automatically. (Existing stacks never hit this — they're already
> defined, so the procedure just redeploys them.)
