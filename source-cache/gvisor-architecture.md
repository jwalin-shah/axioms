# oracle/gvisor-architecture -- Full architecture: Sentry, Gofer, Netstack, Platform abstraction
Source: https://gvisor.dev/docs/architecture_guide/ (intro, security, resources, platforms, performance, networking)
Date pulled: 2026-07-21

## Extracted Invariants

### INV-GVR-001: No syscall passthrough
**Core Invariant:**
```
∀ syscall s issued by sandboxed application A:
  s is intercepted by the Sentry, handled entirely within Sentry code,
  and does NOT result in a host syscall of the same type being issued with A's arguments.
```
**Source:** Intro page, "How does gVisor provide isolation?" and Security Model, Principle #1.
**Counterexample:** If `ioctl(2)` or `ptrace(2)` were passed through directly, a single host kernel vulnerability in those syscalls would provide full escape. The invariant prevents the sandboxed application from directly touching host kernel attack surface.
**Why this matters for bridge/orbit:** Bridge and orbit both execute untrusted code in sandboxes. If any syscall is passed through, the sandbox boundary is not a boundary at all -- it is an advisory filter. This invariant must hold for bridge's code execution sandbox and orbit's session isolation.

### INV-GVR-002: Sentry host syscall surface is exhaustively enumerated and minimized
**Core Invariant:**
```
∀ host syscall h that the Sentry may issue:
  h ∈ explicitly_allowlisted_set ∧
  h ∉ {open(2), socket(2), connect(2), exec(2), accept(2), ...}
```
**Source:** Security Model, "Goals: Limiting Exposure" -- "The Sentry itself operates within an empty mount namespace" and "The sandbox is not permitted to open new files, create new sockets." Principle #3: "The host surface exposed to the Sentry is minimized."
**Counterexample:** If the Sentry could `exec(2)`, a compromised Sentry could spawn arbitrary host binaries. If it could `connect(2)`, it could exfiltrate data. The allowlist is a non-negotiable second line of defense.
**Why this matters for bridge/orbit:** Bridge's sandboxed execution environment must similarly have an enumerated and minimized host syscall surface. Any un-enumerated syscall is a potential escape vector.

### INV-GVR-003: Privilege drop before untrusted code execution
**Core Invariant:**
```
∀ sandbox lifecycle:
  setup phases may use elevated privileges,
  but before_any_untrusted_code_runs => privileges_dropped ∧ user_namespace_isolated
```
**Source:** Intro page, "How can I test gVisor?" -- "Once the sandbox setup is complete, gVisor re-executes itself and drops all privileges in the process. This takes place before any untrusted code runs."
**Counterexample:** If privilege drop happens after application code starts, a malicious workload could race the drop and execute privileged operations. Time-of-check-time-of-use on privilege state.
**Why this matters for bridge/orbit:** Bridge's sandbox initialization must guarantee privilege drop completes before any user-provided code executes. This is a temporal ordering invariant.

### INV-GVR-004: Unsafe code isolation in Go
**Core Invariant:**
```
∀ Go source file f in the Sentry:
  f uses package "unsafe" ⟹ f.ends_with("unsafe.go") ∧
  f does NOT use package "unsafe" ⟹ f does NOT end with "unsafe.go"
```
**Source:** Security Model, "Principles: Defense-in-Depth" -- "All unsafe code is isolated in files that end with 'unsafe.go', in order to facilitate validation and auditing. No file without the unsafe suffix may import the unsafe package."
**Counterexample:** If unsafe code were scattered across the codebase, auditing would be infeasible. A single missed `unsafe.Pointer` conversion could introduce a memory corruption vulnerability exploitable from within the sandbox.
**Why this matters for bridge/orbit:** Bridge is also Go. The same discipline -- isolate all `unsafe` usage in `*unsafe.go` files -- makes adversarial security review tractable. Orbit should adopt this if it doesn't already.

### INV-GVR-005: No CGo in Sentry
**Core Invariant:**
```
∀ Go packages in the Sentry core:
  import "C" is forbidden ∧ CGo is disabled
```
**Source:** Security Model, "Principles: Defense-in-Depth" -- "No CGo is allowed. The Sentry must be a pure Go binary."
**Counterexample:** CGo introduces a C ABI boundary within the Go runtime. A C buffer overflow in cgo-linked code would bypass Go's memory safety guarantees and could provide a sandbox escape path.
**Why this matters for bridge/orbit:** Any CGo usage in bridge's sandbox layer reintroduces the memory-unsafety class that gVisor deliberately eliminates. Must be statically enforced.

