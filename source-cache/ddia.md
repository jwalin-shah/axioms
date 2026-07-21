# oracle/ddia
Source: Designing Data-Intensive Applications, Martin Kleppmann (O'Reilly, 2017)
Date pulled: 2026-07-21

## ACID Properties

### INV-DDIA-001: Atomicity Invariant
**Core Invariant:**
```
Given a transaction T consisting of operations {op₁, ..., opₙ}:
  outcome(T) ∈ {commit, abort}
  if outcome(T) = commit → every op_i is visible with effects durable
  if outcome(T) = abort → no op_i is visible and no effects persist
  ∀op_i, i ∈ [1,n]: either all op_i take effect or none do
```
**Source:** DDIA Chapter 1 (Reliability, Scalability, Maintainability), Chapter 7 (Transactions)
**Counterexample:** A banking transfer where $100 is debited from account A but the credit to account B fails or crashes before commit, and the debit persists while the credit does not.

### INV-DDIA-002: Isolation (Serializability) Invariant
**Core Invariant:**
```
Given concurrent transactions T₁, ..., Tₙ:
  serializable(T₁,...,Tₙ) ≡ ∃a serial ordering π of T₁,...,Tₙ
    such that the outcome of concurrent execution = outcome of π
  ∀operations op_i from T_i and op_j from T_j:
    the effect is equivalent to some serial order of all transactions
```
**Source:** DDIA Chapter 7 (Transactions, Serializable Isolation)
**Counterexample:** Two concurrent withdrawals from a joint account where the balance check reads $500 before either write. Both withdrawals of $400 pass the check (400 ≤ 500), but the final balance is -$300 instead of $100 — a serial schedule would have rejected one.

### INV-DDIA-003: Durability Invariant
**Core Invariant:**
```
After a transaction commits:
  the transaction's writes survive any subsequent crash or power loss
  durability_mechanism ∈ {WAL flush, replication_ack, battery_backed_memory}
  ∀crash at time t_after_commit: recover(data) includes committed writes
```
**Source:** DDIA Chapter 7 (Transactions, Durability discussion)
**Counterexample:** A database that acknowledges a commit before the WAL is flushed to disk. The server crashes, and the committed write is lost.

### INV-DDIA-004: Dirty Read Invariant
**Core Invariant:**
```
Given transactions T₁ (writing) and T₂ (reading):
  T₂ is said to read uncommitted data if:
    T₂ reads value v written by T₁ before T₁ commits or aborts
  read_uncommitted(T₂) ⟹ ¬isolation
  invariant: no transaction reads data written by an uncommitted transaction
```
**Source:** DDIA Chapter 7 (Read Committed isolation level)
**Counterexample:** Transaction T₁ writes "status='active'" and then aborts. Transaction T₂ reads "status='active'" before the abort. T₂ now operates on data that never existed.

## CAP Theorem

### INV-DDIA-005: CAP Theorem (Consistency-Availability Trade-off)
**Core Invariant:**
```
Given a distributed system S with network partition P:
  S cannot simultaneously guarantee:
    C(consistency): all nodes return the same response for the same query
    A(availability): every request receives a (non-error) response
    P(partition tolerance): system continues despite network partitions
  Formally (Gilbert & Lynch 2002):
    If partitions are possible, a system must choose between C and A.
    Write_all(Consistency) → no writes succeed if any replica is partitioned
    Read_any(Availability) → stale data possible during partition
```
**Source:** DDIA Chapter 9 (Consistency and Consensus), Gilbert & Lynch (2002) proof
**Counterexample:** A two-node database with a network partition. A write arrives at node A but can't reach node B. If you serve the write (availability), node B has stale data (no consistency). If you reject the write (consistency), the system is unavailable.

### INV-DDIA-006: CAP PACELC Extension
**Core Invariant:**
```
If partition (P):
  trade-off between availability (A) and consistency (C)
Else (no partition, ~P):
  trade-off between latency (L) and consistency (C)
Thus: PACELC: in case of Partition trade A and C, Else trade L and C
```
**Source:** DDIA Chapter 9 (PACELC, Daniel Abadi)
**Counterexample:** A system that claims "strong consistency" but uses asynchronous replication — during normal operation (no partition), stale reads occur because writes haven't propagated, violating the "else" trade-off claim.

## Write-Ahead Log (WAL) Crash Recovery

### INV-DDIA-007: WAL Correctness Invariant
**Core Invariant:**
```
For every data page modification:
  Before the page is written to disk, its change must be recorded in the WAL
  WAL entry must be flushed to stable storage before the corresponding data page
  After crash recovery: all committed transactions are replayed (redo)
  After crash recovery: all uncommitted transactions are rolled back (undo)
  LSN(order): WAL entries form a total order per log sequence number
  WAL.position ≥ data_page.flushed_position for all pages
```
**Source:** DDIA Chapter 7 (Transactions, WAL), ARIES algorithm
**Counterexample:** A database that writes a data page to disk, crashes before flushing the corresponding WAL entry, then recovers into an inconsistent state.

### INV-DDIA-008: ARIES Recovery Invariant
**Core Invariant:**
```
Recovery phase 1 (Analysis): determine dirty pages and active transactions
Recovery phase 2 (Redo): reapply all changes from the last checkpoint LSN
  for every committed transaction at time of crash
Recovery phase 3 (Undo): revert all changes from aborted/incomplete transactions
  invariant: Redo must be idempotent (can repeat without harm)
  invariant: Undo must be logged itself (compensation log records)
```
**Source:** DDIA Chapter 7 (Transactions, ARIES)
**Counterexample:** During recovery, a transaction that committed (and thus should be durable) is incorrectly rolled back because the redo phase missed a WAL entry that was flushed to the data page but not the log.

## LSM-Tree Compaction

### INV-DDIA-009: LSM-Tree Compaction Correctness
**Core Invariant:**
```
Given key k, values {v₁,...,vₙ} written at times {t₁,...,tₙ}:
  After compaction of SSTables S₁,...,Sₖ:
    ∀k: the retained value vᵢ has max(tᵢ) among all values in S₁..Sₖ
    ∀k: tombstone(k) is removed if no older value of k remains
    No duplicate keys across the output SSTable(s)
    deleted(k) ≡ latest_value(k) is tombstone ∧ no future compaction restores k
```
**Source:** DDIA Chapter 3 (Storage and Retrieval, LSM-Trees, SSTables, Compaction)
**Counterexample:** A compaction that drops a key that has no tombstone because it was in an older SSTable not included in the compaction — the key is permanently lost.

### INV-DDIA-010: LSM-Tree Merge Invariant (Leveled Compaction)
**Core Invariant:**
```
Leveled compaction maintains:
  Level 0: recent writes (may overlap key ranges)
  Level i > 0: each SSTable covers a non-overlapping key range
  Level i < Level i_max: merged into Level i+1 when Level i exceeds size threshold
  total_files(i) is bounded by max_files_per_level(i)
  size(L_i) = T * size(L_{i-1}) (where T is the fan-out factor, typically 10)
```
**Source:** DDIA Chapter 3 (Storage and Retrieval, LevelDB/RocksDB compaction)
**Counterexample:** A compaction that produces overlapping SSTables in Level 2 — a query for key `k` might read from multiple SSTables in Level 2 and get different results depending on read timing.

### INV-DDIA-011: LSM-Tree Size-Tiered Compaction Invariant
**Core Invariant:**
```
Multiple SSTables of similar size are compacted into one SSTable
  threshold: compact when count(SSTables of size ~S) > threshold_n
  after compaction: single SSTable of size ~n*S
  invariant: no more than threshold_n SSTables of comparable size exist
```
**Source:** DDIA Chapter 3 (Cassandra/HBase style compaction)
**Counterexample:** A write-heavy workload that produces hundreds of small SSTables before compaction triggers — read amplification blows up because every query must check all SSTables.

## B-Tree Page Split Invariants

### INV-DDIA-012: B-Tree Page Split Invariant
**Core Invariant:**
```
Given a B-Tree of order m (max entries per page = m, min entries = ceil(m/2)):
  When page P has m entries and a new entry e must be inserted:
    Split P into P_left (first ceil(m/2) entries) and P_right (remaining entries)
    Promote median entry to parent page P_parent
    If P_parent is full, split recursively
    After split: ∀children of P_parent, child page satisfies min ≤ count ≤ max
```
**Source:** DDIA Chapter 3 (B-Trees)
**Counterexample:** A B-Tree split that places the median entry incorrectly, resulting in a child page with fewer than `ceil(m/2)` entries after the split.

### INV-DDIA-013: B-Tree Page Merge Invariant
**Core Invariant:**
```
Given adjacent sibling pages P₁, P₂ with counts c₁, c₂:
  if c₁ + c₂ < m (max per page):
    merge P₁ and P₂ into one page
    demote separator key from parent
  invariant: after merge, no page violates min ≤ count ≤ max
```
**Source:** DDIA Chapter 3 (B-Tree balancing)
**Counterexample:** A merge that produces a page with count exceeding m, forcing an immediate re-split.

### INV-DDIA-014: B-Tree Write-Ahead Log Invariant
**Core Invariant:**
```
Before modifying any B-Tree page on disk:
  Write the intent (split/merge/update) to a pre-write log (WAL)
  After crash: replay WAL to restore consistent B-Tree state
  crash during split: either both halves are visible, or original page is intact
  invariant: the tree is always structurally valid at every point
```
**Source:** DDIA Chapter 3 (B-Tree crash recovery)
**Counterexample:** A crash during a page split that leaves the original page partially overwritten and the new page only half-written — neither the original nor the split state is recoverable.

### INV-DDIA-015: B-Tree Balance Invariant
**Core Invariant:**
```
∀leaf node: depth from root = constant h
∀internal node: ceil(m/2) ≤ entries ≤ m (except root)
root: 1 ≤ entries ≤ m (if non-empty)
h = 1 + ceil(log_{ceil(m/2)} (n/2))   where n = total entries
```
**Source:** DDIA Chapter 3 (B-Tree properties)
**Counterexample:** A B-Tree insert sequence that produces leaves at different depths — this violates the fundamental balance invariant of B-Trees.

## MVCC Snapshot Isolation

### INV-DDIA-016: Snapshot Isolation Visibility Rule
**Core Invariant:**
```
Transaction T with snapshot timestamp ts(T) sees:
  all writes from transactions T' where ts(T') < ts(T) and T' committed
  no writes from transactions T' where ts(T') >= ts(T)
  no writes from concurrent T' (overlapping begin/commit timestamps)
  writes by T itself (read-your-writes)
```
**Source:** DDIA Chapter 7 (Snapshot Isolation and Repeatable Read)
**Counterexample:** Transaction T starts at time 5. Transaction T' starts at time 3 and commits at time 7. T sees T''s writes (since T' started before T), but T' shouldn't be visible because it committed after T started.

