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
- **Self-updating apps:** an app that updates itself in place (muvyo's 自动更新 plugin; the
  cliproxyapi stack, whose Oh My CPA updater container upgrades OMC and CPA from its console;
  miaomiaowu, whose UI updater writes a new binary into `/app/data/server`, which its entrypoint
  then prefers over the image) is
  the exception — a pin would always lag the live version, so it tracks `latest`,
  its image line carries an inline `# allow-latest` for the lint gate, and Renovate is disabled
  for that image in `renovate.json`.
- **Databases & caches** (Postgres, Redis, …): pin to the **major line** instead
  (`pgvector/pgvector:pg16`, `redis:7`). Patches arrive on the next pull and container
  recreation, while a *major* bump
  (pg17, redis 8) — which needs a deliberate data migration — surfaces as an occasional
  major-version PR rather than constant patch noise.
- **Digest-tracked major tags:** cloudreve, n8n, and umami additionally pin bundled Postgres
  and Redis as `name:major@sha256:...`. Renovate tracks digest changes within the same tag,
  so merging the update changes `compose.yaml` and triggers Komodo's deploy-if-changed flow.
  A pull alone never switches an existing container to the new image.
- **ghcr.io pulls are authenticated:** anonymous pulls get throttled (`429 toomanyrequests`
  mid-pull fails the deploy and leaves the old container running — immich hit it repeatedly).
  A stack with any `ghcr.io/` image sets `registry_provider = "ghcr.io"` and
  `registry_account = "synthpop123"` in its `[stack.config]`; Komodo then `docker login`s with
  the token stored under Settings → Providers (a `read:packages` PAT) before pulling. The lint
  gate requires the pair exactly when a ghcr image is present. The host's own
  `/root/.docker/config.json` is **not** used: Periphery runs in a container without it.

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

## Healthchecks
- **Every long-running service that answers on a port carries one**, so Komodo, Beszel and
  `api.lkwplus.com/homelab` can tell *healthy* from merely *up*. Either write the `test`, or —
  when the image ships its own `HEALTHCHECK` — restate only the timing under a
  `# The image's own probe, at this repo's interval.` comment: an image probe left alone runs at
  the image's default (often 30 s or less). One-shot jobs (`amane-intake`, `affine-migration`)
  and port-less workers (`sure-worker`, `kometa`) may go without.
- **Timing:** `interval: 60s`, `start_period: 60s`, `start_interval: 5s`. Each probe is a
  `docker exec` — at ~100 containers a 10 s interval was constant process churn for state that
  Beszel's agent samples once a minute anyway — while `start_interval` still turns a fresh
  container healthy within seconds, so `depends_on: condition: service_healthy` doesn't wait a
  minute. (`start_interval` needs Docker Engine ≥ 25; both hosts run 29.)
- **Lint:** `validate.sh` fails a `healthcheck` without an explicit `interval`, or one under
  60 s (`disable: true` is exempt). A stopped stack (Renovate off for its file, e.g. multica) is
  checked once it comes back — editing its compose now would start it.
- **Writing a probe:** call a binary the image actually has (`curl`, `wget`, `node`, `python`,
  bash's `/dev/tcp` when there is neither, or the app's own subcommand like `/beszel health`),
  hit `127.0.0.1` rather than `localhost` (which may resolve to `::1` the app doesn't bind), and
  prefer a health endpoint to the UI. Run it on the live container before pushing —
  `ssh fame 'docker exec <container> <probe…>'` — since a wrong probe turns a working service
  *unhealthy* and blocks whatever `depends_on` it.
