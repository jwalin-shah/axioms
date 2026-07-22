# oracle/postgresql-wal-internals — WAL internals, recovery, checkpoints

Source: https://www.postgresql.org/docs/current/wal-internals.html
Also: https://www.postgresql.org/docs/current/wal-reliability.html
Also: https://www.postgresql.org/docs/current/runtime-config-wal.html
Date pulled: 2026-07-21
PostgreSQL version: 18

## Extracted Invariants

### INV-WAL-001: Write-Ahead Ordering (the core WAL invariant)
**Core Invariant:**
```
∀ t ∈ Transactions, p ∈ DataPages modified by t:
  WAL_Flushed(t, p) → DB_Write(t, p)
```
That is: the WAL record for a data page modification MUST be written (and flushed)
to stable storage BEFORE the actual data page is modified on disk.

**Source:** wal-internals.html, paragraph 5: "The aim of WAL is to ensure that the
log is written before database records are altered."

**Counterexample:** If the database writes a data page before flushing WAL, and a
power failure occurs, the data page will reflect a modification that has no WAL
record. On recovery, the REDO pass cannot replay what was never logged. The page
is in an inconsistent state — committed data is silently lost or partially applied.

**Why this matters for bridge/orbit:** Bridge's execution log and orbit's session
state both rely on write-ahead semantics. Any component that claims durability
must prove its log record hits stable storage before the data mutation is exposed.
This is the definitive formulation of the WAL ordering constraint.

---

### INV-WAL-002: LSN Strict Monotonicity
**Core Invariant:**
```
∀ r1, r2 ∈ WAL_Records:
  r1 precedes r2 in WAL ⇒ LSN(r1) < LSN(r2)
```
LSN is a byte offset into the WAL that increases monotonically with each new
record. No two distinct records can share an LSN. No record can have an LSN
less than or equal to a record that precedes it.

**Source:** wal-internals.html, paragraph 2: "The insert position is described by
a Log Sequence Number (LSN) that is a byte offset into the WAL, increasing
monotonically with each new record."

**Counterexample:** If LSN were not strictly monotonic (e.g., if two concurrent
writers could claim the same LSN, or if LSN could decrease), replication slots
could not determine which records have been received. Recovery could skip records
or replay them out of order. Comparison of LSN values to measure WAL volume would
return incorrect results.

**Why this matters for bridge/orbit:** Bridge's execution log uses sequential
ordering for audit trails. Any log-based replay or replication system must
guarantee total order with strictly increasing sequence numbers. This invariant
is the canonical formulation.

---

### INV-WAL-003: Full Page Write Tear Protection
**Core Invariant:**
```
∀ p ∈ DataPages, c ∈ Checkpoints:
  first_write(p, after(c)) ⇒ FullPageImage(p) ∈ WAL
```
When full_page_writes is enabled (the default), the FIRST modification to each
data page after a checkpoint writes the ENTIRE page content to WAL — not just
the row-level delta. This guarantees that if the operating system crashes
mid-page-write (producing a torn page — a mix of old and new sector contents),
the full page image in WAL can restore the page to a consistent state.

**Source:** wal-reliability.html, paragraph on partial page writes: "PostgreSQL
periodically writes full page images to permanent WAL storage *before* modifying
the actual page on disk. By doing this, during crash recovery PostgreSQL can
restore partially-written pages from WAL."

**Also:** runtime-config-wal.html, full_page_writes parameter description: "Storing
the full page image guarantees that the page can be correctly restored."

**Counterexample:** If full_page_writes were disabled and the OS crashed during a
page write, the disk would contain a torn page: some 512-byte sectors written with
old data, some with new. Row-level WAL records (INSERT/UPDATE/DELETE) cannot
reconstruct a torn page because they describe logical changes, not the physical
page layout. The database would be corrupt and unrecoverable. This is a stronger
failure mode than lost transactions — it is structural page corruption.

**Why this matters for bridge/orbit:** Any system that writes multi-sector data
structures to disk must handle the torn-write problem. Orbit's execution sandbox
writes container images and bridge writes ledger entries — both are multi-block
writes. The full-page-write pattern (write the whole thing to a log first, then
install) is the proven defense.

---

### INV-WAL-004: CRC-32C End-to-End Integrity
**Core Invariant:**
```
∀ r ∈ WAL_Records:
  Valid(CRC32C(r)) at write_time ⇒ Checked(CRC32C(r)) at recovery_time
```
Each WAL record is protected by a CRC-32C checksum. The CRC is computed and
written at record creation time. It is verified during crash recovery, archive
recovery, AND replication. A WAL record with a mismatched CRC is rejected —
this prevents corrupted WAL data from being replayed into the database.

**Source:** wal-reliability.html, first bullet in corruption protection list:
"Each individual record in a WAL file is protected by a CRC-32C (32-bit) check
that allows us to tell if record contents are correct. The CRC value is set when
we write each WAL record and checked during crash recovery, archive recovery and
replication."