### INV-DDIA-017: First-Committer-Wins (SI Write Conflict)
**Core Invariant:**
```
Given concurrent transactions T₁ and T₂ under snapshot isolation:
  if T₁ and T₂ both write to the same object:
    the first to commit wins; the second must abort
  WriteConflict(T₁, T₂) ≡ T₁ and T₂ write to overlapping keys
  commit(T₁) before commit(T₂) → T₂ aborts with serialization failure
```
**Source:** DDIA Chapter 7 (Snapshot Isolation, First-Committer-Wins)
**Counterexample:** Two concurrent increment operations each read X=5, then both write X=6. Without first-committer-wins, both commit and the write of one is lost (write skew).

### INV-DDIA-018: Predicate-Based MVCC Invariant (Phantom Avoidance)
**Core Invariant:**
```
∀query Q executed in transaction T with snapshot ts(T):
  if Q returns row set R at time t₁:
    if Q is re-executed at time t₂ > t₁ within T:
      R ⊆ R' (no tuples disappear)
      may have new tuples R' \ R that were committed by other transactions
      (this is the phantom read that SI permits — avoided by index-range locks)
```
**Source:** DDIA Chapter 7 (Phantom Reads, Predicate Locks)
**Counterexample:** A meeting room booking transaction that checks "count(bookings for room R at time slot S) = 0", finds zero, inserts a booking. Meanwhile, another transaction concurrently inserts a booking for the same room/slot. Both commit — double booking (the phantom problem).

