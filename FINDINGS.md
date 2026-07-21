# Axiom Verification — Findings and Learning Document

Generated: 2026-07-21 from `axioms/axioms.json` (831 axioms, 731 verdicts)

---

## The Real State (verified against disk, not memory)

The earlier claim that "verdicts were lost" was wrong. **731/831 axioms carry verdicts.** The merge ran and persisted correctly. The 100 unlabeled are:
- **93** networking axioms from `primary:networking-research-2026-07` — no citations, never been verified
- **7** house rules (`doc:axioms`) — orbit's own engineering guidelines

```
VERIFIED:   377 (45.4%) — source citation is correct, axiom faithfully represents it
DISPUTED:   321 (38.6%) — something is wrong with the axiom
DUPLICATE:   30 ( 3.6%) — redundant with another axiom
UNCERTAIN:    3 ( 0.4%) — verifier couldn't decide
UNLABELED:  100 (12.0%) — Tier C, no verdict yet
```

---

## What "VERIFIED" Actually Means

**Critical distinction**: VERIFIED means *the source citation is correct and the axiom faithfully matches the source*. It does NOT mean:

- The invariant has been proven against any codebase
- A TestAX* gate exists in any Go package
- The equation is self-consistent or well-formed
- It isn't vacuously true

The vacuity audit sampled 40 VERIFIED axioms and found **12.5% were vacuous** — they forbid nothing, so proving them proves nothing. Extrapolated: ~23 of the 377 VERIFIED axioms are vacuous and should be demoted.

---

## The 321 Disputes — Failure Mode Breakdown

| Failure Mode | Count | What It Means | Fix |
|---|---|---|---|
| **Fidelity error** | 124 | The axiom says something different from its source — wrong detail, incorrect claim | Fix the axiom text |
| **Vacuous (not invariant)** | 64 | Design guidance or definition stated as ∀ — forbids nothing | Demote to guidance/ |
| **Misattribution** | 60 | Wrong chapter, wrong author, wrong section number | Fix the citation |
| **Contradiction/reversed** | 40 | Axiom states the opposite of what the source says | Fix or delete |
| **Extraction damage** | 36 | Truncated equations, bare quantifiers, markdown tables as equations | Re-extract with limit removed |
| **Fabricated content** | 31 | Numbers, thresholds, or claims that don't exist in the cited source | Delete or re-extract |
| **Wrong threshold/bound** | 20 | Invented numeric limits (e.g., 2s Nielsen threshold, cyclomatic complexity ≤ 20) | Correct to source values |
| **Missing states/cases** | 16 | Enumeration incomplete, missing valid states | Add the missing cases |
| **Over-hardened** | 9 | Source says SHOULD/MAY, axiom says MUST | Relax to source modality |
| **Claim absent from source** | 8 | The entire claim doesn't appear in the cited work | Delete |
| **Wrong standard cited** | 4 | Cites an obsoleted or incorrect standard | Update to current RFC/ISO |

**Key insight**: The categories overlap. A single dispute can be misattributed AND over-hardened AND use a wrong threshold. The counts above are per-pattern-match, not per-axiom. The 31 fabricated-content entries are the most dangerous — they read as authoritative and are entirely invented.

---

## What We Learned — The Patterns

### 1. Extraction pipelines produce systematic damage

~36 axioms were mechanically damaged during extraction: truncated at ~300 chars (the API limit), bare quantifier lines with no predicate, markdown tables flattened into string fields. These are NOT epistemic failures — the source text is on disk and correct. The pipeline needs a character-limit removal before re-extraction.

### 2. Standards literature cannot be rendered as invariants

Domain hardness varies wildly:
```
algorithm-design         67% verified  — theorems with hypotheses and bounds
mathematics              58% verified  — formal content
software-testing         17% verified  — guidance, not invariants
standards                 5% verified  — RFC 2119 SHOULD/SHALL/MAY flattened to MUST
```

Standards use degree language *by design*. Rendering SHALL, SHOULD, and MAY all as `∀ MUST` manufactures precision the source never had. **Do not extract invariants from guidance literature.** Record normative guidance as guidance, not ∀ equations.

### 3. Fabricated citations are the most dangerous failure mode

The 31 fabricated-content entries include:
- A "2 second" response-time threshold attributed to Nielsen (his actual figures: 0.1s / 1.0s / 10s)
- Three inverted container-security claims (containers start with ~14 capabilities, not empty; rootfs defaults to read-write reversed)
- `wp` (Dijkstra 1975) attributed to Floyd 1967
- An invented "Section 8.1-8.2" in Anderson's Security Engineering

Each reads as MORE authoritative than the truth because it cites a named source. A fabricated citation with a correct-looking format is harder to catch than a missing one. **Tier C (uncited axioms) must NOT be given to a model for "verification" — it will manufacture more of exactly this defect.**

