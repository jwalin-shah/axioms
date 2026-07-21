# Principles — Agent Constitution

**Read this first. Apply always. Language-agnostic.**
**Violation of any P1 rule is a hard block. No exceptions.**

---

## The Three Questions

Before writing ANY code, ask three questions. Your answers must be in the response.

### Q1: What kind of thing is this?

Match the code pattern to its oracle. If multiple match, apply ALL.

| Pattern | Keywords | Read This First |
|---|---|---|
| **State machine** | `state`, `switch`, `transition`, `fsm` | `source-cache/compiler-invariants-oracle.md` (INV-LEX-003: Lexer Halt), Hystrix, Raft §5, TCP FSM (RFC 9293) |
| **Resource pool** | `acquire`, `release`, `pool`, `semaphore`, `borrow` | K8s work queue, Tokio, PostgreSQL lock mgmt |
| **Lease / lock** | `lock`, `lease`, `ttl`, `hold`, `fencing` | etcd lease, Chubby, fencing tokens (DDIA Ch 8) |
| **Sandbox / containment** | `resolve`, `validate`, `escape`, `jail`, `sandbox` | gVisor architecture, seccomp, Saltzer & Schroeder 1975 |
| **Rate limit** | `rate`, `throttle`, `burst`, `window`, `token bucket` | Envoy rate limit, GCRA, token bucket |
| **Write-ahead log** | `wal`, `journal`, `append`, `recover`, `redo` | PostgreSQL WAL (AX-POSTGRES-004), SQLite WAL |
| **MVCC / snapshot** | `version`, `snapshot`, `txn`, `isolation`, `undo` | PostgreSQL MVCC, etcd MVCC |
| **Retry / backoff** | `retry`, `attempt`, `backoff`, `jitter`, `exponential` | AWS Builder's Library, AX-SYS-001 (idempotency) |
| **Reconciliation loop** | `observe`, `diff`, `act`, `desired`, `actual`, `controller` | K8s controller pattern |
| **Worker pool** | `worker`, `queue`, `submit`, `drain`, `goroutine` | NGINX, Tokio, AX-GO-001 (context) |
| **Parser / validator** | `parse`, `validate`, `lex`, `token`, `grammar` | Dragon Book (AX-COMPILER-001..007), SQLite input handling |
| **Cache** | `cache`, `invalidate`, `ttl`, `evict`, `miss` | Redis eviction, AX-SYS-003 (degradation) |
| **Queue** | `enqueue`, `dequeue`, `ack`, `deadletter`, `consumer` | Kafka log compaction, SQS |
| **Classifier / router** | `match`, `route`, `classify`, `dispatch`, `filter` | Envoy router, nginx location |
| **API / proxy** | `proxy`, `forward`, `gateway`, `handle`, `middleware` | Envoy, nginx, AX-ORACLE-WEB_PLATFORM (CORS, CSP, rate limiting) |
| **UI / platform** | `view`, `lifecycle`, `render`, `event`, `component` | SwiftUI view lifecycle, React component lifecycle |
| **Pipeline / workflow** | `step`, `stage`, `pipe`, `chain`, `transform` | Airflow, Tekton |
| **Config / feature flag** | `config`, `flag`, `toggle`, `default`, `env` | Envoy xDS, K8s ConfigMap |
| **Compiler / language** | `compile`, `typecheck`, `optimize`, `codegen`, `ssa` | Dragon Book (AX-COMPILER-001..033), TAPL (AX-TAPL-001..008) |
| **Type system** | `type`, `subtype`, `infer`, `unify`, `kind` | TAPL (AX-TAPL-001..008), PFPL |
| **Concurrent data structure** | `atomic`, `mutex`, `channel`, `lock-free`, `rcu` | Go Memory Model (GOMEM-001..036) |
| **Distributed consensus** | `raft`, `paxos`, `leader`, `quorum`, `term` | Raft paper, AX-SYS-001 (idempotency) |
| **Database storage** | `btree`, `lsm`, `page`, `block`, `flush` | PostgreSQL WAL (AX-POSTGRES-004), SQLite testing (AX-SQLITE-001..007) |

### Q2: What invariants must hold?

Go to the axiom corpus and pull the relevant invariants. DO NOT INVENT.

