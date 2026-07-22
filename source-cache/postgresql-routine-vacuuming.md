# oracle/postgresql-routine-vacuuming — VACUUM, autovacuum, transaction ID wraparound
Source: https://www.postgresql.org/docs/current/routine-vacuuming.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-PGVAC-001: Transaction ID Wraparound Prevention — The Two-Billion-Transaction Bound
**Core Invariant:**
```
∀ table t in cluster, ∀ window w of 2B transactions:
  t must be vacuumed at least once within w
  ⟹ otherwise: XID wraparound → past rows appear future → catastrophic data loss
```
**Source:** Section 24.1.5 "Preventing Transaction ID Wraparound Failures" — "To avoid this, it is necessary to vacuum every table in every database at least once every two billion transactions."
**Counterexample:** A static table left unvacuumed for >2B transactions. Its rows carry XIDs that were originally in the past but wrap around to appear in the future. Those rows become invisible to all queries. The data still exists on disk but cannot be read — "catastrophic data loss."
**Why this matters for bridge/orbit:** Bridge's session ledger and orbit's dispatch log both use PostgreSQL. If either runs long enough without vacuum, the audit trail itself becomes unreadable. This is a liveness invariant on the write path of every table — not just user data, but system catalogs too.

### INV-PGVAC-002: FrozenTransactionId Total Ordering
**Core Invariant:**
```
∀ normal XID n: FrozenTransactionId < n   (mod 2^32 comparison)
⟹ Frozen rows are always visible to all normal transactions, forever
```
**Source:** Section 24.1.5 — "FrozenTransactionId ... does not follow the normal XID comparison rules and is always considered older than every normal XID."
**Counterexample:** If FrozenTransactionId were compared using modulo-2^32 arithmetic like normal XIDs, it too would wrap around after 2B transactions. Frozen rows would become invisible and the freeze mechanism would provide no protection. The special comparison rule is what makes freezing work.
**Why this matters for bridge/orbit:** This is a total-order invariant embedded in the transaction system itself. Any correctness argument about long-running bridge/orbit deployments depends on freezing working correctly. If this invariant breaks, all frozen data (including schema metadata in system catalogs) becomes invisible.

### INV-PGVAC-003: XID Exhaustion Hard Stop
**Core Invariant:**
```
∀ database d: when (wraparound_point - oldest_unfrozen_XID_in_d) < 3,000,000:
  system refuses to assign new XIDs in d
  ⟹ all write transactions in d fail
  ⟹ only read-only transactions can start
```
**Source:** Section 24.1.5 — "the system will refuse to assign new XIDs once there are fewer than three million transactions left until wraparound ... In this condition any transactions already in progress can continue, but only read-only transactions can be started."
**Counterexample:** Without this hard stop, a database could silently cross the wraparound boundary. Once XIDs wrap, past data becomes invisible and the outage is silent until queries return wrong results. The 3M-transaction safety margin is a circuit breaker — it trades availability (writes blocked) for integrity (no silent data loss).
**Why this matters for bridge/orbit:** Bridge and orbit both write to PostgreSQL. If XID exhaustion is reached, all write paths fail hard. This is a liveness invariant — the system must detect danger and fail-stop before corruption, not after. Orbit's dispatch loop and bridge's ledger append would both halt.

### INV-PGVAC-004: Anti-Wraparound Autovacuum Is Unkillable
**Core Invariant:**
```
∀ table t: if age(relfrozenxid) > autovacuum_freeze_max_age:
  autovacuum is invoked on t
  ⟹ holds even if autovacuum is globally disabled
  ⟹ conflicting lock requests (SHARE UPDATE EXCLUSIVE) will NOT interrupt this autovacuum
```
**Source:** Section 24.1.5 — "autovacuum is invoked on any table that might contain unfrozen rows with XIDs older than the age specified by the configuration parameter autovacuum_freeze_max_age. (This will happen even if autovacuum is disabled.)" And Section 24.1.6 — "if the autovacuum is running to prevent transaction ID wraparound ... the autovacuum is not automatically interrupted."
**Counterexample:** Suppose autovacuum is disabled globally for performance reasons. A static table accumulates age. Without this invariant, the table would silently pass the wraparound point and data would become invisible. Additionally, if regular lock-acquiring commands (like manual ANALYZE) could interrupt an anti-wraparound vacuum, the vacuum could be starved indefinitely on a busy table, again leading to silent wraparound.
**Why this matters for bridge/orbit:** This is a defense-in-depth invariant. Even if someone misconfigures autovacuum off, even if concurrent lock traffic is high, the system will force vacuum before wraparound. Bridge's session tables and orbit's dispatch tables are write-heavy and could theoretically trigger this path.

