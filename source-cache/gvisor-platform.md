# oracle/gvisor-platform — Platform implementations: KVM, ptrace, systrap

Source: https://gvisor.dev/docs/architecture_guide/platforms/
Deep-linked: https://gvisor.dev/docs/architecture_guide/security/, https://gvisor.dev/docs/architecture_guide/intro/, https://github.com/google/gvisor/blob/master/pkg/sentry/platform/systrap/README.md
Date pulled: 2026-07-21

## Extracted Invariants

### INV-GVP-001: No host syscall pass-through
**Core Invariant:**
```
∀ syscall s invoked by sandboxed workload W:
  handle(s) ∈ Sentry.reimplementations
  ¬∃ s: Sentry passes s directly to host_kernel
  If s ∉ Sentry.reimplementations → W cannot invoke s
```
**Source:** Security Model ("No system call is passed through directly to the host"), Architecture Intro ("gVisor never passes through any system call to the host")
**Counterexample:** A sandboxed process calls `ioctl(SIOCGIFADDR)` on a network interface. If this were passed through to the host kernel (as traditional seccomp-bpf filters might allow), the sandbox could read host network configuration. gVisor prevents this — ioctl is either reimplemented in the Sentry or denied.
**Why this matters for bridge/orbit:** orbit's `Shell()` runs bash via `exec.CommandContext` — no seccomp, no syscall interception. Every syscall made by bash, piped commands, or spawned children goes directly to the host kernel. This is a direct violation of the gVisor security model. Bridge's dispatch is similarly direct-process — no interception layer exists.

### INV-GVP-002: Sentry host surface minimization
**Core Invariant:**
```
Sentry_allowed_syscalls ⊂ host_kernel_syscalls
Sentry_allowed_syscalls ∩ {open, creat, socket, connect, exec, ...} = ∅
  (unless host_networking=true or directfs=true)
Sentry_allowed_syscalls ⊆ {dup, close, futex, clock_gettime, tgkill, ...}
  i.e., FD duplication, synchronization, timers, signals only
```
**Source:** Security Model ("The host surface exposed to the Sentry is minimized... The Sentry is not permitted to open new files, create new sockets"), Architecture Intro ("system call filter prohibits system calls like exec(2), connect(2)")
**Counterexample:** A compromised Sentry attempting to `socket()` + `connect()` to exfiltrate sandbox data over the network. The host seccomp filter blocks it before it reaches the kernel. If the Sentry were allowed arbitrary host syscalls, a single Sentry exploit would equal full host compromise.
**Why this matters for bridge/orbit:** orbit's Gofer equivalent runs with full syscall access. There is no seccomp allowlist restricting what the process can do. A compromised orbit process can open any file, create sockets, exec arbitrary binaries — full host access.

### INV-GVP-003: Two-kernel isolation boundary
**Core Invariant:**
```
Sandbox_kernel(Sentry) ≠ Host_kernel(Linux)
code(Sentry) ∩ code(Host_kernel) = ∅
Exploit_escape ⟹ (compromise(Sentry) ∧ compromise(Host_kernel))
  i.e., attacker must exploit BOTH kernels with independent exploits
```
**Source:** Architecture Intro ("In order to break out of a gVisor sandbox, an attacker would need to simultaneously exploit the gVisor Sentry kernel and the host Linux kernel, which do not share any code")
**Counterexample:** A memory corruption bug in the Sentry's network stack allows code execution within the Sentry process. Without the host seccomp layer, the attacker could then make arbitrary host syscalls (connect, exec). With the Sentry confinement layer, the attacker must also escape the seccomp allowlist — a second, independent exploit.
**Why this matters for bridge/orbit:** orbit has no equivalent dual-kernel boundary. There is one kernel (host Linux), and the orbit process runs as a regular userspace process with no kernel-reimplementation layer between it and the host. Bridge dispatch similarly operates as a single host process — exploit bridge/orbit = host access.

