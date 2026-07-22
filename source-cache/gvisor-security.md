# oracle/gvisor-security — Security model: defense in depth, seccomp, user namespaces
Source: https://gvisor.dev/docs/architecture_guide/security/
Date pulled: 2026-07-21

## Extracted Invariants

### INV-GVS-001: No direct system call passthrough to host
**Core Invariant:**
```
∀ syscall ∈ Sentry.supported_syscalls:
  sentry_implementation(syscall) exists
  ∧ ¬passthrough(syscall, host_kernel)
```
Every supported system call has an independent implementation in the Sentry. No
system call is passed through directly to the host kernel. The Sentry intercepts
and reimplements the entire System API that the application sees.

**Source:** "Principles: Defense-in-Depth" section, bullet 1. "No system call is passed through directly to the host. Every supported call has an independent implementation in the Sentry, that is unlikely to suffer from identical vulnerabilities that may appear in the host."

**Counterexample:** If `open()` were passed through to the host, an application could trigger a host kernel vulnerability (e.g., a race condition in the VFS layer) by crafting specific arguments. The application would have direct access to host kernel code paths, bypassing the Sentry's safety layer entirely. The Dirty Cow example: an application used `ptrace` and `/proc` file opens with multi-threaded racing to gain control of system memory pages.

**Why this matters for bridge/orbit:** Bridge uses a seccomp-based sandbox with a verify-machine gate. The same principle applies: the seccomp filter must never permit untrusted code to make raw host syscalls. If the verify-machine incorrectly approves a syscall that touches the host kernel's attack surface, the sandbox is defeated. Orbit's dispatch model similarly must never allow dispatched code to escape its isolation boundary via direct host syscalls.

**Trust level:** MEDIUM (oracle-extract from gVisor documentation — not independently verified against Sentry source)

---

### INV-GVS-002: Sentry host syscall surface is explicitly enumerated and minimized
**Core Invariant:**
```
∀ op ∈ host_operations:
  permitted(op) ↔ op ∈ {dup, close, sync, timer, signal, fd_read, fd_write, socket_to_gofer, veth_rw}
  ∧ ¬permitted(open_file)
  ∧ ¬permitted(create_socket)  [unless host_networking ∨ directfs]
```
The Sentry may only make a minimal, explicitly enumerated set of host system
calls. It is NOT permitted to open new files or create new sockets on the host
(unless host networking or directfs mode is enabled, which expands the surface).

**Source:** "What can a sandbox do?" section, bullet 2. "Make a minimal set of host system calls. The calls do not include the creation of new sockets (unless host networking mode is enabled) or opening files (unless directfs is enabled). The calls include duplication and closing of file descriptors, synchronization, timers and signal management."

**Counterexample:** If the Sentry could open arbitrary files on the host, an exploit that compromises the Sentry (chain exploit) could write to `/etc/passwd`, drop a kernel module, or exfiltrate host secrets. The surface minimization converts a Sentry compromise from "host takeover" to "limited sandbox escape."

**Why this matters for bridge/orbit:** Bridge workers run in a restricted environment. The set of host operations available to bridge workers must be similarly enumerated and minimized. A bridge worker that can open arbitrary files or create arbitrary sockets has an unnecessarily large blast radius. The audit should verify that bridge's operational surface is explicitly enumerated, not emergent.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-003: Application only manipulates virtualized resources, never host resources
**Core Invariant:**
```
∀ resource ∈ {system_time, kernel_settings, filesystem_attributes}:
  manipulates(app, resource) → virtualized(resource)
  ∧ ¬affects(manipulates(app, resource), host_resource)
```
Even with full Linux capabilities, a user in a gVisor sandbox can only manipulate
virtualized system resources. Changes to system time, kernel settings, or
filesystem attributes affect the sandbox's virtual view, not the underlying host.

**Source:** "What can a sandbox do?" section. "Even with appropriate capabilities, a user in a gVisor sandbox will only be able to manipulate virtualized system resources (e.g. the system time, kernel settings or filesystem attributes) and not underlying host system resources."

**Counterexample:** If an application could change the host system time, it could invalidate TLS certificates, break audit log correlation, or prematurely expire credentials. If it could change host kernel settings, it could disable host-level security mechanisms (e.g., ASLR, mmap_min_addr).

