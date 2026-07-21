# oracle/linux-kernel
Source: Linux kernel headers (include/uapi/linux/seccomp.h), man-pages (epoll(7), namespaces(7), capabilities(7)), kernel documentation (cgroup-v2.rst), kernel source (fs/io_uring.c)
Date pulled: 2026-07-21

## Contents
1. Seccomp Filter Architecture
2. Cgroup Hierarchy & Resource Isolation
3. Epoll Edge-Triggered vs Level-Triggered
4. io_uring Submission/Completion Ordering
5. Namespace Isolation Guarantees
6. Capability Model

---

## 1. Seccomp Filter Architecture

### INV-LNX-SEC-001: Seccomp Action Ordering
**Core Invariant:**
```
∀ret_a, ret_b ∈ SECCOMP_RET_ACTIONS:
  min_t(s32, ret_a, ret_b) selects the least permissive action
```
**Source:** linux/uapi/linux/seccomp.h, seccomp man-page
**Counterexample:** If SECCOMP_RET_KILL_PROCESS (0x80000000U, negative s32) is not the minimum value when composed with any other action, the most restrictive filter would not win.

### INV-LNX-SEC-002: Action Value Partitioning
**Core Invariant:**
```
∀ret ∈ SECCOMP_RET_VALUE:
  action = ret & SECCOMP_RET_ACTION_FULL   // 0xffff0000U
  data   = ret & SECCOMP_RET_DATA          // 0x0000ffffU
  action ∈ {KILL_PROCESS, KILL_THREAD, TRAP, ERRNO, USER_NOTIF, TRACE, LOG, ALLOW}
```
**Source:** linux/uapi/linux/seccomp.h
**Counterexample:** A return value with both action and data overlapping in the same 16-bit range would be ambiguous.

### INV-LNX-SEC-003: Filter Composition Monotonicity
**Core Invariant:**
```
∀filters F = {f_1, ..., f_n}: effective_action = min(s32)({f_i.action | f_i ∈ F})
```
**Source:** Linux kernel seccomp(2) man-page
**Counterexample:** If filters were averaged or maxed rather than min-composed, a permissive filter could override a restrictive one.

### INV-LNX-SEC-004: Architecture Binding
**Core Invariant:**
```
∀seccomp_data d:
  d.arch ∈ ARCH_* values (from linux/audit.h)
  d.arch determines syscall number namespace (e.g., x86_64 vs i386 compat)
```
**Source:** struct seccomp_data definition, seccomp(2)
**Counterexample:** A filter not checking the arch field could match x86_64 syscall numbers against i386 calls, creating a bypass.

### INV-LNX-SEC-005: TSYNC Atomicity
**Core Invariant:**
```
∀SECCOMP_FILTER_FLAG_TSYNC set:
  filter applies atomically to all threads in the thread group
```
**Source:** seccomp(2) man-page
**Counterexample:** If TSYNC were non-atomic, a race window could leave some threads unfiltered.

---

## 2. Cgroup Hierarchy & Resource Isolation

### INV-LNX-CGRP-001: Unified Hierarchy
**Core Invariant:**
```
∀process p: exactly one cgroup v2 hierarchy contains p
  (no process belongs to multiple hierarchies)
```
**Source:** kernel.org cgroup-v2 documentation
**Counterexample:** A process belonging to two separate controller hierarchies (as in v1) would allow double-counting of resources.

### INV-LNX-CGRP-002: No Internal Processes
**Core Invariant:**
```
∀cgroup c:
  (|children(c)| > 0) ⇒ |processes(c)| = 0
```
**Source:** cgroup-v2.rst, "no internal process constraint"
**Counterexample:** A process running in a parent cgroup that also has child cgroups would have ambiguous resource accounting (counted in both parent and child).

### INV-LNX-CGRP-003: Hierarchical Resource Accounting
**Core Invariant:**
```
∀cgroup c:
  usage(c) = usage_self(c) + Σ(usage(child) for child in children(c))
```
**Source:** cgroup-v2.rst
**Counterexample:** If child usage is not propagated to parent, the parent's resource limits could be exceeded without detection.

### INV-LNX-CGRP-004: Controller Inheritance
**Core Invariant:**
```
∀cgroup c, controller ctrl:
  ctrl_enabled(c) ⇒ ctrl_enabled(parent(c))
```
**Source:** cgroup-v2.rst
**Counterexample:** A child cgroup enabling a controller that its parent has disabled would bypass the parent's resource policy.

### INV-LNX-CGRP-005: Thread Mode Domain Isolation
**Core Invariant:**
```
∀cgroup c:
  threaded(c) ⇒ (∀sibling s: threaded(s) ∨ domain(s))
  ∧ threads within a thread-group are confined to threaded subtrees
```
**Source:** cgroup-v2.rst, "threaded" vs "domain" mode
**Counterexample:** A thread moved to a domain cgroup in a different thread-group would corrupt per-thread resource accounting.

