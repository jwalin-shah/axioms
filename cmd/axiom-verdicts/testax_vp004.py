#!/usr/bin/env python3
"""
TestAX_VP004: Coverage check — fail closed when verification is incomplete.

Invariant:  coverage(A) = |{a ∈ A : a.verdict ≠ ⊥}| / |A|  ≥ 1.0

Partial verification must never read as complete. If any axiom lacks a
verdict, the gate exits non-zero.

The coverage threshold is configurable via --threshold (default 1.0).
A threshold of 1.0 means every axiom must have a verdict. Lower thresholds
are useful during active verification campaigns when the corpus is in
transition.

Note on null vs. empty verdict: A verdict of None/null is treated as
"missing" (⊥). A verdict that is an empty string "" is also treated as
missing. A verdict that is any value in the closed vocabulary counts as
present.
"""
import argparse
import sys

from testax_lib import add_common_args, exit_fail, exit_pass, load_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="VP-004: Coverage check — fail closed")
    add_common_args(parser)
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Minimum coverage ratio required (default: 1.0 = 100%%)",
    )
    args = parser.parse_args()

    axioms = load_corpus(args.corpus)
    total = len(axioms)

    if total == 0:
        exit_fail("VP-004: Corpus is empty — no axioms to verify")

    # Count axioms with a verdict (non-null, non-empty)
    covered = 0
    uncovered_ids: list[str] = []
    for axiom in axioms:
        verdict = axiom.get("verdict")
        if verdict is not None and verdict != "":
            covered += 1
        else:
            uncovered_ids.append(axiom.get("id", "unknown"))

    coverage = covered / total
    threshold = args.threshold

    if args.verbose:
        print(f"  Coverage: {covered}/{total} = {coverage:.4f} (threshold: {threshold})")
        if uncovered_ids:
            print(f"  Uncovered: {uncovered_ids}")

    violations = 0
    for axiom in axioms:
        verdict = axiom.get("verdict")
        verdict_discrepancy = axiom.get("verdict_discrepancy")
        # Check for DISPUTED with no discrepancy (structural issue also flagged by VP-003)
        if verdict == "DISPUTED" and not verdict_discrepancy:
            pass  # VP-003 handles this; VP-004 only checks presence

    if coverage < threshold:
        uncovered_sample = uncovered_ids[:10]
        more = len(uncovered_ids) - 10 if len(uncovered_ids) > 10 else 0
        details = [
            f"Coverage: {covered}/{total} = {coverage:.4f} < threshold {threshold}",
            f"Uncovered axioms: {uncovered_sample}" + (f" (+{more} more)" if more else ""),
        ]
        exit_fail(f"VP-004: Verification coverage {coverage:.4f} is below threshold {threshold}", details)
    else:
        exit_pass(f"VP-004: Coverage {coverage:.4f} ({covered}/{total}) meets threshold {threshold}")


if __name__ == "__main__":
    main()