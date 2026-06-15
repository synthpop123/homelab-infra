# Backup & restore

What to back up, what already happens automatically, and how to restore — from rolling
back one service to rebuilding the whole box. The steady-state rules (pinning, `/srv`
data, secrets) live in [conventions.md](./conventions.md); this doc is the *data-safety*
layer on top of them.

> All shell examples run **on the VPS** (`ssh fame`) unless noted.

## The three layers

State is split across three places, each with a different owner, mechanism, and blast
radius. You need **all three** to come back from a total loss:

| Layer | Contains | Lives in | Backed up by | If you lose it |
|-------|----------|----------|--------------|----------------|
| **1. Code / IaC** | `stacks/*/compose.yaml`, `komodo/sync.toml`, docs | this git repo | pushed to **GitHub** (off-box) | `git clone` to recover |
| **2. Komodo metadata** | resource defs, **Variables/secrets**, users, API keys, git/registry accounts, audit log | MongoDB (`komodo-mongo`) | **built-in** dump → `/etc/komodo/backups` (daily) | secrets & accounts gone; stacks must be reconfigured by hand |
| **3. Application data** | each service's DB, uploads, app-held keys | `/srv/<service>/` (~56 GB, mostly emby) | **nothing yet** — see [Layer 2 below](#layer-2--application-data-srv) | the actual user data is gone for good |

Why all three, and why git alone is **not** enough:

- The repo defines *what* each stack is, but every **secret** (DB passwords, API keys,
  Mastodon/Gitea/n8n app keys) is a Komodo **Variable** or lives inside `/srv` — git only
  ever holds `[[PLACEHOLDER]]`s and `*.example` files (see
  [conventions.md → Environment variables](./conventions.md#environment-variables)).
- Komodo's MongoDB holds the Variables and account config, but **not** a single byte of
  application data — that's all under `/srv`.
- So: **git** rebuilds the definitions, **Mongo backup** restores the secrets/accounts,
  and a **`/srv` backup** restores the data. Miss one and recovery is incomplete.

---

## Layer 1 — Komodo metadata (built-in)

Komodo Core ships the **`km` CLI** (`docker exec komodo-core km ...`); run inside the
container it inherits Core's DB config, so backups "just work". Docs:
<https://komo.do/docs/setup/backup>.

### What already runs

A Procedure **`Backup Core Database`** (auto-created on Komodo ≥ v1.19; this box runs `:2`)
fires **every day at 01:00** and runs `km database backup`. It dumps each MongoDB
collection to a gzip file in a timestamped folder:

```
/etc/komodo/backups/
├── 2026-06-15_01-00-01/
│   ├── Variable.gz        # ← your secrets
│   ├── User.gz  ApiKey.gz  Permission.gz  UserGroup.gz
│   ├── GitProviderAccount.gz  DockerRegistryAccount.gz  Server.gz
│   ├── Stack.gz  ResourceSync.gz  Procedure.gz  Repo.gz  Builder.gz
│   ├── Alert.gz  Update.gz  Tag.gz  ...
└── Stats.gz               # latest only — see note
```

- **Retention:** the most recent **14** folders are kept (`KOMODO_CLI_MAX_BACKUPS`);
  older ones are pruned automatically.
- **`Stats`** (historical CPU/mem/disk graphs) is large and disposable, so it is **not**
  in the dated folders — only a single latest `Stats.gz` at the top level.
- **No encryption.** The dump is plaintext gzip and **`Variable.gz` contains your
  secrets** — never copy it off-box unencrypted (see [Layer 3](#layer-3--get-it-off-the-box-3-2-1)).

### Verify / run on demand / tune

```bash
ls -lt /etc/komodo/backups/                       # newest folder = last successful run
docker exec komodo-core km database backup -y     # take one right now
```

Tune retention by setting `KOMODO_CLI_MAX_BACKUPS` in `/opt/komodo/compose.env` and
redeploying Komodo (`docker compose -p komodo -f /opt/komodo/mongo.compose.yaml \
  --env-file /opt/komodo/compose.env up -d`). In the UI you can also confirm/edit the
schedule on the `Backup Core Database` procedure.

### Not in the dump — back these up too

The Mongo dump captures Komodo's *logical* state, but two host-side bits are required to
bring Core back and are **not** in git:

- **`/opt/komodo/compose.env`** — MongoDB credentials and the JWT/webhook secrets (Core↔Periphery
  auth uses the keypair in the `komodo_keys` volume below, not a passkey here). Lose it and the
  restored Mongo won't authenticate. Store it off-box (encrypted); a sanitized copy is versioned
  at [`bootstrap/komodo/`](../bootstrap/komodo/).
- **`komodo_keys` volume** (`/config/keys` in Core) — Core's generated Core/Periphery keypair.

---

## Layer 2 — application data (`/srv`)

**This is the gap.** Every service keeps its real data as absolute bind mounts under
`/srv/<service>/` (there are **no** named or anonymous Docker volumes for apps — only
Komodo's own `komodo_mongo-data` / `komodo_keys`). Nothing backs `/srv` up today.

```
~56G  /srv total   — dominated by emby ~50G (.strm + scraped metadata/artwork, mostly
       rebuildable), cms 3.1G; then immich 1.4G, openwebui 1.1G, new-api ~320M, koito 176M, ...
```

### Make the backup consistent

Copying a *running* database's data directory can capture a torn, unrestorable state.
Two safe options:

- **Logical dump (preferred for DBs):** `pg_dumpall` each Postgres container. Portable
  across major versions (matches the dump/restore pattern in
  [migration.md §10](./migration.md#10-variant--splitting-a-shared-database-into-per-stack-postgres))
  and immune to the `postgres:18` data-dir layout change noted in
  [conventions.md → Volumes](./conventions.md#volumes).
- **Cold file copy:** `docker compose down` the stack, copy its `/srv/<service>` dir, bring
  it back up — a brief outage for a guaranteed-consistent snapshot.

Search indexes (Mastodon Elasticsearch at `/srv/mastodon/elasticsearch`, Karakeep
Meilisearch) are **derived** and rebuildable, so they can be excluded to save space and
sidestep consistency worries — rebuild after restore (e.g. `tootctl search deploy`).

### Reference backup script

A starting point — **review and adapt before relying on it** (auth methods, which DBs to
include, where it ships to). Save as `/usr/local/sbin/backup-srv.sh`, `chmod +x`:

```bash
#!/usr/bin/env bash
# Stage a consistent backup of all app data + the Komodo bits not in the Mongo dump.
set -euo pipefail

ts=$(date +%F_%H-%M-%S)
dest="/srv/_backups/$ts"          # local staging; ship off-box in step 4
mkdir -p "$dest/pgdump"

# 1) Logical dump of every Postgres container (portable + consistent).
#    Local socket auth is trust in the official images, so no password needed.
for c in $(docker ps --format '{{.Names}}'); do
  img=$(docker inspect "$c" --format '{{.Config.Image}}')
  case "$img" in
    *postgres*|*pgvector*|*pgvecto*|*vectorchord*)
      u=$(docker exec "$c" printenv POSTGRES_USER 2>/dev/null || true); u=${u:-postgres}
      echo "pg_dumpall: $c (user=$u)"
      docker exec "$c" pg_dumpall -U "$u" | gzip > "$dest/pgdump/$c.sql.gz"
      ;;
  esac
done

# 2) File-level snapshot of /srv (uploads, app config, app-held secrets like
#    n8n's encryption key, Gitea app.ini). The pg_dumps above are the source of
#    truth for databases; rebuildable search indexes are excluded.
tar --exclude='/srv/_backups' \
    --exclude='/srv/*/elasticsearch' \
    --exclude='/srv/*/meilisearch' \
    -czf "$dest/srv.tar.gz" /srv

# 3) Komodo host-side bits that the Mongo dump does NOT contain.
cp /opt/komodo/compose.env "$dest/komodo.compose.env"
docker run --rm -v komodo_keys:/k:ro -v "$dest":/out alpine \
  tar -czf /out/komodo_keys.tar.gz -C /k .

echo "Staged: $dest"
# 4) Ship off-box, ENCRYPTED — see Layer 3. e.g.:
#    restic -r <repo> backup "$dest" && restic forget --keep-daily 14 --prune
```

> **immich Postgres** uses the VectorChord/pgvecto.rs extensions; a logical dump restores
> cleanly only onto the **same** image. Keep the file-level copy as a fallback and check
> immich's upstream backup guidance.

### Schedule it

Pick one (GitOps-native first):

- **Komodo Action/Procedure** — define an Action that runs the script and schedule it
  daily, mirroring `Backup Core Database`. Fits the "everything is a Komodo resource"
  model and shows up in the UI/alerts.
- **cron** — `0 2 * * * /usr/local/sbin/backup-srv.sh` (run *after* the 01:00 Mongo
  backup so a single off-box push covers both). Note: this box has no service-data cron
  today — `/etc/cron.d` only has OS jobs.

---

## Layer 3 — get it off the box (3-2-1)

Right now **every** backup (Mongo dumps, and any `/srv` copy you add) sits on the **same
disk** as the data it protects (`/dev/sda3`, 41% used). One disk/VPS failure loses the
data *and* its backups. The [3-2-1 rule](https://en.wikipedia.org/wiki/Backup): **3**
copies, on **2** media, **1** off-site.

- **Encrypt first** — the dumps contain secrets and Komodo has no built-in encryption.
  Use a tool that encrypts client-side: [`restic`](https://restic.net) (built-in) or
  `rclone crypt`; or pre-encrypt with `age`/`gpg`.
- **Where** — an object store is the easy off-site target (Mastodon already uses S3/R2,
  so credentials/habits exist). `restic` → S3/B2/R2, or `rclone` to any remote.
- **What to ship**, in one bundle: the latest `/etc/komodo/backups/<ts>/` **+** the
  staged `/srv` dump (`pgdump/` + `srv.tar.gz`) **+** `compose.env` + `komodo_keys`.
- **Retention** off-site can differ from on-box (e.g. `--keep-daily 14 --keep-weekly 8`).
- **Test restores**, don't just trust them — an untested backup is a hope, not a backup.

---

## Restore runbooks

### A. Roll back / restore Komodo metadata

`km database restore` re-imports the gzip dump. It uses **separate** `*_TARGET_*` env vars
from backup *on purpose*, so a stray `restore` can't clobber the live DB. Inside Core,
point it back at `mongo:27017` with the real credentials (read from `compose.env`):

```bash
set -a; . /opt/komodo/compose.env; set +a      # loads KOMODO_DATABASE_USERNAME/PASSWORD

docker exec \
  -e KOMODO_CLI_DATABASE_TARGET_ADDRESS=mongo:27017 \
  -e KOMODO_CLI_DATABASE_TARGET_USERNAME="$KOMODO_DATABASE_USERNAME" \
  -e KOMODO_CLI_DATABASE_TARGET_PASSWORD="$KOMODO_DATABASE_PASSWORD" \
  -e KOMODO_CLI_DATABASE_TARGET_DB_NAME=komodo \
  komodo-core km database restore -y            # add -r 2026-06-15_01-00-01 for a specific folder
```

> **Restore does not clear the target first.** Into an *empty* DB (disaster recovery)
> that's fine. To **roll back** a populated DB, the old documents would linger and mix
> with the restored ones — drop the DB first, or restore into a throwaway
> `KOMODO_CLI_DATABASE_TARGET_DB_NAME=komodo-restore` and inspect before cutting over.

After restoring, Komodo has your Variables/accounts back; a git push (or a manual
ResourceSync run) reconciles stack *definitions* to the latest commit.

### B. Restore one service's data

```bash
# Definition + secrets come from git + Komodo; this is just the data.
cd /opt/komodo && docker compose ... down <service>   # or stop via Komodo UI

# DB from logical dump → throwaway-container restore (per migration.md §10):
gunzip -c /path/<service>-postgres.sql.gz | \
  docker exec -i <service>-postgres psql -U postgres
# ...or restore files: untar /srv/<service> from srv.tar.gz, preserving owner/mode (tar -p).

# Redeploy the stack from the Komodo UI and verify health + data.
```

Postgres data dirs must stay `999:999` mode `700`; app dirs follow the image's user — see
[migration.md §7](./migration.md#7-cutover-downtime-starts).

### C. Full disaster recovery (bare metal)

**Order matters** — secrets and `/srv` data must exist *before* stacks deploy, exactly
like a migration ([migration.md](./migration.md)). On a fresh host:

1. **Install Docker.**
2. **Restore Komodo host files:** put back `/opt/komodo/` (`compose.env` +
   `mongo.compose.yaml`) and the `komodo_keys` volume from your off-site bundle.
3. **Start Komodo:** `docker compose -p komodo -f /opt/komodo/mongo.compose.yaml \
   --env-file /opt/komodo/compose.env up -d` (Mongo comes up **empty**).
4. **Restore the Mongo dump:** copy your latest `/etc/komodo/backups/<ts>/` back, then run
   **runbook A** into the empty DB — this returns Variables/secrets, users, git/registry
   accounts, and the ResourceSync/Procedure definitions.
5. **Restore `/srv`:** untar `srv.tar.gz` and `pg_dump`s into place (runbook B per service);
   reconnect Periphery (the `Famesystems` server) if its address changed.
6. **Deploy:** push to `main` (or run the ResourceSync + `Redeploy On Push` procedure) so
   every stack redeploys against the restored data. Rebuild derived indexes
   (`tootctl search deploy`, etc.).
7. **Verify:** `docker ps`, hit each service, spot-check data — see
   [migration.md §8](./migration.md#8-deploy--verify).

---

## Cadence & checklist

| What | Mechanism | Frequency | Off-site? |
|------|-----------|-----------|-----------|
| Code / IaC | `git push` → GitHub | every change | ✅ GitHub |
| Komodo Mongo dump | `Backup Core Database` procedure | daily 01:00 (keep 14) | ⬜ **add encrypted off-site copy** |
| `/srv` app data + Postgres dumps | `backup-srv.sh` (Action/cron) | **daily 02:00 — to set up** | ⬜ **to set up** |
| `compose.env` + `komodo_keys` | bundled into the `/srv` job | daily | ⬜ with the above |
| Restore drill | runbook B on one service | quarterly | — |

**Current state:** Layer 1 (Mongo) ✅ runs; Layers 2 & 3 (app data, off-site) are **not**
set up yet — the script and scheduling above are the recommended next step.
