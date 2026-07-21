# oracle/kafka
Source: Apache Kafka documentation (https://kafka.apache.org/documentation/)
Date pulled: 2026-07-21

## Log Compaction

### INV-KAFKA-001: Log Compaction Key Retention Invariant
**Core Invariant:**
```
∀topic partition with log compaction enabled, ∀key k:
  If k has at least one record in the log with timestamp ≥ head_timestamp:
    the most recent record for k is retained (the "head" record)
  If the most recent record for k is a tombstone:
    k is retained until the segment's "delete.retention.ms" expires, then removed
  Otherwise: k's older records may be removed during compaction
```
**Source:** https://kafka.apache.org/documentation/#compaction
**Counterexample:** A key k with records [v1 at offset 10, v2 at offset 20] — after compaction, v1 at offset 10 is removed but v2 at offset 20 is retained. If both records were removed, the semantic information about k's last known value is lost.

### INV-KAFKA-002: Log Compaction Tombstone Cleanup Invariant
**Core Invariant:**
```
∀tombstone record T for key k:
  T is retained for delete.retention.ms milliseconds
  After delete.retention.ms elapses, the Log Cleaner may remove T and all prior
  records for k from the log
  Before delete.retention.ms elapses: T and k's prior records are retained
```
**Source:** https://kafka.apache.org/documentation/#compaction
**Counterexample:** A tombstone is removed immediately (within delete.retention.ms). A new consumer starting from the beginning of the log never sees the tombstone and incorrectly assumes the last value for k is still valid.

### INV-KAFKA-003: Log Compacted Topic Offset Continuity
**Core Invariant:**
```
∀topic with log.compaction enabled:
  Offsets within a segment are monotonically increasing
  After compaction, some offsets may be "cleaned" (missing)
  A consumer cannot rely on contiguous offsets and must handle gaps
  The Log Cleaner replaces cleaned segments with new segments containing only
  the last offset for each key
```
**Source:** https://kafka.apache.org/documentation/#compaction
**Counterexample:** A consumer that checks `if next_offset == current_offset + 1` as a validity check — compaction causes gap offsets, and the consumer incorrectly assumes data loss.

### INV-KAFKA-004: Log Cleaner Segments Invariant
**Core Invariant:**
```
∀segment S being compacted:
  S contains records for keys {k₁, ..., kₙ}
  After compaction: S is replaced by a segment containing at most n records
    (one per key, the most recent by offset)
  All records in the output segment have strictly increasing offsets
  The offset-to-position mapping in the index is rebuilt for the output segment
```
**Source:** https://kafka.apache.org/documentation/#compaction
**Counterexample:** A compaction run that produces an output segment with records in non-offset order — the index cannot binary-search correctly, and a consumer reading forward by offset gets records out of order.

### INV-KAFKA-005: Log Cleaner Idempotency
**Core Invariant:**
```
compaction(compaction(log)) = compaction(log)
  (Compaction is idempotent — applying it twice produces the same result as once)
```
**Source:** Apache Kafka documentation, Log Compaction section
**Counterexample:** A compaction run that keeps some records that should have been removed (e.g., duplicate key with older offset), and a second compaction removes them — the two results differ, meaning compaction is not idempotent and may oscillate.

## Producer Idempotency and Exactly-Once Semantics

### INV-KAFKA-006: Idempotent Producer Sequence Number Invariant
**Core Invariant:**
```
∀idempotent producer P with producer_id = pid, epoch = e:
  The broker tracks per-(pid, partition) the last 5 sequence numbers received
  Each request carries (pid, epoch, sequence_number):
    if sequence_number = last_seq + 1 → accept (new record)
    if sequence_number in [last_seq - 4, last_seq] → accept (duplicate, no-op)
    otherwise → OutOfOrderSequenceException
```
**Source:** https://kafka.apache.org/documentation/#semantics
**Counterexample:** A retry that sends the same batch twice — the broker sees the same sequence_number as the already-committed batch and returns success for the duplicate without duplicating the record.

### INV-KAFKA-007: Idempotent Producer Epoch Invariant
**Core Invariant:**
```
∀producer with pid, ∀partition:
  The broker maintains the highest epoch e_seen for each pid
  Producer requests with epoch e_new:
    e_new = e_seen → accepted (within same producer lifecycle)
    e_new > e_seen → fenced: all pending writes with epoch < e_new are aborted
    e_new < e_seen → rejected (stale epoch)
```
**Source:** https://kafka.apache.org/documentation/#semantics
**Counterexample:** A producer crashes and restarts with the same pid but a new epoch. It re-sends records that were in-flight before the crash. The broker accepts them because the epoch matches the new lifecycle, but some records from the old epoch may still be in the log — causing duplicates if the first attempt succeeded.

### INV-KAFKA-008: Exactly-Once Semantics (EOS) Transaction Invariant
**Core Invariant:**
```
Given a transaction T with transaction_id = tid, producer_id = pid:
  T.begin(): coordinator marks T as ONGOING
  T.add(partition): coordinator adds partition to transaction
  T.prepare_commit(): coordinator writes PREPARE_COMMIT marker to transaction log
  T.commit(): coordinator writes COMMIT marker to all transaction partitions
  Outcome: records in T are atomically visible to consumers with isolation_level=read_committed
  If T aborts: ABORT marker written, records hidden from read_committed consumers
```
**Source:** https://kafka.apache.org/documentation/#semantics
**Counterexample:** A transactional produce that writes to partitions A, B, C. The producer crashes after writing to A and B but before C. The transaction coordinator aborts the transaction — the records in A and B must be invisible to read_committed consumers, even though they were written to the log.

### INV-KAFKA-009: Transaction Coordinator Fencing Invariant
**Core Invariant:**
```
∀transactional producer with transactional_id = tid:
  Only one producer instance with a given tid may be active at any time
  The transaction coordinator assigns a new producer epoch on each initTransactions()
  Calls from a producer with a stale epoch are rejected (fenced)
  The fencing guarantees that zombie producers cannot write within a transaction
```
**Source:** https://kafka.apache.org/documentation/#semantics
**Counterexample:** Producer A starts a transaction, then blocks for 30 seconds. A new producer B with the same transactional_id starts, gets a new epoch, and begins a transaction. Producer A wakes up and tries to write — the broker rejects A's writes because its epoch is stale.

### INV-KAFKA-010: Read-Committed Consumer Offset Invariant
**Core Invariant:**
```
∀consumer with isolation_level=read_committed:
  The consumer tracks the Last Stable Offset (LSO) for each partition
  LSO = first offset of the first incomplete (OPEN/ABORT/PREPARE) transaction
  The consumer reads only up to LSO - 1 (all committed records)
  ABORT markers hide uncommitted records from the consumer
```
**Source:** https://kafka.apache.org/documentation/#semantics
**Counterexample:** A read_committed consumer that reads past the LSO — it would see records from an uncommitted transaction. If the transaction later aborts, those records should be invisible but the consumer already consumed them.

## Consumer Group Rebalancing

### INV-KAFKA-011: Consumer Group Protocol Invariant
**Core Invariant:**
```
∀consumer group G with members {c₁, ..., cₙ}:
  The group coordinator (one broker) manages the state machine:
    state ∈ {Empty, PreparingRebalance, AwaitingSync, Stable}
  state transitions:
    Empty → Stable (first join)
    Stable → PreparingRebalance (member join/leave/timeout, partition change)
    PreparingRebalance → AwaitingSync (all members joined within rebalance.timeout.ms)
    AwaitingSync → Stable (group leader provides assignment, all members sync)
```
**Source:** https://kafka.apache.org/documentation/#consumer-group-rebalancing
**Counterexample:** A group coordinator crash during PreparingRebalance — on recovery (if using Kafka 2.5+ with static quorum), the session is lost and the group transitions back to Empty. If using older "sticky" coordinator, the ephemeral state is lost.

### INV-KAFKA-012: Static Group Membership Invariant
**Core Invariant:**
```
∀consumer with group.instance.id set:
  Consumer receives a group.instance.id (persistent identity)
  On leave: coordinator retains the member for session.timeout.ms
  On return within session timeout: member rejoins without triggering rebalance
  On exceed session timeout: member is removed, rebalance triggered
```
**Source:** https://kafka.apache.org/documentation/#consumer-group-rebalancing
**Counterexample:** A consumer with static membership restarts within its session timeout. Without static membership, a rebalance of all consumers would trigger. With static membership, only the rejoining consumer reconnects without disrupting the rest of the group.

### INV-KAFKA-013: Cooperative Sticky Rebalance Invariant
**Core Invariant:**
```
∀consumer group using CooperativeStickyAssignor:
  Rebalance proceeds in multiple rounds to minimize partition movement:
    Round 1: coordinator identifies partitions that MUST move (revoke needed)
    Round 2+: consumers revoke only the partitions that need to move
  Each round converges: monotonically decreasing set of "unassigned" partitions
  Final stable assignment: partitions are evenly distributed (sticky across rebalances)
```
**Source:** https://kafka.apache.org/documentation/#consumer-group-rebalancing, KIP-429
**Counterexample:** Cooperative sticky rebalancing where consumer C1 has partitions [P1, P2, P3, P4] and C2 joins. The first round revokes only P1, P2 from C1 on rebalance 1. In the second round, C2 gets P1, P2 but C1 still has P3, P4 — no partition thrashing occurs.

## Partition Assignment

### INV-KAFKA-014: Partition Assignment Invariant (Single Subscription)
**Core Invariant:**
```
∀consumer group G subscribed to topic T with partitions [P₁, ..., Pₙ] and consumers [C₁, ..., Cₘ]:
  Each partition Pᵢ is assigned to exactly one consumer Cⱼ in the group
  Each consumer Cⱼ is assigned at least one partition or zero
  Σ_assigned(Cⱼ) = total partitions N
  Each partition is uniquely owned (no partition assigned to two consumers)
```
**Source:** https://kafka.apache.org/documentation/#consumer-group-rebalancing
**Counterexample:** After a rebalance, partition P1 is assigned to both C1 and C2 — both consumers process the same messages, violating the at-most-once or exactly-once processing semantics.

### INV-KAFKA-015: Sticky Partition Assignment Invariant
**Core Invariant:**
```
Given rebalance R from assignment A to A':
  The StickyAssignor maximizes the intersection of assignments:
    maximize Σ |A(Cⱼ) ∩ A'(Cⱼ)| for all consumers Cⱼ
  Subject to: balanced distribution (partition count differs by at most 1)
```
**Source:** https://kafka.apache.org/documentation/#consumer-group-rebalancing, StickyAssignor
**Counterexample:** A rebalance where consumer C1 had partitions [P1, P2, P3, P4] and the rebalance assigns [P5, P6, P7, P8] to C1 while [P1, P2, P3, P4] goes to other consumers — this is not sticky.

## ISR (In-Sync Replicas)

### INV-KAFKA-016: ISR Replication Invariant
**Core Invariant:**
```
Given topic partition with replication-factor = N:
  min.insync.replicas = R (R ≤ N)
  Leader accepts writes iff count(ISR) ≥ R
  Replica in ISR iff replica.offset ≥ leader.offset - replica.lag.max.max.messages
    AND replica.last_caught_up_time ≥ now - replica.lag.time.max.ms
  If replica falls out of ISR: it continues fetching but cannot confirm writes
```
**Source:** https://kafka.apache.org/documentation/#replication
**Counterexample:** N=3, R=2. Two replicas (including leader) are in ISR. The third replica falls behind by 10,000 messages (beyond max lag). If the leader fails before the replicas catch up, acks=all writes that were confirmed to with only R=1 (leader only) are lost.

### INV-KAFKA-017: Unclean Leader Election
**Core Invariant:**
```
Given topic partition with unclean.leader.election.enable = false:
  A leader is elected from ISR only
  If no ISR replica is available → partition is UNAVAILABLE (no leader elected)
  With unclean.leader.election.enable = true:
  A leader may be elected from non-ISR replicas (data loss risk)
```
**Source:** https://kafka.apache.org/documentation/#replication
**Counterexample:** All three replicas of a partition are down. Two come back (one in ISR, one not). ISR replica has all data. Non-ISR replica is behind by 100 messages. Unclean leader election picks the non-ISR replica — 100 acknowledged writes are lost.

## KRaft (Kafka Raft)

### INV-KAFKA-018: KRaft Quorum Invariant
**Core Invariant:**
```
Given KRaft cluster of N voters (controller nodes):
  Quorum = floor(N/2) + 1
  Leader requires support from a quorum of voters
  Committed entry = replicated to a quorum of voters
  Each voter has at most one vote per term
  Leader must have the latest log (as determined by last log term + offset)
```
**Source:** https://kafka.apache.org/documentation/#kraft, KIP-595
**Counterexample:** A KRaft leader thinks it has quorum but only 2 of 5 voters are reachable. It continues to commit metadata entries. When the partition heals, the 2 voters have metadata that the 3 other voters never saw — consistency violation.

### INV-KAFKA-019: KRaft Metadata Log Invariant
**Core Invariant:**
```
The metadata log in KRaft replaces ZooKeeper:
  All cluster metadata (brokers, topics, partitions, configs, quotas, ACLs)
  is stored in a single KRaft metadata log replicated across controller nodes
  Each metadata record is committed via Raft consensus
  New brokers (and brokers restarting) catch up via the metadata log
```
**Source:** https://kafka.apache.org/documentation/#kraft
**Counterexample:** A broker starts up and reads the metadata log from a KRaft follower that is behind by 100 records. The broker registers with a stale partition assignment and serves traffic for partitions it should not own.

## Segment and Index

### INV-KAFKA-020: Segment File Invariant
**Core Invariant:**
```
Each partition is divided into segments:
  Active segment: currently being written to
  Closed segments: immutable, read-only
  segment.bytes (default 1GB): max segment size before rolling
  segment.ms: max segment lifetime before rolling
  segment.index.bytes (default 10MB): max index size
  Rolling: close active segment → create new active segment
```
**Source:** https://kafka.apache.org/documentation/#configuration
**Counterexample:** A segment that is not closed when the broker crashes — on recovery, the segment may be partially written, and the last record is truncated at the last valid offset+checksum boundary.

### INV-KAFKA-021: Offset Index Invariant
**Core Invariant:**
```
∀segment S with base_offset b and index file I:
  I is a sparse index mapping relative_offset → file_position
  I contains one entry per log.interval.bytes of segment data (default: 4096 bytes)
  I entries are monotonically increasing in both offset and position
  Searching: binary search on I → find closest offset ≤ target → scan segment from there
```
**Source:** https://kafka.apache.org/documentation/#configuration
**Counterexample:** An index entry with position 1000 at relative_offset 10, and position 900 at relative_offset 20 — the decreasing position violates monotonicity, causing binary search to fail.

### INV-KAFKA-022: Time Index Invariant
**Core Invariant:**
```
∀segment S with base_offset b and time index file TI:
  TI maps timestamp → offset
  TI is monotonically increasing in timestamp (or offset on timestmap tie)
  Searching: binary search on TI → find first offset where timestamp ≥ query_time
  If no timestamp ≥ query_time: return segment's largest offset
```
**Source:** https://kafka.apache.org/documentation/#configuration
**Counterexample:** A time index entry with timestamp 1000 → offset 20, and a subsequent entry with timestamp 900 → offset 25 — the decreasing timestamp violates monotonicity, and timestamp-based search returns wrong offsets.

## Producer Batching

### INV-KAFKA-023: Producer Batch Invariant
**Core Invariant:**
```
∀producer batch B sent to broker:
  B contains records ordered by offset within partition
  B is compressed according to producer compression.type
  B is sent atomically: either all records in B are committed or none are
  linger.ms: max time to wait before sending a batch (trade latency vs throughput)
  batch.size: max bytes of a batch (linger beyond this forces immediate send)
```
**Source:** https://kafka.apache.org/documentation/#producer-batching
**Counterexample:** A producer batch of 10 records for the same partition that is split across two requests — if the first request succeeds and the second fails, 5 records are committed and 5 are lost, violating the atomic batch assumption.

