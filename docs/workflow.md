# Update & deploy workflow

How a change flows from git to a running container.

## Components (defined as code in [`komodo/sync.toml`](../komodo/sync.toml))
- **Resource Sync `homelab`** — reads `komodo/sync.toml` and reconciles resource *definitions*
  (creates/updates Stacks). Every stack is `deploy = false`, so the sync **never deploys** — that
  keeps it from racing the procedure for a stack's deploy lock (the "Resource is busy" error).
- **Procedure `Redeploy On Push`** — the **single git-push entry point** and the **sole deployer**.
  It runs two **sequential** stages: **(1)** `RunSync homelab` reconciles definitions, then
  **(2)** `BatchDeployStackIfChanged *` deploys only the stacks whose configured `file_paths`
  changed.
  Because stage 2 waits for stage 1, a brand-new stack's definition exists before deploy — so it
  comes up on its **first** push (no manual UI deploy, no empty "trigger" commit).

## Webhooks (on the GitHub repo)
**One** `push` webhook (content-type `application/json`, secret `KOMODO_WEBHOOK_SECRET`):

- Procedure `Redeploy On Push` → `…/listener/github/procedure/<id>/main`

Copy the exact URL from the Procedure's page in the Komodo UI (it handles the id/encoding). The
**Resource Sync `homelab`** has a webhook URL too (`…/listener/github/sync/<id>/sync`), but it is
intentionally **left disabled / not added** — the procedure runs the sync itself as stage 1. Adding
it back would run two `homelab` syncs in parallel on every push and fight over the lock.

## How Renovate detects new versions
- Renovate is **not** built into GitHub and needs **no CI / GitHub Actions** in this repo. Install
  the **Mend-hosted Renovate App** from the GitHub Marketplace and grant it access to this (private) repo.
- Mend's own infrastructure then runs Renovate on a schedule (~hourly): it temporarily clones the
  repo, the **docker-compose manager** parses every `image: name:tag`, queries the upstream registry
  (Docker Hub / GHCR) for newer tags, and opens a PR bumping the tag. It does not retain your code.
- If a stack builds a local image from files beside `compose.yaml` (for example a Dockerfile plus
  `requirements.txt`), list those build inputs in that stack's `file_paths` in
  [`komodo/sync.toml`](../komodo/sync.toml). Otherwise dependency-only changes outside
  `compose.yaml` can merge without triggering a redeploy.
- The first run opens a "Configure Renovate" onboarding PR; after you merge it, Renovate creates a
  **Dependency Dashboard** issue and starts proposing updates.
- Self-hosting (npm package / Docker image / GitHub Action on an hourly cron) is the alternative —
  that one *would* need CI. The hosted app is simpler and is what this repo assumes.

## End-to-end

```
Renovate opens PR (bump image tag)
        │  review + merge to main
        ▼
GitHub push webhook ──► Procedure `Redeploy On Push`
                          │
                          ├─ Stage 1: RunSync `homelab`            (reconcile stack definitions; never deploys)
                          ▼
                          └─ Stage 2: BatchDeployStackIfChanged *  (deploy only the changed stacks)
```

> **New stacks come up on the first push.** Stage 1 creates the new stack's definition; stage 2 then
> deploys it (a brand-new stack counts as "changed"). Because the stages are sequential, the
> definition always exists before the deploy stage runs — no manual UI deploy or empty commit needed.
> (Earlier this repo used two parallel webhooks — sync + procedure — which raced, so a new stack
> sometimes missed its first deploy; folding the sync into the procedure as stage 1 fixed that.)
