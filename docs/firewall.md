# Host firewall

How `Famesystems` (a.k.a. *fame*) restricts who can reach its published ports, and why it is
built the way it is. The deployable bits live in [`bootstrap/firewall/`](../bootstrap/firewall/);
this doc is the rationale + runbook.

> Like [`bootstrap/komodo`](../bootstrap/komodo/), the firewall is **not** a Komodo-managed
> stack — it is host infrastructure, deployed by hand and kept in git as a versioned record.

## Why a firewall at all

Every service is reached through the **Akko** reverse proxy: a public hostname resolves to Akko,
Akko's Caddy terminates TLS and **proxies back to fame's published port over the public network**
(`https://<svc>.lkwplus.com` → Akko → `fame-public-ip:200xx`).

The problem: Docker publishes those ports on `0.0.0.0` and, by default, does **not** restrict the
source. So anyone who learns fame's public IP can hit `http://<fame-ip>:20000` directly and
**bypass Akko entirely** — skipping its TLS and any front-door protection. The firewall closes
that hole: container ports are reachable **only from Akko**, with a short list of ports that
genuinely need the open internet.

## Design — and why it can't lock you out

This host once went dark after a firewall attempt fought with Docker's networking (recovered only
via VNC). The current design is shaped specifically to avoid that:

1. **Filter in `DOCKER-USER`, not `INPUT`.** Docker uses the **iptables** firewall backend here, so
   it provides the `DOCKER-USER` chain. Published-port traffic is **DNATed in *prerouting* and then
   *forwarded* to the container — it never traverses the host `INPUT` chain** (this is *the* classic
   "my INPUT drop rule doesn't block the Docker port" gotcha). The only correct place to filter it
   is the `forward` path, i.e. `DOCKER-USER`, which Docker evaluates **before** its own accept rules
   and **never wipes** on its own.
2. **Keep the `INPUT` policy at `accept`; never filter SSH there.** Host ports live on `INPUT`. We
   add exactly **one** jump from `INPUT` to our own `FAME-INPUT` subchain and only drop specific
   host-network ports inside it (currently clouddrive2's `19798`). SSH `11322`, Caddy `80/443`,
   komari `25774` and the `accept` policy are never touched — so a mistake here still *cannot* sever
   SSH, the #1 safeguard against repeating the lockout.
3. **No ruleset-owning tools** (ufw / firewalld). They take over chains and default policies and
   collide with Docker (a `FORWARD` default `DROP` alone breaks all container forwarding). We use
   plain `iptables`/`ip6tables` to manage **only** `DOCKER-USER`, persisted by a small systemd unit.
4. **Match the original port, not the DNATed one.** After DNAT, `--dport` sees the *container's*
   internal port (80, 8083, …), not the host port (20000…). So port exceptions match the pre-DNAT
   host port with `conntrack --ctorigdstport`. Source-IP matches (Akko) are unaffected by DNAT.
5. **Cover IPv4 *and* IPv6.** Every port is published on both. Akko is **IPv4-only**, so the IPv6
   `DOCKER-USER` has no trusted source — it passes only the public exceptions and drops the rest,
   closing the IPv6 direct-connect path that an IPv4-only allowlist would miss.

## Port policy

| Class | Ports | Rule |
|-------|-------|------|
| **Akko-only** (container) | every published port — the `20000–20999` range, komodo `9120`, … — except the exceptions below | `DOCKER-USER`: accept from Akko's IP, **drop** everything else from the WAN NIC |
| **Akko-only** (host-net) | clouddrive2 `19798` | `FAME-INPUT`: accept from Akko's IP, **drop** the rest from the WAN NIC |
| **Public exceptions** (container) | gitea SSH `222`, qBittorrent `65231` (tcp+udp), beszel hub `20011` | `DOCKER-USER`: accept from anywhere (matched via `--ctorigdstport`) |
| **Host-process** (not Docker) | SSH `11322`, Caddy `80/443`, komari `25774` | `INPUT` policy `accept` → **open to the internet** |

Why the public exceptions are public on purpose:
- **`222` gitea SSH** — `git clone/push` over ssh from anywhere.
- **`65231` qBittorrent** — BitTorrent needs unsolicited inbound from peers (tcp **and** udp).
- **`20011` beszel hub** — remote machines' agents report **straight to fame**; routing them through
  `beszel.lkwplus.com` would bounce the metrics through Akko for no reason.

> **Komari `25774`** is intentionally public. clouddrive2's `19798` is host-networked (so it can't
> use `DOCKER-USER`) and is restricted to Akko via the `FAME-INPUT` subchain shown below.

## The rules, in effect

`DOCKER-USER` (IPv4), applied for the WAN interface `eth0`:

```
-A DOCKER-USER -i eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
-A DOCKER-USER -i eth0 -s <AKKO_IP> -j RETURN
-A DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 222   -j RETURN
-A DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 65231 -j RETURN
-A DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 20011 -j RETURN
-A DOCKER-USER -i eth0 -p udp -m conntrack --ctorigdstport 65231 -j RETURN
-A DOCKER-USER -i eth0 -j DROP
```

