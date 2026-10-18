# Media pipeline

A cloud-storage (115) media library served without keeping the files on disk. The library
is split by owner:

- **Movie / TV** — **muvyo** owns them end to end: uploads finished downloads to 115,
  organizes them, writes the `.strm` + `-mediainfo.json` trees, and serves the 302 links.
  Watched with **Plex** (via Cirvel) and **Vyo** (Muvyo's own player).
- **JAV / Hentai / Porn** — still the original **cms + mdc + Emby** chain.

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
                        │       cms ─► .strm ──┼─► /srv/emby/data/{JAV,Hentai,Porn}
                        │       mdc ─► nfo/jpg ┘
                        ▼
  plex (Cirvel)  reads Movie/TV ro
  vyo  (muvyo)   reads Movie/TV
  emby           reads JAV/Porn (Movie/TV libraries frozen, see below)

  playback: the client follows a 302 to the real 115 download link — served by muvyo for
  Movie/TV and by cms's emby-302 proxy for the rest; no media bytes transit this host
```

**Getting new Movie/TV in:** download in qBittorrent — the default save path is
`completed/Movie`; pick the `TV` category for series (categories set the path, so automatic
torrent management stays on). Two muvyo directory-monitor rules upload `Movie` → 115 `/Movie`
and `TV` → 115 `/TV` (copy, so qB keeps seeding). Anything offline-downloaded or saved
straight into 115 goes under `/Others/待整理/{Movie,TV}`, which muvyo's 115 life events
organize the same way; edits made in the 115 app under `/Movie`, `/TV` are mirrored into the
STRM tree. The organize target is never the 115 root — muvyo fails with `Cloud path not
found:` there.

Plex mounts four subtrees of `/srv/emby/data` read-only but has only two libraries —
电影 → `/data/Movie` and 电视节目 → `/data/TV`, ordinary online-agent libraries (zh-CN). The
JAV/Hentai mounts are kept for a later NFO-agent library; none exists today. Cirvel reads the
`-mediainfo.json` next to each `.strm` (media-info path `/{parentFolderPath}/`), so nothing
probes the netdisk. The Plex-side tooling is scoped to those two libraries anyway: kometa's
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

Around the core: **seerr** takes media requests, **tautulli** monitors Plex sessions,
**kometa** maintains Plex collections on a daily schedule (outbound-only),
**letterboxd-plex-sync** mirrors Letterboxd watched/ratings/watchlist into Plex weekly
(outbound-only), and the acquisition side is **torrent** (qBittorrent + qui) with
**autobrr** (IRC/RSS filtering + Telegram notify) — deliberately *not* wired to
qBittorrent, notify-only. **muvyo** (admin `muvyo.lkwplus.com`, Vyo player
`vyo.lkwplus.com`) runs with its own Postgres + Redis and sees the shared library at `/data`
(the path Emby and Plex use), writable only for Movie/TV.

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
| 172.22.0.7 | plex | tautulli, kometa, letterboxd-plex-sync |
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
| `/mnt/CloudNAS/115` (FUSE) | clouddrive2 | cms, mdc |
| `/srv/emby/data/{Movie,TV}` | muvyo (.strm, subtitles, `-mediainfo.json`) | plex (ro), emby, cms (ro) |
| `/srv/emby/data/{JAV,Hentai,Porn}` | cms (.strm), mdc (nfo/jpg) | emby (JAV/Porn), muvyo (ro) |
| `/srv/emby/mediainfo` | emby (Strm Assistant `*-mediainfo.json`, JAV/Porn only) | emby, plex/Cirvel |
| `/srv/torrent/qbittorrent/completed` | qBittorrent | muvyo (uploads to 115) |

Consequence: **emby, cms and mdc only work while clouddrive2's mount is
healthy** (muvyo talks to 115 over its API, not the mount) — after a reboot or clouddrive2 restart, check the mount first
([operations.md → Reboot](./operations.md#reboot)).

### Surviving a clouddrive2 remount

A clouddrive2 redeploy (e.g. a Renovate bump) destroys and recreates the FUSE mount. Binding the
mountpoint itself into a consumer is a snapshot, so the consumer is left holding a dead mount —
empty dir or `ENOTCONN` — and no clouddrive2 restart fixes it. So mdc binds the **parent**
`/mnt/CloudNAS` as `/media` with `:rslave`, and clouddrive2's umount/mount propagates into its
namespace (hence the `/media/115/...` paths in its `config.json`). The host `/` is `shared`,
which is what makes propagation work. Any future consumer of the mount wants the same bind.

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

## Why two 302 paths

Every `.strm` holds a direct-link URL to a 302 service, never the media itself: muvyo's
redirect for Movie/TV, cms's emby-302 proxy (`https://…/d/…`) for the rest. Emby and Vyo
resolve those natively. Stock Plex refuses to play `.strm`, so the plex stack runs
**Cirvel** (a drop-in Plex image with a bundled PMS): it hands the client the link inside
the `.strm` and the client streams it directly — no transcoding load on this host either
way. Akko proxies plex.lkwplus.com straight to fame's published port `20031`; Cirvel's
admin panel lives at `https://plex.lkwplus.com/cirvel/`.
