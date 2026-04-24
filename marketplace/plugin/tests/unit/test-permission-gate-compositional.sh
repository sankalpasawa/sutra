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

# Passthrough: not in Tier 1.5 — should fall through to normal prompt
check_passthrough "git commit"     'git commit -m hi'
check_passthrough "sed"            'sed s/a/b/ file'
check_passthrough "rm"             'rm -rf /'
check_passthrough "command sub"    'echo $(whoami)'
check_passthrough "git -C"         'git -C /tmp log'
check_passthrough "bash -c"        'ls ; bash -c "hi"'

# Env shadowing: even safe-looking commands should NOT auto-approve when shadowed
shadow_out=$(printf '{"tool_name":"Bash","tool_input":{"command":"ls | grep foo"}}' | \
  env "BASH_FUNC_ls%%=() {  echo shadowed; }" bash "$HOOK")
if [ -z "$shadow_out" ]; then
  echo "  ok  env shadow BASH_FUNC_ls%% -> passthrough"
else
  echo "FAIL env shadow guard (output='$shadow_out')"; exit 1
fi

# Also check the allow path still exists for existing allowlist (Bash(sutra:*))
check_allow "sutra command" "sutra status"

echo ""
echo "all passed"
exit 0
