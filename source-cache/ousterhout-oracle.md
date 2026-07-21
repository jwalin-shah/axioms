# Ousterhout Oracle (2018)

Source: "A Philosophy of Software Design" (John Ousterhout, Yaknyam Press, 1st ed. 2018, 2nd ed. 2021).
Also: Ousterhout's Stanford CS 190 lecture series (YouTube, 2016-2020).

This is how you DESIGN software that stays maintainable over time. Ousterhout's central thesis:
complexity is incremental — each small decision either adds a little complexity or removes a little.
The goal is to design modules that make the common case simple and the complex case possible.

---

## 1. Deep Modules

**Principle:** The best modules are DEEP — they provide a large amount of functionality through
a simple interface. The interface is the COST (what the caller must learn and manage).
The implementation is the BENEFIT (what the module does for the caller). Depth = benefit / cost.

**Invariant:**
```
∀module M: depth(M) = |functionality provided| / |interface complexity|
∀design decision D: D should increase depth(M), not decrease it
```

**Purpose:** Shallow modules are everywhere. They have complex interfaces and simple implementations — the caller does all the work, the module just passes data through. A deep module is the opposite: the caller says "do this," and the module handles all the details. The Unix file I/O interface is deep: `open`, `read`, `write`, `close` — 4 functions that hide device drivers, block allocation, caching, and permissions.

**Enforcement patterns:**
- **Functional:** A module exports few functions with rich behavior. `map`, `filter`, `fold` — 3 functions that replace thousands of loops. The depth comes from composability.
- **Imperative/OO:** A class has few public methods, many private methods. The public methods express WHAT the caller wants; the private methods handle HOW.
- **Dynamic:** Same principle. A library that requires 20 imports to use is shallow. A library that does one import and returns results is deep.
- **Concurrent:** A channel or actor exposes one operation: send a message. The actor handles queuing, backpressure, retry, and state management internally.

**orbit packages affected:**
- `pkg/tokenrouter` — Deep module. The interface is `Acquire(ctx) (string, error)` and `Release(key)`. The implementation handles key rotation, rate limiting, cooldown, bucket expiry, and provider health. Benefit: huge. Cost: 2 methods.
- `pkg/circuitbreaker` — Deep module. Interface: `Allow()`, `RecordSuccess()`, `RecordFailure()`. Implementation: state machine, timeout management, threshold counting, HalfOpen probing. Benefit: large. Cost: 3 methods.
- `pkg/sandbox` — Deep module. Interface: `Shell()`, `WriteFile()`, `ReadFile()`. Implementation: path containment, process management, timeout enforcement, env isolation. Benefit: large. Cost: 3 methods.
- `pkg/luaengine` — Deepest module. Interface: `RunRule(script, payload) (Result, error)`. Implementation: Lua interpreter, library whitelisting, sandboxing, JSON serialization. Benefit: huge. Cost: 1 method.

---

## 2. Information Hiding

**Principle:** Each module should hide a SECRET — a design decision that might change.
The secret is not "the implementation" — it's the knowledge that the module encapsulates
and that no other module should depend on. If the secret changes, only the module changes.

**Invariant:**
```
∀module M: ∃secret S such that S is known only to M
∀change C to S: only M's implementation changes, never M's callers
```

**Purpose:** Every module has knowledge: how data is stored, what algorithm is used, what format the output takes, what external service is called. If that knowledge leaks into the interface, callers depend on it. When it changes, callers break. Information hiding puts walls around knowledge so changes don't cascade.

**Enforcement patterns:**
- **Functional:** The secret is the data structure representation. `type Set a = [a]` vs `type Set a = Tree a` — callers use the same `insert`, `member`, `union` functions regardless.
- **Imperative/OO:** Private fields, private methods. The secret is what the public methods DON'T expose. `class LRUCache` — callers use `get`/`put`, unaware of the eviction algorithm.
- **Dynamic:** Convention (underscore prefix) rather than enforcement. `_private_method` means "don't call this, it might change."
- **Concurrent:** The secret is the concurrency model. Callers send messages; the actor's internal threading model is hidden.