If you're building something that matches a pattern above, find the relevant axioms in `axioms/axioms.json` by searching for the pattern name, source type, or related AX-* IDs. Every matching axiom has a tensor equation — write your code to satisfy it.

**Don't know which axioms apply?** Run:
```bash
rg -l "<pattern>" axioms/axioms.json  # search by keyword
jq '.[] | select(.source_type == "textbook-formal") | .tensor_equation' axioms/axioms.json  # highest-trust axioms
```

**Source trust levels (from 825-axiom verification run):**

| Source Type | Verify Rate | Trust Level |
|---|---|---|
| `textbook-formal` (CLRS, Sedgewick, TAOCP, Okasaki, TAPL) | 84% | HIGH — trust any axiom |
| `oracle-extract` (cached MD files) | 60% | MEDIUM — check the source before depending |
| `guideline` | 75% | MEDIUM — but these are guidance, not invariants |
| `textbook-research` (Anderson, Schneier, Katz) | 25% | LOW — verify before trust |
| `standard` (NIST, ISO, FIPS) | 14% | VERY LOW — every claim is overstated |
| `research-primary` (no citation, Tier C) | 0% | NO TRUST — must first attach citations |
| `house-rule` (our own rules) | 0% | NO TRUST — must review, AX-GO-002 was wrong |

**NEVER trust a `standard` axiom without checking the source.** Standards use SHOULD/SHALL/MAY — 86% of extracted axioms misrepresent this.

### Q3: How do I prove it?

Every tensor equation needs an executable gate. Choose the right proof type:

| Proof Type | When | How |
|---|---|---|
| **TestAX\*** | Invariant must hold for all inputs | `func TestAX001_Name(t *testing.T) { ... }` |
| **Property test** | Invariant with random inputs | `rapid.Check(t, func(t *rapid.T) { ... })` |
| **Race detector** | Concurrency invariant | `go test -race ./pkg/...` |
| **Fuzz test** | Malformed input → graceful error | `testing.F` |
| **Linter rule** | Static pattern that can be checked | `errcheck`, `staticcheck`, custom `go vet` |
| **OpenAPI contract** | API structure/response invariants | `go test -run TestOpenAPISchema` |
| **Architecture test** | Package dependency constraints | `go test -run TestArchitecture` |
| **Metric movement** | Counter changes under known action | `before → action → after, delta > 0` |

**A declared invariant that only exists as prose is incomplete.**
**A counter that does not move under a known action is not wired.**

---

## Eight Lessons From the Verification Run

These come from the adversarial verification of 825 axioms. They are not optional.

### 1. Never verify an uncited axiom (P1)
31 axioms had entirely fabricated content — the 2s Nielsen threshold, inverted container claims, wrong Floyd attribution. Every single one came from asking a model to "verify" without providing the source text. **If you don't have the source cached, don't claim a verdict.**
- ✓ Cache the source text first
- ✗ Ask a model to "go find a source"

### 2. Cache the source before verifying (P1)
Tier A (cached text on disk): 0 misattributions, 0 fabricated content. Tier B (model must find source): 60 misattributions, 31 fabricated. **The single biggest quality predictor is whether the source is on disk.**
- ✓ Read from `axioms/source-cache/`
- ✗ Web search for citations

### 3. Formal content is provable, guidance is not (P0)
textbook-formal axioms: 84% verified. Standard axioms: 14% verified. **Don't extract invariants from guidance literature.** Standards, best practices, and process advice cannot be rendered as ∀ equations without lying about what the source says.
- ✓ Extract from source-cache files with INV-* sections
- ✗ Extract from blog posts, standards, or "best practices"

### 4. Your own rules are untested (P1)
AX-GO-002 said "Close() flushes to disk." Wrong. Close() flushes to kernel; durability requires fsync. **Hand-written, unreviewed, sitting in plain text.** All 7 house rules need adversarial review.
- ✓ Adversarially review any hand-written rule
- ✗ Write a rule and assume it's correct

### 5. Guidance is not worthless, it needs different enforcement (P2)
"Error responses must have code/message/details" — can't prove with ∀, but can enforce with OpenAPI schema contract test. **Move provably-vacuous axioms to `axioms/guidance/` with an enforcement mechanism column.**

### 6. Extraction pipelines produce systematic damage (P0)
36 equations truncated at ~300 chars. The source text is correct. **Fix: remove the character limit. Re-extract, don't re-verify.**
- ✓ Re-extract from cached source
- ✗ Re-verify a truncated equation

