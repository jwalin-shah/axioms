# oracle/linux-seccomp-deep — Seccomp BPF: filter program, action ordering, TSYNC, user notification
Source: https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-SCMP-001: Action precedence ordering is total and deterministic
**Core Invariant:**
```
∀ f1,f2 ∈ installed_filters, ∀ s ∈ syscalls:
  action(f1, s) = a1 ∧ action(f2, s) = a2 ⇒
  effective_action(s) = max_precedence(a1, a2)
```
**Source:** "Return values" section — "If multiple filters exist, the return value for the evaluation of a given system call will always use the highest precedent value."

**Precedence order (highest to lowest):**
1. SECCOMP_RET_KILL_PROCESS
2. SECCOMP_RET_KILL_THREAD
3. SECCOMP_RET_TRAP
4. SECCOMP_RET_ERRNO
5. SECCOMP_RET_USER_NOTIF
6. SECCOMP_RET_TRACE
7. SECCOMP_RET_LOG
8. SECCOMP_RET_ALLOW

**Counterexample:** If a later filter returns ALLOW while an earlier filter returns KILL_PROCESS for the same syscall, the process would continue executing a disallowed syscall — violating the sandbox. The kernel prevents this by always taking the highest-precedence action across all installed filters.

**Why this matters for bridge/orbit:** Orbit's seccomp sandbox installs multiple filter layers (base filter + per-sandbox filters). The precedence invariant guarantees that a more permissive filter cannot override a kill action from a stricter filter. Without this invariant, layered sandbox design would be unsound.

---

### INV-SCMP-002: NO_NEW_PRIVS is a hard prerequisite for unprivileged filter installation
**Core Invariant:**
```
∀ task t: install_filter(t, prog) succeeds ⇒
  (has_capability(t, CAP_SYS_ADMIN) ∨ no_new_privs_is_set(t))
```
**Source:** "Usage" section — "Prior to use, the task must call prctl(PR_SET_NO_NEW_PRIVS, 1) or run with CAP_SYS_ADMIN privileges in its namespace. If these are not true, -EACCES will be returned. This requirement ensures that filter programs cannot be applied to child processes with greater privileges than the task that installed them."

**Counterexample:** Without this invariant, an unprivileged process could install a permissive seccomp filter and then exec into a setuid binary. The setuid binary would inherit the permissive filter, and if it were compromised, the attacker would have escalated privileges with a reduced kernel attack surface that the original process didn't intend for a privileged context. The NO_NEW_PRIVS gate prevents this entire class of privilege-escalation-via-filter-inheritance attacks.

**Why this matters for bridge/orbit:** Orbit launches sandboxed processes that must not escape their privilege boundary. This invariant proves that a sandboxed process cannot install a filter on itself and then exec into a privileged binary to bypass the sandbox. The kernel enforces this at the prctl level.

---

### INV-SCMP-003: BPF programs cannot dereference pointers (structural TOCTOU prevention)
**Core Invariant:**
```
∀ bpf_prog p in seccomp context, ∀ instruction i ∈ p:
  i is not a pointer-dereference operation
```
**Source:** "Introduction" section — "BPF makes it impossible for users of seccomp to fall prey to time-of-check-time-of-use (TOCTOU) attacks that are common in system call interposition frameworks. BPF programs may not dereference pointers which constrains all filters to solely evaluating the system call arguments directly."

**Counterexample:** In a non-BPF syscall interposition framework (e.g., ptrace-based), a tracer reads the syscall arguments, checks them, and then allows the syscall. Between the check and the allow, another thread could modify the pointed-to memory, changing the actual arguments the kernel sees — a classic TOCTOU race. BPF eliminates this by forbidding pointer dereference entirely: the BPF program can only inspect the syscall number and argument registers, which are snapshotted by the kernel atomically.

**Why this matters for bridge/orbit:** Bridge's sandbox relies on seccomp to enforce syscall allowlists. The TOCTOU prevention invariant proves that the syscall arguments the BPF filter sees are the same ones the kernel will act on — there is no race window between filter evaluation and syscall execution. This is a stronger guarantee than any userspace interposition mechanism can provide.

---

### INV-SCMP-004: seccomp filter evaluation is not re-run after ptrace notification
**Core Invariant:**
```
∀ syscall s: trace_notification_fired(s) ⇒ ¬evaluate_seccomp_filters(s, again)
```
**Source:** "SECCOMP_RET_TRACE" section — "The seccomp check will not be run again after the tracer is notified. (This means that seccomp-based sandboxes MUST NOT allow use of ptrace, even of other sandboxed processes, without extreme care; ptracers can use this mechanism to escape.)"

