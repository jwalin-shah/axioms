#!/usr/bin/env python3
"""
TestAX_VP002: Every verdict is from a closed vocabulary.

Invariant:  ∀v ∈ V: v.verdict ∈ {VERIFIED, DISPUTED, UNCERTAIN, DUPLICATE}

An unrecognized verdict value is a broken producer. The vocabulary is:
- VERIFIED:  Source citation is correct, axiom faithfully represents it
- DISPUTED:  Something is wrong with the axiom
- UNCERTAIN: Verifier could not decide
- DUPLICATE: Redundant with another axiom

This gate checks that no verdict value outside this set exists in the corpus.
Axioms without a 'verdict' key are treated as missing (not invalid vocabulary)
and flagged as a separate warning.
"""
import argparse
import sys

from testax_lib import CLOSED_VERDICTS, add_common_args, exit_fail, exit_pass, load_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="VP-002: Every verdict is from a closed vocabulary")
    add_common_args(parser)
    args = parser.parse_args()

    axioms = load_corpus(args.corpus)
    total = len(axioms)
    errors: list[str] = []
    warnings: list[str] = []

    for axiom in axioms:
        aid = axiom.get("id", "unknown")
        verdict = axiom.get("verdict")

        if verdict is None:
            warnings.append(f"Axiom '{aid}' has no 'verdict' field (missing, not invalid)")
            continue

        if verdict not in CLOSED_VERDICTS:
            errors.append(f"Axiom '{aid}' has verdict '{verdict}' which is not in {sorted(CLOSED_VERDICTS)}")

    if args.verbose:
        for w in warnings:
            print(f"  WARN: {w}")

    verdict_counts = {}
    for axiom in axioms:
        v = axiom.get("verdict")
        if v in CLOSED_VERDICTS:
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
        elif v is not None:
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

    if args.verbose:
        print(f"  Verdict distribution: {verdict_counts}")

    if errors:
        exit_fail(f"VP-002: {len(errors)} axiom(s) have unrecognized verdicts", errors)
    else:
        exit_pass(f"VP-002: All {total - len(warnings)} verdicts are in the closed vocabulary {sorted(CLOSED_VERDICTS)}")


if __name__ == "__main__":
    main()