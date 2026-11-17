# web

[lab.lkwplus.com](https://lab.lkwplus.com): this repository as a site. Astro for the pages, one
Worker route for what is live, Cloudflare Workers static assets for the rest.

## Pages

| Page | What it draws |
|------|---------------|
| `/` | Both hosts as a field of marks (a cluster to a stack, a square to a container), the latest commits, and a contents list |
| `/services` | The ledger of every stack, narrowed by a typed filter, host, tag or state (the choice is kept in the address) |
| `/services/<name>` | A stack's own page: its addresses with what they answered, its containers and what they wait for, ports, and the four files that record it |
| `/status` | Every address with its response time, status and this browser's record of its last checks; sortable |
| `/ports` | The registry as a strip per host, then as a ledger with vacated numbers kept in place |
| `/flow` | Deploy, Update, Request and Secret as four lanes of stops to step or play through |
| `/changes` | The commit log: four weeks of days as columns, then commits under their day, narrowed by type |

`⌘K` (or the sidebar's search) opens a palette of every page and stack. Pages change by a
cross-document view transition (CSS only, no client router): the sidebar holds still and a
stack's name travels from its ledger row to its page's title.

## Where the content comes from

Nothing is listed here by hand. [`scripts/catalog.ts`](./scripts/catalog.ts) reads the repo into
`src/data/catalog.json` (git-ignored) before every build:

| Drawn | Read from |
|-------|-----------|
| Stacks, their host and tags | `komodo/sync.toml` |
| Containers, images, versions, host ports, `depends_on`, `/srv` binds | `stacks/*/compose.yaml` |
| Addresses and descriptions | the README's service tables |
| The port strips, vacated numbers included | `docs/ports.md` |
| "Stopped" | `renovate.json` (a whole compose file switched off) |

Run without `--json`, the same script is the lint gate's consistency check
(`scripts/validate.sh`, step 6): it fails when those files disagree.

Live, in the visitor's browser: `/api/status` ([`src/worker.ts`](./src/worker.ts)) asks every
address whether it answers (any response below 500), one edge-cached answer a minute.
[`src/lib/status.ts`](./src/lib/status.ts) runs on every page and paints that answer onto
whatever the build drew (`data-endpoint`, `data-stack`, `data-live`); the last answer is kept
for the session so a page reached by a link is not grey, and each one is added to a history in
the visitor's own `localStorage` (thirty checks an address), which is all the sparklines draw
from: nothing is stored on a server. The commits come from GitHub's API, one request kept for
five minutes.

## Commands

```bash
bun install
bun run dev        # astro dev (no Worker: the dots stay grey)
bun run build      # catalog + astro check + astro build -> dist/
bun run preview    # wrangler dev on :8787, assets and Worker as deployed
bun run deploy     # build, then wrangler deploy
bun run format     # Biome; bun run lint for the .ts
```

## Deploy

Cloudflare Workers Builds, connected to this repository with **root directory `web`**, build
command `bun run build`, deploy command `npx wrangler deploy`: every push to `main` rebuilds,
so a merged Renovate bump shows its new version within a minute. `.bun-version` and
`.node-version` pin the toolchain there and in CI (`.github/workflows/web.yml`).

## Design

The design system is [lkwplus.com](https://lkwplus.com)'s, tokens and fonts copied from it
(`src/styles/`): Radix Olive and Grass read through `--neutral-*` and `--accent*`, every line a
hairline, Inter and Geist Mono, four of its five type sizes, no shadows. The accent is kept for
what is live: a dot, a port cell or a cluster turns green only because something just answered,
and the hairline on `/status` fills because the minute is passing. Shared pieces live in
`src/styles/readout.css` (the readout of figures, chips, dots, sparklines) and
`src/styles/commits.css`.
