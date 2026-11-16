# web

[lab.lkwplus.com](https://lab.lkwplus.com): this repository as a page. Astro for the page, one
Worker route for what is live, Cloudflare Workers static assets for the rest.

## Where the content comes from

Nothing is listed here by hand. [`scripts/catalog.ts`](./scripts/catalog.ts) reads the repo into
`src/data/catalog.json` (git-ignored) before every build:

| Drawn | Read from |
|-------|-----------|
| Stacks, their host and tags | `komodo/sync.toml` |
| Containers, images, versions, host ports | `stacks/*/compose.yaml` |
| Addresses and descriptions | the README's service tables |
| The port strips, vacated numbers included | `docs/ports.md` |
| "Stopped" | `renovate.json` (a whole compose file switched off) |

Run without `--json`, the same script is the lint gate's consistency check
(`scripts/validate.sh`, step 6): it fails when those files disagree.

Live, in the visitor's browser: `/api/status` ([`src/worker.ts`](./src/worker.ts)) asks every
address whether it answers (any response below 500), one edge-cached answer a minute; the
latest commits come from GitHub's API.

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
what is live: a dot or a port cell turns green only because something just answered.