### INV-PGVAC-005: relfrozenxid Advancement Requires Full Scan
**Core Invariant:**
```
∀ table t: relfrozenxid advances
  ⟺ every page in t that might contain unfrozen XIDs has been scanned
  ⟹ partial scans (normal VACUUM skipping all-visible pages) do NOT advance relfrozenxid
```
**Source:** Section 24.1.5 — "relfrozenxid will only be advanced when every page of the table that might contain unfrozen XIDs is scanned."
**Counterexample:** If relfrozenxid advanced after a partial scan (skipping all-visible-but-not-all-frozen pages), the system would incorrectly believe the table is safe from wraparound. The skipped pages still carry old unfrozen XIDs. When wraparound occurs, those rows vanish. The invariant ensures that the "oldest XID" watermark is a true lower bound — no row in the table has an unfrozen XID older than relfrozenxid.
**Why this matters for bridge/orbit:** Correctness of the wraparound safety margin (INV-PGVAC-001) depends on relfrozenxid being an honest lower bound. If bridge/orbit tables report a falsely advanced relfrozenxid, the circuit breaker in INV-PGVAC-003 fires too late or not at all.

### INV-PGVAC-006: Aggressive VACUUM Guarantees relminmxid Advancement
**Core Invariant:**
```
∀ table t: aggressive VACUUM on t
  ⟹ relminmxid advances  (oldest multixact ID in t moves forward)
  ⟹ eventually, ∀ databases: oldest multixact values advance
      → on-disk storage for old multixacts is reclaimed
```
**Source:** Section 24.1.5.1 — "Aggressive VACUUMs, regardless of what causes them, are guaranteed to be able to advance the table's relminmxid."
**Counterexample:** If an aggressive VACUUM could fail to advance relminmxid (e.g., because multixact members reference still-running transactions), the multixact storage would grow unboundedly. With a 32-bit multixact ID space, unbounded growth means wraparound and loss of row-lock information. The guarantee ensures liveness — multixact storage is always eventually reclaimed.
**Why this matters for bridge/orbit:** Orbit uses row-level locking for dispatch state management. If multixact storage is not reclaimed, orbit's lock operations could fail when the 20GB members storage limit is hit.

### INV-PGVAC-007: vacuum_freeze_table_age Hard Cap
**Core Invariant:**
```
∀ configuration: effective vacuum_freeze_table_age = min(setting, 0.95 * autovacuum_freeze_max_age)
```
**Source:** Section 24.1.5 — "The effective maximum for vacuum_freeze_table_age is 0.95 * autovacuum_freeze_max_age; a setting higher than that will be capped to the maximum."
**Counterexample:** If an administrator sets vacuum_freeze_table_age > autovacuum_freeze_max_age, the anti-wraparound autovacuum (INV-PGVAC-004) would fire before the table-age threshold is reached. The aggressive vacuum would never trigger from the table-age path — it would only trigger from the anti-wraparound path, which is an emergency mechanism rather than routine maintenance. The 0.95 cap ensures a 5% gap window where routine aggressive vacuuming runs before the emergency override fires.
**Why this matters for bridge/orbit:** Configuration errors cannot create a gap between "routine vacuum" and "emergency vacuum" that the routine path never fills. The invariant prevents misconfigurations that silently degrade to emergency-only vacuuming.