### 4. Domain-specific books are the cleanest source

CLRS, Sedgewick, Okasaki, TAOCP — books with formal content — produce very few disputes (1-3 each) and zero fabricated content. Oracle-source axioms (extracted from cached MD files) have more damage but zero misattribution. The worst quality comes from axioms where an agent had to go find a source it didn't hold.

### 5. Even our own house rules have defects

The 7 house-authored axioms (AX-SYS-001/002/003, AX-GO-001/002, AX-ZIG-001/002) were hand-written by the orbit team and never reviewed. **AX-GO-002 states a factual error**: it claims `Close()` flushes to disk when it only flushes to the kernel. The rule (always check close errors) is correct, but the stated reason is wrong — the same defect class as the fabricated Nielsen threshold, produced by the same lack of adversarial review. **This alone justifies the entire verification run.**

---

## What "Guidance" Means and How to Make It Enforceable

The captain asked: if a design rule is vacuous as a tensor equation, can it still be enforced? **Yes, through different mechanisms:**

| Category | Example | Enforcement Mechanism |
|---|---|---|
| API response structure | "error responses must have code/message/details" | OpenAPI schema contract test |
| Error handling patterns | "always check deferred Close() errors" | `errcheck` linter |
| Resource naming | "endpoints are nouns, not verbs" | API review / lint rule |
| Circuit breaker wrapping | "external calls wrapped in circuit breaker" | Architecture test (e.g., `go test -run TestArchitecture`) |
| Context propagation | "goroutines must accept context.Context" | `staticcheck` SA1012/SA1013 |
| Log structure | "structured logging, not fmt.Println" | Grep in CI |

The right home for guidance axioms is NOT the axiom corpus (which gates on provability). It's a `guidance/` collection with an enforcement mechanism column.

---

## What Needs to Happen Next

### Phase 1: Clean the corpus (immediate, low effort)

| Task | Effort | Action |
|---|---|---|
| **Demote 64 vacuous** | Low | Move vacuous DISPUTED axioms to `guidance/` |
| **Remove 30 DUPLICATE** | Low | Delete from corpus |
| **Demote ~23 vacuous VERIFIED** | Low | From vacuity audit, move to `guidance/` |

Result: corpus drops from 831 to ~714, all carrying real invariants.

### Phase 2: Fix the fixable disputes (medium effort)

| Task | Effort | Action |
|---|---|---|
| **Re-extract 36 damaged** | Low | Re-run extraction without 300-char limit (source text on disk) |
| **Fix 60 misattributions** | Medium | Correct section/chapter/author citations |
| **Fix 124 fidelity errors** | Medium | Correct the axiom to match the source |
| **Fix 40 contradictions** | Medium | Align with source or delete |
| **Fix 20 wrong thresholds** | Low | Replace invented numbers with source values |
| **Fix 9 over-hardened** | Low | Relax MUST→SHOULD to match source modality |

Result: ~249 axioms fixed, corpus becomes ~377 VERIFIED + ~278 fixed = ~655 correct invariants.

### Phase 3: Delete the unfixable (hard)

| Task | Effort | Action |
|---|---|---|
| **Delete 31 fabricated** | Low | No source to fix — these are irreparable |
| **Delete 8 claim-absent** | Low | Claim doesn't exist in any source |

Result: corpus ~616, all with verified, correct sources.

### Phase 4: Run Tier C (the 100 unlabeled)

| Subset | Count | Action |
|---|---|---|
| **Networking axioms** | 93 | Citation-attachment via TIERC-PROMPT.md (find which RFC says each thing) |
| **House rules** | 7 | Label as `house-authored`, fix AX-GO-002 justification |

### Phase 5: Write TestAX* gates

This is the step that turns citation-verified axioms into code-verified invariants. No axiom in the corpus has a test gate today. Every P1 tensor equation needs either:
- A `TestAX*` / `TestT*` Go test that falsifies the invariant against the codebase
- A runtime assertion that fails closed
- A metric/counter movement proof: `before → action → after`, delta > 0

---

## Summary: What This Corpus Actually Is

The axiom corpus is a **catalog of engineering claims extracted from literature, with source validity verified**. It is NOT a set of code-proven invariants. The value is:

1. **Source trust**: 377 verified claims you can cite with confidence; 321 you now know need fixing
2. **Pattern library**: Every disputed axiom's discrepancy text is a concrete counterexample that exposed a real defect in extraction or reasoning
3. **Process learning**: The vacuity rate, domain hardness split, and fabricated-content frequency tell us where the extraction pipeline works and where it doesn't
4. **Self-review**: Even our own house rules had an undetected error — AX-GO-002's wrong justification

The 321 DISPUTED entries are not 321 "rejections." They are 321 defects found before they reached production reasoning. Every one is a finding you can act on.
