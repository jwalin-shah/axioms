#!/usr/bin/env python3
"""
TestAX_VP003: A dispute must have a stated reason.

Invariant:  ∀v ∈ V: v.verdict = DISPUTED → v.discrepancy ≠ ""

A dispute without a stated reason is not a finding. The reason must be
recorded in at least one of the canonical reason fields:
- verdict_discrepancy (preferred — the explicit "why disputed" field)
- verdict_evidence  (fallback — the general evidence field, sufficient for
  DISPUTED since the evidence IS the dispute reason)

This gate checks that every DISPUTED axiom has at least one non-empty,
non-null reason field. AXIOMS CORPUS NOTE: As of 2026-07-24, the canonical
corpus stores dispute reasons in verdict_evidence rather than
verdict_discrepancy. The gate accepts either field to match actual data
layout, but records a warning when verdict_discrepancy is empty.
"""
import argparse
import sys

from testax_lib import VERDICT_REASON_FIELDS, add_common_args, exit_fail, exit_pass, load_corpus


def _is_populated(value) -> bool:
    """Check if a field value is populated (non-null, non-empty string)."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    return bool(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="VP-003: A dispute must have a stated reason")
    add_common_args(parser)
    args = parser.parse_args()

    axioms = load_corpus(args.corpus)
    total = len(axioms)
    errors: list[str] = []
    warnings: list[str] = []

    for axiom in axioms:
        aid = axiom.get("id", "unknown")
        verdict = axiom.get("verdict")

        if verdict != "DISPUTED":
            continue

        # Check if any reason field is populated
        has_reason = any(_is_populated(axiom.get(field)) for field in VERDICT_REASON_FIELDS)

        if not has_reason:
            errors.append(
                f"Axiom '{aid}' is DISPUTED but has no reason in any of {VERDICT_REASON_FIELDS}"
            )
        else:
            # Check if verdict_discrepancy specifically is empty (informational)
            if not _is_populated(axiom.get("verdict_discrepancy")):
                disc = axiom.get("verdict_discrepancy")
                evidence = axiom.get("verdict_evidence", "")
                warnings.append(
                    f"Axiom '{aid}' is DISPUTED: verdict_discrepancy is empty, "
                    f"reason is in verdict_evidence ({len(evidence)} chars)"
                )

    if args.verbose:
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        exit_fail(f"VP-003: {len(errors)} DISPUTED axiom(s) lack a stated reason", errors)
    else:
        message = f"VP-003: All DISPUTED axioms have a stated reason"
        if warnings:
            message += f" ({len(warnings)} use verdict_evidence instead of verdict_discrepancy — see --verbose)"
        exit_pass(message)


if __name__ == "__main__":
    main()