#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/perturn-text-validate.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-06-29
# VERSION=v1 (2026-06-29: A4 — validate the EMITTED TEXT of Input Routing, Depth,
#            and Output Trace in one Stop-time pass. Completes the reframed A4
#            block-text-validation set: h-sutra-enforce.sh (header) +
#            blueprint-text-validate.sh (BLUEPRINT, PreToolUse) + this.)
#
# perturn-text-validate.sh — Stop hook.
#
# WHY (A4): input-classification-gate.sh, depth-marker-pretool.sh validate only
# self-asserted MARKER files (.claude/input-routed, .claude/depth-registered).
# A model can write a perfect marker and emit a garbled, partial, or absent
# block in the text the USER actually sees, and the marker gate waves it through.
# Output Trace had no validator at all. This hook reads the transcript, finds the
# three blocks in the text the user sees, and validates their CONTENT in ONE pass
# -> ONE consolidated repair message (so a single redo fixes everything, not
# three sequential redos).
#
# Validates (presence + well-formedness only — NOT richness; block content may be
# minimal on trivial turns per topic_gating "structure universality"):
#   Input Routing : INPUT anchor + a TYPE in {direction|task|feedback|new concept
#                   |question} + ROUTE.  (Compact form 'INPUT ... (task)' ok.)
#   Depth         : DEPTH: N with N in 1..5 + TASK/EFFORT/COST/IMPACT present.
#   Output Trace  : an 'OS:' / 'OS TRACE:' line with >= 2 '>' segment separators.
#
# Contracts are read from sutra-defaults.json .block_text_validation via jq, with
# hardcoded fallbacks so a missing file / no-jq host fails OPEN.
#
# LOOP SAFETY (non-negotiable): honors stop_hook_active (same as h-sutra-enforce.sh
# + flow-stop-check.sh). The FIRST Stop with an invalid block blocks (one redo);
# on the re-invoked turn stop_hook_active=true -> PASS. Never infinite-loops.
#
# Fail-open: no jq / no python3 / no transcript / parse error -> exit 0 (D40).
#
# Kill: PERTURN_TEXT_VALIDATE_DISABLED=1  OR  ~/.perturn-text-validate-disabled
#       SUTRA_DEFAULTS_DISABLED=1         OR  ~/.sutra-defaults-disabled (all D40)
# Override (per-turn, audit-logged): PERTURN_TEXT_ACK=1 PERTURN_TEXT_ACK_REASON='<why>'

set -u
export LC_ALL=C.UTF-8 LANG=C.UTF-8 2>/dev/null || true

# ── Kill-switches ──
[ "${PERTURN_TEXT_VALIDATE_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.perturn-text-validate-disabled" ] && exit 0
[ "${SUTRA_DEFAULTS_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.sutra-defaults-disabled" ] && exit 0

command -v python3 >/dev/null 2>&1 || exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EXTRACT="$PLUGIN_ROOT/lib/extract_turn_text.py"
SCHEMA="$PLUGIN_ROOT/sutra-defaults.json"
AUDIT="$REPO_ROOT/.enforcement/governance-violations.jsonl"

STDIN_PAYLOAD=""
[ ! -t 0 ] && STDIN_PAYLOAD="$(cat 2>/dev/null || true)"

SESSION_ID="unknown"; TRANSCRIPT_PATH=""; ACTIVE="false"
if command -v jq >/dev/null 2>&1 && [ -n "$STDIN_PAYLOAD" ]; then
  SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // "unknown"' 2>/dev/null)
  TRANSCRIPT_PATH=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.transcript_path // empty' 2>/dev/null)
  ACTIVE=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.stop_hook_active // false' 2>/dev/null)
fi

# ── Loop safety: never pile a second redo onto an already-continuing turn ──
[ "$ACTIVE" = "true" ] && exit 0

# ── Override (audit-logged) ──
if [ "${PERTURN_TEXT_ACK:-0}" = "1" ]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  REASON=$(printf '%s' "${PERTURN_TEXT_ACK_REASON:-no-reason}" | tr -d '\n\r"\\' | head -c 300)
  printf '{"ts":"%s","event":"perturn-text-override","reason":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$REASON" >> "$AUDIT" 2>/dev/null
  exit 0
fi

[ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ] && exit 0
[ -f "$EXTRACT" ] || exit 0

# ── Extract current-turn text (shared lib = one definition of the turn boundary) ──
TURN_TEXT=$(python3 "$EXTRACT" "$TRANSCRIPT_PATH" all 2>/dev/null)
[ -z "$TURN_TEXT" ] && exit 0

# ── Schema-driven params (jq) with hardcoded fallbacks (fail-open) ──
TYPE_ENUM="direction|task|feedback|new concept|question"
DEPTH_MIN=1; DEPTH_MAX=5
TRACE_RE='^OS( TRACE)?:'
if command -v jq >/dev/null 2>&1 && [ -f "$SCHEMA" ]; then
  _enabled=$(jq -r '.block_text_validation.enabled // true' "$SCHEMA" 2>/dev/null)
  [ "$_enabled" = "false" ] && exit 0
  _e=$(jq -r '.block_text_validation.input_routing.type_enum // [] | join("|")' "$SCHEMA" 2>/dev/null)
  [ -n "$_e" ] && TYPE_ENUM="$_e"
  _dn=$(jq -r '.block_text_validation.depth_estimation.depth_min // 1' "$SCHEMA" 2>/dev/null)
  _dx=$(jq -r '.block_text_validation.depth_estimation.depth_max // 5' "$SCHEMA" 2>/dev/null)
  case "$_dn" in ''|*[!0-9]*) ;; *) DEPTH_MIN="$_dn" ;; esac
  case "$_dx" in ''|*[!0-9]*) ;; *) DEPTH_MAX="$_dx" ;; esac
fi

# ── Validate (python) -> prints "ok" or "fail\t<consolidated message>" ──
VERDICT=$(BTV_TEXT="$TURN_TEXT" BTV_TYPE_ENUM="$TYPE_ENUM" \
          BTV_DMIN="$DEPTH_MIN" BTV_DMAX="$DEPTH_MAX" python3 -c '
import os, re, sys

text = os.environ.get("BTV_TEXT", "")
type_enum = [t.strip().lower() for t in os.environ.get("BTV_TYPE_ENUM", "").split("|") if t.strip()]
dmin = int(os.environ.get("BTV_DMIN", "1") or "1")
dmax = int(os.environ.get("BTV_DMAX", "5") or "5")

# Strip ASCII-box pipes so "| DEPTH: 4 |" -> "DEPTH: 4".
def declutter(line):
    s = line.strip()
    if s.startswith("|"): s = s[1:]
    s = re.sub(r"\s*\|\s*$", "", s)
    return s.strip()

lines = [declutter(l) for l in text.splitlines()]
errs = []

def has_line(pat):
    rx = re.compile(pat, re.IGNORECASE)
    return any(rx.search(l) for l in lines)

def find_line(pat):
    rx = re.compile(pat, re.IGNORECASE)
    for l in lines:
        m = rx.search(l)
        if m: return l, m
    return None, None

# ---- Input Routing ----
if not has_line(r"^INPUT\b"):
    errs.append("Input Routing: missing (no INPUT line)")
else:
    # TYPE: explicit "TYPE: x" line OR an enum word in parens on the INPUT line.
    tval = None
    tl, tm = find_line(r"^TYPE:\s*(.+)$")
    if tm:
        tval = tm.group(1).strip().lower()
        # take first token-ish chunk before any separator
        tval = re.split(r"[\.;,/]| - | \(", tval)[0].strip()
    if tval is None:
        il, im = find_line(r"^INPUT\b.*\(([^)]+)\)")
        if im: tval = im.group(1).strip().lower()
    if tval is None:
        errs.append("Input Routing: missing TYPE (need TYPE: one of {%s})" % "|".join(type_enum))
    elif type_enum and not any(tval == e or tval.startswith(e) or e in tval for e in type_enum):
        errs.append("Input Routing: TYPE \"%s\" not in {%s}" % (tval[:30], "|".join(type_enum)))
    if not has_line(r"^ROUTE\b"):
        errs.append("Input Routing: missing ROUTE line")

# ---- Depth ----
# Anchor at line start: the Output Trace line ("... > depth 3 > ...") must NOT
# satisfy the Depth-block check. The Depth block leads its line with "DEPTH".
dl, dm = find_line(r"^DEPTH\b:?\s*([0-9]+)")
if dm is None:
    errs.append("Depth: missing (no DEPTH: N line)")
else:
    n = int(dm.group(1))
    if n < dmin or n > dmax:
        errs.append("Depth: DEPTH=%d out of range %d..%d" % (n, dmin, dmax))
    missing = [f for f in ("TASK", "EFFORT", "COST", "IMPACT") if not has_line(r"^%s\b" % f)]
    if missing:
        errs.append("Depth: missing field(s): %s" % ", ".join(missing))

# ---- Output Trace ----
ol, om = find_line(r"^OS( TRACE)?:")
if om is None:
    errs.append("Output Trace: missing (no \"OS:\" line)")
else:
    if ol.count(">") < 2:
        errs.append("Output Trace: too short (need >= 2 \">\" segments): \"%s\"" % ol[:50])

if errs:
    sys.stdout.write("fail\t" + " | ".join(errs))
else:
    sys.stdout.write("ok")
' 2>/dev/null)

STATUS="${VERDICT%%	*}"
MESSAGE="${VERDICT#*	}"

case "$STATUS" in
  ok|"") exit 0 ;;
