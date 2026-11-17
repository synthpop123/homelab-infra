/**
 * What an answer says about each address, written onto the rows that
 * list addresses (a stack's own page, /status):
 *
 *   <li data-address="<url>">      gets data-state, data-ms and --share
 *     [data-code]                   the HTTP status, or `none`
 *     [data-time]                   the response time in ms
 *     [data-spark]                  this browser's last checks, as a line
 *
 * --share is the row's time against the slowest answer under the same
 * root, on a square-root scale: one slow address would otherwise flatten
 * every other bar to a sliver.
 */
import { history } from "@/lib/history"
import { spark } from "@/lib/spark"
import type { Status } from "@/worker"

export function paintAddresses(root: ParentNode, status: Status) {
  const record = history()
  const rows = [...root.querySelectorAll<HTMLElement>("[data-address]")]
  const probes = rows.map((row) => status.endpoints[row.dataset.address ?? ""])
  const slowest = Math.max(
    1,
    ...probes.map((probe) => (probe?.ok ? probe.ms : 0)),
  )
  rows.forEach((row, i) => {
    const probe = probes[i]
    if (!probe) return
    const set = (part: string, text: string) => {
      const node = row.querySelector(part)
      if (node) node.textContent = text
    }
    row.dataset.state = probe.ok ? "up" : "down"
    row.dataset.ms = String(probe.ok ? probe.ms : -1)
    row.style.setProperty(
      "--share",
      probe.ok ? Math.sqrt(probe.ms / slowest).toFixed(3) : "0",
    )
    set("[data-code]", probe.status ? String(probe.status) : "none")
    set("[data-time]", probe.ok ? String(probe.ms) : "–")
    row
      .querySelector("[data-spark]")
      ?.replaceChildren(spark(record[row.dataset.address ?? ""] ?? []))
  })
}
