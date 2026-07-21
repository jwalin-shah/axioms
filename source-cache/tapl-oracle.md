# TAPL Oracle (2002)

Source: "Types and Programming Languages" (Benjamin C. Pierce, MIT Press, 2002).
Also: "Advanced Topics in Types and Programming Languages" (Pierce, 2004), "Practical Foundations for Programming Languages" (Harper, 2016).

This is how you PROVE that programs don't go wrong. Every concept maps to a type-system invariant,
a language-agnostic enforcement pattern, and specific orbit applications.

---

## 1. Type Safety — "Progress and Preservation"

**Principle:** A type system is a static proof that certain errors cannot occur at runtime.
- **Progress:** If a term is well-typed, it is either a value or can take a step. It never gets "stuck."
- **Preservation (Subject Reduction):** If a term takes a step, its type is preserved. The type of the result is the same as the type of the original.

**Formal definition:**
```
Progress:  ∀t: if ⊢ t : T, then t is a value ∨ ∃t': t → t'
Preservation: ∀t, t': if ⊢ t : T and t → t', then ⊢ t' : T
```

**Purpose:** Type safety is a guarantee, not a convention. "This program won't segfault" is a property you can prove at compile time. In Go, the compiler guarantees no unsafe pointer arithmetic, no buffer overflows, and no use-after-free. But it doesn't guarantee logical correctness — that's what our invariants are for.

