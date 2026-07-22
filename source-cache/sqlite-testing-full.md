# oracle/sqlite-testing-full — Full testing methodology: TH3, Sqllogictest, anomaly testing, fuzzing
Source: https://sqlite.org/testing.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-XXX-001: Atomic commit across crash/power-loss
**Core Invariant:**
```
∀ write-transaction T, ∀ crash/power-loss during T:
  after restart, ∃ exactly one of:
    (a) T's changes are fully committed and visible, OR
    (b) T's changes are completely rolled back and not visible
  ∧ PRAGMA integrity_check reports no corruption
```
**Source:** Section 3.3 "Crash Testing" — "After the child dies, the original test process opens and reads the test database and verifies that the changes attempted by the child either completed successfully or else were completely rolled back. The integrity_check PRAGMA is used to make sure no database corruption occurs."

Also from TH3 crash simulation: "Then the database is opened and checks are made to ensure that it is well-formed and that the transaction either ran to completion or was completely rolled back."

**Counterexample:** A partial write survives a crash — e.g., a row is inserted but its index entry is lost, or a page is written but its parent page pointer is not updated. This violates atomicity: the database is corrupt (integrity_check fails) and contains an inconsistent state.

**Why this matters for bridge/orbit:** Bridge spawns sandboxed processes that may be killed at any time. If bridge's execution ledger makes an analogous guarantee (log entry is fully written or fully absent after restart), it must implement write-ahead-journal semantics with equivalent crash-recovery. Orbit's dispatch table is similarly vulnerable — if a dispatch crashes mid-update, the assignment table must not end up with a ghost assignment.

---

### INV-XXX-002: Write-ahead journal ordering
**Core Invariant:**
```
∀ write to database file at address A:
  the data at A must have been written AND synced to the rollback journal
  BEFORE the write to A occurs
```
**Source:** Section 8.5 "Journal Tests" — "The journal-test VFS monitors all disk I/O traffic between the database file and rollback journal, checking to make sure that nothing is written into the database file which has not first been written and synced to the rollback journal. If any discrepancies are found, an assertion fault is raised."

**Counterexample:** Data written directly to the database file before the journal entry is synced. If a crash occurs between the database write and the journal sync, the journal contains no record of the old value, making rollback impossible. The database is now corrupted with no recovery path.

**Why this matters for bridge/orbit:** This is the fundamental WAL invariant. Bridge's execution ledger and orbit's dispatch log need equivalent ordering: the undo record must be durable before the forward mutation. Without it, crash recovery is impossible.

---

### INV-XXX-003: No memory leak under any failure mode
**Core Invariant:**
```
∀ operation O, ∀ failure mode F ∈ {OOM, disk-I/O-error, malformed-input}:
  after O completes (with error or success),
  memory allocated during O's execution == memory freed after O's completion
  (i.e., no leak)
```
**Source:** Section 6 "Automatic Resource Leak Detection" — "SQLite is designed to never leak memory, even after an exception such as an OOM error or disk I/O error. The test harnesses are zealous to enforce this."

**Counterexample:** An OOM error during a B-tree split: the new node buffer is allocated, the split fails halfway, and one of two allocated buffers is not freed. After many such failures, the process runs out of memory despite all operations having returned errors.

**Why this matters for bridge/orbit:** Bridge's sandbox processes are long-running. A slow memory leak under error conditions (which happen frequently in adversarial sandboxes) would accumulate until the sandbox exhausts memory. Orbit's session multiplexer is similarly at risk: each failed dispatch that leaks memory degrades the multiplexer over time.

---

### INV-XXX-004: Query optimizer semantic preservation
**Core Invariant:**
```
∀ SQL query Q, ∀ optimization flag configuration C (on/off):
  result(Q, optimizations=C_on) = result(Q, optimizations=C_off)
```
**Source:** Section 9 "Disabled Optimization Tests" — "SQLite should always generate exactly the same answer with optimizations enabled and with optimizations disabled; the answer simply arrives quicker with the optimizations turned on."

**Counterexample:** A query optimizer rewrites `x OR y` as a short-circuit when `x` is true and skips evaluating `y`, but `y` has a side effect (e.g., a trigger or a virtual column computation). The result differs because `y` was never evaluated.

**Why this matters for bridge/orbit:** Bridge's axiom verifier and orbit's dispatch engine both perform logical rewrites (e.g., axiom simplification, dispatch constraint propagation). Any optimizer that changes the result is a correctness bug — the invariant provides a test methodology: run the same workload with optimizations disabled and assert identical output.