**orbit packages affected:**
- `pkg/tokenrouter` — Secrets: key rotation algorithm (round-robin, weighted, or priority-based), rate-limit window (per-second buckets), cooldown duration, provider health check mechanism. None visible in the `Router` interface.
- `pkg/circuitbreaker` — Secrets: state machine implementation (mutex vs atomics), timeout calculation (fixed vs exponential), HalfOpen probe count. None visible in the `Breaker` interface.
- `pkg/sandbox` — Secrets: containment mechanism (path validation, seccomp, chroot), process execution model, timeout enforcement. None visible in the `Sandbox` interface.
- `pkg/store` — Secrets: storage format (WAL, B-tree, LSM), recovery mechanism, MVCC implementation. Hidden behind `Get`, `Put`, `Delete`.

---

## 3. Strategic vs. Tactical Programming

**Principle:** Tactical programming is finishing the current task as fast as possible.
Strategic programming is investing in design so future tasks are faster.
The tactical programmer ships today; the strategic programmer ships faster over 6 months.

**Invariant:**
```
∀design investment I: cost(I) is paid now, benefit(I) accrues over time
∀module: if cost(fix_now) < cost(fix_later) + cost(working_around_the_bug), fix now
```

**Purpose:** Complexity is compound interest working AGAINST you. Every quick hack adds little complexity. After 100 quick hacks, the codebase is a maze where every change touches 10 files. Strategic programmers fix problems when they're small, because they compound.

**Enforcement patterns:**
- **All paradigms:** "If it's worth doing, it's worth doing right." A design flaw you notice today will be 10× harder to fix in 6 months when 20 modules depend on it.
- **All paradigms:** Zero tolerance for working around a design flaw. If the interface is wrong, fix the interface. Don't add a wrapper that papers over it.
- **All paradigms:** Design documents before implementation. Not heavy — a paragraph about the module's purpose, interface, and secrets. Written in 10 minutes, saves hours of wrong implementation.

**orbit applications:**
- The invariants.md files are the design documents. Before implementing, the invariant is stated. The implementation proves it.
- The 8-step contract is strategic programming made systematic: think (equation) → design (pseudocode) → implement → prove (TestAX).
- Violation: implementing a feature without writing the invariant first. The code works, but nobody knows what "works" means.

---

## 4. General-Purpose Modules are Deeper

**Principle:** A module that solves a general problem is deeper than one that solves a specific problem.
The general module's interface is the same size, but its implementation is richer,
and it can be used in more contexts. This is the "write once, use everywhere" principle.

**Invariant:**
```
∀module M₁ (specific), M₂ (general): interface(M₁) ≈ interface(M₂) ∧ functionality(M₁) ⊂ functionality(M₂)
→ depth(M₁) < depth(M₂)
```

**Purpose:** The general module might cost 20% more to build initially, but it eliminates N specific modules that would each cost 80% of the general one. The savings compound because the general module gets more testing, more feedback, and more refinement over time.

**Enforcement patterns:**
- **All paradigms:** "Make it work, make it right, make it fast." The "make it right" step is finding the right level of generality. Not too specific (one use case), not too general (a framework that does everything).
- **All paradigms:** The test of generality: "Can I use this module for a problem I didn't anticipate?" If yes, it's general enough.
- **All paradigms:** General modules are parameterized by the parts that vary. The parameters are the interface; the fixed logic is the implementation.

**orbit packages affected:**
- `pkg/circuitbreaker` — General: used by any backend with failure/success semantics. Not specific to HTTP, gRPC, or database calls.
- `pkg/tokenrouter` — General: routes any API-key-backed resource. Not specific to MiniMax, OpenAI, or any provider.
- `pkg/sandbox` — General: sandboxes any command. Not specific to shell commands, Lua scripts, or WASM modules.
- `pkg/ggrind` — General: any pipeline of stages. Not specific to LLM review, data processing, or build steps.

---

## 5. Comments Should Describe Things That Aren't Obvious

