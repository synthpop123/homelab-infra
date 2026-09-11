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
| `mongo.compose.yaml` | The Compose file (MongoDB backend). Based on the upstream Compose file, with a named `komodo` network, an explicit MongoDB version, and a required shared Komodo version variable. |
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

## First deployment

On the host (`ssh fame`):

```bash
cd /opt/komodo
# first time only: seed the env, then fill in the secrets
cp compose.env.example compose.env && $EDITOR compose.env

docker compose -p komodo -f mongo.compose.yaml --env-file compose.env up -d
```

`-p komodo` sets the Compose project name; together with `networks.default.name: komodo` in
the compose file the containers join a clean `komodo` network (instead of `komodo_default`).
Do not change the existing network or volume names during a version upgrade.

State is in three named Docker volumes (kept across redeploys; `down` **without** `-v`):
`komodo_mongo-data`, `komodo_mongo-config`, `komodo_keys`.

## Backup & restore

The MongoDB contents, the `komodo_keys` volume, and `compose.env` are what you need to
rebuild this control plane. The database backs itself up daily; the rest you back up
yourself — see [docs/backup-restore.md](../../docs/backup-restore.md) (Layer 2 + the
full disaster-recovery runbook).

## Version upgrades

`compose.env.example` is the shared Core / Periphery version pin. Renovate tracks
it as `moghtech/komodo` GitHub releases. Merging its PR records the intended version;
it **does not upgrade bootstrap or the arm systemd agent**. Upgrade all three in
one maintenance window, preserving their existing config and keys.

MongoDB is independently pinned to `8.2.11`. Review database upgrades separately;
do not run an unscoped `docker compose pull` during a Komodo upgrade.

1. Review the target release and update the vendored resource schema if necessary
   ([schema notes](../../komodo/schemas/README.md)). Run the lint gate.
2. On fame, run `docker exec komodo-core km database backup -y`. Copy that dump out
   of the rotating backup directory, along with `/opt/komodo/compose.env`, the current
   Compose file, and `docker cp komodo-core:/config/keys <backup>/keys`. Keep the
   backup directory root-only. Record the running image IDs and retain/tag the old
   images locally for rollback. Also take a native BSON archive with `mongodump --archive --gzip`.
   Test the dump in a **separate temporary database**
   and verify all Variables, including string IDs, using the [restore runbook](../../docs/backup-restore.md#a-roll-back--restore-komodo-metadata).
3. On arm, back up `/usr/local/bin/periphery`, `/etc/komodo/periphery.config.toml`,
   `/etc/komodo/keys`, and `systemctl cat periphery`. Confirm there are no running
   Komodo executions before restarting the control plane.
4. Copy this Compose file to `/opt/komodo/`, and change only
   `COMPOSE_KOMODO_IMAGE_TAG` in the live `compose.env` to the reviewed version.
   Never overwrite the live secret-bearing env file with the example. Then:

   ```bash
   cd /opt/komodo
   docker compose -p komodo -f mongo.compose.yaml --env-file compose.env config -q
   docker compose -p komodo -f mongo.compose.yaml --env-file compose.env pull core periphery
   docker compose -p komodo -f mongo.compose.yaml --env-file compose.env up -d --no-deps core periphery
   ```

5. On arm, download `periphery-aarch64` from the **same release tag**, verify the
   downloaded binary with `--version`, and replace `/usr/local/bin/periphery`
   atomically (install to `periphery.new`, then rename). Restart `periphery.service`.
   Existing config and keys stay in place; onboarding is not repeated.
6. Verify Core's startup version in its logs, both Periphery versions, both Servers
   online, and a successful `Redeploy On Push` run. Check that Mongo and unrelated
   business container IDs did not change. Observe agent errors and zombie processes.

Core does not implement `core --version`: read its startup log or the `GetVersion`
API instead. Invoking the binary starts another Core process.

Rollback: stop new executions, restore the saved Compose/env and reference the
retained old Core/Periphery images (do not trust a floating `:2` tag), restore the
arm binary and restart its service. If metadata rollback is needed, restore the
saved database into a separate DB first, verify it, then switch Core to that DB;
never merge an old dump blindly into the populated live database. Keep Mongo's
version, named volumes and authentication keys unchanged.
