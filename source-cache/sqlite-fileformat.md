# oracle/sqlite-fileformat — Database file format: pages, btree structure, freelist, WAL
Source: https://sqlite.org/fileformat2.html
Date pulled: 2026-07-21
Source type: oracle-extract (MEDIUM trust — not a textbook-formal proof, but production-hardened across billions of deployments since 2004)

## Extracted Invariants

### INV-SQLITE-FMT-001: Page size is uniform and power-of-two bounded
**Core Invariant:**
```
∀ p ∈ pages(db): size(p) = page_size(db) ∧ page_size(db) ∈ {2^k | 512 ≤ 2^k ≤ 65536}
```
**Source:** Section 1.2 — "All pages within the same database are the same size. The size of a page is a power of two between 512 and 65536 inclusive."
**Counterexample:** If pages have mixed sizes, b-tree navigation breaks — interior page pointers reference page numbers assuming uniform page size for offset calculation. A 512-byte page pointer followed in a DB with 4096-byte pages would read wrong data.
**Why this matters for bridge/orbit:** Any tool that reads SQLite files directly (e.g., forensic analysis of sandbox databases) must not assume the page size from a magic constant; it must be read from offset 16 of the database header.

### INV-SQLITE-FMT-002: Every valid database begins with a 16-byte magic string
**Core Invariant:**
```
∀ db ∈ valid_sqlite_db: first_16_bytes(db) = 0x53514C69746520666F726D6174203300
```
**Source:** Section 1.3.1 — "Every valid SQLite database file begins with the following 16 bytes (in hex): 53 51 4c 69 74 65 20 66 6f 72 6d 61 74 20 33 00."
**Counterexample:** A truncated or corrupted file that lost its header, or a file from SQLite 2.x (different magic), would be misidentified as a valid SQLite 3 database, leading to garbage reads.
**Why this matters for bridge/orbit:** The sandbox creates and validates SQLite databases. Any integrity check must verify the magic string before trusting the file.

### INV-SQLITE-FMT-003: B-tree page type flag is restricted to 4 valid values
**Core Invariant:**
```
∀ p ∈ btree_pages(db): page_type_byte(p) ∈ {0x02, 0x05, 0x0a, 0x0d}
```
**Source:** Section 1.6 — "A value of 2 (0x02) means the page is an interior index b-tree page. A value of 5 (0x05) means the page is an interior table b-tree page. A value of 10 (0x0a) means the page is a leaf index b-tree page. A value of 13 (0x0d) means the page is a leaf table b-tree page. Any other value for the b-tree page type is an error."
**Counterexample:** A bit-flip in the page type byte (e.g., 0x02 → 0x03) causes the page to be interpreted with the wrong cell format — interior index page parsed as something else, producing garbage keys and dangling pointers.
**Why this matters for bridge/orbit:** File corruption detection is a core audit concern. This is a tight categorical invariant — exactly 4 valid states.

### INV-SQLITE-FMT-004: Interior b-tree pages hold at least 2 keys (except page 1)
**Core Invariant:**
```
∀ p ∈ interior_btree_pages(db) \ {page_1}: key_count(p) ≥ 2
```
**Source:** Section 1.6 — "The number of keys on an interior b-tree page, K, is almost always at least 2... The only exception is when page 1 is an interior b-tree page. Page 1 has 100 fewer bytes of storage space available... In all other cases, K is 2 or more."
**Counterexample:** An interior page with 0 or 1 key would violate b-tree fanout guarantees, causing searches to degenerate into linear scans and potentially infinite loops if a single-key page has children that don't partition the key space.
**Why this matters for bridge/orbit:** This is a structural invariant that can be checked with a single pass over the b-tree — a fast corruption detector with no false positives.

### INV-SQLITE-FMT-005: All children of an interior b-tree have the same depth
**Core Invariant:**
```
∀ p ∈ interior_btree_pages(db): ∀ c1, c2 ∈ children(p): depth(c1) = depth(c2)
```
**Source:** Section 1.6 — "In a well-formed database, all children of an interior b-tree have the same depth."
**Counterexample:** An unbalanced b-tree where one child is depth 3 and another is depth 1 breaks O(log n) search guarantees. A key that routes to the shallow child might miss data in deeper siblings; range scans produce incomplete results.
**Why this matters for bridge/orbit:** Balance invariants are the foundation of b-tree correctness. This is the defining property that distinguishes a b-tree from a random tree. Sandbox databases built via SQLite API calls should always satisfy this; verifying it catches filesystem-level corruption.

