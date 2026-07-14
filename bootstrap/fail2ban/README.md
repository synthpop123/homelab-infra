# fail2ban bootstrap

SSH brute-force protection (~800 failed attempts/day on fame; arm caught its first ban
within minutes of deploy). The **same `jail.local` is deployed on both hosts** — fame and
arm both run sshd on 11322 and both use the journal backend. Like the rest of
[`bootstrap/`](../), deployed **by hand** and versioned here as a record — no secrets in
these files.

| File | Installs to |
|------|-------------|
| `jail.local` | `/etc/fail2ban/jail.local` (fame **and** arm) |

The file exists because of two gotchas (details in its comments): the journal backend
(Debian 12 ships no `auth.log`; harmless-but-consistent on arm's Ubuntu 24.04) and the
non-default sshd port.

## Deploy

```bash
# same for arm — swap the host alias
scp bootstrap/fail2ban/jail.local fame:/etc/fail2ban/jail.local
ssh fame 'fail2ban-client -t && systemctl enable --now fail2ban && systemctl restart fail2ban'
```

## Operate

```bash
ssh fame 'fail2ban-client status sshd'      # current + total bans
ssh fame 'fail2ban-client set sshd unbanip <ip>'
```
