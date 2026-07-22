# oracle/postgresql-planner-stats — Query planner statistics and cost estimation

Source: https://www.postgresql.org/docs/current/planner-stats.html
Date pulled: 2026-07-21

## Extracted Invariants

### INV-PGPLS-001: Planner Independence Assumption
**Core Invariant:**
```
For all WHERE clauses with multiple conditions on different columns:
  selectivity(cond_1 AND cond_2) = selectivity(cond_1) * selectivity(cond_2)
```
**Source:** Section 14.2.2 Extended Statistics, opening paragraph: "The planner normally assumes that multiple conditions are independent of each other, an assumption that does not hold when column values are correlated."
**Counterexample:** Given a zipcodes table where city and zip are correlated, a query `WHERE city = 'San Francisco' AND zip = '94105'` will produce an underestimate of result size because the planner multiplies the individual selectivities. In the worst case, this causes the planner to choose a nested-loop join instead of a hash join, turning a millisecond query into a multi-second one.
**Why this matters for bridge/orbit:** Bridge's Neo4j queries and orbit's session dispatch queries both involve multi-column filters. If the underlying PostgreSQL tables have correlated columns, the planner will produce bad plans unless extended statistics are created. This is a silent performance degradation, not a correctness bug — the most dangerous kind.

---

### INV-PGPLS-002: Functional Dependency Definition
**Core Invariant:**
```
For all column pairs (a, b):
  b is functionally dependent on a
    iff
  not exists two rows r1, r2 such that r1.a = r2.a AND r1.b != r2.b
```
**Source:** Section 14.2.2.1 Functional Dependencies: "We say that column b is functionally dependent on column a if knowledge of the value of a is sufficient to determine the value of b, that is there are no two rows having the same value of a but different values of b."
**Counterexample:** If zip code fully determines city (coefficient 1.0), a query `WHERE zip = '94105' AND city = 'San Francisco'` has the same selectivity as `WHERE zip = '94105'` alone. Without dependency statistics, the planner multiplies the two selectivities, underestimating by up to the inverse of the city selectivity. A fully normalized database would have this dependency, but denormalized schemas (common in analytics workloads) violate it.
**Why this matters for bridge/orbit:** Bridge's knowledge graph stores denormalized data from multiple sources. Columns like `source_type` and `source_version` are functionally dependent in practice. Without dependency statistics, bridge's reporting queries will get systematically worse plans as the corpus grows.

---

### INV-PGPLS-003: Functional Dependency Compatibility Assumption (Unsound)
**Core Invariant:**
```
When functional dependency statistics are used:
  planner assumes conditions on dependent columns are compatible
  (i.e., the conjunction is satisfiable)
```
**Source:** Section 14.2.2.1.1 Limitations of Functional Dependencies: "When estimating with functional dependencies, the planner assumes that conditions on the involved columns are compatible and hence redundant. If they are incompatible, the correct estimate would be zero rows, but that possibility is not considered."
**Counterexample:** `SELECT * FROM zipcodes WHERE city = 'San Francisco' AND zip = '90210'` — San Francisco's zip is not 90210, so the true result is 0 rows. But the planner sees the functional dependency (city determines zip 42% of the time) and disregards the zip clause, producing a non-zero estimate. This is a soundness violation: the planner may choose an index scan when a seq scan would be correct (or vice versa), but will never incorrectly return zero rows.
**Why this matters for bridge/orbit:** If bridge issues queries with contradictory filter conditions (e.g., from conflicting user inputs or buggy query construction), the planner will not detect the contradiction and will return a non-zero row estimate. The query will still execute correctly (returning 0 rows), but the plan will be wrong. This is a defense-in-depth concern: the planner is not a correctness checker; it's an optimizer.

---

### INV-PGPLS-004: Statistics Are Always Approximate
**Core Invariant:**
```
For all tables t:
  t.reltuples is an approximation, not an exact count
  t.reltuples can be stale (updated only by VACUUM, ANALYZE, or DDL)
  The planner scales reltuples to match current physical table size
```
**Source:** Section 14.2.1 Single-Column Statistics: "For efficiency reasons, reltuples and relpages are not updated on-the-fly, and so they usually contain somewhat out-of-date values. They are updated by VACUUM, ANALYZE, and a few DDL commands such as CREATE INDEX. ... In any case, the planner will scale the values it finds in pg_class to match the current physical table size, thus obtaining a closer approximation."
**Counterexample:** After a bulk INSERT of 1M rows without a subsequent ANALYZE, `reltuples` still reports the old count. The planner scales the value based on physical table size, but this scaling is itself a heuristic. If the planner underestimates row count by 10x, it may choose a nested-loop join over a hash join. If it overestimates by 10x, it may choose a seq scan over an index scan. Both produce correct results but with potentially catastrophic performance.
**Why this matters for bridge/orbit:** Bridge's axiom ingestion pipeline does bulk INSERTs. Without explicit ANALYZE after ingestion, the planner will use stale statistics. The scaling heuristic helps but is not guaranteed to be accurate. This is a known failure mode: batch data loads followed by query performance regressions until auto-ANALYZE kicks in.

---

