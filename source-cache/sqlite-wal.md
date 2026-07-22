# oracle/sqlite-wal — WAL mode: checkpoint, wal-index, concurrency guarantees
Source: https://sqlite.org/wal.html
Date pulled: 2026-07-21
Source type: oracle-extract (MEDIUM trust)

## Extracted Invariants

### INV-WAL-001: Snapshot Isolation Per Reader
**Core Invariant:**
```
∀ reader r, ∀ transaction t opened by r:
  end_mark(r, t) = last_valid_commit_record(WAL) at t_open
  ∧ end_mark(r, t) is constant for duration(t)
  ⇒ visible_pages(r, t) = { p ∈ database | p.last_modified ≤ end_mark(r, t) }
```
**Source:** Section 2.2 (Concurrency), paragraphs 1-2.
"When a read operation begins on a WAL-mode database, it first remembers the location of the last valid commit record in the WAL. Call this point the 'end mark'. [...] for any particular reader, the end mark is unchanged for the duration of the transaction, thus ensuring that a single read transaction only sees the database content as it existed at a single point in time."

**Counterexample:** If the end mark were mutable during a read transaction, a reader could observe a page modified by a concurrent writer that committed after the reader's transaction began, violating snapshot isolation. The reader would see a torn (partially updated) view of the database.

**Why this matters for bridge/orbit:** Bridge/orbit's session isolation depends on consistent snapshots. If a reader's view isn't pinned at transaction-open time, provenance queries could see interleaved writes from concurrent dispatch operations, breaking audit log integrity (finding #9 verify-machine blind spot).

---

### INV-WAL-002: Single Writer Constraint
**Core Invariant:**
```
∀ points in time τ, |{ writers active at τ }| ≤ 1
```
**Source:** Section 2.2 (Concurrency), paragraph 5.
"Writers merely append new content to the end of the WAL file. Because writers do nothing that would interfere with the actions of readers, writers and readers can run at the same time. However, since there is only one WAL file, there can only be one writer at a time."

**Counterexample:** Two concurrent writers appending to the WAL would interleave commit records, making it impossible to determine which transaction's pages belong to which commit. A crash between the two appends could leave a partial commit in the WAL that cannot be distinguished from a complete one, causing either phantom writes or silent data loss.

**Why this matters for bridge/orbit:** Bridge's delivery control (finding #7) relies on exactly-once dispatch semantics. If two dispatch writers could interleave WAL appends, a delivery could be marked as both committed and uncommitted simultaneously, breaking the non-repudiable ledger.

---

### INV-WAL-003: Checkpoint Must Not Overwrite Active Reader Pages
**Core Invariant:**
```
∀ checkpoint c, ∀ reader r active during c:
  max_page_checkpointed(c) ≤ min({ end_mark(r) | r active })
```
**Source:** Section 2.2 (Concurrency), paragraph 7.
"A checkpoint can run concurrently with readers, however the checkpoint must stop when it reaches a page in the WAL that is past the end mark of any current reader. The checkpoint has to stop at that point because otherwise it might overwrite part of the database file that the reader is actively using."

**Counterexample:** If a checkpoint wrote a WAL page past reader r's end mark into the database file, and reader r subsequently read that database page (because the page wasn't in the WAL prior to r's end mark), r would see a future-state page. This breaks snapshot isolation (INV-WAL-001) — the reader sees data committed after its transaction began. This is a phantom read.

**Why this matters for bridge/orbit:** Same as INV-WAL-001 — snapshot consistency is the foundation of audit log integrity. If checkpoints can violate reader snapshots, the provenance chain is broken.

---

### INV-WAL-004: WAL-Sync Ordering for Checkpoint Durability
**Core Invariant:**
```
checkpoint_state_machine:
  IDLE → WAL_SYNCED → DB_UPDATED → DB_SYNCED → WAL_RESET → IDLE

order_constraint:
  WAL_sync MUST precede db_write
  ∧ db_sync MUST precede WAL_reset
```
**Source:** Section 2.3 (Performance Considerations), paragraph 4.
"Checkpointing does require sync operations in order to avoid the possibility of database corruption following a power loss or hard reboot. The WAL must be synced to persistent storage prior to moving content from the WAL into the database and the database file must be synced prior to resetting the WAL."

