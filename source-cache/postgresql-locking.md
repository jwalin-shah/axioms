# oracle/postgresql-locking — Lock management, deadlock detection, lock ordering

Source: https://www.postgresql.org/docs/current/explicit-locking.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-PGLOCK-001: Table-level lock conflict exclusion
**Core Invariant:**
```
∀ t1, t2 ∈ active_transactions, ∀ table T, ∀ lock_modes m1, m2:
  (holds(t1, T, m1) ∧ holds(t2, T, m2) ∧ t1 ≠ t2)
  ⇒ ¬conflicts(m1, m2)
```
**Source:** Section 13.3.1, para 1 — "Two transactions cannot hold locks of conflicting modes on the same table at the same time."
**Counterexample:** If txn A holds ACCESS EXCLUSIVE on table X and txn B tries to acquire ACCESS SHARE on table X, B blocks until A commits. If the system allowed both, B could read data that A is in the middle of dropping/truncating, yielding undefined results.
**Why this matters for bridge/orbit:** Orbit's dispatch model acquires table-level locks for session isolation. Any code path that acquires two locks of different modes on the same table in nested scopes must not violate the conflict matrix. The conflict matrix in Table 13.2 is the ground truth.

### INV-PGLOCK-002: Row-level lock conflict exclusion
**Core Invariant:**
```
∀ t1, t2 ∈ active_transactions, ∀ row R, ∀ row_lock_modes m1, m2:
  (holds(t1, R, m1) ∧ holds(t2, R, m2) ∧ t1 ≠ t2)
  ⇒ ¬row_conflicts(m1, m2)
```
**Source:** Section 13.3.2, para 1 — "Two transactions can never hold conflicting locks on the same row."
**Counterexample:** If txn A holds FOR UPDATE on row R and txn B holds FOR UPDATE on row R simultaneously, both could modify the row in an interleaved manner, breaking write isolation. Row-level deadlock in the bank transfer example (13.3.4) is the direct counterexample: unordered row acquisition yields mutually waiting transactions.
**Why this matters for bridge/orbit:** Orbit operations that mutate session state rows must acquire row locks in a consistent global order (e.g., by session ID ascending). Otherwise, concurrent dispatch sessions deadlock.

### INV-PGLOCK-003: Row locks only block writers, never readers
**Core Invariant:**
```
∀ txn_reader, txn_writer, ∀ row R:
  (holds(txn_writer, R, FOR_UPDATE) ∧ txn_reader executes SELECT R)
  ⇒ txn_reader proceeds without blocking
```
**Source:** Section 13.3.2, para 1 — "Row-level locks do not affect data querying; they block only writers and lockers to the same row."
**Counterexample:** If row-level FOR UPDATE blocked plain SELECT, every concurrent read of a locked row would stall until the writer commits — turning MVCC's non-blocking reads into blocking reads and collapsing throughput.
**Why this matters for bridge/orbit:** Bridge's read path (knowledge queries) must not be blocked by orbit's write path (session state mutations). This invariant is guaranteed by PostgreSQL; bridge/orbit must not inadvertently break it by using FOR UPDATE on read-heavy tables.

### INV-PGLOCK-004: Lock held until transaction end
**Core Invariant:**
```
∀ locks l acquired by transaction t:
  release_time(l) ∈ {commit(t), rollback(t), rollback_to_savepoint(t, sp) where sp ≤ acquisition(l)}
```
**Source:** Section 13.3.1, para after lock mode list — "Once acquired, a lock is normally held until the end of the transaction." + "But if a lock is acquired after establishing a savepoint, the lock is released immediately if the savepoint is rolled back to."
**Counterexample:** If locks were released mid-transaction, another txn could observe an intermediate state that was never committed (dirty read), or the original txn could observe changes made by the second txn under a lock it thought it still held.
**Why this matters for bridge/orbit:** Any long-running transaction in orbit that acquires locks and then performs I/O (network call, file read) violates PostgreSQL best practice. Keep transactions short. If orbit holds a lock across a Claude API call, it blocks all conflicting operations for potentially minutes.

