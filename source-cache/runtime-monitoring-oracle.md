# Runtime Monitoring and Observability Oracle

Extracted invariants from the canonical primary sources on runtime verification, monitoring, observability, and formal correctness.

**Sources:** Meyer (1997), Lamport (1977), Alpern & Schneider (1985), Leveson (2011), Google SRE (2016), Havelund & Rosu (2001), Bartocci et al. (2018), Prometheus/OpenMetrics.

**Total axioms extracted:** 40 (AX-ORACLE-MONITOR-001 through AX-ORACLE-MONITOR-040)

---

## 1. Meyer — "Object-Oriented Software Construction" (1997)

### Design by Contract

Meyer introduced Design by Contract: software components interact through precisely specified contracts consisting of preconditions, postconditions, and class invariants. These are runtime-checkable assertions.

**Core invariants (5 axioms):**

```
AX-ORACLE-MONITOR-001: ∀class C, ∀instance o, ∀public_method m, ∀call_time t:
  pre_m(o,t) ∧ inv_C(o,t_before) → post_m(o,t_after) ∧ inv_C(o,t_after)

AX-ORACLE-MONITOR-002: ∀method m, ∀call:
  pre_m(call_args) = false → fault ∈ caller
  post_m(call_result) = false → fault ∈ callee

AX-ORACLE-MONITOR-030: ∀class C, ∀method m, ∀instance o:
  inv_C(o) holds at entry(m) ∧ exit(m); may be temporarily false during body(m)

AX-ORACLE-MONITOR-031: ∀subclass S, ∀parent P, ∀method m:
  pre_S(m) ⇒ pre_P(m) ∧ post_P(m) ⇒ post_S(m)

AX-ORACLE-MONITOR-036: ∀assertion A:
  A is false → halt(program); ¬∃recovery_path from broken invariant
```

### Key principles
- **Class invariant:** A condition that holds for all instances at all stable times (before/after public method calls).
- **Blame assignment:** Precondition violation = caller's bug. Postcondition violation = callee's bug.
- **Fail fast:** A broken invariant means the program state is corrupt. Continue = undefined behavior.
- **Inheritance rules:** Subclass weakens precondition (or equal), strengthens postcondition (or equal). This is the Liskov Substitution Principle in contract form.

### orbit relevance
- Every `pkg/*/invariants.md` is the class invariant for that package.
- Runtime assertions at public API boundaries = precondition/postcondition checks.
- Panic on invariant violation = fail fast.
- Interface implementations must satisfy the interface contract (postcondition strengthening).

---

## 2. Lamport — "Proving the Correctness of Multiprocess Programs" (1977)

### Safety and Liveness for Concurrent Systems

Lamport's foundational paper introduced assertional reasoning for concurrent programs: annotate program points with assertions, prove each atomic action preserves the invariant, conclude the invariant holds in all reachable states.

**Core invariants (4 axioms):**

```
AX-ORACLE-MONITOR-003: ∀reachable_state s: I(s) holds (safety)

AX-ORACLE-MONITOR-004: ∀fair_execution e: ◇P(e) (liveness: eventually P holds)

AX-ORACLE-MONITOR-025: ∀program P, ∀program_point p, ∀execution:
  assertion_A(p) must hold whenever execution reaches p

AX-ORACLE-MONITOR-026: ∀critical_section CS:
  □(at_most_one_process_in(CS)) is safety
  ∀p_ready: ◇(p enters CS) is liveness
```

### Key principles
- **Safety:** "Nothing bad happens." Violated at a specific, observable point in time.
- **Liveness:** "Something good eventually happens." Cannot be violated at a single point — only over infinite behavior.
- **Assertional reasoning:** Prove an inductive invariant: it holds at the entry point, and every atomic action preserves it.
- **Mutual exclusion** is safety; **starvation-freedom** is liveness. Both must be proved.

### orbit relevance
- Every P0/P1 finding is a safety violation.
- TestAX gates prove safety properties.
- Timeout-based tests prove liveness properties.
- `go test -race` checks mutual exclusion (safety).
- Every goroutine entry point should have a runtime assertion.

---

## 3. Alpern & Schneider — "Defining Liveness" (1985)

### Topological Characterization

The definitive formal characterization: safety properties are the closed sets, liveness properties are the dense sets in the natural topology on execution sequences.

