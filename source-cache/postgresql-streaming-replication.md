# oracle/postgresql-streaming-replication — Streaming replication protocol invariants
Source: https://www.postgresql.org/docs/current/protocol-replication.html
Date pulled: 2026-07-21
Source type: oracle-extract
Trust level: MEDIUM (official PostgreSQL documentation, but oracle-extract — not a formal specification; the protocol is defined by implementation, not a separate RFC)

## Context

PostgreSQL 18 documentation, Chapter 54.4. The streaming replication protocol is the wire protocol between a primary PostgreSQL server (WAL sender) and a standby (WAL receiver). It defines the handshake, message framing, keepalive semantics, and the lifecycle of replication slots. The protocol is consumed by tools like `pg_receivewal`, `pg_recvlogical`, and by standby servers directly.

## Extracted Invariants

### INV-PGSR-001: WAL record atomicity across XLogData messages
**Core Invariant:**
```
∀ r ∈ WALRecord, ∀ m₁,m₂ ∈ XLogDataMessage:
  r is not split across m₁ and m₂
```
Equivalently: "A single WAL record is never split across two XLogData messages."
**Source:** XLogData (B) message format section — "A single WAL record is never split across two XLogData messages."
**Scope:** The protocol guarantees that each XLogData message contains zero or more complete WAL records. A WAL record may span multiple messages only via continuation records (when a record crosses a WAL page boundary, the main record and its continuation records can be sent in different messages — but the individual record fragments are themselves complete WAL records, not partial ones).
**Counterexample:** If a WAL sender implementation split a single WAL record across two XLogData messages, the standby would receive a partial record that it cannot decode. The standby's WAL replay would either crash (if it detects the truncation) or silently corrupt state (if it does not). This is a data integrity failure.
**Why this matters for bridge/orbit:** Bridge's audit ledger is append-only and atomically written. Any protocol that ships atomically-written records (like WAL segments or ledger entries) must guarantee that a consumer never receives a partial record. The WAL protocol's atomicity guarantee is a reference design for how to enforce this at the wire level: the framing layer (CopyData + XLogData) is the atomicity boundary. Bridge's ledger writes should similarly guarantee that no consumer sees a half-written entry.

### INV-PGSR-002: Snapshot lifetime is bounded by next command or connection close
**Core Invariant:**
```
∀ s ∈ ExportedSnapshot:
  valid(s) ⇔ (no command executed on connection ∧ connection is open)
```
Equivalently: "The snapshot is valid until a new command is executed on this connection or the replication connection is closed."
**Source:** CREATE_REPLICATION_SLOT response fields — snapshot_name description.
**Counterexample:** If a consumer holds a snapshot reference beyond the next command on the connection, the snapshot's underlying MVCC state may have been advanced or vacuumed away. Queries using the stale snapshot would see inconsistent data (missing rows that were visible at snapshot time, or rows that should have been vacuumed). This is a temporal scope violation — the snapshot is leased, not owned.
**Why this matters for bridge/orbit:** Orbit spawns verification sessions that hold references to system state. Each verification session has an implicit "observation window" — the state it verified was valid at time T. If the session outlives the window (e.g., the verified process is killed and its PID recycled), the verification is stale. This invariant is a pattern for bounding observation windows: tie the window to the connection/session lifecycle, not to an explicit "close" operation (which can be missed).

### INV-PGSR-003: CREATE_REPLICATION_SLOT must be first command in SNAPSHOT 'use' transaction
**Core Invariant:**
```
∀ t ∈ Transaction using SNAPSHOT 'use':
  first_command(t) = CREATE_REPLICATION_SLOT
```
Equivalently: "CREATE_REPLICATION_SLOT must be the first command run in that transaction."
**Source:** CREATE_REPLICATION_SLOT SNAPSHOT option — "'use' will use the snapshot for the current transaction executing the command. This option must be used in a transaction, and CREATE_REPLICATION_SLOT must be the first command run in that transaction."
**Counterexample:** If another command executes before CREATE_REPLICATION_SLOT in the same transaction, that command runs under a different snapshot than the one the slot was created with. The slot's snapshot would not reflect the effects of the earlier command, creating an inconsistency between what the transaction has observed and what the slot will decode. This is a causal ordering violation — the slot's snapshot must be the transaction's first observable state.
**Why this matters for bridge/orbit:** Bridge's spawn sequence has ordering constraints: the sandbox must be configured before the process is launched, the ledger entry must be written before the process is allowed to execute. This invariant is a pattern for enforcing "X must happen before any other observable action in context Y." Bridge can enforce similar ordering constraints by making the first command in a spawn session be the one that establishes the session's consistency point.

