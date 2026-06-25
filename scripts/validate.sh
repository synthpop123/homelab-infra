#!/usr/bin/env bash
# Pre-deploy lint gate for the declarative infra in this repo.
#
# Why this exists: a push to `main` flows straight into Komodo's `Redeploy On Push`
# procedure (see docs/workflow.md) with no other check in between — a malformed
# compose or sync.toml would only blow up mid-deploy on the VPS. This script is the
# cheap gate that runs in CI (.github/workflows/lint.yml) on every PR, and can be run
# by hand before pushing:  ./scripts/validate.sh
#
# It validates three things:
#   1. yamllint        — every stacks/*/compose.yaml (duplicate keys, tabs, structure)
#   2. compose config  — the SAME parser Komodo uses; catches schema errors
#   3. sync.toml / renovate.json — TOML / JSON syntax of the files that drive automation
#
# STRICT=1 (set in CI) turns "tool not installed -> skip" into a hard failure, so CI
# always runs all three. Locally, missing tools are skipped with a warning.
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

# --- 1) yamllint every compose file ---------------------------------------------
echo "== yamllint =="
if command -v yamllint >/dev/null 2>&1; then
  yamllint stacks/ || fail=1
else
  skip_or_fail "yamllint not installed"
fi

# --- 2) docker compose config — real schema validation --------------------------
echo "== docker compose config =="
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  for compose in stacks/*/compose.yaml; do
    dir="$(dirname "$compose")"
    # env_file targets (.env / .env.production) are git-ignored — Komodo materializes
    # them at deploy. Create empty placeholders so `config` doesn't fail on a missing
    # file, then remove them again so the working tree stays clean.
    created=""
    for e in $(grep -oE '\.env[A-Za-z.]*' "$compose" | sort -u); do
      if [ ! -e "$dir/$e" ]; then : > "$dir/$e"; created="$created $dir/$e"; fi
    done
    # `... is not set. Defaulting to a blank string` warnings are expected here —
    # secrets live in Komodo Variables, not in the tree — so drop them and surface
    # only real errors. The exit code (not the text) decides pass/fail.
    if out="$(docker compose -f "$compose" config -q 2>&1)"; then
      echo "ok: $compose"
    else
      echo "FAIL: $compose" >&2
      printf '%s\n' "$out" | grep -v 'level=warning' >&2
      fail=1
    fi
    for c in $created; do rm -f "$c"; done
  done
else
  skip_or_fail "docker compose not available"
fi

# --- 3) sync.toml + renovate.json syntax ----------------------------------------
echo "== sync.toml / renovate.json =="
if command -v python3 >/dev/null 2>&1; then
  python3 - "$repo_root" <<'PY' || fail=1
import json, os, sys
root = sys.argv[1]
ok = True
try:
    import tomllib
except ModuleNotFoundError:
    print("note: python <3.11, skipping sync.toml TOML check")
    tomllib = None
if tomllib is not None:
    try:
        with open(os.path.join(root, "komodo/sync.toml"), "rb") as f:
            tomllib.load(f)
        print("ok: komodo/sync.toml")
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

# --------------------------------------------------------------------------------
if [ "$fail" -ne 0 ]; then
  echo "== validation FAILED ==" >&2
  exit 1
fi
echo "== validation passed =="