**Core invariants (3 axioms):**

```
AX-ORACLE-MONITOR-005: ∀property P:
  P = S_P ∩ L_P, where S_P is safety, L_P is liveness

AX-ORACLE-MONITOR-006: ∀safety_property S:
  ∃runtime_monitor M such that ∀prefix p: M(p) = reject iff p cannot be extended to satisfy S

AX-ORACLE-MONITOR-007: ∀liveness_property L:
  ¬∃finite_prefix_monitor M such that M enforces L
```

### Key principles
- **Every property** decomposes into safety ∩ liveness.
- **Safety** is enforceable by runtime monitors that reject bad finite prefixes.
- **Liveness** cannot be enforced by finite-prefix rejection — requires fairness + timeouts.
- A safety violation is observable in finite time: some finite prefix is "already bad."
- A liveness violation is never observable in finite time: any prefix can still be extended to satisfy.

### orbit relevance
- Every package's invariants.md declares both safety and liveness invariants.
- Runtime assertions and circuit breakers enforce safety.
- Deadlines and timeout alerts detect liveness violations.
- The decomposition P = safety ∩ liveness is the template for specifying correctness.

---

## 4. Leveson — Software System Safety / STPA

### Safety as a Control Problem

Leveson's STPA (System-Theoretic Process Analysis) reframes safety: hazards arise when safety constraints are inadequately enforced in a control structure. Safety is a control problem, not a component-failure problem.

**Core invariants (6 axioms):**

```
AX-ORACLE-MONITOR-008: ∀hazard H:
  ∃safety_constraint C: C prevents H
  monitored_at_runtime(C) ∧ violation(C) → fail_closed

AX-ORACLE-MONITOR-009: ∀hazard H:
  ∃leading_indicator L: L(t) → ◇H(t+δ) for some δ > 0

AX-ORACLE-MONITOR-032: ∀system S:
  before_code(S): hazards(S) are identified
  ∀hazard H: ∃safety_constraint C formalized as tensor equation

AX-ORACLE-MONITOR-033: ∀safety_constraint C:
  ∃controller K: K monitors C, detects violations, applies corrective action
  K is independent of the plant

AX-ORACLE-MONITOR-035: ∀component C:
  failure_mode_analysis(C) is complete
  ∀failure_mode F: F has detection ∧ F has mitigation
```

### Key principles
- **Fail closed:** A safety constraint violation must block the operation, not allow it.
- **Leading indicators:** Measure precursors to hazards, not just the hazards themselves.
- **Hazard analysis before code:** Identify hazards, then safety constraints, then implement.
- **Control loops:** Monitor (sensor), compare to constraint, correct (actuator).
- **Failure mode enumeration:** Every component's failure modes must be analyzed and mitigated.

### orbit relevance
- Circuit breaker, token router, sandbox all fail closed.
- Leading indicators: failure count → circuit breaker trip; bucket depletion rate → rate limit.
- invariants.md = STPA step 3 (safety constraints as tensor equations).
- Every package needs failure mode enumeration.

---

## 5. Google SRE Book (2016)

### Four Golden Signals, Error Budgets, Alerting Philosophy

The SRE book operationalizes reliability: measure the right things, alert on the right conditions, and use error budgets to gate release velocity.

**Core invariants (9 axioms, extending APPLIED-007/008):**

```
AX-ORACLE-MONITOR-010: ∀service S:
  monitored(S, {latency, traffic, errors, saturation})

AX-ORACLE-MONITOR-011: ∀alert A:
  trigger(A) = symptom(user_visible); pages are symptoms only

AX-ORACLE-MONITOR-012: ∀service S, ∀window W:
  burn_rate(S,W) = error_rate(S,W) / error_budget_rate(S)
  burn_rate > 14.4 → page; burn_rate > 2 → ticket

AX-ORACLE-MONITOR-027: ∀service S:
  saturation(S) = max_{resource r} utilization(r)/capacity(r)

AX-ORACLE-MONITOR-028: ∀service S:
  latency(S) reported as p50/p95/p99 histogram; ¬use_mean(latency)

AX-ORACLE-MONITOR-029: ∀service S:
  error_rate(S) = rate(explicit_failures) + rate(implicit_failures)

AX-ORACLE-MONITOR-037: ∀alert A:
  threshold(A) derived from SLO; ∃SLO S: threshold(A) = f(S)

AX-ORACLE-MONITOR-038: ∀alert A: ∃metric m: A fires ⇔ m exceeds threshold
  ∀metric m: ∃consumer C such that C uses m

AX-ORACLE-MONITOR-039: ∀service_endpoint E:
  monitored(E, {rate, errors, duration})  [RED method]
```

