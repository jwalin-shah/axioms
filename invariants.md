# Axiom Verdict Persistence — Invariants

Root cause this addresses: `verify-v2.js` / `verify-v3.js` compute a per-axiom
verdict for every axiom (`{axiom_id, verdict, evidence, discrepancy, confidence}`)
and **return** them, but never write them to disk. Only a hand-authored aggregate
summary survived in `verification-results.json`. All 831 axioms in `axioms.json`
carry zero verdict fields; the per-axiom judgments are unrecoverable
(verified 2026-07-21: no `AX-*`→verdict pair exists in any transcript on disk).

A verification run that yields a summary without per-id labels is a **failed run**.
These equations make that failure detectable and blocking.

## Tensor equations

```
VP-001  ∀v ∈ V: v.axiom_id ∈ ids(A)
        Every verdict names an axiom that exists. Guards corpus drift —
        verifying a corpus that is no longer the canonical one.

VP-002  ∀v ∈ V: v.verdict ∈ {VERIFIED, DISPUTED, UNCERTAIN, DUPLICATE}
        Closed vocabulary. An unrecognized verdict is a broken producer.

VP-003  ∀v ∈ V: v.verdict = DISPUTED → v.discrepancy ≠ ""
        A dispute without a stated reason is not a finding.

VP-004  coverage(A) = |{a ∈ A : a.verdict ≠ ⊥}| / |A|
        check exits non-zero when coverage < 1. Fail closed:
        partial verification must never read as complete.

VP-005  merge(merge(A, V), V) = merge(A, V)
        Idempotent. Re-merging the same verdicts changes nothing,
        so a retried run cannot corrupt the corpus.
```

## What counts as verification (VF)

Comparing an equation to prose in a source is a judgment, not a proof. Three
levels, in increasing strength — a corpus claim should always state which level
it has reached:

```
L1  MECHANICAL   regex scan for extraction damage.
                 axioms/scan-damage.py. ~62% precision — triage only,
                 never an auto-fix signal.

L2  SOURCE       an adversarial agent compares the equation to the source.
                 Catches misstatement, misattribution, over-hardening.
                 Judgment, not proof.

L3  EXECUTABLE   a TestAX gate that PASSES on correct code and FAILS on
                 deliberately broken code. This is the only level that
                 proves anything, and it is what the orbit contract
                 already requires: "a declared invariant that only exists
                 as prose is incomplete".
```

The defect L1 structurally cannot catch is the **well-formed vacuous axiom** —
notation that looks rigorous but forbids nothing:

```
VF-001  ∀ axiom a: ∃ input x such that eval(a, x) = false
        An invariant with no possible violator is not an invariant.
```

Confirmed instances in this corpus, both well-formed, both missed by the scan
and caught only by agent review:

| Axiom | Equation | Why vacuous |
|---|---|---|
| `AX-ORACLE-OWICKI_GRIES-026` | `∀shared_state S: invariant(S)` | `invariant` is an unbound schematic predicate |
| `AX-ORACLE-TAPL-003` | `Γ ⊢ ΛX.t : ∀X.T` | T-TAbs conclusion with premise `Γ, X ⊢ t : T` dropped — types every term |

Operationally, VF-001 is discharged by requiring the verifier to **construct a
counterexample**. If it cannot produce an input that violates the equation, the
axiom is VACUOUS and recorded as DISPUTED with a discrepancy beginning
`VACUOUS: `. This is the same discrimination test as L3: an executable gate that
passes on both correct and broken code proves nothing, exactly as an axiom with
no counterexample forbids nothing.

Tier A (2026-07-21) ran WITHOUT this test and so its 184 VERIFIED verdicts are
L2-at-best and possibly contaminated by vacuity; an audit of a 40-axiom sample
is what establishes the rate. Tier B onward requires the test.

## Gates

`TestAX_VP001` … `TestAX_VP005` in `cmd/axiom-verdicts/main_test.go`.

```bash
go test -run 'TestAX_VP' -count=1 ./cmd/axiom-verdicts/
```

## Corpus lineage (reconciled 2026-07-21)

Four axiom files disagreed on count. Resolved by ID-set comparison:

| File | Entries | Relationship |
|---|---|---|
| `axioms.json` | 831 | **CANONICAL.** Strict subset of `.bak` (831/831 ids shared). |
| `axioms.json.bak` | 900 | Immediate parent of canonical; 69 dropped in dedup. |
| `axioms.json.orig` | 9310 | Raw pre-extraction corpus. Shares only 7 ids with canonical. |
| `axioms-deduped.json` | 2000 | **STALE ORPHAN.** Strict subset of `.orig` (2000/2000). Shares only 4 ids with canonical — a different ID namespace, not a deduplicated canonical. |
| `axioms-index.json` | 2000 | Index over `axioms-deduped.json`. Stale with it. |

`verification-results.json` reports 747 axioms — matching none of the above.
It was produced against a corpus that no longer exists on disk. Its counts
(567 VERIFIED / 107 DISPUTED / 48 DUPLICATE / 25 UNCERTAIN) must not be
treated as describing `axioms.json`.

Consequence: re-verification is required, and `axioms-deduped.json` /
`axioms-index.json` must not be read by any consumer until re-derived
from the canonical corpus.