### INV-GVP-004: Platform syscall interception completeness
**Core Invariant:**
```
∀ platform P ∈ {systrap, KVM, ptrace}:
  ∀ syscall s invoked by sandboxed thread T:
    T is prevented from completing s in host_kernel
    P intercepts s and transfers control to Sentry.handle(s)
  Stub_threads_never_complete_host_syscalls = true
```
**Source:** Platform Guide (all three platforms), Security Model FAQ ("The stubs that are traced are never allowed to continue execution into the host kernel and complete a call directly"), Systrap README ("seccomp filters to trap all user system calls")
**Counterexample:** A ptrace-based sandbox that uses `PTRACE_SYSCALL` (allow-and-inspect) instead of `PTRACE_SYSEMU` (intercept-and-emulate). A TOCTOU race lets the tracee complete a dangerous syscall between the ptracer's check and the kernel's execution. gVisor uses `PTRACE_SYSEMU` which prevents the system call from ever executing in the host kernel.
**Why this matters for bridge/orbit:** orbit's process sandbox has no syscall interception layer at all. `exec.CommandContext` launches a child process that makes syscalls directly to the host. There is nothing equivalent to ptrace, seccomp-trap, or KVM ring de-privileging between orbit child processes and the host kernel.

### INV-GVP-005: Memory-safe Sentry implementation
**Core Invariant:**
```
Language(Sentry) = Go (memory-safe)
Language(Host_kernel) = C (memory-unsafe)
¬∃ CGo in Sentry
∀ file importing "unsafe": filename must end in "unsafe.go"
∀ file NOT ending in "unsafe.go": ¬imports "unsafe"
External imports restricted in core packages
```
**Source:** Security Model ("Unsafe code is carefully controlled... No CGo is allowed... External imports are not generally allowed within the core packages")
**Counterexample:** If the Sentry used CGo to call a C library for performance, a buffer overflow in that C code would be exploitable from within the memory-safe Go context. The invariant eliminates the largest class of memory-corruption bugs from the Sentry itself.
**Why this matters for bridge/orbit:** orbit is written in Go and benefits from memory safety, but bridge's dispatch spawns and manages external processes (bash, compilation toolchains). These child processes are not memory-safe and their exploits give the attacker whatever privileges the bridge process has.

### INV-GVP-006: Sandbox PID namespace isolation
**Core Invariant:**
```
PID_table(Sentry) ∩ PID_table(Host) = ∅
∀ process p visible to sandboxed workload W:
  p ∈ PID_table(Sentry) — a virtual process, not a host process
  top(1) on host does NOT show p
  kill(p.pid, SIGKILL) from host does NOT affect p
```
**Source:** Architecture Intro ("gVisor keeps track of its own PID table representing the processes in the sandbox. These are not real host processes! Running top(1) on the host will not show them.")
**Counterexample:** A traditional container runtime where each container process is a real host process. `docker top` shows host PIDs. `kill -9 <pid>` from the host kills the container process. Namespace isolation alone doesn't prevent this — only PID namespace separation, which is weaker than Sentry-level virtualization.
**Why this matters for bridge/orbit:** orbit's `Shell()` spawns real host processes. `ps aux | grep bash` on the host will show orbit's child processes. `kill -9` from a compromised co-tenant process can terminate orbit operations. The PID table is the host PID table — no virtualization layer.

