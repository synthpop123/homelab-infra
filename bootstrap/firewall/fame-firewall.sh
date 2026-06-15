#!/usr/bin/env bash
# Fame host firewall — restrict Docker-published ports to the Akko reverse proxy.
#
# Read docs/firewall.md for the full rationale. Key invariants (do NOT break these):
#   * Docker uses the *iptables* firewall backend on this host, so it provides the
#     DOCKER-USER chain. All container-published ports are filtered there. DOCKER-USER
#     sits in the FORWARD path and runs BEFORE Docker's own accept rules.
#   * The INPUT policy stays 'accept' and SSH is never filtered. Host-network ports (e.g.
#     clouddrive2 19798) are limited via ONE jump to our FAME-INPUT subchain, which only drops
#     specific ports — SSH 11322 / Caddy / komari are never matched, so it can't lock SSH out.
#   * Published ports are DNATed before FORWARD, so the original host port is matched with
#     conntrack --ctorigdstport, not --dport. Source-IP matches (Akko) are DNAT-agnostic.
#   * Akko is IPv4-only, so the IPv6 path has no trusted source — it only lets the public
#     exception ports through and drops the rest (closing the IPv6 direct-connect hole).
#   * Idempotent: safe to re-run. Invoked by fame-firewall.service after docker.service.
set -uo pipefail

CONF=/etc/fame-firewall.conf
# shellcheck source=/dev/null
[ -r "$CONF" ] && . "$CONF"
: "${WAN_IF:?set WAN_IF in $CONF}"
: "${AKKO_IP:?set AKKO_IP in $CONF}"

# Ports that must stay reachable from the WHOLE internet (not just Akko):
#   222    gitea SSH — git clone/push over ssh
#   65231  qBittorrent BitTorrent listen — P2P needs unsolicited inbound (tcp+udp)
#   20011  beszel hub — remote agents connect straight to fame (no Akko hop)
PUBLIC_TCP="222 65231 20011"
PUBLIC_UDP="65231"

# --- 1) Remove leftover ufw chains (the previous attempt that conflicted with Docker) ---
cleanup_ufw() {
  local ipt="$1" prefix="$2" chain rule c chains
  for chain in INPUT OUTPUT FORWARD; do
    while IFS= read -r rule; do
      [ -n "$rule" ] || continue
      # shellcheck disable=SC2086
      "$ipt" $rule 2>/dev/null || true
    done < <("$ipt" -S "$chain" 2>/dev/null | grep -E -- "-j ${prefix}-" | sed 's/^-A /-D /')
  done
  chains=$("$ipt" -S 2>/dev/null | awk -v p="$prefix" '$1=="-N" && $2 ~ ("^" p "-") {print $2}')
  for c in $chains; do "$ipt" -F "$c" 2>/dev/null || true; done
  for c in $chains; do "$ipt" -X "$c" 2>/dev/null || true; done
}
cleanup_ufw iptables  ufw
cleanup_ufw ip6tables ufw6

# --- 2) (Re)apply DOCKER-USER restrictions for container-published ports ---
ensure_chain() { "$1" -N DOCKER-USER 2>/dev/null || true; }

apply_v4() {
  iptables -F DOCKER-USER
  # return traffic for connections the host/containers initiated
  iptables -A DOCKER-USER -i "$WAN_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  # trusted reverse proxy: may reach every container port
  iptables -A DOCKER-USER -i "$WAN_IF" -s "$AKKO_IP" -j RETURN
  # internet-facing exceptions, matched on the pre-DNAT host port
  for p in $PUBLIC_TCP; do
    iptables -A DOCKER-USER -i "$WAN_IF" -p tcp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  for p in $PUBLIC_UDP; do
    iptables -A DOCKER-USER -i "$WAN_IF" -p udp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  # everything else arriving from the public NIC toward a container: drop
  iptables -A DOCKER-USER -i "$WAN_IF" -j DROP
}

apply_v6() {
  ip6tables -F DOCKER-USER
  ip6tables -A DOCKER-USER -i "$WAN_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  # no trusted v6 source (Akko is IPv4-only) — only public exceptions pass
  for p in $PUBLIC_TCP; do
    ip6tables -A DOCKER-USER -i "$WAN_IF" -p tcp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  for p in $PUBLIC_UDP; do
    ip6tables -A DOCKER-USER -i "$WAN_IF" -p udp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  ip6tables -A DOCKER-USER -i "$WAN_IF" -j DROP
}

# --- 3) Host-network ports (not Docker-published) -> our own FAME-INPUT subchain ---
# clouddrive2's web UI (19798) is host-networked, so it rides INPUT, not DOCKER-USER. We add ONE
# jump from INPUT to FAME-INPUT and only drop that specific port there. SSH 11322 and the INPUT
# accept policy are never touched, so this cannot lock SSH out. No DNAT here -> match --dport.
HOST_ONLY_TCP="19798"
apply_input() {
  local ipt="$1" akko="$2" p
  "$ipt" -N FAME-INPUT 2>/dev/null || true
  "$ipt" -F FAME-INPUT
  for p in $HOST_ONLY_TCP; do
    [ -n "$akko" ] && "$ipt" -A FAME-INPUT -p tcp --dport "$p" -s "$akko" -j RETURN
    "$ipt" -A FAME-INPUT -p tcp --dport "$p" -j DROP
  done
  "$ipt" -C INPUT -i "$WAN_IF" -j FAME-INPUT 2>/dev/null || "$ipt" -I INPUT 1 -i "$WAN_IF" -j FAME-INPUT
}

ensure_chain iptables
ensure_chain ip6tables
apply_v4
apply_v6
apply_input iptables  "$AKKO_IP"
apply_input ip6tables ""

echo "fame-firewall applied: WAN_IF=$WAN_IF, trusted=$AKKO_IP, public tcp=[$PUBLIC_TCP] udp=[$PUBLIC_UDP], host-only tcp=[$HOST_ONLY_TCP]"
