#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/per-turn-hard-gate.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-07-20
#
# per-turn-hard-gate.sh -- Stop-event FLOOR for the Class-A per-turn blocks that
# were previously enforced ONLY at mutation-time (PreToolUse Edit|Write) and so
# were skippable on no-tool turns (a one-line answer, a yes/no, a question).
#
# Canon:   holding/FOUNDER-DIRECTIONS.md §D63 (2026-07-20, "make everything a
#          hard block, like a contract, not a soft nudge" -- fleet-wide).
# Event:   Stop (end of every assistant turn).
# Enforcement: HARD, fleet-wide. Forces exactly one redo if the turn's response
#          text is missing the Input Routing block or the Depth block -- and,
#          since 2026-07-27, the BLUEPRINT block on any turn that mutated a
#          governed file (blueprint-check.sh v3 handed ordinary files to this
#          floor and kept PreToolUse enforcement for foundational paths only).
#
# Why a Stop hook: Input Routing (input-classification-gate.sh) and Depth
# (depth-marker-pretool.sh) are floored at PreToolUse on Edit|Write only. A
# pure no-tool turn fires no tool, so those gates never run -> the blocks were
# soft on exactly the turns that skip tools. H-Sutra (h-sutra-enforce.sh) and
# Flow (flow-stop-check.sh) already floor at Stop; this hook closes the same
# hole for Input Routing + Depth. Together the four Class-A blocks now fire on
# EVERY turn.
#
# TRANSCRIPT-BASED (not marker-based): checks the ACTUAL response text for the
# blocks, mirroring h-sutra-enforce.sh. This is stronger than a proxy marker
# (a marker can be written without emitting the block) and adds no per-turn
# marker bookkeeping tax. Cost: one python transcript walk (~tens of ms).
#
# LOOP SAFETY (non-negotiable): honors stop_hook_active. The FIRST Stop where a
# block is missing blocks (one redo); on the re-invoked turn stop_hook_active=
# true and this hook PASSES. A client can never infinite-loop.
#
# Kill-switch (2-level):
#   - PER_TURN_HARD_DISABLED=1        (per-shell env)
#   - $HOME/.per-turn-hard-disabled   (per-machine fs)
# Override (per-turn, audit-logged):
#   - PER_TURN_HARD_ACK=1 PER_TURN_HARD_ACK_REASON='<why>'
#
# Fail-open on infra failure (no transcript, no python) -> exit 0, never trap.

set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8 2>/dev/null || true

# -- Kill-switches (either bypasses) ---------------------------------------
[ "${PER_TURN_HARD_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.per-turn-hard-disabled" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -z "$REPO_ROOT" ] && exit 0

# -- Fresh-install gate (codex challenge finding (d), 2026-07-20) -----------
# Stay silent until the user has run /core:start, which writes BOTH
# .claude/sutra-project.json AND the governance contract into their CLAUDE.md.
# Enforcing before that ambushes a user who was never handed the contract --
# codex's top blast-radius finding. Enforcement and contract activate together.
# Escape: SUTRA_DISCIPLINE_PRE_ACTIVATION=1.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$REPO_ROOT/.claude/sutra-project.json" ]; then
  exit 0
fi

mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
LEDGER="$REPO_ROOT/.enforcement/per-turn-hard.jsonl"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

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

log_row() {
  local decision="$1" reason="$2"
  reason=$(printf '%s' "$reason" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"ts":"%s","session_id":"%s","decision":"%s","reason":"%s"}\n' \
    "$NOW" "$SESSION_ID" "$decision" "$reason" >> "$LEDGER" 2>/dev/null
}

# -- Override (PER_TURN_HARD_ACK=1 -> audit-log + pass) ---------------------
if [ "${PER_TURN_HARD_ACK:-0}" = "1" ]; then
  R=$(printf '%s' "${PER_TURN_HARD_ACK_REASON:-no-reason}" | tr -d '\n\r' | head -c 300)
  log_row "override" "$R"
  exit 0
fi

# -- Loop-breaker: already forced one redo this turn -> PASS (never trap) ---
if [ "$ACTIVE" = "true" ]; then
  log_row "skipped" "stop_hook_active"
  exit 0
fi

# -- Fail-open if we cannot inspect the transcript -------------------------
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  log_row "skipped" "no_transcript"
  exit 0
fi
command -v python3 >/dev/null 2>&1 || { log_row "skipped" "no_python3"; exit 0; }

# -- Concatenate ALL assistant text of the CURRENT TURN --------------------
# Current turn = everything after the last HUMAN user row (filtering isMeta +
# tool_result rows, same semantics as h-sutra-enforce.sh v6). Lenient by
# design: we accept the blocks anywhere in the turn's text, not just line 1,
# to avoid false-positive redos.
TURN_RAW=$(TRANSCRIPT_FOR_PY="$TRANSCRIPT_PATH" python3 -c '
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

MUTATORS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

out = []
edited = []
for r in rows[last_user+1:]:
    if r.get("role") != "assistant" and r.get("type") != "assistant":
        continue
    content = r.get("message", {}).get("content") or r.get("content")
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict): continue
            if b.get("type") == "text":
                t = b.get("text", "")
                if t: out.append(t)
            elif b.get("type") == "tool_use" and b.get("name") in MUTATORS:
                fp = (b.get("input") or {}).get("file_path") or ""
                edited.append(str(fp).replace("\n", " "))
    elif isinstance(content, str) and content:
        out.append(content)

# Two sections so bash can apply the BLUEPRINT whitelist to the edited paths
# without a second transcript walk.
print("__SUTRA_EDITED__")
for e in edited:
    print(e)