### INV-DDIA-019: Write Skew Invariant
**Core Invariant:**
```
Under snapshot isolation:
  Write skew occurs when two concurrent transactions read overlapping data
  but write to disjoint data, with each decision depending on the other's read.
  Invariant (anti-write-skew): ∀T₁, T₂ concurrent:
    if T₁ reads {A, B} and writes A, T₂ reads {A, B} and writes B:
      there must be a serial order where T₁'s read of B is consistent with T₂'s write
  Allowing write skew requires explicit constraint mechanisms (materialized conflicts)
```
**Source:** DDIA Chapter 7 (Write Skew under Serializable Snapshot Isolation)
**Counterexample:** Two doctors on call: both check `count(on_call_doctors) ≥ 2`, both see 2, both set their status to `off_call` — now zero doctors are on call even though the invariant was "at least 2 on call."

## Quorum Read/Write Consistency

### INV-DDIA-020: Quorum Consistency Invariant
**Core Invariant:**
```
Given W (write quorum size), R (read quorum size), N (replica count):
  if W + R > N: every read includes the latest write
  if W + R > N: stale reads are impossible when quorum is satisfied
  if W + R ≤ N: stale reads are possible (last writer may not be in read quorum)
  optimal: W = R = ceil((N+1)/2)
```
**Source:** DDIA Chapter 9 (Quorum Consistency in Dynamo-style systems)
**Counterexample:** N=3, W=2, R=2. Write to replicas A and B succeeds. Read contacts replicas B and C — C is stale, B has the latest. W+R = 4 > 3 = N, so the read is consistent because B bridges the quorums.

