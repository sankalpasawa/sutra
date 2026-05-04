#!/bin/bash
# csm-cap118-lint.sh — Stop-event hook for cap-118 (no_invented_human_ops_mechanisms).
#
# WHAT: Soft post-response lint per codex 2026-05-04 cap114-split-consult ADVISORY.
# Reads Stop event payload from stdin, extracts last assistant message text from
# the transcript, scans for codex-specified patterns indicating proposals of
# human-ops mechanisms (departments, weekly reviews, standups, etc.).
#
# WHY: cap-114 split required cap-118 to ship as schema + soft lint. Schema
# landed in v2.28.0; this hook closes the lint follow-up so cap-118 can move
# from `shipping (policy-visible)` toward full `shipping` (after 100-turn
# audit + <5% false-positive rate per codex evidence-for-shipping bar).
#
# DESIGN (codex stability advice fold):
# - Composite signal: warn only when ≥2 distinct patterns hit (single hits are
#   too noisy; reduces false-positive training-effect).
# - Log to .enforcement/cap118-lint.jsonl (not stderr by default — prevents
#   founder fatigue). LINT_VERBOSE=1 env enables stderr emission.
# - Allowlist: skip if line is quoted (`>`-prefix), if pattern appears within
#   "existing|already|currently|previously" context (descriptions, not proposals).
#
# Kill-switches:
#   CSM_CAP118_LINT_DISABLED=1
#   ~/.csm-cap118-lint-disabled (file presence)
#
# Build-layer: L0 fleet (sutra/marketplace/plugin/hooks/).

set -u   # not -e: soft-fail (never block Stop event)

[ "${CSM_CAP118_LINT_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.csm-cap118-lint-disabled" ] && exit 0

PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
LOG_DIR="$PROJ/.enforcement"
LOG_FILE="$LOG_DIR/cap118-lint.jsonl"

# Read Stop event JSON from stdin
PAYLOAD="$(cat 2>/dev/null || echo '{}')"

# Extract transcript path (Claude Code Stop hook convention)
TRANSCRIPT=$(echo "$PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -z "$TRANSCRIPT" ] && exit 0
[ ! -f "$TRANSCRIPT" ] && exit 0

# Extract last assistant text turn from transcript (.jsonl)
# Each line is a turn; assistant turns have type="assistant" and message.content[].type="text"
LAST_TEXT=$(jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text' "$TRANSCRIPT" 2>/dev/null | tail -200)
[ -z "$LAST_TEXT" ] && exit 0

# Patterns from sutra-defaults.json:.no_invented_human_ops_mechanisms.lint_patterns_to_flag
# Codex 2026-05-04 ADVISORY specified these.
declare -a PATTERNS=(
  '\bdepartment\b'
  '\bweekly review\b'
  '\bstandup\b'
  '\bmanual KPI\b'
  '\bevery (Monday|Tuesday|Wednesday|Thursday|Friday|day)\b'
  '\bappoint an owner\b'
  '\bmonthly review\b'
  '\bquarterly review\b'
)

# Scan for hits with allowlist heuristics
declare -a HITS=()
declare -a HIT_LINES=()
for pattern in "${PATTERNS[@]}"; do
  # Find candidate lines containing the pattern
  while IFS= read -r line; do
    [ -z "$line" ] && continue

    # Allowlist: skip if line starts with `>` (quote) or has explicit attribution
    case "$line" in
      ">"*|"\""*"\""*|*'said:'*|*'wrote:'*) continue ;;
    esac

    # Allowlist: skip if existing-reality marker is within ~50 chars of the match
    # (describing existing infrastructure, not proposing)
    if echo "$line" | grep -qiE '\b(existing|already|currently|previously|legacy|deprecated|established|in place)\b.{0,80}'"$pattern" 2>/dev/null; then
      continue
    fi
    if echo "$line" | grep -qiE "$pattern"'.{0,80}\b(existing|already|currently|previously|legacy|deprecated|established|in place)\b' 2>/dev/null; then
      continue
    fi

    # Allowlist: skip if critique markers nearby (NOT proposing)
    if echo "$line" | grep -qiE '\b(do not|don'\''t|avoid|never|stop|reject|refuse|forbid)\b.{0,80}'"$pattern" 2>/dev/null; then
      continue
    fi

    HITS+=("$pattern")
    HIT_LINES+=("${line:0:160}")
    break  # one hit per pattern is enough
  done < <(echo "$LAST_TEXT" | grep -iE "$pattern" 2>/dev/null | head -5)
done

# Composite signal: warn only when ≥2 distinct patterns hit
HIT_COUNT=${#HITS[@]}
if [ "$HIT_COUNT" -lt 2 ]; then
  exit 0
fi

# Log to JSONL (always)
mkdir -p "$LOG_DIR" 2>/dev/null
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
HITS_JSON=$(printf '%s\n' "${HITS[@]}" | jq -R . | jq -sc .)
LINES_JSON=$(printf '%s\n' "${HIT_LINES[@]}" | jq -R . | jq -sc .)
jq -nc --arg ts "$TS" --arg hc "$HIT_COUNT" --argjson hits "$HITS_JSON" --argjson lines "$LINES_JSON" \
  '{ts:$ts, action:"CAP118_LINT_HIT", hit_count:($hc|tonumber), patterns:$hits, sample_lines:$lines, schema:"no_invented_human_ops_mechanisms"}' \
  >> "$LOG_FILE" 2>/dev/null

# Verbose mode: emit to stderr too
if [ "${LINT_VERBOSE:-0}" = "1" ]; then
  echo "[CSM·cap-118] LINT: $HIT_COUNT pattern(s) suggest human-ops proposal: ${HITS[*]}" >&2
  echo "[CSM·cap-118] Logged to $LOG_FILE; soft-warn only, exit 0." >&2
fi

exit 0
