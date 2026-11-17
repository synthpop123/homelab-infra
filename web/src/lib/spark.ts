/**
 * A sparkline of one address's answers: the response time as a line, a
 * check that got no answer as a break in it with a tick on the baseline.
 * Drawn to its own scale (the slowest answer it holds touches the top),
 * so it shows the shape of an address's day, not how it ranks.
 */
import type { Sample } from "@/lib/history"

const NS = "http://www.w3.org/2000/svg"
const WIDTH = 64
const HEIGHT = 16
const PAD = 1.5

const el = (name: string, attrs: Record<string, string | number>) => {
  const node = document.createElementNS(NS, name)
  for (const [key, value] of Object.entries(attrs))
    node.setAttribute(key, String(value))
  return node
}

export function spark(samples: Sample[]): SVGElement {
  const svg = el("svg", {
    viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    width: WIDTH,
    height: HEIGHT,
    "aria-hidden": "true",
  })
  if (samples.length < 2) return svg
  const top = Math.max(...samples.map(([, ms]) => ms ?? 0), 1)
  const step = (WIDTH - 2 * PAD) / (samples.length - 1)
  const x = (i: number) => +(PAD + i * step).toFixed(2)
  const y = (ms: number) =>
    +(HEIGHT - PAD - (ms / top) * (HEIGHT - 2 * PAD)).toFixed(2)

  // One path, lifted wherever a check went unanswered.
  let d = ""
  let pen = false
  samples.forEach(([, ms], i) => {
    if (ms === null) {
      pen = false
      svg.append(
        el("line", {
          x1: x(i),
          x2: x(i),
          y1: HEIGHT - PAD - 3,
          y2: HEIGHT - PAD,
          "data-miss": "",
        }),
      )
      return
    }
    d += `${pen ? "L" : "M"}${x(i)} ${y(ms)}`
    pen = true
  })
  if (d) svg.prepend(el("path", { d }))
  const [, last] = samples.at(-1)!
  if (last !== null)
    svg.append(el("circle", { cx: x(samples.length - 1), cy: y(last), r: 1.5 }))
  return svg
}
