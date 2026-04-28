#!/bin/bash
# Unit test: codex-directive-detect.sh
# Covers: positive phrasings, negation suppression, code-block strip, latest-wins

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
DETECT="$PLUGIN_ROOT/hooks/codex-directive-detect.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Each case runs in a fresh tmpdir as CLAUDE_PROJECT_DIR
run_case() {
  local name="$1"
  local prompt="$2"
  local expect="$3"  # "match" or "nomatch"

  local TMPDIR
  TMPDIR=$(mktemp -d -t codex-detect-XXXXXX)
  mkdir -p "$TMPDIR/.claude"

  # v3 hook writes session-scoped marker .claude/codex-directive-pending-<SID>;
  # derive a deterministic SID from the case name (sanitized to [a-zA-Z0-9_-])
  # so failures are reproducible.
  local SID="case-${name//[^a-zA-Z0-9_-]/_}"

  local PAYLOAD
  PAYLOAD=$(jq -nc --arg p "$prompt" --arg sid "$SID" \
    '{prompt:$p,hook_event_name:"UserPromptSubmit",session_id:$sid}')

  printf '%s' "$PAYLOAD" | CLAUDE_PROJECT_DIR="$TMPDIR" bash "$DETECT"

  if [ -f "$TMPDIR/.claude/codex-directive-pending-$SID" ]; then
    got="match"
  else
    got="nomatch"
  fi

  if [ "$got" = "$expect" ]; then
    _ok "$name (expected $expect)"
  else
    _no "$name (expected $expect, got $got)"
  fi

  rm -rf "$TMPDIR"
}

# Positives
run_case "plain-directive"          "use codex to review this"             "match"
run_case "run-codex"                 "please run codex on the migration"   "match"
run_case "codex-review-imperative"   "codex review the diff"                "match"
run_case "slash-codex-review"        "/codex review please"                 "match"
run_case "consult-codex"             "consult codex on this design"         "match"
run_case "codex-should-check"        "codex should check these hooks"       "match"
run_case "mixed-case"                "USE CODEX to review"                  "match"

# Negations (suppressed)
run_case "dont-use-codex"            "don't use codex for this one"         "nomatch"
run_case "do-not-run-codex"          "do not run codex yet"                 "nomatch"
run_case "without-codex"             "let's ship without codex this time"   "nomatch"
run_case "no-need-to-codex"          "no need to have codex review"         "nomatch"

# Not-a-directive phrasings
run_case "mentions-only"             "codex was slow last time"             "nomatch"
run_case "noun-form"                 "what does codex think"                "nomatch"
run_case "unrelated-text"            "we should ship the migration soon"    "nomatch"

# Code-block stripping
run_case "fenced-block-only"         $'here is a block:\n```\nuse codex to review\n```\njust FYI'  "nomatch"
run_case "inline-backtick-only"      'see `use codex` in docs for history'  "nomatch"
run_case "positive-outside-fenced"   $'before\n```\nnot relevant\n```\nuse codex to review this'  "match"

# Empty / missing prompt
run_case "empty-prompt"              ""                                     "nomatch"

# Latest-wins (second prompt overwrites marker — same session, same SID)
{
  TMPDIR=$(mktemp -d -t codex-detect-lw-XXXXXX)
  mkdir -p "$TMPDIR/.claude"
  SID="latest-wins-test"
  P1=$(jq -nc --arg p "use codex to review plan A" --arg sid "$SID" '{prompt:$p,session_id:$sid}')
  P2=$(jq -nc --arg p "use codex to review plan B" --arg sid "$SID" '{prompt:$p,session_id:$sid}')
  printf '%s' "$P1" | CLAUDE_PROJECT_DIR="$TMPDIR" bash "$DETECT"
  ID1=$(grep DIRECTIVE-ID "$TMPDIR/.claude/codex-directive-pending-$SID" | awk '{print $2}')
  sleep 1
  printf '%s' "$P2" | CLAUDE_PROJECT_DIR="$TMPDIR" bash "$DETECT"
  ID2=$(grep DIRECTIVE-ID "$TMPDIR/.claude/codex-directive-pending-$SID" | awk '{print $2}')
  MATCH2=$(grep MATCH "$TMPDIR/.claude/codex-directive-pending-$SID" | cut -d' ' -f2-)
  if [ "$ID1" != "$ID2" ] && printf '%s' "$MATCH2" | grep -q "plan b"; then
    _ok "latest-wins (second directive overwrites marker)"
  else
    _no "latest-wins failed (id1=$ID1, id2=$ID2, match2=$MATCH2)"
  fi
  rm -rf "$TMPDIR"
}

# Kill-switch
{
  TMPDIR=$(mktemp -d -t codex-detect-ks-XXXXXX)
  mkdir -p "$TMPDIR/.claude"
  SID="kill-switch-test"
  P=$(jq -nc --arg p "use codex to review" --arg sid "$SID" '{prompt:$p,session_id:$sid}')
  printf '%s' "$P" | CLAUDE_PROJECT_DIR="$TMPDIR" CODEX_DIRECTIVE_DISABLED=1 bash "$DETECT"
  if [ ! -f "$TMPDIR/.claude/codex-directive-pending-$SID" ]; then
    _ok "kill-switch CODEX_DIRECTIVE_DISABLED suppresses detection"
  else
    _no "kill-switch ignored — marker was written"
  fi
  rm -rf "$TMPDIR"
}

echo ""
echo "detect: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