---

## 3. Epoll Edge-Triggered vs Level-Triggered Semantics

### INV-LNX-EPOLL-001: Level-Triggered Persistence
**Core Invariant:**
```
∀fd ∈ interest_list(epfd), LT mode:
  fd.ready ∧ ¬depleted(fd) ⇒ epoll_wait returns fd on every call
```
**Source:** epoll(7) man-page
**Counterexample:** If LT epoll stops reporting a non-empty fd after one event, the application would never drain remaining data.

### INV-LNX-EPOLL-002: Edge-Triggered Only-on-Change
**Core Invariant:**
```
∀fd ∈ interest_list(epfd), ET mode:
  epoll_wait returns fd on state change only
  ¬(fd.ready ∧ ¬depleted(fd) ∧ ¬new_data) ⇒ fd NOT returned
```
**Source:** epoll(7) man-page, canonical pipe example
**Counterexample:** An ET fd returning readiness when no new data arrived would cause a spurious wakeup that blocks on read (EAGAIN loop hang).

### INV-LNX-EPOLL-003: EAGAIN Drain Requirement (ET)
**Core Invariant:**
```
∀ET fd:
  on epoll_wait(fd) event ⇒ loop read/write until EAGAIN before next epoll_wait
```
**Source:** epoll(7) man-page, Usage Rules
**Counterexample:** A partial read followed by epoll_wait would block permanently because the ET event was already consumed and no new data arrived.

### INV-LNX-EPOLL-004: One-Wakeup for Shared ET FD
**Core Invariant:**
```
∀epfd, ∀threads T = {t_1, ..., t_n} blocked on epoll_wait(epfd):
  |{t | t wakes for single ET fd event}| ≤ 1
```
**Source:** epoll(7) man-page, "Thundering herd" avoidance
**Counterexample:** If all N threads wake for the same single-byte arrival, N-1 threads would wastefully context-switch and find EAGAIN.

### INV-LNX-EPOLL-005: Open File Description Uniqueness
**Core Invariant:**
```
∀fd ∈ interest_list(epfd):
  key = (fd_number, open_file_description_ptr)
  duplicate (fd_number, ofd) → EEXIST
  dup() creates distinct ofd → allowed as separate entry
```
**Source:** epoll(7) man-page
**Counterexample:** Registering the same (fd, ofd) pair twice would create duplicate events without EEXIST rejection.

### INV-LNX-EPOLL-006: Self-Poll Prohibition
**Core Invariant:**
```
epoll_ctl(epfd, EPOLL_CTL_ADD, epfd, ...) → EINVAL
```
**Source:** epoll(7) man-page
**Counterexample:** An epoll fd waiting on itself would deadlock on event delivery.

---

## 4. io_uring Submission/Completion Ordering

### INV-LNX-IOU-001: No Completion Ordering Guarantee
**Core Invariant:**
```
∀submission_order SQEs:
  completion_order is ANY permutation of the submitted SQEs
  (kernel may complete requests in any order)
```
**Source:** io_uring(7) man-page, "Completions are not ordered"
**Counterexample:** Assuming SQE[0] completes before SQE[1] would produce incorrect results when completions arrive out-of-order.

### INV-LNX-IOU-002: user_data Correlation
**Core Invariant:**
```
∀submission sqe:
  cqe.user_data = sqe.user_data
  (user_data field is the sole correlation between SQE and CQE)
```
**Source:** io_uring(7) man-page
**Counterexample:** Using implicit ordering instead of user_data to match completions would fail when ordering is reversed.

### INV-LNX-IOU-003: Memory Barrier Ordering (SQ)
**Core Invariant:**
```
∀SQE submission:
  smp_wmb() or smp_store_release(tail) between filling SQEs and updating tail
  ∧ smp_load_acquire(head) or smp_rmb() before reading new SQ entries
```
**Source:** fs/io_uring.c, io_uring(7) man-page
**Counterexample:** Without the write barrier, the kernel may see uninitialized SQE data when it observes the tail update.

### INV-LNX-IOU-004: Memory Barrier Ordering (CQ)
**Core Invariant:**
```
∀CQE consumption:
  smp_rmb() or smp_load_acquire(tail) before reading CQEs
  ∧ smp_mb() or smp_store_release(head) before updating CQ head
```
**Source:** fs/io_uring.c
**Counterexample:** Without the read barrier, the application may read stale CQE data before the kernel's writes are visible.

### INV-LNX-IOU-005: Ring Ownership Partition
**Core Invariant:**
```
SQ head  → Kernel  | SQ tail  → Application
CQ head  → Application | CQ tail → Kernel
```
**Source:** fs/io_uring.c, struct io_rings
**Counterexample:** If the application writes SQ head or CQ tail, it would corrupt the kernel's bookkeeping.

