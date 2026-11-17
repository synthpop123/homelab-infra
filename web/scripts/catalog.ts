/**
 * The repository read as one catalog: every stack with its host, URLs,
 * ports and images, and each host's port registry. Nothing here is typed
 * in by hand: it comes from komodo/sync.toml, stacks/<name>/compose.yaml,
 * docs/ports.md, the README's service tables and renovate.json.
 *
 * Adding a service touches four of those files, so reading them together
 * is also what checks that they agree. Two callers:
 *
 *   bun web/scripts/catalog.ts                 the lint gate (validate.sh):
 *                                              lists every disagreement,
 *                                              exits 1 if there is one
 *   bun web/scripts/catalog.ts --json <path>   the site's build: writes
 *                                              the catalog it draws
 */
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"

export type Host = "fame" | "arm"

export type Container = {
  name: string
  image: string | null
  version: string | null
  /** A database, cache or helper the stack carries, not what it is. */
  bundled: boolean
  /** The containers this one waits for (`depends_on`), by container name. */
  needs: string[]
  /** Where its data lives on the host: the bind mounts under /srv. */
  mounts: string[]
}

export type Service = {
  name: string
  host: Host
  tags: string[]
  description: string
  urls: string[]
  /** Host ports from the registry (20000–20999), ascending. */
  ports: number[]
  containers: Container[]
  /** The version of the image the stack is named for. */
  version: string | null
  /** Defined but not running: Renovate is switched off for its file. */
  stopped: boolean
}

export type PortCell = {
  port: number
  /** The stack publishing it; null where the number was vacated. */
  stack: string | null
  label: string | null
}

export type Catalog = {
  hosts: Record<
    Host,
    {
      server: string
      region: string
      ports: PortCell[]
      /** The number the next published service takes. */
      next: number
    }
  >
  services: Service[]
  commit: string | null
  builtAt: string
}

type Dict = Record<string, unknown>

const ROOT = resolve(import.meta.dir, "../..")
const SERVERS: Record<Host, string> = { fame: "Famesystems", arm: "Oracle-Arm" }
const HOSTS = Object.keys(SERVERS) as Host[]
const REGISTRY = { first: 20000, last: 20999 }
/** Images a stack bundles rather than is: never the one it is named for. */
const BUNDLED =
  /postgres|pgvector|redis|valkey|elasticsearch|meilisearch|chrome|flaresolverr/

const read = (path: string) => readFileSync(join(ROOT, path), "utf8")
const dict = (value: unknown): Dict =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Dict)
    : {}
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])
const strings = (value: unknown) =>
  list(value).filter((item): item is string => typeof item === "string")

/** `ghcr.io/org/name:1.2.3@sha256:…` → `1.2.3`. */
const imageTag = (image: string) =>
  image.replace(/@.*$/, "").match(/:([^/:]+)$/)?.[1] ?? null

/** A tag as a version to read: `v1.2.3` → `1.2.3`, silo's
 *  `RELEASE.2026-10-26T00-00-00Z` → `2026-10-26`. */
const version = (tag: string) =>
  tag.replace(/^v(?=\d)/, "").replace(/^RELEASE\.([\d-]+)T.*$/, "$1")

/** A compose `ports` entry as its host side: `127.0.0.1:20012:3000/tcp`. */
function published(entry: unknown): { ip: string | null; port: number } | null {
  if (typeof entry === "object" && entry !== null) {
    const { host_ip, published } = entry as Dict
    return published
      ? { ip: typeof host_ip === "string" ? host_ip : null, port: +published }
      : null
  }
  const parts = String(entry)
    .replace(/\/\w+$/, "")
    .split(":")
  if (parts.length < 2) return null
  return { ip: parts.length > 2 ? parts[0] : null, port: +parts.at(-2)! }
}

