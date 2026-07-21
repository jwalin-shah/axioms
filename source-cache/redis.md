# oracle/redis
Source: Redis internals, redis.io documentation, and Redis source code
Date pulled: 2026-07-21
Sources: https://redis.io/docs/latest/develop/reference/, Redis source: sds.h, sds.c, ziplist.c, t_zset.c, dict.c, intset.c

## SDS (Simple Dynamic Strings)

### INV-REDIS-001: SDS Null-Termination Invariant
**Core Invariant:**
```
∀s ∈ SDS: s.buf[s.len] = '\0'
```
**Source:** SDS (sds.h), Redis source
**Counterexample:** An SDS string that has been directly manipulated via pointer arithmetic without updating the null terminator, causing C-string functions to read past the end of the buffer.

### INV-REDIS-002: SDS Allocation Invariant
**Core Invariant:**
```
∀s ∈ SDS: s.len + s.free + sizeof(sdshdr) + 1 = total_allocated(s)
```
**Source:** SDS (sds.h), Redis source
**Counterexample:** A memory corruption that changes the free or len field without adjusting the total allocation, causing buffer overflows or underutilization.

### INV-REDIS-003: SDS Pre-Allocation Invariant
**Core Invariant:**
```
∀s ∈ SDS, new_len > s.len:
  alloc(new_len) ≥ new_len
  ∧ (new_len < 1MB → alloc = 2 × new_len)
  ∧ (new_len ≥ 1MB → alloc = new_len + 1MB)
```
**Source:** SDS (sds.c), Redis source
**Counterexample:** An append operation that allocates exactly the needed size without headroom, causing O(n²) time for repeated appends.

### INV-REDIS-004: SDS Binary Safety
**Core Invariant:**
```
∀s ∈ SDS, ∀i ∈ [0, s.len - 1]: s.buf[i] ∈ {0x00, ..., 0xFF}
```
**Source:** SDS (sds.h), Redis source
**Counterexample:** Treating an SDS string as a C string and using strlen() to find its length, which would stop at the first embedded null byte.

### INV-REDIS-005: SDS Header Type Selection
**Core Invariant:**
```
header_type(s) = sdshdr5 iff s.len < 2^5
                sdshdr8 iff s.len < 2^8
                sdshdr16 iff s.len < 2^16
                sdshdr32 iff s.len < 2^32
                sdshdr64 otherwise
```
**Source:** SDS (sds.h), Redis source
**Counterexample:** A string of length 500 that uses sdshdr16 (wasting 1 byte) instead of sdshdr8 — the system should always use the smallest possible header.

## Ziplist

### INV-REDIS-006: Ziplist Sentinel Invariant
**Core Invariant:**
```
∀zl ∈ ZipList: zl[zlbytes(zl) - 1] = 0xFF
```
**Source:** ziplist.c, Redis source
**Counterexample:** A ziplist whose last byte is not 0xFF — iterating through the ziplist would not know where to stop.

### INV-REDIS-007: Ziplist Entry Encoding Invariant
**Core Invariant:**
```
∀entry ∈ ZipList:
  string_entry → encoding ∈ {00pppppp, 01pppppp qqqqqqqq, 10000000 32-bit-length}
  integer_entry → encoding ∈ {0xC0 (int16), 0xD0 (int32), 0xE0 (int64), 0xF0 (int24), 0xFE (int8), 0xF1..0xFD (4-bit imm)}
```
**Source:** ziplist.c, Redis source
**Counterexample:** An entry with encoding byte 0xFF (which is reserved for the ziplist end sentinel) appearing in the middle of the list — the iterator would prematurely terminate.

### INV-REDIS-008: Ziplist No Downgrade Cascade Invariant
**Core Invariant:**
```
∀zl: entry size changes across 254-byte boundary → NEXT(entry).prevlen expands 1→5 bytes
  (never shrinks: prevlen shrinks to 1 byte only if the entry is deleted and re-inserted)
```
**Source:** ziplist.c, Redis source
**Counterexample:** A ziplist where an entry shrinks from 300 bytes to 200 bytes and the next entry's prevlen is downgraded from 5 to 1 bytes — a subsequent insert/delete could cause the next entry to grow again, causing flapping O(n²) behavior.

## Skiplist (Sorted Set)

### INV-REDIS-009: Skiplist/Dict Dual Consistency
**Core Invariant:**
```
∀zset ∈ SortedSet:
  |zset| = dict_size(zset.dict) = skiplist_length(zset.skiplist)
  ∧ ∀key ∈ zset: dict[key].score = skiplist_node(key).score
```
**Source:** t_zset.c, Redis source
**Counterexample:** A ZADD that adds a key to the hash table but fails to insert into the skiplist (or vice versa) — ZRANK and ZSCORE would return inconsistent results.

### INV-REDIS-010: Skiplist Geometric Level Distribution
**Core Invariant:**
```
∀node ∈ SkipList: level(node) = geometric(p = 0.25), capped at ZSKIPLIST_MAXLEVEL = 32
```
**Source:** t_zset.c, Redis source
**Counterexample:** A skiplist where all nodes are at level 32 — the skip list degenerates into a linked list with O(n) search time.

