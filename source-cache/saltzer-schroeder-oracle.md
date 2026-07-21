# Saltzer & Schroeder Oracle (1975)

Source: "The Protection of Information in Computer Systems" (Saltzer & Schroeder, Proc. IEEE, Sep 1975, pp. 1278-1308).
DOI: 10.1109/PROC.1975.9939

This is the foundational security-design paper. These 8 principles are invariants.
Every principle maps to a first-order-logic expression, a Go enforcement pattern, and
specific orbit packages that must satisfy it.

---

## 1. Economy of Mechanism

**Principle:** Keep the design as simple and small as possible. Every line of code is
a potential bug; every state is a potential inconsistency.

**Invariant:**
```
∀component: minimize(|interfaces| + |states| + |code_paths|)
→ simpler design ⇒ fewer bugs ⇒ smaller attack surface
```

**Go enforcement pattern:**
- Single-responsibility structs, no deep embedding
- Small interfaces (1-3 methods ideal)
- State machine exhaustiveness: every (state, event) pair has one well-defined transition
- Avoid init() side effects; explicit constructors over implicit state

**orbit packages affected:**
- `pkg/circuitbreaker` — 3-state machine (Closed, Open, HalfOpen), 5 transitions, clean.
  AX-001 through AX-010 are exhaustive. Good example of mechanism economy.
- `pkg/luaengine` — RunRule is a single function, 5 whitelisted libraries, no global
  state. AX-018, AX-019. Clean mechanism economy.
- `pkg/sandbox` — One struct (Sandbox), 4 public methods, 1 private (resolve). AX-011
  through AX-017. Clean.
- `pkg/congestion` — VM is 4 opcodes away from a full interpreter. The parser,
  compiler, and VM are all in one file. Still simple for what it does.

**Violation risk:** Adding a new state to circuitbreaker without updating all 5
switch statements. Any new package with >5 public methods deserves scrutiny.

---

## 2. Fail-Safe Defaults

**Principle:** Base access decisions on permission rather than exclusion. The default
is denial. A mistake in the access-check logic should result in denied access, not
granted access.

**Invariant:**
```
∀access_request: default_decision = "deny"
∀access_granted: explicit_check(access_request) = true
```

**Go enforcement pattern:**
- Boolean flags default to false (zero value) meaning "not allowed"
- Mutex default: unlocked = no access until Lock() succeeds
- Context cancellation: ctx.Err() != nil means "stop" (fail-safe)
- Select statement default case: return error, not success
- Slice/channel zero value: nil = empty, operations return zero-value, not panic

**orbit packages affected:**
- `pkg/circuitbreaker` — Open state blocks traffic (Allow() returns false). Default
  state after construction is Closed (operational), but after threshold failures,
  defaults to blocking. AX-001.
- `pkg/tokenrouter` — Cooldown blocks key acquisition (unavailable() returns true).
  Closed router returns ErrNoKeysAvailable. Acquire defaults to no key until one
  passes all checks. IsProbing defaults to false (not probing), but when set to true,
  blocks acquisition — fail-safe.
- `pkg/sandbox` — resolve() rejects paths that escape root (rel starts with "..").
  Empty path returns error. Non-existent worktree returns error. AX-012, AX-013,
  AX-017.
- `pkg/dispatch` — post() treats non-2xx status codes as errors. ctx cancellation
  stops processing and returns ctx.Err(). AX-024.
- `pkg/providerrouter` — Next() when all providers are in backoff returns the
  soonest-to-expire one (not random). New() rejects empty provider list
  (ErrNoProviders), duplicate names, missing env vars. Default backoff is active
  (1s initial, 60s max).

**Violation risk:** Adding a "trusted" path that bypasses sandbox.resolve().
Adding a "fast path" in tokenrouter that skips cooldown check. Any code path that
returns success without explicit validation.

---

## 3. Complete Mediation

**Principle:** Every access to every object must be checked for authority. No caching
of authorization decisions. A cached permission is a stale permission.

**Invariant:**
```
∀access,∀subject,∀object,∀time:
  check(subject, object, operation, time) on every access
  ∧ ¬∃cached_result: access granted based on prior check
```

**Go enforcement pattern:**
- No cached auth tokens in struct fields; re-check every call
- Mutex.Lock() on every state read/write — no "I know it's safe" assumptions
- Every function validates its preconditions at entry, not at construction
- Time-based expiry checked on every call, not lazily

