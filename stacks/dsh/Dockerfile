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
FROM node:22-bookworm-slim

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

# Match the arm host's `agent` user (uid/gid 1002) so bind mounts under /srv/dsh stay
# consistent. npm installed as root into /usr/local (world-readable); agent only reads it.
RUN groupadd -g 1002 agent 2>/dev/null || true \
  && useradd -u 1002 -g 1002 -d /data -M -s /bin/bash agent 2>/dev/null || true

ENV DSH_HOME=/data
USER agent
WORKDIR /workspaces
# Documentation only under host networking; the bind below is what actually decides.
EXPOSE 20003
# --host is the upstream default but stated explicitly: this is the one line keeping the
# harness off every non-loopback interface of the host it shares. --trusted-host is the /api
# browser-trust fence (Host-header authority behind the reverse proxy) and is NOT
# authentication — dsh ships none, so the host Caddy owns the credential gate.
CMD ["dsh", "web", \
     "--host", "127.0.0.1", \
     "--port", "20003", \
     "--trusted-host", "dsh.lkwplus.com"]
