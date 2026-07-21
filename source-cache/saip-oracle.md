# SAIP Quality Attribute Oracle (2021)

Source: "Software Architecture in Practice" (Bass, Clements, Kazman, Addison-Wesley, 4th ed. 2021).
ISBN: 978-0-13-688609-9. Also: Len Bass's SEI blog, SATURN conference talks on quality attribute scenarios (2015-2021).

This is the systematization of quality attributes as architectural invariants. Every quality attribute is a constraint on system behavior that must hold across all stimuli, all environments, and all applicable artifacts. The invariant is not "we hope" — it is "we prove or measure."

---

## The SAIP Framework

SAIP defines a quality attribute scenario as a 6-tuple:

```
Scenario = (Source, Stimulus, Artifact, Environment, Response, ResponseMeasure)
```

The **invariant** is that for every stimulus from every source in every environment, the response satisfies the response measure bound. The quality attribute IS this invariant — a constraint that must hold for the architecturally significant requirements.

```
∀source ∈ Src, ∀stimulus ∈ Stim, ∀environment ∈ Env:
  Response(source, stimulus, artifact, environment) satisfies ResponseMeasure
```

---

## 1. Availability

**SAIP Definition (Ch. 4):** Availability is the property that the system is operational and accessible when required for use. It is the probability that the system will be operational when needed in the current environment.

**General Scenario (SAIP Figure 4.1):**
```
Source:         Internal or external to the system
Stimulus:       Fault — omission, crash, timing, or response
Artifact:       Processors, communication channels, persistent storage, processes
Environment:    Normal operation, degraded mode (i.e., fewer features, a backup solution)
Response:       Record fault (log, notify), switch to redundant or degraded mode, continue operation
ResponseMeasure: Uptime percentage, time to detect fault, time to repair, proportion of faults masked
```

**Core Invariants:**

```
1. AVAILABILITY UPTIME INVARIANT:
   ∀time_window W, ∀observations obs:
     uptime(W) = obs.available_samples / obs.total_samples
     ∧ uptime(W) ≥ A_target
   Where A_target is the availability target (e.g., 0.9999 for four-nines, 0.99999 for five-nines)

2. FAULT DETECTION INVARIANT:
   ∀fault F in {omission, crash, timing, response}:
     time_to_detect(F) ≤ T_detect_max
   Where T_detect_max is a bound on how long a fault can persist undetected

3. FAULT RECOVERY INVARIANT (MTTR):
   ∀fault F: mean_time_to_repair(F) ≤ MTTR_max
   ∧ MTBF / (MTBF + MTTR) ≥ A_target
   Where MTBF = mean time between failures, MTTR = mean time to repair

4. REDUNDANCY INVARIANT (failover):
   ∀primary P, ∀backup B:
     P fails → B assumes P's responsibilities
     ∧ failover_time ≤ T_failover_max
     ∧ no_in_flight_data_lost (or explicitly bounded loss)

5. GRACEFUL DEGRADATION INVARIANT:
   ∀subsystem S_sub, ∀failure in S_sub:
     remaining_subsystems continue to satisfy their quality requirements
     ∧ degraded_capability ⊆ full_capability
     (Failure in one subsystem does not cascade to others)
```

**Verification Strategies:**

| Invariant | Verification | Orbit Example |
|---|---|---|
| Uptime | Measurement probe (health endpoint polling), SLI dashboard | dispatch health endpoint, periodic probe |
| Fault detection | Inject faults (chaos engineering), measure time-to-alert | tokenrouter cooldown: 429 response → cooldown within one Acquire cycle |
| Fault recovery (MTTR) | Induce crash, measure time-to-recovery | store: WAL recovery time bound test |
| Redundancy | Kill primary, observe backup takeover | tokenrouter: key rotation on cooldown — another key takes over |
| Graceful degradation | Kill subsystem, verify others still operational | circuitbreaker: Open state on backend A does not affect backend B |

**Orbit Cross-Reference:**