### INV-GVP-007: Platform address space isolation (KVM-specific)
**Core Invariant:**
```
KVM_platform:
  Sandbox_code_executes_in(guest_ring_3)
  Address_space_switch_uses(VMX/SVM_virtualization_extensions)
  ∀ sandbox_memory_page P:
    P ∈ sandbox_address_space — distinct from Sentry address space
    Sentry cannot accidentally read/write sandbox memory without explicit mapping
  Sentry_acts_as_VMM: manages guest physical memory via KVM API
```
**Source:** Platform Guide ("KVM platform uses the kernel's KVM functionality to allow the Sentry to act as both guest OS and VMM... leverages virtualization extensions available on modern processors in order to improve isolation and performance of address space switches")
**Counterexample:** Without hardware virtualization, address spaces are switched via mmap/munmap in a single process. A bug in the Sentry's memory management could write into sandbox memory or vice versa. KVM's EPT/NPT (Extended/Nested Page Tables) provide hardware-enforced isolation — the MMU enforces the boundary.
**Why this matters for bridge/orbit:** orbit processes share the same address space as the orbit runtime (they're fork/exec children, not KVM guests). A bug in orbit's memory management that writes to a child's address space requires only a standard Go bug, not a page-table escape. Bridge dispatch has the same issue — no hardware-enforced memory isolation between dispatch and dispatched workloads.

### INV-GVP-008: Systrap signal-based interception completeness
**Core Invariant:**
```
Systrap_platform:
  seccomp_filter_installed_for_each_stub_thread
  seccomp_action = SECCOMP_RET_TRAP (not SECCOMP_RET_KILL, not SECCOMP_RET_ALLOW)
  Signals_trapped = {SIGSYS, SIGSEGV, SIGBUS, SIGFPE, SIGTRAP, SIGILL}
  ∀ trapped_event e:
    stub_signal_handler(e) → notifies Sentry → Sentry handles → Sentry resumes stub
  Signal_frame_written_to_shared_memory:
    Sentry can read_and_modify(thread_register_state, thread_FPU_state)
```
**Source:** Systrap README ("Installing seccomp filters to trap all user system calls... Setting up the sysmsg signal handler for SIGSYS, SIGSEGV, SIGBUS, SIGFPE, SIGTRAP, and SIGILL... The signal frame is saved on the signal handler stack. This memory region is shared with the Sentry process.")
**Counterexample:** If a signal type is not trapped (e.g., SIGFPE not in the handler set), a division-by-zero in sandbox code would be delivered to the stub thread's default handler, which might crash the stub or leak FPU state to the host. Completeness of signal trapping is essential — any untrapped signal is a potential bypass.
**Why this matters for bridge/orbit:** Neither bridge nor orbit trap any signals from child processes. A SIGSEGV in a child process is delivered normally, potentially crashing the child or triggering core dumps with sandbox data. There's no Sentry equivalent to intercept and virtualize signals.

### INV-GVP-009: Gofer-mediated filesystem isolation
**Core Invariant:**
```
Sandbox_filesystem_access:
  Sentry operates in empty_mount_namespace
  Sentry has no direct filesystem access (unless directfs=true)
  ∀ file access by sandboxed workload:
    Sentry requests FD from Gofer via connected_socket
    Gofer opens file and donates FD to Sentry
    Sentry reads/writes donated FD directly (no path-based access)
  O_NOFOLLOW enforced: symlinks are not resolved through
```
**Source:** Security Model ("Establish communication with a Gofer process... The sandbox itself operates within an empty mount namespace")
**Counterexample:** If the Sentry had its own mount namespace with /proc or /sys mounted, a Sentry bug that called `open("/proc/self/mem")` could leak Sentry memory. The empty mount namespace ensures the Sentry has no filesystem to open — all file access goes through the Gofer's FD donation, which is an explicit, auditable channel.
**Why this matters for bridge/orbit:** orbit's file resolution is entirely user-space (`filepath.Clean` + `filepath.Rel`). There's no empty mount namespace, no FD donation, no seccomp enforcement of O_NOFOLLOW. A path traversal through symlinks can escape the intended directory. Bridge dispatch has similar path-resolution-only isolation.

### INV-GVP-010: Defense-in-depth: independent security layers
**Core Invariant:**
```
Defense_layers:
  L1_syscall_interception:  platform (seccomp/KVM) — prevents direct host syscalls
  L2_syscall_emulation:     Sentry — reimplements all syscalls in Go
  L3_sentry_confinement:    seccomp allowlist on Sentry (~53 host syscalls)
  L4_filesystem_isolation:  Gofer FD donation + O_NOFOLLOW + empty mount ns
  L5_network_isolation:     netstack (Go userspace TCP/IP)
  L6_linux_isolation:       user_ns + mount_ns + pivot_root
  L7_resource_bounding:     cgroups, rlimits

  ∀ layer L_i: L_i provides independent security property
  compromise(L_i) ⟹ ¬compromise(L_j) for j ≠ i
  Full_escape ⟹ compromise(all_relevant_layers)
```
**Source:** Security Model ("gVisor's primary design goal is to minimize the System API attack vector through multiple layers of defense"), Architecture Intro ("They are used for defense-in-depth rather than as a primary layer of defense")
**Counterexample:** A traditional container that relies solely on seccomp-bpf + namespaces. If the seccomp filter is misconfigured (a single dangerous syscall allowed), full host access is possible — one layer, one breach, full compromise.
**Why this matters for bridge/orbit:** orbit has partial implementation of at most L4 (path containment, user-space only) and L7 (30s timeout). L1-L3, L5, and L6 are completely absent. Bridge dispatch has even fewer layers. A single bug in path resolution yields full filesystem access.

### INV-GVP-011: ptrace SYSEMU: never-execute-in-host guarantee
**Core Invariant:**
```
Ptrace_platform:
  Uses PTRACE_SYSEMU (NOT PTRACE_SYSCALL)
  PTRACE_SYSEMU semantics:
    When tracee reaches a syscall instruction → kernel stops tracee BEFORE executing syscall
    Tracer reads tracee registers, determines intended syscall, emulates it
    Tracer modifies tracee registers to reflect emulated result
    Tracer resumes tracee in userspace (past the syscall instruction)
    The syscall instruction NEVER executes in the host kernel
  TOCTOU_race_impossible: no window between check and execution
```
**Source:** Security Model FAQ ("The stubs that are traced are never allowed to continue execution into the host kernel and complete a call directly. Instead, all system calls are interpreted and handled by the Sentry itself, who reflects resulting register state back into the tracee before continuing execution in userspace.")
**Counterexample:** A sandbox using `PTRACE_SYSCALL` (ptrace-stop-before-and-after but syscall still executes). Between the pre-syscall stop and the post-syscall stop, the kernel executes the syscall with the tracee's arguments. A TOCTOU race where the tracer checks arguments at pre-stop but the kernel uses different arguments is possible. `PTRACE_SYSEMU` eliminates this — the syscall instruction is never handed to the host kernel at all.
**Why this matters for bridge/orbit:** orbit's child processes execute syscalls directly — there is no tracer, no interception, no emulation. The "check" (if any) and "execution" happen in the same kernel with no intermediary. This is the zeroth layer missing entirely.

### INV-GVP-012: Non-1:1 syscall mapping
**Core Invariant:**
```
∀ sandbox_syscall s_sandbox:
  host_syscalls_made_to_service(s_sandbox) may be 0, 1, or many
  ¬∃ mapping function f: s_sandbox → s_host such that s_sandbox ⇔ s_host
  Example: getpid() from sandbox → 0 host syscalls (Sentry PID table lookup)
  Example: read(pipe) from sandbox → futex() host syscall (Go runtime synchronization)
  Example: write(file) from sandbox → pwrite64() host syscall (on donated FD)
```
**Source:** Architecture Intro ("the Sentry does need to be able to perform real system calls, but they do not map 1-to-1 to the system calls made by the sandboxed processes")
**Counterexample:** A seccomp-bpf filter that whitelists `read()` because the application needs it. A kernel bug in `read()` can be exploited by the sandboxed application because the application's `read()` maps 1-to-1 to the host kernel's `read()`. In gVisor, the sandboxed `read()` is handled entirely in the Sentry — the host kernel's `read()` implementation (and any bugs in it) is never reached from the sandbox path.
**Why this matters for bridge/orbit:** Every syscall from orbit child processes maps 1-to-1 to host kernel syscalls. `read()` from bash → host kernel `read()`. Any kernel bug in any syscall used by the child is directly exploitable.

---

## Source Trust Assessment

| Source | Type | Trust Level | Notes |
|---|---|---|---|
| gvisor.dev/docs/architecture_guide/platforms/ | primary (official docs) | HIGH | Authoritative gVisor project documentation, maintained alongside source |
| gvisor.dev/docs/architecture_guide/security/ | primary (official docs) | HIGH | Core security architecture documentation |
| gvisor.dev/docs/architecture_guide/intro/ | primary (official docs) | HIGH | Design-level documentation for security researchers |
| github.com/google/gvisor/pkg/sentry/platform/systrap/README.md | primary (source tree) | HIGH | In-tree documentation, maintained with implementation code |

All sources are official gVisor project documentation, maintained in the same repository as the implementation. Trust level: HIGH across all sources.

## Cross-Reference

- Existing `source-cache/gvisor.md` — covers the 7-layer defense model and CVE analysis
- This entry (`gvisor-platform.md`) — covers platform-level invariants (syscall interception mechanisms, address space isolation, defense-in-depth guarantees)
- The two entries are complementary: `gvisor.md` focuses on what was built and what broke; `gvisor-platform.md` focuses on why it works at the platform/kernel boundary level

## Notes

The platform page itself is a short high-level overview (~200 words of technical content). The substantial invariants come from the linked architecture pages (Security Model, Architecture Intro) and the systrap README. This is expected — the platform page is an index/selector guide, while the security architecture pages contain the design invariants.

This source cache entry synthesizes invariants from 4 pages to provide a complete picture of the gVisor platform security model. Each invariant is falsifiable: it makes a concrete claim that can be tested against the gVisor source code or against orbit/bridge implementations.
