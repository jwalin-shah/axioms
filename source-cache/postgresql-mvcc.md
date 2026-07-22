# oracle/postgresql-mvcc — MVCC and transaction isolation levels
Source: https://www.postgresql.org/docs/current/mvcc.html (Chapter 13, PostgreSQL 18.4)
Date pulled: 2026-07-21

This is a deep-dive extraction from the PostgreSQL concurrency control
documentation. The chapter covers MVCC architecture, the three implemented
isolation levels (Read Committed, Repeatable Read, Serializable via SSI),
explicit locking, application-level consistency enforcement, serialization
failure handling, caveats, and index locking behavior.

Source trust level: HIGH (textbook-formal — PostgreSQL documentation is the
authoritative reference for PostgreSQL behavior, maintained by the PostgreSQL
Global Development Group, extensively peer-reviewed).

---

## Extracted Invariants

### INV-PGMVCC-001: MVCC non-blocking read/write guarantee
**Core Invariant:**
```
∀ readers r, writers w operating on same relation:
  r acquires no lock that conflicts with w's lock ∧
  w acquires no lock that conflicts with r's lock
⇒ reading never blocks writing ∧ writing never blocks reading
```
**Source:** Section 13.1 Introduction. "In MVCC, locks acquired for querying (reading) data do not conflict with locks acquired for writing data, and so reading never blocks writing and writing never blocks reading. PostgreSQL maintains this guarantee even when providing the strictest level of transaction isolation through the use of an innovative Serializable Snapshot Isolation (SSI) level."
**Counterexample:** A long-running SELECT under table-level read locks (as in traditional 2PL databases) would block all UPDATE/INSERT/DELETE operations on that table, starving writers indefinitely. Conversely, a large UPDATE holding exclusive locks would block all readers. MVCC eliminates this class of contention entirely.
**Why this matters for bridge/orbit:** Bridge's knowledge engine and orbit's dispatch loop both perform concurrent reads and writes. This invariant guarantees that audit queries (reads) never stall dispatch operations (writes) and vice versa, even under Serializable isolation. If this were violated, bridge's context assembly could deadlock against orbit's session writes.

---

### INV-PGMVCC-002: Read Committed snapshot boundary
**Core Invariant:**
```
∀ SELECT query q (without FOR UPDATE/SHARE) executing at Read Committed:
  visible_rows(q) = {row | committed(row, t_commit) ∧ t_commit < t_start(q)}
  ∧ ∀ row ∈ visible_rows(q): ¬∃ concurrent_commit(row, t') where t_start(q) ≤ t' ≤ t_end(q)
```
**Source:** Section 13.2.1. "A SELECT query (without a FOR UPDATE/SHARE clause) sees only data committed before the query began; it never sees either uncommitted data or changes committed by concurrent transactions during the query's execution."
**Counterexample:** A SELECT counting account balances midway through a concurrent transfer would see money debited from one account but not yet credited to another, breaking double-entry accounting. The snapshot boundary prevents this per-statement inconsistency.
**Why this matters for bridge/orbit:** Bridge's context assembly queries must never see partially-committed state from orbit's session writes. Read Committed's per-statement snapshot ensures each context fetch sees a point-in-time consistent view, though successive fetches may differ.

---

### INV-PGMVCC-003: Repeatable Read snapshot stability
**Core Invariant:**
```
∀ transaction T at Repeatable Read:
  let t_snapshot = time_of_first_statement(T)
  ∀ SELECT q1, q2 ∈ T:
    visible_rows(q1) = visible_rows(q2) = {row | committed(row, t) ∧ t < t_snapshot}
  ⇒ no non-repeatable reads, no phantom reads within T
```
**Source:** Section 13.2.2. "A query in a repeatable read transaction sees a snapshot as of the start of the first non-transaction-control statement in the transaction, not as of the start of the current statement. Thus, successive SELECT commands within a single transaction see the same data."
**Counterexample:** Without this invariant, a transaction reading a control record to verify batch completion could see the "batch done" flag set but not see the detail records that were committed concurrently — the batch would appear complete yet have missing detail rows. This is the classic write-skew anomaly under snapshot isolation.
**Why this matters for bridge/orbit:** Orbit's multi-step session dispatch (validate, sandbox, execute, record) runs within a transaction. Repeatable Read ensures that the sandbox configuration seen at validation is identical to the configuration at execution time — no TOCTOU gap where configuration changes between steps.

