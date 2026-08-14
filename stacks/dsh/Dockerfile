# DeepSeek Harness (dsh) Web UI — built from upstream source (no published container image).
# Upstream ships npm releases but no git tags at all, so the source is cloned from GitHub and
# pinned to an exact commit by DSH_REF. Never track a branch here: dsh is a developer preview
# whose README warns of breaking changes, and a floating ref would let an unrelated redeploy
# (`extra_args = "--build"`) silently swap the running code. Bump the SHA to upgrade — Renovate
# cannot see this ref, so upgrades are manual; check the version in apps/cli/package.json and
# retag `image:` in compose.yaml to match.
#
# dsh web binds 127.0.0.1 only — packages/host/webserver's Config schema accepts just
# '127.0.0.1' | '0.0.0.0', and the CLI rejects 0.0.0.0 outright ("it would expose remote code
# execution to the network"). A bridge publish therefore cannot reach the process, so
# compose.yaml uses host networking on the arm loopback port 20003 for the host Caddy.
ARG DSH_REF=47f943859bef60e4160492346772ded9b24f765a

FROM node:22-bookworm AS build
ARG DSH_REF
# Node must satisfy upstream's engines: ^22.19.0 || >=24.0.0. pnpm comes from the repo's own
# packageManager field via corepack, so the version tracks the pinned source, not this file.
RUN corepack enable
WORKDIR /src
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates git \
  && rm -rf /var/lib/apt/lists/*
# fetch-by-SHA rather than `clone --branch`, which only accepts branch/tag names.
RUN git init -q . \
  && git remote add origin https://github.com/deepseek-ai/deepseek-harness.git \
  && git fetch --depth 1 origin "${DSH_REF}" \
  && git checkout -q FETCH_HEAD
RUN pnpm install --frozen-lockfile
RUN pnpm run build

FROM node:22-bookworm-slim AS runtime
ARG DSH_REF
LABEL org.opencontainers.image.source="https://github.com/deepseek-ai/deepseek-harness"
LABEL org.opencontainers.image.revision="${DSH_REF}"
WORKDIR /app
RUN apt-get update \
  && apt-get install -y --no-install-recommends bash ca-certificates git \
  && rm -rf /var/lib/apt/lists/*
COPY --from=build /src /app
# Match the arm host's `agent` user (uid/gid 1002) so bind mounts under /srv/dsh stay consistent.
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
CMD ["node", "/app/apps/cli/lib/bin.js", "web", \
     "--host", "127.0.0.1", \
     "--port", "20003", \
     "--trusted-host", "dsh.lkwplus.com"]