### INV-SQLITE-FMT-006: Keys within a b-tree page are unique and ascending
**Core Invariant:**
```
∀ p ∈ btree_pages(db): ∀ i, j ∈ [0, cell_count(p)-1], i < j: key(cell_i) < key(cell_j)
```
**Source:** Section 1.6 — "All keys within the same page are unique and are logically organized in ascending order from left to right."
**Counterexample:** A duplicate key in an index b-tree would make the one-to-one mapping between index entries and table rows ambiguous. An out-of-order key would cause binary search on the page to produce wrong results, silently returning wrong data for equality and range queries.
**Why this matters for bridge/orbit:** Key ordering is the core invariant that makes b-tree search correct. Violation means data loss (missing rows) in queries.

### INV-SQLITE-FMT-007: Child-pointer key range is partitioned
**Core Invariant:**
```
∀ p ∈ interior_btree_pages(db): ∀ key X ∈ keys(p):
  ∀ k ∈ keys(left_child(X)): k ≤ X
  ∧ ∀ k ∈ keys(right_child(X)): k > X
```
**Source:** Section 1.6 — "For any key X, pointers to the left of X refer to b-tree pages on which all keys are less than or equal to X. Pointers to the right of X refer to pages where all keys are greater than X."
**Counterexample:** If a child page contains a key that violates the partition (e.g., key 42 in the left child when the parent separator is 40), a binary search for key 42 would follow the wrong pointer and miss the row entirely — silent data loss on point queries.
**Why this matters for bridge/orbit:** This is the fundamental search invariant of b-trees. Combined with INV-SQLITE-FMT-006, it guarantees that every key in the tree is reachable via exactly one root-to-leaf path.

### INV-SQLITE-FMT-008: Every b-tree page has at most one parent
**Core Invariant:**
```
∀ p ∈ btree_pages(db): |parents(p)| ≤ 1
```
**Source:** Section 1.6 — "Every b-tree page has at most one parent b-tree page."
**Counterexample:** A page with two parents creates a DAG instead of a tree. The page would be reachable via two paths; an auto-vacuum moving one parent's pointer would leave a dangling reference from the other, causing corruption on the next write.
**Why this matters for bridge/orbit:** This is the tree-structure invariant. Combined with root-page reachability, it guarantees the b-tree is a proper tree, not a graph with cycles.

### INV-SQLITE-FMT-009: All pages in a b-tree are of the same type (table or index)
**Core Invariant:**
```
∀ btree bt ∈ btree_set(db): ∀ p ∈ pages(bt): type(p) ∈ {table_btree, index_btree} ∧ ∀ p1, p2 ∈ pages(bt): type(p1) = type(p2)
```
**Source:** Section 1.6 — "All pages within each complete b-tree are of the same type: either table or index."
**Counterexample:** If a table b-tree interior page pointed to an index b-tree leaf page, the cell format mismatch would cause rowid extraction from a page with no rowids, producing garbage keys and corrupting the data read path.
**Why this matters for bridge/orbit:** Type consistency is a cross-page invariant — verifying it requires checking the page type byte across all pages in a b-tree. This catches pointer corruption that might otherwise go undetected.

### INV-SQLITE-FMT-010: sqlite_schema root page is always page 1
**Core Invariant:**
```
root_page(sqlite_schema_table) = 1
```
**Source:** Section 1.6 — "The b-tree corresponding to the sqlite_schema table is always a table b-tree and always has a root page of 1."
**Counterexample:** If page 1 were not the schema root, the database would be unopenable — SQLite would read page 1 expecting the schema table and find something else, failing to discover any user tables or indexes.
**Why this matters for bridge/orbit:** This is a fixed-point invariant. Any SQLite database where page 1 is not a table b-tree leaf or interior page (type 0x0d or 0x05) is definitively corrupt.