/** The README's two service tables: a row per stack under its host. */
function readmeRows() {
  const rows = new Map<
    string,
    { host: Host; urls: string[]; ports: number[]; description: string }
  >()
  let host: Host | null = null
  for (const line of read("README.md").split("\n")) {
    const heading = line.match(/^#{2,3} (.+)$/)
    if (heading) host = HOSTS.find((name) => name === heading[1]) ?? null
    const row = line.match(/^\| \[([\w-]+)\]\(\.\/stacks\/\1\) \|(.*)\|$/)
    if (!row || !host) continue
    const [urls = "", ports = "", description = ""] = row[2]
      .split(" |")
      .map((cell) => cell.trim())
    rows.set(row[1], {
      host,
      urls: [...urls.matchAll(/\]\((https:\/\/[^)]+)\)/g)].map((m) => m[1]),
      ports: [...ports.matchAll(/\b\d{5}\b/g)].map((m) => +m[0]),
      description: description.replace(/\*\*|`/g, ""),
    })
  }
  return rows
}

/** docs/ports.md: each host's allocation table and its "Next free". */
function registry() {
  const tables: Record<Host, { labels: Map<number, string>; next: number }> = {
    fame: { labels: new Map(), next: 0 },
    arm: { labels: new Map(), next: 0 },
  }
  let host: Host | null = null
  for (const line of read("docs/ports.md").split("\n")) {
    const heading = line.match(/^## (.+)$/)
    if (heading)
      host =
        heading[1] === "Allocations"
          ? "fame"
          : heading[1] === "Allocations (arm)"
            ? "arm"
            : null
    if (!host) continue
    const row = line.match(/^\|\s*(\d{5})\s*\|\s*(.+?)\s*\|/)
    if (row) tables[host].labels.set(+row[1], row[2])
    const next = line.match(/^\*\*Next free[^`]*`(\d{5})`/)
    if (next) tables[host].next = +next[1]
  }
  return tables
}

/** Stacks Renovate leaves alone as a whole file: the stopped ones. */
function stoppedStacks() {
  const rules = list(dict(JSON.parse(read("renovate.json"))).packageRules)
  return new Set(
    rules
      .map(dict)
      .filter((rule) => rule.enabled === false && !rule.matchPackageNames)
      .flatMap((rule) => strings(rule.matchFileNames))
      .map((file) => file.match(/^stacks\/([\w-]+)\/compose\.yaml$/)?.[1])
      .filter((name) => name !== undefined),
  )
}

/** The commit being built: what the builder says, else what git says. A
 *  build environment may set neither a usable variable nor a readable
 *  checkout, so each source is only a candidate. */
function commit() {
  const git = (...args: string[]) =>
    Bun.spawnSync(["git", "-c", "safe.directory=*", "-C", ROOT, ...args])
      .stdout.toString()
      .trim()
  const candidates = [
    process.env.WORKERS_CI_COMMIT_SHA,
    process.env.GITHUB_SHA,
    git("rev-parse", "HEAD"),
  ]
  return candidates.find((sha) => sha && /^[0-9a-f]{40}$/.test(sha)) ?? null
}