**Counterexample:** If the database file were synced before the WAL, a power failure after the db sync but before the WAL sync could leave the database with checkpointed pages whose source WAL records were lost. On recovery, the WAL would be replayed from its last synced point, potentially re-applying pages already in the database — corrupting the database with duplicate or stale page content. Conversely, if the WAL were reset before the db sync, a crash after WAL reset would lose the checkpointed pages permanently since they exist neither in the WAL nor durably in the database.

**Why this matters for bridge/orbit:** The sandbox (finding #8) writes execution state to SQLite. If the sync ordering invariant is violated during checkpoint, the sandbox could recover with inconsistent execution state — a process marked as completed in the database but with WAL records that still show it as running. This is a sandbox fail-open scenario.

---

### INV-WAL-005: WAL-Database File Atomicity
**Core Invariant:**
```
∀ database db: db_file(db) and WAL_file(db) form an atomic unit.
  If db_file and WAL_file are separated:
    ⇒ data_loss ∨ corruption
```
**Source:** Section 4 (The WAL File), paragraph 2.
"The WAL file is part of the persistent state of the database and should be kept with the database if the database is copied or moved. If a database file is separated from its WAL file, then transactions that were previously committed to the database might be lost, or the database file might become corrupted."

**Counterexample:** If a database file is copied without its WAL file, the copy reflects only checkpointed state. Any committed transactions that exist only in the WAL (not yet checkpointed) are silently lost. Worse, if the original WAL is later checkpointed into a different copy of the database, the two copies diverge irreconcilably — there is no way to merge them because WAL records reference page numbers, not logical operations.

**Why this matters for bridge/orbit:** Orbit's dispatch mechanism snapshots sandbox state. If a sandbox SQLite database is captured without its WAL file, the snapshot is incomplete — recently committed transactions are missing. This means a sandbox restored from such a snapshot could replay operations that were already committed, violating idempotency (finding #7 delivery control).

---

### INV-WAL-006: Single-Host Shared Memory Constraint
**Core Invariant:**
```
∀ processes p₁, p₂ accessing same WAL-mode database:
  host(p₁) = host(p₂)
```
**Source:** Section 1 (Overview), disadvantages list.
"All processes using a database must be on the same host computer; WAL does not work over a network filesystem. This is because WAL requires all processes to share a small amount of memory and processes on separate host machines obviously cannot share memory with each other."

**Counterexample:** Two processes on different hosts, both with the WAL file mounted via NFS, would each mmap the -shm file independently and get different virtual memory mappings. Their wal-index data structures would diverge. Process A could checkpoint pages that process B's wal-index still shows as WAL-resident, causing B to read stale database pages (missing the checkpointed updates). This is silent data corruption — no error is raised, but queries return incorrect results.

**Why this matters for bridge/orbit:** Bridge and orbit run in separate processes (potentially separate containers). If they share a SQLite database via a network mount and attempt WAL mode, the wal-index divergence would cause orbit to see stale bridge state or vice versa. The audit workflow (launched from this axioms repo) must verify that bridge and orbit never share a WAL-mode database across host boundaries.

---

### INV-WAL-007: WAL-Reset Precondition
**Core Invariant:**
```
WAL_reset_permitted ⇔
  checkpoint_progress = complete(WAL)
  ∧ no_readers_active(WAL)
```
**Source:** Section 2.2 (Concurrency), final paragraph.
"Whenever a write operation occurs, the writer checks how much progress the checkpointer has made, and if the entire WAL has been transferred into the database and synced and if no readers are making use of the WAL, then the writer will rewind the WAL back to the beginning and start putting new transactions at the beginning of the WAL."

**Counterexample:** If the WAL were reset while a reader still had pages referenced in the WAL, the reader would attempt to locate a page by its WAL frame number and find different (newer) content at that position — a use-after-free on WAL frames. This causes the reader to return data from a completely unrelated transaction, a silent corruption. The WAL-reset bug (Section 11, lines 506-567) is a concrete instance: a data race allows a checkpoint to leave the wal-index incorrectly marked, causing a subsequent checkpoint to skip WAL frames that were never written to the database.

**Why this matters for bridge/orbit:** This invariant explains the root cause of finding #7 (delivery control) when applied to the audit's concern about overlapping checkpoint and write operations. If bridge writes delivery confirmations while orbit checkpoints, a WAL-reset race could cause confirmations to be silently dropped.

---

### INV-WAL-008: Format Version Guard Against Downgrade Corruption
**Core Invariant:**
```
∀ db in WAL mode: db.header.bytes[18:20] = 2
  ∧ ∀ SQLite version < 3.7.0: open(db) → error("file is encrypted or is not a database")
```
**Source:** Section 10 (Backwards Compatibility), paragraph 2.
"To prevent older versions of SQLite (prior to version 3.7.0, 2010-07-22) from trying to recover a WAL-mode database (and making matters worse) the database file format version numbers (bytes 18 and 19 in the database header) are increased from 1 to 2 in WAL mode."

**Counterexample:** Without the version bump, an older SQLite version encountering a WAL-mode database would see a database file in an inconsistent state (checkpointed pages mixed with uncheckpointed gaps) and attempt rollback-journal recovery. Since no rollback journal exists, the older version would either (a) treat the database as crashed and zero out uncommitted pages, destroying committed WAL transactions, or (b) fail with an ambiguous error that leads the application to reinitialize the database from scratch.

**Why this matters for bridge/orbit:** If bridge/orbit embed SQLite and a downgrade occurs (e.g., container image rollback), the version guard prevents silent corruption. The audit must verify that bridge and orbit's SQLite version is >= 3.7.0 and that any upgrade/downgrade path preserves the format version invariant.

---

## Additional Constraints (Non-Invariant Properties)

These are properties stated in the documentation that are important but not expressed as universal invariants:

1. **WAL persistence across connections** (Section 3.3): PRAGMA journal_mode=WAL is persistent — closing and reopening preserves WAL mode. This is a configuration durability property, not a ∀ invariant.

2. **Checkpoint starvation bound** (Section 6): If there is always at least one active reader, no checkpoint can complete. This is a liveness hazard, not a safety invariant.

3. **Transaction size constraint** (Section 1): "WAL does not work well for very large transactions" — a performance guideline, not a correctness invariant. (Relaxed in 3.11.0+.)

4. **SQLITE_BUSY in edge cases** (Section 9): Queries can return SQLITE_BUSY during exclusive lock, connection close cleanup, or crash recovery. This is a documented behavioral contract, not an invariant.

5. **WAL-reset bug** (Section 11): A data race in versions 3.7.0–3.51.2. This is a known defect, not an invariant — it is a violation of INV-WAL-007 caused by insufficient synchronization.

## Source Trust Assessment

| Factor | Assessment |
|--------|-----------|
| **Source authority** | Primary — official SQLite documentation, authored by the SQLite developers (D. Richard Hipp et al.) |
| **Falsifiability** | HIGH — each invariant has a clear counterexample describing what breaks |
| **Test coverage** | HIGH — SQLite has one of the most extensive test suites in open source (>100 million tests). The invariants here are exercised by TH3 test harness. |
| **Known errata** | Section 11 (WAL-reset bug) documents a 15-year-old invariant violation (INV-WAL-007). Fixed in 3.51.3. Pre-3.51.3 versions have a data race in the checkpoint/WAL-reset handoff. |
| **Trust level** | MEDIUM (per oracle-extract source type classification) |

## Notes for Bridge/Orbit Audit

- INV-WAL-001 (snapshot isolation) and INV-WAL-003 (checkpoint boundary) directly underpin audit finding #9 (verify-machine blind spot) — if snapshots aren't consistent, provenance is unverifiable.
- INV-WAL-005 (file atomicity) and INV-WAL-007 (reset precondition) map to finding #7 (delivery control) — incomplete WAL state can cause dropped or duplicated deliveries.
- INV-WAL-004 (sync ordering) maps to finding #8 (sandbox fail-open) — incorrect fsync ordering during sandbox state persistence can leave the sandbox recoverable to an inconsistent state.
- INV-WAL-008 (format version) is a defensive design pattern — bridge/orbit should apply the same principle: any state format change should be guarded by a version number that prevents older code from corrupting newer state.