**Counterexample:** Without CRC protection, a bit flip in a WAL record (from
cosmic radiation, faulty RAM, or a silent disk corruption) would be replayed
as a valid database operation. An INSERT might become a DELETE, a transaction
ID might shift, or a page offset might land in the wrong relation. The database
would silently corrupt with no detection. CRC-32C catches this deterministically.

**Why this matters for bridge/orbit:** Bridge's non-repudiable execution log and
orbit's dispatch records both need integrity verification on every read-back.
CRC-on-write, verify-on-read is the minimum bar. This invariant defines the pattern:
checksum is set at write time, checked at every subsequent read.

---

### INV-WAL-005: pg_control Atomic Write (Single-Page Guarantee)
**Core Invariant:**
```
size(pg_control) < DiskPageSize ⇒ AtomicWriteGuaranteed(pg_control)
```
The pg_control file (which stores the latest checkpoint position) is smaller than
one disk page (typically < 8 kB). Disk pages are the atomic write unit — a write
of less than one page is either fully written or fully not-written after a power
loss. pg_control therefore cannot suffer a partial write (torn page), making it a
reliable starting point for recovery.

**Source:** wal-internals.html, last paragraph: "pg_control is small enough (less
than one disk page) that it is not subject to partial-write problems."

**Counterexample:** If pg_control were larger than one page and power was lost
mid-write, the file would contain a torn state — the checkpoint position might
point to the wrong WAL location, or the system identifier might be corrupt.
Recovery would start from a wrong or garbage checkpoint, potentially replaying
no WAL (data loss) or replaying the wrong WAL (data corruption).

**Why this matters for bridge/orbit:** Any critical metadata file that serves as a
recovery bootstrap must fit within one atomic write unit. Bridge's ledger head
pointer and orbit's session registry both need this property — if either can tear,
recovery from crash cannot be guaranteed.

---

### INV-WAL-006: Checkpoint-to-REDO Consistency
**Core Invariant:**
```
∀ c ∈ Completed_Checkpoints:
  Consistent(DB) after REDO(CheckpointLSN(c), LastLSN)
```
After a checkpoint is completed (WAL flushed, checkpoint position saved to
pg_control), running REDO from the checkpoint LSN to the end of WAL restores
all data pages to a consistent state. This works BECAUSE full_page_writes ensures
that every page modified after the checkpoint has a full image in WAL somewhere.

**Source:** wal-internals.html, paragraph 6: "Because the entire content of data
pages is saved in the WAL on the first page modification after a checkpoint...
all pages changed since the checkpoint will be restored to a consistent state."

**Counterexample:** If a checkpoint LSN is saved but the WAL between that LSN and
the database's actual state has been partially lost (e.g., deleted WAL segment,
corrupted archive), the REDO pass will either fail (if the gap is detected) or
worse, silently produce an inconsistent database (if a record is missing and the
next record applies cleanly to a stale page).

**Why this matters for bridge/orbit:** Any system with a snapshot-and-log recovery
model (which bridge uses for execution state) must prove that the snapshot point
plus the log from that point forward is sufficient to reconstruct the full state.
This is the canonical checkpoint invariant.

---

### INV-WAL-007: synchronous_commit = off Does NOT Violate Consistency
**Core Invariant:**
```
synchronous_commit = off ⇒ ∀ crashes:
  DB_State_After_Recovery ≡ DB_State_Before_Crash_With_Uncommitted_Aborted
```
Turning off synchronous_commit means a transaction can be reported as "committed"
to the client before its WAL is flushed. On crash, some recently-"committed"
transactions will be lost. However, the database will be in a CONSISTENT state
— exactly as if those transactions had been cleanly aborted. This is qualitatively
different from fsync=off, which can produce structural database corruption.

**Source:** runtime-config-wal.html, synchronous_commit parameter description:
"Unlike fsync, setting this parameter to off does not create any risk of database
inconsistency: an operating system or database crash might result in some recent
allegedly-committed transactions being lost, but the database state will be just
the same as if those transactions had been aborted cleanly."

**Counterexample:** If synchronous_commit=off DID violate consistency, lost
transactions could leave behind partial effects — an INSERT without its index
entry, a foreign key with no referenced row, or a page split half-completed.
The guarantee is that this does NOT happen: either the transaction's effects
are fully present, or fully absent. Never partially present.

**Why this matters for bridge/orbit:** Bridge can trade off durability for
throughput WITHOUT risking structural corruption. This is a critical design
insight: durability and consistency are orthogonal concerns. Turning off sync
loses durability but preserves consistency. Bridge's execution log can use the
same pattern for non-critical event recording.

---

### INV-WAL-008: Segment File Names Never Wrap
**Core Invariant:**
```
∀ s1, s2 ∈ WAL_Segment_Files:
  Created(s1) before Created(s2) ⇒ SegmentNumber(s1) < SegmentNumber(s2)
```
WAL segment files are named with ever-increasing numbers starting at
`000000010000000000000001`. The numbers never wrap. Each segment is typically
16 MB and divided into 8 kB pages.

