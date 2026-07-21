# Lamport TLA+ Oracle (1999)

Source: "Specifying Systems" (Leslie Lamport, Addison-Wesley, 2002).
Also: "The Temporal Logic of Actions" (Lamport, ACM TOPLAS 16(3), 1994), TLA+ video course (Lamport, 2017).

This is how you SPECIFY before you implement. TLA+ is not a programming language — it's a language for
writing down what a system SHOULD do, then model-checking that it actually does it. Every concept maps
to a specification pattern, a verification strategy, and specific orbit applications.

---

## 1. Specification Before Implementation — "What, Not How"

**Principle:** Write the specification FIRST. The spec describes WHAT the system does (its behavior),
not HOW it does it. The implementation is a refinement of the spec. If the spec is wrong, the
implementation is wrong by definition.

**Invariant:**
```
∀system S: spec(S) is written before code(S)
∀change C: spec(S) is updated before code(S) is changed
∀implementation I: I refines spec(S) — every behavior of I is allowed by S
```

**Purpose:** Most bugs are specification bugs — the code does what the programmer intended, but what the programmer intended is wrong. Writing the spec first forces you to decide what "correct" means BEFORE you start coding. It's cheaper to fix a wrong spec than wrong code.

**Enforcement:**
- Before writing code: write the spec in TLA+/PlusCal or as tensor equations
- Model-check the spec: does it allow bad behaviors? Does it guarantee good ones?
- The spec is the acceptance criterion: "the code is correct" means "the code refines the spec"
- If the spec can't be written clearly, the problem isn't understood

**orbit packages affected:**
- Every package. Each `pkg/*/invariants.md` file IS a specification (in tensor equation form, not full TLA+).
- `pkg/circuitbreaker` — the state machine diagram IS a specification. The tensor equations are the formal version.
- `pkg/tokenrouter` — the rate-limit, cooldown, and bucket expiry equations ARE the specification.
- `pkg/sandbox` — the path containment invariant IS the specification.

---

## 2. Safety — "Bad Things Never Happen"

**Principle:** A safety property is an invariant: it must hold in every reachable state. If it's violated,
the violation happens at a specific point in time. "The circuit breaker never allows traffic when Open"
is a safety property. "No two goroutines hold the mutex simultaneously" is a safety property.

**Formal definition:**
```
□P  —  "always P" — P holds in every state of every behavior

Safety: □Invariant
Example: □(state = Open ∧ timeout_active → Allow() = false)
```

**Purpose:** Safety properties are the MINIMUM correctness conditions. If a safety property is violated, the system is broken at a specific, observable point. Every P0 and P1 finding is a safety violation.

**Enforcement:**
- Model checking: TLC explores all reachable states and checks the invariant
- Runtime assertions: `if !invariant { panic("safety violation") }`
- TestAX gates: `TestAX001_OpenCircuitBlocksTraffic`
- `go test -race` — the race detector checks the safety property "no data races"

**orbit packages affected:**
- `pkg/circuitbreaker` — AX-001 through AX-010 are all safety properties. Each is checked by a TestAX gate.
- `pkg/tokenrouter` — `∀k,t: RequestBuckets[k][t] ≤ RPM/60` is a safety property. If violated, the rate limit is exceeded.
- `pkg/sandbox` — `∀path: resolve(path) is within worktree root` is a safety property. If violated, sandbox escape.
- `pkg/luaengine` — `∀script: only whitelisted libraries are available` is a safety property. If violated, arbitrary code execution.

---

## 3. Liveness — "Good Things Eventually Happen"

**Principle:** A liveness property says that something eventually happens. It cannot be violated at a single point
in time — it can only be violated over an infinite behavior. "Every request eventually gets a response" is a
liveness property. "The circuit breaker eventually transitions to HalfOpen after timeout" is a liveness property.

**Formal definition:**
```
◇P  —  "eventually P" — P holds at some point in every behavior

Liveness: ◇Result
Example: ◇(state = Open → state = HalfOpen)
```

**Purpose:** Liveness is harder to test than safety. A safety violation is a counterexample — a specific state where the invariant fails. A liveness violation is an infinite behavior where the good thing never happens. You can't test for "eventually" — you can only test for "within N seconds."

