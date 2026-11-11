# Media pipeline

A cloud-storage (115) media library served without keeping the files on disk. The library
is split by owner:

- **Movie / TV** — **muvyo** owns them end to end: uploads finished downloads to 115,
  organizes them, writes the `.strm` + `-mediainfo.json` trees, and serves the 302 links.
  Watched with **Plex** (via Cirvel) and **Vyo** (Muvyo's own player).
- **JAV / Porn** — **Amane** owns them: it organizes the videos on 115 (`/Japan`, `/Porn`) and
  writes `.strm` + NFO + images to `/srv/emby/data/{Japan,Western}`; Cirvel adds the
  `-mediainfo.json`. Watched with Plex (JAV, Porn). Deletes made in the 115 app reach the
  STRM trees through muvyo's 115 life events. (mdc is stopped and its data, the old cms `JAV` tree and Emby's Porn library are gone.)
- **Hentai** — stays on 115 only, in no media server. cms (which wrote its STRM tree) is stopped like
  mdc; `/srv/emby/data/Hentai` (.strm + nfo/images) is kept frozen in case a library takes it over later.

This doc is the topology — each stack's compose has the per-service detail.

## Flow

```
qBittorrent completed/{Movie,TV}            115 netdisk
  │ muvyo directory monitor                   │ FUSE mount /mnt/CloudNAS/115
  │ (copy-upload, organize, keep seeding)     │ (clouddrive2 — host-networked, privileged)
  └──────────────► 115 /Movie, /TV ◄──────────┤
                        │ 115 life events      │
                        ▼                      │
  muvyo ─► .strm + -mediainfo.json ─► /srv/emby/data/{Movie,TV}
                        │                      │
                        │       cms ─► .strm ──┼─► /srv/emby/data/Hentai   (legacy, stopped)
                        │                      │
                        │ amane ─► .strm/nfo ──┴─► /srv/emby/data/{Japan,Western}
                        ▼     (muvyo life events: deletes)
  plex (Cirvel)  reads Movie/TV ro, Japan (JAV), Western (Porn)
  vyo  (muvyo)   reads Movie/TV
  emby           Movie/TV libraries frozen as an image source (see below)

  playback: the client follows a 302 to the real 115 download link, served by muvyo for
  every live tree (Movie, TV, Japan, Western); no media bytes transit this host
```

**Getting new Movie/TV in:** download in qBittorrent — the default save path is
`completed/Movie`; pick the `TV` category for series (categories set the path, so automatic
torrent management stays on). Two muvyo directory-monitor rules upload `Movie` → 115 `/Movie`
and `TV` → 115 `/TV` (copy, so qB keeps seeding). Anything offline-downloaded or saved
straight into 115 goes under `/Others/待整理/{Movie,TV}`, which muvyo's 115 life events
organize the same way; edits made in the 115 app under `/Movie`, `/TV` are mirrored into the
STRM tree. The organize target is never the 115 root — muvyo fails with `Cloud path not
found:` there.

**Getting new JAV/Porn in:** put the video (or the whole download folder) under 115
`/Others/待整理/JAV` or `/Others/待整理/Porn`. The Komodo procedure **Media Intake** runs the
one-shot `amane-intake` job daily at 08:30 — or press *Run* for an on-demand intake. It moves the
videos into the library's `_inbox`, scrapes (JAV: the usual content routes; Porn: ThePornDB on a
`Studio.YY.MM.DD` number taken from the file name, so scene-release names like
`blackedraw.25.10.28.name` work), organizes, and Plex picks the new `.strm` up by itself. Amane's
own library automation stays off — without a CloudDrive2 membership (webhook) it would have to
walk the whole tree on 115. Rename an organized file only in Amane, never in the 115 app (a rename
leaves a dead STRM). Plex skips each tree's `_inbox`, where
muvyo's life events give every file moved in a STRM and then ask Plex to scan that folder alone: a
`.plexignore` at `/srv/emby/data/{Japan,Western}` (`_inbox/*`) covers full scans, and one inside
each `_inbox` (`*`) covers those partial scans, which ignore the tree-root file. The nightly
`orphan-cleanup` restores the inner one if it is gone and trashes the `_inbox` STRM muvyo leaves
behind once Amane has organized the file away.

