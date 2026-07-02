# Conventions

## File organization
- **Repo:** one stack per `stacks/<service>/compose.yaml`. Multi-file stacks add more files in
  the same folder.
- **VPS:** Komodo clones this repo under `/etc/komodo/repos/`. Persistent **data lives under
  `/srv/<service>/`** via *absolute* bind mounts, so data never lands inside the git clone and
  survives re-clones / redeploys.
- **Legacy:** the `/opt/<service>` era is fully migrated — `/opt` now holds only host tooling
  (Komodo itself, komari). The runbook that got us here: [migration.md](./migration.md).

## Image pinning
- **App images:** pin to an explicit version (`org/name:1.2.3`, never `:latest`) so Renovate can
  propose upgrades as PRs — see [workflow.md](./workflow.md).
- **Databases & caches** (Postgres, Redis, …): pin to the **major line** instead
  (`pgvector/pgvector:pg16`, `redis:7`). Patches ride along automatically, while a *major* bump
  (pg17, redis 8) — which needs a deliberate data migration — surfaces as an occasional
  major-version PR rather than constant patch noise.

## Ports
- Host ports are allocated sequentially from `20000`, one per published service.
- The registry is the single source of truth: [ports.md](./ports.md). Record the port in the
  same commit that adds the service.
- **Exposure:** published ports are reachable only via the Akko reverse proxy — a host firewall
  drops direct public hits, with a few deliberate exceptions. See [firewall.md](./firewall.md).

## Networks
Name each stack's default network so Komodo does not generate `<project>_default`:

```yaml
networks:
  default:
    name: <stack>
```

## Environment variables
- **Non-secret** (e.g. `TZ`, `PUID`/`PGID`, feature flags): put directly in
  `stacks/<service>/compose.yaml` under `environment:` — committed, keeps the service self-contained.
- **Secrets** (API keys, passwords): never commit. Define them as **Variables & Secrets** in the
  Komodo UI, then:
  - reference `${MY_SECRET}` in `compose.yaml`, and
  - in `komodo/sync.toml`, set the stack's `environment` to `MY_SECRET = [[MY_SECRET]]`.

  Creating / inspecting the actual values (the Komodo UI, and the headless-from-host route an agent
  uses when there's no UI/API): [komodo-variables.md](./komodo-variables.md).

  Komodo interpolates `[[ ]]` at deploy time and writes the real value into `.env` (git-ignored).
  Git only ever contains the placeholder.
- **Whole config files that carry secrets** (e.g. an app's `config.yaml`): keep the real file on
  the host at `/srv/<service>/` (bind-mounted, backed up with `/srv`), **not** in git. Commit a
  sanitized `*.example` alongside the compose for reference.

## Volumes
- **Default: bind mounts to `/srv/<service>/...`** (absolute paths). Easy to back up (back up
  `/srv` — see [backup-restore.md](./backup-restore.md)), visible, and portable — matches the
  data-in-`/srv` policy.
- **Named volumes:** avoid unless an image is picky about bind-mount permissions or the data is
  pure cache/temp. They live under `/var/lib/docker/volumes` (harder to back up) and
  `docker compose down -v` can delete them.
- Ownership follows the image's own user (e.g. LinuxServer images respect `PUID`/`PGID`; the
  wallos image runs as `www-data`/`82`). Don't force a single global UID across services.
- **Bundled Postgres data dir:** for `postgres:18+` the data layout changed — `PGDATA` now defaults
  to `/var/lib/postgresql/<major>/docker` and the mount point is the parent, so bind
  `/srv/<stack>/postgres:/var/lib/postgresql` (data lands at `/srv/<stack>/postgres/18/docker`).
  For `postgres:≤17` (and `pgvector/pgvector:pgNN`) the old layout still applies:
  `/srv/<stack>/postgres:/var/lib/postgresql/data`. A *major* bump still needs a deliberate
  dump/restore in either case.
