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
| komari-agent | outbound | reports to the komari probe on fame |
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
- **dsh** ([stacks/dsh](../stacks/dsh/)) — DeepSeek Harness Web UI, image built locally from
  upstream's **npm package**: no container image is published, but the `@deepseek-ai/dsh-*`
  family is public on npm (since `0.1.0-rc.5`) and the CLI package ships the Web UI assets,
  so the Dockerfile just `npm install -g @deepseek-ai/dsh@${DSH_VERSION}` — no monorepo
  clone, no `pnpm run build`, and an 881MB image instead of the 2.53GB source-built one
  (measured on this host; the build itself drops from minutes to well under one).
  **`DSH_VERSION` is pinned in `compose.yaml`'s `build.args`, not in the Dockerfile**, and
  that is load-bearing: `file_paths` is compose-only, so only a compose change is selected by
  `BatchDeployStackIfChanged`. Renovate tracks the pin through the `customManagers` regex
  entry in `renovate.json` and merging its PR redeploys with `--build` unattended. Upstream has
  only ever shipped prereleases, so that package also sets `ignoreUnstable: false` — without it
  Renovate would silently skip a jump to a new prerelease line (it has happened twice:
  `0.0.1-rc.5` → `0.1.0-rc.2`, `0.1.1-rc.2` → `0.1.2-alpha.1`), and note that npm's `latest`
  dist-tag lags on the rc line while `alpha` carries the newer one. It is a developer
  preview that warns of breaking changes, so read the release notes before merging. The
  base image (Node major) is still a Dockerfile-only change: deploy those by hand.
  The compose sets no `image:` key on purpose: Komodo's
  `auto_pull` runs `compose pull` before deploying and aborts on a locally-built tag ("pull
  access denied"), exactly as for autobrr-notify. Host-networked on `127.0.0.1:20003` (dsh rejects
  `--host 0.0.0.0`); data under `/srv/dsh/`; process uid **1002** matches host user `agent`.
  DeepSeek API keys can be set in the Web UI or via optional `DEEPSEEK_API_KEY` (Komodo
  Variable).
  **Auth is not optional here.** The default agent preset carries `tool-bash`/`tool-fs`, so an
  open origin is remote code execution on this host — upstream refuses to bind `0.0.0.0` for
  exactly that reason, and a reverse proxy bypasses the guard. The `dsh.lkwplus.com` vhost
  therefore gates on Caddy `basic_auth` (bcrypt hash in `/etc/caddy/Caddyfile`, off git). The
  container's `--trusted-host` flag is only the `/api` Host/Origin fence, never a credential
  check.

  **Logging in takes a one-time token (since `0.1.2-alpha.1`).** Each process mints a launch
  token; `GET /?token=…` is the only way to spend it, and spending it mints an authority-bound
  signed cookie (30 days) that authorizes everything afterwards, `/api` WebSocket included. The
  token is printed once at startup, against the container's own URL:

  ```bash
  ssh arm 'docker logs dsh 2>&1 | grep -o "token=[A-Za-z0-9_-]*"'
  ```

  Move it onto `https://dsh.lkwplus.com/?token=…` and open that once. The signing secret lives
  in `/srv/dsh/data/.credentials.yaml`, so restarts and redeploys do **not** log you out; a
  `401 dsh web authentication required` on a healthy container means the cookie expired.

  **The Settings pages need `ownsHost`, injected into `index.html` at build time.** The gate is
  client-side and reads the *page* authority, so no proxy header reaches it:
  `isLoopback = transport?.ownsHost === true || isLoopbackHostname(location.hostname)`, and
  `dsh-client-ui-settings` turns a false there into `persistence: "memory"` — the symptom is
  `加载提供方目录失败: settings are unavailable in this browser` on 设置 → 模型. Only the UI was
  hidden: since `0.1.2-alpha.1` the Host half has no privileged loopback tier, so the flag
  grants a remote browser nothing the server was not already answering.

  **The vhost no longer rewrites `Host`/`Origin`.** Up to `0.1.1-rc.2`, `PRIVILEGED_METHODS`
  (`settings.*`, `credentials.*`, `llm.discoverModels`) re-ran the fence with an *empty* trust
  list, pinning those calls to a loopback `Host`, and the vhost faked one with `header_up Host
  127.0.0.1:20003` + `header_up Origin http://127.0.0.1:20003`. That tier is gone, and the
  rewrite made dsh's own Origin fence vacuous, so it and the `@foreign_origin` matcher that
  compensated for it were removed on 2026-09-01. The vhost now forwards the real
  `dsh.lkwplus.com` authority, matching `--trusted-host`, and dsh enforces `Origin == Host`
  plus a `sec-fetch-site: cross-site` refusal itself. Verified on `0.1.2-alpha.3`: token
  exchange 303s and sets the cookie, `/` and `/api` answer with it, an untrusted `Host` or a
  cross-site marker both 403.

  **After a version bump, clear `/srv/dsh/data/profiles/node_modules`.** dsh boots a profile out
  of `$DSH_HOME` whose `node_modules` is a tree of absolute symlinks into the image's global
  install; a bump adds the new links but never removes the old ones (103 dangling by
  `0.1.1-rc.2`). Nothing breaks today, but the package set churns every release. The tree is
  fully derived — the profile declares no dependencies of its own — so dsh rebuilds it on boot:

  ```bash
  ssh arm 'docker stop dsh && rm -rf /srv/dsh/data/profiles/node_modules && docker start dsh'
  ```
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