### INV-PGVAC-008: MVCC Row Retention — Visibility Before Reclamation
**Core Invariant:**
```
∀ row version v, ∀ transaction T_active:
  if v is potentially visible to T_active:
    v must NOT be removed from disk
  ⟹ VACUUM only removes row versions no longer visible to any active transaction
```
**Source:** Section 24.1.2 — "the row version must not be deleted while it is still potentially visible to other transactions."
**Counterexample:** If VACUUM removed a row version that a long-running transaction still needed to see, that transaction would get incorrect query results (missing rows that should be visible per its snapshot). This violates snapshot isolation. In practice, VACUUM uses the oldest active transaction ID (xmin horizon) as the cutoff — only versions with XID < oldest active XID are eligible for removal.
**Why this matters for bridge/orbit:** Bridge's long-running audit sessions and orbit's multi-step dispatch operations rely on snapshot isolation. If VACUUM incorrectly reaped rows visible to an in-flight transaction, bridge could see inconsistent ledger state and orbit could lose track of dispatched work items.

### INV-PGVAC-009: VACUUM FULL — Exclusive Access Gate
**Core Invariant:**
```
∀ table t: VACUUM FULL on t requires ACCESS EXCLUSIVE lock
  ⟹ ∀ other operations o on t: o is blocked for the duration of VACUUM FULL
```
**Source:** Section 24.1.1 — "VACUUM FULL requires an ACCESS EXCLUSIVE lock on the table it is working on, and therefore cannot be done in parallel with other use of the table."
**Counterexample:** If VACUUM FULL could run without ACCESS EXCLUSIVE lock, concurrent writes could modify pages while the full-table rewrite is in progress. The new table file would miss those writes, losing data. The exclusive lock ensures the rewrite sees a consistent snapshot and no data is lost during compaction.
**Why this matters for bridge/orbit:** Orbit's dispatch loop and bridge's ledger writes cannot tolerate table-level downtime from VACUUM FULL. This invariant means standard VACUUM (which allows concurrent reads/writes) is the only live option for production tables. Any table requiring VACUUM FULL during operation is a design error.

### INV-PGVAC-010: Visibility Map Correctness
**Core Invariant:**
```
∀ page p, ∀ moment m: if p is marked all-visible in visibility map:
  all tuples on p are visible to all active transactions at m
  ∧ all tuples on p are visible to all future transactions (until p is modified)
```
**Source:** Section 24.1.4 — "Vacuum maintains a visibility map for each table to keep track of which pages contain only tuples that are known to be visible to all active transactions (and all future transactions, until the page is again modified)."
**Counterexample:** If a page is marked all-visible in the map but contains a tuple invisible to the current transaction (e.g., an uncommitted INSERT or a row version from a future XID), an index-only scan would skip the heap fetch and return that invisible tuple. The query would see data it should not see — a direct violation of transaction isolation. The index-only scan optimization trusts the visibility map absolutely, so the map must never have false positives.
**Why this matters for bridge/orbit:** Bridge uses index-only scans for its ledger queries. Orbit uses them for dispatch status lookups. A corrupted visibility map would cause bridge to report inconsistent ledger entries and orbit to dispatch tasks based on stale/invisible state.

### INV-PGVAC-011: Autovacuum Track-Counts Dependency
**Core Invariant:**
```
autovacuum is operational ⟹ track_counts = true
(Contrapositive: track_counts = false ⟹ autovacuum cannot determine which tables need vacuuming)
```
**Source:** Section 24.1.6 — "These checks use the statistics collection facility; therefore, autovacuum cannot be used unless track_counts is set to true."
**Counterexample:** If track_counts is false, autovacuum has no visibility into insert/update/delete activity. It cannot compute the vacuum threshold (base + scale * ntuples) and thus never triggers routine vacuum. Only the anti-wraparound emergency path (INV-PGVAC-004) will fire — meaning all vacuuming becomes emergency-driven rather than workload-driven. Tables bloat between wraparound-driven vacuums.
**Why this matters for bridge/orbit:** Bridge and orbit should verify track_counts is on in their PostgreSQL configurations. If turned off (e.g., for benchmarking), the system degrades to emergency-only vacuuming, which is a liveness degradation even if correctness is maintained.

