# Komodo servers — how hosts join the control plane

How a server becomes managed by the Komodo Core on fame, and the runbook for adding
(or re-adding) one. Host inventories: [server.md](./server.md) (fame),
[server-arm.md](./server-arm.md) (arm).

## The mechanism (Komodo v2, outbound mode)

Every managed host runs the **Periphery** agent. Since v2 the agent connects **outbound**
to Core over a websocket (`wss://komodo-core.lkwplus.com/ws/periphery?server=<name>`), so a
new server needs **no inbound port at all** — it only has to reach Core's public HTTPS
endpoint (fame's host Caddy → `127.0.0.1:9120`). The Server resource's `config.address`
stays **empty**; a non-empty address would flip Komodo back to the legacy inbound
(Core→Periphery on :8120) mode.

Authentication is a public-key handshake, keyed off the `connect_as` name:

1. Periphery keeps an X25519 keypair under `${root_directory}/keys/`
   (`/etc/komodo/keys/periphery.key` for a systemd install). Core stores each server's
   expected public key at `Server.info.public_key` in Mongo.
2. On connect, Core looks the Server up **by name**:
   - **Name exists & keys match** → logged in. No onboarding key involved.
   - **Name exists & keys mismatch** → login refused; the offered key is parked in
     `Server.info.attempted_public_key` so an admin can accept it in the UI (or a
     *privileged* onboarding key can overwrite it).
   - **Name unknown** → onboarding flow: the agent must present a valid **onboarding key**
     (Settings → Onboarding Keys), and Core creates the Server resource storing the agent's
     public key.
3. The onboarding key is only ever used for that first contact. Afterwards the keypair is
   the whole trust relationship — Komodo auto-rotates it (`auto_rotate_keys = true`).

Consequences worth remembering:

- **Deleting a Server resource in the UI deletes its stored public key.** The agent on the
  host keeps running with its old keypair and can *not* rejoin by itself — its onboarding
  key is likely gone too (they live in the `OnboardingKey` collection). This exact state
  happened to the arm host in 2026-06; the fix is the headless re-adopt below.
- The `[[server]]` blocks in [`sync.toml`](../komodo/sync.toml) declare the fleet as code,
  but a sync-created Server has an **empty** public key — the key exchange is always
  out-of-band. Adopt the host first (UI onboarding key or headless route), *then* let the
  sync reconcile config.

## Adding a new server

1. **UI:** Settings → Onboarding Keys → create a key (`O_...`). Non-privileged is enough
   for a brand-new name.
2. **On the new host** (root):

```bash
curl -sSL https://raw.githubusercontent.com/moghtech/komodo/main/scripts/setup-periphery.py \
  | python3 - \
  --core-address="https://komodo-core.lkwplus.com" \
  --connect-as="<ServerName>" \
  --onboarding-key="O_..."
systemctl enable periphery   # the installer does NOT enable it — without this it dies on reboot
```

3. Confirm: `journalctl -u periphery -n 5` shows
   `Logged in to Komodo Core ... as Server <ServerName>`, and the server shows **OK** in
   the UI.
4. **Same commit:** add the `[[server]]` block to [`sync.toml`](../komodo/sync.toml) and a
   `docs/server-<name>.md` inventory page.

Config file: `/etc/komodo/periphery.config.toml` (`core_address`, `connect_as`,
`onboarding_key` — the key can be blanked once onboarded). Re-running the installer
script after a Komodo release upgrades the binary without touching existing config.

## Headless re-adopt (no UI — agents, recovery)

When the host still has its keypair but Core lost the Server resource (deleted, or a
Mongo restore from before onboarding), recreate the resource directly in Mongo with the
host's **existing** public key — same pattern as
[komodo-variables.md](./komodo-variables.md#the-host-way-no-uiapi--agents-recovery):

```bash
# 1. Grab the host's public key (single base64 line between the PEM headers)
ssh <host> "sed -n 2p /etc/komodo/keys/periphery.pub"

# 2. Insert the Server document on fame (edit name/description/pubkey)
ssh fame '
cat > /tmp/server.js <<"JS"
const d = db.getSiblingDB("komodo");
const name = "<ServerName>";
if (d.Server.findOne({ name })) { print("already exists"); quit(); }
d.Server.insertOne({
  name, description: "<desc>", template: false, tags: [],
  info: { attempted_public_key: "", public_key: "<PUBKEY_BASE64>" },
  config: {
    address: "", insecure_tls: false, external_address: "", region: "",
    enabled: true, auto_rotate_keys: true, passkey: "",
    ignore_mounts: [], auto_prune: true, links: [],
    stats_monitoring: true, send_unreachable_alerts: true, send_cpu_alerts: true,
    send_mem_alerts: true, send_disk_alerts: true, send_version_mismatch_alerts: true,
    cpu_warning: 90, cpu_critical: 99, mem_warning: 75, mem_critical: 95,
    disk_warning: 75, disk_critical: 95, maintenance_windows: []
  },
  base_permission: "None", updated_at: Long.fromNumber(Date.now())
});
print("inserted " + name);
JS
docker exec -i komodo-mongo sh -c "mongosh \"mongodb://\$MONGO_INITDB_ROOT_USERNAME:\$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin\" --quiet" < /tmp/server.js
rm -f /tmp/server.js
docker restart komodo-core'   # control plane only; running stacks unaffected

# 3. Kick the agent and verify
ssh <host> 'systemctl restart periphery && sleep 5 && journalctl -u periphery -n 3 --no-pager'
```

The agent logs `Logged in to Komodo Core` and the UI shows the server **OK**. If instead
the *host* lost its keypair (rebuilt machine), this route doesn't apply — create a fresh
onboarding key and go through [Adding a new server](#adding-a-new-server); Core will park
the new key in `attempted_public_key` for acceptance if the Server resource still exists.

## Deploying stacks to another server

Nothing else changes in the workflow: a stack targets a host via `server = "<ServerName>"`
in its `[[stack]]` block ([workflow.md](./workflow.md) covers the push→deploy path, which
is server-agnostic). Before pointing a first stack at a new host, make sure the host-side
conventions exist there too: `/srv/<service>/` data dirs, Docker log rotation
(`daemon.json`), fail2ban, and a firewall stance — arm has all but the `/srv` layout in
place ([server-arm.md](./server-arm.md)); its firewall is deny-by-default, so a published
port also needs an exception in `arm-firewall.sh` (or a proxy decision) to be reachable.
