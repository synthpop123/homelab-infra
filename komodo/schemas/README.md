# Komodo resource schema

`resources-v2.3.3.json` is based on the static schema shipped by Komodo v2.3.3:
https://github.com/moghtech/komodo/blob/v2.3.3/ui/public/schema/resources.json

The file was fetched from our v2.3.3 Core's `/schema/resources.json` endpoint and
compared with the tagged upstream file. It contains no instance data or secrets.
It is vendored so CI and editor completion work without a running Core.

Local changes (intentionally more restrictive than upstream):

- Add `BatchDeployStackIfChanged.tags: string[]`, missing from the shipped schema
  but present in the v2.3.3 Rust API definition:
  https://github.com/moghtech/komodo/blob/v2.3.3/client/core/rs/src/api/execute/stack.rs
- Reject unknown root resource names and unknown properties in the partial Stack,
  Server, Procedure and Resource Sync configs. Other upstream objects remain permissive;
  this is not a complete unknown-field detector.
- Replace the upstream Slack webhook example URL with a placeholder so the schema
  does not trip GitHub push protection.
- Add a provenance comment; normalize JSON formatting.

`sync.toml` uses a Taplo `#:schema` directive for editor completion. The lint gate
uses Python jsonschema (Draft 7) for validation. `extra_args` uses the canonical
array form rather than the string shorthand accepted by Komodo's deserializer.

When upgrading Komodo, fetch the schema from the versioned upstream tag, compare
it to the running Core, review these local changes against the Rust types, and
update both the directive and `scripts/validate.sh`. Do not replace it with a
floating URL to the production Core or silently discard the local strictness.