**Counterexample:** A sandboxed process that is allowed to ptrace another sandboxed process could: (1) the target process makes a syscall that the filter would block, (2) seccomp returns TRACE, notifying the ptracer, (3) the ptracer changes the syscall to a permitted one, (4) the syscall proceeds without re-checking seccomp. The ptracer has bypassed the filter. If the filter is re-evaluated after ptrace, the changed syscall would be checked again — but it is not. This is an explicit design decision documented as a pitfall.

**Why this matters for bridge/orbit:** Orbit's sandbox policy must include a rule that denies ptrace (and process_vm_readv/process_vm_writev) for any sandboxed process. This invariant is the proof that the rule is necessary: without it, a compromised sandboxed process could use ptrace to escape the seccomp filter entirely.

---

### INV-SCMP-005: Filter inheritance is total — children are always equally or more constrained
**Core Invariant:**
```
∀ parent p, ∀ child c of p:
  filters(c) ⊇ filters(p)  // child has all of parent's filters, possibly more
```
**Source:** "Usage" section — "If fork/clone and execve are allowed by @prog, any child processes will be constrained to the same filters and system call ABI as the parent."

**Counterexample:** If a child process could shed its parent's seccomp filters, a sandboxed process could fork a child, have the child exec a shell, and escape the sandbox. The inheritance invariant prevents this: once a filter is installed, no descendant can remove it. The only way to escape is if the filter allows a syscall that permits privilege escalation (which is why NO_NEW_PRIVS is also required).

**Why this matters for bridge/orbit:** Bridge spawns child processes (orbit sessions) from a sandboxed parent. This invariant guarantees that orbit sessions inherit the bridge's seccomp constraints — orbit cannot accidentally or maliciously run with fewer restrictions than bridge itself. The sandbox is hermetically sealed across fork/exec boundaries.

---

### INV-SCMP-006: Architecture value must be checked before syscall number in any correct filter
**Core Invariant:**
```
∀ filter f that is safe against syscall-number-spoofing:
  first_instruction(f) checks seccomp_data.arch
```
**Source:** "Pitfalls" section — "The biggest pitfall to avoid during use is filtering on system call number without checking the architecture value. Why? On any architecture that supports multiple system call invocation conventions, the system call numbers may vary based on the specific invocation. If the numbers in the different calling conventions overlap, then checks in the filters may be abused. Always check the arch value!"

**Counterexample:** On x86-64, a process can make syscalls via the native x86-64 ABI (syscall numbers from /usr/include/asm/unistd_64.h) or via the x86 compatibility ABI (syscall numbers from unistd_32.h). Syscall number 4 is write() in x86-64 but stat() in x86. A filter that allows "syscall 4" intending to allow write() would also allow a 32-bit stat() call — potentially leaking file metadata the filter intended to block. Checking arch first and using arch-specific syscall tables prevents this overlap attack.

**Why this matters for bridge/orbit:** Bridge's seccomp BPF programs must include an architecture check as the first instruction. This invariant is not enforced by the kernel (the kernel allows architecturally-naive filters) — it is a correctness requirement that must be verified at code review and test time. A missing arch check is a sandbox bypass vulnerability.

---

### INV-SCMP-007: Multiple same-precedence return values resolve to most-recently-installed filter's data
**Core Invariant:**
```
∀ f_i, f_j ∈ installed_filters where i > j (f_i installed later):
  precedence(action(f_i, s)) = precedence(action(f_j, s)) ⇒
  SECCOMP_RET_DATA(s) = SECCOMP_RET_DATA(action(f_i, s))
```
**Source:** "Return values" section — "Precedence is only determined using the SECCOMP_RET_ACTION mask. When multiple filters return values of the same precedence, only the SECCOMP_RET_DATA from the most recently installed filter will be returned."

**Counterexample:** If two filters both return SECCOMP_RET_ERRNO with different errno values (e.g., -EPERM vs -EACCES), and the older filter's data were used, the sandbox developer's intent (the newer filter being the more specific, refined policy) would be overridden. The kernel chooses the most recently installed filter's data as the tiebreaker, giving predictable control to the filter installer.

