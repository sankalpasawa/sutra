#!/bin/bash
# Unit test: feedback-routing-rule.sh
# Covers: positive phrasings emit rule; unrelated prompts silent; kill-switch works

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
HOOK="$PLUGIN_ROOT/hooks/feedback-routing-rule.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

run_case() {
  local name="$1"
  local prompt="$2"
  local expect="$3"  # "emit" or "silent"
  local env_override="${4:-}"

  local payload
  payload=$(jq -nc --arg p "$prompt" '{prompt:$p,hook_event_name:"UserPromptSubmit"}')

  local out
  if [ -n "$env_override" ]; then
    out=$(printf '%s' "$payload" | env "$env_override" bash "$HOOK")
  else
    out=$(printf '%s' "$payload" | bash "$HOOK")
  fi

  local got="silent"
  if echo "$out" | grep -q "sutra-feedback-routing-rule"; then
    got="emit"
  fi

  if [ "$got" = "$expect" ]; then
    _ok "$name (expected $expect)"
  else
    _no "$name (expected $expect, got $got)"
  fi
}

echo "Testing feedback-routing-rule.sh..."

# Positives — should emit the rule
run_case "how-do-i-give-feedback"    "how do I give feedback?"                     "emit"
run_case "submit-feedback"           "I'd like to submit feedback on this"          "emit"
run_case "file-a-bug"                "can you file a bug for me"                    "emit"
run_case "report-a-problem"          "I want to report a problem"                   "emit"
run_case "feedback-channel"          "what's the feedback channel for Sutra?"       "emit"
run_case "file-github-issue"         "please file a github issue about this"        "emit"
run_case "send-feedback"             "how can I send feedback to the team"          "emit"
run_case "mixed-case"                "REPORT A BUG please"                          "emit"

# Negatives — should stay silent
run_case "refactor"                  "refactor this function"                       "silent"
run_case "review-diff"               "review the diff and tell me what's wrong"     "silent"
run_case "feedback-loop-unrelated"   "improve the feedback loop on measurements"    "silent"
run_case "generic-bug-mention"       "this is a bug in my head"                     "silent"
run_case "empty-prompt"              ""                                              "silent"

# Kill-switch
run_case "env-disabled"              "how do I give feedback?"                       "silent"  "FEEDBACK_ROUTING_RULE_DISABLED=1"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