### INV-PGSR-004: Temporary slots are not durable and auto-cleanup on error/session-end
**Core Invariant:**
```
∀ s ∈ TemporaryReplicationSlot:
  (session_ends ∨ error_occurs) ⇒ s is dropped
  ∧ s is never persisted to disk
```
Equivalently: "Temporary slots are not saved to disk and are automatically dropped on error or when the session has finished."
**Source:** CREATE_REPLICATION_SLOT TEMPORARY option.
**Counterexample:** If a temporary slot were persisted to disk, a crash-restart cycle would leak the slot — it would consume WAL retention resources indefinitely with no consumer to release them. If a temporary slot were not auto-dropped on error, a failed replication client would leave garbage state on the server. Both are resource leaks that degrade into disk-full conditions.
**Why this matters for bridge/orbit:** Orbit creates temporary sandboxes for each spawned process. These sandboxes must be cleaned up when the session ends or when an error occurs. The temporary slot pattern is a reference for how to design cleanup: tie the resource's lifetime to the session, make cleanup automatic (not best-effort), and never persist temporary resources to survive a restart. Bridge's sandbox cleanup should follow the same pattern — if bridge crashes, temporary sandboxes must not survive.

### INV-PGSR-005: Base backup mode is atomically entered and exited
**Core Invariant:**
```
∀ b ∈ BaseBackup:
  backup_mode = true during b
  ∧ backup_mode = false before b ∧ backup_mode = false after b
```
Equivalently: "The system will automatically be put in backup mode before the backup is started, and taken out of it when the backup is complete."
**Source:** BASE_BACKUP command description.
**Counterexample:** If the server were left in backup mode after the backup completes (e.g., due to a client disconnect mid-backup), WAL would accumulate without being recycled, eventually filling the disk. If backup mode were not entered before the backup starts, the backup would capture an inconsistent state — files being modified concurrently by normal operations. This is a state-machine invariant: the backup mode is a critical section that must be entered and exited exactly once per backup.
**Why this matters for bridge/orbit:** Bridge's spawn pipeline has critical sections: the sandbox setup, the process launch, the ledger write. Each critical section must be entered and exited atomically. If bridge crashes mid-spawn, the system must not be left in a half-configured state. The base backup pattern is a reference for how to structure critical sections: automatic entry before the operation, automatic exit after, and the exit must be guaranteed even on error paths.

### INV-PGSR-006: Logical replication start position is the max of requested and confirmed
**Core Invariant:**
```
∀ s ∈ LogicalReplicationStart:
  start_lsn = max(requested_lsn, slot.confirmed_flush_lsn)
```
Equivalently: "Instructs server to start streaming WAL for logical replication, starting at either WAL location XXX/XXX or the slot's confirmed_flush_lsn, whichever is greater."
**Source:** START_REPLICATION SLOT slot_name LOGICAL XXX/XXX command description.
**Counterexample:** If the server started at a position earlier than confirmed_flush_lsn, the client would receive WAL data it has already processed and confirmed, leading to duplicate decoding. If the server started at a position earlier than requested (but the client had advanced beyond it), the same duplication occurs. The max() semantics ensure forward progress — the server will never rewind past what the client has confirmed. However, the client must still verify: "starting at a different LSN than requested might not catch certain kinds of client errors."
**Why this matters for bridge/orbit:** Bridge's audit ledger is append-only with confirmed positions. When a consumer reconnects, it must resume from max(last_confirmed, last_written) to avoid both gaps and duplicates. The max() semantics in the replication protocol are a reference for how to implement idempotent replay: the server guarantees no rewind, but the client must still verify the starting position matches expectations.

### INV-PGSR-007: MAX_RATE range constraint
**Core Invariant:**
```
∀ r ∈ MAX_RATE_option:
  r = 0 ∨ (32 ≤ r ≤ 1048576)  [kB/s]
```
Equivalently: "If this option is specified, the value must either be equal to zero or it must fall within the range from 32 kB through 1 GB (inclusive)."
**Source:** BASE_BACKUP MAX_RATE option description.
**Counterexample:** A rate of 0 disables throttling. A rate below 32 kB/s is rejected because it would make the backup impractically slow. A rate above 1 GB/s is rejected because it exceeds the server's ability to throttle meaningfully. Values outside the range are rejected with an error — this is an input validation invariant that prevents the server from entering an unbounded or useless throttling mode.
**Why this matters for bridge/orbit:** Bridge's resource limits (CPU, memory, disk) for spawned processes have similar range constraints. A limit that is too low is useless (the process starves), a limit that is too high is effectively unbounded. The MAX_RATE pattern is a reference for range-validated resource constraints: define a minimum below which the constraint is meaningless, a maximum above which it's indistinguishable from unbounded, and reject everything outside.

