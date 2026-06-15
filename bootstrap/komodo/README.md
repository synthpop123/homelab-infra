# Komodo bootstrap

The deployment of **Komodo itself** — Core + Periphery + MongoDB, the control plane that
manages every service under [`../../stacks`](../../stacks). Komodo can't deploy itself, so
unlike everything in `stacks/` this is **deployed by hand** and is **not** reconciled by the
`homelab` Resource Sync. These files are kept in git as a versioned record and a
disaster-recovery aid.

> The live copy lives on the host at `/opt/komodo/`. Keep this directory in sync whenever you
> change the live config (and vice-versa).

## Files

| File | Purpose |
|------|---------|
| `mongo.compose.yaml` | The Compose file (MongoDB backend). Byte-for-byte the upstream [`mongo.compose.yaml`](https://github.com/moghtech/komodo/blob/main/compose/mongo.compose.yaml) plus one local change: a named `komodo` network (per the [stack network convention](../../docs/conventions.md#networks)). |
| `compose.env.example` | Sanitized environment. Non-secret values mirror the live deploy; **secrets are `__CHANGE_ME__` placeholders**. The real `compose.env` stays on the host and is git-ignored (`*.env`). |

## Secrets

Komodo's own secrets are the one exception to the repo's "secrets go in the Komodo
Variables UI" rule ([conventions.md](../../docs/conventions.md#environment-variables)) —
this *is* the thing that provides that UI, so they live in `compose.env`:

- `KOMODO_DATABASE_PASSWORD` — MongoDB root password.
- `KOMODO_INIT_ADMIN_PASSWORD` — first-run admin password.
- `KOMODO_WEBHOOK_SECRET` / `KOMODO_JWT_SECRET` — incoming-webhook auth + JWT signing.
- Core ↔ Periphery auth uses the keypair in the `komodo_keys` Docker volume, **not** a
  passkey in this file.

## Deploy / update

On the host (`ssh fame`):

```bash
cd /opt/komodo
# first time only: seed the env, then fill in the secrets
cp compose.env.example compose.env && $EDITOR compose.env

docker compose -p komodo -f mongo.compose.yaml --env-file compose.env up -d
```

`-p komodo` sets the Compose project name; together with `networks.default.name: komodo` in
the compose file the containers join a clean `komodo` network (instead of `komodo_default`).
Changing the network name requires a `down` + `up` so the network is rebuilt.

State is in three named Docker volumes (kept across redeploys; `down` **without** `-v`):
`komodo_mongo-data`, `komodo_mongo-config`, `komodo_keys`.

## Backup & restore

The MongoDB contents, the `komodo_keys` volume, and `compose.env` are what you need to
rebuild this control plane. The database backs itself up daily; the rest you back up
yourself — see [docs/backup-restore.md](../../docs/backup-restore.md) (Layer 2 + the
full disaster-recovery runbook).
