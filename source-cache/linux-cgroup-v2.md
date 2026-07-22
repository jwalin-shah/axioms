# oracle/linux-cgroup-v2 — Cgroup v2: controllers, resource distribution, no internal processes rule
Source: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
Date pulled: 2026-07-21
Source type: oracle-extract (authoritative kernel documentation)
Trust level: HIGH (canonical design doc; maintained by Tejun Heo, kernel.org)

## Extracted Invariants

### INV-CG-001: Every process belongs to exactly one cgroup
**Core Invariant:**
```
∀ p ∈ Processes, ∃! c ∈ Cgroups: p ∈ c
```
Every process in the system belongs to one and only one cgroup. cgroups form a tree structure and processes are the leaves (in domain mode). All threads of a process belong to the same cgroup (default, non-threaded mode).

**Source:** "Terminology" and "Processes" sections. "cgroups form a tree structure and every process in the system belongs to one and only one cgroup. All threads of a process belong to the same cgroup."

**Counterexample:** If a process belonged to two sibling cgroups, resource controllers would have conflicting views of its consumption, breaking the hierarchical distribution model. CPU and memory accounting would be non-deterministic.

**Why this matters for bridge/orbit:** Orbit spawns processes in sandboxed cgroups. The uniqueness guarantee ensures resource accounting for a spawned process is unambiguous. If orbit accidentally placed a process in multiple cgroups, it would violate this invariant and the kernel would reject it (the kernel enforces this).

---

### INV-CG-002: No Internal Process Constraint (domain mode)
**Core Invariant:**
```
∀ c ∈ NonRootCgroups, (∃ d ∈ DomainControllers: enabled(c, d)) ⇒ (∄ p ∈ Processes: p ∈ c)
```
Non-root cgroups can distribute domain resources to their children only when they don't have any processes of their own. Only domain cgroups which contain no processes can have domain controllers enabled in their `cgroup.subtree_control` files.

**Source:** "No Internal Process Constraint" section. "This guarantees that, when a domain controller is looking at the part of the hierarchy which has it enabled, processes are always only on the leaves. This rules out situations where child cgroups compete against internal processes of the parent."

**Counterexample:** If a parent cgroup had both processes and child cgroups with CPU controller enabled, the parent's own processes would compete with its children for CPU cycles. The kernel couldn't determine how to weight the parent's internal processes against the child cgroups. This was a known flaw in cgroup v1 that led to inconsistent behavior across controllers (cpu vs memory vs io handled it differently).

**Why this matters for bridge/orbit:** Orbit uses cgroup nesting for sandbox isolation. When orbit creates nested cgroups for resource control, it must ensure the intermediate cgroup (the parent) has no processes of its own — only the leaf cgroups should contain processes. Violating this would silently break resource isolation guarantees.

---

### INV-CG-003: Top-Down Enablement Constraint
**Core Invariant:**
```
∀ c ∈ NonRootCgroups, ∀ d ∈ Controllers: enabled(c, d) ⇒ enabled(parent(c), d)
```
A controller can be enabled in a non-root cgroup only if the parent has the controller enabled. Conversely, a controller can't be disabled in a parent if one or more children have it enabled. All non-root `cgroup.subtree_control` files can only contain controllers which are enabled in the parent's `cgroup.subtree_control` file.

**Source:** "Top-down Constraint" section. "Resources are distributed top-down and a cgroup can further distribute a resource only if the resource has been distributed to it from the parent."

**Counterexample:** If a child could enable a controller that its parent had not enabled, it could bypass the parent's resource distribution policy. The parent would be unable to control how much of the resource the child can access, breaking the hierarchical control model.

**Why this matters for bridge/orbit:** When orbit configures cgroup hierarchies for sandboxed processes, it must enable controllers at each level of the tree in top-down order. Skipping a level would cause the enable operation to fail. This is a structural constraint on how orbit must sequence cgroup setup.

---

### INV-CG-004: Restrictions are strictly tightening (hierarchical nesting)
**Core Invariant:**
```
∀ c₁, c₂ ∈ Cgroups: is_descendant(c₁, c₂) ⇒ restrictions(c₁) ⊆ restrictions(c₂)
```
When a controller is enabled on a nested cgroup, it always restricts the resource distribution further. The restrictions set closer to the root in the hierarchy cannot be overridden from further away. All controller behaviors are hierarchical.