print("__SUTRA_TEXT__")
print("\n".join(out))
')

# -- Split the two sections -------------------------------------------------
EDITED_PATHS=$(printf '%s\n' "$TURN_RAW" | sed -n '/^__SUTRA_EDITED__$/,/^__SUTRA_TEXT__$/p' | sed '1d;$d')
TURN_TEXT=$(printf '%s\n' "$TURN_RAW" | sed -n '/^__SUTRA_TEXT__$/,$p' | sed '1d')

# No assistant text at all (pure tool turn, no prose) -> nothing to enforce.
if [ -z "$TURN_TEXT" ]; then
  log_row "skipped" "no_text_in_current_turn"
  exit 0
fi

# -- Presence checks -------------------------------------------------------
# LINE-ANCHORED (codex challenge finding P1, 2026-07-20): the tokens must start
# a line (after optional whitespace / a code-fence indent). This defeats the
# spoof "I forgot to include INPUT:, TYPE: task, DEPTH: 3/5" (tokens mid-prose)
# and incidental quotes/docs/diagnostics, while a real emitted block -- whose
# fields ARE at line start -- still matches.
MISSING=""
# Input Routing: needs an INPUT: line AND a TYPE: line naming a routing class.
if ! printf '%s' "$TURN_TEXT" | grep -qE '^[[:space:]]*INPUT:' \
   || ! printf '%s' "$TURN_TEXT" | grep -qE '^[[:space:]]*TYPE:[[:space:]]*.*(direction|task|feedback|new concept|question)'; then
  MISSING="${MISSING}Input-Routing "
fi
# Depth: needs a DEPTH: N/5 line (N in 1..5) at line start.
if ! printf '%s' "$TURN_TEXT" | grep -qE '^[[:space:]]*DEPTH:[[:space:]]*[1-5][[:space:]]*/[[:space:]]*5'; then
  MISSING="${MISSING}Depth "
fi

# BLUEPRINT (added 2026-07-27) — required only when this turn actually MUTATED a
# governed file. blueprint-check.sh v3 stopped HARD-blocking ordinary files at
# PreToolUse (it kept foundational paths only, where pre-spend visibility is
# real); this Stop floor is where the contract lands for everything else — one
# redo, loop-safe, the same guarantee D63 already gives Input Routing + Depth.
# Honors the BLUEPRINT kill-switches so a single switch disarms both layers.
BP_REQUIRED=0
if [ -z "${BLUEPRINT_DISABLED:-}" ] && [ ! -f "$HOME/.blueprint-disabled" ] \
   && [ "${BLUEPRINT_ACK:-0}" != "1" ] && [ -n "$EDITED_PATHS" ]; then
  # Whitelist mirrors blueprint-check.sh — a turn that only touched .claude/,
  # a TODO, or a .jsonl ledger owes no BLUEPRINT.
  while IFS= read -r _p; do
    [ -z "$_p" ] && continue
    case "$_p" in
      "$REPO_ROOT"/*) _rel="${_p#"$REPO_ROOT"/}" ;;
      /*) continue ;;                      # outside the repo — out of scope (#80)
      *) _rel="$_p" ;;
    esac
    case "$_rel" in
      *.lock|*.log|*.jsonl) continue ;;
      .claude/*|.enforcement/*|.analytics/*) continue ;;
      */TODO.md|*/BACKLOG.md|*/CHANGELOG.md|*/MEMORY.md) continue ;;
      holding/checkpoints/*) continue ;;
      sutra/archive/*) continue ;;
    esac
    BP_REQUIRED=1
    break
  done <<EOF
$EDITED_PATHS
EOF
fi
if [ "$BP_REQUIRED" = "1" ]; then
  # Presence only — the deep field validation (Output looks like / Verified by /
  # per-step Verify) stays at PreToolUse on foundational paths. Tolerant of the
  # three emitted shapes: ASCII box, markdown heading, bare field-set.
  if ! printf '%s' "$TURN_TEXT" | grep -qE '^[^A-Za-z]*BLUEPRINT' \
     && ! printf '%s' "$TURN_TEXT" | grep -qiE '^[^A-Za-z]*Doing[^:]*:'; then
    MISSING="${MISSING}BLUEPRINT "
  fi
fi

MISSING="${MISSING% }"

if [ -z "$MISSING" ]; then
  log_row "pass" "both_present"
  exit 0
fi

# -- Missing block(s) -> force exactly one redo (HARD, D63) -----------------
log_row "block" "missing:${MISSING}"
MISSING_ESC=$(printf '%s' "$MISSING" | tr -d '\n' | sed 's/"/\\"/g')
cat <<JSON
{
  "decision": "block",
  "reason": "PER-TURN HARD GATE FIRED (D63).\n\nThis turn's response is missing required governance block(s): ${MISSING_ESC}.\n\nPer D63 the full per-turn stack is HARD every turn (like Input Routing / the H-Sutra header), including no-tool turns. Redo this response with:\n  - Input Routing block (INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION)\n  - Depth block (TASK / DEPTH X/5 / EFFORT / COST / IMPACT)\n  - BLUEPRINT block (Doing / Steps / Output looks like / Verified by / Scale / Stops-if) -- listed only when this turn edited or wrote a governed file\nas literal text near the top, per the /core:start CLAUDE.md contract. Then continue.\n\nIf intentional: PER_TURN_HARD_ACK=1 PER_TURN_HARD_ACK_REASON='<why>' (or PER_TURN_HARD_DISABLED=1 / touch ~/.per-turn-hard-disabled)."
}
JSON
exit 0