A download folder dropped into `待整理` usually carries ads next to the film. Once the film has
been moved out, the intake deletes such a folder on 115 when every file left in it is under 30 MB
and nothing in it has changed for a day (so a folder still uploading is left alone). Loose files
directly under `待整理/{JAV,Porn}` are never deleted.

**The intake report** goes to Telegram (and the container log) whenever a run handled or left
something; a run with nothing to report stays silent. It lists every original name → number and
marks what to check; titles only one site had are noted in the log alone (`weak in:`). A **success
does not mean a right match**: Amane only needs the number it read from the name to exist on a site.

| Mark | Meaning |
|------|---------|
| 🔴 | Already in the library, but doubtful: the number is not a contiguous piece of the name (`madoubt.com 628589…` read as `COM-628589`), the name or its download folder holds another number, or JavDB and JavBus dates differ by over a year (two films under one number; 99 of 11.6k titles when calibrated, so rarely a false alarm) |
| ❌ | Not in the library: the file stays in `/Japan/_inbox` or `/Porn/_inbox`, retried every run. "目标已存在" means a duplicate of a film already organized: delete the extra file |
| ⚠️ | Still in `/Others/待整理`: 30 MB or more but under the size floor, or a same-named file already in `_inbox`. Smaller files are taken for ads and not reported |

Fixing a ❌ or a wrong 🔴, either way:

- **Amane UI:** 指定番号刮削 with the right number. For a ❌, the next run organizes it (a row
  scraped by hand is not re-read from its file name), or press 整理 now. A wrong 🔴 is already in
  the library, so press 整理 yourself to move it.
- **115 app, ❌ only:** rename the file in `_inbox` to the number, then *Run* Media Intake. The old
  row goes away by itself.

A number can also be right while the merged metadata is wrong, because JavDB outranks JavBus and
may hold a different film under that number. Then patch the fields from the right site's snapshot
(`raw` on `GET /api/metadata/{id}`) with `PATCH /api/metadata/{id}`, which also locks them against
later scrapes, and organize again.

**Deleting JAV/Porn:** delete the video or its whole folder in the 115 app. Two muvyo life-event
rules, STRM-only, `/Japan → /data/Japan` and `/Porn → /data/Western`, remove the STRM with the
NFO/images beside it (or the whole local folder) and ask Plex to rescan. Those rules also see
Amane's own organizes (CloudDrive2's moves do raise 115 life events): muvyo then rewrites Amane's
`.strm` at the same path with its own `&pickcode=` form and notifies Plex — harmless, both play.
muvyo resolves a delete event through its 115 file index (`file_info`), and a folder it never
indexed is silently ignored, so a host timer (`muvyo-index.timer`, 09:30) runs muvyo's
incremental full file sync over `/Porn` and `/Japan` after each intake; each new folder costs one
115 lookup (~1.5 s).

A nightly host timer (`orphan-cleanup.timer`, 03:20) tidies those two trees without touching 115:
a film folder whose `.strm` is gone, a `.strm` no Amane row points at, and an Amane row whose
`.strm` is gone. It moves files to `/srv/emby/data/.trash/<date>/` (kept 14 days), and leaves a
tree untouched when it looks off (Amane unreachable, rows < 90 % of the `.strm`s, more than 40
changes in one tree). Such a stop sends a Telegram message and fails the unit. The `_inbox`
leftovers do not count toward the 40 — a big intake leaves hundreds, which used to block the
cleanup for good. Both timers' scripts, units and the stop runbook:
[`bootstrap/media/`](../bootstrap/media/).