| orbit Package | Availability Mechanism | SAIP Property Defended |
|---|---|---|
| `pkg/circuitbreaker` | Open state blocks failing backends | Fault detection + graceful degradation |
| `pkg/tokenrouter` | Cooldown on 429/5xx, key rotation | Redundancy (multiple keys), fault recovery |
| `pkg/providerrouter` | Exponential backoff, NextAvailable | Fault recovery, graceful degradation |
| `pkg/dispatch` | Max 3 retries, context cancellation | Fault recovery (retry = MTTR reduction) |
| `pkg/store` | WAL with atomic write+rename | Crash recovery (MTTR bound by WAL replay) |
| `pkg/scheduler` | DistLock with TTL, retry on panic | Fault containment, graceful degradation |

---

## 2. Modifiability

**SAIP Definition (Ch. 5):** Modifiability is about the cost of change. The invariant is that for anticipated categories of change, the cost (in person-hours, calendar time, or risk) is bounded. Anticipated changes must be localized — the number of modules that must change is small and known.

**General Scenario (SAIP Figure 5.1):**
```
Source:         Developer, system administrator, end user
Stimulus:       Wishes to add/modify/delete functionality, quality attribute, or capacity
Artifact:       User interface, platform, environment, or system interoperating with target system
Environment:    Design time, compile time, build time, integration time, deployment time, runtime
Response:       Changes made, tested, deployed — without affecting other functionality
ResponseMeasure: Cost in person-hours, effort, money, calendar time; extent of change (modules affected)
```

**Core Invariants:**

```
1. CHANGE LOCALIZATION INVARIANT (Open-Closed Principle as Modifiability):
   ∀anticipated_changes C, ∀artifact A:
     |modules_modified(A, C)| ≤ M_bound
     ∧ |modules_touched_by_test_update(A, C)| ≤ T_bound
   Where M_bound and T_bound are architectural constraints on change propagation.

2. MODIFICATION COST INVARIANT:
   ∀change C in AnticipatedChanges:
     cost(C) ≤ CostBound(C)
     ∧ cost(C) measured in person-hours, calendar time, or modules touched

3. COUPLING INVARIANT (re-stated from SAIP Ch. 5):
   ∀modules M_i, M_j where i ≠ j:
     coupling(M_i, M_j) ∈ {none, data, stamp, control, external, common, content} is minimal
     ∧ adding functionality that modifies only M_i's concern does not require modifying M_j

4. ARCHITECTURAL TACTIC INVARIANT (SAIP Table 5.1):
   For each modifiability tactic T ∈ {localize, prevent ripple, defer binding}:
     ∃at least one mechanism implementing T for every anticipated change category
```

**SAIP Modifiability Tactics (Table 5.1):**

| Tactic | What It Does | Invariant |
|---|---|---|
| **Localize modifications** | Assign responsibilities so anticipated changes stay within one module | `∀change C: ∃!module M such that C affects only M` |
| **Prevent ripple effects** | Use interfaces, intermediaries, and information hiding | `∀change in M_i: ∀j≠i, interface(M_j) unchanged` |
| **Defer binding time** | Build in parameters and config so binding happens late | `∀configuration_param P: change(P) does not require recompilation` |

**Verification Strategies:**

| Invariant | Verification |
|---|---|
| Change localization | Scenario walkthrough: "to add feature X, how many files change?" |
| Modification cost | Measure over N change requests: actual vs. estimated cost |
| Coupling | Static analysis tools, import graph analysis, instability/abstractness metrics |
| Tactics present | Architecture review checklist against SAIP Table 5.1 |

**Orbit Cross-Reference:**

| orbit Package | Modifiability Mechanism | SAIP Tactic |
|---|---|---|
| `pkg/circuitbreaker` | State machine with exhaustive transitions | Localize (add state = add well-defined transition) |
| `pkg/tokenrouter` | Strategy pattern: key rotation, cooldown, pacing are independent | Defer binding (key config, RPM limits are parameters) |
| `pkg/sandbox` | resolve() is single point of path containment | Localize (change path logic in one place) |
| `pkg/luaengine` | Library whitelist is a parameter, not hardcoded | Defer binding (which libraries to allow is config) |
| `pkg/dispatch` | Round function is parameterized | Defer binding (dispatch strategy injected, not baked in) |
| `pkg/ggrind` | Pipeline stages are a slice of interfaces | Localize + prevent ripple (add stage = implement interface) |
| All packages | invariants.md before implementation | Localize (design decision in one doc, code follows) |

