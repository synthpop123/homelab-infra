# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

GitOps for self-hosted services — declarative infrastructure, so there is **no build or
test step**. The one local check is a **lint gate**: `./scripts/validate.sh` (also run in CI
on every PR via `.github/workflows/lint.yml`) validates every `stacks/*/compose.yaml` with
`yamllint` + `docker compose config`, plus `sync.toml`/`renovate.json` syntax. Run it before
pushing. The unit of work is editing YAML/TOML and pushing; deployment happens on the VPS via
Komodo, not from this machine — you cannot run or verify a *deploy* locally.

## Deployment model (the big picture)

### Accessing the VPS

The `Famesystems` host (where Komodo and all stacks run) is reachable from this machine via
`ssh fame` (alias defined in `~/.ssh/config`, logs in as `root`). Use it to inspect the live
deploy — e.g. `ssh fame 'docker ps'`, check `/srv/<service>/`, or read Komodo's clone under
`/etc/komodo/repos/`. This is the only way to verify a change actually took effect, since
nothing deploys from the local repo. What runs on the host besides stacks (Caddy, komari,
fail2ban, firewall, daemon config) is inventoried in `docs/server.md`; health-check and
troubleshooting commands are in `docs/operations.md`; the multi-stack media pipeline
(clouddrive2/cms/emby/plex/medialinker and the `mediacenter-net` fixed IPs) in `docs/media.md`.

### Flow

A change flows from git to a running container with no CI in the *deploy* path — deployment
is webhook-driven, not CI-driven (the PR lint gate in `.github/workflows/lint.yml` validates
changes but never deploys):

1. Edit a `stacks/<service>/compose.yaml` (or add one) and push to `main`.
2. Two GitHub `push` webhooks fire into Komodo on the VPS:
   - **Resource Sync `homelab`** reads `komodo/sync.toml` and reconciles resource
     *definitions* only — every stack is `deploy = false`, so it creates/updates Stacks but
     **never deploys** (otherwise it races the procedure for the deploy lock → "Resource is busy").
   - **Procedure `Redeploy On Push`** is the sole deployer: runs `BatchDeployStackIfChanged`
     (pattern `*`), deploying only the stacks whose compose files actually changed.
3. **Renovate** (Mend-hosted app, not CI here) watches every `image: name:tag`, opens PRs
   bumping pinned versions. Merging a bump triggers step 2's redeploy.

If Renovate changes only files inside a stack's local build context (for example an embedded
`Dockerfile` or `requirements.txt`), Komodo syncs the repo but `BatchDeployStackIfChanged` will not
select the stack because `file_paths` are compose files. After merging that kind of PR, manually
deploy the stack through Komodo — UI, or the `km` CLI with an API key (`docs/operations.md`) —
so `extra_args = "--build"` rebuilds the local image.

Both `sync.toml` and the redeploy procedure are themselves defined as code in
`komodo/sync.toml`. Stacks reference their git source via `linked_repo = "homelab-infra"`
(a Komodo "Repo" resource configured in the UI) — the git account/repo intentionally live
in Komodo, not in this file.

## Adding or editing a service

Adding a service is a coordinated change across **four** places, ideally in one commit:

1. `stacks/<service>/compose.yaml` — the compose file (conventions below).
2. `komodo/sync.toml` — add a `[[stack]]` block (`server = "Famesystems"`,
   `linked_repo = "homelab-infra"`, `run_directory`, `file_paths`).
3. `docs/ports.md` — claim the next free host port and update **Next free**.
4. `README.md` — add a row to the Services table.

Adopting an existing deployment from outside the repo (data move, secrets, cutover) has its
own runbook: `docs/migration.md`.

**This repo is public.** Never commit public IPs, tokens, or other instance-specific
secrets — hostnames and host ports are fine (established practice), but IPs stay in off-git
config (`/etc/fame-firewall.conf`, `/srv/...`) and secrets in Komodo Variables.

## Non-obvious conventions (enforced; see `docs/conventions.md`)

- **Pin app images** to an explicit version (`org/name:1.2.3`, never `:latest`); pin
  **databases/caches to their major line** (`pgvector/pgvector:pg16`, `redis:7`) since a major
  bump needs a manual data migration. Renovate relies on these tags to detect updates.
- **Host ports are sequential from `20000`** (range `20000–20999` reserved). `docs/ports.md`
  is the single source of truth; only *published* services consume a number. (The legacy
  `/opt` services and their ad-hoc `13xxx` ports are fully migrated away.)
- **Persistent data goes under `/srv/<service>/…` as absolute bind mounts**, never named
  volumes (unless an image needs them) and never relative paths — Komodo clones this repo
  under `/etc/komodo/repos/`, so data must live outside the clone to survive re-clones.
- **Name each stack's default network** (`networks: default: name: <stack>`) to avoid
  Komodo's auto-generated `<project>_default`.
- **Secrets are never committed.** Define them as Variables & Secrets in the Komodo UI,
  reference `${MY_SECRET}` in compose, and in `sync.toml` map `MY_SECRET = [[MY_SECRET]]`
  under the stack's `environment`. Komodo interpolates `[[ ]]` into a git-ignored `.env` at
  deploy time. Creating/inspecting the values themselves — including the headless-from-host route
  (write straight to the `komodo-mongo` `Variable` collection) when you have only `ssh fame` and no
  UI/API — is in `docs/komodo-variables.md`. Non-secret config (`TZ`, `PUID`/`PGID`, flags) goes
  directly in compose. A whole
  secret-bearing config file (e.g. an app's `config.yaml`) lives on the host under
  `/srv/<service>/` (bind-mounted), never committed — commit a sanitized `*.example` instead.
- **Don't force a global UID** — ownership follows each image's own user (LinuxServer images
  respect `PUID`/`PGID`; the wallos image runs as `www-data`/`82`).