### INV-GVR-006: External import control in Sentry core
**Core Invariant:**
```
∀ Go package p in Sentry core packages:
  p.imports ∩ external_dependencies = ∅
```
**Source:** Security Model, "Principles: Defense-in-Depth" -- "External imports are not generally allowed within the core packages. Only limited external imports are used within the setup code."
**Counterexample:** An unvetted external dependency with a vulnerability (e.g., an HTTP parser with a buffer overflow) would expand the attack surface to include the dependency's code.
**Why this matters for bridge/orbit:** Bridge's knowledge package and sandbox layer should apply the same discipline. External dependency audit is proportional to attack surface.

### INV-GVR-007: Single memfd backing all application memory
**Core Invariant:**
```
∀ sandbox application memory region m:
  m is backed by exactly one host memfd ∧
  host sees all application anonymous memory as shmem (not anon) for that cgroup
```
**Source:** Resource Model, "Memory" -- "A single memfd backs all application memory."
**Counterexample:** If application memory were backed by multiple mechanisms, cgroup accounting would fragment and resource limits (OOM, pressure) would not accurately reflect the sandbox's true memory usage. This would allow a sandbox to exceed its memory limits via accounting blind spots.
**Why this matters for bridge/orbit:** When bridge monitors resource usage of sandboxed executions, it must read `memory.stat` understanding that application memory appears as `shmem`, not `anon`. Misreading this would make memory limits ineffective.

### INV-GVR-008: Sandbox time isolation
**Core Invariant:**
```
∀ time value t returned to sandboxed application:
  t originates from Sentry's own vDSO/time-keeping implementation ∧
  t does NOT share state with host clock after initialization
```
**Source:** Resource Model, "Time" -- "Time in the sandbox is provided by the Sentry, through its own vDSO and time-keeping implementation. This is distinct from the host time, and no state is shared with the host, although the time will be initialized with the host clock."
**Counterexample:** If the sandbox shared host clock state, a side-channel could leak timing information between sandboxes or from host to sandbox. The sandbox could also manipulate host time if the mapping were bidirectional.
**Why this matters for bridge/orbit:** Bridge's execution timeouts rely on monotonic time within the sandbox. If the sandboxed workload could manipulate time, it could evade execution time limits.

### INV-GVR-009: Tickless idle -- zero CPU when no application threads are active
**Core Invariant:**
```
∀ sandbox state where all_application_threads_idle:
  Sentry disables all timers ∧ Sentry CPU usage ≈ 0
```
**Source:** Resource Model, "Time" -- "When all application threads are idle, the Sentry disables timers until an event occurs that wakes either the Sentry or an application thread, similar to a tickless kernel."
**Counterexample:** If timers were not disabled on idle, idle sandboxes would consume CPU, preventing high-density deployment. A thousand idle sandboxes would each burn a sliver of CPU, aggregating to significant waste.
**Why this matters for bridge/orbit:** Bridge may run many idle sandboxes awaiting dispatch. If the sandbox mechanism doesn't go truly idle, it degrades platform density.

### INV-GVR-010: Sentry cannot open host sockets
**Core Invariant:**
```
∀ socket operations:
  Sentry.may_create_socket() = false (unless host networking mode is enabled) ∧
  Sentry receives file descriptors only via SCM_RIGHTS from Gofer
```
**Source:** Networking Guide, "How packets get to and from gVisor" -- "The sentry, which for security cannot open host sockets of its own, is initialized with a single AF_PACKET socket." Resource Model footnote: "Unless host networking is enabled, the Sentry is not able to create or open host file descriptors itself, it can only receive them in this way from the Gofer."
**Counterexample:** If the Sentry could open arbitrary sockets, a compromised Sentry could establish exfiltration channels or connect to internal services. The Gofer is the sole gateway for host resource access.
**Why this matters for bridge/orbit:** Bridge's sandbox must similarly gate all host I/O through a controlled proxy process. Direct socket creation in the sandbox process would be an architectural violation.

### INV-GVR-011: Process isolation -- sandboxed processes invisible to host
**Core Invariant:**
```
∀ process p running inside sandbox S:
  p does NOT appear in host's process table (e.g., /proc, ps, top)
```
**Source:** Resource Model, "Processes" -- "Processes within the sandbox do not manifest as processes on the host system, and process-level interactions within the sandbox require entering the sandbox."
**Counterexample:** If sandboxed processes appeared in the host process table, an attacker could signal, ptrace, or observe them from outside the sandbox, breaking process isolation. Host observability tools could leak information about sandboxed workloads.
**Why this matters for bridge/orbit:** Bridge spawns sandboxed processes. If those processes leak into the host process table, it creates both an observability leak and a potential attack surface (signals, ptrace from other host processes).