**orbit packages affected:**
- `pkg/sandbox` — resolve() checks path containment on every call. Every WriteFile,
  ReadFile, Shell goes through resolve(). No cached "this path is safe" flag.
  AX-011, AX-017.
- `pkg/tokenrouter` — acquireLoop() checks cooldown, NextAt pacing, RPM limit,
  and IsProbing on every Acquire call. No cached "this key is healthy" flag.
  Cooldown expiry is checked by comparing timestamp to now on every call.
- `pkg/circuitbreaker` — Allow() checks state and timeout on every call, even
  though IsAvailable() already checked during Pick(). No cached "this backend is
  available" flag. Pick() uses IsAvailable() for filtering; Call() uses Allow()
  for the actual transition. AX-004.
- `pkg/providerrouter` — Next() re-checks backoff expiry on every call (nowNS
  compared to untilNS). InBackoff() re-checks on every call. No cached "provider
  X is healthy" flag.

**Violation risk:** Adding a "trusted" path that skips resolve() in sandbox. Adding
a "fast acquire" that skips cooldown check. Any middleware that caches auth results.

---

## 4. Open Design

**Principle:** Security should not depend on the design being secret. The mechanism
should be secure even if the attacker knows exactly how it works. (This is Kerckhoffs's
principle, restated.)

**Invariant:**
```
∀mechanism:
  security(mechanism, attacker_with_full_knowledge) =
  security(mechanism, attacker_with_zero_knowledge)
```

**Go enforcement pattern:**
- No hardcoded secrets in source code
- API keys, tokens, passwords from env vars or config files (not compiled in)
- Open-source codebase; security comes from the algorithm, not its secrecy
- Cryptographic keys are the only secrets; algorithms are public

**orbit packages affected:**
- `pkg/providerrouter` — API keys resolved from env vars ($ENV_VAR), never
  hardcoded. resolveAPIKey() enforces that env vars are set and non-empty.
  Config is loaded from JSON files, not embedded.
- `pkg/tokenrouter` — Keys passed to NewRouter() as a []string parameter. The
  router holds tokens in memory but never persists them. No hardcoded keys.
- `pkg/transport` — TLS config with MinVersion=TLS12, no hardcoded certs.
- `pkg/config` — Limits are constants (public), not secrets. MaxOutputTokens,
  ReviewerConcurrencyStandard are operational parameters, not security secrets.

**Violation risk:** Any hardcoded API key, token, or password in source. Any
"secret algorithm" that isn't cryptographically sound. Any env var that defaults
to a hardcoded value if unset (currently no such defaults — good).

---

## 5. Separation of Privilege

**Principle:** Where feasible, a protection mechanism should require two (or more)
keys to unlock it. No single compromised credential should grant access.

**Invariant:**
```
∀critical_operation:
  requires(operation, approval_from at least 2 independent authorities)
```

**Go enforcement pattern:**
- Multi-factor checks: separate conditions that must both pass
- Dual-signature patterns: two independent validations
- Separate read and write capabilities
- No single point of authorization failure

**orbit packages affected:**
- `pkg/tokenrouter` — **GAP IDENTIFIED:** Single-key acquisition. One goroutine
  acquires one key and dispatches. No dual-key mechanism. The invariants.md file
  explicitly identifies this: "Tokenrouter is missing fencing tokens." After
  cooldown expiry, a key can be re-acquired by goroutine B while goroutine A
  still holds a reference. No fencing token to reject stale holders.
  Remediation: `acquire(key) ⇒ token++`, dispatch checks token.
- `pkg/dispatch` — Requires both key acquisition AND valid context. Two independent
  conditions: (1) Acquire must succeed, (2) ctx must not be cancelled. This is
  weak separation (both are internal to the same process).
- `pkg/scheduler` — DistLock + job scheduling are separate concerns. A job must
  both be scheduled (by the scheduler) AND acquire the distributed lock (by
  DistLock.TryAcquire). Two independent authorities. This is a good example.
- `pkg/circuitbreaker` — Pick() requires both healthy AND circuit not open.
  Two independent conditions. AX-009.

**Violation risk:** Tokenrouter's missing fencing token is the primary gap. Any
single check that gates a critical operation should be paired with a second,
independent check.

---

## 6. Least Privilege

**Principle:** Every program and every user of the system should operate using the
least set of privileges necessary to complete the job. Permissions are granted
narrowly and revoked when no longer needed.

