# oracle/linux-capabilities — Capability model: bounding set, ambient set, inheritable set
Source: https://man7.org/linux/man-pages/man7/capabilities.7.html (Linux man-pages 6.18, 2026-02-08)
Date pulled: 2026-07-21
Source type: oracle-extract (MEDIUM trust — man-pages are semi-formal, maintained by kernel developers)

## Extracted Invariants

### INV-LCAP-001: Ambient Set Subset Invariant
**Core Invariant:**
```
∀ thread t, ∀ capability c:
  c ∈ P_ambient(t) ⟹ c ∈ P_permitted(t) ∧ c ∈ P_inheritable(t)
```
**Source:** "Ambient (since Linux 4.3)" section: "The ambient capability set obeys the invariant that no capability can ever be ambient if it is not both permitted and inheritable."

**Counterexample:** If a capability were ambient but not permitted, execve would add it to the new permitted set (P'(permitted) = ... | P'(ambient)), granting a capability the thread should not have. The invariant prevents this privilege-escalation path. If ambient but not inheritable, the capability could not have been legitimately preserved across execve in the first place.

**Why this matters for bridge/orbit:** Bridge spawns sandboxed subprocesses. If the sandbox setup ever attempts to set ambient capabilities, this invariant must hold — violation means the kernel is bypassing its own security model, or (more likely) our capability plumbing has a bug. The ambient set is automatically lowered when permitted/inheritable are lowered, so any code that raises ambient must first ensure both are present.

---

### INV-LCAP-002: execve() Capability Transformation Rules
**Core Invariant:**
```
∀ thread T, executable file F, after execve(F):
  P'_ambient     = (F_is_privileged) ? ∅ : P_ambient
  P'_permitted   = (P_inheritable ∩ F_inheritable) ∪ (F_permitted ∩ P_bounding) ∪ P'_ambient
  P'_effective   = F_effective ? P'_permitted : P'_ambient
  P'_inheritable = P_inheritable     [unchanged]
  P'_bounding    = P_bounding        [unchanged]
```
where F_is_privileged = (F has file capabilities) ∨ (F has setuid/setgid bit set).

**Source:** "Transformation of capabilities during execve()" section — these are the formal kernel equations.

**Counterexample:** 
- Without the P_bounding AND in the second term, a file with F_permitted set could bypass the bounding set — this is the bounding set's entire purpose.
- Without the F_effective guard, a capability-dumb binary (effective bit set) could run with ambient capabilities instead of its full file-permitted ones.
- If P_inheritable were not preserved, a carefully constructed inheritable set would be destroyed across exec chains.

**Why this matters for bridge/orbit:** Orbit dispatches jobs via execve. The capability state of the dispatched process is fully determined by these equations. When bridge constructs a sandbox, the bounding set, inheritable set, and file capabilities together define what the sandboxed process can do. Auditing against these equations proves that the sandbox actually enforces the claimed isolation.

---

### INV-LCAP-003: Bounding Set Irreversibility
**Core Invariant:**
```
∀ thread t, ∀ capability c:
  After PR_CAPBSET_DROP(c), ∀ future states: c ∉ P_bounding(t)
```
**Source:** "Capability bounding set" section: "Once a capability has been dropped from the bounding set, it cannot be restored to that set."

**Counterexample:** If a dropped capability could be restored, a compromised process that later gained CAP_SETPCAP could re-expand its bounding set, rendering the bounding set ineffective as a security mechanism. The irreversibility ensures monotonic privilege reduction.

**Why this matters for bridge/orbit:** Bridge's sandbox should drop all unnecessary capabilities from the bounding set before executing untrusted code. The irreversibility property guarantees that nothing the sandboxed process does — even if it exploits a kernel bug to gain CAP_SETPCAP — can recover dropped bounding capabilities. This is a one-way door, and once closed, it stays closed for all descendants.

---

### INV-LCAP-004: Permitted Set Monotonic Non-Increase
**Core Invariant:**
```
∀ thread t, after capset(2):
  P'_permitted(t) ⊆ P_permitted(t)
```
**Source:** "Programmatically adjusting capability sets" section: "The new permitted set must be a subset of the existing permitted set (i.e., it is not possible to acquire permitted capabilities that the thread does not currently have)."