### INV-PGLOCK-005: Self-conflict is impossible
**Core Invariant:**
```
∀ t ∈ transactions, ∀ lock_mode m1, m2:
  (holds(t, T, m1) ⇒ can_acquire(t, T, m2))
```
**Source:** Section 13.3.1, para 1 — "a transaction never conflicts with itself. For example, it might acquire ACCESS EXCLUSIVE lock and later acquire ACCESS SHARE lock on the same table."
**Counterexample:** If self-conflict were possible, a single transaction doing DDL (ACCESS EXCLUSIVE) followed by a read (ACCESS SHARE) on the same table would deadlock against itself. The system would become unusable for any multi-step operation on the same table.
**Why this matters for bridge/orbit:** Code reviews must not flag lock upgrades within a single transaction as bugs — they're safe by design. However, lock upgrades across *different* objects can still participate in cross-transaction deadlocks.

### INV-PGLOCK-006: FOR UPDATE on changed row errors under SERIALIZABLE
**Core Invariant:**
```
∀ t ∈ transactions with isolation ∈ {REPEATABLE_READ, SERIALIZABLE},
  ∀ row R read by t in a SELECT FOR UPDATE:
  (version(R, t.snapshot_start) ≠ version(R, now))
  ⇒ error_raised(t, "could not serialize access")
```
**Source:** Section 13.3.2, FOR UPDATE description — "Within a REPEATABLE READ or SERIALIZABLE transaction, however, an error will be thrown if a row to be locked has changed since the transaction started."
**Counterexample:** Without this check, a SERIALIZABLE txn doing SELECT FOR UPDATE could lock and return a row that was modified by a concurrent txn after the snapshot was taken — a write skew anomaly. The error forces the application to retry, preserving serializability.
**Why this matters for bridge/orbit:** If orbit runs operations at SERIALIZABLE (necessary for multi-row invariants), any concurrent mutation to a row orbit intends to lock causes an immediate error, not a silent inconsistency. Retry logic must handle serialization failures via savepoint rollback and re-execution.

### INV-PGLOCK-007: Deadlock detection is guaranteed
**Core Invariant:**
```
∀ wait-for-graph G across transactions:
  (G contains a cycle) ⇒ (postgresql detects ∧ aborts at least one t in cycle)
```
**Source:** Section 13.3.4, para 1 — "PostgreSQL automatically detects deadlock situations and resolves them by aborting one of the transactions involved."
**Counterexample:** Without deadlock detection, the bank transfer example (two txns updating rows in opposite order) would hang indefinitely, consuming connections and locks until the connection pool is exhausted. This is a liveness failure.
**Why this matters for bridge/orbit:** The detection exists, but the resolution is non-deterministic — "Exactly which transaction will be aborted is difficult to predict and should not be relied upon." Orbit must not depend on a specific txn being the victim. Any critical-path operation must be retry-safe.

### INV-PGLOCK-008: Lock wait is unbounded in absence of deadlock
**Core Invariant:**
```
∀ t ∈ transactions waiting for lock L, ∀ time τ:
  (¬deadlock_detected(t)) ⇒ t continues waiting
```
**Source:** Section 13.3.4, para 4 — "So long as no deadlock situation is detected, a transaction seeking either a table-level or row-level lock will wait indefinitely for conflicting locks to be released."
**Counterexample:** A long-running analytics query holding ACCESS SHARE on a table blocks a DROP TABLE (ACCESS EXCLUSIVE) until the query finishes. If the query runs for hours, the DROP waits for hours. This is a liveness hazard — not a correctness bug, but a system availability issue.
**Why this matters for bridge/orbit:** Orbit must set `lock_timeout` on any DDL operations. A migration that blocks indefinitely behind a long-running read query can take the system down. This is also why advisory locks need care: a leaked session-level advisory lock blocks forever.

