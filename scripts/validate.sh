#!/usr/bin/env bash
# Pre-deploy lint gate for the declarative infra in this repo.
#
# Why this exists: a push to `main` flows straight into Komodo's `Redeploy On Push`
# procedure (see docs/workflow.md) with no other check in between — a malformed
# compose or sync.toml would only blow up mid-deploy on the VPS. This script is the
# cheap gate that runs in CI (.github/workflows/lint.yml) on relevant infrastructure
# PRs, and can be run by hand before pushing:  ./scripts/validate.sh
#
# It validates five things:
#   1. yamllint        — stack and bootstrap compose files (duplicate keys, tabs, structure)
#   2. compose config  — the SAME parser Komodo uses; catches schema errors
#   3. shell syntax    — bootstrap scripts parse before they are installed on a host
#   4. sync.toml schema / renovate.json — resource types and JSON syntax of the files that drive automation
#   5. image pins      — every `image:` carries an explicit tag, never `:latest`, unless the line
#                        opts out with an inline `# allow-latest` (docs/conventions.md)
#
# STRICT=1 (set in CI) turns "tool not installed -> skip" into a hard failure, so CI
# always runs every check. Locally, missing tools are skipped with a warning.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

: "${STRICT:=0}"
fail=0

skip_or_fail() { # message
  if [ "$STRICT" = "1" ]; then
    echo "ERROR (STRICT): $1" >&2
    fail=1
  else
    echo "skip: $1" >&2
  fi
}

# --- 1) yamllint every compose file (reported after 2) ---------------------------
# Started in the background so it overlaps the compose checks below; its result is
# reported right after them.
yamllint_out="$(mktemp)"
yamllint_pid=""
if command -v yamllint >/dev/null 2>&1; then
  yamllint stacks/ bootstrap/komodo/mongo.compose.yaml > "$yamllint_out" 2>&1 &
  yamllint_pid=$!
fi

# --- 2) docker compose config — real schema validation --------------------------
echo "== docker compose config =="
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  # Each compose file is checked in its own background job: one `config` is ~80 ms of
  # mostly CLI start-up, so ~40 of them serially dominated the whole gate. Every file sits
  # in its own directory, so the per-file env placeholders below never collide.
  check_compose() { # compose
    local compose="$1" dir created="" out
    dir="$(dirname "$compose")"
    # env_file targets (.env / .env.production) are git-ignored — Komodo materializes
    # them at deploy. Create placeholders so `config` doesn't fail on a missing file,
    # then remove them again so the working tree stays clean. The Komodo bootstrap needs
    # its example values for compose-time interpolation; stack env files can stay empty.
    if [ "$compose" = "bootstrap/komodo/mongo.compose.yaml" ]; then
      if [ ! -e "$dir/compose.env" ]; then
        cp "$dir/compose.env.example" "$dir/compose.env"
        created="$created $dir/compose.env"
      fi
    else
      for e in $(grep -oE '\.env[A-Za-z.]*' "$compose" | sort -u); do
        if [ ! -e "$dir/$e" ]; then : > "$dir/$e"; created="$created $dir/$e"; fi
      done
    fi
    # `... is not set. Defaulting to a blank string` warnings are expected here —
    # secrets live in Komodo Variables, not in the tree — so drop them and surface
    # only real errors. The exit code (not the text) decides pass/fail.
    if [ "$compose" = "bootstrap/komodo/mongo.compose.yaml" ]; then
      command=(docker compose --env-file "$dir/compose.env" -f "$compose" config -q)
    else
      command=(docker compose -f "$compose" config -q)
    fi
    if out="$("${command[@]}" 2>&1)"; then
      echo "ok: $compose"
    else
      echo "FAIL: $compose"
      printf '%s\n' "$out" | grep -v 'level=warning'
      for c in $created; do rm -f "$c"; done
      return 1
    fi
    for c in $created; do rm -f "$c"; done
  }
  results="$(mktemp -d)"
  i=0
  for compose in stacks/*/compose.yaml bootstrap/komodo/*.compose.yaml; do
    i=$((i + 1))
    check_compose "$compose" > "$results/$i.out" 2>&1 &
    echo $! > "$results/$i.pid"
  done
  # Collect in file order so the log reads the same as the old serial loop.
  for n in $(seq 1 "$i"); do
    if wait "$(cat "$results/$n.pid")"; then
      cat "$results/$n.out"
    else
      cat "$results/$n.out" >&2
      fail=1
    fi
  done
  rm -rf "$results"
else
  skip_or_fail "docker compose not available"
fi

echo "== yamllint =="
if [ -n "$yamllint_pid" ]; then
  wait "$yamllint_pid" || fail=1
  cat "$yamllint_out"
else
  skip_or_fail "yamllint not installed"
fi
rm -f "$yamllint_out"

# --- 3) bootstrap shell syntax ---------------------------------------------------
echo "== bootstrap shell syntax =="
for script in bootstrap/*/*.sh; do
  if bash -n "$script"; then
    echo "ok: $script"
  else
    fail=1
  fi