**Enforcement:**
- Timeouts: if the good thing doesn't happen within T, fail
- Progress counters: "X happened N times" — if N doesn't increase, no progress
- Weak fairness: if an action is continuously enabled, it eventually executes
- Strong fairness: if an action is repeatedly enabled, it eventually executes

**orbit packages affected:**
- `pkg/circuitbreaker` — `◇(Open → HalfOpen)` — the circuit breaker eventually allows a probe. Enforced by timeout.
- `pkg/tokenrouter` — `◇(Acquire → returns key)` — Acquire eventually returns (or times out). Enforced by context deadline.
- `pkg/dispatch` — `◇(dispatch → result)` — every dispatch eventually completes (or errors). Enforced by retry budget.
- `pkg/ggrind` — `◇(pipeline → all stages complete)` — the grind pipeline eventually finishes. Enforced by context cancellation.

---

## 4. Fairness — "If It Can Happen, It Will"

**Principle:** Fairness is a constraint on the scheduler. Without fairness, a liveness property can be violated
by the scheduler simply never choosing to execute the action that would satisfy it. Fairness rules out
"the scheduler is infinitely unlucky" as a counterexample.

**Formal definition:**
```
Weak Fairness (WF_v(A)):
  (◇□(A enabled) ⇒ □◇(A executed))
  — If A is eventually always enabled, it must be executed infinitely often

Strong Fairness (SF_v(A)):
  (□◇(A enabled) ⇒ □◇(A executed))
  — If A is repeatedly enabled, it must be executed infinitely often
```

**Purpose:** Most liveness properties require at least weak fairness. Without it, any system with a loop can be "stuck" by the scheduler never choosing the action that breaks the loop. Fairness is an assumption about the scheduler, not a property of the system.

**Enforcement:**
- Go's scheduler provides weak fairness: a goroutine that is continuously runnable will eventually be scheduled
- `select` with multiple ready cases: Go randomizes the choice (fairness by randomization)
- `sync.Mutex`: Go's mutex is not fair (no FIFO guarantee). A goroutine can be starved.
- `runtime.Gosched()` — explicit yield for cooperative fairness

**orbit packages affected:**
- `pkg/tokenrouter` — key selection is round-robin (fair by construction). No key is starved.
- `pkg/ggrind` — worker pool with fair work distribution (each worker gets the next task)
- `pkg/circuitbreaker` — `Pick()` is round-robin (WRR). All backends get traffic proportional to weight.
- `pkg/dispatch` — retry with jitter prevents thundering herd (fairness across retries)

---

## 5. Refinement — "Implementation Implies Specification"

**Principle:** An implementation is a refinement of a specification if every behavior of the implementation
is allowed by the specification. The implementation can be more deterministic (fewer behaviors), but it
cannot introduce new behaviors that the spec forbids.

**Formal definition:**
```
I refines S  ⇔  ∀behavior b: b ∈ behaviors(I) → b ∈ behaviors(S)
```

**Purpose:** Refinement is the bridge between specification and implementation. It means: "the code does what the spec says, and nothing the spec doesn't allow." A refinement proof is the ultimate correctness guarantee.

**Enforcement:**
- TLC model checking: check that the implementation's state space is a subset of the spec's state space
- Simulation proofs: the implementation simulates the spec (every step of the implementation maps to a step of the spec)
- Abstraction functions: map the implementation's concrete state to the spec's abstract state
- Invariant: the abstraction function maps reachable states to spec-valid states

**orbit packages affected:**
- `pkg/circuitbreaker` — the Go implementation refines the state machine diagram. Every state transition in the Go code corresponds to a transition in the diagram.
- `pkg/tokenrouter` — the Go implementation refines the rate-limit equation. Every `Acquire` call respects the bucket count.
- `pkg/sandbox` — the Go implementation refines the path containment spec. Every file operation goes through `resolve()`.

---

## 6. Stuttering Steps — "What the Spec Doesn't Say"

**Principle:** A specification allows stuttering steps — steps where nothing changes. This is critical:
the implementation might take 3 steps to do what the spec does in 1 step. The spec allows those extra
steps as stuttering. Without stuttering, refinement would be impossible (the step counts would never match).

**Formal definition:**
```
Stuttering step: s → s  (the state doesn't change)
A specification allows stuttering steps at any point.
```

**Purpose:** Stuttering is the mechanism that makes refinement possible. The implementation can take more steps than the spec, as long as the extra steps don't change the observable state. This is the formal justification for "the implementation can do extra work as long as the result is the same."