**Principle:** Comments are not a substitute for clear code. They are a supplement for things the code
cannot say: the WHY, the invariant, the edge case, the design decision. A comment that says what the code
does is worse than useless — it will become stale, and then it will be actively misleading.

**Invariant:**
```
∀comment C: C describes something that is NOT obvious from reading the code
∀comment C: C is maintained with the same discipline as the code it annotates
∀stale comment C: C is worse than no comment (it lies)
```

**Purpose:** Comments are the bridge between the code (WHAT and HOW) and the design (WHY). The code can say "we check if the state is Open." The comment says "we must check the timeout because Open state transitions to HalfOpen after the timeout elapses — see AX-001." The comment connects the line to the invariant.

**Enforcement patterns:**
- **All paradigms:** Comment the interface (what does this function do, what are its pre/post conditions?). Don't comment the implementation unless it's non-obvious.
- **All paradigms:** Comment invariants. "This list is always sorted." "This field is protected by this mutex." "This function must be called with the lock held."
- **All paradigms:** Comment design decisions. "We use a mutex here instead of a channel because the critical section is 3 lines and a channel would require an additional goroutine."
- **All paradigms:** Delete stale comments. A wrong comment is misinformation. It will cause a bug.

**orbit packages affected:**
- `pkg/circuitbreaker` — each AX invariant has a comment in the code linking the line to the equation. `// AX-001: state = Open ∧ timeout active → return false`
- `pkg/tokenrouter` — rate-limit check has a comment: `// ∀k,t: RequestBuckets[k][t] ≤ RPM/60`
- `pkg/sandbox` — `resolve()` has a comment: `// AX-012: path must be within worktree root`
- Comment discipline: `docs/COMMENT_DISCIPLINE.md` enforces this. A comment without an invariant reference is incomplete.

---

## 6. Exceptions and Error Handling

**Principle:** Exceptions are for truly exceptional conditions. They should not be used for
flow control, for expected conditions, or for "maybe" results. The rule: if the caller
can reasonably be expected to handle the condition, use a return value. If the condition
is truly exceptional (programming error, system failure), use an exception/panic.

**Invariant:**
```
∀error condition E: E is either:
  1. Expected (part of the interface) → return error value
  2. Exceptional (programming error, unrecoverable) → exception/panic
∀expected error E: the caller MUST handle it or explicitly propagate it
```

**Purpose:** Error handling is where most bugs hide. Exceptions that are silently swallowed. Error codes that are checked but not handled. Nil checks that are missing. The error handling strategy must be consistent, explicit, and impossible to accidentally ignore.

**Enforcement patterns:**
- **Functional:** `Result<T, E>` / `Either<L, R>` — errors are values. The type system forces the caller to handle both cases. Pattern matching ensures exhaustiveness.
- **Imperative/OO:** Return codes (Go's `(T, error)`), checked exceptions (Java), `Result<T, E>` (Rust). The compiler enforces that errors are handled (Rust) or the convention is strong enough (Go's `errcheck` linter).
- **Dynamic:** Exceptions with try/catch. The risk is silent swallowing — `except: pass` is a bug waiting to happen. Linters catch bare excepts.
- **Concurrent:** Errors in one goroutine must not crash the process. Error channels, `errgroup`, supervision trees (Erlang) — errors propagate to a handler, not to the caller.

**orbit packages affected:**
- `pkg/dispatch` — HTTP errors classified as P0 (connection refused), P1 (timeout), P2 (invalid request). The classification determines retry behavior. AX-024.
- `pkg/tokenrouter` — `Acquire(ctx) (string, error)` — returns `ErrNoKeysAvailable` when all keys are exhausted. Caller must handle. Not a panic.
- `pkg/circuitbreaker` — `Call(fn) error` — wraps the function's error. If `fn` panics, `Call` recovers and returns the panic as an error. AX-006.
- `pkg/sandbox` — `Shell(cmd) (Output, error)` — returns the command's error. The sandbox doesn't crash if the command fails.

---

## 7. Consistency and Conventions

**Principle:** Consistency reduces cognitive load. If every module follows the same conventions,
a reader who understands one module can understand any module. The conventions are not
"the best possible" — they are "the SAME everywhere."