### INV-PGSR-008: UPLOAD_MANIFEST must precede INCREMENTAL base backup
**Core Invariant:**
```
∀ b ∈ BaseBackup with INCREMENTAL option:
  UPLOAD_MANIFEST must have been executed on this connection before b
```
Equivalently: "The UPLOAD_MANIFEST command must be executed before running a base backup with this option."
**Source:** BASE_BACKUP INCREMENTAL option description.
**Counterexample:** If an incremental backup is requested without a prior manifest upload, the server has no reference point to compute the delta against. The backup would either fail with an error or produce a full backup masquerading as incremental (wasting bandwidth and storage). This is a protocol ordering invariant: operation B depends on the side effects of operation A, and A must complete before B begins.
**Why this matters for bridge/orbit:** Bridge's spawn pipeline has similar ordering dependencies: the sandbox must be configured before the process is launched, the ledger entry must be written before the process is allowed to execute. The UPLOAD_MANIFEST pattern is a reference for enforcing prerequisite operations: make the dependency explicit at the protocol level, and reject the dependent operation if the prerequisite hasn't been satisfied.

### INV-PGSR-009: Keepalive timeout — server disconnects unresponsive clients
**Core Invariant:**
```
∀ k ∈ PrimaryKeepalive with reply_requested = 1:
  ¬client_responds_soon ⇒ connection_timeout
```
Equivalently: "1 means that the client should reply to this message as soon as possible, to avoid a timeout disconnect."
**Source:** Primary keepalive message format — Byte1 field description.
**Counterexample:** If the server does not enforce a timeout on unresponsive clients, a dead standby would hold WAL segments indefinitely (the server retains WAL for all registered standbys). This would eventually fill the primary's disk. The keepalive mechanism is a liveness check: if the client is dead, the server must detect it and release resources. The timeout disconnect is the enforcement mechanism.
**Why this matters for bridge/orbit:** Orbit spawns verification processes that must report status. If a verification process hangs, bridge must detect it and terminate the session (releasing sandbox resources). The keepalive pattern is a reference for liveness monitoring: the server periodically probes, the client must respond, and failure to respond triggers resource cleanup. Bridge's session management should follow the same pattern.

### INV-PGSR-010: DROP_REPLICATION_SLOT WAIT blocks until slot inactive
**Core Invariant:**
```
∀ s ∈ ActiveReplicationSlot, DROP_REPLICATION_SLOT s WAIT:
  command blocks until s becomes inactive
```
Equivalently: "WAIT This option causes the command to wait if the slot is active until it becomes inactive, instead of the default behavior of raising an error."
**Source:** DROP_REPLICATION_SLOT WAIT option.
**Counterexample:** Without WAIT, dropping an active slot raises an error — the caller must retry. With WAIT, the command blocks until the slot's consumer disconnects. If the consumer never disconnects (hung standby), the DROP blocks indefinitely. This is a graceful shutdown pattern: wait for in-flight work to complete before tearing down resources, but with an implicit timeout (the caller can cancel the command).
**Why this matters for bridge/orbit:** When bridge tears down a sandbox, it must wait for the spawned process to exit before cleaning up. If the process is hung, bridge must eventually force-kill. The DROP_REPLICATION_SLOT WAIT pattern is a reference for graceful teardown: block until the resource is quiescent, but allow the caller to cancel (or implement a timeout) for hung resources.

## Additional Observations

### Not extracted as invariants

1. **Standby LSN monotonicity:** The three LSN fields in Standby status update (received, flushed, applied) form a pipeline. While the protocol implies `received >= flushed >= applied` (you can't flush what you haven't received, you can't apply what you haven't flushed), this is not stated as an invariant in the protocol doc — it's a consequence of how PostgreSQL's WAL processing works. Not extracted because it's an implementation property, not a protocol guarantee.

2. **Timeline history completeness:** "the server will stream all the WAL on that timeline starting from the requested start point up to the point where the server switched to another timeline." This is a completeness guarantee (all WAL on a timeline is streamed), but the doc also notes "corner cases where the server can send some WAL from the old timeline that it has not itself replayed before promoting" — the guarantee has a caveat. Not extracted because it's not a clean universal invariant.

3. **TABLESPACE_MAP symbolic links:** "Symbolic links in pg_tblspc are maintained." This is a data preservation guarantee but too narrow to be a general invariant.

4. **Replication commands only in simple query protocol:** "In either physical replication or logical replication walsender mode, only the simple query protocol can be used." This is a protocol constraint, but it's a limitation (not a guarantee) — it says what you can't do, not what must hold.

5. **Slot name validity:** "Must be a valid replication slot name." This is an input validation rule, not a system invariant. The definition of "valid" is deferred to another section.

## Verification Status

These invariants have NOT been verified against the PostgreSQL source code. They are extracted from the documentation, which is authoritative but may lag behind the implementation. A full verification would require:
1. Cross-referencing with `src/backend/replication/walsender.c` for WAL record atomicity
2. Checking that the snapshot lifetime bound is enforced in `src/backend/replication/logical/snapbuild.c`
3. Verifying the max() semantics in `src/backend/replication/logical/logical.c`

This is consistent with the oracle-extract trust level (MEDIUM) — the documentation is the closest thing to a specification but is not a formal spec.