### Key principles
- **Four golden signals:** latency, traffic, errors, saturation — the minimum set every service exports.
- **Symptoms not causes:** Page on what users experience; ticket on what might go wrong.
- **Error budgets:** gate release velocity. Budget exhausted → no feature releases.
- **Burn rate alerting:** multi-window, multi-burn-rate prevents both false positives and false negatives.
- **RED method:** Rate, Errors, Duration — per-endpoint minimum instrumentation.
- **No dead metrics, no phantom alerts:** Every metric consumes resources; justify it.

### orbit relevance
- Dispatch must export four golden signals + RED per endpoint.
- Token router must track burn rate for rate limits.
- Latency must be histogram, never mean.
- Error rate must include implicit failures (HTTP 200 but too slow).
- Saturation must measure the bottleneck resource (goroutines for ggrind).

---

## 6. Havelund & Rosu — "Monitoring Programs Using Rewriting" (2001)

### Rewriting-based Runtime Verification

Introduced rewriting-based runtime verification: specifications as rewrite rules that reduce the execution trace. Distinguished past-time LTL (always monitorable online) from future-time LTL (requires bounded lookahead or offline analysis).

**Core invariants (3 axioms):**

```
AX-ORACLE-MONITOR-016: ∀monitor M, ∀spec φ, ∀trace σ:
  M(σ, φ) = violation → σ ⊭ φ (soundness: no false positives)

AX-ORACLE-MONITOR-017: ∀monitor M, ∀spec φ, ∀trace σ:
  σ ⊭ φ → ∃prefix p ≤ σ: M(p, φ) = violation (completeness up to prefix)

AX-ORACLE-MONITOR-018: ∀past_time_LTL φ: online_monitorable(φ)
  ∀future_time_LTL ψ: online_monitorable(ψ) only with bounded lookahead
```

### Key principles
- **Soundness:** If the monitor reports violation, the trace truly violates the spec. No false positives.
- **Completeness:** If the trace violates the spec, the monitor detects it at the earliest observable prefix. No false negatives (up to observed prefix).
- **Past-time vs future-time:** Past-time LTL ("previously," "sometime in the past") is always monitorable online. Future-time LTL ("eventually," "always") requires bounded lookahead or offline analysis.

### orbit relevance
- TestAX gates must be sound (test failure = true invariant violation) and complete (all violations detected).
- Circuit breaker monitoring uses past-time LTL ("was Open before, now got success").
- Grind pipeline is offline analysis (completed traces).

---

## 7. Bartocci et al. — "Runtime Verification" (2018)

### Comprehensive Survey

The definitive survey of runtime verification: online vs offline monitoring, specification languages, instrumentation strategies, and overhead constraints.

**Core invariants (4 axioms):**

```
AX-ORACLE-MONITOR-019: ∀monitor M, ∀program P:
  overhead(M, P) ≤ ε for fixed, known ε; M's overhead is O(1) per event

AX-ORACLE-MONITOR-020: ∀spec φ, ∀trace σ:
  online_monitor detects violation at min prefix p where σ ⊭ φ
  offline_monitor checks σ after execution completes

AX-ORACLE-MONITOR-021: ∀monitor M, ∀system S:
  M_unavailable → S is blocked (fail-closed)

AX-ORACLE-MONITOR-022: ∀property P:
  ∃spec_language L: L is adequate for P
  safety → state machines; temporal → LTL; data → first-order
```

And cross-cutting with Leveson:
```
AX-ORACLE-MONITOR-040: ∀monitor M, ∀system S:
  M is independent of S; M's failure does not propagate to S
```

### Key principles
- **Bounded overhead:** Monitoring must be O(1) per event. Unbounded overhead is itself a reliability risk.
- **Online vs offline:** Online catches violations immediately (safety enforcement). Offline analyzes completed traces (grind pipeline).
- **Fail closed:** Monitor unavailable = system blocked. Never allow unchecked execution.
- **Specification language adequacy:** State machines for safety, LTL for temporal, first-order for data-dependent.
- **Monitor isolation:** Monitor must be independent of the monitored system.