**Source:** "What is cgroup?" section. "When a controller is enabled on a nested cgroup, it always restricts the resource distribution further. The restrictions set closer to the root in the hierarchy can not be overridden from further away."

**Counterexample:** If a child cgroup could set a higher memory.max than its parent, the parent's limit would be meaningless. The child could consume resources the parent had denied. This would break the delegation model where a parent delegates a subset of its resources to children.

**Why this matters for bridge/orbit:** Orbit's sandbox cgroups can only tighten restrictions, never loosen them. If orbit wants to give a child cgroup more resources, it must first ensure the parent has sufficient headroom. This is a fundamental constraint on dynamic resource adjustment.

---

### INV-CG-005: Memory ownership is static (no migration on process move)
**Core Invariant:**
```
∀ m ∈ MemoryAreas, ∀ p ∈ Processes: charged_to(m, cgroup_at_instantiation(m)) ∧
  (migrate(p, c₁, c₂) ⇒ still_charged_to(m, cgroup_at_instantiation(m)))
```
A memory area is charged to the cgroup which instantiated it and stays charged to that cgroup until the area is released. Migrating a process to a different cgroup doesn't move the memory usages it instantiated while in the previous cgroup to the new cgroup.

**Source:** "Memory Ownership" section. "A memory area is charged to the cgroup which instantiated it and stays charged to the cgroup until the area is released. Migrating a process to a different cgroup doesn't move the memory usages that it instantiated while in the previous cgroup to the new cgroup."

**Counterexample:** If memory followed the process on migration, a process could escape a memory.max limit by moving to a cgroup with a higher limit, carrying its memory with it. The old cgroup's accounting would be wrong, and the new cgroup's limit could be violated without the process allocating new memory.

**Why this matters for bridge/orbit:** When orbit relocates a process between sandbox cgroups, the process's existing memory allocations stay charged to the old cgroup. This means memory limits in the new cgroup only apply to future allocations. Orbit must account for this "memory debt" in the old cgroup when calculating resource headroom.

---

### INV-CG-006: Delegation containment (no cross-delegation moves)
**Core Invariant:**
```
∀ p ∈ DelegatedSubhierarchy(D), ∀ q ∈ Processes:
  migrate(q, src, dst) succeeds ∧ delegatee_has_write_access(D) ⇒
  (src ∈ D ∧ dst ∈ D)
```
A delegated sub-hierarchy is contained: processes can't be moved into or out of the sub-hierarchy by the delegatee. For user delegation, the writer must have write access to the `cgroup.procs` file of the common ancestor of source and destination cgroups. Since the common ancestor of any cross-boundary move is above the delegation point (where the delegatee lacks access), the move is rejected with -EACCES.

**Source:** "Delegation Containment" section. "A delegated sub-hierarchy is contained in the sense that processes can't be moved into or out of the sub-hierarchy by the delegatee."

**Counterexample:** Without this constraint, a less-privileged user delegated a cgroup subtree could pull processes from outside their delegation into their cgroups (potentially to starve them) or push their processes out (to escape resource limits). This would break the security boundary that delegation is meant to provide.

**Why this matters for bridge/orbit:** When bridge delegates a cgroup subtree to orbit for sandbox management, orbit cannot accidentally or maliciously move processes into or out of that subtree. This is a kernel-enforced security boundary that bridge can rely on. The containment is structural, not advisory.

---

### INV-CG-007: Allocation model -- no over-commitment
**Core Invariant:**
```
∀ c ∈ Cgroups, ∀ r ∈ AllocatableResources:
  Σ_{child ∈ children(c)} allocation(child, r) ≤ available(c, r)
```
Allocations can't be over-committed. The sum of the allocations of children cannot exceed the amount of resource available to the parent. This is in contrast to weights, limits, and protections which can be over-committed.

**Source:** "Resource Distribution Models / Allocations" section. "Allocations can't be over-committed - the sum of the allocations of children can not exceed the amount of resource available to the parent."

**Counterexample:** If a parent had 4 CPUs and two children each requested an allocation of 3 CPUs, the kernel cannot satisfy both. The configuration is invalid and must be rejected. If it were accepted, the kernel would have to choose which child gets shorted, violating the exclusivity guarantee of the allocation model.

