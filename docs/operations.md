# Day-2 operations

Routine checks and the short paths for poking the live deploy. Host inventory:
[server.md](./server.md). Deploy flow: [workflow.md](./workflow.md). All commands run from
this machine via `ssh fame` unless noted.

## Health check

```bash
ssh fame 'docker ps --filter health=unhealthy --filter status=restarting --format "{{.Names}}\t{{.Status}}"'
ssh fame 'systemctl --failed --no-legend; df -h / | tail -1'
```

Empty output + disk under ~80% = healthy. Dashboards: **beszel** (per-container CPU/mem),
**komari** (public uptime page), **tautulli** (Plex sessions) — URLs in the README table.

## Komodo

- **UI** — the Komodo hostname (see README). Every stack shows its deploy state, logs, and
  a Redeploy button there; that is the default tool for one-off operations.
- **`km` CLI** — ships inside `komodo-core`. Database commands work as-is
  (`docker exec komodo-core km database backup -y`); *API* commands (deploy/list/…) need an
  API key created in the UI (Settings → API Keys), passed as env:

```bash
ssh fame 'docker exec -e KOMODO_CLI_KEY=... -e KOMODO_CLI_SECRET=... \
  komodo-core km execute deploy-stack <name> -y'
```

## Deploying

Normal path: **push to `main`** — the `Redeploy On Push` procedure syncs definitions, then
deploys only changed stacks ([workflow.md](./workflow.md)). Manual deploy (UI or `km`) is
needed only when:

- a PR changed **build-context files only** (e.g. `stacks/autobrr/notify/`) — compose
  unchanged means `BatchDeployStackIfChanged` skips it; redeploy the stack so
  `--build` picks it up;
- you changed a **Komodo Variable** and want it applied now (redeploy the consuming stack);
- recovering from a failed deploy after fixing the cause.

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
  Renovate bumps accumulate — `docker image prune -a` is safe (running tags are kept; any
  pinned tag can be re-pulled), but skip it while a deploy is running.
- **fail2ban:** `ssh fame 'fail2ban-client status sshd'` — see
  [bootstrap/fail2ban](../bootstrap/fail2ban/).
- **Firewall audit:** verification one-liners in
  [firewall.md → Verify](./firewall.md#verify).
- **OS updates:** security patches are unattended; Docker engine/compose upgrades are
  manual (`apt upgrade` — `live-restore` keeps containers up through the daemon restart).
