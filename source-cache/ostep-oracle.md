# OSTEP Oracle (2015)

Source: "Operating Systems: Three Easy Pieces" (Arpaci-Dusseau, 2015).
Also: OSTEP projects (xv6, pintos), OS:PP (Anderson & Dahlin).

This is how the machine underneath you actually works. Every concept maps to a resource contract,
a language-agnostic enforcement pattern, and specific orbit applications.

---

## 1. CPU Virtualization — "Limited Direct Execution"

**Principle:** The OS gives each process the illusion of its own CPU by time-slicing the physical CPU.
Two modes: user mode (restricted) and kernel mode (privileged). The OS regains control via
timer interrupts (preemptive) or system calls (cooperative).

**Invariant:**
```
∀process P: P cannot prevent the OS from regaining control
∀process P: P cannot access memory or devices it does not own
∀time slice: timer interrupt fires within the slice duration (bounded)
```

**Purpose:** Without this, one process could monopolize the CPU forever. Every goroutine leak, every infinite loop, every deadlock in orbit is a violation of the same principle at the application level — the scheduler must always be able to regain control.

**Enforcement (any language):**
- Timeouts on every blocking operation
- Context cancellation: the caller can always cancel
- Preemption: the runtime can interrupt a running goroutine/thread
- `select` with a `default` or `time.After` branch

**Enforcement (Go):**
- `context.Context` with `WithTimeout`/`WithDeadline` — CPU time bounded
- `time.AfterFunc` — "timer interrupt" at the application level
- Go runtime preemption (Go 1.14+): goroutines are preempted at safe points
- `runtime.Gosched()` — yield the CPU

**orbit packages affected:**
- `pkg/sandbox` — `ShellContext` has a 30s timeout. The shell cannot run forever. AX-014.
- `pkg/dispatch` — dispatch with `ctx` cancellation; the caller can always abort
- `pkg/ggrind` — grind pipeline respects `ctx.Done()`; no stage can block forever
- `pkg/tokenrouter` — `Acquire` with timeout; a key rotation cannot hang the caller

---

## 2. Memory Virtualization — "Address Translation"

**Principle:** Each process sees its own virtual address space. The OS + MMU translate virtual addresses
to physical addresses via page tables. This provides isolation: no process can read another process's memory.

**Invariant:**
```
∀process P: ∀address a in P's virtual address space, translate(a) is either:
  1. A valid physical address owned by P, or
  2. A fault (segfault) — P is terminated
∀process P, Q: P ≠ Q → P's physical pages ∩ Q's physical pages = ∅ (except shared memory)
```

**Purpose:** Memory isolation is the foundation of security. In orbit, the same principle applies: one request's state must not leak into another request's state. A sandboxed process must not access the host's memory.

**Enforcement (any language):**
- Separate address spaces per process/container
- Copy-on-write for shared data
- Bounds checking on all array/slice access
- Null pointer/bottom value checks

**Enforcement (Go):**
- Go's memory safety: no pointer arithmetic, bounds-checked slices, GC prevents use-after-free
- `context.Context` scopes per-request state (not global state)
- `sync.Pool` for reusable memory (explicit ownership transfer)
- Race detector: `go test -race` catches shared-memory violations

**orbit packages affected:**
- `pkg/sandbox` — `resolve()` enforces path containment (process-level address space). AX-012, AX-013, AX-017.
- `pkg/tokenrouter` — per-key bucket state is isolated; key A's rate limit doesn't affect key B
- `pkg/luaengine` — Lua sandbox: 5 whitelisted libraries (base, table, string, math, coroutine). No `os`, no `io`, no `debug`. AX-018, AX-019.
- `pkg/circuitbreaker` — per-backend circuit breaker state; backend A's failure doesn't affect backend B

---

## 3. Concurrency — "Locks, CVs, and Semaphores"

**Principle:** When multiple threads access shared state, you need synchronization. The OS provides:
- **Locks (mutexes):** mutual exclusion — only one thread in the critical section at a time
- **Condition variables:** wait for a condition to become true, atomically releasing the lock
- **Semaphores:** counting permits — up to N threads can access the resource

**Invariant:**
```
∀lock L: at most one thread holds L at any time
∀lock L: L is eventually released (no deadlock)
∀thread T: T eventually acquires L (no starvation, if fair)
∀condition variable CV: wait(CV, L) atomically releases L and blocks until signaled
∀semaphore S with count N: at most N threads hold S simultaneously
```

**Purpose:** Concurrency bugs are the hardest to reproduce and fix. They survive code review, pass tests, and only manifest under load. The invariants above are the MINIMUM correctness conditions — if any of them fails, the program is broken.