**Why this matters for bridge/orbit:** When orbit uses cpuset partitions for CPU pinning, it must respect the non-overcommitment constraint. Attempting to allocate the same exclusive CPU to two sibling cgroups will be rejected by the kernel. Orbit must validate allocation sums before applying configuration.

---

### INV-CG-008: Cpuset exclusivity (one CPU to at most one child)
**Core Invariant:**
```
∀ cpu ∈ ExclusiveCPUs, ∀ parent ∈ Cgroups:
  |{child ∈ children(parent) : cpu ∈ exclusive(child)}| ≤ 1
```
For a parent cgroup, any one of its exclusive CPUs can only be distributed to at most one of its child cgroups. Having an exclusive CPU appear in two or more child cgroups is not allowed. A value that violates this exclusivity rule is rejected with a write error.

**Source:** "cpuset.cpus.exclusive" section. "For a parent cgroup, any one of its exclusive CPUs can only be distributed to at most one of its child cgroups. Having an exclusive CPU appearing in two or more of its child cgroups is not allowed (the exclusivity rule)."

**Counterexample:** If two sibling cgroups both claimed exclusive access to CPU 3, the kernel scheduler couldn't guarantee exclusive access to either. A task in cgroup A could be preempted by a task in cgroup B on CPU 3, violating the partition isolation guarantee.

**Why this matters for bridge/orbit:** Orbit uses cpuset partitions for real-time or latency-sensitive workloads. The exclusivity invariant is what makes partition isolation meaningful. If orbit incorrectly configures overlapping exclusive CPU sets, the kernel rejects the configuration — orbit must handle this error and adjust placement.

---

### INV-CG-009: Cpuset effective subset (child sees parent's effective set)
**Core Invariant:**
```
∀ c ∈ CpusetCgroups: cpuset.cpus.effective(c) ⊆ cpuset.cpus.effective(parent(c))
```
A cgroup's effective CPU set is always a subset of its parent's effective CPU set. The controller cannot use CPUs not allowed by its parent.

**Source:** "Cpuset" section. "The cpuset controller is hierarchical. That means the controller cannot use CPUs or memory nodes not allowed in its parent."

**Counterexample:** If a child could use a CPU not in the parent's effective set, the parent's cpuset configuration would be meaningless. The child would have access to compute resources the parent explicitly denied, breaking hierarchical resource control.

**Why this matters for bridge/orbit:** When orbit configures CPU pinning for a nested sandbox, the effective set is always the intersection of all ancestor constraints. Orbit can compute the effective set as `requested ∩ parent.effective` and should check that the result is non-empty before spawning processes.

---

### INV-CG-010: memory.min -- hard reclaim protection
**Core Invariant:**
```
∀ c ∈ Cgroups: usage(c) ≤ effective_min(c) ⇒ ¬reclaimed(c)
```
If the memory usage of a cgroup is within its effective min boundary, the cgroup's memory won't be reclaimed under any conditions. If there is no unprotected reclaimable memory available, the OOM killer is invoked instead.

**Source:** "memory.min" section. "Hard memory protection. If the memory usage of a cgroup is within its effective min boundary, the cgroup's memory won't be reclaimed under any conditions. If there is no unprotected reclaimable memory available, OOM killer is invoked."

**Counterexample:** If memory.min were violated (the kernel reclaimed memory from a cgroup within its min boundary), a workload with a hard memory guarantee could have its working set evicted, causing unpredictable latency or failure. This is a hard guarantee — the kernel would rather OOM-kill a process than violate it.

**Why this matters for bridge/orbit:** Orbit can use memory.min to guarantee a minimum memory footprint for critical sandbox processes. However, overcommitting memory.min (sum of children's mins exceeds parent's available) leads to the kernel proportionally reducing each child's effective min. Orbit must track effective min, not just configured min.

---

### INV-CG-011: memory.high -- throttle, never OOM
**Core Invariant:**
```
∀ c ∈ Cgroups: usage(c) > memory.high(c) ⇒ throttled(c) ∧ ¬OOM(c)
```
Going over the high limit never invokes the OOM killer. Instead, the processes of the cgroup are throttled and put under heavy reclaim pressure. Under extreme conditions the limit may be breached, but the kernel will not kill processes.

