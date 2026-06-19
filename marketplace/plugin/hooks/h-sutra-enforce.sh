#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/h-sutra-enforce.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-05-12
# VERSION=v6 (2026-06-11: filter isMeta user rows — skill invocations + stop-hook
#            feedback are role:user/isMeta=True, NOT human turns; v4/v5 false-fired
#            the header check on post-skill narration of skill-invoking turns)
# VERSION=v5 (2026-05-28: malformed-vs-missing diagnostic — case errors now
#            report "DIRECTION·VERB must be UPPERCASE" instead of "header missing")
# VERSION=v4 (filters tool_result user rows; first-text-of-current-turn semantic)
#
# h-sutra-enforce.sh — Stop hook. Identifies the LAST HUMAN user message
# (filtering out tool_result user rows), then checks the FIRST text content
# of the FIRST assistant row after it. That text must start with H-Sutra
# header. If not → decision:block JSON forces redo.
#
# v4 fix (2026-05-12 same-day from v3): Claude Code records tool_results
# as role:user with tool_result-typed content. v3 was finding the latest
# tool_result and walking forward → got the LAST text of turn, not the
# FIRST. v4 filters tool_result user rows to find the true human turn.
#
# Kill: SUTRA_HSUTRA_ENFORCE_DISABLED=1  OR  ~/.h-sutra-enforce-disabled

set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8 2>/dev/null || true

[ "${SUTRA_HSUTRA_ENFORCE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.h-sutra-enforce-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
AUDIT_LOG="$REPO_ROOT/.enforcement/h-sutra-audit.jsonl"
VIOLATIONS_LOG="$REPO_ROOT/.enforcement/governance-violations.jsonl"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"

SESSION_ID="unknown"
TRANSCRIPT_PATH=""
ACTIVE="false"

if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_PAYLOAD" ]; then
  SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null)
  TRANSCRIPT_PATH=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
  ACTIVE=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