**The Ousterhout connection:** SAIP's modifiability tactics are the architecture-level statement of what Ousterhout calls "deep modules" and "information hiding." The secret a module hides IS the thing that might change. SAIP says: "identify anticipated changes, encapsulate each in a module." Ousterhout says: "every module hides a secret." They are the same principle at different altitudes.

---

## 3. Performance

**SAIP Definition (Ch. 6):** Performance is about time and the software system's ability to meet timing requirements. Response time, latency, throughput, and jitter must stay within defined bounds under defined load. Performance is NOT about being fast — it is about meeting deadlines.

**General Scenario (SAIP Figure 6.1):**
```
Source:         Internal or external to the system
Stimulus:       Arrival of events — periodic, stochastic, or sporadic
Artifact:       System or one or more components
Environment:    Normal mode, overload mode, degraded mode
Response:       Process events, change level of service (e.g., shed load)
ResponseMeasure: Latency (min, mean, p95, p99), deadline miss rate, throughput, jitter, data loss
```

**Core Invariants:**

```
1. LATENCY BUDGET INVARIANT:
   ∀request r, ∀component C in processing_chain:
     Σ(latency_C(r)) ≤ deadline(r)
     ∧ ∀C: latency_C(r) ≤ budget_C
   Where the sum of per-component latencies stays within the overall deadline.

2. THROUGHPUT INVARIANT:
   ∀time_window W, ∀system_under_load L:
     completed_requests(W) ≥ throughput_target(W)
     ∧ queued_requests(W) does not grow unboundedly
     (System drains queues under steady load — backpressure is applied)

3. DEADLINE INVARIANT:
   ∀request r with deadline D:
     P(response_time(r) ≤ D) ≥ success_probability_target
   Where success_probability_target is the SLO (e.g., 99.9% of requests under 100ms)

4. OVERLOAD BEHAVIOR INVARIANT (load shedding):
   ∀arrival_rate λ > service_rate μ:
     system_applies_backpressure
     ∧ admitted_rate ≤ μ
     ∧ rejected_requests receive fast failure, not indefinite queue
     (System degrades gracefully under overload — no unbounded queues)

5. RESOURCE UTILIZATION INVARIANT:
   ∀resource R ∈ {CPU, memory, connections, file_descriptors, goroutines}:
     utilization(R) ≤ U_max(R)
     ∧ utilization(R) measured periodically
```

**SAIP Performance Tactics (Table 6.1):**

| Tactic | What It Does | Invariant |
|---|---|---|
| **Control resource demand** | Reduce processing, limit event rate, bound queue sizes | `∀queue Q: size(Q) ≤ Q_max` |
| **Manage resources** | Concurrency, caching, data replication, scheduling | `∀resource R: allocated_instances(R) ≥ demand_instances(R)` |
| **Resource arbitration** | FIFO, fixed priority, dynamic priority, earliest deadline first | `∀request r_i, r_j: deadline(r_i) < deadline(r_j) → r_i served before r_j` |

**Verification Strategies:**

| Invariant | Verification | Orbit Example |
|---|---|---|
| Latency budget | Benchmark with histograms; p50/p95/p99 tracking | dispatch: time to first byte, time to completion |
| Throughput | Load test at multiples of expected load | tokenrouter: RPM tracking per key |
| Deadline | SLO measurement; alert on p99 > threshold | ggrind: per-stage timeout enforcement |
| Overload behavior | Load test beyond capacity; verify fast failure, not hang | circuitbreaker: Open state returns false immediately |
| Resource utilization | Continuous profiling, heap profiles, goroutine counts | Every TestAX leak check: `NumGoroutine` before/after |

**Orbit Cross-Reference:**

