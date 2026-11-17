/**
 * The live half of the site: /api/status says which addresses answer,
 * and this paints it onto what the build drew, on whichever page is open:
 *
 *   [data-endpoint="<url>"]   an address: its dot, and what it answered
 *   [data-stack="<name>"]     a stack's mark (a row, a port cell, a
 *                             cluster in the field): up when every
 *                             address of the stack answers
 *   [data-live="<figure>"]    a figure in a readout or the sidebar
 *
 * Asked again each minute while the page is in view. The last answer is
 * kept for the session, so a page reached by a link is painted at once
 * instead of going grey and waiting; each new one is added to this
 * browser's own history (src/lib/history.ts) and handed to the pages
 * that draw more than dots (`onStatus`). With no
 * answer (the dev server has no Worker) the page stays as built.
 */

import { remember } from "@/lib/history"
import { ago } from "@/lib/time"
import type { Probe, Status } from "@/worker"

const MINUTE = 60_000
const CACHE = "lab:status"

let latest: Status | null = null

/** The answer on screen, for a script that starts after it arrived. */
export const current = () => latest

/** What an address answered, as a sentence for its title. */
export const answer = (probe: Probe) =>
  probe.ok
    ? `Answered ${probe.status} in ${probe.ms} ms`
    : probe.status
      ? `Answered ${probe.status}`
      : "No answer"

export function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = values.toSorted((a, b) => a - b)
  const mid = sorted.length >> 1
  return sorted.length % 2
    ? sorted[mid]
    : Math.round((sorted[mid - 1] + sorted[mid]) / 2)
}

function set(figure: string, text: string) {
  for (const node of document.querySelectorAll(`[data-live="${figure}"]`))
    node.textContent = text
}

function paint(status: Status) {
  const probes = Object.values(status.endpoints)
  const stacks = new Map<string, boolean>()
  for (const probe of probes)
    if (probe.stack)
      stacks.set(probe.stack, (stacks.get(probe.stack) ?? true) && probe.ok)

  for (const node of document.querySelectorAll<HTMLElement>(
    "[data-endpoint]",
  )) {
    const probe = status.endpoints[node.dataset.endpoint ?? ""]
    if (!probe) continue
    const dot = node.matches("[data-dot]")
      ? node
      : node.querySelector<HTMLElement>("[data-dot]")
    if (dot) dot.dataset.state = probe.ok ? "up" : "down"
    node.title = answer(probe)
  }
  for (const node of document.querySelectorAll<HTMLElement>("[data-stack]")) {
    const up = stacks.get(node.dataset.stack ?? "")
    if (up !== undefined) node.dataset.state = up ? "up" : "down"
  }

  const up = probes.filter((probe) => probe.ok)
  const down = probes.length - up.length
  const middle = median(up.map((probe) => probe.ms))
  set("answering", String(up.length))
  set("total", String(probes.length))
  set("down", String(down))
  set("median", middle === null ? "–" : String(middle))
  for (const node of document.querySelectorAll<HTMLElement>("[data-pulse]"))
    node.dataset.pulse = down ? "down" : "up"
  stamp(status)
}

/** How long ago the answer was taken: repainted as it ages. */
function stamp({ checkedAt }: Status) {
  for (const time of document.querySelectorAll<HTMLTimeElement>(
    '[data-live="checked"]',
  )) {
    time.dateTime = checkedAt
    time.textContent = ago(checkedAt)
  }
}

function show(status: Status, fresh: boolean) {
  latest = status
  paint(status)
  if (fresh) remember(status)
  document.dispatchEvent(new CustomEvent("lab:status", { detail: { status } }))
}

/** A stored answer, whatever its age: an old one still says more than
 *  grey dots while the new one is on its way. */
function stored(): Status | null {
  try {
    const status = JSON.parse(sessionStorage[CACHE] ?? "null") as Status | null
    return status?.endpoints ? status : null
  } catch {
    return null
  }
}

async function check() {
  if (document.hidden) return
  // The edge keeps one answer a minute: asking sooner returns the same.
  if (latest && Date.now() - Date.parse(latest.checkedAt) < MINUTE) return
  try {
    const response = await fetch("/api/status", {
      signal: AbortSignal.timeout(15_000),
    })
    if (!response.ok) return
    const status = (await response.json()) as Status
    if (status.checkedAt === latest?.checkedAt) return
    try {
      sessionStorage[CACHE] = JSON.stringify(status)
    } catch {
      // Storage blocked: every page asks for itself.
    }
    show(status, true)
  } catch {
    // Unreachable: what is drawn stays.
  }
}

const kept = stored()
if (kept) show(kept, false)
check()
setInterval(check, MINUTE / 4)
setInterval(() => latest && stamp(latest), MINUTE / 2)
document.addEventListener("visibilitychange", check)

export type StatusEvent = CustomEvent<{ status: Status }>

/** Runs `paint` with every answer, starting with the one already on
 *  screen if this script started after it arrived. */
export function onStatus(paint: (status: Status) => void) {
  document.addEventListener("lab:status", (event) =>
    paint((event as StatusEvent).detail.status),
  )
  if (latest) paint(latest)
}