audit_log() {
  local decision="$1" first200="$2" reason="${3:-}"
  first200=$(printf '%s' "$first200" | head -c 200 | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  reason=$(printf '%s' "$reason" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"ts":"%s","session_id":"%s","decision":"%s","first200":"%s","reason":"%s"}\n' \
    "$NOW" "$SESSION_ID" "$decision" "$first200" "$reason" \
    >> "$AUDIT_LOG" 2>/dev/null
}

if [ "$ACTIVE" = "true" ]; then
  audit_log "skipped" "" "stop_hook_active=true"
  exit 0
fi

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  audit_log "skipped" "" "no_transcript"
  exit 0
fi

# Identify FIRST TEXT of CURRENT TURN via Python (clean JSONL walk).
# Current turn = everything after the last HUMAN user row (not tool_result).
FIRST_TEXT_OF_TURN=$(TRANSCRIPT_FOR_PY="$TRANSCRIPT_PATH" python3 -c '
import os, sys, json
p = os.environ["TRANSCRIPT_FOR_PY"]
rows = []
try:
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
except: sys.exit(0)

def is_human_user(r):
    if r.get("role") != "user" and r.get("type") != "user":
        return False
    # v6 (2026-06-11): Skill invocations AND stop-hook feedback are recorded
    # as role:user rows with isMeta=True (no promptSource). They are NOT human
    # turns. v4/v5 counted them as human, so on any turn that invoked a Skill
    # the current-turn boundary reset to the skill-injection row and the hook
    # checked the assistant POST-skill narration (no header) instead of the
    # real first response. Filtering isMeta restores true-human-turn semantics.
    # (NOTE: no apostrophes in this block — it lives inside python3 -c '...'.)
    if r.get("isMeta") is True:
        return False
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, str): return True
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                return False
        return True
    return False

last_user = -1
for i, r in enumerate(rows):
    if is_human_user(r):
        last_user = i

for r in rows[last_user+1:]:
    if r.get("role") != "assistant" and r.get("type") != "assistant":
        continue
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                t = b.get("text", "")
                if t:
                    print(t)
                    sys.exit(0)
    elif isinstance(content, str) and content:
        print(content)
        sys.exit(0)
')

if [ -z "$FIRST_TEXT_OF_TURN" ]; then
  audit_log "skipped" "" "no_text_in_current_turn"
  exit 0
fi

FIRST_LINE=$(printf '%s' "$FIRST_TEXT_OF_TURN" | head -1)
FIRST200=$(printf '%s' "$FIRST_TEXT_OF_TURN" | head -c 200)

# v8 (2026-06-19, founder-directed): DIRECTION·VERB now case-insensitive
# ([A-Za-z0-9-] not [A-Z0-9-]). Postel's law — emit UPPERCASE, accept any case.
# Kills the "case-error" block class (was 4/28 violations). Confirmed safe:
# nothing downstream parses the header value by case (grep audit 2026-06-19) —
# the hook is the sole consumer; dashboard + loggers display/log raw.
HEADER_RE='^\[(D[0-9]+|[A-Za-z0-9-]+)·([A-Za-z0-9-]+)( · (TIMING|TENSE|CHANNEL|REV|RISK|attempt):[^]·]+)*\]|^\[STAGE-1-FAIL · CLARIFY( · attempt:[0-9]+/[0-9]+)?\]'

# v7 (2026-06-13, founder-directed): a VALID header that is merely MISPLACED
# (present within the first N non-empty lines, but not line 1) now PASSES with a
# non-blocking nudge instead of forcing a full-response redo. Only a genuinely
# ABSENT or MALFORMED (case-error) header still blocks. Rationale: a
# correctly-formed header on line 2 carries the full scannable info; the redo
# round-trip was pure friction (4 redos in one session, all misplaced-but-valid).
# Tunable: SUTRA_HSUTRA_HEADER_SCAN_LINES (default 8). HDR_POS = 1-based index of
# the first valid header among the opening non-empty lines (empty if none).
SCAN_N="${SUTRA_HSUTRA_HEADER_SCAN_LINES:-8}"
HDR_POS=$(printf '%s\n' "$FIRST_TEXT_OF_TURN" | awk 'NF' | head -n "$SCAN_N" | grep -nE "$HEADER_RE" | head -1 | cut -d: -f1)

if [ "${HDR_POS:-}" = "1" ]; then
  audit_log "pass" "$FIRST200" "header_matched"
  exit 0
elif [ -n "${HDR_POS:-}" ]; then
  # valid header present but not the first non-empty line -> SOFT pass + nudge
  audit_log "pass" "$FIRST200" "header_present_not_first_soft pos=${HDR_POS}"
  printf 'H-Sutra (soft): valid header found at opening line %s, not line 1 -- PASSED, no redo. Next turn, put the bracketed header as the literal first text.\n' "$HDR_POS" >&2
  exit 0
fi

# --- Block branch: diagnose MALFORMED vs MISSING (v5, 2026-05-28) ---
# A first line that is bracket+middot shaped but fails the strict match is
# almost always a CASE error (Title-case/lowercase DIRECTION·VERB). Earlier
# versions reported "header missing" in that case, which is misleading and
# sent at least one author chasing a phantom tool-turn bug. Distinguish so
# the redo guidance is actionable.
if printf '%s' "$FIRST_LINE" | grep -qE '^\[[^]·]+·[^]·]+'; then
  REASON_CODE="header_malformed_layer_fired"
  DIAG="Your first line IS an H-Sutra header but it FAILED the canonical format — almost always a CASE error. DIRECTION and VERB must be UPPERCASE letters/digits/hyphens (or DIRECTION may be Dnn, e.g. D48). Canonical example: [INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]. DIRECTION in {INBOUND|INTERNAL|OUTBOUND} or an UPPERCASE actor (e.g. ASAWA, FOUNDER); VERB in {QUERY|ASSERT|DIRECT|...} UPPERCASE. Re-emit the SAME header with DIRECTION and VERB fully UPPERCASE."
else
  REASON_CODE="header_missing_layer_fired"
  DIAG="No H-Sutra header found as the first text. Emit it as the literal FIRST line before any other text."
fi

audit_log "block" "$FIRST200" "$REASON_CODE"

FIRST_ESC=$(printf '%s' "$FIRST200" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"ts":"%s","session_id":"%s","violation":"h_sutra_header_invalid","reason_code":"%s","layer":"h-sutra","layer_fired":true,"first_line_observed":"%s","action":"stop_blocked_force_redo"}\n' \
  "$NOW" "$SESSION_ID" "$REASON_CODE" "$FIRST_ESC" \
  >> "$VIOLATIONS_LOG" 2>/dev/null

cat <<JSON
{
  "decision": "block",
  "reason": "H-Sutra layer FIRED.\n\n${DIAG}\n\nFormat: [<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]  (or [STAGE-1-FAIL · CLARIFY · attempt:1/1]).\n\nFirst 200 chars observed: '${FIRST_ESC}'\n\nRedo with the corrected header as the literal FIRST line, then continue with Input Routing + Depth blocks per CLAUDE.md."
}
JSON
exit 0
