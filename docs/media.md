# Media pipeline

Seven stacks cooperate to serve a cloud-storage (115) media library without keeping the
files on disk. This doc is the topology — each stack's compose has the per-service detail.

## Flow

```
115 netdisk
  │ FUSE mount /mnt/CloudNAS/115           (clouddrive2 — host-networked, privileged)
  │
  ├─► cms  syncs netdisk changes ──► writes .strm files ──► /srv/emby/data  (shared library)
  │        also runs the "emby-302" direct-link proxy                │
  ├─► mdc  scrapes metadata      ──► writes nfo/posters ─────────────┤
  │        (flaresolverr sidecar for Cloudflare)                     │
  │                                                                  ▼
  │                                             ┌── emby   reads /srv/emby/data
  │                                             └── plex   reads Movie/TV read-only
  │                                                  ▲
  └─ playback: client follows a 302 to the real     medialinker (nginx+njs) fronts Plex,
     115 download link served by cms's emby-302      302-redirects .strm playback the same
     proxy — no media bytes transit this host        way Emby does natively
```

Around the core: **seerr** takes media requests, **tautulli** monitors Plex sessions,
**kometa** maintains Plex collections on a daily schedule (outbound-only),
**letterboxd-plex-sync** mirrors Letterboxd watched/ratings/watchlist into Plex weekly
(outbound-only), and the acquisition side is **torrent** (qBittorrent + qui) with
**autobrr** (IRC/RSS filtering + Telegram notify) — deliberately *not* wired to
qBittorrent, notify-only.

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
| 172.22.0.7 | plex | medialinker (`plexHost`), tautulli, kometa |
| 172.22.0.8 | medialinker | — |
| 172.22.0.9 | tautulli | — |

**These addresses must not change** — renumbering means editing `/srv/.../` configs on the
host, not just compose files. kometa and letterboxd-plex-sync join the network without a
fixed IP (outbound-only).

If the network is ever lost: `docker network create --subnet 172.22.0.0/24 mediacenter-net`,
then redeploy the member stacks.

## Shared paths

| Path | Written by | Read by |
|------|-----------|---------|
| `/mnt/CloudNAS/115` (FUSE) | clouddrive2 | cms, mdc |
| `/srv/emby/data` | cms (.strm), mdc (nfo/jpg) | emby (rw), plex + medialinker (ro) |

Consequence: **emby, cms, mdc, plex and medialinker only work while clouddrive2's mount is
healthy** — after a reboot or clouddrive2 restart, check the mount first
([operations.md → Reboot](./operations.md#reboot)).

## Why two 302 paths

The `.strm` files hold `https://…/d/…` direct-link URLs served by cms's emby-302 proxy.
Emby resolves those natively. Plex refuses to play `.strm`, so clients connect to
**medialinker** instead of Plex directly; it proxies everything to Plex except playback
requests, whose `.strm` content it reads (same ro mounts) and 302-redirects — giving Plex
the exact path Emby already uses, with no transcoding load on this host either way.