**Enforcement (any language):**
- Static type checking: the compiler rejects programs that would get stuck
- Pattern matching exhaustiveness: the compiler checks that all cases are handled
- Null safety: `Option<T>` / `Maybe T` / nil-checked types
- Resource linearity: a resource is used exactly once (Rust's ownership, linear types)

**Enforcement (Go):**
- Go's type system: sound for memory safety, unsound for nil (nil deref is a runtime panic, not a compile-time error)
- `interface{}` / `any` is an escape hatch — it bypasses type checking
- `type switch` with `default` case — exhaustiveness check
- `go vet` — static analysis for common type errors
- Generics (Go 1.18+): type parameters replace `interface{}` with compile-time type safety

**orbit packages affected:**
- Every package. Go's type system is the first line of defense.
- `pkg/tokenrouter` — `Acquire(ctx) (string, error)` — the return type IS the contract. You can't accidentally return an int.
- `pkg/circuitbreaker` — `State` is a typed enum: `type State int; const (Closed State = iota; Open; HalfOpen)`. The compiler prevents `cb.state = 42`.
- `pkg/luaengine` — `RunRule(script, payload) (Result, error)` — the Lua result is parsed into a typed Go struct, not a raw `interface{}`.

---

## 2. The Lambda Calculus — "The Smallest Language"

**Principle:** The untyped lambda calculus (λ-calculus) has three constructs: variables, abstractions, and applications.
Every programming language is syntactic sugar over this core. Understanding it means understanding
what computation IS — not how it's spelled in a particular language.

**Syntax:**
```
t ::= x          (variable)
    | λx.t       (abstraction — function definition)
    | t t        (application — function call)
```

**Purpose:** The λ-calculus is the "tensor equation" of computation. It strips away syntax, types, and runtime to reveal the essence: everything is a function, and computation is substitution. When you're designing a new feature, ask: "What's the λ-calculus of this?" — what's the minimal core that captures the idea?

**Enforcement (any language):**
- First-class functions (closures, lambdas, anonymous functions)
- Higher-order functions (map, filter, fold, compose)
- Function composition over mutation
- Tail-call optimization (or explicit loops for non-TCO languages)

**Enforcement (Go):**
- `func` literals, closures over scope
- `func(x int) int { return x + 1 }` — the λ-calculus of Go
- Method values: `obj.Method` — partial application
- No tail-call optimization in Go (use loops instead of deep recursion)

**orbit packages affected:**
- `pkg/luaengine` — the Lua interpreter IS a λ-calculus evaluator. Rules are λ-expressions applied to payloads.
- `pkg/congestion` — the VM evaluates a minimal instruction set. The VM IS a λ-calculus in machine code.
- `pkg/ggrind` — the grind pipeline is function composition: `filter(map(reviewer, prompts))`

---

## 3. Simple Types — "Types as Predicates"

**Principle:** A type is a predicate on values. `int` means "this value is an integer." `string → int` means
"this is a function from string to int." The type system checks that predicates are consistent:
if `f : string → int` and `x : string`, then `f(x) : int`.

**Formal definition:**
```
Typing rule for application:
  Γ ⊢ f : T₁ → T₂    Γ ⊢ x : T₁
  -------------------------------
        Γ ⊢ f x : T₂
```

**Purpose:** Types are documentation that the compiler ENFORCES. A function signature `func Validate(req Request) (Result, error)` is a predicate: "this function, given a Request, returns a Result or an error." The compiler checks every call site. No human reviewer needs to verify that nobody passes a string where a Request is expected.

**Enforcement (any language):**
- Type annotations on all function signatures
- No `void*` / `Object` / `any` in public interfaces (use generics instead)
- Newtypes: `type UserID string` (not just `string`) — the type IS the documentation
- Phantom types: type parameters that don't appear in the runtime representation but enforce invariants

**Enforcement (Go):**
- Named types: `type KeyID string`, `type BucketID int`
- Struct tags: `json:"name"`, `validate:"required"`
- `go generate` for type-safe boilerplate
- `//go:generate stringer -type=State` — type-safe enum stringification

**orbit packages affected:**
- `pkg/tokenrouter` — `type KeyID string`, not `string`. The type system prevents passing a key ID where a provider name is expected.
- `pkg/circuitbreaker` — `type State int` with `//go:generate stringer`. The type system prevents assigning a State to an int without a cast.
- `pkg/dispatch` — `type Spec struct`, `type Attempt int`. The type system prevents swapping arguments.

---

## 4. Subtyping — "Is-A vs. Has-A"

**Principle:** A type S is a subtype of T if a value of type S can be used wherever a value of type T is expected.
In OO languages, this is "inheritance." In Go, this is "interface satisfaction" (structural, not nominal).

**Formal definition:**
```
Subsumption rule:
  Γ ⊢ t : S    S <: T
  --------------------
      Γ ⊢ t : T
```

**Purpose:** Subtyping enables polymorphism — code that works with T works with any subtype of T. But deep inheritance hierarchies are brittle (the "fragile base class" problem). Go's structural subtyping (interfaces) avoids this: any type that has the right methods satisfies the interface, regardless of its position in a hierarchy.

**Enforcement (any language):**
- Prefer composition over inheritance (the "has-a" over "is-a" principle)
- Interface segregation: small interfaces (1-3 methods) over large ones
- Liskov substitution principle: S <: T means S can do everything T can, and nothing that contradicts T's contract
- No deep inheritance hierarchies (max depth 2-3)

**Enforcement (Go):**
- Interfaces are implicit: a type satisfies an interface by having the methods
- Small interfaces: `io.Reader` (1 method), `io.Writer` (1 method), `http.Handler` (1 method)
- Embedding: `type MyStruct struct { BaseStruct }` — composition, not inheritance
- `var _ Interface = (*Impl)(nil)` — compile-time interface satisfaction check

**orbit packages affected:**
- `pkg/tokenrouter` — `type Router interface { Acquire(ctx) (string, error); Release(key) }`. Any implementation that satisfies this interface is a valid token router.
- `pkg/circuitbreaker` — `type Breaker interface { Allow() bool; RecordSuccess(); RecordFailure() }`. Hystrix-style and Envoy-style breakers both satisfy this.
- `pkg/sandbox` — `type Sandbox interface { Shell(cmd) (Output, error); WriteFile(path, data) error }`. The interface hides the containment mechanism.

---

## 5. Parametric Polymorphism — "Generics / Type Parameters"

**Principle:** A function is polymorphic if it works uniformly for all types. The type is a PARAMETER.
`map : ∀A,B. (A → B) → List A → List B` — the same `map` function works for any A and B.

**Formal definition (System F):**
```
Typing rule for type abstraction:
  Γ, X ⊢ t : T
  ----------------
  Γ ⊢ ΛX.t : ∀X.T

Typing rule for type application:
  Γ ⊢ t : ∀X.T
  ----------------
  Γ ⊢ t[U] : [X↦U]T
```

**Purpose:** Without generics, you either write the same code for every type (code duplication) or use `interface{}`/`any` (lose type safety). Generics give you both: one implementation, type-safe at every call site.

**Enforcement (any language):**
- Generics/type parameters for containers and algorithms
- `map`, `filter`, `fold` are polymorphic (they work for any type)
- `Option<T>` / `Result<T, E>` — polymorphic error handling
- No `Object` / `any` / `void*` in public APIs (use generics instead)

**Enforcement (Go):**
- Generics (Go 1.18+): `func Map[T, U any](xs []T, f func(T) U) []U`
- `constraints.Ordered`, `constraints.Integer` — type constraints
- `golang.org/x/exp/maps`, `golang.org/x/exp/slices` — generic collection functions
- Type inference: `Map(xs, func(x int) string { ... })` — T and U inferred

**orbit packages affected:**
- `pkg/tokenrouter` — `type Pool[T any] struct { keys []T; ... }` — the key pool is generic over key type
- `pkg/ggrind` — `func Pipeline[T, U any](input <-chan T, stage func(T) U) <-chan U` — the grind pipeline is generic
- `pkg/store` — `func Store[T any](s *Store, key string, val T) error` — the store is generic over value type

---

## 6. Recursive Types — "Data Structures"

**Principle:** A recursive type is one that refers to itself. Lists, trees, and graphs are all recursive types.
`List A = Nil | Cons A (List A)` — a list of A is either empty or a head of A followed by a tail of List A.

**Formal definition:**
```
Iso-recursive types:
  μα.T  ≅  [α ↦ μα.T]T

Example: List A = μα. (Unit + A × α)
```

**Purpose:** Recursive types are the foundation of data structures. Every tree, every graph, every nested structure is a recursive type. Understanding them means understanding the structure of your data.

**Enforcement (any language):**
- Algebraic data types: sum types (enum) + product types (struct) + recursion
- Pattern matching: exhaustiveness check on recursive types
- Structural recursion: the recursive call is on a structurally smaller value
- Termination: the recursion must be well-founded (no infinite recursion)

**Enforcement (Go):**
- Recursive structs: `type Node struct { Left, Right *Node }`
- `type List[T any] struct { Head T; Tail *List[T] }`
- `type Tree[T any] struct { Value T; Children []*Tree[T] }`
- No native sum types in Go; use `interface{}` + type switch, or sealed interfaces

**orbit packages affected:**
- `pkg/store` — WAL entries form a recursive structure: each entry points to the previous
- `pkg/circuitbreaker` — the state machine is a recursive type: `State → Event → State → Event → ...`
- `pkg/tokenrouter` — the key hierarchy is a tree: key groups contain keys, groups can contain groups
- `pkg/sandbox` — the worktree is a recursive type: directories contain files and directories

---

## 7. Type Inference — "Let the Compiler Figure It Out"

**Principle:** The type system can deduce types from usage, without explicit annotations.
Hindley-Milner (HM) type inference is the gold standard: it is sound, complete, and always finds
the most general type.

**Formal definition:**
```
Given: Γ ⊢ t : ? (unknown type)
Find: the most general type T such that Γ ⊢ t : T
HM: unify type constraints, solve for type variables, produce principal type
```

**Purpose:** Type inference reduces boilerplate: the programmer writes the logic, the compiler figures out the types. But it's also a design tool: if the compiler infers a type that surprises you, your design might be wrong.

**Enforcement (any language):**
- Type inference: `let x = 42` (no type annotation needed)
- The compiler infers the most general type; annotations are for documentation, not necessity
- Gradual typing: annotate public interfaces, infer private ones
- `auto` (C++), `var` (C#/Java), `:=` (Go), type inference in Rust/Haskell/OCaml

**Enforcement (Go):**
- `:=` — short variable declaration with type inference
- `x := f()` — the type of x is inferred from f's return type
- `const x = 42` — the type is inferred from the literal
- Generic type inference: `Map(xs, func(x int) string { ... })` — T and U inferred

**orbit packages affected:**
- Every package. Go's `:=` is type inference at the expression level.
- Go's generics use unification-based type inference for type parameters.
- The `pkg/typechecker` package (if it existed) would implement HM-style inference for a domain-specific language.

---

## 8. Featherweight Calculi — "The Essence of a Language"

**Principle:** To understand a language feature, strip it to its essence. Featherweight Java (FJ) is Java
without assignment, without interfaces, without generics — just classes, inheritance, and method dispatch.
The core calculus is small enough to prove properties about, and the full language is a conservative extension.

**Purpose:** When you're designing a new feature, write the "featherweight" version first — the smallest core that captures the idea. Prove it works. Then add the syntactic sugar. This is the same principle as the tensor equation: strip to the invariant, prove it, then implement.

**Enforcement:**
- Before implementing: write the minimal calculus (1 page) that captures the idea
- Prove progress and preservation for the calculus
- The full implementation is a conservative extension of the calculus
- If the calculus has a problem, the implementation will too

**orbit packages affected:**
- `pkg/congestion` — the VM IS a featherweight calculus: 4 opcodes (push, add, store, load). The full interpreter is a conservative extension.
- `pkg/luaengine` — the Lua sandbox is a restricted version of the full Lua language. The restriction IS the security property.
- `pkg/circuitbreaker` — the state machine IS a featherweight calculus: 3 states, 3 events. Every transition is explicit.

---

## The TAPL Test

For any code, ask:
1. **Progress:** Can this expression get stuck? (nil deref, missing case, infinite loop)
2. **Preservation:** Does this operation preserve the type? (no type cast that loses information)
3. **Abstraction:** What's the λ-calculus of this? (what's the minimal core?)
4. **Subtyping:** Is this interface small enough? (1-3 methods ideal)
5. **Polymorphism:** Would a type parameter eliminate duplication?
6. **Recursion:** Is this data structure well-founded? (does recursion terminate?)
7. **Inference:** Could the compiler deduce this type? (if not, is the annotation necessary?)

TAPL is the proof that types prevent bugs. Every type annotation is a theorem. Every `go build` is a proof check.