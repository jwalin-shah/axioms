# Kernighan & Plaugher Oracle (1974/1999)

Source: "The Elements of Programming Style" (Kernighan & Plaugher, McGraw-Hill, 1974, 2nd ed. 1978).
Also: "The Practice of Programming" (Kernighan & Pike, Addison-Wesley, 1999).

This is the craft. Not the theory, not the proof — the PRACTICE. How to write code that is clear, correct,
and maintainable. These are principles that hold across every language, every paradigm, every era.
Kernighan wrote C and Unix. These principles apply equally to Go, Rust, Python, and the language
that replaces them all in 50 years.

---

## 1. Simplicity

**Principle:** Do the simplest thing that works. Simplicity is not naivety — it's the result of
understanding the problem well enough to eliminate everything unnecessary. Complex code is code
that does more than the problem requires.

**Invariant:**
```
∀solution S to problem P: S is minimal iff removing any part of S would break correctness for some input
∀complexity C: C must be justified by a requirement, not by a guess about future needs
```

**Purpose:** Complexity is the root of all bugs. Every line of code is a potential bug. Every condition is a place where the code can be wrong. Every abstraction is a place where the model can diverge from reality. The simplest solution that works has the fewest places to be wrong.

**Enforcement (any language):**
- Write the test first. When the test passes, STOP. Don't add "just in case" code.
- Delete code that isn't covered by a test. It's either dead or untested — both are bugs waiting to happen.
- If a function has more than one reason to change, split it. If a module has more than 5 public functions, question it.
- The best code is the code you don't write.

**orbit packages affected:**
- `pkg/circuitbreaker` — 3 states, 5 transitions. Simplest state machine that works. Adding a "Recovering" state between HalfOpen and Closed would add complexity without a proven need.
- `pkg/luaengine` — 5 whitelisted libraries. The minimum set for rule evaluation. Adding `string` was debated but justified (rule payloads contain string data).
- `pkg/congestion` — 4 opcodes. A full VM in one file. Every opcode is justified by a use case.
- Violation: `pkg/dispatch` — `post()` is 80+ lines. Does too many things. Should be decomposed.

---

## 2. Clarity

**Principle:** Write code for humans to read, not for machines to execute. The machine doesn't care
about variable names, formatting, or comments. The human who maintains your code in 6 months does.
That human is often you.

**Invariant:**
```
∀identifier name: name describes what the thing IS or DOES, not how it's implemented
∀function f: f does exactly one thing, and its name says what that thing is
∀comment: explains WHY, not WHAT (the code already says WHAT)
```

**Purpose:** Code is read far more often than it is written. The reader must be able to understand what the code does and why. If the reader can't understand it in one pass, they'll misinterpret it, and their "fix" will introduce a bug.

**Enforcement (any language):**
- Names are the primary documentation. A good name eliminates the need for a comment.
- Functions are named with verbs (`ComputeHash`, `AcquireKey`), types with nouns (`KeyPool`, `CircuitBreaker`), booleans with predicates (`IsOpen`, `HasExpired`).
- Comments explain the non-obvious: why this approach, why not the alternative, what invariant this code maintains.
- Consistent formatting. Not a matter of taste — a matter of reducing cognitive load for the reader.

**orbit packages affected:**
- `pkg/tokenrouter` — `Acquire(ctx) (string, error)` — the name says exactly what happens. `RotateKeys()` — clear verb.
- `pkg/circuitbreaker` — `Allow()`, `RecordSuccess()`, `RecordFailure()`. Each name is a verb describing the action.
- `pkg/sandbox` — `resolve(path)`, `Shell(cmd)`, `WriteFile(path, data)`. Names match their behavior.
- Violation: if a function is named `Process()` or `Handle()` or `Do()` — it does too many things or the author didn't know what it does.

---

## 3. Generality

**Principle:** Solve the general problem, not the specific instance. The specific instance is a special case
of the general solution with one parameter fixed. Find the parameter, make it an argument, and the
specific instance becomes a one-line call.

**Invariant:**
```
∀solution S: if S solves problem P by hardcoding a value V that could vary, S is too specific
∀parameter p: if p could change independently of the algorithm, p is an argument, not a constant
```

**Purpose:** The difference between "a script that works for me" and "a library others can use" is generality. Generality is not over-engineering — it's recognizing parameters that will change and making them actual parameters instead of hidden assumptions.

**Enforcement (any language):**
- If a function has a magic number, make it a parameter with a default.
- If a module hardcodes a file path, make it a configuration value.
- If a workflow assumes a specific order, make the order configurable.
- The test of generality: can someone with a slightly different problem use your code by changing only the arguments?

**orbit packages affected:**
- `pkg/tokenrouter` — `New(config Config) *Router` — the key pool is configurable (not hardcoded to MiniMax). Any API can be routed.
- `pkg/circuitbreaker` — `New(threshold int, timeout time.Duration) *CB` — threshold and timeout are parameters, not constants.
- `pkg/sandbox` — `NewSandbox(root string) *Sandbox` — the worktree root is a parameter.
- Violation: if `pkg/dispatch` hardcodes the retry count to 3 instead of making it a parameter. (Currently does this.)