**Why this matters for bridge/orbit:** Bridge's verify-machine must distinguish between operations on sandboxed/virtualized resources and operations on host resources. A false negative that treats a host-resource-modifying operation as safe would violate this invariant. Orbit's session isolation must similarly prevent one session from manipulating resources visible to another session.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-004: No specialized API passthrough — ioctls, raw sockets, extended attributes blocked
**Core Invariant:**
```
∀ api ∈ {ioctl, raw_socket, xattr, specialized_fs_module}:
  ¬implements(Sentry, api)
  ∧ ¬passthrough(Sentry, api, host)
```
Only common, universal kernel functionality is implemented in the Sentry.
Specialized APIs exposed by specific filesystems, network devices, or kernel
modules (ioctls, raw sockets, extended attributes) are neither implemented nor
passed through.

**Source:** "Principles: Defense-in-Depth" section, bullet 2. "Only common, universal functionality is implemented. Some filesystems, network devices or modules may expose specialized functionality to user space applications via mechanisms such as extended attributes, raw sockets or ioctls. Since the Sentry is responsible for implementing the full system call surface, we do not implement or pass through these specialized APIs."

**Counterexample:** If raw sockets were passed through, an application could craft arbitrary IP packets, spoof source addresses, or send packets that bypass network policy. If ioctls were passed through, a device-specific ioctl could trigger a kernel driver bug (device drivers are a well-known source of kernel vulnerabilities). If extended attributes were passed through, an application could set security.* xattrs that alter MAC policy.

**Why this matters for bridge/orbit:** Bridge's seccomp filter must block ioctl, raw socket creation, and other specialized syscall classes. The audit should verify that no specialized API path exists in bridge's operational surface. Even if a syscall number is in the allowed set, its argument combinations may create a specialized API surface.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-005: No unsafe Go code outside files named unsafe.go
**Core Invariant:**
```
∀ file ∈ Sentry_source_tree:
  file.imports("unsafe") → file.name matches "*unsafe.go"
```
All unsafe Go code is isolated in files with the suffix "unsafe.go". Regular
source files are not permitted to import the `unsafe` package. This constraint
enables mechanical auditing: grep for `unsafe` imports and verify they only
appear in files whose names end with `unsafe.go`.

**Source:** "Principles: Defense-in-Depth" section, "Unsafe code is carefully controlled." "All unsafe code is isolated in files that end with 'unsafe.go', in order to facilitate validation and auditing. No file without the unsafe suffix may import the unsafe package."

**Counterexample:** If unsafe code were scattered across the codebase, a reviewer could not efficiently audit all memory-unsafe paths. A bug in an `unsafe.Pointer` usage buried in a regular file (e.g., `mm.go`, `vfs.go`) would evade the targeted audit that the naming convention enables. Memory corruption in the Sentry could be chained into a sandbox escape.

**Why this matters for bridge/orbit:** Bridge is also Go. The same invariant should apply: all `unsafe` usage must be isolated in `*_unsafe.go` files. The audit should verify this mechanically. Bridge's use of `unsafe` for syscall argument marshaling is the most dangerous code path — it must be auditable in isolation.

**Trust level:** MEDIUM (oracle-extract — verifiable mechanically)

---

### INV-GVS-006: No CGo in Sentry — pure Go binary
**Core Invariant:**
```
Sentry.binary ∈ pure_go_binaries
∧ ¬∃ cgo_import ∈ Sentry.transitive_deps
```
The Sentry must be a pure Go binary. CGo is not allowed. This eliminates the
entire class of memory-safety bugs that arise from C/Go interop: buffer
overflows, use-after-free, and FFI marshaling errors in the CGo boundary layer.

**Source:** "Principles: Defense-in-Depth" section. "No CGo is allowed. The Sentry must be a pure Go binary."

**Counterexample:** If Sentry used CGo to call into a C library (e.g., libseccomp, libcap), a vulnerability in that C library becomes a vulnerability in the Sentry. More subtly, CGo introduces implicit memory sharing between Go's GC'd heap and C's manual heap — a common source of use-after-free and double-free bugs that Go's memory model was designed to prevent.