done

# --- 4) sync.toml + renovate.json syntax ----------------------------------------
echo "== sync.toml / renovate.json =="
if command -v python3 >/dev/null 2>&1; then
  python3 - "$repo_root" <<'PY' || fail=1
import json, os, sys
root = sys.argv[1]
ok = True
try:
    import tomllib
except ModuleNotFoundError:
    print("skip: Python 3.11+ required for sync.toml", file=sys.stderr)
    if os.environ.get("STRICT") == "1":
        ok = False
    tomllib = None
if tomllib is not None:
    try:
        with open(os.path.join(root, "komodo/sync.toml"), "rb") as f:
            resources = tomllib.load(f)
        try:
            import jsonschema
        except ModuleNotFoundError:
            print("skip: install scripts/lint-requirements.txt for sync.toml schema validation", file=sys.stderr)
            if os.environ.get("STRICT") == "1":
                ok = False
        else:
            with open(os.path.join(root, "komodo/schemas/resources-v2.3.3.json")) as f:
                schema = json.load(f)
            jsonschema.Draft7Validator.check_schema(schema)
            errors = list(jsonschema.Draft7Validator(schema).iter_errors(resources))
            for error in errors:
                location = ".".join(map(str, error.absolute_path)) or "root"
                print(f"FAIL: sync.toml {location}: {error.message}", file=sys.stderr)
            if errors:
                ok = False
            else:
                print("ok: komodo/sync.toml (v2.3.3 resource schema)")
    except Exception as e:
        print(f"FAIL: komodo/sync.toml: {e}", file=sys.stderr); ok = False
try:
    with open(os.path.join(root, "renovate.json")) as f:
        json.load(f)
    print("ok: renovate.json")
except Exception as e:
    print(f"FAIL: renovate.json: {e}", file=sys.stderr); ok = False
sys.exit(0 if ok else 1)
PY
else
  skip_or_fail "python3 not available"
fi

# --- 5) image pins ---------------------------------------------------------------
# Renovate's docker-compose manager reads the literal `image:` text, so check that text
# (not the resolved config): an untagged or `:latest` image is invisible to Renovate.
echo "== image pins =="
pins_ok=1
while IFS= read -r line; do
  file="${line%%:*}"; rest="${line#*:}"; lineno="${rest%%:*}"
  raw="${rest#*:}"
  image="$(printf '%s' "$raw" | sed -E 's/^[[:space:]]*image:[[:space:]]*//; s/[[:space:]]+#.*$//; s/^["'\'']//; s/["'\'']$//')"
  name="${image##*/}"
  # `# allow-latest` opts a line out: used when upstream updates itself out-of-band, so a
  # version pin would only ever lag behind the running software.
  if [[ "$raw" != *allow-latest* && "$image" != *@sha256:* && ( "$name" != *:* || "$name" == *:latest ) ]]; then
    echo "FAIL: $file:$lineno image not pinned to an explicit tag: $image" >&2
    pins_ok=0
  fi
done < <(grep -nE '^[[:space:]]*image:' stacks/*/compose.yaml bootstrap/komodo/*.compose.yaml /dev/null)
if [ "$pins_ok" -eq 1 ]; then echo "ok: all images pinned"; else fail=1; fi

# --------------------------------------------------------------------------------
if [ "$fail" -ne 0 ]; then
  echo "== validation FAILED ==" >&2
  exit 1
fi
echo "== validation passed =="