IPv6 is identical minus the Akko line (Akko has no IPv6). Container-to-container traffic (on the
`br-*` bridges) and outbound traffic (`-o eth0`, plus `ESTABLISHED` return) never match `-i eth0`'s
`DROP`, so internal links and egress are unaffected.

Host-networked ports can't use `DOCKER-USER`, so they go through a parallel `FAME-INPUT` chain,
jumped to once from `INPUT` for the WAN interface:

```
-A INPUT -i eth0 -j FAME-INPUT
-A FAME-INPUT -p tcp --dport 19798 -s <AKKO_IP> -j RETURN
-A FAME-INPUT -p tcp --dport 19798 -j DROP
```

Only `19798` is matched, so SSH and every other host port fall straight through to the `INPUT`
`accept` policy. There is no DNAT here, so it matches `--dport` directly (unlike the published
ports above). The IPv6 `FAME-INPUT` drops `19798` outright (no Akko v6).

## Files

| File | Where | In git? |
|------|-------|---------|
| `fame-firewall.sh` | `/usr/local/sbin/` | ✅ `bootstrap/firewall/` (no secrets) |
| `fame-firewall.service` | `/etc/systemd/system/` | ✅ `bootstrap/firewall/` |
| `fame-firewall.conf` | `/etc/` | ❌ host-only — names the Akko IP (`*.conf.example` is versioned) |

The script reads `WAN_IF` and `AKKO_IP` from `/etc/fame-firewall.conf`, so the versioned script
carries **no IPs**. It also **cleans up the leftover `ufw-*` / `ufw6-*` chains** from the previous
failed attempt (idempotent — safe to re-run).

## Persistence

`fame-firewall.service` is `oneshot` + `RemainAfterExit`, ordered `After=docker.service` with
`PartOf=docker.service`, so it re-applies on boot **and** whenever Docker restarts (Docker rebuilds
`DOCKER-USER` and would otherwise drop our rules). We deliberately do **not** use
`iptables-persistent` — restoring a saved ruleset races Docker's own rule management.

## Runbook

### Deploy / re-deploy

```bash
# on this repo:
scp bootstrap/firewall/fame-firewall.sh      fame:/usr/local/sbin/fame-firewall.sh
scp bootstrap/firewall/fame-firewall.service fame:/etc/systemd/system/fame-firewall.service

# on the host (ssh fame), first time only — create the off-git config:
cp /path/to/fame-firewall.conf.example /etc/fame-firewall.conf
$EDITOR /etc/fame-firewall.conf      # set WAN_IF + AKKO_IP; chmod 600
chmod +x /usr/local/sbin/fame-firewall.sh

systemctl daemon-reload
systemctl enable --now fame-firewall.service
```

### Change a port / the Akko IP

- A **port** exception: edit `PUBLIC_TCP` / `PUBLIC_UDP` in `fame-firewall.sh`, re-`scp`,
  `systemctl restart fame-firewall`.
- The **Akko IP** or **WAN interface**: edit `/etc/fame-firewall.conf`, `systemctl restart
  fame-firewall`.

### Apply changes safely (auto-rollback — do this for any risky edit)

Arm a timer that restores the previous ruleset unless you cancel it, so a bad rule self-heals
instead of stranding you:

```bash
iptables-save  > /root/fw-backup-v4.rules
ip6tables-save > /root/fw-backup-v6.rules
systemd-run --on-active=600 --unit=fw-rollback \
  /bin/sh -c 'iptables-restore < /root/fw-backup-v4.rules; ip6tables-restore < /root/fw-backup-v6.rules'

systemctl restart fame-firewall      # apply the change

# verify (see below). If good:
systemctl stop fw-rollback.timer
# If you got locked out: do nothing — it auto-restores in 10 min.
```

### Verify

```bash
# from the host: rules present, no ufw leftovers
iptables -S DOCKER-USER; ip6tables -S DOCKER-USER
iptables-save | grep -c ufw          # expect 0

# from Akko (trusted) — should return HTTP codes:
ssh akko 'curl -s -o /dev/null -w "%{http_code}\n" --max-time 8 http://<fame-ip>:20000/'

# from any other host (untrusted) — Akko-only ports must hang/blocked, exceptions must answer:
curl -s4 --max-time 6 http://<fame-ip>:20000/   # 20000 → blocked (timeout)
curl -s4 --max-time 6 http://<fame-ip>:20011/   # beszel → answers
nc -z -w6 <fame-ip> 222                          # gitea-ssh → open
```

## Lessons (so the next person doesn't repeat the lockout)

- Filtering Docker-published ports belongs in **`DOCKER-USER` (forward)**, never the host `INPUT`
  chain — DNAT means `INPUT` never sees them anyway.
- Keep chain **policies at `accept`**; protect host-network ports in a dedicated subchain
  (`FAME-INPUT`) that only drops specific ports, never SSH.
- Don't install ufw/firewalld on a Docker host — they own the whole ruleset and fight Docker.
- Always apply firewall changes behind a **timed auto-rollback**.