export function load(): { catalog: Catalog; problems: string[] } {
  const problems: string[] = []
  const sync = dict(Bun.TOML.parse(read("komodo/sync.toml")))
  const defined = new Map(
    list(sync.stack).map((stack) => [String(dict(stack).name), dict(stack)]),
  )
  const regions = new Map(
    list(sync.server).map((server) => [
      String(dict(server).name),
      String(dict(dict(server).config).region ?? ""),
    ]),
  )
  const folders = readdirSync(join(ROOT, "stacks")).filter(
    (name) => Bun.file(join(ROOT, "stacks", name, "compose.yaml")).size,
  )
  const rows = readmeRows()
  const tables = registry()
  const stopped = stoppedStacks()
  const owners: Record<Host, Map<number, string>> = {
    fame: new Map(),
    arm: new Map(),
  }

  for (const name of defined.keys())
    if (!folders.includes(name))
      problems.push(
        `${name}: in sync.toml, but stacks/${name}/ has no compose.yaml`,
      )
  for (const name of rows.keys())
    if (!folders.includes(name))
      problems.push(`${name}: a README row for a stack that does not exist`)

  const services = folders.flatMap((name): Service[] => {
    const fail = (message: string) => problems.push(`${name}: ${message}`)
    const stack = defined.get(name)
    if (!stack) {
      fail("no [[stack]] block in komodo/sync.toml")
      return []
    }
    const config = dict(stack.config)
    const tags = strings(stack.tags)
    const host = HOSTS.find((key) => SERVERS[key] === config.server)
    if (!host) {
      fail(`unknown server ${config.server}`)
      return []
    }

    const text = read(`stacks/${name}/compose.yaml`)
    const compose = dict(Bun.YAML.parse(text))
    const entries = Object.entries(dict(compose.services)).map(
      ([key, value]) => [key, dict(value)] as const,
    )

    // The stack's definition.
    if (stack.deploy !== false)
      fail("deploy must be false (the procedure deploys)")
    if (config.linked_repo !== "homelab-infra")
      fail("linked_repo must be homelab-infra")
    if (config.run_directory !== `stacks/${name}`)
      fail(`run_directory must be stacks/${name}`)
    if (strings(config.file_paths).join() !== "compose.yaml")
      fail('file_paths must be ["compose.yaml"]')
    if (!tags.includes(`host-${host}`)) fail(`missing the host-${host} tag`)
    const builds = entries.some(([, service]) => service.build)
    if (builds !== tags.includes("source-build"))
      fail("the source-build tag must match whether a service has build:")
    if (builds !== strings(config.extra_args).includes("--build"))
      fail('extra_args must be ["--build"] exactly when a service has build:')

    // Secrets: every ${VAR} the compose reads is one Komodo writes.
    const env = new Set(
      [...String(config.environment ?? "").matchAll(/^([A-Za-z0-9_]+)=/gm)].map(
        (m) => m[1],
      ),
    )
    const refs = new Set(
      [
        ...text.replace(/^\s*#.*$/gm, "").matchAll(/\$\{([A-Za-z0-9_]+)\}/g),
      ].map((m) => m[1]),
    )
    for (const ref of refs)
      if (!env.has(ref))
        fail(`\${${ref}} has no mapping in the stack's environment`)
    if (!entries.some(([, service]) => service.env_file))
      for (const key of env)
        if (!refs.has(key))
          fail(`environment sets ${key}, which the compose never reads`)

    // Networks and volumes.
    const networks = dict(compose.networks)
    for (const [key, network] of Object.entries(networks))
      if (!dict(network).name) fail(`network ${key} needs an explicit name`)
    const onDefault = entries.some(
      ([, service]) => !service.network_mode && !service.networks,
    )
    if (onDefault && dict(networks.default).name !== name)
      fail(`the default network must be named ${name}`)
    if (compose.volumes) fail("named volumes: bind /srv instead")
    for (const [key, service] of entries)
      for (const volume of strings(service.volumes))
        if (!volume.startsWith("/") && !volume.endsWith(":ro"))
          fail(`${key}: bind ${volume} is relative and writable`)

    // Ports.
    const ports: number[] = []
    for (const [key, service] of entries)
      for (const entry of list(service.ports)) {
        const bind = published(entry)
        if (!bind) continue
        if (host === "arm" && bind.ip !== "127.0.0.1")
          fail(`${key}: port ${bind.port} must bind 127.0.0.1 on arm`)
        if (bind.port < REGISTRY.first || bind.port > REGISTRY.last) continue
        const owner = owners[host].get(bind.port)
        if (owner) fail(`port ${bind.port} is already published by ${owner}`)
        owners[host].set(bind.port, name)
        ports.push(bind.port)
        if (!tables[host].labels.has(bind.port))
          fail(`port ${bind.port} is not in docs/ports.md (${host})`)
      }
    ports.sort((a, b) => a - b)

    // The README row.
    const row = rows.get(name)
    if (!row) fail("no row in the README's service tables")
    else {
      if (row.host !== host) fail(`its README row belongs in the ${host} table`)
      if (row.ports.toSorted((a, b) => a - b).join() !== ports.join())
        fail(
          `the README lists ports ${row.ports.join("/") || "none"}, the compose publishes ${ports.join("/") || "none"}`,
        )
    }

    const names = new Map(
      entries.map(([key, service]) => [
        key,
        String(service.container_name ?? key),
      ]),
    )
    const containers = entries.map(([key, service]): Container => {
      const image = typeof service.image === "string" ? service.image : null
      const pin = Object.values(dict(dict(service.build).args))[0]
      const tag = image ? imageTag(image) : pin == null ? null : String(pin)
      // `depends_on` is a list of service keys, or a map of them to conditions.
      const waits = Array.isArray(service.depends_on)
        ? strings(service.depends_on)
        : Object.keys(dict(service.depends_on))
      const sources = list(service.volumes).map((volume) =>
        typeof volume === "string"
          ? volume.split(":")[0]
          : String(dict(volume).source ?? ""),
      )
      return {
        name: names.get(key) ?? key,
        image: image?.replace(/@.*$/, "") ?? null,
        version: tag ? version(tag) : null,
        bundled: BUNDLED.test(image ?? ""),
        needs: waits.flatMap((need) => names.get(need) ?? []),
        mounts: [
          ...new Set(sources.filter((path) => path.startsWith("/srv/"))),
        ],
      }
    })
    const main =
      containers.find((container) => !container.bundled) ?? containers[0]

    return [
      {
        name,
        host,
        tags: tags.filter((tag) => !tag.startsWith("host-") && tag !== "app"),
        description: row?.description ?? "",
        urls: row?.urls ?? [],
        ports,
        containers,
        version: main?.version ?? null,
        stopped: stopped.has(name),
      },
    ]
  })

  const hosts = Object.fromEntries(
    HOSTS.map((host) => {
      const { labels, next } = tables[host]
      const top = Math.max(REGISTRY.first - 1, ...owners[host].keys())
      for (const port of labels.keys())
        if (!owners[host].has(port))
          problems.push(
            `docs/ports.md (${host}): ${port} is listed, but no stack publishes it`,
          )
      if (next !== top + 1)
        problems.push(
          `docs/ports.md (${host}): Next free is ${next}, expected ${top + 1}`,
        )
      const ports = Array.from(
        { length: top - REGISTRY.first + 1 },
        (_, i): PortCell => {
          const port = REGISTRY.first + i
          const stack = owners[host].get(port) ?? null
          return {
            port,
            stack,
            label: stack ? (labels.get(port) ?? stack) : null,
          }
        },
      )
      return [
        host,
        {
          server: SERVERS[host],
          region: regions.get(SERVERS[host]) ?? "",
          ports,
          next: top + 1,
        },
      ]
    }),
  ) as Catalog["hosts"]

  const order = (service: Service) =>
    [
      HOSTS.indexOf(service.host),
      service.ports[0] ?? REGISTRY.last + 1,
    ] as const
  services.sort(
    (a, b) => order(a)[0] - order(b)[0] || order(a)[1] - order(b)[1],
  )

  return {
    catalog: {
      hosts,
      services,
      commit: commit(),
      builtAt: new Date().toISOString(),
    },
    problems,
  }
}

if (import.meta.main) {
  const { catalog, problems } = load()
  for (const problem of problems) console.error(`FAIL: ${problem}`)
  const out = process.argv.indexOf("--json")
  if (out > 0) {
    const path = resolve(process.argv[out + 1])
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(path, `${JSON.stringify(catalog, null, 2)}\n`)
    console.log(
      `catalog: ${catalog.services.length} stacks at ${catalog.commit?.slice(0, 7) ?? "no commit"} → ${path}`,
    )
  } else if (problems.length === 0) {
    console.log(
      `ok: ${catalog.services.length} stacks agree across sync.toml, compose, ports.md and the README`,
    )
  }
  if (problems.length > 0) process.exit(1)
}
