# Migrating a service into Komodo

Runbook for moving an existing `/opt/<service>` Docker Compose deployment into this repo as a
Komodo-managed stack. The steady-state rules (pinning, ports, networks, secrets, volumes) live in
[conventions.md](./conventions.md); this doc is the *procedure* and the gotchas, distilled from
migrating ~15 services — single apps, multi-container stacks, and splitting a shared Postgres into
per-stack instances (§10–11).

> Expect a short outage during cutover (the old stack is down until the new one is healthy).
> All shell examples run **on the VPS** unless noted.

## Checklist

1. [ ] Inspect the live service (compose, image, ports, volumes, env, secrets, config files)
2. [ ] Choose pins — app to an exact version, DB/cache to its major line; confirm the pin == what's running
3. [ ] Plan secrets & config files (Komodo Variables vs off-git `/srv` files)
4. [ ] Claim the next host port in [ports.md](./ports.md)
5. [ ] Author the repo files (don't push yet)
6. [ ] Create any Komodo Variables
7. [ ] Cutover: stop old stack → copy data to `/srv` → verify perms
8. [ ] Push → Komodo deploys → verify health + data
9. [ ] Later: remove the old named volumes and `/opt/<service>`

**Order matters:** a push auto-deploys the stack (via the `Redeploy On Push` procedure). So the
`/srv` data and any Komodo Variables must exist **before** you push — i.e. do steps 6–7 before step 8.

## 1. Inspect the live service

```bash
ls -la /opt/<service>            # compose file(s), .env, config files
docker ps -a --filter name=<service> --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'
cat /opt/<service>/docker-compose.yml
```

For each container note: image + tag, published ports, **named volumes vs bind mounts**, env vars,
and any **secrets** (inline passwords, `.env`, or a bind-mounted config file). Multi-container
stacks (app + Postgres + Redis) migrate the same way — just more volumes.

## 2. Choose image pins

Per [conventions.md → Image pinning](./conventions.md#image-pinning): app → exact version,
databases/caches → major line (`pg16`, `redis:7`).

**Gotcha:** `:latest` often tracks `main`, which can be *ahead* of the newest release tag — so
pinning to the release might be a silent downgrade. Confirm the tag you pin matches what's actually
running before cutover:

```bash
# digest of the running image
docker image inspect <repo>:latest --format '{{index .RepoDigests 0}}'
# digest of the candidate tag (GHCR example) — compare the two
tok=$(curl -s "https://ghcr.io/token?scope=repository:<org>/<img>:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $tok" -H "Accept: application/vnd.oci.image.index.v1+json" \
  "https://ghcr.io/v2/<org>/<img>/manifests/<tag>" \
  | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}'
```

Pre-pulling the pinned tag (`docker pull <repo>:<tag>`) shortens the cutover window.

## 3. Plan secrets & config

Nothing secret goes in git (this repo is open-source-bound). Two mechanisms — see
[conventions.md → Environment variables](./conventions.md#environment-variables):

- **Env secrets** (DB/Redis passwords, API keys) → **Komodo Variables**. Compose references
  `${VAR}`; `komodo/sync.toml` maps `VAR=[[VAR]]` in the stack's `environment`.
- **Whole secret-bearing config files** (e.g. `config.yaml`) → keep the real file at
  `/srv/<service>/` (bind-mounted, off-git); commit a sanitized `*.example`.

**Reuse existing credentials.** A database password is baked into its data at first init — keep the
*current* password (don't invent a new one) or the migrated data won't authenticate.

## 4. Claim a port

Take the next free host port from [ports.md](./ports.md) and record it there in the same commit.
Only the publicly-served container gets a port; a bundled DB/cache stays internal. If the service is
behind a reverse proxy, repoint the proxy upstream to the new port.

## 5. Author the repo files (don't push yet)

- `stacks/<service>/compose.yaml` — pinned images, `/srv/<service>/...` bind mounts, the allocated
  port, a named `default` network, and `${VAR}` placeholders for secrets. Copy an existing stack as
  a template.
- `stacks/<service>/<config>.example.yaml` — sanitized, if the app uses a config file.
- `komodo/sync.toml` — add a `[[stack]]` block (plus an `environment` mapping if there are Variables).
- `docs/ports.md` + `README.md` — record the port / add the service row.

Validate the compose **before** any downtime (set dummy values for each `${VAR}` it references):

```bash
VAR1=x VAR2=x docker compose -f stacks/<service>/compose.yaml config -q && echo OK
```

## 6. Create Komodo Variables

For each env secret, add a Variable in the Komodo UI (**Settings → Variables**, mark it secret),
named to match the `[[VAR]]` placeholders, using the existing values from step 1.

## 7. Cutover (downtime starts)

```bash
# Stop the old stack — NO -v, so named volumes survive for copying.
cd /opt/<service> && docker compose down

# Copy each volume to a /srv bind dir, preserving ownership/mode.
# Let `cp -a` CREATE the leaf dir (don't mkdir it first) so perms carry over.
mkdir -p /srv/<service>
cp -a /var/lib/docker/volumes/<volume>/_data /srv/<service>/<dir>
# ...repeat per volume...
cp -a /opt/<service>/config.yaml /srv/<service>/config.yaml   # if the app uses a config file

# Verify: Postgres PGDATA must be 999:999 mode 700; app data matches the image's user.
stat -c '%n  %U:%G  %a' /srv/<service>/*
```

Gotchas:
- **Postgres/Redis** data is owned by uid/gid `999`. `cp -a` preserves it; pre-creating the dir with
  `mkdir` would leave it `root:root` and Postgres would refuse to start. (`stat` may show the host's
  name for `999`, e.g. `caddy:systemd-journal` — that's fine, it's still numeric `999:999`.)
- A bind-mounted config **file** must exist on the host before deploy, or Docker creates a
  *directory* with that name.

## 8. Deploy & verify

```bash
git add -A && git commit -m "feat: add <service> stack (migrated from /opt)" && git push
```

The push triggers the `homelab` sync (creates the stack *definition*) and the `Redeploy On Push`
procedure (deploys it) — see [workflow.md](./workflow.md). A brand-new stack occasionally needs a
one-time Deploy from the Komodo UI if the procedure fired before the definition existed. Then confirm:

```bash
docker ps --filter name=<service> --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:<port>/
docker logs <container> --tail 30   # look for a clean DB/Redis connect and your existing data
```

## 9. Clean up (once you're confident)

The old named volumes and `/opt/<service>` are your rollback. After verifying:

```bash
docker volume rm <volume> ...     # old named volumes
rm -rf /opt/<service>             # old compose dir
```

## 10. Variant — splitting a shared database into per-stack Postgres

Several services shared one external `postgres` (each app talking to `host.docker.internal:5432`).
Giving each stack its own bundled Postgres is cleaner: isolation, per-app version + backup, no shared
SPOF, and host `5432` no longer needs publishing. The app-config change is minimal — keep the same
DB name / user / password (as a [Komodo Variable](./conventions.md#environment-variables)); only the
**host** changes (`host.docker.internal` → the bundled service name, e.g. `n8n-postgres`).

Load the data **before** the app starts, via a throwaway container, so the bundled `PGDATA` is
already populated when the stack comes up (the image sets the data-dir ownership itself — no manual
chown, unlike copying a raw `PGDATA`):

```bash
# 1. Stop only the app for a consistent dump; the shared pg keeps running.
cd /opt/<svc> && docker compose down

# 2. Dump just this database (logical dump → portable across pg majors, e.g. pg17 -> pg18).
mkdir -p /srv/<svc>/postgres /srv/<svc>/migrate
docker exec <shared-pg> pg_dump -U postgres -Fc --no-owner --no-acl -d <db> > /srv/<svc>/migrate/<db>.dump

# 3. Init the new data dir with a throwaway pg (same major the stack will use), restore, then drop
#    the throwaway — the data persists on disk.
docker run -d --name tmp-<svc>-pg \
  -e POSTGRES_USER=<u> -e POSTGRES_PASSWORD=<pw> -e POSTGRES_DB=<db> \
  -v /srv/<svc>/postgres:/var/lib/postgresql postgres:18-alpine
until docker exec tmp-<svc>-pg pg_isready -U <u> -d <db>; do sleep 1; done
docker exec -i tmp-<svc>-pg pg_restore -U <u> --no-owner -d <db> < /srv/<svc>/migrate/<db>.dump
docker rm -f tmp-<svc>-pg
```

Then author the stack (app + a bundled, internal-only `postgres` on the stack network) and push.
`pg_restore` warnings about extensions/comments are usually harmless — verify with row counts.

> **postgres:18** moved its data dir — bind `/srv/<svc>/postgres:/var/lib/postgresql` (data lands at
> `…/18/docker`), not `…/data`. See [conventions.md → Volumes](./conventions.md#volumes).

**Decommission the shared instance** only after every consumer is migrated and verified:

```bash
# Prove nothing still uses it (no app connections + no container points at it):
docker exec <shared-pg> psql -U postgres -tAc \
  "select datname,usename,count(*) from pg_stat_activity where datname is not null group by 1,2;"
for c in $(docker ps --format '{{.Names}}'); do \
  docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -q 'host.docker.internal:5432' && echo "still using: $c"; done
# Archive a final full dump into /srv (backed up), then stop it — keep the volume as rollback:
mkdir -p /srv/postgres-archive
docker exec <shared-pg> pg_dumpall -U postgres > /srv/postgres-archive/shared-dumpall-$(date +%F).sql
cd /opt/postgres && docker compose down      # no -v
```

## 11. Gotchas from real migrations

- **Secrets that live in the data dir, not env.** Migrate the data dir *faithfully* (`cp -a`,
  preserving uid + mode) or you lose them: n8n's encryption key (`.n8n/config`, mode `0600`),
  Open WebUI's `WEBUI_SECRET_KEY` (`.webui_secret_key`), Gitea's `app.ini`
  (SECRET_KEY/INTERNAL_TOKEN). A changed key means users get logged out or data turns undecryptable.
- **`host.docker.internal` is rarely only for the DB.** Open WebUI also uses it for admin-configured
  model endpoints — don't strip `extra_hosts` just because the DB moved in-stack.
- **External shared networks.** A service joined to a shared bridge (e.g. seerr on `mediacenter-net`
  with a fixed IP, to reach the *arr apps) must stay there — put its bundled DB on a *second*,
  private network the app also joins, and reach the DB by service name.
- **Anonymous volumes hold real data too.** Find them via
  `docker inspect <c> --format '{{json .Mounts}}'`, not just the compose file.
- **Pinning a rolling tag** (`latest`/`stable`/`main-slim`): get the real version from the app
  (`/api/version`, a `SERVER_VERSION` env, the `org.opencontainers.image.version` label) or by
  mapping the tag's digest to a version tag on the registry — then confirm the versioned (and any
  `-slim`-style variant) tag exists before pinning.
- **`network_mode: host` / privileged apps** (clouddrive2): don't fit the port scheme or named
  networks — migrate only the config dir and leave host networking, devices and `/mnt` mounts as-is.
- **Derived indexes are disposable.** Elasticsearch/search data rebuilds (`tootctl search deploy`
  for mastodon), so a major ES bump (7→8 here) can preserve *or* wipe the data dir freely.