### INV-PGLOCK-009: Advisory lock self-grant always succeeds
**Core Invariant:**
```
∀ session s, ∀ advisory_lock_id id:
  holds(s, id) ⇒ acquire(s, id) == immediate_success
```
**Source:** Section 13.3.5, para 3 — "If a session already holds a given advisory lock, additional requests by it will always succeed, even if other sessions are awaiting the lock; this statement is true regardless of whether the existing lock hold and new request are at session level or transaction level."
**Counterexample:** If re-acquisition blocked, a session that holds an advisory lock and tries to re-acquire it (e.g., nested function calls) would deadlock against itself if another session was queued for the same lock. This would make advisory locks unusable in reentrant code.
**Why this matters for bridge/orbit:** Orbit can safely call `pg_advisory_lock` in nested contexts without risk of self-deadlock. However, this also means advisory locks provide no reentrancy guard — if orbit accidentally acquires the same lock twice in different code paths, the second acquisition silently succeeds and the lock is held until both are released (session-level) or transaction end (txn-level).

### INV-PGLOCK-010: Lock memory is finite and bounded
**Core Invariant:**
```
∀ granted_locks G:
  |G| ≤ max_locks_per_transaction × max_connections + additional_shared_memory
```
**Source:** Section 13.3.5, para 5 — "Both advisory locks and regular locks are stored in a shared memory pool whose size is defined by the configuration variables max_locks_per_transaction and max_connections. Care must be taken not to exhaust this memory or the server will be unable to grant any locks at all."
**Counterexample:** Exhausting the lock table causes the server to refuse ALL new lock acquisitions — not just advisory locks. Every new transaction, every SELECT, every UPDATE fails with "out of shared memory." This is a full denial-of-service condition, not a graceful degradation.
**Why this matters for bridge/orbit:** If orbit uses advisory locks per-session and has 10,000 concurrent sessions, it must verify that `max_locks_per_transaction` is tuned accordingly. The "tens to hundreds of thousands" ceiling is a hard system limit, not a guideline.

### INV-PGLOCK-011: Session-level advisory locks survive rollback
**Core Invariant:**
```
∀ session s, ∀ advisory_lock_id id, ∀ transaction t in s:
  acquire_session_level(s, id) during t ∧ rollback(t)
  ⇒ holds(s, id) after rollback
```
**Source:** Section 13.3.5, para 2 — "session-level advisory lock requests do not honor transaction semantics: a lock acquired during a transaction that is later rolled back will still be held following the rollback."
**Counterexample:** If an application uses session-level advisory locks as a mutex, acquires the lock, does work, hits an error, and rolls back the transaction — the lock is still held. If the application doesn't explicitly release it, no other session can acquire that lock until the session disconnects. This is a silent resource leak.
**Why this matters for bridge/orbit:** Orbit must prefer transaction-level advisory locks (`pg_advisory_xact_lock`) for any mutex that should release on error. Session-level locks are for cross-transaction coordination (e.g., "only one deployment at a time" across multiple txns in the same session).

### INV-PGLOCK-012: Consistent lock ordering prevents deadlock
**Core Invariant:**
```
∀ transactions t1, t2, ∀ objects A, B:
  (order(t1, A) < order(t1, B) ∧ order(t2, A) < order(t2, B))
  ⇒ ¬deadlock(t1, t2) over {A, B}
```
**Source:** Section 13.3.4, para 3 — "The best defense against deadlocks is generally to avoid them by being certain that all applications using a database acquire locks on multiple objects in a consistent order."
**Counterexample:** The bank transfer deadlock (txn1: lock row 11111 → lock row 22222; txn2: lock row 22222 → lock row 11111) creates a cycle in the wait-for graph. If both had locked rows in ascending account-number order, txn2 would have blocked on txn1's lock on 11111 before acquiring any locks, and no cycle would form.
**Why this matters for bridge/orbit:** Every code path in orbit that touches multiple rows, tables, or advisory locks must follow the same global ordering. The consistent-order invariant is a design constraint, not a runtime check — it must be verified at code review time.