**Source:** "memory.high" section. "Going over the high limit never invokes the OOM killer and under extreme conditions the limit may be breached."

**Counterexample:** If memory.high triggered OOM kills, it would be indistinguishable from memory.max. The whole point of the high/max distinction is that high is a soft throttle (allowing graceful degradation and external intervention) while max is the hard kill boundary. Confusing the two would eliminate the two-tier defense against memory exhaustion.

**Why this matters for bridge/orbit:** Bridge can use memory.high as a first-line defense — when a sandbox process exceeds its high watermark, it gets throttled but not killed. Bridge can then monitor and decide whether to increase the limit or terminate. Memory.max is the last resort. This two-tier model gives bridge operational flexibility.

---

### INV-CG-012: memory.max -- hard limit, OOM on failure
**Core Invariant:**
```
∀ c ∈ Cgroups: usage(c) ≥ memory.max(c) ∧ ¬reclaimable(c) ⇒ OOM(c)
```
If a cgroup's memory usage reaches the hard limit and can't be reduced, the OOM killer is invoked in the cgroup. Under certain circumstances, usage may go over the limit temporarily (during the reclaim window).

**Source:** "memory.max" section. "Memory usage hard limit. If a cgroup's memory usage reaches this limit and can't be reduced, the OOM killer is invoked in the cgroup."

**Counterexample:** If the kernel allowed a cgroup to permanently exceed its memory.max without OOM, the limit would be advisory rather than a hard constraint. A memory-leaking process could consume unbounded memory, starving other cgroups and eventually the entire system.

**Why this matters for bridge/orbit:** This is the containment boundary for bridge's sandbox processes. If a sandbox process leaks memory, it will be OOM-killed within its own cgroup — the OOM killer won't cross cgroup boundaries. Bridge can rely on memory.max to contain memory-hungry workloads without risking system-wide OOM.

---

### INV-CG-013: oom.group -- atomic kill
**Core Invariant:**
```
∀ c ∈ Cgroups: memory.oom.group(c) = 1 ⇒
  (OOM(c) ⇒ (∀ p ∈ subtree(c): killed(p) ∨ oom_protected(p)))
```
If memory.oom.group is set, all tasks belonging to the cgroup or its descendants are killed together or not at all. Tasks with OOM protection (oom_score_adj = -1000) are never killed. If the OOM killer is invoked in a cgroup, it will not kill any tasks outside of that cgroup, regardless of ancestor memory.oom.group values.

**Source:** "memory.oom.group" section. "Determines whether the cgroup should be treated as an indivisible workload by the OOM killer. If set, all tasks belonging to the cgroup or to its descendants are killed together or not at all."

**Counterexample:** Without oom.group, a multi-process workload in a cgroup could be partially killed — one process OOM-killed while others survive. This leaves the workload in an inconsistent state (e.g., a database with a killed writer but live readers). The oom.group flag prevents this partial-failure mode.

**Why this matters for bridge/orbit:** Orbit spawns multi-process workloads within a single cgroup. If any process in the group hits memory pressure, orbit may want atomic kill-or-survive semantics. Setting oom.group ensures the workload is either fully alive or fully dead, preventing the inconsistent state that partial kills create.

---

### INV-CG-014: Thread mode is irreversible
**Core Invariant:**
```
∀ c ∈ Cgroups: type(c) = threaded ⇒ type(c) = threaded forever
```
Once a cgroup is made threaded (by writing "threaded" to cgroup.type), it can't be made a domain cgroup again. The operation is a single-direction transition.

**Source:** "Threads" section. "Once threaded, the cgroup can't be made a domain again."

**Counterexample:** If a threaded cgroup could revert to domain mode, its children (which might be threaded, domain-invalid, or contain scattered threads) would be in an undefined state. The kernel's resource domain model for that subtree would be inconsistent, potentially causing resource accounting bugs.

**Why this matters for bridge/orbit:** If orbit uses threaded mode for fine-grained thread-level resource control, it must commit to that decision permanently for that cgroup. There is no undo. Orbit should gate thread-mode transitions with an explicit confirmation that the cgroup will never need domain controllers again.

---

### INV-CG-015: Dying cgroup is immutable and terminal
**Core Invariant:**
```
∀ c ∈ Cgroups: dying(c) ⇒ (∄ p ∈ Processes: migrate(p, _, c)) ∧ ¬revive(c)
```
A process can't enter a dying cgroup under any circumstances, and a dying cgroup can't revive. A dying cgroup can consume system resources not exceeding limits that were active at the moment of deletion.

