# oracle/sqlite-locking — Locking and concurrency: shared, reserved, pending, exclusive
Source: https://sqlite.org/lockingv3.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-SQLITE-LOCK-001: Lock state machine — mutual exclusion
**Core Invariant:**
```
∀ p, q ∈ processes, ∀ db ∈ databases:
  (lock_state(p, db) = EXCLUSIVE) ⇒ ¬∃ q ≠ p : lock_state(q, db) ≠ UNLOCKED
```
**Source:** Section 3.0 (Locking), EXCLUSIVE definition: "Only one EXCLUSIVE lock is allowed on the file and no other locks of any kind are allowed to coexist with an EXCLUSIVE lock."
**Counterexample:** Two processes both hold EXCLUSIVE locks on the same database file. Concurrent writes interleave, corrupting pages. If one process holds EXCLUSIVE and another holds SHARED, the reader sees partially-written pages.
**Why this matters for bridge/orbit:** Orbit dispatches sandboxed processes that may each open SQLite databases. If two sandboxes accidentally share a database file without proper locking, orbit's own dispatch isolation invariant is violated. Bridge's ledger integrity depends on exclusive access to its state database.

### INV-SQLITE-LOCK-002: RESERVED lock uniqueness
**Core Invariant:**
```
∀ t1, t2 ∈ transactions, ∀ db ∈ databases:
  lock_state(t1, db) = RESERVED ⇒ ¬∃ t2 ≠ t1 : lock_state(t2, db) = RESERVED
```
**Source:** Section 3.0 (Locking), RESERVED definition: "Only a single RESERVED lock may be active at one time, though multiple SHARED locks can coexist with a single RESERVED lock."
**Counterexample:** Two transactions both acquire RESERVED locks. Both create rollback journals independently. Both write original page contents to their respective journals. When one commits, its journal is deleted; the other commits, its journal is deleted too, but the database now contains the second writer's changes without the first writer's journal being rolled back. The first writer's changes are lost and the database is left in an inconsistent state.
**Why this matters for bridge/orbit:** Bridge's commit sequence must be serialized. If bridge spawns concurrent write operations that both try to RESERVE the same database, one must get SQLITE_BUSY and retry — not silently proceed.

### INV-SQLITE-LOCK-003: PENDING lock blocks new readers
**Core Invariant:**
```
∀ p ∈ processes, ∀ db ∈ databases:
  lock_state(p, db) = PENDING ⇒ ¬∃ q : can_acquire(q, db, SHARED)
```
**Source:** Section 3.0 (Locking), PENDING definition: "No new SHARED locks are permitted against the database if a PENDING lock is active, though existing SHARED locks are allowed to continue."
**Counterexample:** A writer holds PENDING but new readers are admitted. The set of SHARED locks never drains to zero. The writer never acquires EXCLUSIVE. Writer starvation — the database is permanently read-only.
**Why this matters for bridge/orbit:** Bridge's audit workflow must eventually write findings. If bridge's reader connections never drain, bridge's writer starves. The PENDING lock semantics guarantee forward progress for writers as long as readers eventually terminate.

### INV-SQLITE-LOCK-004: Lock upgrade ordering
**Core Invariant:**
```
∀ t ∈ transactions, ∀ db ∈ databases:
  can_write(t, db) ⇒ lock_state(t, db) must follow path:
    UNLOCKED → SHARED → RESERVED → PENDING → EXCLUSIVE
```
**Source:** Section 5.0 (Writing to a database file): "To write to a database, a process must first acquire a SHARED lock... After a SHARED lock is obtained, a RESERVED lock must be acquired." Section 3.0: "A PENDING lock is always just a temporary stepping stone on the path to an EXCLUSIVE lock."
**Counterexample:** A process jumps directly from UNLOCKED to EXCLUSIVE without passing through RESERVED. If another process holds SHARED, the EXCLUSIVE acquisition violates INV-001. If the process skips RESERVED, it has not created the rollback journal before writing, so a crash during the write leaves the database in an unrecoverable state (no journal to roll back).
**Why this matters for bridge/orbit:** Bridge's transactional state machine must follow this ordering. If bridge's code shortcuts the lock sequence (e.g., by calling OS-level file locking directly), it bypasses the journaling protocol and loses crash recovery.