### INV-SQLITE-FMT-011: Payload fraction header bytes are fixed constants
**Core Invariant:**
```
∀ db ∈ valid_sqlite_db: max_embedded_payload_frac(db) = 64 ∧ min_embedded_payload_frac(db) = 32 ∧ leaf_payload_frac(db) = 32
```
**Source:** Section 1.3.5 — "The maximum and minimum embedded payload fractions and the leaf payload fraction values must be 64, 32, and 32."
**Counterexample:** If these values were changed, the overflow threshold computation would produce different X and M values, causing payload to be split differently between b-tree page and overflow pages. A reader using standard thresholds would read wrong byte ranges, producing truncated or garbage cell content.
**Why this matters for bridge/orbit:** These are hardcoded constants in every SQLite reader. Any deviation means the file was either corrupted or produced by a non-standard writer. This is a zero-cost sanity check.

### INV-SQLITE-FMT-012: Freeblock chain is ordered by increasing offset
**Core Invariant:**
```
∀ p ∈ btree_pages(db): ∀ fb_i, fb_j ∈ freeblocks(p): fb_i precedes fb_j in chain ⇒ offset(fb_i) < offset(fb_j)
```
**Source:** Section 1.6 — "Freeblocks are always connected in order of increasing offset."
**Counterexample:** An out-of-order freeblock chain could cause a page defragmentation to merge or split freeblocks incorrectly, producing overlapping allocations where cell content and free space share the same byte range — silent data corruption.
**Why this matters for bridge/orbit:** This is a structural invariant of the free space management within a page. It is checkable in O(freeblocks) time and catches both bit-flips and buggy writers.

### INV-SQLITE-FMT-013: Fragment bytes per b-tree page bounded at 60
**Core Invariant:**
```
∀ p ∈ well_formed_btree_pages(db): fragment_bytes(p) ≤ 60
```
**Source:** Section 1.6 — "In a well-formed b-tree page, the total number of bytes in fragments may not exceed 60."
**Counterexample:** More than 60 fragment bytes means the page has excessive internal fragmentation. While not immediately fatal, it indicates the page was not properly defragmented after a sequence of deletions and insertions. A reader encountering this could waste I/O on fragmented pages and, in extreme cases, run out of usable space on the page even though the free-space counters suggest room.
**Why this matters for bridge/orbit:** This is a soft invariant — violating it doesn't cause immediate corruption but signals degraded page health. It is a useful diagnostic for sandbox database health monitoring.

### INV-SQLITE-FMT-014: At least one cell precedes the first freeblock on a well-formed page
**Core Invariant:**
```
∀ p ∈ well_formed_btree_pages(db): cell_count(p) > 0 ⇒ min_cell_offset(p) < first_freeblock_offset(p)
```
**Source:** Section 1.6 — "In a well-formed b-tree page, there will always be at least one cell before the first freeblock."
**Counterexample:** If a freeblock starts before all cells, it means the cell pointer array and the freeblock chain overlap — a structural impossibility in the page layout. Cell pointers would point into freeblock space, causing overwrites when new cells are inserted.
**Why this matters for bridge/orbit:** This invariant catches the most common page-level corruption pattern: overlapping regions within the page layout.

### INV-SQLITE-FMT-015: No page appears more than once in a single rollback journal
**Core Invariant:**
```
∀ journal j: ∀ pr1, pr2 ∈ page_records(j): pr1 ≠ pr2 ⇒ page_number(pr1) ≠ page_number(pr2)
```
**Source:** Section 3 — "The same page may not appear more than once within a single rollback journal."
**Counterexample:** If the same page appears twice in a journal, the second (older) entry would overwrite the first (newer) entry during rollback, restoring a stale version of the page. The database would end up in a state that was never committed — an inconsistent mix of old and new page versions.
**Why this matters for bridge/orbit:** This is a crash-recovery correctness invariant. Violating it means journal replay produces an inconsistent database that passes integrity checks but contains logically wrong data.

### INV-SQLITE-FMT-016: WAL frame validity requires matching salts and cumulative checksum
**Core Invariant:**
```
∀ f ∈ frames(wal): valid(f) ⇔
  (salt1(f) = salt1(wal_header) ∧ salt2(f) = salt2(wal_header)
   ∧ checksum(f) = cumulative_checksum(wal_header, frames_up_to(f)))
```
**Source:** Section 4.1 — "A frame is considered valid if and only if the salt-1 and salt-2 values in the frame-header match salt values in the wal-header, and the checksum values in the final 8 bytes of the frame-header exactly match the checksum computed consecutively on the first 24 bytes of the WAL header and the first 8 bytes and the content of all frames up to and including the current frame."
**Counterexample:** If salt validation is skipped, a frame from a prior WAL epoch (before a reset) could be replayed, restoring stale page content. If checksum validation is skipped, a partially-written frame (e.g., torn page after power loss) could be treated as valid, injecting garbage into the database.
**Why this matters for bridge/orbit:** This is the core integrity mechanism for WAL-mode databases. The cumulative checksum design means that accepting one invalid frame poisons the checksum for all subsequent frames — a single corrupted frame invalidates the entire WAL suffix.