**Why this matters for bridge/orbit:** Bridge is Go. Any bridge dependency that uses CGo expands the attack surface. The audit should enumerate all CGo imports in bridge's dependency tree and assess each one. Pure Go is a security property, not just a stylistic preference.

**Trust level:** MEDIUM (oracle-extract — verifiable via `go tool nm` or `go version -m`)

---

### INV-GVS-007: Core Sentry packages have no external imports
**Core Invariant:**
```
∀ pkg ∈ Sentry.core_packages:
  imports(pkg) ⊆ {stdlib, Sentry.internal_packages}
```
External (third-party) imports are not generally allowed within the core
packages. Only limited external imports are permitted in setup code. The code
available inside the Sentry's runtime is carefully controlled.

**Source:** "Principles: Defense-in-Depth" section. "External imports are not generally allowed within the core packages. Only limited external imports are used within the setup code. The code available inside the Sentry is carefully controlled, to ensure that the above rules are effective."

**Counterexample:** If core Sentry packages imported an external library with a vulnerability (e.g., an HTTP parser, a YAML parser, a crypto library), that vulnerability becomes part of the Sentry's trusted computing base. Since the Sentry implements the kernel-equivalent for the sandbox, any vulnerability in the Sentry's TCB is a potential sandbox escape.

**Why this matters for bridge/orbit:** Bridge's verify-machine and sandbox code should minimize external dependencies. Each external Go module in bridge's `go.sum` for core packages is a potential vulnerability. The audit should list every external import in bridge's sandbox/verification path.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-008: Ptrace stubs never execute host syscalls directly
**Core Invariant:**
```
∀ tracee ∈ Sentry.ptrace_stubs:
  ¬executes_in_host_kernel(tracee)
  ∧ ∀ syscall ∈ tracee.attempted_syscalls:
    intercepted_by(Sentry, syscall)
    ∧ registers(tracee) ← Sentry.computed_result(syscall)
```
On platforms that use ptrace, the traced stubs are never allowed to continue
execution into the host kernel and complete a system call directly. Instead, the
Sentry intercepts every attempted syscall, computes the result, and reflects
the resulting register state back into the tracee before it resumes in userspace.

**Source:** FAQ "Is this just a ptrace sandbox?" "The stubs that are traced are never allowed to continue execution into the host kernel and complete a call directly. Instead, all system calls are interpreted and handled by the Sentry itself, who reflects resulting register state back into the tracee before continuing execution in userspace."

**Counterexample:** A TOCTOU (time-of-check, time-of-use) race: if the ptrace supervisor inspected a syscall's arguments and then allowed the tracee to continue into the kernel, a concurrent thread could modify the arguments between check and execution. This is the fundamental flaw in "ptrace sandboxes" — they authorize syscalls by inspecting arguments at check time, but the tracee's memory is mutable by other threads until the kernel actually executes the syscall.

**Why this matters for bridge/orbit:** Bridge's seccomp filter is a TOCTOU-free mechanism (seccomp-BPF filters are applied atomically at syscall entry). However, bridge's verify-machine pre-approval model is a logical equivalent of check-time authorization. If bridge pre-approves a code block for execution, and the code block's behavior changes between approval and execution (e.g., via a dependency update, filesystem change, or shared memory), we have a TOCTOU race. The audit should verify that bridge's verify-approve-execute pipeline has no mutable state between the verify and execute phases.

**Trust level:** MEDIUM (oracle-extract — architectural claim verifiable against Sentry platform code)

---

### INV-GVS-009: Sentry operates within an empty mount namespace
**Core Invariant:**
```
Sentry.mount_namespace = empty_mount_namespace
∧ filesystem_access(Sentry) ⊆ {fds_from_Gofer}
```
The Sentry process itself operates within an empty mount namespace. It has no
direct filesystem access except through file descriptors provided by the Gofer
process. The Sentry can be further hardened to deny all direct filesystem access,
in which case the Gofer performs all filesystem operations on the Sentry's behalf.

**Source:** "What can a sandbox do?" section, bullet 1. "The sandbox itself operates within an empty mount namespace."