### INV-SQLITE-LOCK-005: Hot journal detection — RESERVED lock as hotness signal
**Core Invariant:**
```
∀ db ∈ databases:
  is_hot(journal(db)) ⇔
    exists(journal(db)) ∧
    size(journal(db)) > 512 ∧
    has_well_formed_header(journal(db)) ∧
    (super_journal_name(journal(db)) = "" ∨ exists(super_journal(journal(db)))) ∧
    lock_state(db) ≠ RESERVED
```
**Source:** Section 4.0 (The Rollback Journal), hot journal bullet list: "A journal is hot if... It exists, and... Its size is greater than 512 bytes, and... The journal header is non-zero and well-formed, and... Its super-journal exists or the super-journal name is an empty string, and... There is no RESERVED lock on the corresponding database file."
**Counterexample:** A process crashes while holding RESERVED. The journal exists and is non-zero. Another process checks for hot journal but sees RESERVED is held, so it skips recovery. The crashed process's RESERVED was an OS-level lock that died with the process. The database now has a hot journal that will never be rolled back — the next reader will see the journal, but only if RESERVED is properly released. The critical invariant: RESERVED is the "this journal is still being written" signal. If RESERVED is released (by crash), the journal becomes hot and must be rolled back.
**Why this matters for bridge/orbit:** Bridge's crash recovery depends on this. If bridge crashes mid-write to its ledger, the next bridge restart must detect the hot journal and roll back. If bridge stores its database on a filesystem where POSIX locks are unreliable (NFS), the RESERVED lock may not be properly released on crash, and the hot journal is never detected.

### INV-SQLITE-LOCK-006: Hot journal recovery before read
**Core Invariant:**
```
∀ db ∈ databases, ∀ p ∈ processes:
  before(p, reads(db)) ⇒
    (is_hot(journal(db)) ⇒ rollback(p, journal(db)) ∧ delete(journal(db)))
```
**Source:** Section 4.1 (Dealing with hot journals): "Before reading from a database file, SQLite always checks to see if that database file has a hot journal. If the file does have a hot journal, then the journal is rolled back before the file is read."
**Counterexample:** A process opens a database with a hot journal, skips the check, and reads the database. It sees partially-committed data from the crashed transaction — rows that should have been atomic either appear half-inserted, or index entries without corresponding table rows. The database is in an inconsistent state.
**Why this matters for bridge/orbit:** Bridge's startup sequence must guarantee this check happens before any ledger query. If bridge's initialization code reads the database before the pager has opened it (e.g., via a raw file read), it bypasses hot journal recovery.

### INV-SQLITE-LOCK-007: Hot journal recovery uses PENDING, not RESERVED
**Core Invariant:**
```
∀ db ∈ databases, ∀ p ∈ processes:
  is_hot(journal(db)) ∧ rollback(p, journal(db)) ⇒
    lock_state(p, db) transitions UNLOCKED → SHARED → PENDING → EXCLUSIVE
    (NOT through RESERVED)
```
**Source:** Section 4.1 (Dealing with hot journals), step 3: "Acquire a PENDING lock then an EXCLUSIVE lock on the database file. (Note: Do not acquire a RESERVED lock because that would make other processes think the journal was no longer hot.)"
**Counterexample:** A process recovers a hot journal but acquires RESERVED first. Another process checks for hot journals, sees RESERVED is held, and concludes the journal is not hot. It reads the database without rolling back. The first process rolls back its copy, but the second process has already read the inconsistent state and propagated it.
**Why this matters for bridge/orbit:** If bridge's recovery code is implemented manually (not through the SQLite pager), it must replicate this exact lock sequence. Acquiring RESERVED during recovery is a race condition that can cause two bridge instances to disagree on database state.

### INV-SQLITE-LOCK-008: Journal flush before commit
**Core Invariant:**
```
∀ t ∈ transactions:
  commit(t) ⇒
    fsync_complete(journal(t)) ∧
    after(fsync_complete(journal(t)), delete(journal(t)))
```
i.e., the journal data must be on durable storage before the journal file is deleted.
**Source:** Section 5.0 (Writing), commit step 1: "Make sure all rollback journal data has actually been written to the surface of the disk." Step 2: "Flush all database file changes to the disk." Step 3: "Delete the journal file. This is the instant when the changes are committed."
**Counterexample:** Journal data is in OS buffer cache, not on disk. The journal file is deleted. A power failure occurs. The database file has been modified but the journal (which was in cache) is lost. On restart, no hot journal exists, so no rollback occurs. The database contains the committed changes but may have partially-written pages from the interrupted write. The database is corrupt and unrecoverable.
**Why this matters for bridge/orbit:** Bridge's durability guarantees depend on fsync. If bridge runs on a filesystem where fsync is a no-op (misconfigured NFS, some virtualized storage), bridge's ledger can lose committed transactions after a crash. This is a known failure mode documented in Section 6.0.

