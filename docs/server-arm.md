# Host: Oracle-Arm (arm)

One-page inventory of the second VPS — an Oracle Cloud ARM machine in Chuncheon, South
Korea, connected to the Komodo control plane on fame ([komodo-servers.md](./komodo-servers.md))
but **running no stacks yet**. The primary host's page: [server.md](./server.md).

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

## Host processes (not Docker)

| Process | Port | Purpose |
|---------|------|---------|
| sshd | 11322 | admin access (public; fail2ban-guarded) |
| komari-agent | outbound | reports to the komari status page on fame |
| unified-monitoring-agent | outbound | Oracle Cloud's own telemetry (stock on OCI images) |
| rpcbind | 111 (WAN-dropped) | stock on OCI images; left running but closed by `ARM-INPUT` |

## systemd units that matter

- **`arm-firewall.service`** — deny-by-default `DOCKER-USER` rules (v4+v6) so any future
  published port starts internet-unreachable, plus an `ARM-INPUT` drop for rpcbind.
  `PartOf=docker.service`, so it re-runs whenever Docker restarts. Source:
  [`bootstrap/firewall/`](../bootstrap/firewall/) (`arm-firewall.*`).
- **`fail2ban.service`** — sshd jail on the journal backend, ban targets port 11322
  (same [`jail.local`](../bootstrap/fail2ban/jail.local) as fame; banning within minutes
  of deploy).
- **`periphery.service`** — the Komodo agent (above).
- **`unattended-upgrades`** — Ubuntu defaults.
- docker, komari-agent — `enabled`.

## Docker daemon (`/etc/docker/daemon.json`)

Mirrors fame: log rotation `json-file` 10 MB × 3 per container, `live-restore: true`.
Docker **29.5.3**, idle — no containers, no data, default address pools, default networks
only.

## Known state / pending (before the first stack lands here)

- **No `/srv` layout yet** — created per-service when the first stack arrives.
- **Port registry** — [ports.md](./ports.md) is fame's allocation; ports on this host will
  get their own scheme when the first published service lands. Every published port is
  dropped by `arm-firewall.sh` until explicitly excepted there — decide per service
  whether it's public or proxied.
- **No reverse-proxy story yet** — fame's services sit behind Akko; nothing equivalent is
  decided for arm.
- **No swap** — 12 GiB RAM idle machine; add a swapfile only if workloads ever need it.
