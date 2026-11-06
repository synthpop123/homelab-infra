# Komari panel (fame host binary)

The komari panel runs on fame as a plain binary, not a Komodo stack:
`/opt/komari/komari` under systemd unit `komari` (`komari server -l 0.0.0.0:25774`), data in
`/opt/komari/data`. Komodo never deploys it.

[`upgrade.sh`](./upgrade.sh) pins the panel version. Renovate watches that pin and opens a PR
for each upstream release — that PR is the update notice. Merging it changes nothing on the
host; run the script afterwards from the repository root:

```sh
ssh fame 'bash -s' < bootstrap/komari/upgrade.sh
```

It verifies the download against GitHub's asset digest, keeps the old binary as `komari.prev`,
and restarts the panel. On first start after a version change komari itself zips `data/` to
`data/backup/upgrade-<time>.zip`; prune those by hand. Read the release notes first: 1.6.1, for example, swapped the JavaScript runtime used
by plugins and JS notification scripts.

The agents (`komari-agent` on fame and arm) are separate binaries and not covered here.