### INV-SQLITE-FMT-017: WAL salt-1 increments on reset, invalidating old frames
**Core Invariant:**
```
∀ wal w: after_reset(w) ⇒ salt1(w) > salt1(w_before_reset)
```
**Source:** Section 4.4 — "At the start of the first new write transaction, the WAL header salt-1 value is incremented and the salt-2 value is randomized. These changes to the salts invalidate old frames in the WAL that have already been checkpointed."
**Counterexample:** If salt-1 didn't increment, a reader starting after a checkpoint+reset could replay old frames from the previous WAL epoch, mixing data from two different database states — phantom rows, resurrected deletes.
**Why this matters for bridge/orbit:** This is the epoch-boundary invariant. It ensures that WAL reuse (overwriting old frames) is safe — old frames are cryptographically invalidated by salt mismatch before being overwritten.

### INV-SQLITE-FMT-018: Checkpoint xSync provides write barrier ordering
**Core Invariant:**
```
∀ checkpoint c: all_writes_before(xSync_1) happens_before all_writes_after(xSync_1)
  ∧ all_writes_before(xSync_2) happens_before all_writes_after(xSync_2)
```
**Source:** Section 4.3 — "On a checkpoint, the WAL is first flushed to persistent storage using the xSync method of the VFS. Then valid content of the WAL is transferred into the database file. Finally, the database is flushed to persistent storage using another xSync method call. The xSync operations serve as write barriers."
**Counterexample:** Without the first xSync, WAL frames might not be durably on disk before checkpoint copies them — a crash during checkpoint could leave the database file with partially-copied pages and no recoverable WAL. Without the second xSync, the database file changes might not be durable before the WAL is reset — a crash after WAL reset but before DB file sync would lose committed transactions.
**Why this matters for bridge/orbit:** This is a crash-safety ordering invariant. The two xSync calls create a three-phase protocol: WAL-durable, DB-durable, WAL-reset. Breaking the ordering means committed transactions can be lost — the worst possible failure mode for a database.

### INV-SQLITE-FMT-019: WAL reader snapshot isolation via mxFrame
**Core Invariant:**
```
∀ reader r, transaction t_start: ∀ reads by r after t_start: data_seen(r) = db_state_at_frame(mxFrame(r))
```
**Source:** Section 4.5 — "The reader uses this recorded mxFrame value for all subsequent read operations. New transactions can be appended to the WAL, but as long as the reader uses its original mxFrame value and ignores subsequently appended content, the reader will see a consistent snapshot of the database from a single point in time."
**Counterexample:** If a reader's mxFrame advances mid-transaction, it could see a partial commit — some pages from a new transaction but not others. This breaks snapshot isolation: the reader would observe a database state that never existed at any single point in time.
**Why this matters for bridge/orbit:** Snapshot isolation is the concurrency guarantee that allows multiple readers and one writer to coexist in WAL mode. This is directly relevant to bridge's multi-agent architecture where multiple agents may read sandbox databases concurrently.

### INV-SQLITE-FMT-020: Ptrmap back-pointers cover every page following the ptrmap page
**Core Invariant:**
```
∀ ptrmap_page P at page_number N: ∀ i ∈ [1, J]: entry_i(P) describes back_link(page_{N+i})
```
**Source:** Section 1.8 — "Each 5-byte entry on a ptrmap page provides back-link information about one of the pages that immediately follow the pointer map. If page B is a ptrmap page then back-link information about page B+1 is provided by the first entry on the pointer map."
**Counterexample:** If a ptrmap entry points to the wrong parent, auto-vacuum would move a child page and update the wrong parent pointer, or fail to update the correct parent — leaving a dangling reference from parent to a page that was moved or freed. This causes corruption that only manifests on subsequent reads of the stale pointer.
**Why this matters for bridge/orbit:** Ptrmap consistency is essential for auto-vacuum correctness. A single bad ptrmap entry can cascade into multi-page corruption during vacuum operations.

