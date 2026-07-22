#!/usr/bin/env bash
MARKER="/Users/jwalinshah/projects/axioms/.claude/.preflight-status"
if [ ! -f "$MARKER" ] || [ "$(head -1 "$MARKER")" != "pass" ]; then
  REASON="Axioms preflight has not passed this session. See $MARKER."
  if [ -f "$MARKER" ]; then
    REASON=$(tail -n +2 "$MARKER" | head -c 500)
    REASON="Axioms preflight is failing: $REASON"
  fi
  printf '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": %s}}' "$(printf '%s' "$REASON" | jq -Rs .)"
  exit 0
fi
exit 0