### INV-SQLITE-LOCK-009: Commit point = journal deletion
**Core Invariant:**
```
∀ t ∈ transactions:
  is_committed(t) ⇔ (journal(t) does not exist ∨ journal(t) has zero header)
```
**Source:** Section 5.0 (Writing), commit step 3: "Delete the journal file. This is the instant when the changes are committed. Prior to deleting the journal file, if a power failure or crash occurs, the next process to open the database will see that it has a hot journal and will roll the changes back. After the journal is deleted, there will no longer be a hot journal and the changes will persist."
**Counterexample:** A process crashes between writing database changes and deleting the journal. On restart, the journal exists and is hot, so the changes are rolled back — correct (atomicity preserved). A process crashes after deleting the journal. On restart, no journal exists, changes are persisted — correct. The invariant is: the journal's existence is the commit bit. If journal exists, changes are not committed. If journal does not exist, changes are committed.
**Why this matters for bridge/orbit:** Bridge's two-phase commit protocol across databases must respect this. If bridge manually deletes a journal file without going through the SQLite commit protocol, it may falsely commit a transaction that was never actually written to the database file.

### INV-SQLITE-LOCK-010: Multi-database commit atomicity via super-journal
**Core Invariant:**
```
∀ t ∈ transactions, ∀ db1, db2 ∈ databases(t):
  is_committed(t, db1) ⇔ is_committed(t, db2)
```
Achieved by: super-journal deletion is the commit point for all attached databases.
**Source:** Section 5.0 (Writing), multi-database commit step 5: "Delete the super-journal file. This is the instant when the changes are committed. Prior to deleting the super-journal file, if a power failure or crash occurs, the individual file journals will be considered hot and will be rolled back... After the super-journal has been deleted, the file journals will no longer be considered hot and the changes will persist."
**Counterexample:** A transaction spans two databases (e.g., ATTACH). The super-journal names both file journals. After writing database changes but before deleting the super-journal, a crash occurs. The super-journal exists, so both file journals are hot and both are rolled back — atomicity preserved. If the crash occurs after deleting the super-journal but before deleting one file journal, the surviving file journal is not hot (because its super-journal is gone), so the changes in that database are not rolled back. Both databases are in the committed state — atomicity preserved. The invariant holds only if the super-journal is deleted atomically (a single file deletion) and all databases are on the same disk volume.
**Why this matters for bridge/orbit:** Bridge may use ATTACHed databases for its ledger + audit log. If bridge's databases are on different volumes (Section 6.0 warns against this), a power failure during commit can cause partial commit — some databases rolled back, others not. Bridge must ensure all databases in a transaction are on the same volume.

### INV-SQLITE-LOCK-011: Writer starvation prevention
**Core Invariant:**
```
∀ db ∈ databases:
  ∃ writer w : lock_state(w, db) = PENDING ⇒
    eventually ∃ t : lock_state(w, db) = EXCLUSIVE
  assuming all existing readers eventually release their SHARED locks
```
**Source:** Section 5.1 (Writer starvation): "The PENDING lock allows existing readers to continue but prevents new readers from connecting to the database. So when a process wants to write a busy database, it can set a PENDING lock which will prevent new readers from coming in. Assuming existing readers do eventually complete, all SHARED locks will eventually clear and the writer will be given a chance to make its changes."
**Counterexample:** Without PENDING, a continuous stream of readers prevents any writer from acquiring EXCLUSIVE. The writer starves indefinitely. With PENDING, new readers are blocked, so the set of readers monotonically decreases. If readers never terminate (infinite queries), the writer still starves — the invariant requires readers to eventually terminate.
**Why this matters for bridge/orbit:** Bridge's audit workflow runs long read queries. If bridge launches a new audit while one is still running, the PENDING lock from the write phase of the first audit prevents the second audit from acquiring SHARED. This is a self-DoS concern: bridge must ensure reads eventually terminate so writes can proceed.

