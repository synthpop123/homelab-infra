# Fame THP collapse limits

`fame-thp.service` applies before Docker at boot. It sets
`khugepaged/max_ptes_none=0` and `max_ptes_swap=0`: background THP collapse
must not fill unmapped pages or bring swapped-out pages back into RAM.
It leaves the host's `enabled=always`, `defrag=madvise`, and
`shmem_enabled=never` policies unchanged. Fault-time THP allocations remain
possible; this does not release existing huge pages or allocator caches.

Install from the repository root (host configuration is not deployed by Komodo):

```sh
scp bootstrap/thp/fame-thp.service fame:/etc/systemd/system/fame-thp.service
ssh fame 'systemd-analyze verify /etc/systemd/system/fame-thp.service && systemctl daemon-reload && systemctl enable --now fame-thp.service'
```

Check the active values (both should be `0`):

```sh
ssh fame 'systemctl is-enabled fame-thp.service; systemctl is-active fame-thp.service; cat /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_swap'
```

No container or host restart is required. After editing an already active unit,
run `daemon-reload` and `restart fame-thp.service` to apply it again.

Rollback to the values recorded before installation:

```sh
ssh fame 'systemctl disable --now fame-thp.service && echo 511 > /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_none && echo 64 > /sys/kernel/mm/transparent_hugepage/khugepaged/max_ptes_swap'
```

Stopping the unit alone does not restore the previous values.
See the [Linux 6.1 THP documentation](https://kernel.org/doc/html/v6.1/admin-guide/mm/transhuge.html).
