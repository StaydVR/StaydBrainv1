# Dream cycle

`agent-brain dream` is deterministic, lock-protected maintenance. It is review-first: it may rebuild derived indexes, write the daily report, write a database backup, and append audit/run metadata. It never edits, merges, forgets, or rewrites ordinary canonical memories.

The phases are:

1. Acquire an exclusive, durable local lock and recover a provably stale process lock.
2. Validate and synchronize canonical and cache documents; rebuild a corrupt disposable index when possible.
3. Recompute links, backlinks, exact normalized-body duplicate candidates, fact contradictions, stale evidence, orphans, and broken links.
4. Render one deterministic daily review report with a deterministic UUIDv5 identity.
5. Atomically replace the report only when its bytes changed, then resynchronize derived state.
6. Run SQLite integrity checking and atomically replace the daily backup after fsync.
7. Finish the run record and append a hash-chained audit event containing hashes and safe metadata only.

Analysis excludes earlier dream reports. Its freshness cutoff is anchored to UTC midnight for the report day. Repeating a run against unchanged ordinary knowledge yields identical findings and report bytes; run and audit records still show each execution.

A failed report or backup replacement leaves the previous artifact intact. The run becomes `failed` with only an exception type, and the lock is released. `--dry-run` parses current canonical files directly and writes no index, report, run, audit event, or backup.
