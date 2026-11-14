# Host: Famesystems (fame)

One-page inventory of the primary VPS — what lives on the host *besides* the
Komodo-managed stacks, and its known state. Day-2 commands are in
[operations.md](./operations.md). It runs the Komodo Core that also manages the second
host, [Oracle-Arm](./server-arm.md) (its stacks are listed on that page); how servers join the
control plane is in [komodo-servers.md](./komodo-servers.md).

## System

| | |
|---|---|
| Access | `ssh fame` (root, key auth; sshd on port **11322**) |
| OS | Debian 12 (bookworm), kernel 6.1 |
| Hardware | 6 vCPU (AMD EPYC 9654), 24 GiB RAM, 1 GiB swap, 294 GiB disk |
| Network | static IPv4 + IPv6 on `eth0` (`/etc/network/interfaces`; addresses stay off-git, like the Akko IP in `/etc/fame-firewall.conf`) |

DNS: service hostnames (`*.lkwplus.com`) are CNAMEs to the **Akko** reverse proxy, which
forwards to fame's published ports. One admin hostname (the Komodo UI) resolves to fame
directly and is served by the host Caddy — see the host's `/etc/caddy/Caddyfile`.

## Host processes (not Docker)

| Process | Port | Purpose |
|---------|------|---------|
| sshd | 11322 | admin access (public; fail2ban-guarded) |
| Caddy | 80/443 | one site: the Komodo-UI hostname → `127.0.0.1:9120` (direct admin path, no Akko hop) |
| komari + komari-agent | 25774 | server probe both hosts report into (public on purpose); panel upgrades: [`bootstrap/komari/`](../bootstrap/komari/) |
| exim4 | local only | MTA for cron mail |

The `clouddrive` process visible on host port `19798` is the **clouddrive2 container**
(host-networked); it provides the FUSE mount `/mnt/CloudNAS/115` that the media pipeline
reads — see [media.md](./media.md).

## systemd units that matter

- **`fame-thp.service`** — sets THP background-collapse limits `max_ptes_none=0`
  and `max_ptes_swap=0` before Docker starts. THP remains `always`; this limits
  sparse-page expansion and swap-in during collapse, not fault-time allocations.
  Installation and rollback: [`bootstrap/thp/`](../bootstrap/thp/).
- **`fame-firewall.service`** — applies the `DOCKER-USER` rules; `PartOf=docker.service`, so
  it re-runs whenever Docker restarts. Source: [`bootstrap/firewall/`](../bootstrap/firewall/).
- **`fail2ban.service`** — sshd jail on the systemd journal backend (bookworm has no
  `auth.log`), ban targets port 11322. Config: [`bootstrap/fail2ban/`](../bootstrap/fail2ban/).
- **`unattended-upgrades`** — Debian **security** origin only. Docker engine/compose and
  other third-party repos are **not** auto-upgraded — do those by hand (with `live-restore`
  enabled, a daemon restart keeps containers running).
- **`orphan-cleanup.timer`** (03:20) and **`muvyo-index.timer`** (09:30) — housekeeping for the
  Amane STRM trees; a cleanup that refuses to act fails its unit and alerts on Telegram. Source
  and runbook: [`bootstrap/media/`](../bootstrap/media/); what they do: [media.md](./media.md).
- caddy, komari, docker — all `enabled`.

## Docker daemon (`/etc/docker/daemon.json`)

- Log rotation: `json-file`, 10 MB × 3 per container.
- Address pools: `172.17–172.21.0.0/16` (size /24). `mediacenter-net` (`172.22.0.0/24`)
  is deliberately **outside** the pools and created by hand — see
  [media.md](./media.md#the-shared-network).
- `live-restore: true` — containers survive daemon restarts/upgrades (not host reboots).

## Disk layout

| Path | What | Size |
|------|------|------|
| `/srv/<service>/` | all app data (bind mounts) | ~108 GiB (2026-11) — plex 64 (mostly metadata/artwork), amane 23, emby 7 (only `data`, the shared STRM tree — the name outlived Emby), muvyo 5.5, immich 1.4 |
| `/srv/_backups/` | snapshots from the 2026-10 media move (two `*-pre-migration-*`) and the muvyo DB dump taken before Emby's removal (`muvyo-pre-emby-removal-20261114`) | 7 GiB — delete once the new pipeline is trusted |
| `/root/archive/` | one-off scripts from that migration, kept for reference | small |
| `/opt/komodo/` | Komodo control plane (compose + env) | see [bootstrap/komodo](../bootstrap/komodo/) |
| `/opt/{komari,containerd,fake115uploader}` | host tools; fake115uploader is dormant | small |
| `/etc/komodo/repos/homelab-infra` | Komodo's clone of this repo | — |
| `/etc/komodo/backups/` | daily Mongo dumps, 14 kept | — |

The `/opt` → stacks migration is **complete**: no compose-managed services remain under
`/opt`, and the legacy `13xxx` ports are all gone.

## Known state / pending

- **Reboot pending** — kernel `6.1.0-54` installed, `-52` still running (last reboot 2026-08).
  A reboot picks up the new kernel; containers come back via `restart: unless-stopped`, the
  firewall re-applies, clouddrive2 remounts FUSE (see
  [operations.md → Reboot](./operations.md#reboot)).
- **Swap 1 GiB is ~full** (`swappiness=10`) while RAM has headroom — stale pages, harmless.
  Add a swapfile only if OOM ever shows up.
- **Manual upgrades queued** — docker-ce / compose-plugin / containerd (+ a few
  non-security debs) are upgradable; not covered by unattended-upgrades.
- 2026-07 fixes: fail2ban repaired (dead since 2025-08 — bookworm ships no rsyslog/auth.log,
  so the sshd jail found no log file; now on the journal backend, see
  [bootstrap/fail2ban](../bootstrap/fail2ban/)); `networking.service` failure root-caused to a
  duplicate IPv6 default-route line in `/etc/network/interfaces` (now `|| true`-guarded);
  stale failed units cleared; `en_US.UTF-8` locale generated; unattended-upgrades +
  `live-restore` enabled.