**Counterexample:** If a thread could add capabilities to its permitted set via capset(2), any process could escalate privilege without execve-ing a privileged binary. Combined with the effective-set-as-subset rule, this would allow arbitrary capability acquisition. The only way to gain new permitted capabilities is execve of a file that grants them (and even then, only within the bounding set constraint).

**Why this matters for bridge/orbit:** This invariant means that once bridge drops a capability from the permitted set, no amount of capset manipulation by the sandboxed code can recover it. Combined with the bounding set irreversibility (INV-LCAP-003), this gives a two-layer defense: the bounding set prevents re-acquisition via execve, and the permitted set prevents re-acquisition via capset.

---

### INV-LCAP-005: Effective Set Subset Invariant
**Core Invariant:**
```
∀ thread t: P_effective(t) ⊆ P_permitted(t)
```
**Source:** "Programmatically adjusting capability sets" section: "The new effective set must be a subset of the new permitted set." Also implicit in the execve rules where P'_effective = F_effective ? P'_permitted : P'_ambient, and P'_ambient ⊆ P_inheritable ⊆ P_permitted.

**Counterexample:** If effective could contain capabilities not in permitted, the permitted set's role as a "limiting superset" would be meaningless — a thread could exercise capabilities it is not permitted to hold. This would break the entire capability model.

**Why this matters for bridge/orbit:** When auditing sandbox state, checking that effective ⊆ permitted is a cheap safety check. If it fails, something has gone very wrong (kernel bug or memory corruption). This is a good invariant to assert before launching untrusted code.

---

### INV-LCAP-006: UID Transition Capability Clearing
**Core Invariant:**
```
∀ thread t:
  (is_root_before(t) ∧ ¬is_root_after(t)) ⟹ P_permitted(t) = P_effective(t) = P_ambient(t) = ∅
  (euid(t) = 0 → euid'(t) ≠ 0) ⟹ P_effective(t) = ∅
  (euid(t) ≠ 0 → euid'(t) = 0) ⟹ P_effective(t) = P_permitted(t)
```
where is_root = (ruid == 0) ∨ (euid == 0) ∨ (suid == 0).

**Source:** "Effect of user ID changes on capabilities" section. Three sub-rules:
1. All real/effective/saved UIDs go from 0→nonzero ⇒ clear permitted, effective, ambient.
2. Effective UID goes 0→nonzero ⇒ clear effective.
3. Effective UID goes nonzero→0 ⇒ copy permitted to effective.

**Counterexample:** Without rule 1, a root process that dropped privileges via setuid() would retain its root capabilities in the permitted set, and could later re-enable them — breaking the Unix security model where dropping root is supposed to be irreversible (absent execve of a setuid binary). Without rule 2, a process whose effective UID became unprivileged could continue exercising root capabilities. Without rule 3, a setuid-root program would need to explicitly re-enable its effective set.

**Why this matters for bridge/orbit:** Bridge runs as root (or with elevated capabilities) to set up sandboxes, then drops privileges before executing untrusted code. If the UID transition clearing rules are not respected — or if SECBIT_KEEP_CAPS is set without understanding the consequences — the sandboxed process could retain root capabilities. This is a critical audit point.

---

### INV-LCAP-007: SECBIT_KEEP_CAPS Cleared on execve
**Core Invariant:**
```
∀ thread t, after execve(F):
  SECBIT_KEEP_CAPS ∉ securebits(t)
```
**Source:** "The securebits flags" section: "This flag is always cleared on an execve(2)."

**Counterexample:** If KEEP_CAPS persisted across execve, a process could exec a setuid-root binary, retain its prior capabilities, and then drop UIDs to nonzero while keeping capabilities — bypassing the UID transition clearing rules. The execve clearing ensures each new program image starts fresh regarding this flag.

**Why this matters for bridge/orbit:** Bridge might use KEEP_CAPS during sandbox setup (to drop UIDs without losing permitted capabilities needed for further setup). The execve clearing guarantees that the actual sandboxed program cannot inherit this flag — it must re-establish it if needed. This is a safety property: KEEP_CAPS is transient, scoped to a single program image.

