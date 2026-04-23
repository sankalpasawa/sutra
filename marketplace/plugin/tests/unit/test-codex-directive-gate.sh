#!/bin/bash
# Unit test: codex-directive-gate.sh
# Covers: no-marker passthrough, matching-PASS clears, FAIL blocks,
# missing-verdict blocks, malformed marker blocks, override clears+logs,
# non-destructive Bash passthrough, destructive Bash blocks, kill-switch,
# non-matching DIRECTIVE-ID does not clear.

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
GATE="$PLUGIN_ROOT/hooks/codex-directive-gate.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

make_marker() {
  local dir="$1" id="$2" ts="$3" match="$4"
  mkdir -p "$dir/.claude"
  cat > "$dir/.claude/codex-directive-pending" <<EOF
DIRECTIVE-ID: $id
TS: $ts
MATCH: $match
EOF
}

make_verdict() {
  local dir="$1" id="$2" verdict="$3" name="$4"
  mkdir -p "$dir/.enforcement/codex-reviews"
  cat > "$dir/.enforcement/codex-reviews/$name.md" <<EOF
# Codex review for directive $id
DIRECTIVE-ID: $id
CODEX-VERDICT: $verdict
findings go here.
EOF
}

run_gate() {
  local dir="$1" tool="$2" cmd="${3:-}" ack="${4:-0}" ack_reason="${5:-}"
  local payload
  if [ "$tool" = "Bash" ]; then
    payload=$(jq -nc --arg t "$tool" --arg c "$cmd" '{tool_name:$t,tool_input:{command:$c}}')
  else
    payload=$(jq -nc --arg t "$tool" '{tool_name:$t,tool_input:{}}')
  fi
  printf '%s' "$payload" | \
    CLAUDE_PROJECT_DIR="$dir" CODEX_DIRECTIVE_ACK="$ack" CODEX_DIRECTIVE_REASON="$ack_reason" \
    bash "$GATE" 2>/dev/null
  echo $?
}

# 1. No marker → allow
{
  D=$(mktemp -d); mkdir -p "$D/.claude"
  rc=$(run_gate "$D" "Edit")
  [ "$rc" -eq 0 ] && _ok "no marker → allow" || _no "no marker but got exit $rc"
  rm -rf "$D"
}

# 2. Marker + matching PASS verdict → clear + allow
{
  D=$(mktemp -d)
  make_marker "$D" "1111" "2026-04-23T22:00:00Z" "use codex to review"
  make_verdict "$D" "1111" "PASS" "v1"
  rc=$(run_gate "$D" "Write")
  if [ "$rc" -eq 0 ] && [ ! -f "$D/.claude/codex-directive-pending" ]; then
    _ok "PASS matching → clear marker + allow"
  else
    _no "PASS matching: exit=$rc marker_still=$([ -f $D/.claude/codex-directive-pending ] && echo yes || echo no)"
  fi
  rm -rf "$D"
}

# 3. Marker + matching FAIL → block
{
  D=$(mktemp -d)
  make_marker "$D" "2222" "2026-04-23T22:00:00Z" "codex review"
  make_verdict "$D" "2222" "FAIL" "v2"
  rc=$(run_gate "$D" "Edit")
  if [ "$rc" -eq 2 ] && [ -f "$D/.claude/codex-directive-pending" ]; then
    _ok "FAIL matching → block + marker remains"
  else
    _no "FAIL matching: exit=$rc"
  fi
  rm -rf "$D"
}

# 4. Marker with no verdict → block
{
  D=$(mktemp -d)
  make_marker "$D" "3333" "2026-04-23T22:00:00Z" "run codex"
  rc=$(run_gate "$D" "Write")
  [ "$rc" -eq 2 ] && _ok "no verdict → block" || _no "no verdict: exit=$rc"
  rm -rf "$D"
}

