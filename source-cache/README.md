# Research Pipeline — Oracle Catalog

Battle-tested invariants extracted from canonical sources. Each oracle is language-agnostic —
principles stated as formal invariants, enforcement patterns shown across paradigms,
orbit-specific applications noted where relevant.

## CS Fundamentals (How to think, design, prove, refactor)

| File | Source | Principles | Status |
|---|---|---|---|
| `owicki-gries-oracle.md` | Owicki & Gries (1976) | Sequential correctness, interference freedom for concurrent programs | ✅ COMPLETE |
| `saltzer-schroeder-oracle.md` | Saltzer & Schroeder (1975) | 8 security design principles, trust boundaries | ✅ COMPLETE |
| `sicp-oracle.md` | Abelson & Sussman (1985/1996) | Procedural/data abstraction, higher-order procedures, streams, metacircular evaluation | ✅ COMPLETE |
| `ostep-oracle.md` | Arpaci-Dusseau (2015) | CPU/memory virtualization, concurrency primitives, persistence, scheduling, security | ✅ COMPLETE |
| `tapl-oracle.md` | Pierce (2002) | Type safety (progress + preservation), subtyping, parametric polymorphism, recursive types | ✅ COMPLETE |
| `lamport-tla-oracle.md` | Lamport (2002) | Safety, liveness, fairness, refinement, stuttering, model checking, PlusCal | ✅ COMPLETE |
| `fowler-oracle.md` | Fowler (1999/2002) | Refactoring catalog, code smells, two-hats principle, enterprise patterns | ✅ COMPLETE |
| `kernighan-plaughter-oracle.md` | Kernighan & Plaugher (1974/1999) | Simplicity, clarity, generality, interfaces, debugging, testing, portability | ✅ COMPLETE |
| `ousterhout-oracle.md` | Ousterhout (2018) | Deep modules, information hiding, strategic programming, design-it-twice | ✅ COMPLETE |

## Infrastructure (How systems stay up)

| File | System | Principles | Status |
|---|---|---|---|
| `gvisor.md` | gVisor | Sandbox safety (7 defense layers), O_NOFOLLOW, shell confinement | ✅ COMPLETE |
| `envoy.md` | Envoy | Circuit breaker as resource manager, retry budget, per-priority isolation | ✅ COMPLETE |
| `postgresql.md` | PostgreSQL | Error severity tiers, WAL, MVCC, process model | ✅ COMPLETE |
| `sqlite-testing.md` | SQLite | Testing methodology (2M+ test cases), 100% branch coverage approach | ✅ COMPLETE |
| `pty.md` | POSIX/PTY | PTY lifecycle, signal propagation, raw vs cooked mode, EIO on master close | ✅ COMPLETE |

## Platform (How platforms enforce contracts)

| File | System | Principles | Status |
|---|---|---|---|
| `pty.md` | PTY/terminal | POSIX termios, escape sequences, flow control | ✅ COMPLETE |

## Framework (The glue)

| File | Purpose | Status |
|---|---|---|
| `framework.md` | 7 lenses that map problem types to oracles + invariant patterns | ✅ COMPLETE |
| `canon.md` | Routing table: "your problem → the canonical reference that solved it" | ✅ COMPLETE |

---

## How To Use This

### When encountering a problem

1. **Classify the problem type** using `framework.md` — Infrastructure? Design? Concurrency? Security?
2. **Apply the right lens** — the lens tells you WHICH oracle to consult
3. **Pull the invariant** from the oracle — don't invent, reference
4. **Write the tensor equation** in the relevant `pkg/*/invariants.md`
5. **Write the TestAX proof** in the relevant `pkg/*/ax_test.go`
6. **Gate** — P0 for crashes, P1 for invariant violations with line evidence

### When designing a new module

1. **Consult Ousterhout** — is the interface deep? What's the secret?
2. **Consult Fowler** — is there a pattern that already solves this?
3. **Consult Kernighan** — is this the simplest thing that works?
4. **Write the invariant first** — if you can't state the invariant, you don't understand the problem

### When reviewing code

1. **Check invariants.md** — does the code satisfy every tensor equation?
2. **Run TestAX gates** — does every invariant have a passing test?
3. **Check against the oracle** — does the implementation match the canonical pattern?

---

## Gap Tracker

Known gaps between oracle invariants and current implementation:

| Gap | Oracle Source | Our Subsystem | Severity | Status |
|---|---|---|---|---|
| No fencing token on Acquire | etcd leases | tokenrouter | P1 | Open |
| HalfOpen allows unlimited traffic | Hystrix/Envoy | circuitbreaker | P1 | Open |
| No retry budget (global cap) | Envoy | dispatch | P2 | Open |
| 7 packages have invariants.md but no ax_test.go | — | tokenrouter, dispatch, ggrind, codemetrics, congestion, scheduler, store | P1 | Open |

---

## Process

1. Agent identifies invariant violation or design question
2. Consults the relevant oracle (via `framework.md` → lens → oracle)
3. Writes invariant as tensor equation in `pkg/<pkg>/invariants.md`
4. Implements code against the invariant
5. Writes TestAX proof
6. P0 gate passes (`go build`, `go test -race`, `golangci-lint`)
7. Axiom extracted to `axioms/axioms.json` via `axiom-ingestor`
