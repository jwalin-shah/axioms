# Owicki & Gries Oracle (1976)

Source: "An Axiomatic Proof Technique for Parallel Programs I" (Owicki & Gries, Acta Informatica, 1976, pp. 319-340).
Also: "Verifying Properties of Parallel Programs: An Axiomatic Approach" (CACM 19(5):279-285, 1976).

This is how you PROVE (not just test) that concurrent code satisfies invariants. The method extends
Hoare logic to shared-variable parallel programs. It decomposes into two obligations: **sequential
correctness** (prove each thread correct in isolation) and **interference freedom** (prove no thread
invalidates another's assertions). If both hold, the parallel composition is correct.

Every concept maps to a first-order-logic expression, a Go enforcement pattern, and specific orbit
TestAX gates.

---

## 1. Sequential Correctness

**Principle:** Each thread, considered in isolation, satisfies its pre/post-condition specification
using standard Hoare logic. You annotate the thread's code with assertions (a "proof outline") and
verify each Hoare triple locally.

**Formal definition:**
```
∀thread T, ∀Hoare triple {P} S {Q} in T:
  P ⇒ wp(S, Q)                                                (weakest precondition holds)
```
Where wp(S, Q) is the weakest precondition such that executing S from any state satisfying wp(S, Q)
guarantees Q afterward.

**Go enforcement pattern:**
- Every function's preconditions are checked at entry (nil checks, bounds checks, state checks)
- Post-conditions are verified in tests, not at runtime (Go lacks contract system)
- Explicit error returns for violated preconditions (never panic on user input)
- The Go compiler checks types but NOT logical pre/post-conditions — we must verify in tests

**orbit packages affected:**
- `pkg/circuitbreaker` — Allow() precondition: cb != nil. Allow() postcondition: if state==Open
  and timeout active, return false. AX-001 tests this postcondition.
- `pkg/sandbox` — WriteFile precondition: path must be within worktree root. resolve() enforces
  this. AX-011, AX-017 test path containment.
- `pkg/tokenrouter` — Acquire precondition: key must pass cooldown, RPM limit, MinInterval.
  AX-007 tests exhausted keys return error.
- `pkg/luaengine` — RunRule precondition: script is valid Lua, payload is valid JSON. AX-020
  tests valid result contract.

**Given by Go:** Type safety, nil-deref panic (runtime check), bounds-check panic (runtime).
**We must enforce:** Semantic pre/post-conditions via TestAX gates. Type safety is not correctness.

---

## 2. Interference Freedom

**Principle:** This is the KEY contribution of Owicki-Gries. After proving each thread correct in
isolation, you must check that NO atomic statement in one thread invalidates an assertion in
another thread's proof outline.

**Formal definition:**
```
∀thread T₁, ∀assertion p in proof outline of T₁,
∀thread T₂ ≠ T₁, ∀atomic statement a in T₂:
  {p ∧ pre(a)} a {p}                                         (a does not falsify p)
```

This is a cross-product: if T₁ has n assertions and T₂ has m atomic statements, there are
O(n × m) interference-freedom obligations. EVERY pair must be checked.

For n threads, the total obligations are O(k × n²) where k is the average thread size.

**What counts as "atomic" in Owicki-Gries:**
- An assignment to a shared variable
- A read of a shared variable (if the value matters for assertions)
- A `Lock()` / `Unlock()` call (acquire/release of mutual exclusion)
- In Go: any statement between synchronization points is NOT atomic unless explicitly
  protected by a mutex or atomic operation

**Example:**
```
Thread T₁:                          Thread T₂:
  {x = 0}                             {x = 0}
  x := x + 1                          x := x + 5
  {x = 1}                             {x = 5}
```

Sequential correctness: each Hoare triple holds (if x starts at 0, T₁ sets it to 1; T₂ sets it to 5).

Interference freedom: Does T₂'s assignment `x := x + 5` interfere with T₁'s assertion `{x = 1}`?
  `{x = 1 ∧ x = 0} x := x + 5 {x = 1}` → precondition is FALSE (x cannot be both 1 and 0),
  so this triple is vacuously true. But this is at the WRONG point — before T₂ runs, x could be 1
  (if T₁ already ran). The interference check must consider ALL intermediate states:
  `{x = 1} x := x + 5 {x = 1}` → this FAILS. After T₂ runs, x = 6 ≠ 1.

Result: interference freedom fails. This program is NOT correct under Owicki-Gries. And indeed,
the final value of x is nondeterministic (could be 1, 5, or 6 depending on interleaving).

**Go enforcement pattern:**
- Every shared variable access must be protected by a mutex or atomic operation
- Mutex-protected sections become the "atomic statements" in O-G terms
- Channel operations (send/recv) are atomic synchronization points
- TestAX gates run concurrent goroutines and assert invariants hold after all interleavings
- `go test -race` detects happens-before violations but NOT Owicki-Gries violations
  (see Section 4)

**orbit packages affected:**
- `pkg/circuitbreaker` — Allow() (read), RecordFailure() (write), RecordSuccess() (write)
  all protected by cb.mu. The atomic unit is the locked section. AX-003: IsAvailable()
  is side-effect-free — this IS an interference-freedom gate (a read doesn't invalidate
  another thread's state assumption).
- `pkg/tokenrouter` — Per-key CAS-based buckets. The atomic unit is the CAS operation.
  Interference-freedom gate: when goroutine A reads bucket count, goroutine B's CAS on
  the same bucket must not invalidate A's assertion. Lazy expiry uses atomic CAS on
  BucketTime.
- `pkg/ggrind` — AX-035: NoPanicOnConcurrentSubmitStop. This is a direct interference-freedom
  test: Submit() and Stop() running concurrently must not panic or corrupt shared state.
- `pkg/scheduler` — MemDistLock with per-key locks. DistLock.TryAcquire() and
  DistLock.Release() are atomic sections. AX-005: double release must not panic
  (interference-freedom: release must be idempotent under concurrent access).

**Given by Go:** sync.Mutex, sync.RWMutex, sync/atomic, channel happens-before guarantees.
**We must enforce:** Cross-goroutine assertion stability via interference-freedom TestAX gates.

---

## 3. The Composition Rule: Sequential + Interference-Free = Concurrently Correct

**Principle:** This is the central formula. If you prove (a) each thread correct in isolation
and (b) all cross-thread assertions interference-free, the parallel composition is correct.

**Formal rule (Owicki-Gries Parallel Composition):**
```
  {P₁} S₁ {Q₁}  ∧  {P₂} S₂ {Q₂}  ∧  IF(S₁, S₂)
  ───────────────────────────────────────────────
  {P₁ ∧ P₂} S₁ ∥ S₂ {Q₁ ∧ Q₂}
```

Where IF(S₁, S₂) means "S₁ and S₂ are interference-free proof outlines."

**What this means for us:**
```
ConcurrentCorrectness(program) ⇔
  ∀thread t ∈ program: SequentiallyCorrect(t)
  ∧ ∀thread t₁, t₂, t₁≠t₂: InterferenceFree(t₁, t₂)
```

If either component fails, the program is NOT proven correct. The race detector can catch SOME
interference-freedom violations (data races), but not all (see Section 4). A program that passes
`go test -race` may still have Owicki-Gries violations — meaning it is NOT interference-free
and thus NOT concurrently correct.

**orbit application:**
- For every package with shared mutable state, we need BOTH:
  1. Sequential correctness tests (normal unit tests)
  2. Interference-freedom tests (concurrent goroutine tests with invariants)
- The race detector is a necessary condition, NOT a sufficient condition
- A TestAX gate that passes `-race` but fails under concurrent stress is an O-G violation

**Given by Go:** Nothing directly. The race detector helps but is incomplete.
**We must enforce:** Both obligations explicitly. The contract requires it.

---

## 4. Go's Race Detector: What It Catches and What It Doesn't

**Principle:** Go's race detector (ThreadSanitizer/TSan) detects happens-before violations
dynamically. It instruments memory accesses at runtime and reports pairs of conflicting
accesses that are not ordered by happens-before in the CURRENT execution.

### What the Go race detector CATCHES:

**C-consistent races** — races that actually manifest in the observed execution trace.
A race is "C-consistent" if it is consistent with the concrete schedule that occurred.

```
∀access a₁, a₂: conflicting(a₁, a₂) ∧ ¬happens-before(a₁, a₂) in current execution
→ race detected
```

This catches:
- Unsynchronized concurrent reads and writes to the same variable
- Mutex-unprotected shared state mutation
- Channel send/close without happens-before ordering
- Race conditions that happen to trigger during the test run

### What the Go race detector DOES NOT catch:

1. **Races in unexecuted code paths** — only instrumented code that actually runs is checked.
   If a test doesn't cover a branch, races there are invisible.
   ```
   ∀race in code_path: ¬executed(code_path) ⇒ race NOT detected
   ```

2. **Races whose problematic interleaving does not occur** — TSan only sees ONE schedule.
   A race that requires a specific interleaving not exercised is invisible.
   ```
   ∀race: ¬occurs_in_current_schedule(race) ⇒ race NOT detected
   ```
   This is the fundamental difference from Owicki-Gries: O-G proves absence across ALL
   interleavings. TSan proves presence in ONE interleaving.

3. **Owicki-Gries interference-freedom violations that are NOT data races** — two threads can
   be properly synchronized (no happens-before violation) but still violate an assertion.
   Example: T₁ sets x=1, T₂ reads x=1 and sets y=2, T₁ reads y expecting 0. Each access is
   properly synchronized (mutex around each pair), so TSan sees no race. But the ASSERTION
   "y=0" in T₁ is invalidated by T₂ — this is a PROVABLE O-G violation, but NOT a data race.
   ```
   ∀violation: synchronized_but_assertion_broken(violation) ⇒ TSan silent
   ```

4. **Races hidden by synchronization primitives TSan doesn't model** — condition variables,
   lost signals, spurious wakeups. TSan models mutex, channel, and atomic happens-before but
   not all synchronization patterns.
   ```
   ∀pattern: ¬tracked_by_tsan(pattern) ⇒ races in pattern NOT detected
   ```

5. **Races beyond the 8192 goroutine limit** — the Go race detector has a finite shadow
   memory and goroutine ID space.
   ```
   ∀race: goroutine_count > 8192 ⇒ race may NOT be detected
   ```

6. **Static/potential races** — Owicki-Gries can prove that a race COULD happen even if it
   didn't in a given run. The race detector cannot do this; it only sees what happened.
   ```
   ∀race: ∃schedule_where(race_occurs) but ¬occurs_in_current_schedule
         ⇒ O-G can detect, TSan cannot
   ```

### Summary table:

| Property | Go Race Detector (TSan) | Owicki-Gries |
|----------|------------------------|--------------|
| Scope | Dynamic (one execution) | Static (all interleavings) |
| Detects | Data races (happens-before violations) | Interference-freedom violations |
| Guarantee | Sound for races in the run | Complete iff sequential correctness + IF |
| Misses | Races not executed, assertion violations w/o data races | Nothing (if proofs are complete) |
| Cost | Low (runtime instrumentation, ~10x slowdown) | High (manual proof, O(n²) obligations) |
| orbit use | CI gate (`go test -race`) | TestAX gates for critical shared-state paths |

**orbit rule:** `go test -race` passes is a NECESSARY condition for any TestAX gate that uses
concurrent goroutines. It is NOT sufficient. The TestAX gate must also assert invariants hold
under repeated concurrent stress (dozens or hundreds of iterations) to catch schedule-dependent
violations that the race detector misses.

---

## 5. TLA+ Relationship

**Principle:** TLA+ (Temporal Logic of Actions, Lamport) model-checks for Owicki-Gries violations
at the SPEC level. It exhaustively explores all interleavings of actions against declared
invariants.

### How TLA+ maps to Owicki-Gries:

| Owicki-Gries concept | TLA+ equivalent |
|---------------------|-----------------|
| Proof outline (assertions in code) | Invariant (predicate over state) |
| Atomic statement a | Action (Next-state relation) |
| {p ∧ pre(a)} a {p} (interference freedom) | TLC checks: Invariant ∧ Action ⇒ Invariant' |
| Sequential correctness | Each action preserves the invariant in isolation |
| Parallel composition | Conjunction of actions (disjunct in Next) |
| Proof obligation: ∀ assertions × ∀ statements | TLC exhaustively explores all state-action pairs |

### What TLA+ provides that Go cannot:

1. **Exhaustive exploration of ALL interleavings** — TLC checks every possible sequence of
   actions up to a bounded model size. No scheduling-dependent misses.

2. **Counterexample traces** — when TLC finds an invariant violation, it produces the exact
   sequence of states and actions that led to it. This is a direct interference-freedom
   counterexample: "action a from thread T₂ invalidated assertion p in thread T₁."

3. **Invariant preservation proofs** — `Invariant ∧ [Next]_vars ⇒ Invariant'` is provably
   equivalent to the O-G interference-freedom check for that invariant.

4. **Spec-level, not code-level** — TLA+ proves the SPEC is correct. The code must still
   faithfully implement the spec. This is the spec-code gap.

### orbit relevance:

- TLA+ is appropriate for ALGORITHM-LEVEL concurrent correctness (circuit breaker state
  machine, tokenrouter bucket algorithm, WRR distribution)
- TestAX gates are appropriate for CODE-LEVEL concurrent correctness (does this specific
  Go implementation satisfy the invariant?)
- Both are needed: TLA+ for the design, TestAX for the implementation
- The tensor equations in `pkg/circuitbreaker/invariants.md` are TLA+-style invariants
  expressed as first-order logic over state variables

**orbit rule:** Any new concurrent algorithm (3+ goroutines, shared mutable state, custom
synchronization) should have a TLA+ spec BEFORE Go implementation. The TLA+ invariant
becomes the tensor equation in the TestAX gate. The TestAX gate proves the Go code
implements the spec.

---

## 6. Invariant Categories: Formal Expression and Go Mapping

### 6.1 Partial Correctness

**Definition:** If the program terminates, the result satisfies the postcondition.

**Invariant:**
```
∀execution e of program P with input x:
  terminates(e) ⇒ postcondition(result(e), x)
```

**Go provides:** Nothing. Go has no contract system, no pre/post-condition checking.
**We enforce:** TestAX gates that run the function and assert the postcondition:
```go
func TestAX_Postcondition(t *testing.T) {
    result := functionUnderTest(input)
    // ∀ valid input: result satisfies postcondition
    assertPostcondition(t, result, input)
}
```

**orbit examples:** AX-020 (luaengine valid result contract), AX-003 (circuitbreaker
IsAvailable side-effect-free), AX-034 (WAL commit record durable before install).

### 6.2 Mutual Exclusion

**Definition:** At most one thread is executing in a critical section at any time.

**Invariant:**
```
∀threads t₁, t₂, ∀time τ:
  t₁ ≠ t₂ ⇒ ¬(in_critical(t₁, τ) ∧ in_critical(t₂, τ))
```

**Go provides:** `sync.Mutex.Lock()/Unlock()` guarantees mutual exclusion at runtime.
  `sync.RWMutex` provides shared-read, exclusive-write mutual exclusion.
**We enforce:** For custom synchronization (CAS-based, channel-based), TestAX gates
  that run concurrent goroutines and assert no concurrent critical section entry:
```go
func TestAX_MutualExclusion(t *testing.T) {
    var inCritical atomic.Int32
    var wg sync.WaitGroup
    for i := 0; i < N; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            enterCriticalSection()
            count := inCritical.Add(1)
            assert(t, count == 1, "mutual exclusion violated")
            inCritical.Add(-1)
            leaveCriticalSection()
        }()
    }
    wg.Wait()
}
```

**orbit examples:** AX-023 (dispatch concurrency cap), AX-002 (scheduler expired lock
reacquirable), AX-005 (scheduler MemDistLock double release).

### 6.3 Deadlock Freedom

**Definition:** In every reachable state, at least one thread can make progress.
Equivalently: no state where ALL threads are blocked waiting for each other.

**Invariant:**
```
∀reachable state s:
  ∃thread t: can_make_progress(t, s)
```

**Go provides:** The Go runtime detects deadlock when ALL goroutines are asleep
  (blocked on channel, mutex, etc.) and panics with "fatal error: all goroutines
  are asleep - deadlock!" This is a RUNTIME check, not a compile-time guarantee.
  It only detects TOTAL deadlock (all goroutines blocked), not partial deadlock
  (a subset blocked indefinitely).
**We enforce:** TestAX gates that run concurrent operations with a timeout and
  assert all goroutines complete:
```go
func TestAX_DeadlockFreedom(t *testing.T) {
    done := make(chan struct{})
    go func() {
        concurrentOperation()
        close(done)
    }()
    select {
    case <-done:
        // pass
    case <-time.After(5 * time.Second):
        t.Fatal("deadlock: operation did not complete within timeout")
    }
}
```

**orbit examples:** AX-024 (dispatch clean shutdown on cancel), AX-005 (tokenrouter
router shutdown idempotent), AX-035 (ggrind no panic on concurrent submit/stop).

### 6.4 Starvation Freedom

**Definition:** Every thread that attempts to enter a critical section eventually
succeeds. No thread is indefinitely postponed.

**Invariant:**
```
∀thread t:
  t attempts to enter critical section ⇒ eventually(t enters critical section)
```

**Go provides:** `sync.Mutex` is NOT starvation-free (no fairness guarantee). A
  goroutine can be repeatedly beaten to Lock() by other goroutines. The mutex
  has a "starvation mode" (Go 1.9+) that kicks in after 1ms of waiting, but
  this is a mitigation, not a proof.
**We enforce:** TestAX gates that run N goroutines through a critical section
  and assert ALL complete within a deadline:
```go
func TestAX_StarvationFreedom(t *testing.T) {
    var completions atomic.Int32
    for i := 0; i < N; i++ {
        go func(id int) {
            for j := 0; j < K; j++ {
                mutex.Lock()
                // critical section
                mutex.Unlock()
            }
            completions.Add(1)
        }(i)
    }
    // wait with timeout; assert completions.Load() == N
}
```

**orbit examples:** AX-010 (WRR distribution preserves weight ratio — ensures
each backend gets its fair share over time), AX-008 (tokenrouter two healthy
keys distribute evenly), AX-010 (tokenrouter min interval paces key reuse).

### 6.5 Interference Freedom

**Definition:** No atomic statement in one thread invalidates an assertion in
another thread's proof outline. This is THE Owicki-Gries invariant.

**Invariant:**
```
∀threads t₁, t₂, t₁ ≠ t₂:
  ∀assertion p in proof outline of t₁,
  ∀atomic statement a in t₂:
    {p ∧ pre(a)} a {p}
```

**Go provides:** Nothing. This is the invariant we must prove ourselves. The
  race detector catches SOME interference-freedom violations (data races) but
  not all (synchronized assertion violations — see Section 4).
**We enforce:** TestAX gates that exercise the cross-product of shared-state
  operations concurrently and assert the invariant holds:
```go
func TestAX_InterferenceFreedom(t *testing.T) {
    // For shared state S with operations O₁, O₂, ..., Oₙ:
    // Run ALL pairs (Oᵢ, Oⱼ) concurrently for many iterations
    // Assert invariant I(S) holds after every interleaving
    for iter := 0; iter < 1000; iter++ {
        state := newState()
        var wg sync.WaitGroup
        wg.Add(2)
        go func() { defer wg.Done(); op1(state) }()
        go func() { defer wg.Done(); op2(state) }()
        wg.Wait()
        assertInvariant(t, state)
    }
}
```

**orbit examples:** AX-003 (IsAvailable side-effect-free — read doesn't mutate
state), AX-035 (no panic on concurrent submit/stop — no shared state corruption),
AX-005 (shutdown idempotent — multiple concurrent shutdowns don't break invariants),
AX-015 (sandbox write-read consistency under concurrent access).

---

## 7. What Go Provides vs What We Must Enforce

| Invariant Category | Go Provides | We Must Enforce (TestAX) | O-G Obligation |
|-------------------|-------------|--------------------------|----------------|
| **Type safety** | Compile-time type checking | N/A (compiler guarantee) | Not an O-G concern |
| **Memory safety** | Bounds checks, nil-deref panic | TestAX for nil handling (AX-006) | Precondition in Hoare triple |
| **Data race detection** | `go test -race` (TSan) | TestAX for races TSan misses | Partial: catches some IF violations |
| **Mutual exclusion** | sync.Mutex, sync.RWMutex | TestAX for custom sync (CAS, channel-based) | Atomicity of critical sections |
| **Deadlock detection** | Runtime (all goroutines asleep → panic) | TestAX with timeouts for partial deadlock | Progress obligation |
| **Starvation freedom** | Mutex starvation mode (Go 1.9+) | TestAX for fairness (WRR, pacing) | Liveness obligation |
| **Interference freedom** | NOTHING | TestAX for cross-goroutine assertion stability | THE O-G obligation |
| **Sequential correctness** | NOTHING | TestAX for pre/post-conditions | THE O-G obligation |
| **Invariant preservation** | NOTHING | TestAX for state transition exhaustiveness | Both O-G obligations together |

---

## 8. Map to Existing orbit TestAX Gates

### Interference-Freedom Gates (existing):

| AX ID | Package | What It Proves | O-G Category |
|-------|---------|---------------|--------------|
| AX-003 | circuitbreaker | IsAvailable() is side-effect-free (read doesn't mutate state) | IF: read assertion |
| AX-035 | ggrind | No panic on concurrent Submit/Stop | IF: shared state safety |
| AX-005 | tokenrouter | Router shutdown idempotent | IF: shutdown assertion stability |
| AX-005 | store | WAL double close no panic | IF: close idempotence |
| AX-005 | scheduler | MemDistLock double release | IF: release idempotence |
| AX-015 | sandbox | Write-read consistency | IF: concurrent write/read |

### Mutual Exclusion Gates (existing):

| AX ID | Package | What It Proves | O-G Category |
|-------|---------|---------------|--------------|
| AX-002 | scheduler | Expired lock reacquirable | ME: lock lifecycle |
| AX-023 | dispatch | Concurrency cap respected | ME: bounded concurrency |

### Partial Correctness Gates (existing):

| AX ID | Package | What It Proves | O-G Category |
|-------|---------|---------------|--------------|
| AX-001 | circuitbreaker | Open circuit blocks traffic | PC: Allow() postcondition |
| AX-008 | circuitbreaker | HalfOpen success → Closed | PC: state transition |
| AX-020 | luaengine | Valid result contract | PC: RunRule postcondition |
| AX-034 | store | Commit record durable before install | PC: WAL ordering |
| AX-010 | tokenrouter | RecordKeyUsage on every outcome | PC: counter wiring |
| AX-026 | dispatch | Result ordering preserved | PC: ordering postcondition |

### Deadlock/Starvation Freedom Gates (existing):

| AX ID | Package | What It Proves | O-G Category |
|-------|---------|---------------|--------------|
| AX-024 | dispatch | Clean shutdown on cancel | DF: cancellation unblocks |
| AX-010 | tokenrouter | Min interval paces key reuse | SF: starvation prevention |
| AX-008 | tokenrouter | Two healthy keys distribute evenly | SF: fairness |

### Gaps: O-G Invariants We Need New TestAX Gates For

| Priority | Package | O-G Obligation | What to Test |
|----------|---------|---------------|--------------|
| **P0** | tokenrouter | Interference-freedom: concurrent Acquire | N goroutines calling Acquire() concurrently; assert per-key bucket invariants hold |
| **P0** | circuitbreaker | Interference-freedom: concurrent Allow + RecordFailure | Allow() and RecordFailure() running concurrently; assert no state corruption |
| **P1** | dispatch | Deadlock freedom: concurrent dispatch | N concurrent Run() calls; assert all complete or cancel cleanly |
| **P1** | tokenrouter | Starvation freedom: key pacing fairness | Verify that over N acquires, no key is starved (each gets proportional share) |
| **P1** | scheduler | Interference-freedom: concurrent Schedule + Remove | Add/Remove/Every running concurrently; assert job list invariant |
| **P2** | sandbox | Interference-freedom: concurrent WriteFile + ReadFile | Write and Read on same file from different goroutines; assert consistency |
| **P2** | congestion | Interference-freedom: concurrent Compile + Run | Compile and Run on shared VM from different goroutines; assert no corruption |

---

## 9. Owicki-Gries Proof Template for orbit

When adding a new concurrent component to orbit, follow this template:

### Step 1: Declare the invariant
```
∀shared_state S: invariant(S)
```
Express as a tensor equation like the existing ones in `pkg/circuitbreaker/invariants.md`.

### Step 2: Prove sequential correctness for each thread
```
For each goroutine function f:
  {pre(f)} f_body {post(f)}
```
Write unit tests that verify the function's postcondition given valid preconditions.

### Step 3: Prove interference freedom for each cross-thread pair
```
For each assertion p in thread T₁'s proof outline,
for each atomic statement a in thread T₂ (T₁ ≠ T₂):
  {p ∧ pre(a)} a {p}
```
Write concurrent tests that run both operations simultaneously and assert p holds.

### Step 4: Compose
```
If steps 2 and 3 hold, then {P₁ ∧ P₂} T₁ ∥ T₂ {Q₁ ∧ Q₂}
```
The TestAX gate satisfies this iff: `go test -race` passes AND the invariant assertions
hold under repeated concurrent stress (at least 100 iterations to flush out
schedule-dependent failures).

### Step 5: Run the race detector
```
go test -race -run TestAX -count=1 ./pkg/<package>/
```
Race detector must pass. This is the P0 gate. Then run with `-count=100` for stress.

---

## 10. Cross-Reference: O-G Obligations × orbit Packages

| Package | Sequential Correctness | Interference Freedom | Mutual Exclusion | Deadlock Freedom | Starvation Freedom |
|---------|----------------------|---------------------|-----------------|------------------|-------------------|
| circuitbreaker | AX-001, AX-002, AX-008 | AX-003, AX-004 | sync.Mutex (built-in) | Timeout-based | WRR: AX-010 |
| tokenrouter | AX-007, AX-010 | AX-005 | Per-key CAS (built-in) | AX-005 | AX-008, AX-010 |
| sandbox | AX-011, AX-012, AX-013 | AX-015, AX-017 | Per-sandbox root | N/A (single-goroutine) | N/A |
| luaengine | AX-020 | AX-019 (fresh state) | N/A (single-goroutine) | N/A | N/A |
| dispatch | AX-026 | AX-025 | AX-023 | AX-024 | N/A (ordered results) |
| scheduler | AX-003 | AX-005 | AX-002 | Timeout-based | Cron-based |
| ggrind | N/A | AX-035 | Channel-based | AX-035 | N/A |
| store | AX-034 | AX-005 | WAL order | N/A | N/A |
| congestion | AX-003 | **GAP** | N/A (single-goroutine) | N/A | N/A |
| matrix | AX-003, AX-004, AX-006 | N/A | N/A | N/A | N/A |
| tensorlogic | AX-037 | N/A | N/A | N/A | N/A |
| bytecodevm | AX-036 | N/A | N/A | N/A | N/A |

---

## Key References

- Owicki & Gries, "An Axiomatic Proof Technique for Parallel Programs I," Acta Informatica 6:319-340, 1976.
- Owicki & Gries, "Verifying Properties of Parallel Programs: An Axiomatic Approach," CACM 19(5):279-285, 1976.
- Lamport, "Verification and Specification of Concurrent Programs," https://lamport.azurewebsites.net/pubs/lamport-verification.pdf
- Lamport, "The 'Hoare Logic' of Concurrent Programs," https://lamport.azurewebsites.net/pubs/control.pdf
- Go Data Race Detector: https://go.dev/doc/articles/race_detector
- TLA+ Home: https://lamport.azurewebsites.net/tla/tla.html
- orbit circuitbreaker invariants: `pkg/circuitbreaker/invariants.md`
- orbit axiom catalog: `axioms/AXIOMS.md`
- orbit ADR-022 (retired Lean, adopted TestAX): `docs/ADR.md`