---

## 4. Interfaces

**Principle:** The interface is the contract. What goes on behind the interface is nobody's business.
Design the interface first — what does the caller need? What does the caller NOT need to know?
Then implement behind that interface. Change the implementation without changing the interface.

**Invariant:**
```
∀interface I: the set of methods in I is exactly what callers need, nothing more
∀implementation change C: if C doesn't change I's behavior, no callers change
∀new implementation I': I' satisfies the same contract as I, without callers knowing which is used
```

**Purpose:** Interfaces are the seams of the system. They are where one concern ends and another begins. A well-designed interface hides complexity behind a simple contract. The caller doesn't know or care how the contract is fulfilled — only that it is.

**Enforcement patterns:**
- **Functional:** Typeclasses, modules with signatures (OCaml), protocols (Clojure). The interface is a set of function signatures, and any module/type that implements them satisfies it.
- **Imperative/OO:** Interfaces (Go, Java), abstract base classes (Python, C++), traits (Rust). The interface declares the contract; implementations fulfill it.
- **Dynamic:** Duck typing (Python, Ruby) — "if it walks like a duck." The interface is implicit, enforced by `hasattr` or runtime errors. Contracts become documentation, not compilation.
- **Concurrent:** Message-passing protocols (Erlang/Elixir gen_server, Akka actors). The interface is a set of messages the actor accepts, and the behavior is the actor's response.

**orbit packages affected:**
- `pkg/tokenrouter` — `Router` interface: `Acquire`, `Release`. The implementation (key rotation, rate limiting, cooldown) is hidden. Could swap in a database-backed router without callers knowing.
- `pkg/circuitbreaker` — `Breaker` interface: `Allow`, `RecordSuccess`, `RecordFailure`. Hystrix-style or Envoy-style — callers don't know.
- `pkg/sandbox` — `Sandbox` interface: `Shell`, `WriteFile`, `ReadFile`. The containment mechanism is hidden.
- `pkg/luaengine` — `RunRule(script, payload) Result` — the interface is one function. The Lua interpreter, sandboxing, and library whitelisting are hidden.

---

## 5. Debugging

**Principle:** Debugging is systematic, not mystical. Every bug has a root cause. Find it by
bisecting the problem space: narrow the input until the bug disappears, then expand until it
reappears. The boundary between "works" and "doesn't work" IS the bug.

**Invariant:**
```
∀bug B: ∃smallest input I such that program(I) exhibits B
∀debugging session: each step reduces the search space by at least half
∀fix F: F addresses the root cause, not the symptom
```

**Purpose:** "It works on my machine" is a statement about the environment, not the code. Every bug is reproducible given the right input and environment. The skill of debugging is finding that minimal reproduction. Once you have it, the fix is usually obvious.

**Enforcement patterns:**
- **All paradigms:** Bisect the input. If the bug disappears when you remove half the input, the bug is in that half. Repeat. This finds the minimal reproduction in O(log n) steps.
- **All paradigms:** `printf` debugging is valid. A well-placed log line tells you whether execution reached a point and what the state was.
- **All paradigms:** The bug is in YOUR code, not the compiler, not the OS, not the library. The library may have a bug, but you haven't proven that yet.
- **All paradigms:** Fix the root cause, not the symptom. If a nil pointer crashes, don't add a nil check — figure out why the pointer was nil and fix THAT.
- **Concurrent:** Race conditions are bugs. They are reproducible given the right interleaving. `go test -race` finds them deterministically. Stress testing makes them more likely.

**orbit applications:**
- `pkg/circuitbreaker` — AX-001 found and fixed: `Allow()` was side-effecting state when called during `Pick()` filtering. The fix: `IsAvailable()` is a read-only check; `Allow()` is called only when a backend is selected.
- `pkg/tokenrouter` — bucket time lazy expiry was a bug: expired buckets weren't zeroed until the next Acquire. Fixed by checking expiry in Acquire.
- `pkg/sandbox` — path traversal via symlinks: `resolve()` used `filepath.EvalSymlinks` but didn't verify the resolved path was within root. Fixed by checking after resolution.

---

## 6. Testing

**Principle:** Test code is as important as production code. It must be clear, maintainable, and correct.
A flaky test is worse than no test — it trains the team to ignore test failures.

**Invariant:**
```
∀test T: T passes ← code is correct ∧ T fails ← code is wrong
∀test T: T is deterministic (same input → same result every time)
∀test suite: runs fast enough to run on every change (< 5 minutes for full suite)
```

**Purpose:** Tests are the proof that code works. But tests are also code — they have bugs, they rot, they become irrelevant. A test that never fails is not testing anything. A test that sometimes fails is noise. A test that takes too long won't be run.

**Enforcement patterns:**
- **Functional:** Property-based testing (QuickCheck) — generate random inputs, check invariants. Catches edge cases manual tests miss.
- **Imperative/OO:** Table-driven tests (Go), parameterized tests (JUnit, pytest). One test function, many test cases.
- **Dynamic:** REPL-driven development. Explore the code interactively, then codify the exploration as tests.
- **Concurrent:** Stress tests (`go test -count=100`), race detector, `-race` flag. Run with `GOMAXPROCS` set high.