### INV-DDIA-021: Sloppy Quorum and Hinted Handoff Invariant
**Core Invariant:**
```
During partition: system may accept writes on any W (not just N) nodes
  sloppy quorum: W nodes are the first W of N that respond (may not be preferred nodes)
  after partition heals: hinted handoff replays writes to the true preferred nodes
  invariant: hinted_handoff(T) must be idempotent (replay-safe)
  invariant: sloppy quorum sacrifices strong consistency for availability
```
**Source:** DDIA Chapter 9 (Sloppy Quorum in Dynamo/Riak)
**Counterexample:** A hint is handed off to a replica that already received the write via gossip. Without idempotency, the write is applied twice.

## Leader Election and Fencing Tokens

### INV-DDIA-022: Fencing Token Invariant
**Core Invariant:**
```
Given a monotonically increasing fencing token f:
  Each leader election yields a strictly larger token than any previous:
    f_0 < f_1 < f_2 < ... < f_n
  Any write with token f_i must be rejected by storage if f_current > f_i
  invariant: a stale leader with token f_i cannot mutate state after f_current > f_i
```
**Source:** DDIA Chapter 8 (Fencing Tokens, Leases)
**Counterexample:** A stale leader with token 1 issues a write command. A new leader with token 2 exists. Without fencing, the storage accepts the stale leader's write, corrupting state.

### INV-DDIA-023: Lease-Based Leader Invariant
**Core Invariant:**
```
Leader holds lease valid for [t₀, t₀ + lease_duration]:
  lease_holder must refresh lease before expiration
  no two nodes hold overlapping leases for the same term
  clock_skew must be bounded: max_clock_skew < lease_duration / 2
  if lease expires, another node may assume leadership without risk of conflict
```
**Source:** DDIA Chapter 8 (Leases for Leader Election)
**Counterexample:** Two nodes both believe they are leaders because clock skew on node A is 10 seconds and the lease is only 5 seconds, causing A's lease to expire earlier than expected while A continues to issue writes.

