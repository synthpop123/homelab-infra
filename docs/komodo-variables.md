# Komodo Variables & Secrets — operating the values

The secret *flow* (reference `${VAR}` in a compose, map `VAR = [[VAR]]` under a stack's
`environment` in [`sync.toml`](../komodo/sync.toml)) is in
[conventions.md](./conventions.md#environment-variables). This runbook is the other half:
how to **create, inspect, and update the actual values** Komodo interpolates — from the UI, and
from the host when there is no UI/API access (an agent with only `ssh fame`, or disaster recovery).

## Where they live

Komodo keeps every Variable in its MongoDB, inside the `komodo-mongo` container:

- **DB** `komodo`, **collection** `Variable`.
- **Document shape:** `{ _id: ObjectId, name, description, is_secret, value }`.
  - `name` has a **unique index** — one document per variable; upsert by `name`.
  - `value` is stored **in plaintext**. `is_secret: true` only masks it in the UI, API responses
    and logs — Komodo does **not** encrypt it at rest. So Mongo (and its `/srv`-style backups) hold
    secrets in the clear; protect them accordingly.
- `${VAR}` in a compose and `[[VAR]]` in `sync.toml` both resolve to that `value` (Komodo writes the
  stack's git-ignored `.env` at deploy time).

## The UI way (humans, default)

Komodo UI → **Settings → Variables** → add the variable, paste the value, toggle **Secret** on for
anything sensitive. This is the default the [conventions](./conventions.md#environment-variables)
assume.

## The host way (no UI/API — agents, recovery)

Mongo's port isn't published, so go through the container. It already holds the root creds in its
own env (`MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`), so reference them **inside**
the container — never put a password on the command line, in a file, or in chat. The pattern below
generates the value on the host and hands it to `mongosh` through the container **environment**
(`docker exec -e`), so the secret never appears in `argv` or the script file.

### Create / update a secret (idempotent)

```bash
ssh fame '
export MY_SECRET="$(openssl rand -hex 16)"   # 32 hex chars; use -hex 32 for a 64-char app secret
cat > /tmp/var.js <<"JS"
const d = db.getSiblingDB("komodo");
const name = "MY_SECRET";
const r = d.Variable.updateOne(
  { name },
  { $setOnInsert: { description: "what this is (auto-created)", is_secret: true, value: process.env.MY_SECRET } },
  { upsert: true }
);
print(name + " -> upserted=" + (r.upsertedId ? "yes" : "no (matched " + r.matchedCount + ")"));
JS
docker exec -i -e MY_SECRET komodo-mongo sh -c \
  "mongosh \"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin\" --quiet" \
  < /tmp/var.js
rm -f /tmp/var.js
'
ssh fame 'docker restart komodo-core'   # reload so Core sees the value before the next deploy
```

Why each piece matters:

- **`$setOnInsert` (not `$set`)** makes it idempotent — re-running never clobbers an existing value.
  To deliberately overwrite, use `$set` instead.
- **Quoted heredoc (`<<"JS"`)** stops the host shell from expanding `$setOnInsert` / `process.env`;
  the value reaches `mongosh` only via `docker exec -e MY_SECRET`.
- **URL-safe hex** keeps the value from breaking connection strings like
  `postgresql://user:<pwd>@host:5432/db` (no `@ : / + =` to escape).
- **`docker restart komodo-core`** guarantees Core picks up the change before the next deploy;
  running stacks/containers are untouched by a Core restart (it's only the control plane). Core
  comes back in a few seconds — confirm with `curl -s -o /dev/null -w '%{http_code}' localhost:9120`
  returning `200`.

### Inspect what exists (no values printed)

```bash
ssh fame 'cat > /tmp/q.js <<"JS"
db.getSiblingDB("komodo").Variable.find({}, { name: 1, is_secret: 1, _id: 0 }).sort({ name: 1 })
  .forEach(v => print(v.name + "  secret=" + v.is_secret));
JS
docker exec -i komodo-mongo sh -c "mongosh \"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin\" --quiet" < /tmp/q.js
rm -f /tmp/q.js'
```

To confirm a just-written value landed correctly **without leaking it**, print its length, never the
value itself — swap the `forEach` for:
`.forEach(v => print(v.name + " len=" + v.value.length))` on a `find({ name: "MY_SECRET" })`.

### Read a value back (rare)

A secret is masked in the UI. If you genuinely need the plaintext (e.g. to connect to a bundled DB
by hand), read it from Mongo the same way — and keep it out of anything that logs.

## Conventions for new variables

- **Name:** `SERVICE_PURPOSE` in upper snake case — `UMAMI_DB_PASSWORD`, `N8N_DB_PASSWORD`,
  `KARAKEEP_OPENAI_API_KEY`.
- **Value:** URL-safe (hex) for anything that lands in a connection string; a long random string for
  app secrets / signing keys.
- In the **same change**, add the matching `VAR = [[VAR]]` line to the stack's `environment` in
  [`sync.toml`](../komodo/sync.toml) (see [conventions.md](./conventions.md#environment-variables)).