**Invariant:**
```
∀convention C: C is applied uniformly across the codebase
∀new code N: N follows existing conventions, even if N's author prefers a different convention
```

**Purpose:** The reader's brain is the scarcest resource. Every inconsistency is a context switch — "wait, why is this module using a different pattern?" The answer is usually "the author had a different preference." That's not a good reason. Consistency is more important than individual preference.

**Enforcement patterns:**
- **All paradigms:** A style guide that is enforced by automation. `gofmt`, `prettier`, `rustfmt`, `black`. No human reviews formatting.
- **All paradigms:** Naming conventions. `GetX` vs `FetchX` vs `ReadX` — pick one. `Error` vs `Err` — pick one. `ID` vs `Id` — pick one.
- **All paradigms:** Error handling conventions. All errors are checked. All panics are recovered at the top level. All contexts are passed as the first argument.
- **All paradigms:** File organization. One module per directory. Tests next to code. Documentation next to tests.

**orbit packages affected:**
- Every package follows the same structure: `pkg/<name>/<name>.go`, `pkg/<name>/<name>_test.go`, `pkg/<name>/ax_test.go`, `pkg/<name>/invariants.md`.
- Every TestAX test is named `TestAX<NNN>_<DescriptiveName>`. The AX number is globally unique.
- Every invariant is a tensor equation with `∀` quantifiers. The equation format is the same across all 10 packages.
- Error handling: `if err != nil { return ..., fmt.Errorf("context: %w", err) }` — always wrap, always include context.

---

## 8. Design it Twice

**Principle:** For any non-trivial design, sketch TWO approaches. Compare them. The comparison reveals
tradeoffs that neither approach makes visible on its own. The first design is your habitual approach;
the second forces you to see the problem differently.

**Invariant:**
```
∀design D: ∃alternative D' with different tradeoffs
∀design decision: the choice between D and D' is explicit and documented
```

**Purpose:** Your first design is driven by habit. You always reach for a mutex, or always reach for a channel, or always reach for inheritance. The second design forces you to question the habit. Maybe a channel is better here. Maybe composition is better than inheritance. The comparison IS the design process.

**Enforcement patterns:**
- **All paradigms:** Before implementing: write two design sketches. One paragraph each. Compare: which is simpler? Which has a deeper interface? Which handles edge cases better?
- **All paradigms:** The comparison reveals assumptions. "Oh, I was assuming single-threaded." "Oh, I was assuming the data fits in memory." The second design questions those assumptions.
- **All paradigms:** Document the rejected design and WHY it was rejected. The next reader will wonder "why didn't they use X?" — the documented rejection answers that question.

**orbit applications:**
- `pkg/circuitbreaker` — Design 1: Hystrix-style state machine (closed/open/half-open). Design 2: Envoy-style atomic counters. Comparison: state machine is simpler for single-backend, counters handle per-request isolation better. Chose state machine for simplicity, documented the Envoy alternative in `envoy.md`.
- `pkg/tokenrouter` — Design 1: eager bucket expiry (timer per bucket). Design 2: lazy expiry (check on Acquire). Comparison: eager is O(buckets × timers) goroutines, lazy is O(1) per Acquire. Chose lazy. Documented in invariants.md.

---

## The Ousterhout Test

For any module, ask:
1. **Depth:** Is the interface small and the implementation rich? Or is it a pass-through?
2. **Information hiding:** What's the secret? If it changes, how many files change?
3. **Strategic vs. tactical:** Am I fixing this design flaw now, or leaving it to compound?
4. **Generality:** Could this module solve a slightly different problem? If so, where's the parameter?
5. **Comments:** Does this comment say something the code doesn't? Or is it a translation of the code into English?
6. **Error handling:** Can the caller accidentally ignore this error? Is the error classified (recoverable vs unrecoverable)?
7. **Consistency:** Does this follow the same conventions as the rest of the codebase?
8. **Design it twice:** What's the alternative? Why was it rejected?

Ousterhout is the design discipline. Deep modules, information hiding, strategic investment, and design-it-twice. Every module is judged by its depth.