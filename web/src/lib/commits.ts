/**
 * The repository's commits, read from GitHub by the visitor's browser so
 * the log is current without a rebuild. One request serves the overview
 * and Changes alike: it is kept for the session for five minutes, which
 * also keeps a visitor well inside GitHub's unauthenticated allowance.
 */
import { CHANGES, REPO } from "@/consts"
import { ago } from "@/lib/time"

export type Commit = {
  sha: string
  url: string
  date: string
  /** The subject line, without its type prefix or pull request number. */
  subject: string
  /** `feat`, `fix`, `chore`, …: the conventional-commit type, if it has one. */
  type: string | null
  scope: string | null
  /** Opened by Renovate rather than written by hand. */
  bot: boolean
}

const ENDPOINT = `https://api.github.com/repos/${REPO}/commits?per_page=${CHANGES.log}`
export const LOG = `https://github.com/${REPO}/commits/main`
const KEY = "lab:commits"
const FRESH = 5 * 60_000

/** GitHub's commit list, down to what a row shows; anything that is not
 *  the expected shape is left out rather than drawn. */
const decode = (body: unknown): Commit[] =>
  (Array.isArray(body) ? body : []).flatMap((entry) => {
    const { sha, html_url, commit, author } = entry ?? {}
    const date = commit?.committer?.date
    const message = commit?.message
    if (![sha, html_url, date, message].every((v) => typeof v === "string"))
      return []
    const line = (message as string).split("\n")[0].replace(/ \(#\d+\)$/, "")
    const parts = line.match(/^(\w+)(?:\(([^)]+)\))?!?:\s*(.+)$/)
    const login = typeof author?.login === "string" ? author.login : ""
    return [
      {
        sha,
        url: html_url,
        date,
        subject: parts?.[3] ?? line,
        type: parts?.[1] ?? null,
        scope: parts?.[2] ?? null,
        bot: login.startsWith("renovate") || parts?.[2] === "deps",
      },
    ]
  })

export async function commits(): Promise<Commit[]> {
  try {
    const kept = JSON.parse(sessionStorage[KEY] ?? "null")
    if (kept && Date.now() - kept.at < FRESH) return kept.commits
  } catch {
    // Nothing kept, or storage blocked: ask.
  }
  const response = await fetch(ENDPOINT, {
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new Error(`GitHub answered ${response.status}`)
  const list = decode(await response.json())
  if (list.length === 0) throw new Error("no commits")
  try {
    sessionStorage[KEY] = JSON.stringify({ at: Date.now(), commits: list })
  } catch {
    // Storage blocked: the next page asks again.
  }
  return list
}

/** A commit as a row: when, what (its type and scope set small before
 *  the subject), and its hash. */
export function commitRow(
  { sha, url, date, subject, type, scope }: Commit,
  when: (date: string) => string = ago,
): HTMLLIElement {
  const item = document.createElement("li")
  if (type) item.dataset.type = type
  const time = document.createElement("time")
  time.dateTime = date
  time.textContent = when(date)
  const what = document.createElement("span")
  if (type) {
    const tag = document.createElement("i")
    tag.textContent = scope ? `${type} · ${scope}` : type
    what.append(tag)
  }
  const link = document.createElement("a")
  link.href = url
  link.textContent = subject
  what.append(link)
  const code = document.createElement("code")
  code.textContent = sha.slice(0, 7)
  item.append(time, what, code)
  return item
}

/** What a list shows when GitHub did not answer. */
export function unavailable(): HTMLParagraphElement {
  const note = document.createElement("p")
  const link = document.createElement("a")
  link.href = LOG
  link.textContent = "commit log"
  note.append("GitHub did not answer. The ", link, " has them.")
  return note
}
