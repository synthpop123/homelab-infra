# Host: Oracle-Arm (arm)

One-page inventory of the second VPS — an Oracle Cloud ARM machine in Chuncheon, South
Korea, connected to the Komodo control plane on fame ([komodo-servers.md](./komodo-servers.md)).
Runs the **multica**, **storageui**, **dsh** and **beszel-agent** stacks (see below). The primary
host's page: [server.md](./server.md).

## System

| | |
|---|---|
| Access | `ssh arm` (root, key auth; sshd on port **11322**, fail2ban-guarded) |
| OS | Ubuntu 24.04 LTS (noble), Oracle kernel 6.17 |
| Hardware | 2 vCPU (Ampere/Neoverse-N1, **aarch64**), 12 GiB RAM, no swap, 96 GiB disk |
| Network | private `10.0.0.0/24` VCN address on `enp0s6` (public IPv4 is Oracle-NATed) + a public IPv6; both stay off-git |
| Region | `ap-chuncheon-1` (Oracle Cloud free-tier ARM shape) |

**It's ARM.** Any stack targeted at this host needs `linux/arm64` images — most official
images are multi-arch, but check before pointing a `[[stack]]` here.

## Komodo

- **Periphery agent** — systemd service (`periphery.service`, enabled), binary at
  `/usr/local/bin/periphery`, config `/etc/komodo/periphery.config.toml`. Connects
  **outbound** to `https://komodo-core.lkwplus.com` as Server **`Oracle-Arm`** — no
  inbound port open for Komodo. Keypair: `/etc/komodo/keys/`. Mechanism + re-adopt
  runbook: [komodo-servers.md](./komodo-servers.md).
- History: first onboarded 2026-06-16 (as `Oracle-Arm-1`); the Server resource was later
  deleted from Komodo, leaving the agent orphaned (retrying with a dead onboarding key)
  until 2026-07-14, when it was headlessly re-adopted with its existing keypair, the
  service `enable`d, and the whole thing renamed to `Oracle-Arm`.

## Reverse proxy (the arm model)

