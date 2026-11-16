const monthDay = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
})

/** `just now`, `4m ago`, `3h ago`, `2d ago`, then the day itself. */
export function ago(at: string | number, now = Date.now()): string {
  const then = typeof at === "string" ? Date.parse(at) : at
  const minutes = Math.floor((now - then) / 60_000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return monthDay.format(then)
}
