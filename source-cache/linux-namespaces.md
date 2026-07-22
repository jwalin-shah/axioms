# oracle/linux-namespaces — Namespace types and isolation guarantees
Source: https://www.kernel.org/doc/html/latest/admin-guide/namespaces/index.html (and sub-pages)
Date pulled: 2026-07-21
Kernel version: 7.2.0-rc4 (as rendered on kernel.org)

## Pages fetched

1. `index.html` — TOC only; links to two sub-pages
2. `compatibility-list.html` — Cross-namespace compatibility matrix and known breakage
3. `resource-control.html` — User namespace resource exhaustion risks and mitigations

## Summary

The kernel.org admin-guide namespace documentation is thin. The compatibility
list is the richest source of concrete invariants. The resource-control page is
a single-paragraph advisory. No deep-dive on namespace implementation semantics
is present in this part of the kernel docs — for that, see the man pages
(`namespaces(7)`, `user_namespaces(7)`, `pid_namespaces(7)`, etc.) and the
kernel source under `kernel/nsproxy.c`, `kernel/user_namespace.c`, and
`kernel/pid_namespace.c`.

---

## Extracted Invariants

### INV-LNXNS-001: Namespace-scoped IDs are not valid across namespace boundaries
**Core Invariant:**
```
For any namespace-scoped identifier id obtained in namespace N,
and any namespace M where M != N:
  resolve(id, M) is undefined — it may resolve to a different object,
  or to no object.
```
**Source:** compatibility-list.rst, item 1
**Source text:** "this ID is only valid within the namespace it was obtained in
and may refer to some other object in another namespace"
**Scope:** IPC IDs (semaphore IDs, message queue IDs, shared memory IDs) and
PID namespace IDs (process IDs, process group IDs).
**Counterexample:** Process A in PID namespace N1 obtains PID 42 and writes it
to a file on a shared filesystem. Process B in PID namespace N2 reads PID 42
from that file and sends a signal — it signals the wrong process (or no
process at all).
**Why this matters for bridge/orbit:** Bridge spawns orbit processes in
separate PID namespaces. Any PID or IPC ID leaked across the namespace boundary
(e.g., via a shared filesystem mount, a log line, or an IPC channel) is a
cross-namespace reference bug. The sandbox must ensure that namespace-scoped
identifiers never cross the boundary.

### INV-LNXNS-002: Cross-namespace ID exposure via shared resources is prohibited
**Core Invariant:**
```
For any two tasks t1 in namespace N1 and t2 in namespace N2 where N1 != N2,
and any shared resource R (filesystem, IPC shmem/message queue):
  t1 must not expose a namespace-scoped ID obtained in N1 to t2 via R.
```
**Source:** compatibility-list.rst, item 1
**Source text:** "tasks shouldn't try exposing this ID to some other task
living in a different namespace via a shared filesystem or IPC shmem/message"
**Scope:** Applies when IPC or PID namespaces differ between tasks while they
share a filesystem or IPC channel.
**Counterexample:** Two containers share a tmpfs mount. Container A creates a
System V semaphore with ID 7 in its IPC namespace, writes "7" to a file on the
tmpfs. Container B reads "7" and calls semctl(7, ...) — it operates on a
different semaphore (or gets EINVAL).
**Why this matters for bridge/orbit:** If bridge and orbit share any filesystem
mount (even /tmp) or any IPC channel, and either side obtains a PID or IPC ID
from its own namespace, exposing that ID to the other side is a correctness
bug. The sandbox architecture must ensure that no shared resource carries
namespace-scoped identifiers.

### INV-LNXNS-003: User namespace UID isolation for VFS (INTENDED BUT BROKEN)
**Core Invariant (intended):**
```
For any two user namespaces U1 and U2 where U1 != U2,
and any numeric UID u:
  VFS permission check for uid=u in U1 must not grant access to
  resources owned by uid=u in U2.
```
**Source:** compatibility-list.rst, item 2
**Source text:** "two equal user IDs in different user namespaces should not be
equal from the VFS point of view"
**Status:** **BROKEN** — the doc explicitly states "But currently this is not
so." This is a known kernel limitation.
**Counterexample:** User 1000 in user namespace A can access files owned by
user 1000 in user namespace B if the namespaces share a filesystem, because the
kernel does not properly distinguish them in VFS permission checks.
**Why this matters for bridge/orbit:** If bridge runs in a different user
namespace than orbit, and they share any filesystem, the UID-based file access
controls are unreliable. This is a known kernel bug — the sandbox must not
rely on user-namespace UID distinctions for filesystem isolation. Use mount
namespaces or separate filesystem trees instead.

