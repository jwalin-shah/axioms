# oracle/sqlite-arch — Architecture: VDBE, B-tree, pager, OS interface
Source: https://sqlite.org/arch.html
Date pulled: 2026-07-21
Source type: oracle-extract (MEDIUM trust)
Covers: High-level architectural decomposition of SQLite. Component-specific deep invariants live in the per-component documentation pages (btree.html, pager.html, wal.html, vdbe.html, etc.) — this page is the map, not the specification.

---

## Page Summary

This is the architecture overview page. It describes SQLite's layered design:
1. **Interface** — public C API (sqlite3_*)
2. **SQL Compiler** — Tokenizer -> Parser (Lemon-generated) -> Code Generator (query planner)
3. **Core** — Virtual Machine (VDBE bytecode engine)
4. **Backend** — B-Tree -> Pager (page cache, locking, atomic commit) -> OS Interface (VFS)

The page is **not** a deep specification. It names the components and describes their roles at a high level. Concrete, falsifiable invariants about data integrity, concurrency, and crash recovery are documented on the component-specific pages. The invariants extracted below are architectural invariants — constraints on the system's decomposition and control flow, not data-structure invariants.

## Extracted Invariants

### INV-SQLITE-ARCH-001: Bytecode compilation barrier
**Core Invariant:**
```
∀ SQL statements executed via sqlite3_step():
  the statement was first compiled to bytecode via sqlite3_prepare_v2()
  (or equivalent prepare interface)
```
**Source:** Overview section — "SQLite works by compiling SQL text into bytecode, then running that bytecode using a virtual machine."
**Counterexample:** Bypassing preparation and executing raw SQL text directly would break the entire execution model. The prepared statement (sqlite3_stmt) is the only valid input to sqlite3_step(). There is no eval()-style direct execution path.
**Why this matters for bridge/orbit:** Bridge's sandbox executes untrusted code. This compilation barrier means SQL text is never interpreted — it's always compiled to a bounded bytecode program first. This is the same pattern bridge should follow: compile before execute, never eval.

### INV-SQLITE-ARCH-002: Token stream is strictly one-at-a-time
**Core Invariant:**
```
∀ tokens produced by the tokenizer for a given SQL string:
  tokens are delivered to the parser one at a time,
  in order,
  with no buffering or lookahead beyond immediate context
```
**Source:** Tokenizer section — "The tokenizer breaks the SQL text into tokens and hands those tokens one by one to the parser."
**Counterexample:** Batch delivery of tokens would break the parser's ability to handle incremental/streaming input. It would also prevent the tokenizer-calls-parser control flow.
**Why this matters for bridge/orbit:** Orbit's session dispatch processes streaming input. The one-at-a-time token model is a concurrency-safe design pattern — no shared token buffer between producer and consumer.

### INV-SQLITE-ARCH-003: Tokenizer drives parser (control flow inversion)
**Core Invariant:**
```
∀ SQL parsing operations:
  the tokenizer calls the parser (not parser calls tokenizer)
```
**Source:** Tokenizer section — "the tokenizer calls the parser. People who are familiar with YACC and BISON may be accustomed to doing things the other way around — having the parser call the tokenizer. Having the tokenizer call the parser is better, though, because it can be made threadsafe and it runs faster."
**Counterexample:** Parser-calls-tokenizer (the YACC/BISON convention) creates a shared mutable state problem: the parser must repeatedly call into the tokenizer, and both must agree on parsing state. Tokenizer-calls-parser avoids this — the tokenizer owns the input stream and push-drives the parser, making each parse operation self-contained.
**Why this matters for bridge/orbit:** This is a control-flow inversion pattern relevant to bridge's agent dispatch. Push-driven (producer calls consumer) is inherently more concurrency-safe than pull-driven (consumer calls producer) when the producer owns the input stream.

