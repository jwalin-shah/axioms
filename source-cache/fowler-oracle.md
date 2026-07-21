# Fowler Oracle (1999/2002)

Source: "Refactoring: Improving the Design of Existing Code" (Martin Fowler, Addison-Wesley, 1st ed. 1999, 2nd ed. 2018).
Also: "Patterns of Enterprise Application Architecture" (Fowler, 2002), "Refactoring to Patterns" (Kerievsky, 2004).

This is how you IMPROVE code without changing what it does. Refactoring is a behavior-preserving transformation.
The test suite is the safety net. Every concept maps to a transformation rule, a pre/post-condition invariant,
and a detection mechanism that works across language paradigms.

---

## 1. The Definition of Refactoring

**Principle:** Refactoring is a change to the internal structure of software that does not change its
observable behavior. It is NOT rewriting. It is NOT "fixing bugs while reorganizing." It is a
sequence of small, reversible steps, each verified by tests.

**Invariant:**
```
∀refactoring R: behavior(R(code)) = behavior(code)
∀step s in R: tests pass before s ∧ tests pass after s
```

**Purpose:** Without this invariant, "refactoring" is just "changing code and hoping." The test suite is the proof that behavior is preserved. If a test fails after a refactoring step, either the step broke something (undo it) or the test was coupled to implementation details (fix the test first, then retry).

