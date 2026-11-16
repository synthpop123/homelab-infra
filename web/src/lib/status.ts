/**
 * The live half of the page: /api/status says which addresses answer,
 * and this paints it onto what the build drew: each address's dot in
 * Services, each stack's cells in Ports, and the count in the readout.
 * Asked again each minute while the page is in view. With no answer
 * (the dev server has no Worker) the page stays as built.
 */
import type { Status } from "@/worker"
import { ago } from "@/lib/time"

const MINUTE = 60_000

function paint({ checkedAt, endpoints }: Status) {
  const stacks = new Map<string, boolean>()
  let answering = 0
  const links = document.querySelectorAll<HTMLAnchorElement>("[data-endpoint]")
  for (const link of links) {
    const probe = endpoints[link.dataset.endpoint ?? ""]
    const dot = link.querySelector<HTMLElement>("[data-dot]")
    const stack = link.closest("[data-row]")?.id
    if (!probe || !dot || !stack) continue
    if (probe.ok) answering++
    stacks.set(stack, (stacks.get(stack) ?? true) && probe.ok)
    dot.dataset.state = probe.ok ? "up" : "down"
    link.title = probe.ok
      ? `Answered ${probe.status} in ${probe.ms} ms`
      : probe.status
        ? `Answered ${probe.status}`
        : "No answer"
  }
  for (const cell of document.querySelectorAll<HTMLElement>("[data-stack]")) {
    const up = stacks.get(cell.dataset.stack ?? "")
    if (up !== undefined) cell.dataset.state = up ? "up" : "down"
  }
  const count = document.querySelector("[data-answering]")
  if (count) count.textContent = String(answering)
  const checked = document.querySelector<HTMLTimeElement>("[data-checked]")
  if (checked) {
    checked.dateTime = checkedAt
    checked.textContent = ago(checkedAt)
  }
}

async function check() {
  if (document.hidden) return
  try {
    const response = await fetch("/api/status", {
      signal: AbortSignal.timeout(15_000),
    })
    if (response.ok) paint((await response.json()) as Status)
  } catch {
    // Unreachable: what is drawn stays.
  }
}

check()
setInterval(check, MINUTE)
document.addEventListener("visibilitychange", check)
