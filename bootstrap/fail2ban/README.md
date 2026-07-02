# fail2ban bootstrap

SSH brute-force protection for the host (~800 failed attempts/day). Like the rest of
[`bootstrap/`](../), deployed **by hand** and versioned here as a record — no secrets in
these files.

| File | Installs to |
|------|-------------|
| `jail.local` | `/etc/fail2ban/jail.local` |

The file exists because of two Debian-12 gotchas (details in its comments): the journal
backend (no `auth.log` on bookworm) and the non-default sshd port.

## Deploy

```bash
scp bootstrap/fail2ban/jail.local fame:/etc/fail2ban/jail.local
ssh fame 'fail2ban-client -t && systemctl enable --now fail2ban && systemctl restart fail2ban'
```

## Operate

```bash
ssh fame 'fail2ban-client status sshd'      # current + total bans
ssh fame 'fail2ban-client set sshd unbanip <ip>'
```