esac

# ── Profile gate (mirror depth-marker-pretool.sh + PR #72) ──
# Only the `company` profile force-redos. individual / project / unknown WARN
# (classify + audit-log, no decision:block) — consistent with every other Stop
# and PreToolUse layer, which already warn for non-company. Without this, this
# hook would be the lone Stop layer still forcing redos on individual/project
# sessions. Profile token is sanitized to [a-zA-Z0-9_-] (PR #72 review) so a
# crafted value cannot forge the audit JSON row. Fail-open: no config / no jq ->
# default `individual` -> warn.
CONFIG="$REPO_ROOT/.claude/sutra-project.json"
PROFILE="individual"
if [ -f "$CONFIG" ]; then
  if command -v jq >/dev/null 2>&1; then
    _PROFILE_READ=$(jq -r '.profile // empty' "$CONFIG" 2>/dev/null)
  else
    _PROFILE_READ=$(sed -n 's/.*"profile"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG" | head -1)
  fi
  _PROFILE_READ=$(printf '%s' "$_PROFILE_READ" | tr -cd 'a-zA-Z0-9_-')
  [ -n "$_PROFILE_READ" ] && PROFILE="$_PROFILE_READ"
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
MSG_ESC=$(printf '%s' "$MESSAGE" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g' | head -c 500)

if [ "$PROFILE" != "company" ]; then
  # WARN-only: classification + audit still run; no forced redo.
  printf '{"ts":"%s","session_id":"%s","violation":"perturn_block_text_invalid","layer":"perturn-text","profile":"%s","detail":"%s","action":"warn_no_redo"}\n' \
    "$NOW" "$SESSION_ID" "$PROFILE" "$MSG_ESC" >> "$AUDIT" 2>/dev/null
  echo "perturn-text-validate (warn, profile=$PROFILE): malformed governance block(s) -> $MESSAGE" >&2
  exit 0
fi

# ── company profile: HARD block with ONE consolidated repair message ──
printf '{"ts":"%s","session_id":"%s","violation":"perturn_block_text_invalid","layer":"perturn-text","profile":"%s","detail":"%s","action":"stop_blocked_force_redo"}\n' \
  "$NOW" "$SESSION_ID" "$PROFILE" "$MSG_ESC" >> "$AUDIT" 2>/dev/null

cat <<JSON
{
  "decision": "block",
  "reason": "PER-TURN BLOCK TEXT validation FIRED — the governance blocks the USER sees are malformed (not the marker files).\n\nProblems: ${MSG_ESC}\n\nRe-emit this turn with each block well-formed:\n  Input Routing — INPUT / TYPE (one of: ${TYPE_ENUM}) / ROUTE (+ EXISTING HOME / FIT CHECK / ACTION on full turns)\n  Depth — TASK / DEPTH: N (1-5) / EFFORT / COST / IMPACT\n  Output Trace — an 'OS:' line with at least two '>' segments.\n\nOverride: PERTURN_TEXT_ACK=1 PERTURN_TEXT_ACK_REASON='<why>'. Kill: PERTURN_TEXT_VALIDATE_DISABLED=1."
}
JSON
exit 0