### INV-REDIS-011: Skiplist Span Invariant
**Core Invariant:**
```
∀node ∈ SkipList, ∀i ∈ [0, node.level - 1]:
  node.level[i].span = count_nodes_between(node, node.level[i].forward)
```
**Source:** t_zset.c, Redis source
**Counterexample:** A node insertion that updates forward pointers but not the span values — ZRANK and ZREVRANK return incorrect ranks.

## Dict (Hash Table)

### INV-REDIS-012: Dict Incremental Rehashing Invariant
**Core Invariant:**
```
∀d ∈ Dict:
  (d.rehashidx = -1) ⟺ (d.ht[1].size = 0 ∧ d.ht[1].used = 0)
  rehashidx ≥ 0 ⇒ ∀bucket with index < rehashidx: bucket is fully migrated to ht[1] or empty
```
**Source:** dict.c, Redis source
**Counterexample:** A lookup operation that checks both ht[0] and ht[1] but the bucket was already migrated from ht[0] — the key is found in both tables, and the wrong value is returned.

### INV-REDIS-013: Dict Power-of-Two Size Invariant
**Core Invariant:**
```
∀d ∈ Dict: ht[0].size = 2^n ∧ ht[1].size = 2^(n+1) at rehash start
  bucket_index = hash(key) & (size - 1)  // fast modulo via bitwise AND
```
**Source:** dict.c, Redis source
**Counterexample:** A hash table with size 7 (non-power-of-two) — the bitwise AND modulo would produce incorrect bucket indices (masking loses bits).

### INV-REDIS-014: Dict Load Factor Invariant
**Core Invariant:**
```
∀d ∈ Dict: d.ht[0].used / d.ht[0].size ≥ 1 → trigger_rehash(d)
  load_factor ≥ 5 → force_rehash even if dict_can_resize is false
```
**Source:** dict.c, Redis source
**Counterexample:** A hash table with load factor 10 and rehashing disabled — the chains grow to 10 entries per bucket, and lookups degenerate to O(n).

## Intset

### INV-REDIS-015: Intset Strictly Ascending Invariant
**Core Invariant:**
```
∀is ∈ IntSet, ∀i ∈ [0, is.length - 2]: is.contents[i] < is.contents[i + 1]
```
**Source:** intset.c, Redis source
**Counterexample:** An intset with duplicate value 5 — binary search for 5 returns the first instance, but insertion checks for duplicates would fail.

### INV-REDIS-016: Intset Upgrade-Only Invariant
**Core Invariant:**
```
∀is ∈ IntSet: insert(x) with x exceeding current encoding width → upgrade_encoding(is)
  remove(x) where all remaining values fit in narrower encoding → NO downgrade
```
**Source:** intset.c, Redis source
**Counterexample:** An intset with values {0, 1, 2, 3, 2^31} in INT32 encoding. Removing the value 2^31 should keep the encoding at INT32 even though {0, 1, 2, 3} fits in INT16 — downgrading would cause thrashing if values oscillate.

## RDB Persistence

### INV-REDIS-017: RDB Atomic Write Invariant
**Core Invariant:**
```
∀rdb_save: write_to_tempfile → fsync → fclose → rename(temp, dump.rdb) → fsync(containing_dir)
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
**Counterexample:** A crash after writing to tempfile but before rename — the temp file is lost and the old dump.rdb is preserved. If the rename were not atomic, a crash during rename could corrupt the dump.

### INV-REDIS-018: RDB Crash Consistency Invariant
**Core Invariant:**
```
crash_before_rename → old(dump.rdb) unchanged (temp file lost)
crash_after_rename_before_dir_fsync → dump.rdb contains complete data (rename durable on journaling FS)
crash_after_dir_fsync → dump.rdb contains complete snapshot (fully durable)
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
**Counterexample:** A crash during the rename(2) syscall on a non-journaling filesystem — the dump.rdb file could be partially overwritten, containing a mix of old and new data.

## AOF Persistence

### INV-REDIS-019: AOF fsync Guarantee Invariant
**Core Invariant:**
```
∀aof_mode: mode ∈ {always, everysec, no}
  always → fsync every write (0 data loss on crash)
  everysec → fsync via background thread every 1s (≤1s data loss, ≤2s under disk stall)
  no → OS-controlled flush (typ. ≤30s data loss)
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
**Counterexample:** A Redis server with appendfsync everysec that crashes 1.5 seconds after the last fsync — up to 1.5 seconds of writes are lost, exceeding the documented 1s window.

### INV-REDIS-020: AOF Multi-Part Atomicity (Redis 7.0+)
**Core Invariant:**
```
parent → opens new increment file (for ongoing writes)
child → generates new base file (RDB or AOF format)
new_base + new_increment → temp_manifest → atomic_exchange_manifest → delete_old_files
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
**Counterexample:** A crash during AOF rewrite that deletes the old manifest before the new one is fully written — the server restarts with no valid manifest, unable to recover the dataset.