| orbit Package | Performance Mechanism | SAIP Tactic |
|---|---|---|
| `pkg/tokenrouter` | RPM cap (290/min), per-key pacing (MinInterval 207ms), MaxConcurrentAcquires | Control demand, manage resources |
| `pkg/circuitbreaker` | Open state: fast-fail without queuing | Control demand (stop sending to dead backend) |
| `pkg/dispatch` | Concurrency semaphore, ctx deadline, max 3 retries | Manage resources, control demand |
| `pkg/ggrind` | Pipeline parallelism, per-stage timeouts | Manage resources, resource arbitration |
| `pkg/congestion` | VM stack cap (65536), stack overflow → error not panic | Control demand |
| `pkg/config` | MaxConcurrentBuilds=4, CompileMemLimitMiB=1800 | Control demand, manage resources |
| `pkg/providerrouter` | Round-robin scheduling, NextAvailable() blocking | Resource arbitration |

**The Envoy connection:** Envoy's circuit breaker (counters, not state machine) is a pure performance tactic: "control resource demand by bounding concurrency." orbit's hybrid model (state machine for failure, but with the option of counter-based per-request isolation) combines SAIP's "control resource demand" and "manage resources" tactics.

---

## 4. Security (CIA Triad as Invariants)

**SAIP Definition (Ch. 7):** Security is the capability of a system to protect data and information from unauthorized access while still providing access to authorized persons and systems. The CIA triad — Confidentiality, Integrity, Availability — is expressed as three simultaneous invariants.

**General Scenario (SAIP Figure 7.1):**
```
Source:         Individual or system — correctly identified, incorrectly identified, internal, external
Stimulus:       Attack — unauthorized attempt to display data, change/delete data,
                access services, change system behavior, or reduce availability
Artifact:       System services, data within system, or system-produced/consumed data
Environment:    Online/offline, connected/disconnected, behind firewall or not
Response:       Authenticate user, authorize access, block access, record attempt, notify entity, restore system
ResponseMeasure: Time to detect, time to recover, proportion of resisted attacks, extent of damage
```

 **Core Invariants (CIA Triad):**

```
1. CONFIDENTIALITY INVARIANT:
   ∀data D, ∀principal P:
     read(P, D) → authorized(P, D)
     ∧ ¬authorized(P, D) → ¬observable(P, D)
   (No unauthorized read. This is Saltzer-Schroeder "Complete Mediation" + "Fail-Safe Defaults")
   (SAIP calls this "resisting unauthorized attempts to display data")

2. INTEGRITY INVARIANT:
   ∀data D, ∀modification M:
     applied(M, D) → authorized(modifier(M), D)
     ∧ D_at_rest = D_as_stored
     ∧ D_in_transit = D_as_sent
   (No unauthorized modification. Data is not corrupted at rest or in transit)
   (SAIP calls this "resisting unauthorized attempts to change/delete data")

3. AVAILABILITY INVARIANT (Security-specific, distinct from general Availability):
   ∀principal P authorized for service S:
     accessible(P, S) = true
     ∧ denial_of_service_attack → P still can access S within SLA
   (Authorized users retain access even under attack)
   (SAIP calls this "resisting attempts to reduce availability")

4. NON-BYPASSABILITY INVARIANT:
   ∀access_path Path to resource R:
     Path passes through security mechanism M
     ∧ ¬∃Path' to R that does not pass through M
   (No backdoors, no unauthenticated paths. Saltzer-Schroeder "Complete Mediation")
```

**SAIP Security Tactics (Table 7.1):**

| Tactic | Sub-tactic | Invariant |
|---|---|---|
| **Detect attacks** | Detect intrusion, detect service denial, detect message delay, verify integrity | `∃audit_log(attempted_access) ∧ detection_time ≤ D_max` |
| **Resist attacks** | Identify actors, authenticate, authorize, encrypt, limit access, maintain integrity | `∀unauthorized_attempt: access_granted = false` |
| **React to attacks** | Revoke access, lock computer, inform actors | `∀detected_attack: mitigation_applied within R_max` |
| **Recover from attacks** | Restore state, identify attackers (audit trail) | `∀successful_attack: pre_attack_state recoverable within T` |

**Verification Strategies:**