**Source:** wal-internals.html, paragraph 3: "Segment files are given
ever-increasing numbers as names, starting at 000000010000000000000001. The
numbers do not wrap."

**Counterexample:** If segment numbers wrapped, a new segment could be mistaken
for an old one. A recovery process or a standby server reading archived WAL
could replay old WAL as if it were new (duplicate replay) or skip new WAL
thinking it is old (data loss). The non-wrapping property ensures that a segment
file name uniquely identifies a position in the database's timeline.

**Why this matters for bridge/orbit:** Bridge's execution log and orbit's dispatch
records both use sequential IDs. Any system that uses sequence numbers for
ordering must guarantee no wraparound (or handle it explicitly with epoch
numbers). PostgreSQL's approach — just make the namespace large enough — is the
simplest correct solution.

---

### INV-WAL-009: wal_level Hierarchy (Strict Inclusion)
**Core Invariant:**
```
wal_level(minimal) ⊂ wal_level(replica) ⊂ wal_level(logical)
```
Each WAL level includes all information logged at all lower levels. `minimal`
contains only crash-recovery info. `replica` adds everything needed for WAL
archiving and streaming replication. `logical` adds everything needed for
logical decoding. The levels form a strict inclusion hierarchy.

**Source:** runtime-config-wal.html, wal_level parameter description: "Each level
includes the information logged at all lower levels."

**Counterexample:** If `logical` did not include `replica`-level info, setting
wal_level=logical would break streaming replication because needed WAL records
(like heap inserts with full tuple data) would be missing. The standby would fall
behind or fail. The hierarchy guarantee means you can always upgrade wal_level
without losing any capability.

**Why this matters for bridge/orbit:** Bridge's execution log can produce
different levels of detail (summary, full, debug). Each level must be a strict
superset of the level below it. This invariant formalizes that design constraint:
upgrading detail level must never lose information.

---

### INV-WAL-010: archive_command Zero-Exit Convention
**Core Invariant:**
```
archive_command(file) returns 0 ⇔ File_Archived_Successfully(file)
```
The archive_command must return a zero exit status IFF it successfully archived
the WAL segment. A nonzero exit means failure, and PostgreSQL will retry. The
command will be asked for files not present in the archive and MUST return
nonzero in that case (not crash, not hang).

**Source:** runtime-config-wal.html, archive_command parameter description: "It is
important for the command to return a zero exit status only if it succeeds."

**Counterexample:** If archive_command returns 0 when it failed, PostgreSQL will
delete or recycle the WAL segment believing it was safely archived. If the
database later needs that segment for point-in-time recovery, the data is
permanently lost. If archive_command returns nonzero for a file it was merely
asked about (not expected to have), the archiver will retry forever, eventually
filling pg_wal and halting the database.

**Why this matters for bridge/orbit:** Bridge's external command dispatch and
orbit's sandbox execution both invoke external processes. Any external process
contract must specify: zero exit = success and nothing else. This is the
canonical pattern — derived from PostgreSQL's battle-tested approach to
external process contracts.

---

## Failure Modes Summary

| Failure Mode | Invariant Violated | Consequence |
|---|---|---|
| Disk falsely reports fsync complete | INV-WAL-001 (Write-Ahead) | Irrecoverable data corruption on power loss |
| Torn page after OS crash (no full_page_writes) | INV-WAL-003 (Full Page Write) | Structural page corruption — mix of old/new sectors unrecoverable |
| WAL record bit-flip (no CRC) | INV-WAL-004 (CRC-32C) | Silent data corruption — wrong operation replayed |
| pg_control torn on write | INV-WAL-005 (Atomic Write) | Recovery starts from garbage checkpoint — data loss or corruption |
| fsync=off + power failure | INV-WAL-001 (Write-Ahead) | Database file corruption — not just lost transactions |
| synchronous_commit=off + power failure | INV-WAL-007 (Consistency Safe) | Lost recent transactions, but database remains structurally consistent |
| WAL segment names wrap | INV-WAL-008 (No Wrap) | Recovery replays wrong WAL — duplicate or skipped operations |
| archive_command lies about success | INV-WAL-010 (Zero-Exit) | Lost WAL archives, impossible PITR |

## Trust Assessment

These are **oracle-extract** invariants from the PostgreSQL 18 official
documentation. PostgreSQL's documentation is maintained by the core development
team and reviewed as part of the commit process. The WAL subsystem has been
battle-tested in production for over 20 years across millions of deployments.

**Trust level: HIGH** (treated as oracle-extract with textbook-formal rigor).
The invariants are:

- Falsifiable: each one has a specific counterexample
- Specific: the ordering, atomicity, and integrity properties are precisely stated
- Battle-tested: the WAL subsystem is PostgreSQL's most critical reliability
  mechanism and has survived adversarial testing by the entire database community

Note: INV-WAL-006 (Checkpoint-to-REDO) and INV-WAL-007 (sync-commit consistency)
are partly dependent on INV-WAL-001 (Write-Ahead) and INV-WAL-003 (Full Page Write).
If those foundational invariants are violated, the derived invariants also fail.