---

### INV-PGMVCC-004: Repeatable Read first-committer-wins conflict detection
**Core Invariant:**
```
∀ transaction T_rr at Repeatable Read, row r:
  if another transaction T_other commits a modification to r after t_snapshot(T_rr):
    T_rr's attempt to UPDATE/DELETE/LOCK r ⇒ serialization_failure (SQLSTATE 40001)
```
**Source:** Section 13.2.2. "If the first updater commits (and actually updated or deleted the row, not just locked it) then the repeatable read transaction will be rolled back with the message 'could not serialize access due to concurrent update'."
**Counterexample:** Without this check, two concurrent Repeatable Read transactions could both read row X (value=10), then each try to increment it. Both would write value=11, losing one increment. This is the lost-update anomaly. PostgreSQL detects this via first-committer-wins: the second committer is rolled back.
**Why this matters for bridge/orbit:** Orbit's ledger updates (non-repudiable audit trail) must never lose writes. If two orbit instances concurrently append to the same session ledger, one must detect the conflict and retry rather than silently overwriting. This invariant is the detection mechanism.

---

### INV-PGMVCC-005: Serializable true-serializability guarantee
**Core Invariant:**
```
∀ set of committed Serializable transactions S = {T1, ..., Tn}:
  ∃ permutation π of [1..n] such that:
    effect(commit(S)) = effect(serial_execute(T_π(1), ..., T_π(n)))
  ⇒ no serialization anomalies in any committed Serializable transaction
```
**Source:** Section 13.2.3. "The Serializable isolation level provides the strictest transaction isolation. This level emulates serial transaction execution for all committed transactions; as if transactions had been executed one after another, serially, rather than concurrently."
**Counterexample:** Two Serializable transactions each computing SUM of disjoint subsets and inserting the result — if both see the pre-insertion state and both commit, no serial order explains the result. PostgreSQL's SSI detects the rw-dependency cycle and rolls one back. Without this, integrity constraints spanning multiple rows (e.g., "total credits = total debits") become unenforceable.
**Why this matters for bridge/orbit:** Bridge's knowledge engine maintains derived invariants aggregated across multiple axiom verifications. If two concurrent verifications read overlapping axiom sets and write conflicting conclusions, Serializable isolation guarantees one serial order exists — the knowledge graph cannot enter an impossible state.

---

### INV-PGMVCC-006: Serializable predicate locks are non-blocking
**Core Invariant:**
```
∀ SIReadLock l held by Serializable transaction T:
  l does not block any other transaction's progress
  ∧ l cannot participate in any deadlock cycle
```
**Source:** Section 13.2.3. "In PostgreSQL these locks do not cause any blocking and therefore can not play any part in causing a deadlock. They are used to identify and flag dependencies among concurrent Serializable transactions which in certain combinations can lead to serialization anomalies."
**Counterexample:** If predicate locks blocked (like traditional 2PL), Serializable isolation would be unusable in high-concurrency environments — every read would acquire locks that block writers, and deadlocks would be routine. The non-blocking property means SSI adds overhead (rw-dependency tracking) but never reduces concurrency below Repeatable Read levels.
**Why this matters for bridge/orbit:** Bridge's knowledge engine can run Serializable transactions for consistency without risk of deadlocking against orbit's dispatch writes. The separation of correctness (predicate locks) from liveness (no blocking) is the architectural insight that makes SSI practical.

---

