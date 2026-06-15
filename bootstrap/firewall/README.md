# Firewall bootstrap

The **host firewall** for `Famesystems` — restricts Docker-published ports to the Akko reverse
proxy, with a few internet-facing exceptions. Like [`../komodo`](../komodo/), this is host
infrastructure deployed **by hand** (not a Komodo-managed stack), kept in git as a versioned
record and disaster-recovery aid.

> Full rationale, port policy, and runbook: [`docs/firewall.md`](../../docs/firewall.md).

## Files

| File | Installs to | Purpose |
|------|-------------|---------|
| `fame-firewall.sh` | `/usr/local/sbin/` | Applies `DOCKER-USER` rules (v4+v6) and cleans up leftover `ufw-*` chains. Idempotent; reads config from `/etc/fame-firewall.conf`. **No IPs in this file.** |
| `fame-firewall.service` | `/etc/systemd/system/` | Runs the script `After=docker.service` (and re-runs if Docker restarts). Enable for persistence. |
| `fame-firewall.conf.example` | — | Template for `/etc/fame-firewall.conf` (the real file stays **off git**; it names the Akko IP). |

## Why it's built this way (the short version)

- Docker uses the **iptables** backend here → the `DOCKER-USER` chain exists and is the *only*
  correct place to filter published ports (they're DNATed + forwarded, bypassing host `INPUT`).
- The script keeps the `INPUT` policy at `accept` and adds **one** jump to its own `FAME-INPUT`
  subchain for host-networked ports (e.g. clouddrive2 `19798`), dropping only those specific ports
  there — SSH is never filtered, so it cannot lock SSH out.
- No ufw/firewalld (they own the whole ruleset and collide with Docker); persistence is a small
  systemd unit, not `iptables-persistent`.

## Deploy

```bash
scp fame-firewall.sh      fame:/usr/local/sbin/fame-firewall.sh
scp fame-firewall.service fame:/etc/systemd/system/fame-firewall.service
# on the host: create /etc/fame-firewall.conf from the example (set WAN_IF + AKKO_IP, chmod 600)
ssh fame 'chmod +x /usr/local/sbin/fame-firewall.sh && systemctl daemon-reload && systemctl enable --now fame-firewall.service'
```

Apply risky changes behind a timed auto-rollback — see
[`docs/firewall.md` → Runbook](../../docs/firewall.md#runbook).
