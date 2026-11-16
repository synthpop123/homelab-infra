import type { Host } from "../scripts/catalog"

export const SITE = {
  title: "homelab",
  description:
    "Self-hosted services on two hosts, declared in git and deployed by Komodo: what runs, where, and whether it answers.",
  locale: "en-US",
} as const

/** The repository this page is built from, and whose commits it lists. */
export const REPO = "synthpop123/homelab-infra"
export const HOME = { href: "https://lkwplus.com", label: "lkw123" } as const

/** The page's sections: the sidebar is their table of contents. */
export const SECTIONS = [
  { id: "services", label: "Services" },
  { id: "ports", label: "Ports" },
  { id: "flow", label: "Flow" },
  { id: "changes", label: "Changes" },
] as const

/** What a host is, which no file in the repo states as data
 *  (docs/server.md, docs/server-arm.md). Its region comes from sync.toml. */
export const HOSTS: Record<Host, { spec: string[]; edge: string }> = {
  fame: { spec: ["Debian 12", "6 vCPU, 24 GiB"], edge: "behind Akko" },
  arm: { spec: ["Ubuntu 24.04", "2 vCPU, 12 GiB"], edge: "behind Caddy" },
}

/** How many commits Changes lists. */
export const CHANGES = 8