### INV-PGMVCC-007: Read Committed UPDATE re-evaluation (Eval-on-Update)
**Core Invariant:**
```
∀ UPDATE/DELETE command c at Read Committed:
  if target row r was concurrently modified by T_other that committed:
    let r' = updated_version(r, T_other)
    if eval(WHERE_clause(c), r') = true: apply c to r'
    else: skip r'
```
**Source:** Section 13.2.1. "The search condition of the command (the WHERE clause) is re-evaluated to see if the updated version of the row still matches the search condition. If so, the second updater proceeds with its operation using the updated version of the row."
**Counterexample:** Without re-evaluation, a DELETE WHERE hits > 10 would delete a row that was concurrently updated from hits=9 to hits=11 (the pre-update value 9 wouldn't match, but the post-update value 11 should). With re-evaluation, the row is correctly deleted. Without it, the row survives despite now matching the condition — a silent correctness bug.
**Why this matters for bridge/orbit:** Bridge's axiom verification pipeline may concurrently update verdict fields. If two verification agents process related axioms simultaneously, the re-evaluation invariant ensures WHERE conditions are checked against the latest committed state, preventing stale-condition updates.

---

### INV-PGMVCC-008: Serialization failure always SQLSTATE 40001
**Core Invariant:**
```
∀ error raised due to serialization anomaly detection:
  error.SQLSTATE = '40001' (serialization_failure)
```
**Source:** Section 13.5. "Such an error's message text will vary according to the precise circumstances, but it will always have the SQLSTATE code 40001 (serialization_failure)."
**Counterexample:** If serialization failures returned arbitrary error codes, retry logic would be unreliable — the application couldn't distinguish between a transient conflict (safe to retry) and a persistent error (retry would waste resources or loop forever). The stable error code is a contract.
**Why this matters for bridge/orbit:** Bridge and orbit both need retry loops around Serializable transactions. The invariant that conflict = 40001 means retry logic can be simple: catch 40001, exponential backoff, re-execute. Any other error code is not a serialization conflict and should be handled differently.

---

### INV-PGMVCC-009: Sequence values escape transactional semantics
**Core Invariant:**
```
∀ sequence S, transaction T that calls nextval(S):
  value = nextval(S) is immediately visible to ALL other transactions
  ∧ ¬rollback(value) when T aborts
```
**Source:** Section 13.2. "Changes made to a sequence (and therefore the counter of a column declared using serial) are immediately visible to all other transactions and are not rolled back if the transaction that made the changes aborts."
**Counterexample:** If sequence values were transactional (rolled back on abort), concurrent INSERTs could receive the same sequence value after a rollback, violating uniqueness. The non-transactional behavior is a deliberate trade-off: gaps in sequences are acceptable, duplicate keys are not.
**Why this matters for bridge/orbit:** If bridge uses SERIAL primary keys for audit log entries, aborted transactions will leave gaps in the ID sequence. Consumers of the audit log must never assume gapless, monotonic IDs. Gap detection is not an error condition.

---

### INV-PGMVCC-010: TRUNCATE/table-rewrite ALTER TABLE are non-MVCC-safe
**Core Invariant:**
```
∀ DDL command d ∈ {TRUNCATE, table-rewriting ALTER TABLE}:
  ∀ concurrent transaction T_concurrent with snapshot taken before commit(d):
    effect(T_concurrent, table) = table_appears_empty
  ⇒ visible inconsistency between target table and other tables in the database
```
**Source:** Section 13.6. "Some DDL commands, currently only TRUNCATE and the table-rewriting forms of ALTER TABLE, are not MVCC-safe. This means that after the truncation or rewrite commits, the table will appear empty to concurrent transactions, if they are using a snapshot taken before the DDL command committed."
**Counterexample:** A long-running Repeatable Read transaction that read table A (populated) and table B (empty) before a TRUNCATE on A — after the TRUNCATE commits, table A appears empty to the transaction, contradicting its earlier observation that A had rows. The snapshot is violated for DDL-affected tables.
**Why this matters for bridge/orbit:** Orbit must never TRUNCATE a session table while bridge holds a Repeatable Read snapshot for context assembly. If bridge's snapshot predates the TRUNCATE, it will see an empty table where rows previously existed — a silent data consistency violation in the knowledge assembly.

---

### INV-PGMVCC-011: System catalog visibility anomaly under Repeatable Read/Serializable
**Core Invariant:**
```
∀ database object O created by transaction T_create:
  ∀ concurrent Repeatable Read or Serializable transaction T_concurrent:
    internal_access(T_concurrent, O) ⇒ O is visible
    ∧ explicit_query(T_concurrent, pg_class WHERE relname = O.name) ⇒ O is NOT visible
  ⇒ metadata visibility is inconsistent within T_concurrent
```
**Source:** Section 13.6. "Internal access to the system catalogs is not done using the isolation level of the current transaction. This means that newly created database objects such as tables are visible to concurrent Repeatable Read and Serializable transactions, even though the rows they contain are not."
**Counterexample:** A Serializable transaction might successfully INSERT into a newly created table (internal access sees it) but fail to SELECT from pg_class to verify the table exists (explicit query doesn't see it). The transaction simultaneously "knows" and "doesn't know" about the table — a paradox for metadata-driven logic.
**Why this matters for bridge/orbit:** Bridge's knowledge engine populates schema metadata via system catalog queries. If orbit creates a new relation type during a bridge snapshot, bridge's metadata queries won't see it but internal operations will. Metadata-driven dispatch decisions must account for this split visibility.

---

### INV-PGMVCC-012: B-tree index nonblocking concurrency guarantee
**Core Invariant:**
```
∀ B-tree index I:
  ∀ read/write operations on I:
    locks held are short-term share/exclusive page-level locks
    ∧ locks are released immediately after each index row fetch/insert
  ⇒ no deadlock conditions possible through B-tree index operations
```
**Source:** Section 13.7. "Short-term share/exclusive page-level locks are used for read/write access. Locks are released immediately after each index row is fetched or inserted. These index types provide the highest concurrency without deadlock conditions."
**Counterexample:** If B-tree operations held locks across multiple row accesses (index-level or bucket-level locks, as hash indexes do), concurrent index scans and inserts could deadlock — an index scan holding a shared lock on page P1 waiting for P2, while an insert holds exclusive on P2 waiting for P1.
**Why this matters for bridge/orbit:** Bridge's knowledge graph and orbit's session tables both use B-tree indexes. The nonblocking guarantee means index-heavy workloads (range scans during context assembly, unique lookups during dispatch) will never deadlock at the index level. Deadlocks can only arise from explicit row-level or table-level locks.

---

### INV-PGMVCC-013: Hash index deadlock possibility
**Core Invariant:**
```
∀ Hash index I:
  locks held are share/exclusive hash-bucket-level locks
  ∧ locks are released only after the whole bucket is processed
  ⇒ deadlock is possible between concurrent Hash index operations
```
**Source:** Section 13.7. "Share/exclusive hash-bucket-level locks are used for read/write access. Locks are released after the whole bucket is processed. Bucket-level locks provide better concurrency than index-level ones, but deadlock is possible since the locks are held longer than one index operation."
**Counterexample:** Two concurrent transactions each needing two hash buckets in opposite order: T1 holds shared lock on bucket A, waits for bucket B; T2 holds shared lock on bucket B, waits for bucket A. Classic deadlock. B-tree avoids this by releasing locks between individual row operations.
**Why this matters for bridge/orbit:** Bridge/orbit should default to B-tree indexes for all scalar-keyed tables. Hash indexes should only be used where the bucket-level concurrency benefit outweighs the deadlock risk and where access patterns are single-bucket (point queries only, no range scans).

---

### INV-PGMVCC-014: SELECT FOR UPDATE temporal-only protection
**Core Invariant:**
```
∀ row r locked by SELECT FOR UPDATE in transaction T:
  ∀ concurrent transaction T_other:
    T_other is blocked from UPDATE/DELETE/SELECT FOR UPDATE on r while T is active
    ∧ after T commits or rolls back: T_other can proceed with UPDATE/DELETE on r
      UNLESS T performed an actual UPDATE of r
```
**Source:** Section 13.4.2. "SELECT FOR UPDATE temporarily blocks other transactions from acquiring the same lock or executing an UPDATE or DELETE which would affect the locked row, but once the transaction holding this lock commits or rolls back, a blocked transaction will proceed with the conflicting operation unless an actual UPDATE of the row was performed while the lock was held."
**Counterexample:** An application using SELECT FOR UPDATE to "reserve" a row for later update, then performing computations outside the transaction before updating — a concurrent transaction could update and commit the row in between, and the original transaction's subsequent UPDATE would see a modified row (or trigger a serialization failure under Repeatable Read). The lock protects only while held; it does not reserve the row across transaction boundaries.
**Why this matters for bridge/orbit:** Orbit's resource allocation (sandbox assignment) cannot rely on SELECT FOR UPDATE as a reservation mechanism across transaction boundaries. If orbit selects a sandbox "for update," computes eligibility externally, then re-enters a transaction to claim it, the sandbox may already be assigned. Allocation must be atomic within a single transaction.

---

### INV-PGMVCC-015: Deferrable read-only Serializable snapshot validity
**Core Invariant:**
```
∀ DEFERRABLE READ ONLY Serializable transaction T:
  T blocks at startup until it can acquire a snapshot S such that:
    S is guaranteed free from serialization anomalies
    ⇒ all data read within T is known-valid at read time
```
**Source:** Section 13.2.3. "Data read within a deferrable read-only transaction is known to be valid as soon as it is read, because such a transaction waits until it can acquire a snapshot guaranteed to be free from such problems before starting to read any data."
**Counterexample:** A non-deferrable read-only Serializable transaction may read data, compute derived results, and only discover at COMMIT time that the snapshot was part of a serialization anomaly — all computation is wasted work. The deferrable variant trades startup latency for guaranteed-valid reads, eliminating wasted computation.
**Why this matters for bridge/orbit:** Bridge's knowledge engine could use DEFERRABLE READ ONLY Serializable transactions for long-running analytical queries (axiom cross-validation, dependency graph traversal). The startup wait ensures all read data is consistent; no risk of computing derived invariants from an inconsistent snapshot.

---

### INV-PGMVCC-016: MERGE does not retry on concurrent uniqueness violation
**Core Invariant:**
```
∀ MERGE command with INSERT action at Read Committed:
  if a unique index exists and a duplicate row is concurrently inserted by T_other:
    MERGE raises uniqueness_violation (SQLSTATE 23505)
    ∧ MERGE does NOT restart evaluation of MATCHED conditions
```
**Source:** Section 13.2.1. "If MERGE attempts an INSERT and a unique index is present and a duplicate row is concurrently inserted, then a uniqueness violation error is raised; MERGE does not attempt to avoid such errors by restarting evaluation of MATCHED conditions."
**Counterexample:** Contrast with INSERT ON CONFLICT DO UPDATE, which guarantees exactly one of INSERT or UPDATE succeeds. MERGE offers no such guarantee — a concurrent insert can cause MERGE to fail with a uniqueness violation rather than falling through to an UPDATE action. Applications using MERGE for upsert semantics must handle 23505 as a retryable error.
**Why this matters for bridge/orbit:** If bridge uses MERGE for idempotent axiom ingestion (insert if new, update if exists), concurrent ingestion of the same axiom by two pipeline workers can cause uniqueness violations rather than graceful merges. The retry loop must catch 23505 alongside 40001.

---

## Summary Statistics

- 16 invariants extracted
- 11 from Section 13.2 (Transaction Isolation)
- 2 from Section 13.4 (Application-Level Consistency)
- 1 from Section 13.5 (Serialization Failure Handling)
- 2 from Section 13.6 (Caveats)
- 2 from Section 13.7 (Locking and Indexes)
- 1 from Section 13.1 (Introduction)
- Source trust: HIGH (authoritative PostgreSQL documentation)
- All invariants are falsifiable: each specifies a concrete observable behavior and a counterexample condition

## Key Architectural Insights

1. **MVCC is the foundation**: All isolation guarantees derive from the snapshot model. The invariant "reads never block writes, writes never block reads" is the architectural axiom from which everything else follows.

2. **SSI layers on Snapshot Isolation**: PostgreSQL's Serializable = Repeatable Read + nonblocking rw-dependency monitoring. The predicate locks (SIReadLocks) detect anomalies without reducing concurrency — a qualitative leap over traditional 2PL.

3. **Isolation levels are contracts about snapshot recency**: Read Committed = per-statement snapshots, Repeatable Read = per-transaction snapshots, Serializable = per-transaction snapshots with anomaly detection. The snapshots are always consistent within themselves; the difference is when they're taken and whether conflicts between snapshots are detected.

4. **Deliberate exceptions exist**: Sequence values and TRUNCATE deliberately violate MVCC semantics for specific engineering reasons (uniqueness preservation and implementation complexity, respectively). These are documented as features, not bugs — but they are traps for the unwary.

5. **Error codes are the retry contract**: SQLSTATE 40001 (serialization_failure) is the universal signal for "retry this transaction." SQLSTATE 40P01 (deadlock_detected) and 23505 (unique_violation) may also be retryable but require more care. This triage logic is load-bearing for any application using Serializable isolation.