# 5. Marker + verdict with non-matching DIRECTIVE-ID → block (Codex finding #3)
{
  D=$(mktemp -d)
  make_marker "$D" "4444" "2026-04-23T22:00:00Z" "use codex"
  make_verdict "$D" "9999" "PASS" "v-wrong-id"
  rc=$(run_gate "$D" "Edit")
  if [ "$rc" -eq 2 ] && [ -f "$D/.claude/codex-directive-pending" ]; then
    _ok "non-matching DIRECTIVE-ID → does not clear, blocks"
  else
    _no "non-matching DIRECTIVE-ID: exit=$rc"
  fi
  rm -rf "$D"
}

# 6. Override clears marker + logs
{
  D=$(mktemp -d)
  make_marker "$D" "5555" "2026-04-23T22:00:00Z" "codex should check"
  rc=$(run_gate "$D" "Edit" "" "1" "founder-override-test")
  if [ "$rc" -eq 0 ] && [ ! -f "$D/.claude/codex-directive-pending" ] \
      && grep -q "directive-override" "$D/.enforcement/codex-reviews/gate-log.jsonl" 2>/dev/null; then
    _ok "override → allow + clear + log"
  else
    _no "override: exit=$rc"
  fi
  rm -rf "$D"
}

# 7. Malformed marker → block
{
  D=$(mktemp -d); mkdir -p "$D/.claude"
  echo "garbage content" > "$D/.claude/codex-directive-pending"
  rc=$(run_gate "$D" "Edit")
  [ "$rc" -eq 2 ] && _ok "malformed marker → block (fail-safe)" || _no "malformed: exit=$rc"
  rm -rf "$D"
}

# 8. Bash non-destructive → allow
{
  D=$(mktemp -d)
  make_marker "$D" "6666" "2026-04-23T22:00:00Z" "use codex"
  rc=$(run_gate "$D" "Bash" "ls -la")
  [ "$rc" -eq 0 ] && _ok "Bash non-destructive (ls) → allow" || _no "ls blocked, exit=$rc"
  rm -rf "$D"
}

# 9. Bash destructive (git commit) → block
{
  D=$(mktemp -d)
  make_marker "$D" "7777" "2026-04-23T22:00:00Z" "use codex"
  rc=$(run_gate "$D" "Bash" "git commit -m hello")
  [ "$rc" -eq 2 ] && _ok "Bash destructive (git commit) → block" || _no "git commit allowed, exit=$rc"
  rm -rf "$D"
}

# 10. Bash destructive (rm -rf) → block
{
  D=$(mktemp -d)
  make_marker "$D" "8888" "2026-04-23T22:00:00Z" "use codex"
  rc=$(run_gate "$D" "Bash" "rm -rf /tmp/x")
  [ "$rc" -eq 2 ] && _ok "Bash destructive (rm -rf) → block" || _no "rm -rf allowed, exit=$rc"
  rm -rf "$D"
}

# 11. Kill-switch env → allow
{
  D=$(mktemp -d)
  make_marker "$D" "aaaa" "2026-04-23T22:00:00Z" "use codex"
  payload=$(jq -nc '{tool_name:"Edit",tool_input:{}}')
  printf '%s' "$payload" | CLAUDE_PROJECT_DIR="$D" CODEX_DIRECTIVE_DISABLED=1 bash "$GATE" 2>/dev/null
  rc=$?
  [ "$rc" -eq 0 ] && _ok "kill-switch → allow" || _no "kill-switch ignored, exit=$rc"
  rm -rf "$D"
}

# 12. Verdict with unrecognized text → block
{
  D=$(mktemp -d)
  make_marker "$D" "bbbb" "2026-04-23T22:00:00Z" "use codex"
  mkdir -p "$D/.enforcement/codex-reviews"
  cat > "$D/.enforcement/codex-reviews/v-bad.md" <<EOF
DIRECTIVE-ID: bbbb
(no CODEX-VERDICT line)
EOF
  rc=$(run_gate "$D" "Edit")
  [ "$rc" -eq 2 ] && _ok "unrecognized verdict → block" || _no "unrecognized verdict: exit=$rc"
  rm -rf "$D"
}

echo ""
echo "gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