**Source:** "cgroup.stat" section. "A process can't enter a dying cgroup under any circumstances, a dying cgroup can't revive. A dying cgroup can consume system resources not exceeding limits, which were active at the moment of cgroup deletion."

**Counterexample:** If a process could enter a dying cgroup, it would be orphaned when the cgroup is destroyed. If a dying cgroup could revive, the deletion semantics would be nondeterministic — a user removing a cgroup directory couldn't rely on the cgroup actually going away.

**Why this matters for bridge/orbit:** When orbit tears down a sandbox cgroup, it enters a dying state. During this window, orbit must ensure no new processes are spawned into it. The kernel enforces this, but orbit should also avoid the attempt, as it would fail with an error. The dying-period resource consumption is bounded by the limits at deletion time.

---

### INV-CG-016: Controller enable/disable is atomic
**Core Invariant:**
```
∀ c ∈ Cgroups, ∀ ops ∈ ControllerOperations: |ops| > 1 ⇒
  (all_succeed(ops) ∨ all_fail(ops))
```
When multiple controller enable/disable operations are specified in a single write to `cgroup.subtree_control`, either they all succeed or all fail.

**Source:** "Enabling and Disabling" section. "When multiple operations are specified as above, either they all succeed or fail."

**Counterexample:** If partial success were allowed, a write enabling "+cpu +memory" could succeed for cpu but fail for memory, leaving the cgroup in an unintended intermediate state. The user would have to check which controllers were actually enabled and retry, creating a fragile and race-prone interface.

**Why this matters for bridge/orbit:** When orbit configures multiple controllers for a cgroup (e.g., cpu + memory + io for a sandbox), it can batch them in a single write and rely on atomic success/failure. If the write fails, orbit knows no controllers were partially enabled — it can retry or report the error without cleanup.

---

### INV-CG-017: Fork obeys PID limits (not migration)
**Core Invariant:**
```
∀ c ∈ Cgroups: pids.current(c) > pids.max(c) is possible via migration or limit-lowering,
  but fork()/clone() ⇒ (pids.current(c) < pids.max(c) ∨ returns -EAGAIN)
```
It is possible to have pids.current > pids.max by setting the limit below current or migrating processes in. However, fork() and clone() will return -EAGAIN if the creation of a new process would cause a cgroup PID policy to be violated.

**Source:** "PID" section. "Organisational operations are not blocked by cgroup policies, so it is possible to have pids.current > pids.max. ... However, it is not possible to violate a cgroup PID policy through fork() or clone()."

**Counterexample:** If pids.max were enforced at migration time, moving a process into a cgroup already at its PID limit would fail. The kernel explicitly allows this (the limit is a "soft cap" that only blocks new process creation). If fork() were allowed past the limit, a fork bomb inside a cgroup would escape PID containment.

**Why this matters for bridge/orbit:** Orbit can use pids.max to prevent fork bombs in sandbox cgroups. The limit only blocks new process creation, not migration. If orbit needs to enforce a hard process count (including migration), it must do its own admission control check before migrating processes, since the kernel won't block it.

---

### INV-CG-018: Freezer is hierarchical and OR-composed
**Core Invariant:**
```
∀ c ∈ Cgroups: frozen(c) ⇔ (frozen_self(c) ∨ (∃ a ∈ ancestors(c): frozen(a)))
```
A cgroup can be frozen either by its own settings or by settings of any ancestor cgroup. If any ancestor cgroup is frozen, the cgroup will remain frozen. The freeze is hierarchical: writing "1" to cgroup.freeze causes freezing of the cgroup and all descendant cgroups.

**Source:** "cgroup.freeze" section. "A cgroup can be frozen either by its own settings, or by settings of any ancestor cgroups. If any of ancestor cgroups is frozen, the cgroup will remain frozen."

**Counterexample:** If freezing were not hierarchical, freezing a parent cgroup would leave child cgroups' processes running. The parent's freeze would be meaningless — its children would continue consuming CPU and making progress. The OR-composition means any ancestor freeze is sufficient to stop all descendant processes.

