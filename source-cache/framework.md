# The Framework

**One file. Every principle. Apply the right lens for the right problem.**

---

## When to use which lens

| Problem type | Lens | Source |
|---|---|---|
| Services, proxies, databases, sandboxes | **Relationship Arrows** | etcd, gVisor, SQLite, Hystrix, Envoy |
| API design, module structure, testability | **Deep Modules** | Ousterhout, Feathers |
| iOS, macOS, UI, animation | **Platform Contracts** | Apple HIG, UIKit/SwiftUI lifecycle |
| Formal proofs, safety-critical | **Temporal Logic** | TLA+, Lean, DO-178C |
| ML models, data pipelines | **Data Quality** | TFX, model cards, drift detection |
| Security, sandboxing, auth | **Trust Boundaries** | STRIDE, seccomp, gVisor |
| Performance, resource usage | **Resource Contracts** | GC, ARC, backpressure |

---

## Lens 1: Relationship Arrows (Infrastructure)

Every bug is a broken relationship between two components.

| Arrow | Reads | Violation |
|---|---|---|
| **Causality** | "A happens before B" | Race condition, uninit memory |
| **Ownership** | "Only X owns R" | Double-free, leaked resource |
| **Containment** | "Value stays inside bounds" | Path traversal, buffer overflow |
| **Correspondence** | "State A mirrors State B" | Cache inconsistency, stale replica |
| **Exclusion** | "A and B cannot both hold" | Deadlock, split-brain |
| **Rate** | "≤ N events per window" | DoS, retry storm, token exhaustion |
| **Liveness** | "Event E eventually happens" | Goroutine leak, starvation |
| **Freshness** | "Data has timestamp T" | Stale data served as current |
| **Uniqueness** | "ID appears exactly once" | Duplicate, missing entry |
| **Persistence** | "Survives crash/restart" | Lost data, corrupt state |
| **Atomicity** | "All-or-nothing" | Partial update, torn write |
| **Idempotency** | "Do it once = do it N times" | Double-charge, replay attack |
| **Isolation** | "Concurrent = sequential" | Dirty read, lost update |
| **Non-Interference** | "Operation A doesn't disturb B" | Clipboard destroyed by paste |
| **Reversibility** | "Can undo to prior state" | Failed migration leaves corrupt DB |

**Process:** For each component, ask "what breaks if X?" Write the invariant. Write the test.

---

## Lens 2: Deep Modules (Design)

Design is about interfaces, not implementations. From Ousterhout/Feathers.

| Principle | Reads | Anti-pattern |
|---|---|---|
| **Depth** | "Large behavior behind small interface" | Shallow: interface as complex as code |
| **Information Hiding** | "Caller doesn't need to know" | Leaky abstraction |
| **Seam** | "Can alter behavior without editing there" | Hardcoded dependency |
| **Locality** | "Change in one place" | Same change across N files |
| **Leverage** | "One implementation, N callers" | Every caller reimplements |
| **Test surface = Interface** | "Tests cross the same seam as callers" | Testing internals, brittle tests |
| **Deletion test** | "Delete module → complexity vanishes or spreads?" | Pass-through modules |
| **Accept, don't create dependencies** | `fn(order, gateway)` not `fn(order)` that news Stripe | Untestable code |
| **Return, don't side-effect** | `fn(cart) → Discount` not `fn(cart) mutates cart` | Hidden mutation |

**Process:** For each module, ask: "Can I make the interface smaller? Can I hide more? Does deletion spread complexity or remove it?"

---

## Lens 3: Platform Contracts (Apps/UI)

Every platform has contracts. Violating them = crash, jank, or rejection.

### iOS/macOS (Swift)
| Contract | Reads | Enforcement |
|---|---|---|
| **Main thread UI** | All UIKit/AppKit updates on main queue | MainActor, runtime assertion |
| **View lifecycle** | viewDidLoad → viewWillAppear → viewDidAppear | Order enforced by UIKit |
| **Memory** | ARC retain cycles → leak | Xcode memory graph, instruments |
| **Background** | Limited time, specific task types | BackgroundTasks framework |
| **Sandbox** | No filesystem access outside container | OS-enforced (like gVisor L1) |
| **Accessibility** | VoiceOver, Dynamic Type | UIAccessibility protocol |
| **Animation** | 60fps, no main-thread blocking | CADisplayLink, instruments |