### INV-SQLITE-ARCH-004: Parser reentrancy and thread-safety
**Core Invariant:**
```
∀ Lemon-generated parser instances:
  the parser is reentrant (can be paused and resumed)
  AND the parser is thread-safe (multiple instances can run concurrently)
```
**Source:** Parser section — "Lemon also generates a parser which is reentrant and thread-safe."
**Counterexample:** A non-reentrant parser would block the calling thread during long parse operations. A non-thread-safe parser would require external synchronization for concurrent prepare operations, creating a bottleneck.
**Why this matters for bridge/orbit:** Orbit runs multiple concurrent sessions. Any shared component (like a parser) must be reentrant and thread-safe, or it becomes a serialization point.

### INV-SQLITE-ARCH-005: No memory leak on parse error
**Core Invariant:**
```
∀ syntax errors encountered during parsing:
  all memory allocated for the parse tree up to the error point is freed
  (no leak; non-terminal destructor runs for all partially-constructed nodes)
```
**Source:** Parser section — "Lemon defines the concept of a non-terminal destructor so that it does not leak memory when syntax errors are encountered."
**Counterexample:** Without destructors on parse errors, every malformed SQL statement would leak memory allocated for partial parse tree nodes. Over many failed prepare() calls (e.g., from fuzzing or adversarial input), this becomes a denial-of-service vector.
**Why this matters for bridge/orbit:** Bridge handles untrusted input. Any parser/compiler that processes adversarial input **must** have error-path cleanup — otherwise it's a memory-exhaustion DoS. This is a P0 invariant for sandbox code.

### INV-SQLITE-ARCH-006: Per-table, per-index B-tree isolation
**Core Invariant:**
```
∀ tables T and indices I in a database D:
  T has a distinct B-tree BT
  AND each index i ∈ I has a distinct B-tree Bi
  AND BT ≠ Bi for all i
  AND all B-trees {BT} ∪ {Bi} are stored in the same disk file
```
**Source:** B-Tree section — "Separate B-trees are used for each table and each index in the database. All B-trees are stored in the same disk file."
**Counterexample:** Shared B-tree across tables would mean corrupting one table's structure could cascade to another. Per-table B-trees provide fault isolation. Shared storage in a single file means the atomic commit mechanism (pager) can treat all B-trees as a single transactional unit.
**Why this matters for bridge/orbit:** This is the classic "separate mechanism, unified policy" pattern. Bridge's sandbox should isolate sessions (separate mechanism) but audit them under a unified ledger (unified policy). The B-tree architecture demonstrates both isolation and unification coexisting.

### INV-SQLITE-ARCH-007: File format backward compatibility
**Core Invariant:**
```
∀ database files created by SQLite version V:
  the file is readable and writable by all SQLite versions V' where V' ≥ V
  (the file format is stable and guaranteed forward-compatible)
```
**Source:** B-Tree section — "The file format details are stable and well-defined and are guaranteed to be compatible moving forward."
**Counterexample:** Breaking the file format would orphan all existing databases. SQLite has maintained backward compatibility since version 3.0.0 (2004-06-18). This is a ~20-year invariant with massive blast radius if violated.
**Why this matters for bridge/orbit:** Bridge's knowledge ledger format needs the same backward-compatibility discipline. Any change to the ledger schema must handle both old and new formats.

### INV-SQLITE-ARCH-008: Page size is a power of two in [512, 65536]
**Core Invariant:**
```
∀ database pages:
  page_size ∈ {2^n | n ∈ ℕ, 9 ≤ n ≤ 16}
  (i.e., page_size is a power of two between 512 and 65536)
```
**Source:** Page Cache section — "The default page_size is 4096 bytes but can be any power of two between 512 and 65536 bytes."
**Counterexample:** A non-power-of-two page size would break alignment assumptions throughout the B-tree and pager code. The power-of-two constraint enables efficient bit-masking for page-offset calculations instead of division/modulo. Violating it corrupts all I/O.
**Why this matters for bridge/orbit:** Resource bounds with power-of-two constraints are a common pattern for efficient bitwise operations. Bridge's sandbox memory limits should follow the same pattern — allocate in power-of-two blocks for alignment efficiency.