### INV-SQLITE-LOCK-012: autocommit state machine — lock acquisition is lazy
**Core Invariant:**
```
∀ t ∈ transactions:
  BEGIN ⇒ lock_state(t, db) = UNLOCKED  (no lock acquired)
  first_SELECT(t) ⇒ lock_state(t, db) = SHARED
  first_INSERT_UPDATE_DELETE(t) ⇒ lock_state(t, db) = RESERVED
  cache_spill(t) ∨ COMMIT(t) ⇒ lock_state(t, db) = EXCLUSIVE
```
**Source:** Section 7.0 (Transaction Control): "Note that the BEGIN command does not acquire any locks on the database. After a BEGIN command, a SHARED lock will be acquired when the first SELECT statement is executed. A RESERVED lock will be acquired when the first INSERT, UPDATE, or DELETE statement is executed. No EXCLUSIVE lock is acquired until either the memory cache fills up and must be spilled to disk or until the transaction commits."
**Counterexample:** BEGIN acquires EXCLUSIVE immediately. No other processes can read the database during the entire transaction, even if the transaction is read-only. Concurrency is destroyed. The lazy lock acquisition maximizes concurrency by deferring exclusive access to the last possible moment.
**Why this matters for bridge/orbit:** Bridge's transaction design should exploit this laziness. Long-running transactions should do reads first (SHARED only), then writes (RESERVED), and commit quickly (EXCLUSIVE for minimal time). If bridge acquires EXCLUSIVE early, it blocks all other bridge components from reading.

### INV-SQLITE-LOCK-013: COMMIT retry on SHARED conflict
**Core Invariant:**
```
∀ t ∈ transactions:
  autocommit_on(t) ∧ commit_attempt(t) ∧ (∃ q : lock_state(q, db) = SHARED) ∧ commit_fails(t) ⇒
    autocommit_off(t)  -- retry loop: user can try COMMIT again
```
**Source:** Section 7.0 (Transaction Control): "If the SQL COMMIT command turns autocommit on and the autocommit logic then tries to commit change but fails because some other process is holding a SHARED lock, then autocommit is turned back off automatically. This allows the user to retry the COMMIT at a later time after the SHARED lock has had an opportunity to clear."
**Counterexample:** COMMIT fails because SHARED locks are held and the EXCLUSIVE lock cannot be acquired. The transaction is aborted and all changes are lost. The user must redo the entire transaction. With the retry mechanism, the transaction stays open and the user can retry COMMIT without redoing the work.
**Why this matters for bridge/orbit:** Bridge's commit logic must handle SQLITE_BUSY from COMMIT. Bridge should retry COMMIT (not the entire transaction) with backoff. If bridge aborts and retries the full transaction on COMMIT failure, it may re-enter an infinite loop if readers are continuously active.

## Cross-cutting themes

### Lock compatibility matrix (derived from Section 3.0)

| State held | UNLOCKED | SHARED | RESERVED | PENDING | EXCLUSIVE |
|-----------|----------|--------|----------|---------|-----------|
| UNLOCKED  | yes | yes | yes | yes | yes |
| SHARED    | yes | yes | yes | yes | **no** |
| RESERVED  | yes | yes | **no** | **no** | **no** |
| PENDING   | yes | **no** | **no** | **no** | **no** |
| EXCLUSIVE | **no** | **no** | **no** | **no** | **no** |

Rows: lock already held by process A. Columns: lock requested by process B.
"yes" = compatible (both can hold). "no" = incompatible (B must wait or get SQLITE_BUSY).

### Failure modes requiring trust in OS primitives (Section 6.0)

SQLite correctness depends on three OS primitives working correctly:
1. **POSIX advisory locks / LockFileEx**: Must provide mutual exclusion. Broken on many NFS implementations.
2. **fsync / FlushFileBuffers**: Must flush to durable media. Broken on some IDE disks with write caching, and on some Windows configurations.
3. **Filesystem atomicity**: Journal file creation/deletion must be atomic. ext3 without barrier=1 can lose journal file metadata after a crash.

If any of these fail, all invariants above are void. The pager cannot defend against OS/hardware failure.