### INV-GVR-012: Network resource containment
**Core Invariant:**
```
∀ network state s (sockets, routing tables, connection tracking, port bindings):
  s exists only within the sandbox's netstack ∧
  s does NOT appear in host network state (except packets in flight on virtual devices)
```
**Source:** Resource Model, "Networking" -- "The sandbox attaches a network endpoint to the system, but runs its own network stack. All network resources, other than packets in flight on the host, exist only inside the sandbox."
**Counterexample:** If socket state leaked to the host, host-level firewall rules could interfere with sandbox networking, or one sandbox could observe another's connections. Network namespace sharing would create cross-sandbox side channels.
**Why this matters for bridge/orbit:** Bridge may run multiple sandboxes concurrently. Network isolation between sandboxes must hold -- one sandbox's connections must not be visible to or influenceable by another sandbox.

### INV-GVR-013: Memory release on madvise
**Core Invariant:**
```
∀ memory region r where application calls madvise(DONTNEED/FREE):
  Sentry releases r back to host immediately ∧
  r can be reclaimed by host for other uses
```
**Source:** Resource Model, "Physical memory" -- "When an application marks a region of memory as no longer needed, for example via a call to madvise, the Sentry releases this memory back to the host."
**Counterexample:** If madvise hints were ignored, a sandbox that freed memory internally would continue to hold host memory, preventing effective resource multiplexing. A long-running sandbox would exhibit monotonic memory growth.
**Why this matters for bridge/orbit:** Bridge's sandboxed executions may allocate and free memory over their lifetime. If freed memory is not returned to the host, memory pressure accumulates and degrades platform density over time.

### INV-GVR-014: Dual-kernel exploit requirement
**Core Invariant:**
```
∀ sandbox escape:
  attacker must exploit BOTH the Sentry (Go) ∧ the host Linux kernel (C) ∧
  these attack surfaces share zero code paths
```
**Source:** Intro page, "How does gVisor provide isolation?" -- "In order to break out of a gVisor sandbox, an attacker would need to simultaneously exploit the gVisor Sentry kernel AND the host Linux kernel, which do not share any code."
**Counterexample:** If the Sentry and host kernel shared code (e.g., via a common library), a single vulnerability could compromise both. The lack of shared code means two independent exploits are needed for escape.
**Why this matters for bridge/orbit:** This is the foundational security property of the dual-kernel architecture. Bridge's own sandbox design must ensure no code is shared between the sandbox boundary layer and the host kernel interface. Any shared code would reduce the escape requirement from two exploits to one.

### INV-GVR-015: Specialized API non-implementation
**Core Invariant:**
```
∀ kernel feature f that is specialized (raw sockets, ioctls, extended attributes, module-specific):
  Sentry does NOT implement f ∧ Sentry does NOT pass through f to host
```
**Source:** Security Model, Principle #2: "Only common, universal functionality is implemented. Some filesystems, network devices or modules may expose specialized functionality... we do not implement or pass through these specialized APIs."
**Counterexample:** If `ioctl` were passed through on a device, the device driver's attack surface becomes reachable from the sandbox. Specialized APIs are often less audited and contain more vulnerabilities than core syscalls.
**Why this matters for bridge/orbit:** Bridge's syscall filtering must not allow specialized APIs through. The filtering must be a deny-by-default allowlist, where only common, well-audited syscalls are permitted and all specialized interfaces are blocked.

### INV-GVR-016: Platform interception completeness
**Core Invariant:**
```
∀ sandboxed execution on platform P:
  P intercepts ALL syscalls AND page faults from sandboxed code ∧
  no execution path reaches host kernel directly from sandboxed code
```
**Source:** Platforms page -- "gVisor requires a platform to implement interception of syscalls, basic context switching, and memory mapping functionality." Intro page: "gVisor contains multiple mechanisms by which it can intercept system calls and page faults."
**Counterexample:** If a platform misses a syscall interception (e.g., a new syscall number not in the seccomp filter), that syscall executes directly on the host kernel, bypassing the Sentry entirely. This is a single-point escape.
**Why this matters for bridge/orbit:** Bridge's sandbox platform (likely seccomp-based) must have a deny-by-default syscall filter. Any syscall not explicitly handled by the sandbox layer must be blocked, not passed through.