---

### INV-XXX-005: Malformed input must produce defined error, not undefined behavior
**Core Invariant:**
```
∀ malformed database file D (bytes changed by non-SQLite means):
  SQLite's operations on D must return SQLITE_CORRUPT
  ∧ must NOT: overflow buffers, dereference NULL, or invoke UB
```
**Source:** Section 4.2 "Malformed Database Files" — "The malformed database tests verify that SQLite finds the file format errors and reports them using the SQLITE_CORRUPT return code without overflowing buffers, dereferencing NULL pointers, or performing other unwholesome actions."

**Counterexample:** A crafted database file with an impossibly large page count causes an unchecked integer multiplication that overflows, allocating a tiny buffer, which is then written past. Classic buffer overflow from adversarial input.

**Why this matters for bridge/orbit:** Bridge consumes untrusted inputs (user-submitted code, axiom databases, sandbox manifests). Any malformed input that causes UB instead of a clean error is a sandbox-escape vector. Orbit's dispatch messages arrive over a network — a malformed message that causes UB in the dispatcher is an RCE vector.

---

### INV-XXX-006: Graceful degradation under resource exhaustion
**Core Invariant:**
```
∀ operation O, ∀ allocation site i ∈ [0, N] in O's call graph:
  if malloc fails at site i (and all subsequent sites if continuous-fail mode),
  O must return an error code
  ∧ the database must remain consistent
  ∧ no crash, no undefined behavior
```
**Source:** Section 3.1 "Out-Of-Memory Testing" — Loop testing: instrumented malloc fails at allocation 1, then 2, ..., then N. "Some SQLite operation is carried out and checks are done to make sure SQLite handled the OOM error correctly." Done twice: single-failure and continuous-failure modes.

**Counterexample:** An OOM during a commit at allocation site 47 causes the WAL header to be partially written; the database is now in an inconsistent state that integrity_check flags. Or worse: a NULL pointer from malloc is dereferenced without checking, causing a segfault.

**Why this matters for bridge/orbit:** This is directly applicable to sandbox resource limits. Bridge must verify that sandboxed code handles memory exhaustion at every allocation site without corrupting the sandbox invariant. Orbit's session multiplexer must gracefully degrade under memory pressure — a single OOM should drop one session, not corrupt the multiplexer state for all sessions.

---

### INV-XXX-007: I/O error must not introduce corruption
**Core Invariant:**
```
∀ operation O, ∀ I/O operation site i ∈ [0, N]:
  if I/O fails at site i,
  O must return an error code
  ∧ after failure simulation is disabled, PRAGMA integrity_check must pass
  (no corruption introduced by the failed I/O)
```
**Source:** Section 3.2 "I/O Error Testing" — "After the I/O error simulation failure mechanism is disabled, the database is examined using PRAGMA integrity_check to make sure that the I/O error has not introduced database corruption."

**Counterexample:** A write to a B-tree page fails halfway through (partial page write). The page is left in an inconsistent state — child pointers reference freed pages, or the page header's cell count doesn't match the actual cells. integrity_check fails.

**Why this matters for bridge/orbit:** Bridge writes execution logs and sandbox manifests to disk. A partial write due to disk-full must not leave a corrupt log entry that breaks the ledger's integrity. Orbit's dispatch table is the same: a write failure mid-update must not leave a half-written assignment.

---

### INV-XXX-008: Test coverage meta-invariant — 100% branch coverage + 100% MC/DC
**Core Invariant (meta-invariant about the codebase, not the runtime):**
```
∀ branch instruction B in core SQLite (excluding extensions):
  ∃ at least one test case that executes B-taken AND
  ∃ at least one test case that executes B-not-taken
```
**Source:** Section 7 "Test Coverage" — "The SQLite core, including the unix VFS, has 100% branch test coverage under TH3 in its default configuration as measured by gcov."

And Section 7.4: "SQLite also achieves 100% MC/DC in addition to 100% branch coverage."

**Counterexample:** A branch that is only ever taken (or only ever not-taken) in tests means that the untaken path has unknown behavior — it may contain a bug that ships to production. The classic example is defensive `if (ptr != NULL)` where `ptr` is "always" non-NULL in tests but can be NULL under production conditions.

