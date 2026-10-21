# Day-2 operations

Routine checks and the short paths for poking the live deploy. Host inventories:
[server.md](./server.md) (fame), [server-arm.md](./server-arm.md) (arm). Deploy flow:
[workflow.md](./workflow.md). All commands run from this machine via `ssh fame` unless
noted; use `ssh arm` for multica, storageui, beszel-agent, the host Caddy, and
Periphery on arm (see [server-arm.md](./server-arm.md) and
[komodo-servers.md](./komodo-servers.md)).

## Health check

```bash
ssh fame 'docker ps --filter health=unhealthy --filter status=restarting --format "{{.Names}}\t{{.Status}}"'
ssh fame 'systemctl --failed --no-legend; df -h / | tail -1'
```

Empty output + disk under ~80% = healthy. Dashboards: **beszel** (per-container CPU/mem)
and **tautulli** (Plex sessions), both in the README table, plus **komari**, the public
server probe at [komari.lkwplus.com](https://komari.lkwplus.com) — a host process rather
than a stack, so it has no row there.

## Komodo

- **UI** — the Komodo hostname (see README). Every stack shows its deploy state, logs, and
  a Redeploy button there; that is the default tool for one-off operations.
- **API key** — lives on fame in **`/etc/komodo/km.env`** (root, `0600`, off git):
  `KOMODO_CLI_KEY=…` / `KOMODO_CLI_SECRET=…`. Created in the UI (Settings → API Keys); to rotate,
  make a new key there, overwrite the file, delete the old key. Prefer it over editing Mongo
  directly (the [komodo-variables.md](./komodo-variables.md) host route is now the fallback).
- **`km` CLI** — ships inside `komodo-core`. Database commands work as-is
  (`docker exec komodo-core km database backup -y`); API commands take the key file:

```bash
ssh fame 'docker exec --env-file /etc/komodo/km.env komodo-core km ls stacks'
ssh fame 'docker exec --env-file /etc/komodo/km.env komodo-core km execute deploy-stack <name> -y'
```

- **HTTP API** — `km` 2.3 has **no delete** (only list/execute/create/update). For anything else,
  `POST http://localhost:9120/{read,write,execute}` on fame with `{"type": "<Request>", "params": {…}}`
  and the `X-Api-Key` / `X-Api-Secret` headers:

```bash
ssh fame 'set -a; . /etc/komodo/km.env; set +a
api() { curl -s -X POST "http://localhost:9120/$1" -H "Content-Type: application/json" \
  -H "X-Api-Key: $KOMODO_CLI_KEY" -H "X-Api-Secret: $KOMODO_CLI_SECRET" -d "$2"; }
api write "{\"type\":\"DeleteStack\",\"params\":{\"id\":\"<name>\"}}" >/dev/null'
```

  Verified on 2.3.3: `ListStacks` / `ListVariables`; `CreateStack` / `DeleteStack` (`id` takes the
  name); `CreateVariable` / `UpdateVariableValue` / `DeleteVariable` (by `name`; `CreateVariable`
  defaults to `is_secret: false` — pass `true`); `DeleteTag` needs the ObjectId, not the
  name. Deleting a stack from `sync.toml` does **not** delete its Komodo resource — remove it here.
  **Write responses echo the full object, secret `value` included** — send them to `/dev/null`
  when writing a secret, and generate the value on the host (`$(openssl rand -hex 16)`).

Komodo's Stats page now provides multi-server charts and separates memory use from
cache. Use it alongside Beszel/Komari; those monitors remain independent of Core.
Custom resource/container list API callers must paginate or set `limit: 0` on
Komodo 2.3 (default page size: 50). The built-in batch deploy Procedure is not capped
by this API default. Manual tag-scoped Procedures are documented in
[workflow.md](./workflow.md#manual-maintenance-groups).

## Deploying

Normal path: **push to `main`** — the `Redeploy On Push` procedure syncs definitions, then
deploys only changed stacks ([workflow.md](./workflow.md)). Manual deploy (UI or `km`) is
needed only when:

- a PR changed **build-context files only** (e.g. `stacks/autobrr/notify/`) — compose
  unchanged means `BatchDeployStackIfChanged` skips it; redeploy the stack so
  `--build` picks it up;
- you changed a **Komodo Variable** and want it applied now (redeploy the consuming stack);
- recovering from a failed deploy after fixing the cause;
- refreshing a floating database/cache tag after a pull when the compose file did not change.
  Existing containers keep their original image ID until recreated. cloudreve, n8n, and umami
  track their bundled Postgres/Redis digests through Renovate to put these refreshes on the
  normal merge-and-deploy path.

## When a push didn't deploy

Check in this order:

1. **GitHub → repo → Settings → Webhooks** — the procedure hook's recent delivery is green?
2. **Komodo UI → Procedures → Redeploy On Push** — last run's stages; stage 1 (sync) failing
   aborts stage 2.
3. `Resource is busy` = two executors racing for the stack's deploy lock. Wait and rerun the
   procedure; if it recurs, make sure the ResourceSync's own webhook is still **disabled**
   ([workflow.md → Webhooks](./workflow.md#webhooks-on-the-github-repo)).
4. Komodo's clone is current? `ssh fame 'git -C /etc/komodo/repos/homelab-infra log --oneline -1'`

## Logs

```bash
ssh fame 'docker logs <container> --tail 50'          # app logs (rotated 10MB×3)
ssh fame 'journalctl -u fame-firewall -n 20'          # host units: caddy, fail2ban, ...
```

## Reboot

Kernel updates need one (see [server.md](./server.md#known-state--pending)); everything is
designed to come back unattended: containers via `restart: unless-stopped`, firewall via
`fame-firewall.service`, FUSE mount via the clouddrive2 container. Afterwards verify:

```bash
ssh fame 'uname -r; docker ps -q | wc -l; iptables -S DOCKER-USER | tail -1; ls /mnt/CloudNAS/115 | head -3'
```

Expect the new kernel, ~60 containers, a trailing `DROP` rule, and a listing (not an
empty/IO-error mount). cms/mdc depend on that mount — restart them if it came up late.

## Housekeeping

- **Disk:** `ssh fame 'docker system df; du -sh /srv/* | sort -rh | head'`. Old images from
  Renovate bumps accumulate. `docker image prune` removes untagged images with no container
  references; `docker image prune -a` also removes unused tagged images, including pre-pulled
  updates and local builds. Skip cleanup during deploys. Untagged images still referenced by
  containers become removable only after those containers are replaced and removed; shared
  layers remain while another image needs them. For a targeted refresh, verify health first,
  then use `docker image rm <old-image-id>` without `--force` to remove only the old image.
- **fail2ban:** `ssh fame 'fail2ban-client status sshd'` — see
  [bootstrap/fail2ban](../bootstrap/fail2ban/).
- **Firewall audit:** verification one-liners in
  [firewall.md → Verify](./firewall.md#verify).
- **OS updates:** security patches are unattended; Docker engine/compose upgrades are
  manual (`apt upgrade` — `live-restore` keeps containers up through the daemon restart).
