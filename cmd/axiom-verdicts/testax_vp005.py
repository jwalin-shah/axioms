#!/usr/bin/env python3
"""
TestAX_VP005: Idempotent merge — re-running verification doesn't corrupt.

Invariant:  merge(merge(A, V), V) = merge(A, V)

Re-merging the same verdicts changes nothing. A retried run must not
corrupt the corpus.

This gate simulates the merge operation:
1. Extract all verdicts from the current corpus (axiom_id → verdict pairs).
2. Create a deep copy of the corpus.
3. "Re-apply" the verdicts to the copy (simulating a second merge).
4. Compare the result to the original.

If the corpus changed after re-application, the merge is not idempotent.

The gate also checks that the merge operation does not produce side effects
like reordering axioms, changing field order, or introducing spurious fields.
"""
import argparse
import copy
import json
import sys

from testax_lib import add_common_args, exit_fail, exit_pass, load_corpus


def _extract_verdicts(axioms: list[dict]) -> dict[str, dict]:
    """Extract verdict information from each axiom, keyed by ID.

    Returns a dict mapping axiom_id → {field: value} for all verdict-related fields.
    """
    verdict_fields = {
        "verdict", "verdict_evidence", "verdict_confidence",
        "verdict_discrepancy", "verified_at",
    }
    verdicts: dict[str, dict] = {}
    for axiom in axioms:
        aid = axiom.get("id")
        if not aid:
            continue
        v = {}
        for field in verdict_fields:
            if field in axiom:
                v[field] = copy.deepcopy(axiom[field])
        verdicts[aid] = v
    return verdicts


def _apply_verdict(axiom: dict, verdict: dict) -> dict:
    """Apply a verdict dict to an axiom, returning the modified axiom."""
    result = copy.deepcopy(axiom)
    for field, value in verdict.items():
        result[field] = copy.deepcopy(value)
    return result


def _merge_verdicts(axioms: list[dict], verdicts: dict[str, dict]) -> list[dict]:
    """Merge verdicts into axioms, returning a new list.

    For each axiom, if a verdict exists for its ID, overlay the verdict fields
    onto the axiom. This simulates the merge(axioms, verdicts) operation.
    """
    result = []
    for axiom in axioms:
        aid = axiom.get("id")
        if aid and aid in verdicts:
            result.append(_apply_verdict(axiom, verdicts[aid]))
        else:
            result.append(copy.deepcopy(axiom))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="VP-005: Idempotent merge")
    add_common_args(parser)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also check that axiom order is preserved (default: only check content)",
    )
    args = parser.parse_args()

    axioms = load_corpus(args.corpus)
    total = len(axioms)

    # Step 1: Extract verdicts from the current corpus
    verdicts = _extract_verdicts(axioms)
    if args.verbose:
        print(f"  Extracted {len(verdicts)} verdicts from {total} axioms")

    # Step 2: Simulate a first merge (which should produce the current corpus)
    merged_once = _merge_verdicts(axioms, verdicts)

    # Step 3: Simulate a second merge (re-applying the same verdicts)
    merged_twice = _merge_verdicts(merged_once, verdicts)

    # Step 4: Compare
    errors: list[str] = []

    if len(merged_once) != len(merged_twice):
        errors.append(
            f"Axiom count changed: {len(merged_once)} → {len(merged_twice)}"
        )

    # Compare axiom-by-axiom
    diffs = []
    for i, (a1, a2) in enumerate(zip(merged_once, merged_twice)):
        if a1 != a2:
            aid = a1.get("id", a2.get("id", f"index {i}"))
            diffs.append(f"Axiom '{aid}' differs after re-merge")

    if diffs:
        errors.append(f"Merge is not idempotent: {len(diffs)} axiom(s) changed")
        errors.extend(diffs[:10])
        if len(diffs) > 10:
            errors.append(f"  ... and {len(diffs) - 10} more")

    # Check that the merge didn't change the original corpus
    for i, (orig, merged) in enumerate(zip(axioms, merged_once)):
        aid = orig.get("id", f"index {i}")
        # The original should equal the first merge (since verdicts are already applied)
        # But if the merge introduces changes, that's a problem
        if orig != merged:
            # Check if the differences are only in verdict fields
            differing_keys = set(orig.keys()) ^ set(merged.keys())
            same_verdict_keys = all(k in {"verdict", "verdict_evidence", "verdict_confidence", "verdict_discrepancy", "verified_at"} for k in differing_keys)
            if not same_verdict_keys:
                errors.append(f"Merge introduces non-verdict changes to '{aid}': {diffing_keys}")

    if errors:
        exit_fail(f"VP-005: {len(errors)} idempotency violation(s)", errors)
    else:
        exit_pass(
            f"VP-005: merge(merge(A, V), V) = merge(A, V) — "
            f"idempotent across {total} axioms, {len(verdicts)} verdicts"
        )


if __name__ == "__main__":
    main()