# Audit Workflow — Usage Guide

## When to run the audit

The bridge-orbit audit is the pre-change verification step. Run it:

1. **Before any change to spawn, sandbox, verify, or dispatch** — these are the
   packages under active audit (findings #7, #8, #9). Running the audit first
   establishes a baseline; running it after the change confirms you didn't
   regress.

2. **Before merging any PR that touches bridge's internal packages or orbit's
   dispatch/session** — the audit is the "does this violate any axioms?" check
   that verify-machine's 5 gates cannot perform.

3. **Weekly** — as a health check. The axiom corpus evolves (new axioms added,
   verdicts updated). A weekly re-audit catches drift.

4. **After any Neo4j re-index** — if the cocoindex pipeline has re-indexed
   axioms, the audit should re-run against the fresh data.

The audit is NOT:
- A replacement for `go test -race ./...` (that's P0)
- A replacement for verify-machine's daily gate (that catches config staleness)
- A CI gate (yet — the audit requires Neo4j + subagent access)

## How to run it

```bash
# 1. Verify Neo4j is current
brew services list | grep neo4j  # must say "started"
curl -s -u neo4j:axiom-knowledge "http://localhost:7474/db/neo4j/tx/commit" \
  -H "Content-Type: application/json" \
  -d '{"statements":[{"statement":"MATCH (a:Axiom) RETURN count(a)"}]}' | jq '.results[0].data[0].row[0]'
# Should return 1196

# 2. Generate the filtered axiom corpus
# (Run from axioms repo)
curl -s -u neo4j:axiom-knowledge "http://localhost:7474/db/neo4j/tx/commit" \
  -H "Content-Type: application/json" \
  -d '{"statements":[{"statement":"MATCH (a:Axiom) WHERE a.category IN [\"saltzer-schroeder\", \"software-correctness\", \"software-testing\", \"architecture\", \"sandbox\", \"testing\", \"testability\", \"provenance\", \"systems\", \"safety\"] OR a.id IN [\"AX-GVISOR-003\", \"AX-DDIA-022\", \"AX-DDIA-004\", \"AX-ORACLE-MONITOR-040\", \"AX-ORACLE-AUTHZ-013\", \"AX-ORACLE-APPLIED-012\", \"AX-ORACLE-OSTEP-015\", \"AX-CRYPTO-016\", \"AX-ORACLE-AUTHZ-017\", \"AX-ORACLE-DTXN-018\", \"AX-SAIP-021\", \"AX-SQLITE-005\"] RETURN a.id AS id, a.equation AS equation, a.domain AS domain, a.category AS category, a.severity AS severity, a.verdict AS verdict"}]}' \
  | jq '[.results[0].data[] | {id: .row[0], equation: .row[1], domain: .row[2], category: .row[3], severity: .row[4], verdict: .row[5]}]' \
  > /tmp/audit_final.json

# 3. Launch audit agents (from axioms repo)
# Agent 1: scout axioms for themes
# Agents 2-5: audit bridge (#7, #8, #9, general)
# Agents 6-7: audit orbit (dispatch, session)

# 4. Review results
# Each agent returns findings with file:line evidence
# Verify phase: adversarially check each finding

# 5. Write findings to wayfinder
# Update ~/projects/portfolio/wayfinder/bridge-loop-architecture/map.md
# or create a new wayfinder map for the audit results
```

## Skills integration

The audit is part of the pre-code pipeline. The full sequence:

```
axi (blast radius) → cocoindex (code search) → audit (axiom check) → code change
                                                      ↓
                                        mattpocock-skills:codebase-design (deep modules)
                                        mattpocock-skills:domain-modeling (ubiquitous language)
                                        mattpocock-skills:diagnosing-bugs (if findings found)
                                        mattpocock-skills:mp-code-review (review change)
                                        mattpocock-skills:tdd (test-first)
```

The audit feeds into Pocock's skills:
- **codebase-design**: audit findings about deep module boundaries → informs where to draw seams
- **domain-modeling**: audit findings about missing invariants → informs domain model updates
- **diagnosing-bugs**: confirmed P1 findings → feeds the diagnosis loop
- **mp-code-review**: audit report → checklist for standards + spec review
- **tdd**: confirmed violations → red (failing test) → green (fix) → refactor

## What the audit produces

A report with:
1. **Executive summary** — overall state, biggest risk
2. **Per-finding status** — for #7, #8, #9: still real? New evidence? Mitigations?
3. **New findings** — things the wayfinder map doesn't cover
4. **Orbit assessment** — how coupled are bridge/orbit issues?
5. **Recommendations** — prioritized P0/P1/P2 actions

Each finding includes:
- Title + severity
- File:line reference
- Concrete evidence (code snippet or behavior)
- Axiom reference (which axiom is violated)
- Adversarial verification result (CONFIRMED/REFUTED/PARTIALLY_CONFIRMED)

## Filtering methodology (reference)

From 1196 axioms → 117 relevant:

| Why included | Count |
|---|---|
| Saltzer-Schroeder design principles | 14 |
| Software correctness (Hoare/Dijkstra/Owicki-Gries/Liskov) | 26 |
| Software testing methodology | 21 |
| Architecture (idempotency, circuit breakers) | 7 |
| Sandbox/gVisor | 6 |
| Systems/kernel security | 17 |
| Testing/sqlite discipline | 7 |
| Testability/SAIP | 5 |
| Concept-search hits (fencing, audit, isolation) | 12 |
| Safety (Go/zig) + provenance | 5 |

| Why excluded | Count |
|---|---|
| Protocol-level sys axioms (TCP, HTTP, TLS) | 93 |
| Oracle API design rules | ~510 |
| Network protocol specs | 128 |
| DDIA/Kafka/Redis specifics | ~200 |
| Cryptographic protocol specs | 27 |
| Compiler axioms | 62 |
