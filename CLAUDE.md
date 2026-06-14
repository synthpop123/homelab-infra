# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

GitOps for self-hosted services. There is **no build/test/lint** — it is declarative
infrastructure. The unit of work is editing YAML/TOML and pushing; deployment happens
on the VPS via Komodo, not from this machine. You cannot run or verify a deploy locally.

## Deployment model (the big picture)

### Accessing the VPS

The `Famesystems` host (where Komodo and all stacks run) is reachable from this machine via
`ssh fame` (alias defined in `~/.ssh/config`, logs in as `root`). Use it to inspect the live
deploy — e.g. `ssh fame 'docker ps'`, check `/srv/<service>/`, or read Komodo's clone under
`/etc/komodo/repos/`. This is the only way to verify a change actually took effect, since
nothing deploys from the local repo.

### Flow

A change flows from git to a running container without any CI in this repo:

1. Edit a `stacks/<service>/compose.yaml` (or add one) and push to `main`.
2. Two GitHub `push` webhooks fire into Komodo on the VPS:
   - **Resource Sync `homelab`** reads `komodo/sync.toml` and reconciles resource
     *definitions* — it creates/updates Stacks but does **not** redeploy on compose *content*
     changes.
   - **Procedure `Redeploy On Push`** runs `BatchDeployStackIfChanged` (pattern `*`),
     redeploying only the stacks whose compose content actually changed.
3. **Renovate** (Mend-hosted app, not CI here) watches every `image: name:tag`, opens PRs
   bumping pinned versions. Merging a bump triggers step 2's redeploy.

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

## Non-obvious conventions (enforced; see `docs/conventions.md`)

- **Pin every image** to an explicit version (`org/name:1.2.3`, never `:latest`) — Renovate
  depends on this to detect updates.
- **Host ports are sequential from `20000`** (range `20000–20999` reserved). `docs/ports.md`
  is the single source of truth; only *published* services consume a number. Legacy `/opt`
  services use ad-hoc `13xxx`/`1<port>` and are left untouched.
- **Persistent data goes under `/srv/<service>/…` as absolute bind mounts**, never named
  volumes (unless an image needs them) and never relative paths — Komodo clones this repo
  under `/etc/komodo/repos/`, so data must live outside the clone to survive re-clones.
- **Name each stack's default network** (`networks: default: name: <stack>`) to avoid
  Komodo's auto-generated `<project>_default`.
- **Secrets are never committed.** Define them as Variables & Secrets in the Komodo UI,
  reference `${MY_SECRET}` in compose, and in `sync.toml` map `MY_SECRET = [[MY_SECRET]]`
  under the stack's `environment`. Komodo interpolates `[[ ]]` into a git-ignored `.env` at
  deploy time. Non-secret config (`TZ`, `PUID`/`PGID`, flags) goes directly in compose.
- **Don't force a global UID** — ownership follows each image's own user (LinuxServer images
  respect `PUID`/`PGID`; the wallos image runs as `www-data`/`82`).