### INV-PGVAC-012: Multixact Storage Bound
**Core Invariant:**
```
Multixact members storage ≤ ~20GB before wraparound
⟹ if members storage > ~10GB: aggressive vacuum scans occur more often for all tables
```
**Source:** Section 24.1.5.1 — "if the storage occupied by multixacts members exceeds about 10GB, aggressive vacuum scans will occur more often for all tables ... The members storage area can grow up to about 20GB before reaching wraparound."
**Counterexample:** Without the 10GB threshold triggering more aggressive scans, multixact storage could grow unchecked to the 20GB wraparound limit. At that point, new multixact IDs cannot be assigned, and any operation requiring row locking by multiple concurrent transactions fails — a partial write-path outage.
**Why this matters for bridge/orbit:** Orbit's concurrent dispatch model can generate multixacts when multiple sessions lock the same dispatch rows. If multixact storage wraparound occurs, orbit's locking operations fail but non-locking writes continue — a partial and hard-to-diagnose failure mode.

### INV-PGVAC-013: XID Wraparound Warning Threshold
**Core Invariant:**
```
∀ database d: when (wraparound_point - datfrozenxid) < 40,000,000:
  system emits WARNING log messages
  (Warning fires at 40M remaining, hard stop fires at 3M remaining — INV-PGVAC-003)
```
**Source:** Section 24.1.5 — "the system will begin to emit warning messages like this when the database's oldest XIDs reach forty million transactions from the wraparound point."
**Counterexample:** Without this warning, the first signal of trouble would be the hard stop at 3M transactions (INV-PGVAC-003) — which blocks all writes with no prior notice. The 40M warning gives operators a 37M-transaction window to intervene. This is observability as an invariant — the system guarantees a warning before the fatal condition.
**Why this matters for bridge/orbit:** Bridge and orbit monitoring should alert on these PostgreSQL WARNING log lines. Ignoring them means the first symptom is a hard write outage when the 3M threshold is crossed.

### INV-PGVAC-014: Autovacuum Cost Balancing Across Workers
**Core Invariant:**
```
∀ set W of autovacuum workers (using default cost settings):
  total I/O impact on system is constant, independent of |W|
  ⟹ cost parameters are balanced proportionally across running workers
```
**Source:** Section 24.1.6 — "the autovacuum cost delay parameters are 'balanced' among all the running workers, so that the total I/O impact on the system is the same regardless of the number of workers actually running."
**Counterexample:** Without cost balancing, adding more autovacuum workers would linearly increase I/O, creating a tradeoff between vacuum throughput and production query performance. With balancing, each worker gets cost_delay * |W|, so total throttling is constant. An operator can increase max_workers for throughput without fear of I/O overload.
**Why this matters for bridge/orbit:** Bridge and orbit share PostgreSQL with other services. The invariant means autovacuum I/O is predictable regardless of worker count, so the database's background maintenance load is bounded even as table count grows.

## Summary

Extracted 14 falsifiable invariants from the PostgreSQL Routine Vacuuming documentation. The invariants cluster into three categories:

1. **Liveness/Safety of the XID space (INV-001 through INV-007, INV-012, INV-013):** These are hard mathematical bounds on the 32-bit transaction ID and multixact ID spaces. They are the most critical invariants — violation means data loss.

2. **MVCC correctness (INV-008, INV-010):** These ensure that vacuum's row reclamation and the visibility map optimization never violate snapshot isolation. They are precondition invariants for correct query results.

3. **Operational guarantees (INV-009, INV-011, INV-014):** These govern lock behavior, autovacuum prerequisites, and I/O throttling. Violation means performance degradation or unavailability, not data loss.

All 14 invariants are directly relevant to bridge (ledger, session management) and orbit (dispatch, locking) because both systems rely on PostgreSQL for their core state.

Source trust: HIGH — PostgreSQL official documentation (version 18/current). The invariants describe documented system behavior, not implementation details that might change between minor versions. Each invariant is backed by specific configuration parameters and error messages that make them testable.