**Invariant:**
```
∀process,∀task:
  permissions(process) = min(permissions needed to complete task)
  ∧ permissions revoked when task complete
```

**Go enforcement pattern:**
- Per-goroutine caps (semaphores, rate limits)
- Scoped contexts with timeouts and cancellation
- Minimal interfaces: pass only the methods needed, not the whole struct
- Defer-based cleanup: release resources, close connections
- Sandbox construction: start with nothing, add only what's needed

**orbit packages affected:**
- `pkg/luaengine` — SkipOpenLibs=true, only base/table/string/math/coroutine
  loaded. No os.execute, io.open, os.getenv, os.exit. AX-018. Each RunRule call
  gets a fresh L state (AX-019). This is the strongest example of least privilege
  in the codebase.
- `pkg/sandbox` — All file operations confined to worktree root. resolve() blocks
  path traversal. Shell runs with CWD=sandbox root. AX-011, AX-016, AX-017.
- `pkg/dispatch` — Concurrency semaphore caps in-flight HTTP requests per
  Dispatcher. ctx governs both key acquisition and HTTP request lifetime.
  AX-023.
- `pkg/config` — MaxConcurrentBuilds=4 (prevents OOM), CompileMemLimitMiB=1800
  (per-process memory cap), WASMCompileMemLimitMiB=2000.
- `pkg/tokenrouter` — MaxConcurrentAcquires caps in-flight Acquire calls.
  RPMLimit=290 (safe margin below 300 RPM cap). MinInterval=207ms (per-key
  pacing). Each key gets its own Cooldown.

**Violation risk:** Removing the SkipOpenLibs flag in luaengine. Removing the path
containment check in sandbox. Increasing MaxConcurrentBuilds without testing for
OOM. Any "admin mode" that bypasses normal permission checks.

---

## 7. Least Common Mechanism

**Principle:** Minimize the amount of mechanism common to more than one user and
depended on by all users. Every shared mechanism is a potential covert channel
and a potential single point of failure.

**Invariant:**
```
∀domain₁,∀domain₂:
  shared_state(domain₁, domain₂) = ∅
  (no observable state common to two security domains)
```

**Go enforcement pattern:**
- Per-key/per-user state, not global mutable state
- Lock-free data structures where possible (CAS-based)
- Isolated goroutines communicating via channels (no shared memory)
- Fresh instances per invocation (no singleton state leakage)
- sync.Pool or constructor-based allocation (no package-level globals)

**orbit packages affected:**
- `pkg/luaengine` — Fresh L state per RunRule call. AX-019: "RunRule(script₁)
  does not leak globals into RunRule(script₂)." Defer L.Close() ensures cleanup.
  This is textbook least common mechanism.
- `pkg/sandbox` — Each Sandbox instance has its own root directory. Two sandboxes
  cannot observe each other's state. No global sandbox registry.
- `pkg/tokenrouter` — Per-key CAS-based sliding window buckets. KeyState structs
  are independent. No cross-key state leakage. Lazy expiry uses atomic CAS on
  BucketTime. AX-017: "lazy expiry correctness."
- `pkg/circuitbreaker` — Each backend has its own CircuitBreaker. No shared state
  between backends. WeightedRR.Pick() iterates backends independently.
- `pkg/scheduler` — MemDistLock has per-key locks. Each job has its own JobInfo.
  No shared state between jobs except the priority queue (which is the scheduler's
  job, not a covert channel).
- `pkg/providerrouter` — Per-provider state (providerState). No shared state
  between providers. Backoff is per-provider.

**Violation risk:** Adding a global cache shared across all sandboxes. Adding a
shared rate-limiter that all tokenrouter keys draw from. Any package-level
mutable variable that multiple goroutines read/write without synchronization.

---

## 8. Psychological Acceptability

**Principle:** The human interface must be easy to use so that users routinely and
automatically apply the protection mechanisms correctly. If the security mechanism
is harder to use correctly than to bypass, users will bypass it.

**Invariant:**
```
∀user,∀mechanism:
  effort(use_correctly) << effort(bypass)
  ∧ correct_use is the path of least resistance
```

**Go enforcement pattern:**
- Clear, actionable error messages (not "something went wrong")
- Sensible defaults that are also secure
- No surprises: zero values mean safe defaults
- Single-call APIs: one function call to do the right thing
- Explicit names: Allow() vs IsAvailable() — the name tells you what it does