## Consensus Protocol Properties

### INV-DDIA-024: Consensus Safety (Uniform Agreement)
**Core Invariant:**
```
∀protocol correctly implementing consensus (e.g., Paxos, Raft, Zab):
  Uniform Agreement: no two nodes decide different values
  Validity: any decided value was proposed by some node
  Termination: every correct node eventually decides some value
  Integrity: no node decides twice
```
**Source:** DDIA Chapter 9 (Consensus, FLP impossibility, Raft)
**Counterexample:** In Raft without the Election Safety property, two nodes could become leaders in the same term, each deciding a different log entry for the same slot.

### INV-DDIA-025: Raft Election Safety
**Core Invariant:**
```
At most one leader per term — ∀term t: at most one node receives votes
from a quorum of the cluster.
  candidate receives votes from majority (⌊n/2⌋ + 1)
  each node votes once per term
  leader must have log at least as up-to-date as the voter
```
**Source:** DDIA Chapter 9 (Raft), Raft extended paper (Ongaro)
**Counterexample:** A network partition splits a 5-node cluster into {A,B} and {C,D,E}. Both groups elect a leader for the same term — but this violates Raft's election safety because each leader needs a majority.

### INV-DDIA-026: Raft Log Matching
**Core Invariant:**
```
If two logs have an entry at the same index with the same term:
  the logs are identical up to and including that index
  If two entries in different logs have the same index and term:
    they store the same command
    all prior entries are identical
```
**Source:** DDIA Chapter 9 (Raft), Raft extended paper (Ongaro)
**Counterexample:** Two nodes have identical term/index for entry 5 but different commands stored. This would cause different state machine outputs after applying the log, violating safety.