### Web (JS/TS)
| Contract | Reads | Enforcement |
|---|---|---|
| **Event loop** | Don't block the main thread | async/await, Web Workers |
| **DOM consistency** | Render = f(state), never mutate DOM directly | React/Vue/Svelte |
| **Same-origin** | Script can only access same origin | Browser-enforced |
| **CSP** | Only allowed script sources execute | Content-Security-Policy header |

**Process:** For each platform API used, ask: "What contract does this API impose? What happens if I violate it?"

---

## Lens 4: Temporal Logic (Proofs)

For when tests aren't enough. TLA+/PlusCal/Lean.

| Property | Reads | Example |
|---|---|---|
| **Safety** | "Bad thing never happens" | `□(state ≠ Corrupted)` |
| **Liveness** | "Good thing eventually happens" | `◇(request → response)` |
| **Fairness** | "If enabled infinitely often, eventually executes" | Weak/strong fairness |
| **Refinement** | "Concrete impl ≤ Abstract spec" | `Impl ⇒ Spec` |
| **Invariant** | "Always true" | `□(lock_count ≥ 0)` |
| **Temporal** | "Eventually always" | `◇□(leader_elected)` |

**Process:** Identify the 1-3 critical safety properties. Write in PlusCal. Model check with TLC. Generate TestAX from counterexamples.

---

## Lens 5: Data Quality (ML/Data)

For pipelines, models, and data-dependent systems.

| Property | Reads | Detection |
|---|---|---|
| **Schema** | "Column X is type Y, not null" | Great Expectations, schema validation |
| **Distribution** | "Feature Z ∈ [0, 1] with μ=0.5" | Drift detection, KS test |
| **Completeness** | "No missing values in required columns" | Null check, imputation |
| **Lineage** | "This data came from that source at time T" | Data catalog, metadata |
| **Freshness** | "Data is ≤ N hours old" | Timestamp check, SLA monitor |
| **Privacy** | "PII is masked or absent" | Differential privacy, k-anonymity |

---

## Lens 6: Trust Boundaries (Security)

Every system has trust boundaries. Crossing one = potential vulnerability.

| Boundary | Reads | Enforcement |
|---|---|---|
| **Network → Process** | "Input is adversarial" | Input validation, fuzzing |
| **Process → File System** | "Path is contained" | Sandbox, chroot, seccomp |
| **User → Kernel** | "Syscall args are validated" | Kernel validation, CAP_SYS_* |
| **Tenant A → Tenant B** | "No cross-tenant data access" | Namespace isolation, authz |
| **Public → Admin** | "Auth required for privileged ops" | AuthN + AuthZ + audit log |

---

## Lens 7: Resource Contracts (Performance)

Every resource has a contract. Violating it = degraded system.

| Resource | Contract | Detection |
|---|---|---|
| **Memory** | "≤ N bytes allocated, freed when done" | Allocations instrument, heap profiles |
| **CPU** | "Operation completes in ≤ T ms" | Timeout, p99 latency tracking |
| **File descriptors** | "Open → close, max N concurrent" | lsof, FD leak detection |
| **Connections** | "Connect → use → close, pool size ≤ N" | Connection pool metrics |
| **Goroutines** | "Start → exit, no leaks" | runtime.NumGoroutine before/after |
| **Disk** | "Write ≤ N bytes, fsync when durable" | Disk usage monitoring |

---

## How to use this

1. **Classify the problem.** Infrastructure? Design? UI? Proof? ML? Security? Performance?
2. **Apply the right lens.** Sometimes 2-3 lenses apply simultaneously.
3. **For each property in the lens, ask:** "Does my code satisfy this? What's the test?"
4. **Write the invariant.** ∀x: expr.
5. **Write the test.** TestAX*, platform test, property check, or proof.
6. **Gate.** P0 for crashes and invariants. P1 for provable violations. P2 for style.

The lens tells you WHAT to check. The battle-tested reference tells you HOW to enforce it. The TestAX test proves you did.