---

### INV-LCAP-008: Securebits Locked Flag Irreversibility
**Core Invariant:**
```
∀ thread t, ∀ flag f ∈ {KEEP_CAPS, NO_SETUID_FIXUP, NOROOT, NO_CAP_AMBIENT_RAISE}:
  f_LOCKED ∈ securebits(t) ⟹ f is immutable for t and all descendants
```
**Source:** "The securebits flags" section: "Setting any of the 'locked' flags is irreversible, and has the effect of preventing further changes to the corresponding 'base' flag."

**Counterexample:** Without locked flags, a compromised child process could unset NOROOT, then exec a setuid-root binary to regain full capabilities. Locked flags create a capability-only environment that cannot be escaped, even by execve of setuid-root binaries.

**Why this matters for bridge/orbit:** The securebits lock pattern (explicitly shown in the man page) is how bridge should irrevocably enter a "no root magic" mode. Once locked, no descendant can ever use setuid-root to escape the sandbox. This is the strongest form of privilege reduction available in Linux.

---

### INV-LCAP-009: Capability-Dumb Binary All-or-Nothing Check
**Core Invariant:**
```
∀ file F with F_effective = true:
  execve(F) succeeds ⟹ F_permitted ⊆ P'_permitted
  execve(F) fails with EPERM ⟺ F_permitted ⊈ P'_permitted
```
**Source:** "Safety checking for capability-dumb binaries" section: "If the process did not obtain the full set of file permitted capabilities, then execve(2) fails with the error EPERM."

**Counterexample:** A capability-dumb binary (e.g., a setuid-root program converted to file capabilities without code changes) expects all its file-permitted capabilities to be active. If the bounding set masks some out, the binary would run with fewer capabilities than it expects — potentially opening security holes where error paths or privilege checks are silently skipped. The EPERM failure makes this condition explicit and safe.

**Why this matters for bridge/orbit:** Bridge may need to execute capability-dumb binaries inside or outside the sandbox. If the bounding set is too restrictive, these binaries will fail with EPERM rather than run in a degraded state. This is a diagnostic signal: EPERM on execve means the sandbox is too tight, not a kernel bug.

---

### INV-LCAP-010: File Effective Bit Propagation Constraint
**Core Invariant:**
```
∀ file F, ∀ c ∈ F_permitted ∪ F_inheritable with c's effective flag set:
  ∀ d ∈ F_permitted ∪ F_inheritable with d's permitted/inheritable flag set:
    d's effective flag must also be set
```
Equivalently: if the effective bit is set for any file capability, it must be set for all file capabilities that have permitted or inheritable set.

**Source:** "File capabilities" section: "if we specify the effective flag as being enabled for any capability, then the effective flag must also be specified as enabled for all other capabilities for which the corresponding permitted or inheritable flag is enabled."

**Counterexample:** If a file grants CAP_NET_RAW (permitted+effective) and CAP_SYS_ADMIN (permitted only, not effective), the execve rules (with F_effective=true) would grant CAP_SYS_ADMIN in the effective set too — because F_effective is a single bit for the entire file, not per-capability. The constraint prevents this accidental privilege amplification.

**Why this matters for bridge/orbit:** When bridge sets file capabilities on sandbox binaries, this constraint must be satisfied. Violating it would result in capabilities being granted to the effective set that were not intended to be active — a privilege escalation. Tools like setcap(8) enforce this constraint automatically, but hand-crafted xattr writes may not.

---

### INV-LCAP-011: Bounding Set Masks Inheritable Set Addition
**Core Invariant:**
```
∀ thread t, ∀ capability c:
  c ∉ P_bounding(t) ⟹ c cannot be added to P_inheritable(t) via capset(2)
```
**Source:** "Capability bounding set" section: "The new inheritable set must be a subset of the combination of the existing inheritable set and the capability bounding set" and "if a capability is not in the bounding set, then a thread can't add this capability to its inheritable set."

