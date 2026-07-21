# The Canon — What To Reference, When

Every problem in every repo has already been solved. Here's where.

## Your problems → The book that solved it

| Your Problem | The Reference | Chapter/Section |
|---|---|---|
| **State machines** (circuitbreaker) | Kleppmann, DDIA | Ch 8: "The Trouble with Distributed Systems" |
| **WAL / crash recovery** (store) | Kleppmann, DDIA | Ch 3: "Storage and Retrieval" (LSM-Trees, B-Trees, WAL) |
| **Rate limiting** (tokenrouter) | Kleppmann, DDIA | Ch 4: "Encoding and Evolution" (backpressure) |
| **Retry / backoff** (dispatch) | AWS Builder's Library | "Timeouts, Retries, and Backoff with Jitter" |
| **Lock / lease** (tokenrouter) | Kleppmann, DDIA | Ch 8: "Leader Lock" (fencing tokens) |
| **MVCC / snapshots** (store) | Kleppmann, DDIA | Ch 7: "Transactions" |
| **Sandbox / containment** (sandbox) | gVisor docs + Saltzer & Schroeder 1975 | "The Protection of Information in Computer Systems" |
| **Controller pattern** (dispatch cycle) | Kubernetes docs + Kleppmann, DDIA | Ch 9: "Consistency and Consensus" |
| **Worker pool** (ggrind) | Goetz, "Java Concurrency in Practice" | Ch 6-8: Task Execution, Cancellation, Thread Pools |
| **Module design** (every package) | Ousterhout, "A Philosophy of Software Design" | Entire book (deep modules, information hiding) |
| **Interface/seam** (every adapter) | Feathers, "Working Effectively with Legacy Code" | Ch 4-7: Seams, breaking dependencies |
| **Testing** (every test) | SQLite testing docs | 2+ million test cases pattern |
| **Formal proof** (invariants) | Lamport, "Specifying Systems" (TLA+) | Entire book |
| **UI lifecycle** (voice-engine-swift) | Apple HIG + WWDC sessions | View lifecycle, MainActor |
| **Error handling** (every package) | PostgreSQL source conventions | Primary/Detail/Hint, severity tiers |
| **Concurrency** (tokenrouter, ggrind) | Goetz + OSTEP | Lock ordering, memory model |
| **API design** (btw-v1, MCP) | Fielding, REST dissertation + gRPC design guides | Resource modeling, error codes |
| **Security** (sandbox, auth) | Saltzer & Schroeder + STRIDE | Principles of protection, threat modeling |
| **Performance** (all Go packages) | Hennessy & Patterson, CS:APP | Memory hierarchy, caching patterns |
| **Quality attributes** (availability, modifiability, performance, security, testability) | Bass, Clements, Kazman, SAIP (4th ed. 2021) | Ch. 4-8: Quality attribute scenarios, tactics, tradeoff analysis |
| **Team/process** (how we work) | Brooks, "The Mythical Man-Month" | No silver bullet, conceptual integrity |

## The 10 oracles every agent reads first

### CS Fundamentals (how to think)
1. **SICP** (Abelson & Sussman) — abstraction, higher-order procedures, streams, metacircular evaluation
2. **OSTEP** (Arpaci-Dusseau) — CPU/memory virtualization, concurrency, persistence, scheduling
3. **TAPL** (Pierce) — type safety, progress/preservation, subtyping, parametric polymorphism
4. **Lamport TLA+** (Lamport) — safety, liveness, fairness, refinement, model checking
5. **Owicki-Gries** (Owicki & Gries) — sequential correctness, interference freedom for concurrent programs
6. **Fowler** (Fowler) — refactoring catalog, code smells, two-hats principle
7. **Kernighan & Plaugher** (Kernighan & Plaugher) — simplicity, clarity, generality, debugging, testing
8. **Ousterhout** (Ousterhout) — deep modules, information hiding, strategic vs tactical
9. **Saltzer & Schroeder** (Saltzer & Schroeder) — 8 security design principles, trust boundaries
10. **SAIP** (Bass, Clements, Kazman) — quality attributes as architectural invariants, scenario-based design, attribute tradeoffs

### Infrastructure (how systems stay up)
- etcd, gVisor, Envoy, PostgreSQL, SQLite, PTY — in `docs/research/`

## How agents use the canon

1. Read the problem → map to the reference above
2. Pull the invariant from the reference (don't invent)
3. Write TestAX from the invariant
4. Gate

That's it. The canon is the standard. We don't rewrite Kleppmann. We reference Kleppmann.