Unlike fame (whose services sit behind the **Akko** proxy host), arm serves directly:
DNS (`multica.lkwplus.com` → CNAME `arm.lkwplus.com`) points at this machine, and a
**host Caddy** (80/443, apt package from Caddy's official repo) terminates TLS and
reverse-proxies to stack ports bound on `127.0.0.1` (arm's own registry section in
[ports.md](./ports.md#allocations-arm)). Loopback binding means container ports never
touch the `DOCKER-USER` exposure path. Config: `/etc/caddy/Caddyfile` on the host.

## Host processes (not Docker)

| Process | Port | Purpose |
|---------|------|---------|
| sshd | 11322 | admin access (public; fail2ban-guarded) |
| Caddy | 80/443 | TLS + reverse proxy for this host's stacks (multica / storageui / dsh) |
| multica daemon | — | Multica agent daemon (user `agent`; binary under `~agent/.local/bin`) |
| komari-agent | outbound | reports to the komari status page on fame |
| unified-monitoring-agent | outbound | Oracle Cloud's own telemetry (stock on OCI images) |
| rpcbind | 111 (WAN-dropped) | stock on OCI images; left running but closed by `ARM-INPUT` |

## systemd units that matter

- **`arm-firewall.service`** — deny-by-default `DOCKER-USER` rules (v4+v6) so any future
  published port starts internet-unreachable, plus an `ARM-INPUT` drop for rpcbind.
  `PartOf=docker.service`, so it re-runs whenever Docker restarts. Source:
  [`bootstrap/firewall/`](../bootstrap/firewall/) (`arm-firewall.*`).
- **`caddy.service`** — host reverse proxy for this host's stacks (see above).
- **`fail2ban.service`** — sshd jail on the journal backend, ban targets port 11322
  (same [`jail.local`](../bootstrap/fail2ban/jail.local) as fame; banning within minutes
  of deploy).
- **`periphery.service`** — the Komodo agent (above).
- **`unattended-upgrades`** — Ubuntu defaults.
- docker, komari-agent — `enabled`.

## Docker daemon (`/etc/docker/daemon.json`)

Mirrors fame: log rotation `json-file` 10 MB × 3 per container, `live-restore: true`.
Docker **29.5.3**, default address pools.

## Stacks on this host

- **multica** ([stacks/multica](../stacks/multica/)) — the first stack here. Backend +
  web + bundled Postgres; data under `/srv/multica/`; ports `127.0.0.1:20000/20001`
  fronted by the host Caddy at `multica.lkwplus.com`. The daemon side (the `multica` CLI
  + AI coding tools) runs as host user **`agent`**, not a container. Keep the CLI at
  `/home/agent/.local/bin/multica` (agent-owned) so web-triggered self-updates can write
  `multica-update-*` next to the binary — **do not** install it under `/usr/local/bin`
  (root-owned; update fails with `permission denied`). Prefer
  `MULTICA_BIN_DIR=/home/agent/.local/bin` when (re)installing as `agent`, or skip
  sudo so the installer falls back to `~/.local/bin`.
- **storageui** ([stacks/storageui](../stacks/storageui/)) — Storage UI, web file manager
  for the two Cloudflare R2 buckets (`imagebed` / `public`). Single stateless container, no
  volumes; config is all env vars (credentials via Komodo Variables). Port `127.0.0.1:20002`
  fronted by the host Caddy at `storageui.lkwplus.com`.
- **dsh** ([stacks/dsh](../stacks/dsh/)) — DeepSeek Harness Web UI, image built from upstream
  source: no container image is published, and upstream carries no git tags, so the Dockerfile
  pins an exact commit in `DSH_REF` (currently `47f9438`, upstream version `0.1.0-rc.5`).
  Renovate cannot see that ref — upgrades are a manual SHA bump, redeployed with `--build`; a
  Dockerfile-only change is not selected by `BatchDeployStackIfChanged` either (`file_paths` is
  compose-only), so deploy it by hand. The compose sets no `image:` key on purpose: Komodo's
  `auto_pull` runs `compose pull` before deploying and aborts on a locally-built tag ("pull
  access denied"), exactly as for autobrr-notify. Host-networked on `127.0.0.1:20003` (dsh rejects
  `--host 0.0.0.0`); data under `/srv/dsh/`; process uid **1002** matches host user `agent`.
  DeepSeek API keys can be set in the Web UI or via optional `DEEPSEEK_API_KEY` (Komodo
  Variable).
  **Auth is not optional here.** dsh ships no authentication of its own and its default agent
  preset carries `tool-bash`/`tool-fs`, so an open origin is remote code execution on this
  host — upstream refuses to bind `0.0.0.0` for exactly that reason, and a reverse proxy
  bypasses the guard. The `dsh.lkwplus.com` vhost therefore gates on Caddy `basic_auth`
  (bcrypt hash in `/etc/caddy/Caddyfile`, off git). The container's `--trusted-host` flag is
  only the `/api` browser-trust fence (Host-header authority), never a credential check.
  **The Settings pages answer 403 through the reverse proxy, by upstream design.**
  `PRIVILEGED_METHODS` in `packages/client/connection` (`settings.*`, `credentials.*`,
  `llm.discoverModels`) re-runs the fence with an *empty* trust list, pinning those calls to a
  loopback `Host` — no `--trusted-host` value or patch layer can grant them. Symptom in the UI:
  `加载提供方目录失败: transport failure for /api/settings.describe: HTTP 403`. Ordinary
  chat/session calls are unaffected. To reach Settings, tunnel instead of proxying:
  `ssh -L 20003:127.0.0.1:20003 arm`, then open `http://127.0.0.1:20003`.
- **beszel-agent** ([stacks/beszel-agent](../stacks/beszel-agent/)) — metrics agent for
  the beszel hub on fame. Host-networked, outbound-only to `fame.lkwplus.com:20011`
  (fame's public-exception hub port, skipping Akko); data under `/srv/beszel-agent/`;
  fallback listener 45876 stays closed by the deny-by-default firewall.

## Known state / pending

- **Port registry** — this host's own allocation lives in
  [ports.md → Allocations (arm)](./ports.md#allocations-arm), starting at `20000`,
  loopback-bound behind the host Caddy. Any future port that must be *publicly* published
  needs an explicit exception in `arm-firewall.sh` (`PUBLIC_TCP`/`PUBLIC_UDP`).
- **No swap** — 12 GiB RAM machine; add a swapfile only if workloads ever need it.
- **k3s history** — the host briefly ran a k3s cluster (2026-06, pre-Komodo); it was
  uninstalled back then, and the last leftovers (helm binary, `/root/.kube`, helm caches,
  a Tailscale auth key sitting in root's bash history, orphaned `agent-os_*` volumes and
  build cache) were purged during the 2026-07-16 inspection.
