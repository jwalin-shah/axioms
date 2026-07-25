# TestAX Gate Infrastructure — cmd/axiom-verdicts/

## Purpose

This directory contains the TestAX gate infrastructure for the axioms corpus.
These gates verify the integrity of the corpus and serve as templates for
codebase-level verification of individual axioms.

## Architecture

The gates are Python scripts because the axioms corpus is a Python/JSON knowledge
base. Each gate is independently runnable and fails closed (exit non-zero on
failure).

### Directory Layout

```
cmd/axiom-verdicts/
  __init__.py           # Package marker
  testax_lib.py         # Shared utilities (corpus loading, verdict helpers)
  testax_vp001.py       # VP-001: Every verdict names an axiom that exists
  testax_vp002.py       # VP-002: Every verdict is from a closed vocabulary
  testax_vp003.py       # VP-003: A dispute must have a stated reason
  testax_vp004.py       # VP-004: Coverage check — fail closed
  testax_vp005.py       # VP-005: Idempotent merge
  testax_template.py    # Template for new TestAX gates
  run_all.sh            # Unified runner
  README.md             # This file
```

## Running Gates

```bash
# Run a single gate
python3 cmd/axiom-verdicts/testax_vp001.py

# Run all gates
bash cmd/axiom-verdicts/run_all.sh

# Run against a specific corpus file
python3 cmd/axiom-verdicts/testax_vp001.py --corpus /path/to/axioms.json
```

## Gate Convention

| Property | Value |
|---|---|
| Exit code 0 | PASS — invariant holds |
| Exit code non-zero | FAIL — invariant violated, details on stderr |
| Argument `--corpus` | Override path to axioms.json (default: `axioms.json` in repo root) |
| Argument `--verbose` | Print detailed pass/fail per axiom |

## VP Gates Summary

| Gate | Invariant | What It Checks |
|---|---|---|
| VP-001 | ∀v ∈ V: v.id ∈ ids(A) | Every axiom has a unique, non-empty ID |
| VP-002 | ∀v ∈ V: v.verdict ∈ {VERIFIED, DISPUTED, UNCERTAIN, DUPLICATE} | Closed vocabulary |
| VP-003 | ∀v ∈ V: v.verdict = DISPUTED → v.discrepancy ≠ "" | Dispute has a stated reason |
| VP-004 | coverage(A) ≥ 1.0 | Fail closed when verification is incomplete |
| VP-005 | merge(merge(A, V), V) = merge(A, V) | Idempotent merge |

## TestAX Template

See `testax_template.py` for the skeleton used to create L3 (executable) gates
that prove an axiom holds for a specific codebase.

## Verification Levels

- **L1 (Mechanical)**: Regex scan for extraction damage — `axioms/scan-damage.py`
- **L2 (Source)**: Adversarial agent compares equation to source text
- **L3 (Executable)**: A TestAX gate that PASSES on correct code and FAILS on
  deliberately broken code. This is the only level that proves anything.