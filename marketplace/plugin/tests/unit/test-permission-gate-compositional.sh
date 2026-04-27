#!/usr/bin/env bash
# test-permission-gate-compositional.sh — integration test
# Tier 1.5 compositional-read end-to-end: hook + python helper together.
set -u

HOOK="$(cd "$(dirname "$0")/../.." && pwd)/hooks/permission-gate.sh"
export CLAUDE_PLUGIN_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export CLAUDE_PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

run() {
  local cmd="$1"
  printf '{"tool_name":"Bash","tool_input":{"command":%s}}' \
    "$(printf '%s' "$cmd" | jq -R -s .)" | bash "$HOOK"
}

check_allow() {
  local desc="$1" cmd="$2"
  local got
  got=$(run "$cmd" | jq -r '.hookSpecificOutput.decision.behavior // empty' 2>/dev/null)
  if [ "$got" = "allow" ]; then echo "  ok  $desc"
  else echo "FAIL $desc (got='$got')"; exit 1; fi
}

check_passthrough() {
  local desc="$1" cmd="$2"
  local out
  out=$(run "$cmd")
  if [ -z "$out" ]; then echo "  ok  $desc (passthrough)"
  else echo "FAIL $desc (output='$out')"; exit 1; fi
}

# Positive: compositional reads should auto-approve
check_allow     "ls+grep+tail"     'ls .claude/ | grep foo ; tail -3 file.log'
check_allow     "grep+echo+grep+head"   'grep -l x a b ; echo --- ; grep -A1 y f | head -20'
check_allow     "cat+wc"           'cat /tmp/file | wc -l'

# v2.5 trust-mode policy:
#   - Auto-approves: sed, rm-non-recursive, command-sub, git-read, bash -c
#   - Still prompts: git mutations (commit/push), sudo, recursive deletes outside allowlist
check_passthrough "git commit"             'git commit -m hi'
check_allow       "sed (v2.5 trust)"       'sed s/a/b/ file'
check_passthrough "rm -rf / (v2.5 prompt)" 'rm -rf /'
check_allow       "command sub (v2.5)"     'echo $(whoami)'
check_allow       "git -C log (v2.5)"      'git -C /tmp log'
check_allow       "bash -c (v2.5)"         'ls ; bash -c "hi"'

# v2.5 policy: under trust-mode (single-user trusted environment), BASH_FUNC
# shadowing is acceptable risk — user has full local control. The strict v2.4
# compositional path still applies its env-shadow guard, but trust-mode (Tier
# 1.6) intentionally does not. Test accepts either passthrough or allow.
shadow_out=$(printf '{"tool_name":"Bash","tool_input":{"command":"ls | grep foo"}}' | \
  env "BASH_FUNC_ls%%=() {  echo shadowed; }" bash "$HOOK")
shadow_decision=$(echo "$shadow_out" | jq -r '.hookSpecificOutput.decision.behavior // "passthrough"' 2>/dev/null)
if [ "$shadow_decision" = "allow" ] || [ -z "$shadow_out" ]; then
  echo "  ok  env shadow under v2.5 trust-mode (decision=$shadow_decision; user-controlled env trusted)"
else
  echo "FAIL env shadow case (output='$shadow_out')"; exit 1
fi

# Also check the allow path still exists for existing allowlist (Bash(sutra:*))
check_allow "sutra command" "sutra status"

echo ""
echo "all passed"
exit 0
