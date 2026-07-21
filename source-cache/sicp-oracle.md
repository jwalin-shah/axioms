# SICP Oracle (1985/1996)

Source: "Structure and Interpretation of Computer Programs" (Abelson, Sussman, and Sussman, MIT Press, 2nd ed. 1996).
Also: Lecture videos (MIT 6.001, 1986), "The Wizard Book."

This is how you MANAGE COMPLEXITY through abstraction. Every concept maps to a design principle,
a language-agnostic enforcement pattern, and specific orbit applications.

---

## 1. Procedural Abstraction — "Wishful Thinking"

**Principle:** Build programs in layers. At each layer, you assume the layer below exists and works.
You name a function for what it DOES, not how it does it. Implementation is deferred to a lower layer.

**Invariant:**
```
∀layer L: L only depends on the contract of L-1, never its implementation
∀function f: |f's body| ≤ 1 screen of code (≈24 lines)
```

**Purpose:** This is the foundation of modularity. Without it, every change cascades through the entire system because every layer knows how every other layer works. The invariant isn't about line counts — it's about cognitive load. If a function can't fit in one screen, the reader can't hold its entire behavior in their head, and they'll make mistakes when modifying it.

**Enforcement (any language):**
- Every function/class/module has a documented contract (pre/post conditions, invariants)
- A function body fits on one screen — if it doesn't, decompose
- No function reads the internal state of a module it doesn't own
- Tests exercise the contract, not the implementation

**Enforcement (Go):**
- Interfaces define contracts; structs implement them
- `func (s *Service) Do(ctx context.Context, req Request) (Response, error)` — the signature IS the contract
- No reaching into another package's unexported fields
- `internal/` packages enforce the layer boundary at the compiler level

**orbit packages affected:**
- Every package. The `pkg/` directory is structured as layers — `pkg/tokenrouter` is below `pkg/dispatch`, `pkg/sandbox` is below `pkg/luaengine`. Each layer assumes the layer below fulfills its contract.
- Violation: if `pkg/dispatch` bypasses `pkg/tokenrouter` and reads API keys directly.

---

## 2. Data Abstraction — "Closures as Objects"

**Principle:** Data is defined by its BEHAVIOR (the operations you can perform on it), not its representation.
A pair is anything that supports `car` and `cdr`. A stack is anything that supports `push` and `pop`.

**Invariant:**
```
∀abstract type T: code that uses T only calls T's interface methods, never accesses T's representation
∀representation change: only the implementation of T's interface changes, never its callers
```

**Purpose:** The representation of data changes far more often than the operations on it. A list might start as a linked list, then become a slice, then become a B-tree. If every caller knows the representation, every caller must change. Data abstraction isolates that change to one place.

**Enforcement (any language):**
- Struct/class fields are private; access is through methods
- Constructors build the invariant, never the caller
- A type's interface is small (1-5 methods), not a mirror of its fields
- Changing the representation doesn't change the callers

**Enforcement (Go):**
- Unexported struct fields, exported methods
- `func NewFoo(...) *Foo` — constructor enforces invariants
- Interfaces define the abstraction; structs are the implementation
- `go:generate` for interface satisfaction checks

**orbit packages affected:**
- `pkg/tokenrouter` — `Router` interface hides key rotation, bucket tracking, cooldown. Callers only see `Acquire(ctx) (string, error)`. The underlying key store could be a file, a database, or a remote service — callers don't know.
- `pkg/circuitbreaker` — `CircuitBreaker` interface: `Allow()`, `RecordSuccess()`, `RecordFailure()`. The state machine (Closed/Open/HalfOpen) is hidden. Could be replaced with Envoy-style counters without changing callers.
- `pkg/sandbox` — `Sandbox` interface: `Shell()`, `WriteFile()`, `ReadFile()`. The containment mechanism (chroot, seccomp, path validation) is hidden.

---

## 3. Higher-Order Procedures — "Functions as Values"

**Principle:** Functions are first-class values. They can be passed as arguments, returned as results, and composed.
This is the mechanism for building abstractions that capture PATTERNS, not just operations.

**Invariant:**
```
∀pattern P: express P as a higher-order function that takes the variable part as an argument
∀repeated code block B: B appears exactly once, parameterized by the varying part
```