Plex mounts subtrees of `/srv/emby/data`: 电影 → `/data/Movie` and 电视节目 → `/data/TV` are
ordinary online-agent libraries (zh-CN, read-only mounts); JAV → `/data/Japan` is a "Plex NFO
Movie" library on Amane's NFOs, and Porn → `/data/Western` (section 7) the same. Cirvel reads the `-mediainfo.json` next to each `.strm`
(media-info path `/{parentFolderPath}/`), so nothing probes the netdisk; where none exists it
analyzes the `.strm` itself and, for the Amane trees (`/data/Japan`, `/data/Western`, the only
writable Plex mounts), writes the json there ("生成媒体信息文件" on, "也写入其他工具…" off). The Plex-side tooling is scoped to those two libraries anyway: kometa's
config whitelists only 电影/电视节目, letterboxd-plex-sync is pinned with
`PLEX_LIBRARY_NAME=电影` (compose), and the local plex-metadata-fixer tool sets
`PLEX_LIBRARIES=电影,电视节目` in its `.env`. Plex and Vyo
share watch state through muvyo's 观看进度同步 (two-way, Emby not in the group).

### Emby's Movie/TV libraries are a frozen image source

Vyo's 电影/电视剧 libraries were imported from Emby, and Vyo does **not** copy imported
artwork — it proxies posters, backdrops and logos live from Emby. So Emby keeps its 电影/
电视剧 libraries as a read-only metadata fallback: realtime monitoring off, no scheduled
library scan, no new items (titles in Vyo are locked, so only images depend on Emby). Rules:

- **Never scan those two libraries in Emby** (nor "scan all libraries"): a scan reprobes new
  `.strm` through 115 and drops missing items, i.e. their artwork.
- Toggling a library's realtime monitor needs an **Emby restart** to drop the old watcher.
- If Vyo rescans while Emby is down, its posters fall back to TMDB — rescan once Emby is up.
- Items added after the freeze are scraped by Vyo itself (Chinese poster when TMDB has one,
  else English).

Around the core: **seerr** takes media requests against **Plex** (switched off Emby
2026-10-22; libraries 电影/电视节目 only, admin user bound to the Plex owner account),
**tautulli** monitors Plex sessions,
**kometa** maintains Plex collections on a daily schedule (outbound-only),
**letterboxd-plex-sync** mirrors Letterboxd watched/ratings/watchlist into Plex weekly
(outbound-only), and the acquisition side is **torrent** (qBittorrent + qui) with
**autobrr** (IRC/RSS filtering + Telegram notify) — deliberately *not* wired to
qBittorrent, notify-only. **muvyo** (admin `muvyo.lkwplus.com`, Vyo player
`vyo.lkwplus.com`) runs with its own Postgres + Redis and sees the shared library at `/data`
(the path Emby and Plex use), writable only for Movie/TV and, for the delete rules, Japan/Western.

## The shared network

`mediacenter-net` (`172.22.0.0/24`) is an **external** bridge created by hand — outside
the daemon's address pools and outside any stack, so no single stack owns (or can recreate)
it. Members that are dial-in *targets* hold fixed IPs, because peers reference them by
address in off-git config:

| IP | Container | Referenced by |
|----|-----------|---------------|
| 172.22.0.4 | emby | cms (`EMBY_HOST_PORT`) |
| 172.22.0.5 | cloud-media-sync | — (kept stable by convention) |
| 172.22.0.6 | seerr | — (kept from the pre-migration setup) |
| 172.22.0.7 | plex | seerr, tautulli, kometa, letterboxd-plex-sync |
| 172.22.0.8 | *(retired — was medialinker)* | — |
| 172.22.0.9 | tautulli | — |
| 172.22.0.10 | *(retired — was moviepilot)* | — |
| 172.22.0.11 | muvyo | Cirvel (Muvyo address in its panel), Emby/Plex webhooks |

**These addresses must not change** — renumbering means editing `/srv/.../` configs on the
host, not just compose files. kometa and letterboxd-plex-sync join the network without a
fixed IP (outbound-only).

If the network is ever lost: `docker network create --subnet 172.22.0.0/24 mediacenter-net`,
then redeploy the member stacks.

## Shared paths