**orbit packages affected:**
- `pkg/circuitbreaker` — IsAvailable() is read-only, Allow() is the mutating
  check. The naming makes the distinction clear. 3-state machine is intuitive
  (Closed, Open, HalfOpen). Timeout-based automatic recovery — no manual
  intervention needed.
- `pkg/tokenrouter` — Acquire() is a single blocking call that handles all
  the complexity (cooldown, pacing, RPM limits, probing). The caller doesn't
  need to know about the internal state machine. Clear error: ErrNoKeysAvailable.
- `pkg/transport` — Client() is a single call returning a pre-configured
  http.Client with sensible defaults (TLS 1.2+, connection pooling, timeouts).
- `pkg/sandbox` — WriteFile is atomic (temp file + rename). AX-014. ReadFile
  returns what was written. AX-015. Shell has a default 30s timeout. These
  defaults make correct use easy.
- `pkg/dispatch` — Run() accepts a slice of Tasks and returns a slice of Results
  in order. AX-026. The caller doesn't manage concurrency, retries, or key
  rotation. dispatch handles all of it internally.
- `pkg/providerrouter` — Next() is a simple call. MarkRateLimited/MarkSuccess
  are obvious. The exponential backoff is automatic. The caller just reports
  what happened.

**Violation risk:** Any API that requires the caller to remember a multi-step
sequence to use correctly. Any error message that says "error" without saying
what went wrong or how to fix it. Any boolean flag whose meaning is unclear
from the name.

---

## Two Additional Principles (from the paper, "apply only imperfectly")

### 9. Work Factor

**Principle:** The cost of circumventing a mechanism should be compared with the
resources of a potential attacker. The mechanism doesn't need to be perfect; it
needs to be more expensive to break than the value of what it protects.

**Invariant:**
```
∀mechanism,∀attacker:
  cost(bypass(mechanism, attacker)) > value(protected_asset)
```

**orbit:** tokenrouter cooldown (60s + jitter) raises the cost of key exhaustion.
Exponential backoff in providerrouter raises the cost of sustained 429 attacks.
Not formally modeled.

### 10. Compromise Recording

**Principle:** Sometimes it's more practical to reliably record that a compromise
has occurred than to prevent it entirely. Audit trails, logs, and tamper-evident
records can substitute for prevention.

**Invariant:**
```
∀compromise: ∃tamper_evident_record(compromise)
```

**orbit:** tokenrouter's RecordKeyUsage, RecordUsage, and PerKeyStats provide
observability. circuitbreaker's RecordFailure/RecordSuccess track state transitions.
workpack's WriteCheckpoint writes atomic (temp+rename) checkpoint records.
dispatch's reportFinal ensures every request outcome is recorded. Not formally
modeled as a security property.

---

## STRIDE Threat Model

STRIDE is a threat categorization framework (Microsoft, Kohnfelder & Garg, 1999).
Each category threatens a specific security property — a specific invariant.

### S — Spoofing Identity

**Threat:** Attacker impersonates a user, device, or service to bypass authentication.

**Invariant threatened:**
```
∀principal: identity(principal) is verifiable
∧ ∀action: the claimed principal is the actual principal
```

**orbit surface:**
- `pkg/dispatch` — Bearer token in Authorization header. If the token is
  compromised, the attacker can impersonate a legitimate API key. No mutual TLS.
- `pkg/providerrouter` — API keys from env vars. If the env is compromised, all
  providers are impersonatable.
- `pkg/tokenrouter` — No authentication of the caller. Any goroutine that holds
  a reference to the Router can call Acquire(). This is by design (internal
  package), but worth noting.
- `pkg/httpserver` — No authentication at all. No TLS. This is a scratch/learning
  HTTP server, but it accepts any connection.

### T — Tampering with Data

**Threat:** Unauthorized modification of data, code, or configuration in transit,
at rest, or in a build pipeline.

**Invariant threatened:**
```
∀data: integrity(data) = true
∧ ∀modification: authorized(modifier, data) = true
```

**orbit surface:**
- `pkg/sandbox` — WriteFile is atomic (temp file + rename), preventing partial
  writes. AX-014. But no checksumming or signing of written files.
- `pkg/transport` — TLS 1.2+ protects data in transit (via HTTPS). No certificate
  pinning.
- `pkg/dispatch` — JSON payloads are marshaled and sent over HTTPS. No
  request signing. The upstream could tamper with the response.