### orbit relevance
- Every runtime check (circuit breaker, token router, sandbox) must be O(1).
- Online monitoring: circuit breaker, token router, sandbox.
- Offline monitoring: grind pipeline, axiom-ingestor.
- All safety-critical monitors fail closed.
- invariants.md specifies the appropriate language per package.

---

## 8. Prometheus / OpenMetrics

### Metric Design and Instrumentation

The de facto standard for metrics in the cloud-native ecosystem. Defines metric types (counter, gauge, histogram, summary), naming conventions, label cardinality constraints, and query patterns.

**Core invariants (6 axioms):**

```
AX-ORACLE-MONITOR-013: ∀counter c, ∀t1 < t2:
  c(t2) ≥ c(t1) except across restarts
  rate(c[window]) = (c(t_now) - c(t_now - window)) / window

AX-ORACLE-MONITOR-014: ∀gauge g:
  g(t) ∈ ℝ is a snapshot; ¬monotonic(g); rate(g) is undefined

AX-ORACLE-MONITOR-015: ∀histogram h:
  h has buckets b_1,...,b_n
  p99 ≈ histogram_quantile(0.99, rate(h_bucket[5m]))

AX-ORACLE-MONITOR-023: ∀metric m, ∀action a that should trigger m:
  m(t_before) < m(t_after); delta > 0 proves m is wired

AX-ORACLE-MONITOR-024: ∀metric m:
  name(m) = namespace_subsystem_name_unit
  counter → _total suffix; histogram → _bucket/_count/_sum

AX-ORACLE-MONITOR-034: ∀metric m, ∀label L of m:
  |values(L)| ≤ K for small, fixed K; cardinality does not grow with traffic
```

### Key principles
- **Counter:** Monotonically increasing (except restarts). Use for cumulative event counts. rate() computes per-second average.
- **Gauge:** Can go up and down. Use for current state. Never call rate() on a gauge.
- **Histogram:** Distribution with configurable buckets. Use for latency. histogram_quantile() computes percentiles.
- **Metric movement proof:** Before → action → after, delta > 0. A counter that doesn't move isn't wired.
- **Naming convention:** namespace_subsystem_name_unit. _total for counters, _bucket/_count/_sum for histograms.
- **Bounded label cardinality:** No user IDs, request IDs, or URL paths as labels.

### orbit relevance
- All event counts must be counters, not gauges.
- All latency measurements must be histograms.
- All metric names must follow naming convention.
- Every metric must have a TestAX movement proof.
- Label cardinality must be bounded.

---

## Tensor Equation Registry