| Invariant | Verification | Orbit Example |
|---|---|---|
| Confidentiality | Penetration test, access control audit, data flow analysis | luaengine: library whitelist (no os.execute) |
| Integrity | Checksum validation, tamper detection, WAL replay | sandbox: atomic WriteFile (temp+rename), store: WAL |
| Availability (security) | DDoS simulation, rate-limit verification | tokenrouter: cooldown, RPM cap; circuitbreaker: Open state |
| Non-bypassability | Architecture review: trace every access path through security mechanism | sandbox.resolve(): every file op passes through it |

**Orbit Cross-Reference:**

Already exhaustively covered in `saltzer-schroeder-oracle.md` with STRIDE threat model. Key mapping:

| SAIP Tactic | Saltzer-Schroeder Principle | orbit Mechanism |
|---|---|---|
| Resist — identify actors | Economy of mechanism, fail-safe defaults | tokenrouter: cooldown, pacing |
| Resist — authenticate | Open design, complete mediation | dispatch: bearer token per request |
| Resist — limit access | Least privilege, least common mechanism | luaengine: library whitelist, fresh L state |
| Detect attacks | Compromise recording | tokenrouter: RecordKeyUsage, PerKeyStats |
| Recover from attacks | (Saltzer-Schroeder is silent; SAIP adds this) | store: WAL crash recovery |

---

## 5. Testability

**SAIP Definition (Ch. 8):** Testability is the ease with which software can be made to demonstrate its faults through testing. A system is testable if its internal state is observable and controllable — you can see what happened, and you can put the system into the state you want to test.

**General Scenario (SAIP Figure 8.1):**
```
Source:         Developer, tester, integration tester, user, system administrator
Stimulus:       Analysis, architecture review, design check, test execution
Artifact:       Design, piece of code, complete system
Environment:    Design time, development time, compile time, integration time, deployment time
Response:       Provides access to state values, computes complexity metrics, finds fault
ResponseMeasure: Effort to find fault, effort to achieve coverage, probability of finding fault,
                 time to perform tests, effort to control and observe, length of longest test dependency chain
```

**Core Invariants:**

```
1. OBSERVABILITY INVARIANT:
   ∀internal_state S relevant to behavior B:
     ∃test_interface I such that observe_B(I, S) = true
     ∧ S is externally readable without modifying production code paths
   (Every behaviorally-relevant state is test-observable)

2. CONTROLLABILITY INVARIANT:
   ∀state S necessary for test T:
     ∃mechanism M to set_S(T) without executing unrelated code paths
     ∧ time_to_set_up(S) is sub-second for unit tests
   (Every test-relevant state is reachable through the test harness)

3. SEPARABILITY INVARIANT:
   ∀component C:
     ∃test suite T(C) that tests C in isolation from its dependencies
     ∧ T(C) does not require running the full system
   (Components can be tested independently — no "test the monolith" bottleneck)

4. TEST EXECUTION TIME INVARIANT:
   ∀unit_test T:
     execution_time(T) ≤ T_unit_max (target: <1 second, SAIP suggests milliseconds)
     ∧ full_test_suite_time ≤ T_suite_max (target: <5 minutes for P0 gate)

5. DETERMINISM INVARIANT:
   ∀test T, ∀executions E₁, E₂:
     same_input(E₁, E₂) ∧ same_environment(E₁, E₂) → same_result(E₁, E₂)
   (Tests are deterministic — no flaky tests. A failing test always fails; a passing test always passes)
```

**SAIP Testability Tactics (Table 8.1):**

| Tactic | What It Does | Invariant |
|---|---|---|
| **Control and observe system state** | Provide interfaces to set/get state, abstract data sources, sandbox external dependencies | `∀state: set(S) and get(S) are available through test interface` |
| **Limit complexity** | Limit structural complexity, limit nondeterminism, limit dependencies | `∀component C: cyclomatic_complexity(C) ≤ CC_max` |

**Verification Strategies:**

| Invariant | Verification |
|---|---|
| Observability | Architecture review: for each behavioral invariant, is there a test that observes it? |
| Controllability | Test coverage of error paths: can we inject faults at every level? |
| Separability | Unit test vs. integration test ratio: target >80% unit, <20% integration |
| Test execution time | CI pipeline timing; `go test -count=1 -timeout` enforcement |
| Determinism | Rerun test suite N times; zero flakes tolerated |