**Purpose:** The most common source of bugs is copy-paste. Two blocks of code that look the same but differ in one small detail will diverge — one gets fixed, the other doesn't. Higher-order functions eliminate the copy by making the difference a parameter.

**Enforcement (any language):**
- DRY (Don't Repeat Yourself) enforced by static analysis
- Functions that take functions (map, filter, fold, retry, withLock, withTimeout)
- Callbacks, middleware, decorators, interceptors are all this pattern
- No block of code appears twice with only a variable name or type difference

**Enforcement (Go):**
- `func` types, closures, method values
- `http.Handler` (middleware pattern): `func(h http.Handler) http.Handler`
- `func WithRetry(f func() error, n int) error` — the retry pattern parameterized
- Generics (Go 1.18+) for type-parameterized patterns

**orbit packages affected:**
- `pkg/dispatch` — `func Dispatch(ctx, spec, attempt) error` — the dispatch pattern parameterized by spec
- `pkg/circuitbreaker` — `func (cb *CB) Call(fn func() error) error` — the circuit-breaker pattern parameterized by the wrapped function
- `pkg/tokenrouter` — `func (r *Router) WithKey(ctx, fn func(key string) error) error` — the acquire-use-release pattern as a higher-order function

---

## 4. Streams and Lazy Evaluation — "Infinite Data Structures"

**Principle:** Separate computation from consumption. A stream is a data structure that produces values on demand.
This decouples the producer from the consumer: the producer doesn't know how many values are needed,
and the consumer doesn't know how the values are generated.

**Invariant:**
```
∀stream s: consumer controls how many values are pulled from s
∀stream s: producer is suspended until consumer pulls the next value
```

**Purpose:** Most performance bugs come from computing more than needed — loading the entire dataset when only the first 10 rows are shown, rendering all frames when the user is on frame 3. Streams make "stop when you have enough" the default, not an optimization.

**Enforcement (any language):**
- Generators, iterators, channels, async iterators
- Pagination: `LIMIT`/`OFFSET` in SQL, cursor-based pagination
- `yield` (Python), `yield return` (C#), `chan` (Go)
- Never `SELECT *` without a limit

**Enforcement (Go):**
- Channels: `ch <- value` (producer), `v := <-ch` (consumer)
- `iter.Seq` (Go 1.23+): `func(yield func(V) bool)`
- `database/sql` Rows: `rows.Next()` + `rows.Scan()` — pull-based cursor
- Context cancellation: consumer closes `ctx.Done()`, producer checks `ctx.Err()`

**orbit packages affected:**
- `pkg/ggrind` — grind pipeline stages are streams: each stage pulls from the previous, stops when context is cancelled
- `pkg/dispatch` — dispatch results are pulled by the caller; the dispatcher doesn't buffer unboundedly
- `pkg/tokenrouter` — key acquisition is lazy: `Acquire()` returns the next available key, the caller doesn't need to know how many exist

---

## 5. Metacircular Evaluator — "Programs that Reason About Programs"

**Principle:** A program can be data for another program. The evaluator loop — read, eval, print — is itself a program.
This is the foundation of interpreters, compilers, DSLs, and code-generation tools.

**Invariant:**
```
∀language L defined by eval: ∀expression e in L, eval(e) = meaning(e)
∀program-as-data: the program P is a value that can be inspected, transformed, and executed
```

**Purpose:** When you need to enforce rules that span multiple functions or modules, a human reviewer is unreliable. A program that reads the code as data and checks rules is reliable. This is the foundation of linters, static analyzers, and formal verification.

**Enforcement (any language):**
- AST-based static analysis (linters, formatters, type checkers)
- DSLs embedded in the host language (macros, code generation)
- Reflection, metaprogramming, annotation processors
- Property-based testing: the test framework generates inputs and checks invariants

**Enforcement (Go):**
- `go/ast`, `go/parser`, `go/types` — the Go standard library for reading Go code as data
- `go generate` — code generation from annotations
- `go/analysis` — the static analysis framework used by `golangci-lint`
- `//go:build` constraints — compile-time program selection

**orbit packages affected:**
- `cmd/static-check/` — AST-based static analysis that enforces orbit-specific invariants
- `cmd/verify-v3/` — reads Go source as data, checks against tensor equations
- `pkg/luaengine` — embeds a Lua interpreter; Lua scripts are data processed by the engine
- `pkg/ggrind` — reviewer prompts are data; the grind pipeline transforms and evaluates them

---

## 6. The Environment Model — "Lexical Scope"

**Principle:** A variable's meaning is determined by its lexical context (where it is defined in the source code),
not by the dynamic call chain. Every function closes over its defining environment.

**Invariant:**
```
∀variable reference v: the binding of v is determined by the innermost enclosing scope at definition time
∀function f: f carries its defining environment, not its calling environment
```

**Purpose:** Dynamic scope (variable meaning depends on who called you) is the source of "action at a distance" bugs — a function's behavior changes because someone up the call stack changed a variable. Lexical scope makes the meaning of every variable locally determinable.

**Enforcement (any language):**
- Lexical scoping (all modern languages): variable meaning is local to definition
- `const`/`final`/`let` — bind-once, never reassign
- No global mutable state; if globals exist, they are read-only after initialization
- Dependency injection: dependencies are passed explicitly, not found in a global registry

**Enforcement (Go):**
- Package-level variables are initialized once; `init()` is discouraged
- `context.Context` carries request-scoped values (explicit, not implicit)
- `sync.Once` for one-time initialization of shared state
- Struct fields over package-level variables for mutable state

**orbit packages affected:**
- `pkg/tokenrouter` — key rotation state is in a struct, not a package-level map. Multiple routers can coexist.
- `pkg/circuitbreaker` — each breaker has its own state; no global breaker map
- `pkg/sandbox` — each sandbox has its own worktree; no global working directory
- Violation: adding a `var globalRouter *Router` that `dispatch` reads directly (action at a distance)

---

## 7. The SICP Curriculum — What To Learn, In Order

| Chapter | Concept | orbit Application |
|---|---|---|
| 1.1 | Elements of programming: primitives, combinations, abstractions | Every function: name its contract, keep it small |
| 1.2 | Procedures and processes: linear, iterative, tree recursion | `pkg/ggrind` pipeline stages, recursive dispatch |
| 1.3 | Higher-order procedures: map, filter, fold, accumulate | `pkg/dispatch` retry, `pkg/circuitbreaker` Call() |
| 2.1 | Data abstraction: constructors, selectors, barriers | `pkg/tokenrouter` Router interface, `pkg/sandbox` Sandbox interface |
| 2.2 | Hierarchical data: lists, trees, sequences | `pkg/store` WAL entries, `pkg/tokenrouter` key hierarchy |
| 2.3 | Symbolic data: quotation, symbolic differentiation | `pkg/luaengine` Lua as data, `cmd/static-check` Go AST |
| 2.5 | Generic operations: data-directed programming, dispatch tables | `pkg/dispatch` dispatch by type, `pkg/circuitbreaker` state transitions |
| 3.1 | Assignment and local state: the environment model | `pkg/tokenrouter` per-key state, `pkg/circuitbreaker` per-backend state |
| 3.2 | The environment model of evaluation | `context.Context` propagation, closure over configuration |
| 3.3 | Mutable list structure: sharing, identity, mutation | `pkg/store` MVCC, snapshot isolation |
| 3.5 | Streams: delayed evaluation, infinite streams | `pkg/ggrind` pull-based pipeline, `pkg/tokenrouter` lazy key rotation |
| 4.1 | The metacircular evaluator | `cmd/static-check`, `cmd/verify-v3`, `pkg/luaengine` |
| 4.3 | Variations on a scheme: lazy evaluation, nondeterministic computing | `pkg/ggrind` redteam reviewers, `pkg/circuitbreaker` ensemble verification |
| 5.1 | Register machine design | `pkg/congestion` VM (4 opcodes from a full interpreter) |
| 5.5 | Compilation | `pkg/luaengine` Lua → Go bridge, `pkg/wasmbox` WASM compilation |

---

## The SICP Test

For any piece of code, ask:
1. **Abstraction:** Does this function do ONE thing, named for WHAT not HOW?
2. **Data:** Is the representation hidden behind an interface? Could I change it without changing callers?
3. **Higher-order:** Is there a repeated pattern that should be parameterized?
4. **Laziness:** Does this compute more than its consumer needs?
5. **Environment:** If I read this variable, do I know exactly where it was defined?
6. **Metacircular:** If this rule matters, is there a program that checks it automatically?

If the answer to any of these is "no," the code has a design debt.