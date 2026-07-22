#!/usr/bin/env python3
import json
import subprocess
import sys
from datetime import date

REPO = "/Users/jwalinshah/projects/axioms"
MARKER = f"{REPO}/.claude/.preflight-status"


def fail(reason):
    with open(MARKER, "w") as f:
        f.write("fail\n" + reason)
    msg = f"PREFLIGHT FAILED (axioms): {reason} Write/Edit/Bash are blocked until this is fixed. Details: {MARKER}"
    print(json.dumps({"systemMessage": msg}))
    sys.exit(0)


def ok():
    with open(MARKER, "w") as f:
        f.write("pass")
    print("{}")
    sys.exit(0)


try:
    with open(f"{REPO}/axioms.json") as f:
        working = json.load(f)
except Exception as e:
    fail(f"axioms.json is not valid JSON: {e}")

try:
    head_raw = subprocess.run(
        ["git", "-C", REPO, "show", "HEAD:axioms.json"],
        capture_output=True, text=True, check=True,
    ).stdout
    head = json.loads(head_raw)
except Exception as e:
    fail(f"could not load HEAD version of axioms.json for comparison: {e}")

head_by_id = {a["id"]: a for a in head if "id" in a}
today = date.today().isoformat()

offenders = []
for a in working:
    aid = a.get("id")
    if aid in head_by_id:
        old_verdict = head_by_id[aid].get("verdict")
        new_verdict = a.get("verdict")
        if old_verdict != new_verdict:
            verified_at = a.get("verdict_evidence") and a.get("verified_at", "")
            evidence = a.get("verdict_evidence", "")
            is_fresh = str(a.get("verified_at", "")).startswith(today)
            has_evidence = bool(evidence) and len(evidence) > 10
            if not (is_fresh and has_evidence):
                offenders.append(f"{aid}: {old_verdict}->{new_verdict} (verified_at={a.get('verified_at')!r}, evidence_len={len(evidence)})")

if offenders:
    fail(
        "verdict changed without a fresh verified_at + verdict_evidence record for: "
        + "; ".join(offenders[:10])
        + (f" (+{len(offenders)-10} more)" if len(offenders) > 10 else "")
    )

ok()