**Orbit Cross-Reference:**

| orbit Package | Testability Mechanism | SAIP Tactic |
|---|---|---|
| `pkg/circuitbreaker` | TestAX gates for every state transition; exported Allow/State for observation | Control and observe |
| `pkg/tokenrouter` | BucketTime is atomically accessible; KeyState exported for test inspection | Control and observe |
| `pkg/sandbox` | Real filesystem tests (not mocked); resolve() is testable independently | Separability |
| `pkg/luaengine` | RunRule takes script as string parameter; no external dependencies | Separability, controllability |
| `pkg/sqlite/testing` | SQLite's 4-level assertion typology: invariant/always/boundary/corrupt | Limit complexity |
| All packages | invariants.md → TestAX mapping requires every equation to have a gate | Observability |
| `pkg/dispatch` | Exported NewDispatcher takes config struct; mock HTTP transport possible | Controllability |
| `pkg/ggrind` | Pipeline stages are interfaces: inject mock stages for testing | Separability |

**The SQLite connection:** SQLite's testing methodology (590:1 test-to-code ratio, 100% branch coverage) is the gold standard for SAIP's testability tactics. orbit's invariants.md-to-TestAX mapping is the lightweight version: every invariant in the spec has an executable gate. A declared invariant without a TestAX is testability debt — the state is claimed observable but is not actually observed.

---

## Quality Attribute Tradeoffs (SAIP Ch. 2, 13)

SAIP emphasizes that quality attributes interact — improving one often degrades another. These interactions are themselves invariants that must be architecturally managed.

```
TRADEOFF — Security vs. Performance:
  ∀security_check C in request_path:
    latency_overhead(C) is bounded and known
    ∧ C does not violate latency_budget for its tier

TRADEOFF — Availability vs. Consistency (CAP-like):
  ∀partition_event: choose(availability, consistency) is explicit
    ∧ the choice is documented per-operation, not per-system

TRADEOFF — Modifiability vs. Performance:
  ∀abstraction_layer L:
    overhead(L) is known (e.g., virtual dispatch, indirection)
    ∧ benefit(L) in modifiability terms is documented
    (Indirection is a cost you accept for flexibility — but you must know the cost)

TRADEOFF — Testability vs. Performance:
  ∀test_hook H in production_path:
    overhead(H) in production = 0 (compiled out, build tags)
    ∨ overhead(H) is negligible (<1% throughput)
```

---

## Cross-Reference: SAIP Quality Attributes x orbit Packages

| Package | Availability | Modifiability | Performance | Security | Testability |
|---|---|---|---|---|---|
| `circuitbreaker` | Fault detection via Open state | State machine: add state = add case | Fast-fail on Open | DoS resistance | Exported State, TestAX for every transition |
| `tokenrouter` | Key rotation, cooldown recovery | Key config injected at construction | RPM cap, per-key pacing, jitter | Confidentiality of API keys (in-memory) | BucketTime atomic, KeyState exported |
| `sandbox` | Path containment (no escape = no crash) | resolve() is single point of change | Atomic writes, no buffering | Integrity (path traversal prevention) | Real FS tests, no mocking |
| `luaengine` | Fresh L state per call (no cross-contamination) | Library whitelist is a parameter | SkipOpenLibs reduces init overhead | Least privilege, no os.execute | RunRule takes string script |
| `dispatch` | Retry (MTTR reduction), ctx deadline | Round function parameterized | Concurrency semaphore, bounded retries | Bearer token per request | Config struct, mockable transport |
| `ggrind` | Pipeline continues past stage failure | Add stage = implement interface | Per-stage timeouts, parallelism | N/A (internal pipeline) | Stage interface, mock injection |
| `store` | WAL crash recovery | Storage backend is an interface | Atomic writes, no fsync in hot path | Integrity (WAL prevents torn writes) | Interface-based, in-memory backend for tests |
| `scheduler` | DistLock TTL, panic recovery | Job scheduling policy is swappable | Priority queue for scheduling | N/A (internal) | MemDistLock for unit tests |
| `congestion` | Stack overflow → error, not crash | VM opcodes are a well-defined set | Stack cap at 65536 | N/A (internal VM) | Compile+Run API is testable |
| `providerrouter` | Exponential backoff recovery | Per-provider config | Round-robin, NextAvailable() | API keys from env vars | InBackoff() exported for test observation |