### INV-PGLOCK-013: Most restrictive lock first
**Core Invariant:**
```
∀ t ∈ transactions, ∀ object O, ∀ lock_modes m1 first, m2 later:
  acquire(t, O, m1) followed by acquire(t, O, m2)
  ⇒ mode_strength(m1) ≥ mode_strength(m2)
  (recommended: take the strongest lock you'll need up front)
```
**Source:** Section 13.3.4, para 3 — "One should also ensure that the first lock acquired on an object in a transaction is the most restrictive mode that will be needed for that object."
**Counterexample:** If txn A acquires ACCESS SHARE on table T and later tries to upgrade to ACCESS EXCLUSIVE, the upgrade blocks behind any concurrent ACCESS SHARE holders — including one held by a slow reader. Worse, if txn B also holds ACCESS SHARE and tries the same upgrade, both deadlock: each wants EXCLUSIVE but holds SHARE, and neither can proceed because SHARE conflicts with EXCLUSIVE.
**Why this matters for bridge/orbit:** Orbit's DDL operations (schema migrations, index creation) must acquire the target lock level immediately, not start with a weak lock and escalate. Lock escalation is a deadlock hazard.

## Conflict Matrices

### Table-Level Lock Conflict Matrix (Table 13.2)

Rows are requested lock modes, columns are existing (held) lock modes. X = conflict.

| Requested \ Existing | ACS | RS | RE | SUE | S | SRE | E | AE |
|---|---|---|---|---|---|---|---|---|
| ACCESS SHARE | | | | | | | | X |
| ROW SHARE | | | | | | | X | X |
| ROW EXCLUSIVE | | | | | X | X | X | X |
| SHARE UPDATE EXCL | | | | X | X | X | X | X |
| SHARE | | | X | X | | X | X | X |
| SHARE ROW EXCL | | | X | X | X | X | X | X |
| EXCLUSIVE | | X | X | X | X | X | X | X |
| ACCESS EXCLUSIVE | X | X | X | X | X | X | X | X |

### Row-Level Lock Conflict Matrix (Table 13.3)

| Requested \ Current | FKS | FS | FNKU | FU |
|---|---|---|---|---|
| FOR KEY SHARE | | | | X |
| FOR SHARE | | | X | X |
| FOR NO KEY UPDATE | | X | X | X |
| FOR UPDATE | X | X | X | X |

## Relevance Summary for Bridge/Orbit

1. **Orbit session isolation** depends on INV-PGLOCK-001 and INV-PGLOCK-002 (lock conflict exclusion). If orbit's dispatch model uses table-level or row-level locks, the conflict matrix in Table 13.2 is the contract.
2. **Read path non-blocking** (INV-PGLOCK-003): Bridge's knowledge queries must use plain SELECT, never SELECT FOR UPDATE, to avoid blocking behind orbit's write locks.
3. **Deadlock prevention by ordering** (INV-PGLOCK-012, INV-PGLOCK-013): Orbit's multi-step operations must follow a globally consistent lock ordering. This is the single most important design constraint — failure here yields non-deterministic deadlocks at runtime.
4. **Serializable safety** (INV-PGLOCK-006): If orbit uses SERIALIZABLE, all lock acquisitions on rows that changed since snapshot start will error. Retry loops must be correct and bounded.
5. **Resource bounds** (INV-PGLOCK-010): Advisory lock ceiling is a hard limit. Orbit must budget `max_locks_per_transaction` against peak concurrent sessions.
6. **Advisory lock semantics** (INV-PGLOCK-009, INV-PGLOCK-011): Session-level vs transaction-level choice matters. Wrong choice = silent resource leaks or self-deadlock.