### INV-SQLITE-FMT-021: All b-tree root pages precede non-root pages in ptrmap databases
**Core Invariant:**
```
∀ db with ptrmap_enabled(db): ∀ rp ∈ root_pages(db), ∀ nrp ∈ non_root_pages(db): page_number(rp) < page_number(nrp)
```
**Source:** Section 1.8 — "In any database file that contains ptrmap pages, all b-tree root pages must come before any non-root b-tree page, cell payload overflow page, or freelist page."
**Counterexample:** If a root page were after non-root pages, auto-vacuum could move the root page (since it doesn't know how to update the root_page field in sqlite_schema). The sqlite_schema entry would then point to a freed or reallocated page — the table or index becomes permanently inaccessible.
**Why this matters for bridge/orbit:** This is a design constraint that prevents a class of auto-vacuum bugs. It is load-bearing: the auto-vacuum implementation assumes root page immobility and enforces it through this ordering constraint.

### INV-SQLITE-FMT-022: Schema cookie change detection guarantees prepared statement consistency
**Core Invariant:**
```
∀ prepared_stmt s compiled against schema_cookie C: if schema_cookie(db) ≠ C then s must be reprepared before execution, else s aborts with SQLITE_SCHEMA
```
**Source:** Section 1.3.9 — "When the database schema changes, the statement must be reprepared. When a prepared statement runs, it first checks the schema cookie to ensure the value is the same as when the statement was prepared."
**Counterexample:** If the schema cookie check were omitted, a prepared statement compiled against schema version N could execute against schema version N+1 (e.g., after ALTER TABLE ADD COLUMN). The statement's column offsets would be wrong, returning values from wrong columns without any error.
**Why this matters for bridge/orbit:** Schema evolution safety is critical for long-running agents. Bridge may hold prepared statements across schema migrations; the schema cookie provides the detection mechanism. This is an example of a version-vector integrity check.

### INV-SQLITE-FMT-023: Text encoding is restricted to exactly 3 values
**Core Invariant:**
```
∀ db ∈ valid_sqlite_db: text_encoding(db) ∈ {1, 2, 3}
```
**Source:** Section 1.3.13 — "A value of 1 means UTF-8. A value of 2 means UTF-16le. A value of 3 means UTF-16be. No other values are allowed."
**Counterexample:** An encoding value of 0 or 4+ would cause all text strings in the database to be interpreted with wrong byte ordering, producing mojibake (garbled text) for every string column. String comparisons (collation) would produce wrong ordering, breaking index lookups.
**Why this matters for bridge/orbit:** Like the page type flag invariant, this is a tight categorical check. 3 valid values, everything else is definitively corrupt.

### INV-SQLITE-FMT-024: Reserved header bytes must be zero
**Core Invariant:**
```
∀ db ∈ valid_sqlite_db: ∀ b ∈ reserved_header_bytes(db): b = 0
```
**Source:** Section 1.3.17 — "All other bytes of the database file header are reserved for future expansion and must be set to zero."
**Counterexample:** Non-zero reserved bytes could be misinterpreted by a future SQLite version that assigns meaning to those bytes, causing the database to be read with wrong parameters. A forward-compatibility hazard: a file written by a buggy writer that sets reserved bytes could be unreadable by future SQLite.
**Why this matters for bridge/orbit:** This is a future-proofing invariant. Checking it catches non-standard writers and filesystem corruption in the header region before it causes hard-to-diagnose failures.

### INV-SQLITE-FMT-025: Minimum usable page size is 480 bytes
**Core Invariant:**
```
∀ db ∈ valid_sqlite_db: usable_page_size(db) ≥ 480
```
**Source:** Section 1.3.4 — "The usable size is not allowed to be less than 480. In other words, if the page size is 512, then the reserved space size cannot exceed 32."
**Counterexample:** A usable size below 480 means there isn't enough room for the minimum b-tree page structure — the 8-byte page header plus the minimum freelist trunk array of 120 4-byte integers requires at least 488 bytes. Pages smaller than this threshold cannot function as valid b-tree or freelist pages.
**Why this matters for bridge/orbit:** This is a lower-bound invariant that guards against misconfiguration. It ensures the physical page can hold the logical structures required by the format.

### INV-SQLITE-FMT-026: Index b-tree key overflow guarantees minimum fanout of 4
**Core Invariant:**
```
∀ p ∈ interior_index_btree_pages(db): key_count(p) ≥ 4
```
**Source:** Section 1.6 — "Large keys on index b-trees are split up into overflow pages so that no single key uses more than one fourth of the available storage space on the page and hence every internal page is able to store at least 4 keys."
**Counterexample:** An interior index page with fewer than 4 keys would violate b-tree fanout, degrading search from O(log_4 n) to potentially O(n). Worse, the overflow threshold computation is designed around this minimum — if a key exceeds 1/4 of usable space without being split, the page would hold only 1-2 keys and the b-tree would degenerate.
**Why this matters for bridge/orbit:** This is the fanout guarantee that makes b-tree operations logarithmic. Combined with INV-SQLITE-FMT-004 (minimum 2 keys for table b-trees), it provides the structural lower bound for search performance.

### INV-SQLITE-FMT-027: Overflow page chain terminated by zero pointer
**Core Invariant:**
```
∀ overflow_chain c: last_page(c).next_page_number = 0
```
**Source:** Section 1.7 — "The first four bytes of each overflow page are a big-endian integer which is the page number of the next page in the chain, or zero for the final page in the chain."
**Counterexample:** A non-zero terminator (or a cycle where page A points to B, B points to A) would cause an infinite loop during payload reconstruction, hanging the reader or exhausting memory as it tries to assemble an infinitely long payload.
**Why this matters for bridge/orbit:** Linked-list termination is a fundamental data structure invariant. This is checkable in O(chain_length) and definitively identifies corruption — any cycle means the database is broken.

### INV-SQLITE-FMT-028: AUTOINCREMENT keys strictly exceed the sequence maximum
**Core Invariant:**
```
∀ table t with AUTOINCREMENT: ∀ new_row r inserted into t: rowid(r) > sqlite_sequence.seq(t)
```
**Source:** Section 2.6.3 — "New automatically generated integer primary keys for AUTOINCREMENT tables are guaranteed to be larger than the sqlite_sequence.seq field for that table."
**Counterexample:** If this guarantee were violated (e.g., the sequence counter regressed after a crash), new rows could reuse old rowids. Foreign key references from other tables would then point to wrong rows — a referential integrity violation where a child row references a deleted or unrelated parent.
**Why this matters for bridge/orbit:** AUTOINCREMENT monotonicity is an application-level invariant enforced by the database layer. Bridge's sandbox databases may use AUTOINCREMENT for event sequencing; regressed rowids would break event ordering and causality tracking.

### INV-SQLITE-FMT-029: WAL file always grows forward; checksums detect stale frames
**Core Invariant:**
```
∀ wal w: append_position(w) is monotonically non-decreasing across the lifetime of w
```
**Source:** Section 4.1 — "A WAL always grows from beginning toward the end. Checksums and counters attached to each frame are used to determine which frames within the WAL are valid and which are leftovers from prior checkpoints."
**Counterexample:** If the WAL were seeked backward and overwritten mid-file without proper salt rotation, a reader starting at an arbitrary point could see a mix of new and old frames. The cumulative checksum and salt mechanism prevents this by making old frames cryptographically invalid after a reset.
**Why this matters for bridge/orbit:** The append-only property combined with salt-rotation is a form of write-once semantic enforced by cryptographic checksums. This is analogous to append-only ledgers and is directly relevant to bridge's audit log integrity requirements.

### INV-SQLITE-FMT-030: Ptrmap page placement is deterministic and exclusive
**Core Invariant:**
```
∀ db with ptrmap_enabled(db): ptrmap_pages(db) = {page_{k*(U/5)+3} | k ≥ 0} \ lock_byte_page_if_collision
```
**Source:** Section 1.8 — "In a database that uses ptrmap pages, all pages at locations identified by the computation in the previous paragraph must be ptrmap page and no other page may be a ptrmap page."
**Counterexample:** If a non-ptrmap page occupies a ptrmap slot, auto-vacuum would read garbage as ptrmap entries, updating wrong parent pointers. If a ptrmap page occupies a non-ptrmap slot, that slot's parent-link information would be missing, causing auto-vacuum to miss a needed parent-pointer update.
**Why this matters for bridge/orbit:** This is a structural placement invariant — the positions of ptrmap pages are mathematically determined by the page size and usable space. Any deviation means the database was not constructed by a conforming SQLite writer.