- `pkg/workpack` — WriteCheckpoint uses temp file + rename (atomic), but no
  checksum or signature. A compromised process could write fake checkpoints.

### R — Repudiation

**Threat:** A user or attacker performs an action and later denies it because the
system cannot prove otherwise.

**Invariant threatened:**
```
∀action: ∃non_repudiable_evidence(action)
∧ ∀evidence: verifiable(evidence, action) = true
```

**orbit surface:**
- `pkg/tokenrouter` — RecordKeyUsage, PerKeyStats provide per-key metrics but
  not cryptographic proof of who sent what. No signing.
- `pkg/dispatch` — dispatch() records every outcome via reportFinal(). But no
  cryptographic audit trail. Logs can be deleted.
- `pkg/workpack` — WriteCheckpoint records step completion with timestamps.
  Evidence field can contain git diff output. But no cryptographic signature.
- `pkg/scheduler` — JobInfo records Runs, Last, Errors. But no persistent,
  tamper-evident audit log.
- **No orbit package implements non-repudiation.** This is a known gap. Logs
  are textual and mutable.

### I — Information Disclosure

**Threat:** Sensitive data is exposed to unauthorized parties.

**Invariant threatened:**
```
∀secret: accessible(secret) = authorized_readers_only
∧ ∀disclosure: authorized(reader, secret) = true
```

**orbit surface:**
- `pkg/tokenrouter` — KeyState.Token holds raw API keys in memory. PerKeyStats()
  exposes key IDs but not tokens. However, if a debugger or memory dump captures
  the process, tokens are in plaintext. No in-memory encryption.
- `pkg/providerrouter` — API keys are resolved from env vars and stored in
  providerState.cfg.APIKey. Providers() returns them (snapshot). Snapshot()
  does NOT include the APIKey field in Stats — good.
- `pkg/luaengine` — Input JSON payload is injected as a global Lua variable.
  A malicious script could leak it via the return value or error message.
  Currently only 'passed' and 'reason' are extracted — but the script could
  embed the payload in 'reason'. AX-021 validates injection but not exfiltration.
- `pkg/dispatch` — HTTP requests are sent over HTTPS (if endpoint is HTTPS).
  Responses are decoded and stored in Result.Response. No redaction of sensitive
  content in responses.
- `pkg/httpserver` — No TLS. All traffic is plaintext. This is a scratch server
  but worth noting for completeness.

### D — Denial of Service

**Threat:** System availability is disrupted by exhausting resources or crashing
services.

**Invariant threatened:**
```
∀service,∀legitimate_user:
  available(service, legitimate_user) = true
```

**orbit surface:**
- `pkg/circuitbreaker` — Directly defends against cascading failures. Open state
  blocks traffic to failing backends. AX-001. HalfOpen probe prevents thundering
  herd. AX-015. WeightedRR.Pick() returns nil when all backends unavailable.
  AX-009. This is the primary DoS defense.
- `pkg/tokenrouter` — Cooldown on 429/5xx prevents hammering a rate-limited
  provider. MinInterval (207ms) paces requests. RPMLimit (290) caps per-key
  send rate. MaxConcurrentAcquires caps in-flight Acquire calls. IsProbing
  acts as a single-flight semaphore during cooldown recovery. Jittered waits
  prevent thundering herds. nextPacedWait() handles all-backoff and all-at-RPM-limit
  cases with jittered waits.
- `pkg/providerrouter` — Exponential backoff on 429. MaxBackoff=60s cap.
  NextAvailable() blocks until a provider is available.
- `pkg/dispatch` — Concurrency semaphore (max d.concurrency goroutines).
  AX-023. Max 3 attempts per task. AX-025. ctx cancellation stops processing.
  AX-024.
- `pkg/config` — MaxConcurrentBuilds=4 prevents OOM. CompileMemLimitMiB=1800
  per-process. BuildValidationTimeout=90s, WASMRunTimeout=30s,
  WASMCompileTimeout=60s. All are DoS defenses.
- `pkg/congestion` — VM stack overflow → error, not panic. AX-044. Division
  by zero → error, not panic. AX-041. Stack cap at 65536. Stack grows
  dynamically (append). These prevent VM-based DoS.
- `pkg/scheduler` — MemDistLock prevents duplicate job execution. Timeout on
  job execution. Panic recovery with retries. DistLock TTL prevents stale locks.