### INV-SQLITE-ARCH-009: Atomic commit via pager abstraction
**Core Invariant:**
```
∀ transactions T:
  either all pages modified by T are durably written to disk (commit)
  OR no pages modified by T persist (rollback)
  (the pager provides atomic commit)
```
**Source:** Page Cache section — "The page cache also provides the rollback and atomic commit abstraction."
**Counterexample:** Partial commit (some pages written, some not) after a crash would corrupt the database. The pager ensures that after recovery, the database is always in a consistent state — either the transaction happened or it didn't.
**Why this matters for bridge/orbit:** Bridge's audit ledger needs the same atomicity guarantee. Every audit entry must be all-or-nothing. The pager's rollback journal / WAL pattern is the classic implementation of this invariant.

### INV-SQLITE-ARCH-010: All disk I/O through VFS
**Core Invariant:**
```
∀ file operations (open, read, write, close, sync, lock, unlink):
  the operation goes through the VFS abstraction layer
  NO component below the VFS interface makes direct OS syscalls
```
**Source:** OS Interface section — "In order to provide portability across operating systems, SQLite uses an abstract object called the VFS."
**Counterexample:** Direct OS calls in the B-tree or pager would break portability and make it impossible to inject test doubles for crash testing. SQLite's test suite relies on VFS injection to simulate power failures, I/O errors, and full disks.
**Why this matters for bridge/orbit:** This is the dependency inversion pattern. Bridge's sandbox should route all system calls through an injectable interface, enabling hermetic testing of failure modes.

### INV-SQLITE-ARCH-011: sqlite3_step() termination guarantees
**Core Invariant:**
```
∀ calls to sqlite3_step(S) where S is a prepared statement:
  the call returns within finite time with exactly one of:
  - SQLITE_ROW (a result row is available)
  - SQLITE_DONE (execution complete)
  - SQLITE_ERROR (fatal error)
  - SQLITE_INTERRUPT (externally interrupted)
```
**Source:** Overview section — "The sqlite3_step() interface passes a bytecode program into the virtual machine, and runs the program until it either completes, or forms a row of result to be returned, or hits a fatal error, or is interrupted."
**Counterexample:** An infinite loop in bytecode execution would hang the calling thread indefinitely. The VDBE is designed so every opcode consumes a fixed amount of virtual "operations" and the VM enforces an operation limit (sqlite3_progress_handler) to catch runaway queries.
**Why this matters for bridge/orbit:** Bridge's untrusted code execution must have the same termination guarantee — any execution step either produces output, completes, errors, or is interrupted. No unbounded execution. This is the universal sandbox invariant.

### INV-SQLITE-ARCH-012: No test code in production builds
**Core Invariant:**
```
∀ source files in src/ whose name begins with "test":
  the file is excluded from standard (non-test) builds
```
**Source:** Test Code section — "Files in the 'src/' folder of the source tree whose names begin with test are for testing only and are not included in a standard build of the library."
**Counterexample:** Test code in production builds could introduce backdoors (e.g., test hooks that bypass authorization), inflate binary size, or expose internal state. The naming convention acts as a build-system-level security boundary.
**Why this matters for bridge/orbit:** Bridge's build must similarly exclude test-only code paths from production sandbox builds. Test hooks that bypass security checks are a classic sandbox escape vector.

---

## Assessment

**Trust level: MEDIUM** (oracle-extract). The page is an official SQLite documentation page, well-maintained, but it is an architecture overview — not a specification. The invariants extracted are architectural constraints, not formal data-structure invariants.

**What this page is good for:**
- Understanding SQLite's layered decomposition (compiler -> VM -> storage)
- Architectural patterns: push-driven tokenizer, reentrant parser, VFS abstraction, atomic commit
- Component boundaries and interface contracts

**What this page does NOT cover (needs separate source-cache entries):**
- B-tree page structure invariants (btree.html)
- Pager crash recovery invariants (pager.html, wal.html)
- VDBE opcode semantics and safety (opcode.html)
- Locking and concurrency invariants (lockingv3.html)
- WAL invariants (wal.html)
- File format invariants (fileformat2.html)

**Relevance to bridge/orbit audit:** HIGH. Eight of twelve extracted invariants have direct architectural analogues in bridge (sandbox compilation barrier, reentrancy, error-path cleanup, atomic ledger, VFS-style dependency injection, termination guarantees, per-component isolation, production/test build separation).