### INV-LNX-IOU-006: SQPOLL Wakeup Ordering
**Core Invariant:**
```
∀IORING_SETUP_SQPOLL mode:
  after updating SQ tail → smp_mb() → check IORING_SQ_NEED_WAKEUP
```
**Source:** io_uring(7) man-page
**Counterexample:** Checking NEED_WAKEUP before the memory barrier may see the flag before the kernel observes the new tail, causing missed wakeups.

---

## 5. Namespace Isolation Guarantees

### INV-LNX-NS-001: PID Namespace Hierarchy & Visibility
**Core Invariant:**
```
∀PID namespaces p, q:
  p is ancestor of q ⇒ processes(p) ⊇ processes(q)
  ¬(p is ancestor of q) ⇒ processes(p) ∩ processes(q) = ∅
```
**Source:** namespaces(7) man-page, PID namespace documentation
**Counterexample:** A child namespace seeing processes in a sibling or parent namespace would break isolation.

### INV-LNX-NS-002: PID 1 Reaper Invariant
**Core Invariant:**
```
∀PID namespace n:
  first process in n → pid = 1
  pid1_process is orphan reaper for all children(n)
  SIGKILL/SIGSTOP from parent(n) still works on pid1_process
```
**Source:** namespaces(7), pid_namespaces(7)
**Counterexample:** If PID 1 in a namespace does not reap orphans, zombie processes would accumulate unreaped.

### INV-LNX-NS-003: Network Device Singularity
**Core Invariant:**
```
∀physical network device d:
  |{netns | d ∈ devices(netns)}| = 1
```
**Source:** namespaces(7), network_namespaces(7)
**Counterexample:** A physical NIC appearing in two namespaces simultaneously would allow cross-namespace packet injection.

### INV-LNX-NS-004: Network Device Retirement
**Core Invariant:**
```
∀physical network device d, ∀netns n:
  last_process(n) terminates ∧ d ∈ devices(n) ⇒ d moves to root_netns
```
**Source:** namespaces(7) man-page
**Counterexample:** A physical device disappearing when a namespace exits would strand hardware.

### INV-LNX-NS-005: unshare(CLONE_NEWPID) Deferred Entry
**Core Invariant:**
```
unshare(CLONE_NEWPID):
  calling_process ∉ new_pidns
  children(fork() after unshare) ∈ new_pidns
```
**Source:** namespaces(7) man-page
**Counterexample:** If unshare(CLONE_NEWPID) immediately changed the caller's PID namespace, getpid() would return a value inconsistent with /proc.

### INV-LNX-NS-006: Mount Namespace Independence
**Core Invariant:**
```
∀mount namespaces a, b:
  mount(a) ≠ mount(b) unless explicitly shared via mount propagation
```
**Source:** namespaces(7), mount_namespaces(7)
**Counterexample:** Unmounting a filesystem in one namespace affecting another would violate isolation.

---

## 6. Capability Model

### INV-LNX-CAP-001: Privilege Escalation Boundary
**Core Invariant:**
```
∀process p:
  effective(p) ⊆ permitted(p) ⊆ inheritable(p) ∪ bounding(p) ∪ ambient(p)
  new_effective ⊆ new_permitted ⊆ (permitted ∩ bounding) ∪ ambient
```
**Source:** capabilities(7) man-page
**Counterexample:** A process gaining a capability outside its permitted set would violate the monotonicity of privilege.

### INV-LNX-CAP-002: execve Capability Reset
**Core Invariant:**
```
∀execve() of non-setuid program:
  effective' = ambient
  permitted' = (permitted ∩ bounding) ∪ ambient
  inheritable' = inheritable
```
**Source:** capabilities(7) man-page
**Counterexample:** If capabilities persisted across exec without the inheritable/ambient mechanism, a compromised binary could inherit admin capabilities.

### INV-LNX-CAP-003: User Namespace Capability Escalation
**Core Invariant:**
```
∀user namespace n:
  CAP_NET_RAW in n → raw socket access only within n's network namespace
  CAP_SYS_ADMIN in n → admin rights only within n's scope
```
**Source:** user_namespaces(7), capabilities(7)
**Counterexample:** CAP_NET_RAW in a non-initial user namespace granting the ability to craft raw packets in the host network namespace would violate isolation.

### INV-LNX-CAP-004: Ambient Capability Inheritance
**Core Invariant:**
```
∀ambient capability c:
  c ∈ permitted ∧ c ∈ inheritable
  ∧ execve preserves c across all non-setuid binary executions
```
**Source:** capabilities(7) man-page
**Counterexample:** An ambient capability that is not in both permitted and inheritable sets would be lost on exec.

### INV-LNX-CAP-005: Bounding Set as Upper Bound
**Core Invariant:**
```
∀capability c:
  c ∉ bounding ⇒ c ∉ permitted' after any execve
```
**Source:** capabilities(7) man-page
**Counterexample:** A capability removed from the bounding set becoming available after exec would defeat the bounding set's purpose as a hard ceiling.
