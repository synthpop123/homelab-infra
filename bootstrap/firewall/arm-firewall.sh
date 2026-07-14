#!/usr/bin/env bash
# Arm (Oracle-Arm) host firewall — deny-by-default for Docker-published ports.
#
# Same design as fame-firewall.sh (read docs/firewall.md), minus what arm doesn't have:
# no Akko trusted source, no public port exceptions yet, no ufw leftovers to clean.
# Key invariants (do NOT break these):
#   * Container-published ports are filtered in DOCKER-USER (the FORWARD path) — with no
#     exceptions listed, every future published port starts unreachable from the internet
#     (v4 AND v6) until deliberately added to PUBLIC_TCP/PUBLIC_UDP here.
#   * The INPUT policy stays 'accept' and SSH (11322) is never filtered. Host ports we do
#     want closed (rpcbind 111, stock on Oracle images) are dropped in our own ARM-INPUT
#     subchain, which matches only those ports — it cannot lock SSH out.
#   * Published ports are DNATed before FORWARD -> match with conntrack --ctorigdstport.
#   * Idempotent: safe to re-run. Invoked by arm-firewall.service after docker.service.
set -uo pipefail

CONF=/etc/arm-firewall.conf
# shellcheck source=/dev/null
[ -r "$CONF" ] && . "$CONF"
: "${WAN_IF:?set WAN_IF in $CONF}"

# Ports that must stay reachable from the WHOLE internet. None yet — when a service on
# arm genuinely needs unsolicited inbound, add its HOST port here (and document it).
PUBLIC_TCP=""
PUBLIC_UDP=""

# Host (non-Docker) ports to close on the WAN side. rpcbind (111) ships enabled on
# Oracle's Ubuntu images and has no business being public; the service itself is left
# alone in case OCI tooling wants it locally.
HOST_DROP_TCP="111"
HOST_DROP_UDP="111"

apply_docker_user() {
  local ipt="$1" p
  "$ipt" -N DOCKER-USER 2>/dev/null || true
  "$ipt" -F DOCKER-USER
  # return traffic for connections the host/containers initiated
  "$ipt" -A DOCKER-USER -i "$WAN_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  # internet-facing exceptions, matched on the pre-DNAT host port
  for p in $PUBLIC_TCP; do
    "$ipt" -A DOCKER-USER -i "$WAN_IF" -p tcp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  for p in $PUBLIC_UDP; do
    "$ipt" -A DOCKER-USER -i "$WAN_IF" -p udp -m conntrack --ctorigdstport "$p" -j RETURN
  done
  # everything else arriving from the public NIC toward a container: drop
  "$ipt" -A DOCKER-USER -i "$WAN_IF" -j DROP
}

apply_input() {
  local ipt="$1" p
  "$ipt" -N ARM-INPUT 2>/dev/null || true
  "$ipt" -F ARM-INPUT
  for p in $HOST_DROP_TCP; do
    "$ipt" -A ARM-INPUT -p tcp --dport "$p" -j DROP
  done
  for p in $HOST_DROP_UDP; do
    "$ipt" -A ARM-INPUT -p udp --dport "$p" -j DROP
  done
  "$ipt" -C INPUT -i "$WAN_IF" -j ARM-INPUT 2>/dev/null || "$ipt" -I INPUT 1 -i "$WAN_IF" -j ARM-INPUT
}

apply_docker_user iptables
apply_docker_user ip6tables
apply_input iptables
apply_input ip6tables

echo "arm-firewall applied: WAN_IF=$WAN_IF, public tcp=[$PUBLIC_TCP] udp=[$PUBLIC_UDP], host-drop tcp=[$HOST_DROP_TCP] udp=[$HOST_DROP_UDP]"
