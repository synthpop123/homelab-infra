# Media housekeeping timers (fame)

Two host-side timers that keep the Amane-organized STRM trees (`/srv/emby/data/{Japan,Western}`)
in step with 115. They talk to Amane, Muvyo and Plex over their published localhost ports and
touch files under `/srv`, so they run on the host, not in a stack. What they are for:
[`docs/media.md`](../../docs/media.md).

Like the rest of [`bootstrap/`](../), this is deployed **by hand** and kept in git as a versioned
record.

## Files

| File | Installs to | Purpose |
|------|-------------|---------|
| `orphan-cleanup.py` | `/usr/local/sbin/` | Nightly, local only: trashes STRM/metadata left without a counterpart (to `/srv/emby/data/.trash/<date>/`, kept 14 days). Stops and alerts instead of acting when a tree looks wrong. |
| `orphan-cleanup.{service,timer}` | `/etc/systemd/system/` | Runs it with `--apply` at 03:20. |
| `muvyo-index.py` | `/usr/local/sbin/` | Runs Muvyo's incremental 115 file-index sync over `/Porn` and `/Japan`, so a delete in the 115 app finds its STRM. |
| `muvyo-index.{service,timer}` | `/etc/systemd/system/` | Runs it at 09:30, after the 08:30 Media Intake. |

## Secrets

None are in these files, and none belong here. Each script reads what it needs on the host:

| Secret | Read from |
|--------|-----------|
| Amane API token | `/srv/amane/data/token` (Amane generates it) |
| Plex token | Plex's own `Preferences.xml` under `/srv/plex/config` |
| Muvyo API key | `/root/.muvyo.api` (root-only, `0600`; create it by hand) |
| Telegram bot token + chat id | `/etc/komodo/repos/homelab-infra/stacks/amane/.env`, which Komodo writes when it deploys the amane stack. The unit loads it as an optional `EnvironmentFile`. |

## Deploy

From the repository root:

```sh
scp bootstrap/media/orphan-cleanup.py bootstrap/media/muvyo-index.py fame:/usr/local/sbin/
scp bootstrap/media/*.service bootstrap/media/*.timer fame:/etc/systemd/system/
ssh fame 'chmod 755 /usr/local/sbin/orphan-cleanup.py /usr/local/sbin/muvyo-index.py && systemctl daemon-reload && systemctl enable --now orphan-cleanup.timer muvyo-index.timer'
```

## Check

```sh
ssh fame 'python3 /usr/local/sbin/orphan-cleanup.py'            # dry run: prints the plan, changes nothing
ssh fame 'journalctl -u orphan-cleanup -n 20 --no-pager'        # last runs
ssh fame 'tail -3 /srv/amane/muvyo-index.log'
```

## When orphan-cleanup stops

A stop means one tree was skipped untouched: the script sends a Telegram message and the unit
fails, so it also shows in `systemctl --failed`. The reasons:

| Stop | Meaning |
|------|---------|
| `N actions > 40: needs a human look` | Too many orphans at once for a routine night. Run it dry and read the plan. If the list is right, apply that one tree with the limit raised: `ORPHAN_MAX_ACTIONS=300 python3 /usr/local/sbin/orphan-cleanup.py --apply --only <tree>`. Otherwise fix what orphaned them. |
| `amane rows … < 90% of STRMs …` | Amane's index is missing a large part of the tree (a library was removed or re-created). Nothing local is wrong until that is settled. |
| `amane unreachable` | Amane was down at 03:20; the next night retries. |
| `tree missing or has no STRM` | `/srv/emby/data/<tree>` is empty or gone. |

STRMs under `<tree>/_inbox` do not count toward the 40: the intake leaves one behind for every
file it stages, and a large intake leaves hundreds. `amane tasks in flight` is not a stop — the
run is skipped quietly and the next night picks it up.

After fixing the cause, clear the failed state with `systemctl reset-failed orphan-cleanup.service`
or just let the next run succeed.
