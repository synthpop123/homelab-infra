# DeepSeek Harness (dsh) Web UI — installed from upstream's published npm package.
# Upstream publishes no container image, but since 0.1.0-rc.5 the whole `@deepseek-ai/dsh-*`
# family is public on npm, and the CLI package carries `bin: dsh` plus the Web UI assets (via
# its @deepseek-ai/dsh-web-app dependency). Installing the tarball replaces the old
# clone-and-`pnpm run build` image: no monorepo checkout, no build toolchain, ~400MB instead
# of 2.53GB. Pure JS — the package declares no cpu/os and pulls no gyp addon — so it installs
# on this aarch64 host unchanged.
#
# The version is NOT set here: it lives in compose.yaml's `build.args` as DSH_VERSION. That is
# deliberate and load-bearing. `file_paths` in komodo/sync.toml is compose-only (Komodo parses
# every entry as a ComposeFile, so listing this Dockerfile breaks the stack), which means a
# Dockerfile-only edit syncs but is never selected by BatchDeployStackIfChanged. Keeping the
# pin in compose.yaml makes a version bump a compose change, so Renovate's PR redeploys itself
# on merge and `extra_args = "--build"` rebuilds. Never add a default value below — an unset
# arg would silently resolve `@deepseek-ai/dsh@` to the `latest` dist-tag, which for a
# developer preview that warns of breaking changes is exactly the floating ref this pin exists
# to prevent. The guard on the install layer fails the build instead.
#
# Bumping the base image is still a Dockerfile-only change: Renovate will offer node major
# updates here, but merging one does NOT redeploy — deploy that by hand (a Node major is worth
# the manual step anyway; upstream engines are `^22.19.0 || >=24.0.0`).
#
# dsh web binds 127.0.0.1 only — packages/host/webserver's Config schema accepts just
# '127.0.0.1' | '0.0.0.0', and the CLI rejects 0.0.0.0 outright ("it would expose remote code
# execution to the network"). A bridge publish therefore cannot reach the process, so
# compose.yaml uses host networking on the arm loopback port 20003 for the host Caddy.
FROM node:24-bookworm-slim

ARG DSH_VERSION
LABEL org.opencontainers.image.source="https://github.com/deepseek-ai/deepseek-harness"
LABEL org.opencontainers.image.version="${DSH_VERSION}"

# git and bash are runtime deps of the agent's own tooling (tool-bash, workspace git ops),
# not of the install.
RUN apt-get update \
  && apt-get install -y --no-install-recommends bash ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

# Fail loudly rather than installing the `latest` dist-tag (see the header note).
RUN test -n "${DSH_VERSION}" \
    || { echo "DSH_VERSION build arg is required (set it in compose.yaml)" >&2; exit 1; } \
  && npm install -g --omit=dev "@deepseek-ai/dsh@${DSH_VERSION}" \
  && npm cache clean --force

# Unhide the Settings surfaces for a non-loopback browser. The gate is client-side and reads
# the *page* authority, so no proxy header reaches it: dsh-client-connection computes
# `isLoopback = transport?.ownsHost === true || isLoopbackHostname(location.hostname)`, and
# dsh-client-ui-settings turns a false there into `persistence: "memory"` — the symptom is
# `加载提供方目录失败: settings are unavailable in this browser` on 设置 → 模型.
#
# Only the UI was hidden: since 0.1.2-alpha.1 the Host half has no privileged loopback tier,
# every RPC passes the same Host/Origin fence and then the session cookie. `__DSH_TRANSPORT__`
# is upstream's own page global and its other members are optional, so this is a switch rather
# than a logic patch — but it still edits a shipped artifact, hence the guards: fail the build
# if the anchor moves or upstream starts shipping the global, never serve an unpatched page.
RUN set -eu; \
    index="$(find /usr/local/lib/node_modules -type f -path '*/dsh-web-frontend/dist/index.html')"; \
    test -n "${index}" && test "$(printf '%s\n' "${index}" | wc -l)" = "1" \
      || { echo "expected exactly one dsh-web-frontend dist index.html, found: ${index:-none}" >&2; exit 1; }; \
    ! grep -q '__DSH_TRANSPORT__' "${index}" \
      || { echo "${index} already sets __DSH_TRANSPORT__; drop this layer and re-read upstream" >&2; exit 1; }; \
    grep -q '<title>DeepSeek Harness</title>' "${index}" \
      || { echo "${index} lost the <title> anchor this injection hangs on" >&2; exit 1; }; \
    sed -i 's#<title>DeepSeek Harness</title>#&\n    <script>window.__DSH_TRANSPORT__ = { ownsHost: true }</script>#' "${index}"; \
    grep -q '__DSH_TRANSPORT__' "${index}"

# Match the arm host's `agent` user (uid/gid 1002) so bind mounts under /srv/dsh stay
# consistent. npm installed as root into /usr/local (world-readable); agent only reads it.
RUN groupadd -g 1002 agent 2>/dev/null || true \
  && useradd -u 1002 -g 1002 -d /data -M -s /bin/bash agent 2>/dev/null || true

ENV DSH_HOME=/data
USER agent
WORKDIR /workspaces
# Documentation only under host networking; the bind below is what actually decides.
EXPOSE 20003
# `dsh web` is still the alias for `dsh --profile web` in 0.1.2-alpha.x.
#
# --host is the upstream default but stated explicitly: it is the one line keeping the harness
# off every non-loopback interface of the host it shares. --trusted-host is the /api
# Host/Origin fence, not authentication — the credential gate is Caddy `basic_auth` plus dsh's
# own session cookie (compose.yaml documents how that cookie is first obtained). --no-open
# suppresses the default-browser handoff, which in a container only logs a failure.
CMD ["dsh", "web", \
     "--host", "127.0.0.1", \
     "--port", "20003", \
     "--trusted-host", "dsh.lkwplus.com", \
     "--no-open"]