**Counterexample:** Without bounding set enforcement on inheritable additions, a thread could add a capability to its inheritable set (which persists across execve), then execve a file with that capability in its inheritable set — bypassing the bounding set constraint. The bounding set guards not just the direct permitted path (via AND with F_permitted) but also the inheritable path.

**Note:** "If a thread maintains a capability in its inheritable set that is not in its bounding set, then it can still gain that capability in its permitted set by executing a file that has the capability in its inheritable set." This means the bounding set only prevents NEW additions to inheritable, not existing ones — a subtle asymmetry.

**Why this matters for bridge/orbit:** When constructing an inheritable set for a sandboxed process, both the bounding set and the existing inheritable set must be considered. A capability already in the inheritable set can survive even if it is NOT in the bounding set — this is a potential escape hatch if bridge incorrectly assumes the bounding set fully gates the inheritable set.

---

### INV-LCAP-012: Namespaced File Capability Containment
**Core Invariant:**
```
∀ file F with VFS_CAP_REVISION_3 xattr, ∀ process p:
  (p executes F ∧ capabilities conferred) ⟹
    (uid 0 in p's user namespace maps to the root user ID stored in F's xattr)
    ∨ (p's user namespace is a descendant of such a namespace)
```
**Source:** "Namespaced file capabilities" section: "capabilities are conferred only if the binary is executed by a process that resides in a user namespace whose UID 0 maps to the root user ID that is saved in the extended attribute, or when executed by a process that resides in a descendant of such a namespace."

**Counterexample:** Without namespace scoping, file capabilities from one container would be active in another container or on the host — a container breakout. The namespace root user ID binding ensures file capabilities are scoped to the user namespace hierarchy that created them.

**Why this matters for bridge/orbit:** Bridge operates in user namespaces for sandbox isolation. File capabilities set inside a bridge-managed namespace should not confer capabilities to processes outside that namespace (including the host). This invariant proves that VFS_CAP_REVISION_3 enforces this containment.

---

### INV-LCAP-013: Capability-Bounding Execve Gate
**Core Invariant:**
```
∀ thread t, ∀ file F, after execve(F):
  P'_permitted ⊆ P_bounding(t)
```
Because P'_permitted = (P_inheritable ∩ F_inheritable) ∪ (F_permitted ∩ P_bounding) ∪ P'_ambient, and (F_permitted ∩ P_bounding) ⊆ P_bounding, and P'_ambient ⊆ P_inheritable ⊆ P_bounding (when bounded properly), the result is always a subset of the bounding set.

**Source:** Derived from the execve transformation rules in "Transformation of capabilities during execve()" — the P_bounding AND with F_permitted term directly enforces this. Not stated as a standalone invariant in the man page, but it is the defining property of the bounding set.

**Counterexample:** If this were violated, the bounding set would not "bound" anything. A file with F_permitted set could grant capabilities outside the bounding set, making the entire bounding set mechanism useless.

**Why this matters for bridge/orbit:** This is the fundamental guarantee that makes the bounding set useful for sandboxing. If bridge drops CAP_SYS_ADMIN from the bounding set, no execve — of any file, with any file capabilities — can grant CAP_SYS_ADMIN to the process. Period.

---

## Notes

- This page was fetched from man7.org because the kernel.org HTML docs path (/doc/html/latest/userspace-api/capabilities.html) returns 404. The kernel documentation tree no longer hosts a dedicated capabilities.html page under userspace-api; the canonical source is the capabilities(7) man page.
- The execve transformation rules constitute a formal specification of Linux capability transitions. They are the closest thing to a mathematical specification of process privilege in Linux.
- Several invariants (sections "Per-thread capability sets" and "Programmatically adjusting capability sets") are presented as rules governing system calls; they function as invariants because the kernel enforces them on every operation.
- The SECBIT_NOROOT + SECBIT_NOROOT_LOCKED combination creates an irrevocable "no root magic" environment — this is the strongest available Linux primitive for ensuring a process tree can never regain full root capabilities.
- The capabilities(7) page is maintained alongside the kernel (man-pages project), making it a high-quality source. However, it is documentation, not executable specification — some edge cases may exist that are not documented here. The actual enforcement is in kernel/security/commoncap.c.