| ID | Equation (abbreviated) | Source |
|----|------------------------|--------|
| MONITOR-001 | inv_C holds at entry/exit of every public method | Meyer 1997 |
| MONITOR-002 | precondition violation = caller bug, postcondition = callee bug | Meyer 1997 |
| MONITOR-003 | ∀reachable_state s: I(s) holds (safety) | Lamport 1977 |
| MONITOR-004 | ∀fair_execution e: ◇P(e) (liveness) | Lamport 1977 |
| MONITOR-005 | P = S_P ∩ L_P (decomposition theorem) | Alpern & Schneider 1985 |
| MONITOR-006 | safety = runtime-enforceable by prefix rejection | Alpern & Schneider 1985 |
| MONITOR-007 | liveness = not finite-prefix enforceable | Alpern & Schneider 1985 |
| MONITOR-008 | safety constraints monitored at runtime, fail closed | Leveson |
| MONITOR-009 | leading indicators precede hazards | Leveson |
| MONITOR-010 | four golden signals: latency, traffic, errors, saturation | Google SRE 2016 |
| MONITOR-011 | alert on symptoms (user-visible), not causes | Google SRE 2016 |
| MONITOR-012 | burn rate > 14.4 → page; > 2 → ticket | Google SRE 2016 |
| MONITOR-013 | counter monotonic; rate() gives per-second average | Prometheus |
| MONITOR-014 | gauge non-monotonic; rate() on gauge = undefined | Prometheus |
| MONITOR-015 | histogram for distributions; histogram_quantile for percentiles | Prometheus |
| MONITOR-016 | monitor soundness: M(σ,φ)=violation → σ⊭φ | Havelund & Rosu 2001 |
| MONITOR-017 | monitor completeness: σ⊭φ → M detects at earliest prefix | Havelund & Rosu 2001 |
| MONITOR-018 | past-time LTL online-monitorable; future-time needs lookahead | Havelund & Rosu 2001 |
| MONITOR-019 | monitoring overhead O(1) per event | Bartocci et al. 2018 |
| MONITOR-020 | online detects at min prefix; offline checks full trace | Bartocci et al. 2018 |
| MONITOR-021 | monitor fail-closed; unavailable → system blocked | Bartocci et al. 2018 |
| MONITOR-022 | spec language must match property type | Bartocci et al. 2018 |
| MONITOR-023 | metric movement proof: before → action → after, delta > 0 | Prometheus/orbit |
| MONITOR-024 | namespace_subsystem_name_unit naming convention | Prometheus |
| MONITOR-025 | program points annotated with assertions | Lamport 1977 |
| MONITOR-026 | mutual exclusion = safety; starvation-freedom = liveness | Lamport 1977 |
| MONITOR-027 | saturation = max(resource utilization/capacity) | Google SRE 2016 |
| MONITOR-028 | latency as histogram p50/p95/p99, not mean | Google SRE 2016 |
| MONITOR-029 | error rate = explicit + implicit failures | Google SRE 2016 |
| MONITOR-030 | invariant holds at entry/exit, may break during body | Meyer 1997 |
| MONITOR-031 | subclass weakens precondition, strengthens postcondition | Meyer 1997 |
| MONITOR-032 | hazard analysis before code; safety constraints as tensor equations | Leveson |
| MONITOR-033 | control loop: monitor → compare → correct, controller independent | Leveson |
| MONITOR-034 | label cardinality bounded, does not grow with traffic | Prometheus |
| MONITOR-035 | failure mode enumeration complete with detection + mitigation | Leveson |
| MONITOR-036 | assertion failure → halt; no recovery from broken invariant | Meyer 1997 |
| MONITOR-037 | alert thresholds derived from SLOs, not intuition | Google SRE 2016 |
| MONITOR-038 | no alert without metric; no metric without consumer | Google SRE 2016 |
| MONITOR-039 | RED method: Rate, Errors, Duration per endpoint | Google SRE/Wilkie |
| MONITOR-040 | monitor independent of monitored system; failure isolated | Bartocci/Leveson |

---

## Gap Analysis — orbit Coverage

Current orbit state vs these invariants:

| Invariant | orbit Status |
|-----------|-------------|
| MONITOR-001 (class invariants) | PARTIAL — invariants.md exists, but not runtime-checked at every package boundary |
| MONITOR-003 (safety) | COVERED — TestAX gates, -race, runtime assertions |
| MONITOR-004 (liveness) | GAP — no systematic liveness monitoring with timeout-based detection |
| MONITOR-008 (fail closed) | COVERED — CB, TR, sandbox all fail closed |
| MONITOR-010 (four golden signals) | GAP — dispatch reports HTTP status but lacks latency histograms, saturation |
| MONITOR-013 (counter monotonic) | GAP — no programmatic verification of counter monotonicity |
| MONITOR-015 (histogram latency) | GAP — no latency histograms in any package |
| MONITOR-019 (O(1) overhead) | PARTIAL — designed O(1), not verified by benchmark |
| MONITOR-023 (metric movement proof) | GAP — no systematic movement proofs for existing metrics |
| MONITOR-028 (latency distribution) | GAP — no p50/p95/p99 exported anywhere |
| MONITOR-035 (failure mode analysis) | GAP — no failure mode documentation per package |
| MONITOR-038 (no dead metrics) | GAP — no audit of metric consumers |
| MONITOR-039 (RED method) | GAP — no per-endpoint RED metrics |

**Priority actions:**
1. Add latency histograms to dispatch (MONITOR-015, MONITOR-028)
2. Add liveness monitoring with timeouts (MONITOR-004)
3. Add metric movement proofs (MONITOR-023)
4. Add failure mode analysis per package (MONITOR-035)
5. Audit metric consumers (MONITOR-038)
