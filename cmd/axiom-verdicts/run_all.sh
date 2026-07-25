#!/usr/bin/env bash
# run_all.sh — Run all TestAX VP gates and report results.
#
# Usage:
#   bash cmd/axiom-verdicts/run_all.sh
#   bash cmd/axiom-verdicts/run_all.sh --verbose
#   bash cmd/axiom-verdicts/run_all.sh --corpus /path/to/axioms.json
#
# Exit code: 0 if all gates pass, 1 if any gate fails.

set -o pipefail
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CORPUS="${REPO_DIR}/axioms.json"
VERBOSE=""
ARGS=""

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --verbose)
            VERBOSE="--verbose"
            ARGS="$ARGS --verbose"
            ;;
        --corpus=*)
            CORPUS="${arg#*=}"
            ARGS="$ARGS --corpus=${CORPUS}"
            ;;
        --corpus)
            # Skip --corpus value; handled in next iteration
            ;;
        *)
            # Could be the value for --corpus from previous iteration
            if [[ "$arg" != --* ]]; then
                ARGS="$ARGS $arg"
            fi
            ;;
    esac
done

GATES=(
    "testax_vp001.py:VP-001:Every verdict names an axiom that exists"
    "testax_vp002.py:VP-002:Every verdict is from a closed vocabulary"
    "testax_vp003.py:VP-003:A dispute must have a stated reason"
    "testax_vp004.py:VP-004:Coverage check — fail closed"
    "testax_vp005.py:VP-005:Idempotent merge"
)

echo "==========================================="
echo " TestAX VP Gates — Verdict Persistence Suite"
echo " Corpus: ${CORPUS}"
echo "==========================================="
echo ""

PASSED=0
FAILED=0
FAILED_NAMES=""

for gate_entry in "${GATES[@]}"; do
    IFS=":" read -r filename gate_id description <<< "$gate_entry"
    gate_path="${SCRIPT_DIR}/${filename}"

    if [ ! -f "$gate_path" ]; then
        echo "  [SKIP] ${gate_id}: Gate file not found: ${gate_path}"
        continue
    fi

    echo -n "  [....] ${gate_id}: ${description} ... "

    if python3 "$gate_path" --corpus="$CORPUS" $VERBOSE > /tmp/testax_${gate_id}.out 2>&1; then
        echo -e "\r  [PASS] ${gate_id}: ${description}"
        PASSED=$((PASSED + 1))
    else
        echo -e "\r  [FAIL] ${gate_id}: ${description}"
        while IFS= read -r line; do
            echo "         ${line}"
        done < /tmp/testax_${gate_id}.out
        FAILED=$((FAILED + 1))
        FAILED_NAMES="${FAILED_NAMES} ${gate_id}"
    fi
done

echo ""
echo "==========================================="
echo " Results: ${PASSED} passed, ${FAILED} failed"
echo "==========================================="

if [ "$FAILED" -gt 0 ]; then
    echo "Failed gates:${FAILED_NAMES}"
    exit 1
fi
exit 0