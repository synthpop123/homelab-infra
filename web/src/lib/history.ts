/**
 * What this browser has seen each address answer: the last few checks,
 * kept in localStorage so a sparkline has something to draw on the next
 * visit. It is one visitor's own record, not the services': nothing is
 * kept on a server, and a check that happened while no page was open is
 * simply not in it.
 */
import type { Status } from "@/worker"

/** A check of one address: when, and in how many ms (null: no answer). */
export type Sample = [at: number, ms: number | null]
export type History = Record<string, Sample[]>

const KEY = "lab:history"
const KEEP = 30

export function history(): History {
  try {
    const stored = JSON.parse(localStorage[KEY] ?? "{}")
    return typeof stored === "object" && stored !== null ? stored : {}
  } catch {
    return {}
  }
}

/** Adds an answer to the record, unless it is the one already at its end. */
export function remember({ checkedAt, endpoints }: Status): History {
  const at = Date.parse(checkedAt)
  const record = history()
  for (const [url, probe] of Object.entries(endpoints)) {
    const samples = record[url] ?? []
    if (samples.at(-1)?.[0] === at) continue
    samples.push([at, probe.ok ? probe.ms : null])
    record[url] = samples.slice(-KEEP)
  }
  // An address the catalog no longer has takes no more room.
  for (const url of Object.keys(record)) if (!endpoints[url]) delete record[url]
  try {
    localStorage[KEY] = JSON.stringify(record)
  } catch {
    // Storage blocked or full: this visit's checks are not kept.
  }
  return record
}