**Counterexample:** If the Sentry had access to the host filesystem tree, a Sentry compromise could read `/proc/self/environ` (leaking host environment variables including secrets), access `/etc/kubernetes` (leaking cluster credentials), or write to host paths. The empty mount namespace ensures that even a fully compromised Sentry has no visibility into the host filesystem tree.

**Why this matters for bridge/orbit:** Bridge workers should similarly operate with minimal mount access. The audit should verify that bridge worker processes have no unnecessary filesystem mounts. Orbit sessions should each have an isolated filesystem view that prevents cross-session data leakage.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-010: Two-layer defense — app never talks to host, Sentry has minimal host surface
**Core Invariant:**
```
∀ app_syscall:
  path(app_syscall) = app → Sentry → host_kernel
  ∧ ¬∃ path(app_syscall) = app → host_kernel  [layer 1]
  ∧ surface(Sentry → host_kernel) ⊆ minimal_syscall_set  [layer 2]
```
gVisor's security model is a two-layer defense. Layer 1: the application's direct
interactions with the host System API are intercepted by the Sentry (the Sentry
implements the System API instead). Layer 2: the Sentry's own System API access
to the host is minimized to a safer, restricted set. Both layers must hold for
the security model to be sound.

**Source:** "Goals: Limiting Exposure" section. "First, the application's direct interactions with the host System API are intercepted by the Sentry, which implements the System API instead. Second, the System API accessible to the Sentry itself is minimized to a safer, restricted set."

**Counterexample:** Layer 1 failure: if an application finds a path to make a raw host syscall (e.g., via a Sentry bug that incorrectly handles a syscall, or via a side channel), it escapes the sandbox. Layer 2 failure: if a compromised Sentry has full host syscall access, the compromise escalates to full host takeover. Both layers are necessary — layer 1 alone is insufficient (defense in depth requires the second layer).

**Why this matters for bridge/orbit:** This is the same architecture bridge uses: the verify-machine (layer 1) prevents untrusted code from executing host syscalls unsafely, and the seccomp filter + sandbox (layer 2) constrains even the verified code's host access. The audit should verify both layers independently: (1) does the verify-machine correctly reject unsafe code? (2) does the seccomp filter correctly constrain even verified code? A failure in either layer is a sandbox escape.

**Trust level:** MEDIUM (oracle-extract)

---

### INV-GVS-011: Sandbox is not a substitute for secure architecture
**Meta-Principle:**
```
secure_system ⇒ (secure_architecture ∧ (sandbox ⇒ defense_in_depth))
sandbox ¬⇒ secure_system
```
A sandbox is a defense-in-depth measure, not a replacement for secure system
architecture. If there is an exploitable network-accessible service on the host
or another API path, an attacker need not escape the sandbox at all.

**Source:** "Other Vectors" section. "An attacker need not escalate privileges within a container if there's an exploitable network-accessible service on the host or some other API path. A sandbox is not a substitute for a secure architecture."

**Counterexample:** A host running an unpatched HTTP server on port 443 is exploitable regardless of how secure the container sandbox is. The sandbox protects against exploitation through the container's system call interface but does nothing against network-level attacks on the host's own services. Defense in depth requires securing both the sandbox boundary and the host surface.

**Why this matters for bridge/orbit:** Bridge's sandbox is similarly defense-in-depth, not a security silver bullet. The audit should verify the full security posture: bridge sandbox + host hardening + network policy + credential management. A finding that says "bridge sandbox prevents X" is incomplete without verifying that X cannot be reached through another path that bypasses the sandbox entirely.

**Trust level:** MEDIUM (oracle-extract)

---

## Constraints and Design Rules

### CSTR-GVS-001: Gofer process is the sole filesystem gateway
The Sentry accesses the container filesystem exclusively through a Gofer
process connected via socket. The Gofer provides file descriptors; the
Sentry reads/writes those fds directly. The Sentry has no independent
filesystem access. The Gofer is the single chokepoint for filesystem
policy enforcement.

### CSTR-GVS-002: No device emulation — no virtual hardware attack surface
gVisor does not implement device emulation (unlike VMs which emulate APIC,
vhost, block devices, etc.). This eliminates the entire class of exploits
that target virtual device implementations — a historically rich source of
VM escape vulnerabilities (VENOM, Cloudburst, VENOM 2.0).

