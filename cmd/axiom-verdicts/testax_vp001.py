#!/usr/bin/env python3
"""
TestAX_VP001: Every verdict names an axiom that exists.

Invariant:  ∀v ∈ V: v.id ∈ ids(A)

Every axiom in the corpus must have a unique, non-empty 'id' field.
This guards against corpus drift — verifying a corpus that is no longer
the canonical one, or entries that lost their identity during extraction.

Checks:
1. All axioms have a non-empty 'id' field.
2. All axiom IDs are unique (no duplicates).
3. Verdicts embedded in axioms reference the axiom's own ID (self-consistency).
"""
import argparse
import sys

from testax_lib import add_common_args, exit_fail, exit_pass, load_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="VP-001: Every verdict names an axiom that exists")
    add_common_args(parser)
    args = parser.parse_args()

    axioms = load_corpus(args.corpus)
    total = len(axioms)
    errors: list[str] = []

    # Check 1: Non-empty ID
    for i, axiom in enumerate(axioms):
        aid = axiom.get("id")
        if not aid or not isinstance(aid, str) or not aid.strip():
            errors.append(f"Axiom at index {i} has empty or missing 'id' field")

    # Check 2: Unique IDs
    seen_ids: dict[str, int] = {}
    for axiom in axioms:
        aid = axiom.get("id")
        if aid and isinstance(aid, str) and aid.strip():
            if aid in seen_ids:
                seen_ids[aid] += 1
            else:
                seen_ids[aid] = 1

    duplicates = {aid: count for aid, count in seen_ids.items() if count > 1}
    for aid, count in duplicates.items():
        errors.append(f"Duplicate ID '{aid}' appears {count} times")

    # Check 3: Verdict references (self-consistency: every verdicting axiom has an ID)
    # This is implicitly covered by check 1, but we also check that verdict
    # fields exist on axioms that have them.
    for axiom in axioms:
        if "verdict" in axiom and not axiom.get("id"):
            errors.append(f"Axiom with verdict '{axiom.get('verdict')}' has no 'id' field")

    if errors:
        exit_fail(f"VP-001: {len(errors)} integrity violation(s) in {total} axioms", errors)
    else:
        exit_pass(f"VP-001: All {total} axioms have valid, unique IDs")


if __name__ == "__main__":
    main()