| Path | Written by | Read by |
|------|-----------|---------|
| `/mnt/CloudNAS/115` (FUSE) | clouddrive2 | amane (and cms, mdc — both stopped) |
| `/srv/emby/data/{Movie,TV}` | muvyo (.strm, subtitles, `-mediainfo.json`) | plex (ro), emby |
| `/srv/emby/data/{Japan,Western}` | amane (.strm, nfo/jpg), muvyo (life-event .strm/deletes), plex/Cirvel (`-mediainfo.json`) | plex |
| `/srv/emby/data/Hentai` | cms (.strm), mdc (nfo/jpg) — legacy, frozen, no library reads it | plex (mounted, unused) |
| `/srv/emby/mediainfo` | emby (Strm Assistant `*-mediainfo.json`) — legacy | — |
| `/srv/torrent/qbittorrent/completed` | qBittorrent | muvyo (uploads to 115) |

Consequence: **amane and its intake job only work while clouddrive2's mount is healthy** (muvyo
talks to 115 over its API, not the mount; the stopped cms and mdc needed it too) — after a reboot
or clouddrive2 restart, check the mount first ([operations.md → Reboot](./operations.md#reboot)).

### Surviving a clouddrive2 remount

A clouddrive2 redeploy (e.g. a Renovate bump) destroys and recreates the FUSE mount. Binding the
mountpoint itself into a consumer is a snapshot, so the consumer is left holding a dead mount —
empty dir or `ENOTCONN` — and no clouddrive2 restart fixes it. So amane and amane-intake (like mdc
before them) bind the **parent** `/mnt/CloudNAS` as `/media` with `:rslave`, and clouddrive2's
umount/mount propagates into their namespace (hence the `/media/115/...` library paths). The host
`/` is `shared`, which is what makes propagation work. Any future consumer of the mount wants the
same bind.

The rest of this section and the next are about **mdc, which is stopped**; they matter only if it
is started again.

mdc's fsnotify watches do not re-register after an umount, even once the path is live again; if
its folder monitoring goes quiet after a clouddrive2 redeploy, `docker restart mdc` by hand.

### mdc leaks flaresolverr sessions

Every mdc start creates a fresh FlareSolverr session `mdc_ng_<id>` — a whole Chromium — and never
destroys the previous one; FlareSolverr does not expire sessions on its own. mdc's hourly keepalive
also leaves the live tab parked on the target site, whose JS keeps a renderer busy. The flaresolverr container is capped
(`deploy.resources` in `stacks/mdc/compose.yaml`) so this cannot run away, but if it sits at its
limit, destroy every session except the one in recent logs (`request.get` recreates a missing
session on demand, so restarting the container is also safe):

```sh
ssh fame 'docker logs --since 2h mdc-flaresolverr 2>&1 | grep -o "mdc_ng_[0-9a-f]*" | sort -u'
ssh fame "docker exec mdc-flaresolverr curl -s localhost:8191/v1 -H 'Content-Type: application/json' \
  -d '{\"cmd\":\"sessions.list\"}'"
ssh fame "docker exec mdc-flaresolverr curl -s localhost:8191/v1 -H 'Content-Type: application/json' \
  -d '{\"cmd\":\"sessions.destroy\",\"session\":\"mdc_ng_<old>\"}'"
```

## The 302 path

Every `.strm` holds a direct-link URL to a 302 service, never the media itself. All four live
trees (Movie, TV, Japan, Western) point at muvyo's redirect (`https://muvyo.…/redirect?path=…`).
Only the frozen Hentai tree still holds cms's emby-302 form (`https://cms.…/d/…`), which answers
only while the cms stack runs; taking Hentai over later means regenerating its STRM through
muvyo, not starting cms again. Emby and Vyo
resolve those natively. Stock Plex refuses to play `.strm`, so the plex stack runs
**Cirvel** (a drop-in Plex image with a bundled PMS): it hands the client the link inside
the `.strm` and the client streams it directly — no transcoding load on this host either
way. Akko proxies plex.lkwplus.com straight to fame's published port `20031`; Cirvel's
admin panel lives at `https://plex.lkwplus.com/cirvel/`.