### E — Elevation of Privilege

**Threat:** An attacker gains higher privileges than intended, bypassing
authorization checks.

**Invariant threatened:**
```
∀principal: hasOnly(principal, explicitly_granted_permissions)
∧ ∀privilege_escalation: ¬∃path_to_higher_privilege
```

**orbit surface:**
- `pkg/sandbox` — Path traversal prevention. AX-017: resolve("../../../etc/passwd")
  returns error. AX-011: resolved path must be within root. This is the primary
  privilege escalation defense. Without it, an attacker could write/read files
  outside the sandbox.
- `pkg/luaengine` — Library whitelist. AX-018: no os.execute, io.open, etc.
  Without this, a Lua script could execute arbitrary shell commands (full EoP).
  This is the strongest EoP defense in the codebase.
- `pkg/providerrouter` — API keys from env vars, not hardcoded. Configuration
  from JSON files, not embedded. This prevents configuration-based EoP (attacker
  modifies code to use their own keys).
- `pkg/congestion` — VM is stack-based with bounds checking. Stack overflow
  returns error, not panic. No native code execution. The VM cannot escape its
  sandbox to execute arbitrary machine code.
- **Gap:** No orbit package implements formal authorization levels (e.g., admin
  vs. user). The codebase assumes all callers are trusted. This is acceptable
  for a single-user CLI tool but would be a critical gap in a multi-tenant
  server.

---

## Cross-Reference: Principles × orbit Packages

| Package | Economy | Fail-Safe | Complete Mediation | Open Design | Sep. of Privilege | Least Privilege | Least Common Mech | Psych. Accept. |
|---------|---------|-----------|-------------------|-------------|-------------------|-----------------|-------------------|----------------|
| circuitbreaker | AX-001..010 | AX-001 | AX-004 | N/A | AX-009 (dual condition) | CB per-backend | Per-backend CB | Clean state names |
| tokenrouter | Lock-free CAS | Cooldown, closed | Per-call checks | Keys from caller | **GAP: no fencing token** | RPM cap, pacing | Per-key state | Single Acquire() |
| sandbox | 4 public methods | resolve() denies | Every op via resolve | N/A | N/A | Worktree confinement | Per-sandbox root | Atomic writes |
| luaengine | Single func | SkipOpenLibs | Fresh L per call | N/A | N/A | **Strongest example** | Fresh L per call | Single RunRule call |
| dispatch | Clear cycle | 4xx/5xx = error | Per-attempt acquire | Bearer token | Key+ctx (weak) | Concurrency semaphore | Per-dispatcher sem | Run() returns ordered |
| providerrouter | Round-robin | Default backoff | Per-call backoff check | Env vars for keys | N/A | Per-provider backoff | Per-provider state | Next()/MarkSuccess |
| congestion | One-file VM | Divide by zero→err | Per-instruction check | Open-source VM | N/A | Stack bounds | Per-VM stack | Compile()→Run() |
| scheduler | Heap-based | DistLock blocks | Per-fire lock check | N/A | DistLock+schedule | Timeout, retries | Per-job state | Add/Remove API |
| transport | Single Client() | TLS 1.2+ min | Per-connection TLS | No hardcoded certs | N/A | Conn pool limits | sync.Once singleton | One call |
| config | Constants only | Conservative defaults | Compile-time | Public constants | N/A | Low build caps | N/A | Single source of truth |

---

## Key Gaps Identified

1. **tokenrouter: missing fencing token** (Separation of Privilege) — documented in
   tokenrouter/invariants.md. A stale key holder can dispatch after cooldown expiry
   while a new holder has already re-acquired the key. No fencing token to reject
   stale holders.

2. **No non-repudiation anywhere** (Repudiation) — logs are textual and mutable.
   No cryptographic signatures on checkpoints, dispatch results, or key usage records.

3. **No formal authorization levels** (Elevation of Privilege) — all callers are
   trusted. Acceptable for single-user CLI, gap for multi-tenant server.

4. **luaengine: no payload exfiltration guard** (Information Disclosure) — a script
   could embed the input payload in the 'reason' string. AX-021 validates injection
   but not exfiltration.

5. **dispatch: no response integrity check** (Tampering) — the upstream could
   tamper with responses. No request signing or response verification.

6. **httpserver: no authentication, no TLS** (Spoofing, Information Disclosure) —
   this is a scratch/learning server, not a production component, but the gap
   exists.