**Enforcement (any language):**
- Lock ordering: all threads acquire locks in the same order → no deadlock
- Lock scoping: lock, do work, unlock — never hold a lock across I/O
- Condition variables: always check the condition in a loop (spurious wakeups)
- Semaphores: use for bounded resource pools, not mutual exclusion

**Enforcement (Go):**
- `sync.Mutex` for mutual exclusion
- `sync.Cond` for condition variables (rare; channels are preferred)
- Buffered channels as semaphores: `make(chan struct{}, N)`
- `sync.WaitGroup` for thread join
- `sync.Once` for one-time initialization
- "Do not communicate by sharing memory; share memory by communicating" — channels

**orbit packages affected:**
- `pkg/tokenrouter` — `sync.Mutex` on key rotation, `sync.Once` for one-time key pool init
- `pkg/circuitbreaker` — `sync.Mutex` on state transitions. AX-001 through AX-010 are all concurrency invariants.
- `pkg/sandbox` — `sync.Once` on worktree initialization. AX-015.
- `pkg/ggrind` — worker pool with bounded concurrency (semaphore pattern)
- `pkg/congestion` — mutex on VM state, concurrent access to compiled programs

---

## 4. Persistence — "File Systems and I/O"

**Principle:** Data that survives a crash must be written to persistent storage. The OS provides:
- **File descriptors:** handles to open files, sockets, pipes
- **Buffering:** the OS buffers writes; `fsync` forces them to disk
- **Atomicity:** a write is NOT atomic by default; the OS can crash mid-write
- **Write-ahead logging:** write the INTENT before the DATA (WAL) — recoverable after crash

**Invariant:**
```
∀write W: after W returns, the data is in the OS buffer (not necessarily on disk)
∀fsync F: after F returns, all buffered writes up to F are on disk
∀crash C: after recovery, the file system is consistent (no partial metadata, no dangling inodes)
∀WAL: log record is written before the data page is modified
```

**Purpose:** "The file system is consistent after a crash" is a hard-won property. PostgreSQL and SQLite both use WAL to achieve it. Without WAL, a crash during a write leaves the database in an inconsistent state — half-written records, corrupted indexes, lost data.

**Enforcement (any language):**
- `fsync`/`fdatasync` after critical writes
- Atomic rename: write to temp file, rename over target (POSIX: `rename` is atomic)
- Checksums on all stored data
- Crash recovery: on startup, replay the WAL, then truncate

**Enforcement (Go):**
- `*os.File.Sync()` — fsync
- `os.Rename()` — atomic rename (same filesystem)
- `io.Writer` — the universal persistence interface
- `database/sql` — transactions with rollback

**orbit packages affected:**
- `pkg/store` — WAL-based persistence. Write-ahead log, crash recovery, MVCC snapshots.
- `pkg/sandbox` — `WriteFile()` writes to the worktree; `ReadFile()` reads. No fsync promise (the sandbox is ephemeral).
- `pkg/tokenrouter` — key state is in-memory only (no persistence). A crash resets all buckets. This is intentional (the key pool is external).

---

## 5. Process Scheduling — "MLFQ and CFS"

**Principle:** The OS scheduler decides which process runs next. Key algorithms:
- **MLFQ (Multi-Level Feedback Queue):** prioritize interactive jobs, deprioritize CPU-bound jobs. Jobs that use their full time slice move down; jobs that block on I/O stay up.
- **CFS (Completely Fair Scheduler, Linux):** each process gets a fair share of CPU time, weighted by priority. The scheduler picks the process with the lowest vruntime.

**Invariant:**
```
∀process P: P eventually gets CPU time (no starvation)
∀interactive process I: I gets CPU quickly after I/O (low latency)
∀priority p₁ > p₂: process with p₁ gets more CPU share than p₂, but p₂ is not starved
```

**Purpose:** Scheduling is a universal problem — not just for CPUs, but for requests, tasks, tokens, and reviewers. Every orbit subsystem that has multiple consumers competing for a shared resource needs a scheduling policy.

