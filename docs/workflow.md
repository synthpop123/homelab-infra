# Update & deploy workflow

How a change flows from git to a running container.

## Components (defined as code in [`komodo/sync.toml`](../komodo/sync.toml))
- **Resource Sync `homelab`** — reads `komodo/sync.toml` and reconciles resource *definitions*
  (creates/updates Stacks). Every stack is `deploy = false`, so the sync **never deploys** — that
  keeps it from racing the procedure for a stack's deploy lock (the "Resource is busy" error).
- **Procedure `Redeploy On Push`** — the **single git-push entry point** and the **sole deployer**.
  It runs two **sequential** stages: **(1)** `RunSync homelab` reconciles definitions, then
  **(2)** `BatchDeployStackIfChanged *` deploys only the stacks whose compose files changed.
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
  the **Mend-hosted Renovate App** from the GitHub Marketplace and grant it access to this repo.
- Mend's own infrastructure then runs Renovate on a schedule (~hourly): it temporarily clones the
  repo, the **docker-compose manager** parses every `image: name:tag`, queries the upstream registry
  (Docker Hub / GHCR) for newer tags, and opens a PR bumping the tag. It does not retain your code.
- Renovate can also bump dependencies inside a stack's local build context (for example a
  `Dockerfile` or `requirements.txt`). Komodo stack `file_paths` are compose files, so a PR that
  only changes build-context files will sync the repo but will not be selected by
  `BatchDeployStackIfChanged`. After merging one of those PRs, manually deploy that stack, e.g.
  `km deploy stack autobrr`, so `extra_args = "--build"` rebuilds the local image.
- The first run opens a "Configure Renovate" onboarding PR; after you merge it, Renovate creates a
  **Dependency Dashboard** issue and starts proposing updates.
- Self-hosting (npm package / Docker image / GitHub Action on an hourly cron) is the alternative —
  that one *would* need CI. The hosted app is simpler and is what this repo assumes.

## Pre-merge lint gate (CI)

Because a merge to `main` flows straight into the `Redeploy On Push` procedure with no
check in between, a malformed compose or `sync.toml` would only surface mid-deploy on the
VPS. A GitHub Actions workflow ([`.github/workflows/lint.yml`](../.github/workflows/lint.yml))
closes that gap: on every relevant infrastructure PR (including the ones Renovate opens) it runs
[`scripts/validate.sh`](../scripts/validate.sh), which

- `yamllint`s every stack compose plus the Komodo bootstrap compose,
- runs `docker compose config -q` on every stack and bootstrap compose — the **same parser
  Komodo uses**, so
  schema errors are caught here instead of on the box, and
- syntax-checks the bootstrap firewall shell scripts with `bash -n`, and
- syntax-checks `komodo/sync.toml` (TOML) and `renovate.json` (JSON).

It runs entirely on GitHub's runners — it **does not touch the VPS and deploys nothing**.
Run it locally before pushing with `./scripts/validate.sh` (it skips any tool you don't
have installed; CI sets `STRICT=1` so all checks are mandatory there).

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