### INV-DDIA-027: Raft Leader Completeness (Election Restriction)
**Core Invariant:**
```
A candidate can only become leader if its log contains all committed entries.
  committed entry at term t is known to a majority
  candidate must receive votes from a majority
  each voter checks candidate's last_log_term ≥ own_last_log_term
    and last_log_index ≥ own_last_log_index on tie
  invariant: committed entries are never overwritten
```
**Source:** DDIA Chapter 9 (Raft Leader Completeness)
**Counterexample:** A node with an outdated log becomes leader (because it's reachable during a partition) and overwrites committed entries on replicas that have a more up-to-date log.

### INV-DDIA-028: Raft State Machine Safety
**Core Invariant:**
```
If a server has applied a log entry at a particular index to its state machine,
  no other server will ever apply a different entry for the same index.
  (Log Matching + Leader Completeness ⇒ State Machine Safety)
```
**Source:** DDIA Chapter 9 (Raft, Theorem 1)
**Counterexample:** Two servers apply different entries at index 10 because of a buggy leader change — the state machines diverge permanently.

### INV-DDIA-029: Paxos Safety (Consistency)
**Core Invariant:**
```
Paxos ensures:
  Safety: only a single value is chosen (agreement)
  Validity: only proposed values can be chosen
  Progress: some proposed value is eventually chosen (given sufficient liveness)
  Phase 1: prepare(n) → promise(n, v_max_accepted) for n > any seen, or reject
  Phase 2: accept!(n, v) if a majority promised the prepare for n
  Invariant: if value v is chosen at ballot n, any higher ballot must propose v
```
**Source:** DDIA Chapter 9 (Paxos, Lamport)
**Counterexample:** A Paxos proposer that skips Phase 1 and goes straight to Phase 2 — it might propose a value different from the one that would satisfy the "chosen value propagation" invariant.

## Replication

### INV-DDIA-030: Single-Leader Replication Invariant
**Core Invariant:**
```
All writes go to a single leader node.
Followers replicate from the leader's log.
∀write: received by leader → replicated to all followers (eventually)
∀read from follower: may be stale (replication lag exists)
 synchronous replication: leader waits for ack from (all | W-1) followers
 asynchronous replication: leader does not wait for follower ack
```
**Source:** DDIA Chapter 5 (Replication, Single-Leader)
**Counterexample:** A read-your-writes violation: user writes a comment on the leader, refreshes the page, and a follower read doesn't show the new comment because replication lag.

### INV-DDIA-031: Multi-Leader Replication Conflict Resolution
**Core Invariant:**
```
Given concurrent writes w₁ to key k at leader L₁ and w₂ to key k at leader L₂:
  Conflict must be resolved deterministically:
    LWW (last-writer-wins) based on timestamp or hybrid logical clock (HLC)
    CRDT (commutative replicated data types)
    custom merge logic (application-specific)
  All replicas must converge to the same final value for all keys
```
**Source:** DDIA Chapter 5 (Multi-Leader Replication, Conflict Resolution)
**Counterexample:** Two leaders accept concurrent updates to the same shopping cart item with different quantities. Without proper CRDT (e.g., use LWW set instead of last-write-wins per field), one update is silently lost.

### INV-DDIA-032: Version Vector Invariant (Conflict Detection)
**Core Invariant:**
```
Given N replicas, version vector V = [c₁, c₂, ..., cₙ]:
  V[replica_i] = number of versions of this object created at replica i
  V₁ ≤ V₂ iff ∀i: V₁[i] ≤ V₂[i]  (V₂ dominates/is descendant of V₁)
  V₁ ∥ V₂ iff ¬(V₁ ≤ V₂) ∧ ¬(V₂ ≤ V₁) (concurrent, conflict exists)
  Require merge when V₁ ∥ V₂
```
**Source:** DDIA Chapter 5 (Version Vectors, Dynamo-style conflict detection)
**Counterexample:** Two replicas each increment their version vector entry for the same key without the other knowing. If the reconciliation merges rather than detects the conflict, data loss occurs.

## Distributed Transactions

### INV-DDIA-033: Two-Phase Commit (2PC) Safety
**Core Invariant:**
```
Phase 1 (Prepare): Coordinator asks all participants to prepare
  participant: write prepare record to WAL, respond yes/no
Phase 2 (Commit): If all yes, coordinator tells all to commit
  coordinator crash before commit decision → participants remain in-doubt
  participant with prepared but no commit decision → blocking
  invariant: if any participant prepared, coordinator MUST commit (no unilateral abort)
  invariant: all participants that prepared eventually get the commit decision
```
**Source:** DDIA Chapter 9 (Distributed Transactions, 2PC)
**Counterexample:** The coordinator crashes after receiving all "yes" votes but before logging the commit decision. The participants remain in-doubt, holding locks, potentially forever (blocking).

### INV-DDIA-034: Linearizability Invariant
**Core Invariant:**
```
An execution is linearizable if there exists a total ordering of operations
such that:
  the total order respects the real-time precedence (op₁ finishes before op₂ starts)
  each operation appears atomically at a single point in the total order
  each read returns the value of the most recent write in the total order
```
**Source:** DDIA Chapter 9 (Linearizability, Herlihy & Wing 1990)
**Counterexample:** A distributed lock that returns "lock acquired" to client A, then client B also acquires the same lock at a wall-clock time after A's response — this violates the real-time precedence of linearizability.

## CRDT Convergence

### INV-DDIA-035: CRDT Strong Eventual Consistency
**Core Invariant:**
```
Given a CRDT C replicated on nodes N₁,...,Nₖ:
  Synchronous operations: any two nodes that have received the same set of updates
    are in the same state (convergence)
  All operations commute (or are idempotent):
    apply(apply(state, op₁), op₂) = apply(apply(state, op₂), op₁)
  The merge operation is associative, commutative, and idempotent:
    merge(merge(a, b), c) = merge(a, merge(b, c))
    merge(a, b) = merge(b, a)
    merge(a, a) = a
```
**Source:** DDIA Chapter 5 (CRDTs, Shapiro et al.)
**Counterexample:** A counter CRDT that uses addition for increment but does not handle concurrent decrements correctly — if two nodes each see different increments and decrements, they diverge.
