import { defineConfig } from "astro/config"

export default defineConfig({
  site: "https://homelab.lkwplus.com",
  trailingSlash: "never",
  compressHTML: true,
  // No Markdown here; off so the build does not warn about Shiki and CSP.
  markdown: { syntaxHighlight: false },
  // Each page carries a CSP <meta>: scripts run only from this origin or
  // by the hash of an inline one Astro emitted. Styles stay open to
  // inline ones (`style` attributes carry the strips' custom properties).
  // The page fetches its own /api/status and the repository's commits;
  // public/_headers adds what a <meta> cannot say (frame-ancestors).
  security: {
    csp: {
      styleDirective: { resources: ["'self'", "'unsafe-inline'"] },
      directives: [
        "default-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self' https://api.github.com",
        "object-src 'none'",
        "base-uri 'self'",
      ],
    },
  },
})