**Why this matters for bridge/orbit:** Orbit can freeze an entire sandbox subtree by freezing the root cgroup of that subtree. Individual child cgroups cannot override the freeze. This is a powerful containment primitive — orbit can stop all processes in a sandbox with a single write, regardless of what the sandbox processes are doing.

---

### INV-CG-019: Cgroup kill is atomic and migration-safe
**Core Invariant:**
```
∀ c ∈ Cgroups: write("1", cgroup.kill(c)) ⇒
  (∀ p ∈ subtree(c): eventually_receives_SIGKILL(p))
```
Writing "1" to cgroup.kill causes the cgroup and all descendant cgroups to be killed via SIGKILL. Killing a cgroup tree deals with concurrent forks appropriately and is protected against migrations.

**Source:** "cgroup.kill" section. "Killing a cgroup tree will deal with concurrent forks appropriately and is protected against migrations."

**Counterexample:** If killing were not migration-safe, a process could escape SIGKILL by migrating to a sibling cgroup during the kill operation. If forks were not handled, a process could fork a child after the kill signal was sent, leaving an orphaned process that escapes the kill.

**Why this matters for bridge/orbit:** When bridge needs to forcefully terminate a sandbox, cgroup.kill provides a reliable, race-free mechanism. It is stronger than iterating PIDs and sending signals individually, which would be vulnerable to PID reuse and fork races. Orbit can rely on cgroup.kill to clean up a sandbox regardless of what the sandbox processes are doing.

---

### INV-CG-020: Writeback cgroup ownership is inode-based (not page-based)
**Core Invariant:**
```
∀ inode ∈ Inodes: ∃! c ∈ Cgroups: owner(inode, c) ∧
  ∀ bio ∈ WritebackIOs(inode): attributed_to(bio, c)
```
For writeback, an inode is assigned to a cgroup and all IO requests to write dirty pages from the inode are attributed to that cgroup. Memory tracking is per-page, but writeback is per-inode. Foreign pages (pages charged to a different cgroup than the inode's owner) are tracked, and if a foreign cgroup becomes the majority, the inode ownership switches.

**Source:** "Writeback" section. "Memory is tracked per page while writeback per inode. For the purpose of writeback, an inode is assigned to a cgroup and all IO requests to write dirty pages from the inode are attributed to that cgroup."

**Counterexample:** If writeback attribution were per-page (matching memory tracking), every writeback bio would need to be split by cgroup ownership, which is impractical at the block layer. The inode-based model is an approximation that works for single-writer workloads but breaks down when multiple cgroups write to the same file. In the multi-writer case, a "significant portion of IOs are likely to be attributed incorrectly."

**Why this matters for bridge/orbit:** If orbit runs multiple sandbox processes that write to shared files, the IO attribution for writeback will be incorrect — all IO for that inode goes to whichever cgroup "owns" it. Orbit should avoid shared-file write patterns across cgroup boundaries if accurate IO accounting matters.

---

## Summary Statistics

- **Total invariants extracted:** 20
- **Hard structural invariants (kernel-enforced):** 1-6, 8-9, 14-17, 19
- **Soft guarantees (design contract, not always enforced):** 7, 10-13, 18, 20
- **Falsifiable claims:** All 20 — each has a specific counterexample
- **Relevance to bridge/orbit:** All 20 — cgroup v2 is the sandbox mechanism orbit uses

## Key Themes

1. **Hierarchical control is the organizing principle.** Every invariant (top-down, no-internal-process, restriction-tightening) derives from the tree structure. Resources flow down; restrictions tighten; processes are leaves.

2. **Memory is sticky.** Static memory ownership (INV-CG-005) is the most surprising invariant — it means cgroup migration is not a full resource transfer. Process migration moves the process but not its memory history.

3. **The kernel is deliberate about enforcement gaps.** PID limits allow breach via migration but block fork (INV-CG-017). The dying state allows residual resource consumption (INV-CG-015). These are documented design choices, not bugs.

4. **Delegation is a security boundary, not just a namespace convenience.** The containment invariant (INV-CG-006) is enforced by the kernel at the VFS layer, not by userspace policy.

5. **Two-tier defense (high/max, low/min) is a pattern.** Memory, swap, and IO all use this pattern: soft boundary for throttling/warning, hard boundary for rejection/kill. This gives management agents (like bridge) operational flexibility.