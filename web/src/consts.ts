import type { Host } from "../scripts/catalog"

export const SITE = {
  title: "homelab",
  description:
    "Self-hosted services on two hosts, declared in git and deployed by Komodo: what runs, where, and whether it answers.",
  locale: "en-US",
} as const

/** The repository this site is built from, and whose commits it lists. */
export const REPO = "synthpop123/homelab-infra"
export const REPO_URL = `https://github.com/${REPO}`
export const HOME = { href: "https://lkwplus.com", label: "lkw123" } as const

/** The site's pages: the sidebar, the overview's index and the palette
 *  all list these. */
export const NAVIGATION = [
  {
    href: "/",
    label: "Overview",
    blurb: "Both hosts at a glance, and what changed last.",
  },
  {
    href: "/services",
    label: "Services",
    blurb: "Every stack as a ledger, each with a page of its own.",
  },
  {
    href: "/status",
    label: "Status",
    blurb: "Which addresses answer, and how fast, asked every minute.",
  },
  {
    href: "/ports",
    label: "Ports",
    blurb: "The registry from 20000 up: who holds which number.",
  },
  {
    href: "/flow",
    label: "Flow",
    blurb: "How a change, an update, a request and a secret travel.",
  },
  {
    href: "/changes",
    label: "Changes",
    blurb: "The commit log, which here is also the deploy log.",
  },
] as const

/** What a host is, which no file in the repo states as data
 *  (docs/server.md, docs/server-arm.md). Its region comes from sync.toml. */
export const HOSTS: Record<Host, { spec: string[]; edge: string }> = {
  fame: { spec: ["Debian 12", "6 vCPU, 24 GiB"], edge: "behind Akko" },
  arm: { spec: ["Ubuntu 24.04", "2 vCPU, 12 GiB"], edge: "behind Caddy" },
}

/** How many commits the overview lists, and how many Changes asks for
 *  (GitHub's most for one request). */
export const CHANGES = { latest: 5, log: 100 } as const