## Replication

### INV-REDIS-021: PSYNC2 Partial Resync Invariant
**Core Invariant:**
```
partial_resync_possible ⟺ replica.replid ∈ {master.replid, master.replid2}
  ∧ replica.offset ∈ [master.repl_backlog_first_byte_offset, master.master_repl_offset]
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/replication/
**Counterexample:** A replica reconnects after a brief network interruption. The master's backlog has wrapped around and the replica's offset is below the backlog's first byte — a full resync is required even though the disconnection was short.

### INV-REDIS-022: Replica Expiry Invariant
**Core Invariant:**
```
∀key with expiry:
  master expires(key) → master propagates DEL to all replicas
  replica NEVER independently expires keys
  replica uses logical clock for READ operations only
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/management/replication/
**Counterexample:** A replica that independently expires a key (without the master's DEL command) while the master still has the key — a client reading from the replica sees a different dataset than the master.

## Eviction

### INV-REDIS-023: LFU Morris Counter Invariant
**Core Invariant:**
```
∀lfu: counter_increment: P[increment] = 1 / (current_counter × lfu_log_factor + 1)
  counter_decay: counter /= 2 every lfu_decay_time_minutes
  high_16_bits: last_decrement_time (minutes since epoch)
  low_8_bits: probabilistic counter (0-255)
```
**Source:** https://redis.io/docs/latest/develop/reference/eviction/
**Counterexample:** An LFU counter that reaches 255 quickly (too many increments) and stays there, losing the ability to distinguish between frequently and rarely accessed keys.

### INV-REDIS-024: Volatile Policy Degeneration Invariant
**Core Invariant:**
```
∀policy ∈ {volatile-lru, volatile-lfu, volatile-lrm, volatile-random, volatile-ttl}:
  |keys_with_TTL| = 0 → policy behaves identically to noeviction
```
**Source:** https://redis.io/docs/latest/develop/reference/eviction/
**Counterexample:** A database with no keys having TTL that uses volatile-lru — writes should be rejected (noeviction behavior), but if the policy tries to evict non-existent TTL keys, it would fail silently.

## Transactions

### INV-REDIS-025: Transaction Serialized Execution
**Core Invariant:**
```
∀multi_session: EXEC → execute_all_queued_commands_sequentially (no interleaving)
  command_fails_during_EXEC → subsequent_commands_still_execute (no rollback)
```
**Source:** https://redis.io/docs/latest/develop/reference/
**Counterexample:** A transaction with INCR on key "foo" (an integer) and INCR on "foo" (now a string due to a previous SET in the same transaction) — the second INCR fails, but subsequent commands continue executing, potentially causing partial updates.

### INV-REDIS-026: WATCH Optimistic Locking Invariant
**Core Invariant:**
```
EXEC_aborts(nil) ⟺ ∃key ∈ {watched_keys}: key modified by other client since WATCH
  same_client_modifications_within_MULTI → do NOT trigger abort
  EXEC (success or abort) → UNWATCH(all) automatically
```
**Source:** https://redis.io/docs/latest/develop/reference/
**Counterexample:** A WATCH on key "counter" that is modified by a different client after the WATCH but the EXEC succeeds — the transaction overwrites the other client's modification without detection (lost update).

## Cluster

### INV-REDIS-027: Hash Slot Mapping Invariant
**Core Invariant:**
```
∀key: slot(key) = CRC16(key) mod 16384, slot ∈ [0, 16383]
  all 16384 slots must be assigned to some master node
  cluster healthy ⟺ all slots assigned to live masters
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
**Counterexample:** A cluster with 16383 slots assigned (one missing) — the cluster is not healthy and any key mapping to the unassigned slot receives a CLUSTERDOWN error.

### INV-REDIS-028: Cluster Slot Migration Atomicity
**Core Invariant:**
```
MIGRATE command moves key atomically:
  dest ACKNOWLEDGES receipt → source DELETES
  key exists on exactly one node throughout migration
  new keys for migrating slot → created on destination (never source)
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
**Counterexample:** A key migration where the destination acknowledges but the source crashes before deleting — the key exists on both nodes, causing duplicate keys after failover.

### INV-REDIS-029: Cluster Configuration Epoch Monotonicity
**Core Invariant:**
```
configuration_epoch(C) strictly monotonically increasing
  epoch_increment_on_failover
  highest_epoch_wins_in_split_brain
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
**Counterexample:** A network partition where both sides create a new configuration epoch and the same value is assigned — the side with the lower epoch's configuration is discarded, and its writes are lost.

### INV-REDIS-030: Cluster Strong Consistency NOT Guaranteed
**Core Invariant:**
```
master_acks_write_to_client → master_replicates_to_replicas asynchronously
  write_loss_possible_if_master_crashes_before_replication
  WAIT(N_replicas) reduces window but does NOT provide strong consistency
```
**Source:** https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/
**Counterexample:** A client writes to master, gets ACK, then master crashes before the write reaches any replica. The replica is promoted and the write is permanently lost.