**Enforcement patterns:**
- **Functional:** Property-based tests (QuickCheck, Hedgehog) — test invariants across random inputs, not specific behaviors. The invariant survives refactoring because it's about properties, not implementation.
- **Imperative/OO:** Unit test suite as safety net. Red-green-refactor: write failing test, make it pass, refactor. The test stays green through every step.
- **Dynamic:** Same as OO but with more reliance on integration tests (types don't catch interface changes). `pytest`, `rspec`, `jest` — test runners that give fast feedback.
- **Concurrent:** Stress tests + race detector. Refactoring concurrent code requires proving no new races. `go test -race`, ThreadSanitizer, loom.

**orbit packages affected:**
- Every refactoring in orbit must pass `go test -race ./pkg/...` before and after.
- `pkg/circuitbreaker` — refactored from Hystrix-style to add Envoy-style counters. Tests stayed green.
- `pkg/tokenrouter` — refactored bucket expiry from eager (timer-based) to lazy (on Acquire). Behavior preserved: same keys expire at the same wall-clock time.

---

## 2. Code Smells — "When to Refactor"

**Principle:** A code smell is a surface indication that usually corresponds to a deeper problem.
It is not a bug — the code works. But it is a signal that the design is decaying.
Smells are heuristics, not rules. They are the "why" that triggers a refactoring.

**Canonical smells and their invariants:**

| Smell | Invariant Violated | Detection |
|---|---|---|
| **Duplicated Code** | ∀logic block B: B appears exactly once | Copy-paste detection (PMD, SonarQube, `jscpd`) |
| **Long Method** | ∀method: fits on one screen | `golangci-lint` `funlen`, `eslint` `max-lines-per-function` |
| **Large Class** | ∀class: single responsibility | `golangci-lint` `gocritic`, cohesion metrics (LCOM) |
| **Long Parameter List** | ∀function: ≤ 4 parameters | `golangci-lint` `revive` `max-params` |
| **Divergent Change** | ∀concern: lives in exactly one module | Change frequency per file (git history) |
| **Shotgun Surgery** | ∀change: touches ≤ 3 files | Change coupling (files that always change together) |
| **Feature Envy** | ∀method: accesses more foreign data than own data | Static analysis: count field accesses by owner |
| **Data Clumps** | ∀data group: fields that always appear together are one type | Find parameter groups that repeat across signatures |
| **Primitive Obsession** | ∀domain concept: has its own named type | Find `string`/`int` used where a newtype belongs |
| **Switch Statements** | ∀type dispatch: polymorphism over switch | Find `switch` on type code (replace with interface) |
| **Comments** | ∀comment: explains what, not why — what should be the code | `grep` for "// " that explain mechanics |
| **Lazy Element** | ∀abstraction: justifies its existence | Find classes/functions that are pass-through only |

**Purpose:** Smells are the early warning system. They don't cause bugs today, but they make bugs inevitable tomorrow. Every smell increases the cost of future changes. The smell list is the triage queue for refactoring.

**orbit packages affected:**
- `pkg/tokenrouter` — Data Clumps: `keyID`, `apiKey`, `providerName` always travel together → should be a `Key` struct (currently separate params)
- `pkg/dispatch` — Long Method: `post()` is 80+ lines, handles HTTP, retry, and error classification. Should be 3 functions.
- `pkg/circuitbreaker` — Primitive Obsession: `State` is `int`, failures/successes are `int`. Should be newtypes with validation.
- `pkg/sandbox` — Switch Statements: `Shell()` dispatches on command type with a switch. Could be a `Runner` interface.

---

## 3. The Refactoring Catalog

**Principle:** Every refactoring has a name, a motivation, a mechanics (step-by-step instructions), and examples.
The catalog is the shared vocabulary — teams that share refactoring names communicate more precisely.
"Extract method" means something specific, as does "replace conditional with polymorphism."

**Key refactorings and their pre/post conditions:**

### Composing Methods
| Refactoring | Pre-condition | Post-condition |
|---|---|---|
| **Extract Method** | Block of code with well-defined purpose | New method, original calls it. Same behavior. |
| **Inline Method** | Method body is as clear as the name | Method removed, body inlined at call sites |
| **Extract Variable** | Expression is complex | Named variable, expression assigned to it |
| **Inline Temp** | Temp variable used once | Variable removed, expression used directly |
| **Replace Temp with Query** | Temp holds result of expression | Method returns expression, temp removed |
| **Split Temporary Variable** | Same temp assigned twice for different purposes | Two separate temps, each for one purpose |

### Moving Features
| Refactoring | Pre-condition | Post-condition |
|---|---|---|
| **Move Method** | Method uses more features of another class | Method moved to that class |
| **Move Field** | Field used more by another class | Field moved to that class |
| **Extract Class** | Class does work of two | Two classes, each with single responsibility |
| **Inline Class** | Class does almost nothing | Class removed, features moved to users |
| **Hide Delegate** | Client calls `a.b.c()` | Client calls `a.c()`, which delegates to `a.b.c()` |

### Organizing Data
| Refactoring | Pre-condition | Post-condition |
|---|---|---|
| **Replace Magic Number with Symbolic Constant** | Literal appears in code | Named constant, literal replaced |
| **Encapsulate Field** | Public field | Private field, getter/setter |
| **Replace Record with Data Class** | Raw map/struct for domain data | Typed class with named accessors |
| **Replace Type Code with Class** | Int/enum for type | Class hierarchy, one subclass per type |

### Simplifying Conditionals
| Refactoring | Pre-condition | Post-condition |
|---|---|---|
| **Decompose Conditional** | Complex if condition | Named method for condition, then, else |
| **Consolidate Conditional Expression** | Same action in multiple if branches | Single condition with OR |
| **Replace Nested Conditional with Guard Clauses** | Deeply nested if-else | Guard clauses return early |
| **Replace Conditional with Polymorphism** | Switch on type code | Interface method, one impl per type |

**Purpose:** The catalog is a playbook. For every design problem, there's a refactoring that solves it. The name is the shared vocabulary — "extract method" means the same thing in Go, Rust, and Python. The mechanics differ by language, but the transformation is the same.

**orbit applications:**
- `pkg/dispatch` — Extract Method on `post()`: extract `buildRequest`, `executeHTTP`, `classifyError`, `backoff`
- `pkg/tokenrouter` — Replace Type Code with Class: `ProviderName string` → `type ProviderName struct { name string }`
- `pkg/circuitbreaker` — Decompose Conditional on `Allow()`: the timeout check is a separate method
- `pkg/sandbox` — Consolidate Conditional Expression in `resolve()`: the "path escapes" checks are scattered

---

## 4. Testing as the Enabler

**Principle:** Refactoring is impossible without tests. The tests are the proof that behavior is preserved.
Without tests, you're not refactoring — you're just changing code and hoping.

**Invariant:**
```
∀refactoring step s: all tests pass before s ∧ all tests pass after s
∀untested code U: refactoring(U) requires writing tests for U first
∀test suite T: T must be fast enough to run after every step (< 1 second for unit, < 5 seconds for integration)
```

**Purpose:** The test suite is the safety net. If a test fails during refactoring, you know exactly which step broke it. Without this, refactoring is guesswork with a high probability of introducing bugs.

**Enforcement patterns:**
- **Functional:** Property tests run on every compilation. Immutability means fewer tests needed (no state space explosion).
- **Imperative/OO:** Unit tests per class, integration tests per module. Test doubles (mocks, stubs, fakes) for isolation.
- **Dynamic:** More integration tests (compiler doesn't catch type errors). Contract tests for interfaces.
- **Concurrent:** Stress tests + race detector + deterministic simulation (like FoundationDB's simulation testing).

**orbit packages affected:**
- `pkg/circuitbreaker` — 17 TestAX tests, run in <0.2s. Fast enough to run after every refactoring step.
- `pkg/tokenrouter` — tokenrouter tests take 60s (involve real API keys). Too slow for step-by-step refactoring. Need faster unit tests.
- `pkg/sandbox` — sandbox tests create real processes, take ~0.2s each. Acceptable.
- Gap: 7 packages have invariants.md but no TestAX tests. Cannot refactor these packages safely.

---

## 5. Enterprise Application Patterns

**Principle:** (From PoEAA, 2002) Enterprise applications have recurring architectural patterns.
These are not refactorings — they are design decisions made ONCE at the architecture level.
But they MUST be applied correctly, and when they're wrong, refactoring fixes them.

**Key patterns and their invariants:**

| Pattern | Invariant | Violation |
|---|---|---|
| **Domain Model** | Business logic lives in domain objects, not services | Anemic domain (all logic in services, domain is just data) |
| **Service Layer** | Service layer is a thin facade over domain model | Fat service (domain model is anemic, service has all logic) |
| **Repository** | Mediates between domain and data mapping layer | Direct DB access in domain logic |
| **Unit of Work** | Tracks changes to objects, commits atomically | Partial commit (some objects saved, others not) |
| **Lazy Load** | Related objects loaded on demand | N+1 query problem (loop loads each related object individually) |
| **Identity Map** | Each object loaded once per transaction | Duplicate objects for same DB row |
| **Data Mapper** | Domain objects don't know about the database | Domain objects contain SQL |
| **Table Module** | One class per database table | God class for all tables |
| **Transaction Script** | One script per use case, no shared state | God script with shared state |

**Purpose:** These patterns are architectural decisions. Getting them wrong means the entire codebase is organized around the wrong abstraction. Refactoring across architectural patterns is the hardest kind of refactoring — it requires understanding both the old and new pattern, and migrating incrementally.

**orbit applications:**
- `pkg/store` — Repository pattern over WAL. The store mediates between the WAL (data layer) and callers (domain layer).
- `pkg/tokenrouter` — Service Layer over key management. The router is a facade over key acquisition, rotation, and rate limiting.
- `pkg/dispatch` — Transaction Script pattern. Each dispatch is a script that executes a sequence of steps. No shared state between dispatches.
- `pkg/circuitbreaker` — Domain Model pattern. The circuit breaker has state and behavior (Allow, RecordSuccess, RecordFailure). Not anemic.

---

## 6. The Two Hats

**Principle:** When programming, you wear one of two hats:
- **Adding function:** Adding new capabilities. Tests are written, code is added, tests pass. Refactoring is NOT done during functional changes.
- **Refactoring:** Restructuring existing code. No new tests, no new functionality. Tests stay green through every step.

**Invariant:**
```
∀development session: wear exactly one hat at a time
∀commit: either adds function OR refactors, never both
```

**Purpose:** Mixing function addition and refactoring is the #1 source of regression bugs. You change structure AND behavior simultaneously, and when a test fails, you don't know which change broke it. The two-hats rule forces you to separate the two: first refactor to make the change easy, then add the function.

**orbit enforcement:**
- Every commit is either `feat:` (adds function) or `refactor:` (changes structure, no behavior change) or `fix:` (changes behavior to match spec)
- `rtk diff "git diff HEAD"` before commit — verify the diff matches the commit type
- A `refactor:` commit that changes test expectations is a red flag (behavior changed!)

---

## The Fowler Test

For any change, ask:
1. **Am I adding function or refactoring?** (one hat at a time)
2. **Do tests pass before and after?** (behavior preserved)
3. **Is there a smell that justifies this?** (don't refactor "just because")
4. **Is this step small enough?** (can be undone with Ctrl-Z)
5. **Is there a catalog name for what I'm doing?** (if not, am I sure I know what I'm doing?)
6. **Is the test suite fast enough?** (< 1 second to run after each step)

Fowler is the discipline of improvement. Without it, code rots. With it, every change makes the code better than it was before.