"""
Shared utilities for TestAX VP gates.

Provides:
- load_corpus(): Load axioms.json from the repo root or a custom path.
- resolve_corpus_path(): Find the canonical axioms.json path.
- AXIOM_FIELDS: Known field names in the corpus.
- CLOSED_VERDICTS: The allowed verdict vocabulary.
"""
import argparse
import json
import os
import sys

# The allowed verdict vocabulary. Maps to the tensor equation:
# v.verdict ∈ {VERIFIED, DISPUTED, UNCERTAIN, DUPLICATE}
CLOSED_VERDICTS = frozenset({"VERIFIED", "DISPUTED", "UNCERTAIN", "DUPLICATE"})

# Fields that carry verdict reason/evidence
VERDICT_REASON_FIELDS = ("verdict_discrepancy", "verdict_evidence")

# Known fields in the corpus (for reference/documentation)
AXIOM_FIELDS = (
    "category", "citation", "citation_rfc", "citation_section",
    "confidence", "counterexample", "id", "inv_code", "invariant",
    "prompt_information", "prompt_injection", "redpattern",
    "redteam_pattern", "redteam_template", "severity", "source",
    "source_document", "source_file", "source_section", "source_type",
    "static_check", "tensor_equation", "title", "verdict",
    "verdict_confidence", "verdict_discrepancy", "verdict_evidence",
    "verification", "verified_at",
)


def resolve_corpus_path() -> str:
    """Resolve the path to the canonical axioms.json file.

    Order of precedence:
    1. AXIOMS_CORPUS environment variable
    2. ../axioms.json relative to this script's directory
    3. cmd/../axioms.json relative to this script's directory
    """
    env_path = os.environ.get("AXIOMS_CORPUS")
    if env_path:
        return env_path

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Walk up from cmd/axiom-verdicts/ -> cmd/ -> axioms/
    for candidate in (
        os.path.join(script_dir, "..", "..", "axioms.json"),
        os.path.join(script_dir, "..", "axioms.json"),
    ):
        candidate = os.path.normpath(candidate)
        if os.path.isfile(candidate):
            return candidate

    return os.path.normpath(os.path.join(script_dir, "..", "..", "axioms.json"))


def load_corpus(corpus_path: str | None = None) -> list[dict]:
    """Load the axioms corpus from a JSON file.

    Args:
        corpus_path: Path to axioms.json. If None, resolved automatically.

    Returns:
        List of axiom dicts.

    Raises:
        FileNotFoundError: If the corpus file does not exist.
        json.JSONDecodeError: If the corpus is not valid JSON.
    """
    path = corpus_path or resolve_corpus_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Axiom corpus not found: {path}")
    with open(path, "r") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise TypeError(f"Expected JSON array, got {type(data).__name__}")
    return data


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add standard arguments shared across VP gates."""
    parser.add_argument(
        "--corpus",
        default=None,
        help="Path to axioms.json (default: auto-resolve)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed pass/fail per axiom",
    )


def exit_pass(message: str = "") -> None:
    """Exit with code 0 (PASS)."""
    if message:
        print(f"PASS: {message}")
    sys.exit(0)


def exit_fail(message: str, details: list[str] | None = None) -> None:
    """Exit with code 1 (FAIL)."""
    print(f"FAIL: {message}", file=sys.stderr)
    if details:
        for d in details:
            print(f"  {d}", file=sys.stderr)
    sys.exit(1)