#!/usr/bin/env bash
# Upgrade the komari panel (host binary under /opt/komari, systemd unit `komari`) to the
# pinned version. Run from the repository root:
#   ssh fame 'bash -s' < bootstrap/komari/upgrade.sh
#
# The pin below is what Renovate watches (renovate.json customManagers): a new upstream
# release opens a PR here, and merging it changes nothing on the host until this is run.
set -euo pipefail

# renovate: datasource=github-releases depName=komari-monitor/komari
KOMARI_VERSION="1.6.1"

dir=/opt/komari
repo=komari-monitor/komari
case "$(uname -m)" in
  x86_64) asset=komari-linux-amd64 ;;
  aarch64) asset=komari-linux-arm64 ;;
  *) echo "unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

current="$("$dir/komari" --help 2>&1 | grep -oE 'Komari Monitor [^ ]+' | head -1 | cut -d' ' -f3 || true)"
echo "current: ${current:-unknown}  target: $KOMARI_VERSION"
if [ "$current" = "$KOMARI_VERSION" ]; then
  echo "already at $KOMARI_VERSION"
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# GitHub records a sha256 digest for every release asset; verify the download against it.
want="$(curl -fsSL "https://api.github.com/repos/$repo/releases/tags/$KOMARI_VERSION" |
  jq -r --arg a "$asset" '.assets[] | select(.name == $a) | .digest' | sed 's/^sha256://')"
[ -n "$want" ] && [ "$want" != null ] || { echo "no digest for $asset in $KOMARI_VERSION" >&2; exit 1; }
curl -fsSL -o "$tmp/komari" "https://github.com/$repo/releases/download/$KOMARI_VERSION/$asset"
echo "$want  $tmp/komari" | sha256sum -c -
chmod 755 "$tmp/komari"

# No separate data backup: on first start after a version change komari itself zips ./data
# to data/backup/upgrade-<time>.zip before migrating.
systemctl stop komari
cp -p "$dir/komari" "$dir/komari.prev"
install -m 755 "$tmp/komari" "$dir/komari"
systemctl start komari

sleep 3
systemctl is-active komari
journalctl -u komari --since "-1min" --no-pager | grep -E 'Komari Monitor [0-9]|upgrade-backup' || true
echo "rollback: systemctl stop komari && mv $dir/komari.prev $dir/komari && restore data from $dir/data/backup/upgrade-*.zip && systemctl start komari"