**orbit packages affected:**
- `pkg/circuitbreaker` — 17 TestAX tests, table-driven, deterministic, fast (<0.2s).
- `pkg/tokenrouter` — tests take 60s (involve real API keys). These are integration tests, not unit tests. Need mocks for fast unit tests.
- `pkg/sandbox` — tests create real processes. Acceptably fast (~0.2s each) but brittle (depend on OS behavior).
- Gap: 7 packages have invariants but no tests. The invariant is prose without a proof.

---

## 7. Portability

**Principle:** Code that depends on a specific environment is fragile. The environment will change —
OS version, library version, hardware, network conditions. Write code that works across environments
by depending on STANDARDS, not on implementation details.

**Invariant:**
```
∀environment dependency D: D is either:
  1. A documented standard (POSIX, HTTP, SQL), or
  2. Explicitly versioned and tested across supported environments
∀non-standard dependency: the cost of the dependency is understood and accepted
```

**Purpose:** "It works on my machine" is the symptom of an implicit environment dependency. The code makes an assumption about the OS, the filesystem, the network, the clock — and that assumption is wrong on another machine. Making the assumption explicit (through configuration, abstraction, or documented requirements) prevents the bug.

**Enforcement patterns:**
- **All paradigms:** Depend on standards, not implementations. HTTP, not libcurl. SQL, not PostgreSQL-specific syntax. POSIX paths, not `/home/user/`. Use `/` as path separator, not `\`.
- **All paradigms:** Abstract the environment behind an interface. Filesystem? `fs.FS` (Go), `pathlib` (Python), `java.nio` (Java). Time? `Clock` interface, not `time.Now()`. Network? `http.RoundTripper`, not raw sockets.
- **All paradigms:** Test on multiple environments. CI matrix: linux, macos, windows. Go cross-compilation makes this easy.
- **Concurrent:** `GOMAXPROCS` matters. Test with `GOMAXPROCS=1` and `GOMAXPROCS=16`. Race conditions that don't appear at low concurrency may appear at high concurrency.

**orbit packages affected:**
- `pkg/sandbox` — `resolve()` uses `filepath.Clean` + `filepath.Rel`. Works on Linux and macOS. Would NOT work on Windows (different path separator, no symlinks).
- `pkg/tokenrouter` — HTTP client calls to API providers. Works on any OS with network. No OS-specific assumptions.
- `pkg/circuitbreaker` — pure in-memory state machine. No OS dependencies. Trivially portable.
- `pkg/store` — WAL uses `os.File`. Works on POSIX. Would need `fs.FS` abstraction for full portability.

---

## 8. Notation

**Principle:** Notation is a tool for thought. The right notation makes the problem simple; the wrong
notation makes it impossible. Choose notation that matches the problem domain, not notation that
matches the implementation language.

**Invariant:**
```
∀problem P: express P in the notation closest to P's domain, not the implementation language
∀notation N: N is judged by how clearly it expresses the invariant, not by how familiar it is
```

**Purpose:** The most important design decision is the language you think in. If you're implementing a state machine, draw the state diagram. If you're implementing a parser, write the grammar. If you're implementing a concurrent algorithm, write the PlusCal. The implementation is a translation of the domain notation into code.

**Enforcement patterns:**
- **State machines:** Draw the diagram. States are boxes, transitions are arrows. The diagram IS the specification.
- **Parsers:** Write the grammar (BNF, PEG, regex). The grammar IS the parser.
- **Concurrent algorithms:** Write the PlusCal. Model-check it. Then translate to code.
- **Data transformations:** Write the pipeline: `input → transform₁ → transform₂ → output`. Each arrow is a function.
- **Invariants:** Write the tensor equation: `∀x: property(x)`. The equation IS the invariant.

**orbit applications:**
- `pkg/circuitbreaker` — the state machine diagram in `invariants.md` IS the specification. The Go code is the translation.
- `pkg/tokenrouter` — the rate-limit equation `∀k,t: RequestBuckets[k][t] ≤ RPM/60` IS the specification. The Go code implements the check.
- `pkg/ggrind` — the pipeline `prompts → reviewers → findings → triage → report` IS the specification. Each stage is a goroutine pool.

---

## The Kernighan Test

For any code, ask:
1. **Simplicity:** Can I delete anything without breaking a test?
2. **Clarity:** If I read this in 6 months, will I understand it?
3. **Generality:** If the requirement changes slightly, does the code change or just the arguments?
4. **Interface:** What does the caller NOT need to know? Is it hidden?
5. **Debugging:** If this code has a bug, how would I find it?
6. **Testing:** Is there a test that would catch the bug I'm about to write?
7. **Portability:** Does this depend on something that might change?
8. **Notation:** Am I thinking in the right language?

Kernighan & Plaugher is the craft. Theory tells you what's possible. Craft tells you what's wise.