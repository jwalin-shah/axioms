# Axiom-to-Code Pipeline — Overarching Plan

## The Three Layers

| Layer | What | Count | Status |
|---|---|---|---|
| **Literature axioms** | `axioms/axioms.json` — engineering claims from books, standards, papers | 831 | 731 verified (source validity), 100 Tier C pending |
| **Package invariants** | `pkg/*/invariants.md` — tensor equations specific to orbit's code | 40+ equations | Written per-package, some need review |
| **TestAX* gates** | `pkg/*/ax_test.go` — Go tests that prove the invariant holds | 116 tests | 12 packages covered, 78+ packages not covered |

## How They Connect

```
Literature axioms (831) ──inform──→ Package invariants (40+) ──enforce──→ TestAX* gates (116)
       │                                  │
       │                                  │
       ▼                                  ▼
  Source trust:                      Code verification:
  "Is this claim                     "Does orbit's code
   actually from                     actually satisfy
   the cited source?"                this equation?"
```

The literature axioms are **reference material** — they train our understanding of what invariants matter. The package invariants are **code-specific** — written for orbit's own subsystems. The TestAX* gates are **enforcement** — they run in CI and fail if the invariant breaks.

## The SHOULD/MUST Question

You asked: if the source says SHOULD, shouldn't we be MORE strict? The answer is **yes, but we must be honest about what we're claiming**.

The defect in the over-hardened axioms is NOT that they're too strict — it's that they **misrepresent the source**. If we say "ISO 25010 says availability MUST be ≥ target" but ISO 25010 actually says "SHOULD define a target," we're lying about the source. Someone reading the axiom for engineering judgment would think the ISO standard is stricter than it is.

**The fix: two fields per axiom**

```
source_modality: SHOULD    ← what the source actually says
enforcement: MUST           ← what orbit enforces (can be stricter)
```

The source modality is for citation accuracy. The enforcement is for our own code. We can (and should) enforce stricter standards. We just can't pretend the source said them.

## The Vacuous/Guidance Question

You asked: if guidance axioms are vacuous as ∀ equations, can we still enforce them? **Yes — through different mechanisms:**

| Axiom type | Example | Enforcement mechanism |
|---|---|---|
| ∀ state invariant | "∀cb: cb.Allow() side-effect-free" | TestAX* Go test ✅ (exists) |
| ∀ protocol invariant | "∀request: response has content-type header" | Integration test or OpenAPI schema check |
| ∀ design guideline | "error responses have code/message/details" | Code review + OpenAPI contract test |
| ∀ coding pattern | "always check Close() errors" | `errcheck` linter in CI |
| ∀ architecture rule | "external calls wrapped in circuit breaker" | Architecture test (`go test -run TestArch`) |

The vacuous ones move to `guidance/` with an enforcement mechanism column. They're not worthless — they're just not ∀-provable, which means they need a different enforcement tool.

## What Books to Add Next

The cleanest sources (highest verification rate, zero fabrication) were:

| Source | Domain | Why |
|---|---|---|
| CLRS | Algorithms | Formal content, theorem-proof structure |
| Sedgewick & Wayne | Algorithms | Same |
| Okasaki | Purely functional data structures | Same |
| TAOCP (Knuth) | Algorithms | Same |
| **TAPL (Pierce)** | Type systems | Formal — type soundness proofs |
| **PFPL (Harper)** | Programming languages | Same |
| **Dragon Book (Aho et al.)** | Compilers | Well-defined, but less formal |
| **Go Memory Model** | Go concurrency | Directly relevant to our codebase |
| **Rustonomicon** | Unsafe Rust | Directly relevant (Zig invariants) |
| **Lamport (Specifying Systems)** | Formal specification | The TLA+ community is already in the corpus |

The key insight: **formal content survives verification**. Books with theorems, proofs, and precise definitions produce ~60%+ verified. Books with guidance and heuristics produce ~5-17%. Future extraction should target formal sources.

## Execution Plan

### Phase 1: Clean the corpus (today)
- Demote 87 vacuous → `guidance/`
- Delete 30 duplicates + 31 fabricated + 8 claim-absent

### Phase 2: Fix the fixable (this week)
- Re-extract 36 damaged equations (source text on disk)
- Fix 60 misattributions (correct section/chapter numbers)
- Fix 124 fidelity errors (align axiom with source)
- Fix 40 contradictions (align or delete)
- Add `source_modality` and `enforcement` fields to replace the over-hardened 9

### Phase 3: Tier C citation-attachment (this week)
- 93 networking axioms → find which RFC says each thing
- 7 house rules → label as `house-authored`, fix AX-GO-002

### Phase 4: Write TestAX* gates (ongoing)
- Every package invariant needs a TestAX* gate
- 12 packages have them today; 78+ don't
- Each gate is step 5 of the 8-step development contract

### Phase 5: Extract from new formal sources (next)
- TAPL, PFPL, Go Memory Model, Rustonomicon
- Extract only from formal content, not guidance chapters