**Enforcement:**
- The spec describes OBSERVABLE behavior, not internal steps
- The implementation can add logging, metrics, caching — as long as the observable state is unchanged
- A test checks the observable state, not the internal steps
- `TestAX` tests check the invariant, not the implementation path

**orbit packages affected:**
- Every package. The spec says WHAT, the implementation says HOW. The implementation can add logging, metrics, caching, optimization — as long as the observable behavior matches the spec.
- `pkg/circuitbreaker` — the spec says `Allow() returns false when Open`. The implementation can check the timeout, update metrics, log — as long as `Allow()` returns false.
- `pkg/tokenrouter` — the spec says `Acquire respects the rate limit`. The implementation can rotate keys, check cooldown, update buckets — as long as the rate limit is respected.

---

## 7. PlusCal — "TLA+ for Programmers"

**Principle:** PlusCal is an algorithm language that compiles to TLA+. It looks like a programming language
(while loops, if-then-else, variables) but has the semantics of TLA+ (states, transitions, stuttering).
It's the bridge between "I can write pseudocode" and "I can prove properties."

**Purpose:** PlusCal makes TLA+ accessible. You write the algorithm in a familiar syntax, and the PlusCal translator generates the TLA+ specification. Then you model-check the TLA+ spec with TLC. This is the workflow: write PlusCal → translate to TLA+ → model-check with TLC → find counterexamples → fix the algorithm → repeat.

**Example (PlusCal for a lock):**
```
--algorithm Lock {
  variable locked = FALSE;
  process (Acquirer \in {1, 2}) {
    acquire:
      await ~locked;
      locked := TRUE;
    release:
      locked := FALSE;
      goto acquire;
  }
}
```

**orbit applications:**
- `pkg/circuitbreaker` — the state machine is a PlusCal algorithm. States are labels, transitions are gotos.
- `pkg/tokenrouter` — the rate limiter is a PlusCal algorithm. Buckets are variables, Acquire is a process.
- `pkg/dispatch` — the retry loop is a PlusCal algorithm. Attempts are a counter, backoff is a timer.

---

## 8. Model Checking — "Brute-Force Proof"

**Principle:** TLC (the TLA+ model checker) explores all reachable states of a finite model of the specification.
If the invariant is violated, TLC produces a counterexample: a sequence of states leading to the violation.
This is a BUG in the specification — a case the spec didn't handle.

**Invariant:**
```
∀finite model M: TLC(M) = {states reachable from Init | all transitions}
∀invariant I: TLC checks I in every reachable state
∀counterexample: TLC produces a trace from Init to the state where I fails
```

**Purpose:** Model checking is exhaustive testing for specifications. It finds bugs that human review misses. A counterexample from TLC is a concrete scenario where the spec is wrong — the most valuable kind of bug report.

**Enforcement:**
- Model-check the spec before implementing
- TLC counterexample → fix the spec → model-check again → repeat until clean
- The spec is the acceptance criterion: "the implementation is correct" means "the implementation refines a model-checked spec"
- For orbit, the tensor equations are the spec, and TestAX gates are the model check (for a finite set of inputs)

**orbit packages affected:**
- `pkg/circuitbreaker` — the state machine is small enough to model-check exhaustively. 3 states × 3 events = 9 transitions. TestAX coverage is exhaustive for the state machine but not for concurrent interleaving.
- `pkg/tokenrouter` — the rate limiter is too large for exhaustive model checking (too many keys, too many time windows). TestAX checks a finite set of scenarios.
- `pkg/sandbox` — path containment is model-checkable: a finite set of path inputs, each checked against the resolve() function.

---

## The TLA+ Test

For any system, ask:
1. **Spec:** Is there a written specification that says what this system SHOULD do?
2. **Safety:** What bad thing must never happen? How do I prove it doesn't?
3. **Liveness:** What good thing must eventually happen? How do I prove it does?
4. **Fairness:** Does the liveness property depend on fairness assumptions? Are they valid?
5. **Refinement:** Does the implementation refine the spec? Can I prove it?
6. **Stuttering:** Does the spec describe observable behavior, not internal steps?
7. **Model checking:** Can I model-check the spec? For what finite model?

TLA+ is the proof that specification comes first. A program without a spec is a program that is correct by accident.