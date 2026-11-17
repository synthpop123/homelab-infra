/**
 * /api/status: whether each service answers, asked from Cloudflare's
 * edge the way a visitor would reach it (through Akko for fame, through
 * arm's Caddy for arm). Everything else on the host is a static asset
 * and never reaches this script (wrangler.jsonc, `run_worker_first`).
 *
 * The list of URLs is the catalog's, so a new stack is probed from the
 * build that first draws it. An answer is any HTTP response below 500:
 * a login page, a 401 or a 404 all mean the service and the proxy in
 * front of it are up; a 502 or a timeout means they are not.
 *
 * One edge-cached answer serves every visitor for a minute, so the page
 * cannot be used to hammer the services.
 */
import { catalog } from "./lib/catalog"

export type Probe = {
  ok: boolean
  status: number | null
  ms: number
  /** The stack the address belongs to, so a page that draws stacks
   *  (the field, the port strip) needs no map of its own. */
  stack: string
}
export type Status = { checkedAt: string; endpoints: Record<string, Probe> }

const TTL = 60
const TIMEOUT = 8_000

const targets = catalog.services
  .filter((service) => !service.stopped)
  .flatMap((service) =>
    service.urls.map((url) => ({ url, stack: service.name })),
  )

async function probe({ url, stack }: (typeof targets)[number]): Promise<Probe> {
  const start = Date.now()
  try {
    const response = await fetch(url, {
      redirect: "manual",
      headers: {
        "user-agent": "homelab-status (+https://lab.lkwplus.com)",
      },
      signal: AbortSignal.timeout(TIMEOUT),
    })
    await response.body?.cancel()
    return {
      ok: response.status < 500,
      status: response.status,
      ms: Date.now() - start,
      stack,
    }
  } catch {
    return { ok: false, status: null, ms: Date.now() - start, stack }
  }
}

export default {
  async fetch(
    request: Request,
    _env: unknown,
    ctx: { waitUntil(promise: Promise<unknown>): void },
  ): Promise<Response> {
    if (new URL(request.url).pathname !== "/api/status")
      return new Response("Not found", { status: 404 })
    if (request.method !== "GET")
      return new Response("Method not allowed", { status: 405 })

    const cache = (caches as unknown as { default: Cache }).default
    const key = new Request(new URL("/api/status", request.url))
    const cached = await cache.match(key)
    if (cached) return cached

    const probes = await Promise.all(targets.map(probe))
    const status: Status = {
      checkedAt: new Date().toISOString(),
      endpoints: Object.fromEntries(
        targets.map(({ url }, i) => [url, probes[i]]),
      ),
    }
    const response = Response.json(status, {
      headers: { "cache-control": `public, max-age=${TTL}` },
    })
    ctx.waitUntil(cache.put(key, response.clone()))
    return response
  },
}