---

## SAIP Quality Attribute Workshop (QAW) Lite

SAIP describes a Quality Attribute Workshop as the method for eliciting quality attribute scenarios. For orbit's purposes, the lightweight version is:

1. **Identify drivers:** For each package, which 2-3 quality attributes matter most?
2. **Write scenarios:** For each driver, write one concrete scenario (stimulus + response + measure)
3. **Extract invariants:** Each scenario yields one or more tensor equations
4. **Gate:** Each invariant gets a TestAX gate

**Example — circuitbreaker:**
```
Driver:        Availability
Scenario:      Backend returns 5xx on 3 consecutive requests → circuit opens → traffic blocked
Invariant:     AX-001: ∀backend B: consecutive_failures(B) ≥ threshold → Allow(B) returns false
Gate:          TestAX001_OpenCircuitBlocksTraffic
```

**Example — tokenrouter:**
```
Driver:        Performance
Scenario:      RPM approaches 300 → per-key pacing activates → no key exceeds 290 RPM
Invariant:     ∀k,t: RequestBuckets[k][t] ≤ RPM/60
Gate:          TestAX per-second request cap assertion
```

**Example — sandbox:**
```
Driver:        Security (Integrity)
Scenario:      Attacker submits path "../../../etc/passwd" → resolve() returns error
Invariant:     ∀path: resolved_path within worktree_root
Gate:          TestAX path traversal rejection
```

---

## Integration with orbit's Existing Framework

SAIP does not replace orbit's existing oracles — it systematizes them:

| orbit Framework Lens | SAIP Quality Attribute | SAIP Source (Ch.) |
|---|---|---|
| Lens 1: Relationship Arrows (Infrastructure) | Availability, Performance | Ch. 4, 6 |
| Lens 2: Deep Modules (Design) | Modifiability | Ch. 5 |
| Lens 3: Platform Contracts (Apps/UI) | (Performance via platform SLAs) | Ch. 6 |
| Lens 4: Temporal Logic (Proofs) | (Cross-cutting: formalizes all attributes) | — |
| Lens 5: Data Quality (ML/Data) | (Domain-specific; SAIP doesn't cover) | — |
| Lens 6: Trust Boundaries (Security) | Security (CIA triad) | Ch. 7 |
| Lens 7: Resource Contracts (Performance) | Performance | Ch. 6 |

**What SAIP adds that orbit's framework doesn't yet have:**
- Systematic quality attribute scenarios with stimulus/response/measure
- Explicit tradeoff analysis between attributes
- Modifiability as a first-class architectural invariant (not just Ousterhout design discipline)
- Testability as a first-class architectural invariant (not just SQLite testing methodology)
- Availability as distinct from fault tolerance (with MTBF/MTTR formalization)

**What orbit already has that SAIP formalizes:**
- Security: Saltzer-Schroeder + STRIDE (SAIP Ch. 7 cites Saltzer-Schroeder)
- Performance: Envoy resource contracts (SAIP's "manage resources" tactic)
- Design: Ousterhout deep modules (SAIP's "localize modifications" tactic)

---

## The SAIP Test

For any architectural decision, ask:
1. **Availability:** If this component fails, what masks the failure? What is the MTTR?
2. **Modifiability:** If this component's implementation changes, how many other files change?
3. **Performance:** What is the latency budget for this code path? What is the throughput bound?
4. **Security:** What CIA property does this component defend? Where is the trust boundary?
5. **Testability:** Can I observe every behaviorally-relevant state? Can I inject every fault I need to test?

SAIP is the architecture-level systematization of what the other oracles teach at the design level. Ousterhout teaches how to design a module. SAIP teaches why the module must exist — which quality attribute it defends, and how to prove it does.