**Why this matters for bridge/orbit:** Bridge may layer filters: a base deny-by-default filter then a per-workload allowlist filter. If both return ERRNO for a blocked syscall, bridge needs to know which errno value the process will see. This invariant gives deterministic semantics: the most recent filter's errno wins.

---

### INV-SCMP-008: seccomp notification fd reads/writes are synchronized (single-reader-safe, multi-reader-safe)
**Core Invariant:**
```
∀ notification_fd fd:
  reads(fd) are serialized ∧ writes(fd) are serialized
```
**Source:** "Userspace Notification" section — "Reads and writes to/from a filter fd are also synchronized, so a filter fd can safely have many readers."

**Counterexample:** Without synchronization, two supervisor threads reading from the same notification fd could race: both see the same notification, both respond, and the second response is applied to a different (or no) notification — corrupting the supervisor-target protocol. Kernel-level synchronization prevents this: each notification is delivered to exactly one reader, and each response is matched to exactly one notification via the id field.

**Why this matters for bridge/orbit:** If bridge uses SECCOMP_RET_USER_NOTIF for intercepting specific syscalls (e.g., mount()), the notification fd can be shared across bridge worker threads. This invariant guarantees correct delivery without bridge needing to implement its own mutual exclusion on the fd.

---

### INV-SCMP-009: actions_logged sysctl rejects SECCOMP_RET_ALLOW with EINVAL
**Core Invariant:**
```
∀ write w to /proc/sys/kernel/seccomp/actions_logged:
  "allow" ∈ tokens(w) ⇒ write returns -EINVAL
```
**Source:** "Sysctls / actions_logged" section — "The 'allow' string is not accepted in the actions_logged sysctl as it is not possible to log SECCOMP_RET_ALLOW actions. Attempting to write 'allow' to the sysctl will result in an EINVAL being returned."

**Counterexample:** If logging ALLOW actions were permitted, every allowed syscall would generate a log entry — flooding the log and making it useless for debugging. More subtly, it would create a false sense of audit completeness: an operator might think "all syscalls are logged" when in fact logging changes the timing characteristics of the system. The kernel rejects it explicitly.

**Why this matters for bridge/orbit:** When debugging seccomp filter policies, bridge operators may try to enable logging for all actions to trace syscall patterns. This invariant tells them that "allow" logging is impossible by design — they must use other mechanisms (e.g., auditd, bpftrace) to trace allowed syscalls.

---

### INV-SCMP-010: SECCOMP_RET_USER_NOTIF without attached listener returns -ENOSYS
**Core Invariant:**
```
∀ filter f returning SECCOMP_RET_USER_NOTIF for syscall s:
  ¬has_listener(f) ⇒ process(s) receives -ENOSYS
```
**Source:** "SECCOMP_RET_USER_NOTIF" section — "Results in a struct seccomp_notif message sent on the userspace notification fd, if it is attached, or -ENOSYS if it is not."

**Counterexample:** If the kernel blocked the syscall (returned an error other than ENOSYS) or silently hung the process when no listener was attached, a process whose supervisor died would become unrecoverable. ENOSYS is the correct failure mode: it tells the process "this syscall is not available" which is a standard, handleable error that most software already checks for. The process can degrade gracefully or exit, rather than hanging indefinitely.

**Why this matters for bridge/orbit:** Bridge's supervisor process must remain alive for sandboxed processes that use USER_NOTIF. If the supervisor crashes, sandboxed processes receive ENOSYS rather than hanging — they can fail safely. This invariant proves the fail-safe behavior.

---

## Notes

- **Not a sandbox:** The documentation explicitly states "System call filtering isn't a sandbox." Seccomp is a mechanism for minimizing kernel attack surface; complete sandboxing requires additional techniques (namespaces, LSMs, rlimits, etc.). Bridge/orbit use seccomp as one layer in a defense-in-depth strategy, not as the sole isolation mechanism.

- **vsyscall quirks:** On x86-64, vsyscall emulation interacts with seccomp in non-obvious ways. For SECCOMP_RET_TRACE, the syscall number can only be changed to -1 (skip), not to another valid syscall. The rip and rsp registers must not be modified by the tracer. Modern systems using vDSO are not affected.

- **Source trust level:** This is a linux-kernel primary source — the authoritative documentation for the seccomp subsystem. Trust level: HIGH. Equivalent to `standard` in the axioms trust taxonomy, but as a kernel-internal interface specification, it carries even higher weight than external standards because it defines the actual behavior, not just a specification.