### INV-PGPLS-005: Statistics Visibility Restriction
**Core Invariant:**
```
For all users u:
  If u is not a superuser
    then u CANNOT read pg_statistic directly
    and u CAN read pg_stats, but only rows for tables u can read
```
**Source:** Section 14.2.1: "pg_stats is readable by all, whereas pg_statistic is only readable by a superuser. (This prevents unprivileged users from learning something about the contents of other people's tables from the statistics. The pg_stats view is restricted to show only rows about tables that the current user can read.)"
**Counterexample:** An unprivileged user who can read `pg_statistic` could infer the distribution of values in a table they cannot read — e.g., knowing that `most_common_vals` for a `salary` column includes `[100000, 200000]` leaks information about the table's contents. This is a side-channel information leak through metadata.
**Why this matters for bridge/orbit:** Bridge runs with a dedicated database user. If bridge ever needs to inspect planner statistics (e.g., for self-diagnosis of query performance), it must use `pg_stats`, not `pg_statistic`. Conversely, if orbit's sandbox isolation leaks `pg_stats` access to a sandboxed process, that process could infer table contents it shouldn't see.

---

### INV-PGPLS-006: Extended Statistics Sampling Consistency
**Core Invariant:**
```
For all ANALYZE operations:
  extended_statistics_sample = same_sample AS single_column_statistics_sample
```
**Source:** Section 14.2.2: "ANALYZE computes extended statistics based on the same sample of table rows that it takes for computing regular single-column statistics."
**Counterexample:** If extended statistics were computed from a different sample than single-column statistics, the dependency coefficients and MCV frequencies would be inconsistent with the per-column statistics. This would cause the planner to combine incompatible estimates, potentially producing a selectivity > 1.0 or < 0.0. The shared-sample invariant prevents this class of inconsistency.
**Why this matters for bridge/orbit:** This is a data-integrity invariant at the statistics-collection layer. It's an example of the general principle: "Correlated estimates must be derived from the same sample." This applies to any system that computes joint distributions — including bridge's own knowledge graph statistics.

---

### INV-PGPLS-007: Multivariate MCV Base Frequency as Correlation Detector
**Core Invariant:**
```
For all multivariate MCV entries (v1, v2, ..., vn):
  base_frequency(v1, v2, ..., vn) = product(per_column_frequency(v_i))
  If actual_frequency >> base_frequency: columns are positively correlated
  If actual_frequency << base_frequency: columns are negatively correlated
```
**Source:** Section 14.2.2.3 Multivariate MCV Lists: The example shows `base_frequency` of Washington,DC = 0.0027% vs actual frequency 0.35%, "resulting in two orders of magnitude under-estimates."
**Counterexample:** The Washington,DC example: simple per-column frequencies multiply to 0.0027%, but the actual joint frequency is 0.35% — a 130x underestimate. A query `WHERE city = 'Washington' AND state = 'DC'` would be estimated as 130x fewer rows than reality, potentially causing the planner to choose a nested-loop join where a hash join is needed.
**Why this matters for bridge/orbit:** Bridge's knowledge graph has natural correlations (axiom category + source type, verification status + source trust level). If these correlations are strong but not captured by extended statistics, bridge's analytical queries (e.g., "find all VERIFIED axioms from high-trust sources in category X") will get systematically bad plans.

---

## Constraints (Non-Invariant Design Rules)

### C-PGPLS-001: Statistics Target Default
The default `default_statistics_target` is 100 entries for `most_common_vals` and `histogram_bounds`. Raising it improves accuracy for irregular distributions at the cost of storage and computation time. This is a tunable knob, not an invariant — the system remains correct at any setting.

### C-PGPLS-002: Extended Statistics Are Opt-In
Extended statistics (dependencies, ndistinct, MCV) are not computed automatically. They must be explicitly created via `CREATE STATISTICS`. This is a design choice to avoid the combinatorial explosion of column combinations. The invariant is that *without* explicit DDL, the planner operates under the independence assumption.

### C-PGPLS-003: Functional Dependencies Are Equality-Only
Functional dependency statistics are only applied to equality conditions comparing columns to constants and IN clauses with constant values. Range clauses, LIKE, column-to-column comparisons, and expressions are excluded. This is a scope limitation, not an invariant.

---

## Failure Modes Summary

| Failure Mode | Invariant Broken | Symptom | Silent? |
|---|---|---|---|
| Correlated columns without extended stats | INV-PGPLS-001 | Query plan underestimates row count → bad join strategy | Yes |
| Stale statistics after bulk load | INV-PGPLS-004 | Planner uses old reltuples → wrong plan until ANALYZE | Yes |
| Incompatible FD conditions | INV-PGPLS-003 | Planner estimates non-zero rows for impossible query | Yes |
| Unprivileged user reads pg_statistic | INV-PGPLS-005 | Information leak via value distributions | Yes |
| Missing ndistinct stats on GROUP BY columns | INV-PGPLS-002 | Wrong group count estimates → wrong aggregation strategy | Yes |
| Missing MCV stats on correlated filter columns | INV-PGPLS-007 | Joint selectivity off by orders of magnitude | Yes |

All failure modes are silent — the query returns correct results, but with potentially catastrophic performance degradation. This is the defining characteristic of planner statistics failures: correctness is preserved, performance is not.