**Why this matters for bridge/orbit:** This is a methodology invariant, not a runtime one. But it sets a standard: bridge's test suite should achieve 100% branch coverage on the execution ledger and sandbox boundary code. Orbit's dispatch engine and session isolation should similarly aim for MC/DC. The methodology of `ALWAYS()`, `NEVER()`, and `testcase()` macros constitutes a reusable pattern for any C codebase that wants to reconcile defensive code with coverage metrics.

---

### INV-XXX-009: Compound failure resilience
**Core Invariant:**
```
∀ {crash_event, I/O_error, OOM_fault} in sequence:
  recovery from crash_event must succeed even if
  recovery itself encounters I/O_error or OOM_fault
```
**Source:** Section 3.4 "Compound failure tests" — "Tests are run to ensure correct behavior when an I/O error or OOM fault occurs while trying to recover from a prior crash."

**Counterexample:** A crash recovery reads the WAL to replay transactions, but the WAL read itself hits an I/O error. The recovery code does not handle this nested error, leaving the database in an unrecoverable state — worse than the original crash.

**Why this matters for bridge/orbit:** Bridge's crash recovery for the execution ledger must be resilient to failures during recovery itself. If the ledger replay encounters a corrupt entry, it must skip it and continue — not crash again. Orbit's dispatch recovery is similar: if replaying a dispatch log encounters an I/O error, the recovery must not leave the dispatch table in an inconsistent state.

---

### INV-XXX-010: Regression test for every fixed bug
**Core Invariant (process invariant):**
```
∀ bug B reported and fixed:
  ∃ a test case T that would have exhibited B before the fix
  ∧ T is permanently added to the test suite
  ∧ T passes on every subsequent release
```
**Source:** Section 5 "Regression Testing" — "Whenever a bug is reported against SQLite, that bug is not considered fixed until new test cases that would exhibit the bug have been added to either the TCL or TH3 test suites."

**Counterexample:** A bug is fixed but no test is added. A later refactoring reintroduces the same bug. The release ships with a known regression.

**Why this matters for bridge/orbit:** This is a process invariant applicable to any engineering project. Bridge's sandbox escape bugs and orbit's session isolation bugs must each have permanent regression tests. Without them, the same escape vector can silently reopen.

---

### INV-XXX-011: Mutation testing — every branch must affect output
**Core Invariant (meta-invariant about test quality):**
```
∀ branch instruction B in core SQLite (excluding /*OPTIMIZATION-IF-{TRUE,FALSE}*/):
  mutating B (flip to unconditional jump or no-op) must cause
  at least one test case to fail
```
**Source:** Section 7.6 "Mutation Testing" — "SQLite strives to verify that every branch instruction makes a difference using mutation testing... The script steps through the generated assembly language and, one by one, changes each branch instruction into either an unconditional jump or a no-op, compiles the result, and verifies that the test suite catches the mutation."

**Counterexample:** A branch that flips without any test failure means either (a) the branch is dead code or (b) the test suite has a gap — it doesn't verify the output that the branch produces. Both are defects.

**Why this matters for bridge/orbit:** Mutation testing is the gold standard for test suite quality. Bridge's sandbox exit-code verification and orbit's dispatch correctness tests should be mutation-tested to ensure no code path is untested. A mutation that survives the test suite is an untested code path that could harbor a sandbox escape or dispatch error.

---

## Summary

This page describes SQLite's testing methodology rather than database invariants directly. However, the testing methodology implicitly defines invariants by describing what the tests verify:

1. **Data integrity invariants** (INV-001, 002, 005, 007): crash atomicity, WAL ordering, corruption detection, graceful error handling for malformed input and I/O errors.

2. **Resource invariants** (INV-003, 006): zero leaks under failure, graceful degradation at every allocation site.

3. **Correctness invariants** (INV-004): optimizer semantic preservation — same answer regardless of optimization flags.

4. **Resilience invariants** (INV-009): recovery must survive failures during recovery itself.

5. **Process/meta invariants** (INV-008, 010, 011): 100% MC/DC, regression test per bug, mutation testing. These are not runtime guarantees but engineering process constraints that produce runtime quality.

The most technically specific invariants for bridge/orbit consumption are INV-001 (atomic commit), INV-002 (WAL ordering), INV-003 (no leak under failure), and INV-007 (I/O error must not corrupt state). These are directly transferable to bridge's execution ledger design and orbit's dispatch/session isolation design.