### INV-LNXNS-004: User namespace UID isolation for IPC (INTENDED BUT BROKEN)
**Core Invariant (intended):**
```
For any two user namespaces U1 and U2 where U1 != U2,
and any numeric UID u, and any IPC object O:
  if O is owned by (u, U1), then a process with credentials (u, U2)
  must not be able to access O.
```
**Source:** compatibility-list.rst, item 2
**Source text:** "two users from different user namespaces should not access
the same IPC objects even having equal UIDs"
**Status:** **BROKEN** — same as INV-LNXNS-003. The doc states "currently this
is not so."
**Counterexample:** Two processes in different user namespaces but both running
as UID 1000 can access each other's IPC objects (semaphores, message queues,
shared memory) if the IPC namespace is shared.
**Why this matters for bridge/orbit:** If bridge and orbit share an IPC
namespace but use different user namespaces, IPC isolation by UID is broken.
The sandbox must ensure that either (a) IPC namespaces are also separate, or
(b) no reliance on UID-based IPC access control exists.

### INV-LNXNS-005: User namespaces without resource limits are unsafe for untrusted code
**Core Invariant:**
```
For any system S that enables user namespaces and hosts untrusted users:
  S must enable memory control groups (cgroups) to bound per-user
  resource consumption.
  Without this bound, a user can exhaust kernel resources by
  creating objects that lack per-instance limits or whose limits
  are bypassed by UID switching.
```
**Source:** resource-control.rst
**Source text:** "On a system where the admins don't trust their users or their
users' programs, user namespaces expose the system to potential misuse of
resources. In order to mitigate this, we recommend that admins enable memory
control groups on any system that enables user namespaces."
**Counterexample:** A malicious user creates a new user namespace, switches
UIDs repeatedly, and allocates kernel objects (e.g., network namespaces, mount
namespaces) that have no per-user limits. Without memory cgroups, the kernel
memory is exhausted — a DoS attack.
**Why this matters for bridge/orbit:** Orbit spawns untrusted code in
sandboxes. If user namespaces are enabled for isolation, memory cgroups must
also be configured or the sandbox is not actually resource-safe. The spawn
pipeline must verify cgroup configuration before declaring a sandbox "ready."

---

## Namespace Types Referenced

| Namespace | What it isolates | Flag | Kernel constant |
|-----------|-----------------|------|-----------------|
| UTS | hostname, domainname | CLONE_NEWUTS | CLONE_NEWUTS |
| IPC | System V IPC, POSIX message queues | CLONE_NEWIPC | CLONE_NEWIPC |
| VFS (Mount) | filesystem mount points | CLONE_NEWNS | CLONE_NEWNS |
| PID | process IDs | CLONE_NEWPID | CLONE_NEWPID |
| User | UID/GID mappings | CLONE_NEWUSER | CLONE_NEWUSER |
| Net | network devices, IPs, routing tables | CLONE_NEWNET | CLONE_NEWNET |

Note: The kernel.org docs use "VFS" to refer to the mount namespace (CLONE_NEWNS).

---

## Known Gaps in This Source

1. **No semantics for cgroup, time, or sysvipc namespaces** — these were added
   after this documentation was written. The cgroup namespace (CLONE_NEWCGROUP)
   and time namespace (CLONE_NEWTIME) are not mentioned.
2. **No implementation details** — no discussion of `nsproxy`, `struct
   ns_common`, or the namespace lifecycle (creation, refcounting, cleanup).
3. **No unshare/setns semantics** — the `unshare(2)` and `setns(2)` syscalls
   are not documented here.
4. **No privilege model** — creating namespaces requires `CAP_SYS_ADMIN`
   (except user namespaces, which require no privilege since kernel 3.8). This
   is not documented on these pages.
5. **The compatibility matrix is self-reported as incomplete** — "this matrix
   shows the known problems." It is not an exhaustive enumeration of all
   cross-namespace interactions.
6. **Two of the five invariants are explicitly documented as broken** in the
   current kernel. This makes the source useful for understanding what NOT to
   rely on, but it means the invariants are aspirational, not guaranteed.

---

## Trust Assessment

**Source type:** `standard` (Linux kernel official documentation)
**Trust level:** MEDIUM — per the trust table, standards have a 14% verify
rate. However, the kernel.org admin-guide is primary documentation from the
kernel developers, and the compatibility list explicitly documents known bugs
(which is a sign of honesty). The invariants about namespace-scoped ID validity
(INV-LNXNS-001, INV-LNXNS-002) are fundamental to the namespace design and are
backed by the kernel implementation. The broken invariants (INV-LNXNS-003,
INV-LNXNS-004) are documented as broken, which is useful for negative
verification. INV-LNXNS-005 is a recommendation, not a proven invariant.