### CSTR-GVS-003: Continuous fuzzing required
The Sentry is fuzzed continuously. Production crashes are recorded and
triaged. This is a process requirement, not a code property, but it's a
necessary condition for the sandbox to maintain its security guarantees
over time as new syscalls are implemented and existing ones are modified.

### CSTR-GVS-004: Platform-dependent defense delegation
Defense against System ABI attacks (traps, interrupts) and hardware side
channels is delegated to the host kernel/hypervisor and platform choice.
gVisor does not claim to provide protection against these vectors and
explicitly states this is out of scope.

---

## Failure Modes (what breaks when invariants are violated)

### FM-GVS-001: Syscall passthrough → host kernel exploit
If INV-GVS-001 is violated and any syscall passes directly to the host,
an application can craft arguments to trigger host kernel vulnerabilities.
This is the most common exploit class and the primary threat gVisor exists
to counter.

### FM-GVS-002: Sentry surface expansion → chain exploit escalation
If INV-GVS-002 is violated and the Sentry can open files/create sockets,
a Sentry compromise (from a Sentry-level bug) escalates to full host
compromise. The minimized surface is what makes a Sentry bug less severe
than a host kernel bug.

### FM-GVS-003: Host resource manipulation → system integrity loss
If INV-GVS-003 is violated, sandboxed applications can modify host system
time (breaking TLS, audit logs), host kernel settings (disabling ASLR),
or host filesystem attributes (escaping MAC policy).

### FM-GVS-004: TOCTOU in ptrace → sandbox bypass
If INV-GVS-008 is violated and stubs execute host syscalls, a multi-threaded
application can modify syscall arguments between the check and the execution,
effectively executing any syscall with any arguments.

### FM-GVS-005: CGo in Sentry → memory unsafety
If INV-GVS-006 is violated, CGo introduces manual memory management into
the Sentry's Go runtime. Use-after-free, double-free, and buffer overflow
in the CGo boundary are all potential sandbox escape vectors.

---

## Verification Status

None of these invariants have been independently verified against the
gVisor source code. This is an oracle-extract from gVisor's own
documentation. The invariants describe what gVisor claims about itself.

To verify these, one would need to:
1. Audit the Sentry syscall table against INV-GVS-001 (no passthrough)
2. Audit the Sentry's host syscall usage against INV-GVS-002 (minimized surface)
3. Grep for `unsafe` imports against INV-GVS-005 (naming convention)
4. Run `go tool nm` or `go version -m runsc` against INV-GVS-006 (no CGo)
5. Audit the Go module graph against INV-GVS-007 (no external core imports)
6. Audit the ptrace platform code against INV-GVS-008 (stub control)

**Trust level for all invariants:** MEDIUM (oracle-extract — documented claims, not independently verified)

---

## Bridge/Orbit Audit Relevance Summary

These invariants are directly applicable to the bridge+orbit audit because
both systems implement sandboxing layers with similar architectural patterns:

| gVisor Invariant | Bridge/Orbit Analog |
|---|---|
| INV-GVS-001 (no passthrough) | verify-machine must never approve raw host syscalls |
| INV-GVS-002 (minimized Sentry surface) | bridge worker capabilities must be enumerated and audited |
| INV-GVS-003 (virtualized resources) | orbit sessions must not access host resources |
| INV-GVS-004 (no specialized APIs) | seccomp filter must block ioctl, raw sockets, xattr paths |
| INV-GVS-005 (unsafe isolation) | bridge's unsafe code must be in isolated, auditable files |
| INV-GVS-006 (no CGo) | bridge must be pure Go or CGo surface must be audited |
| INV-GVS-007 (no external core imports) | bridge's sandbox path must minimize third-party deps |
| INV-GVS-008 (no TOCTOU) | verify-approve-execute pipeline must be atomic |
| INV-GVS-009 (empty mount namespace) | bridge workers must have minimal mount access |
| INV-GVS-010 (two-layer defense) | verify-machine + seccomp filter = two layers |
| INV-GVS-011 (sandbox != architecture) | bridge sandbox is defense-in-depth, not primary security |