**Enforcement (any language):**
- Priority queues with aging (prevent starvation)
- Weighted fair queuing (each consumer gets its share)
- Work stealing: idle workers take work from busy workers' queues
- Backpressure: when the queue is full, reject new work (don't accept and drop)

**Enforcement (Go):**
- Go scheduler: GOMAXPROCS, work stealing, preemptive scheduling
- `runtime.Gosched()` — yield, don't spin
- `golang.org/x/sync/semaphore` — weighted semaphore for fair queuing
- `errgroup` — bounded concurrency, cancel on first error

**orbit packages affected:**
- `pkg/ggrind` — reviewer scheduling: weighted fair queuing across projects, backpressure on queue full
- `pkg/tokenrouter` — key scheduling: round-robin across available keys, cooldown as priority demotion
- `pkg/dispatch` — task scheduling: retry with backoff, priority by task type
- `pkg/scheduler` — the abstraction layer: schedule(task, pool) → assignment

---

## 6. Swapping and Paging — "Beyond Physical Memory"

**Principle:** When physical memory is full, the OS moves pages to disk (swap) to make room.
This is a policy decision: which page to evict? LRU, clock, and 2Q are common algorithms.

**Invariant:**
```
∀page P in memory: P is either:
  1. Actively in use (recently accessed), or
  2. A candidate for eviction (not recently accessed)
∀eviction E: if P is evicted but still needed, a page fault brings it back (correct but slow)
```

**Purpose:** The page-replacement problem is isomorphic to cache eviction, connection pool management, and token bucket refill. Every system with a bounded resource and unbounded demand needs an eviction policy.

**Enforcement (any language):**
- Cache eviction: LRU, LFU, TTL, 2Q
- Connection pool: evict idle connections, keep active ones
- Token bucket: tokens expire after a window; new tokens arrive at a fixed rate
- GC: generational hypothesis (young objects die quickly; old objects survive)

**Enforcement (Go):**
- `sync.Pool` — automatic GC-based eviction (pool may be cleared at any GC)
- `container/heap` — priority queue for eviction policies
- `time.Ticker` — periodic cleanup (token expiry, connection cleanup)
- `context.Context` — explicit lifetime management

**orbit packages affected:**
- `pkg/tokenrouter` — bucket time lazy expiry: `BucketTime[k][i] < now-60 → bucket[k][i]=0`. This IS a page-replacement policy.
- `pkg/circuitbreaker` — HalfOpen → Open after a failure: the probe is "evicted" from the recovery path
- `pkg/store` — MVCC snapshot GC: old versions are evicted when no transaction references them

---

## 7. Security — "Protection and Isolation"

**Principle:** The OS is the ultimate trust boundary. It enforces:
- **User/kernel separation:** user code runs in ring 3; kernel code runs in ring 0
- **Process isolation:** one process cannot access another's memory or files
- **Access control:** file permissions (rwx), capabilities (CAP_SYS_*), user IDs
- **System call filtering:** seccomp restricts which syscalls a process can make

**Invariant:**
```
∀user process U: U cannot execute privileged instructions (ring 0)
∀process P: P can only access resources for which it has explicit permission
∀syscall S: seccomp policy(S) ∈ {allow, trap, kill}
```

**Purpose:** This is the same as Saltzer & Schroeder's principles, but from the OS perspective. The OS is the ENFORCER — it can't be bypassed. Orbit's sandbox tries to do the same at the application level, but without kernel support, it's a best-effort approximation.

**Enforcement (any language):**
- Containerization (Docker, gVisor, Firecracker)
- seccomp, AppArmor, SELinux
- Capability dropping: start with all capabilities, drop unnecessary ones
- User namespaces: root in the container ≠ root on the host

**Enforcement (Go):**
- `syscall` package — raw system calls (use with extreme care)
- `os/exec` with `SysProcAttr` — setuid, setgid, chroot, capabilities
- `golang.org/x/sys/unix` — seccomp, capabilities, namespaces
- `internal/sandbox` (gVisor) — the reference for Go sandboxing

**orbit packages affected:**
- `pkg/sandbox` — `Shell()` runs bash with `--norc --noprofile`. Path containment via `resolve()`. No seccomp, no user namespaces. See `gvisor.md` for the gap analysis.
- `pkg/luaengine` — library whitelisting (base, table, string, math, coroutine). No `os`, no `io`, no `debug`. This is the application-level equivalent of seccomp.
- `pkg/wasmbox` — WASM sandbox: the WASM runtime enforces memory isolation at the bytecode level

---

## The OSTEP Test

For any code that manages a resource, ask:
1. **CPU:** Can the caller cancel this? Is there a timeout?
2. **Memory:** Is this state scoped to one request? Could it leak to another?
3. **Concurrency:** What lock protects this? Is the lock ordering consistent?
4. **Persistence:** If we crash here, what data is lost? Is there a WAL?
5. **Scheduling:** Who gets the resource next? Can anyone be starved?
6. **Eviction:** When the resource is full, what gets evicted? Is the policy fair?
7. **Security:** What's the trust boundary? What syscalls does this code path allow?

OSTEP is the foundation. Every other oracle builds on it.