### 7. Source type is the trust signal (P1)
textbook-formal (84% trust) → oracle-extract (60%) → standard (14%). **Check the source type before using an axiom to make a claim.** See Q2 table above.

### 8. The corpus is reference, the proof is the TestAX* gate (P0)
825 axioms in the corpus. Only 10/102 packages have gates. **An axiom is not verified until there's a Go test that proves it holds for the code.**
- ✓ `go test -run 'TestAX' -count=1 ./pkg/...`
- ✗ Declare an invariant without writing its gate

---

## The Gate (P0 / P1 / P2)

```
P0 (HARD BLOCK — CI must fail):
  go build fails, go test -race fails
  nil deref, deadlock, data race
  axiom extracted from guidance literature promoted to invariant
  TestAX* declared but missing the test function

P1 (HARD BLOCK — must include equation + line):
  Invariant violation with line-level evidence
  Verifying an axiom without caching the source first
  Writing a hand-written rule without adversarial review
  Claiming a STANDARD source axiom is faithful to the source

P2 (ADVISORY — always fix, never blocks):
  Style, unnecessary code, opinion without proof
  Guidance that should be in axioms/guidance/ instead of the corpus
  Vacuous ∀ equation that forbids nothing
```

**ACCEPT** only if: P0 passes AND no P1 violations with line-level evidence.
**REJECT** for: P0 failure OR P1 violation with tensor equation + line number.
Reviewer output without a tensor equation and line number is P2 by default.

---

## Pre-Code Gates

Before writing ANY code, run in this order (from AGENTS.md):

```bash
# 1. Identify the pattern (Q1) → find the oracle
# 2. Read the relevant axioms from the verified corpus
# 3. Trace blast radius: rg for affected packages + imports
# 4. Check OSS prior art: gh-axi search "<problem>"
# 5. Check existing test coverage: go test -race -cover ./pkg/<pkg>/
```

---

## What to Read When

| You're building... | Read this |
|---|---|
| Any state machine | compiler-invariants-oracle.md (Lexer Halt), RFC 9293 (TCP FSM) |
| Any resource pool | PostgreSQL source conventions (AX-POSTGRES-002, 003) |
| Any sandbox | gVisor architecture guide (AX-GVISOR-001..006), Saltzer & Schroeder |
| Any rate limiter | Envoy rate limit docs, GCRA algorithm |
| Any WAL | PostgreSQL WAL (AX-POSTGRES-004), SQLite WAL |
| Any retry/backoff | AWS Builder's Library, AX-SYS-001 (idempotency) |
| Any lock/lease | etcd lease, DDIA Ch 8 (fencing tokens) |
| Any concurrency | Go Memory Model (GOMEM-001..036), AX-GO-001 |
| Any parser/compiler | Dragon Book (AX-COMPILER-001..033), TAPL (AX-TAPL-001..008) |
| Any cache | Redis eviction docs |
| Any queue | Kafka log compaction |
| Any distributed system | DDIA Ch 8-9, Raft paper |
| Any API/HTTP | HTTP RFCs (RFC 9110, 9113, 9114 — in Tier C) |
| Any database storage | PostgreSQL MVCC, SQLite testing (AX-SQLITE-001..007) |
| Any test | SQLite testing methodology (AX-SQLITE-001..007) |
| Any security boundary | Saltzer & Schroeder 1975 + STRIDE, AX-GVISOR-001..006 |
| Any quality attribute | SAIP (AX-SAIP-001..027) |

---

## The Enforcement Report

Current state (measured 2026-07-21):

```
Corpus axioms:      825 (84% textbook-formal verified, 14% standard verified)
Go Memory Model:    36 (separate file, not in corpus)

Packages with invariants.md + TestAX*:    10 of 102 (10%)
Packages with NO invariants at all:       90 of 102 (88%)

Target:             ALL 102 packages have invariants.md + TestAX* gates
```

Every new package must add:
1. `pkg/<name>/invariants.md` with tensor equations
2. `pkg/<name>/ax_test.go` with TestAX* gates
3. Linked to the relevant axiom IDs from the corpus

See `axioms/source-cache/MANIFEST.md` for what's been extracted vs what's still on disk.
