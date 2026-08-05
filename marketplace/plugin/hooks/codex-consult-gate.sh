#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/codex-consult-gate.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-07-20
#
# codex-consult-gate.sh -- PreToolUse Edit|Write FLOOR for the D40 codex-consult
# policy ("consult before Edit/Write at Depth >= 3"), upgraded from SOFT default
# to HARD per D63 (2026-07-20).
#
# THE DEGRADATION CARVE-OUT (D63, founder-flagged): codex-consult is the ONE
# block that depends on an EXTERNAL binary (the OpenAI Codex CLI) + an API key
# many fleet machines do not have. A naive hard gate ("no Edit at D3+ until you
# run codex") would BRICK Edit for anyone without codex installed. So this gate
# is hard ONLY where it can be satisfied:
#   - codex binary present  -> HARD: require a codex-consult marker OR an ack
#   - codex binary ABSENT   -> DEGRADE: auto-write .claude/codex-unavailable,
#                              log it, and PASS. Never block a codex-less user.
# Net: the gate bites on codex-present machines (Asawa + anyone who installed
# codex) and is a logged no-op elsewhere. That is the honest maximum -- you
# cannot force a consult on a tool the machine lacks.
#
# Satisfy the gate (any one):
#   - .claude/codex-consulted   (written when a codex consult runs this turn)
#   - CODEX_CONSULT_ACK=1 CODEX_CONSULT_ACK_REASON='<why>'   (per-call ack)
#
# Kill-switch (2-level):
#   - CODEX_CONSULT_DISABLED=1         (per-shell env)
#   - $HOME/.codex-consult-disabled    (per-machine fs)
#
# Fires HARD (exit 2) only when ALL of: depth>=3, non-whitelisted path, codex
# present, no consult marker, no ack. Otherwise exit 0. Fail-open on infra.

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
[ -z "$REPO_ROOT" ] && exit 0

# -- Kill-switches ---------------------------------------------------------
[ "${CODEX_CONSULT_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.codex-consult-disabled" ] && exit 0

# -- Fresh-install gate (codex challenge finding (d), 2026-07-20) -----------
# Do not gate edits until the user has run /core:start (writes
# .claude/sutra-project.json + the governance contract). Pre-onboarding, this
# would block a user who never received the policy.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$REPO_ROOT/.claude/sutra-project.json" ]; then
  exit 0
fi

mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
LEDGER="$REPO_ROOT/.enforcement/codex-consult-gate.jsonl"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log_row() {
  local decision="$1" reason="$2"
  reason=$(printf '%s' "$reason" | tr -d '\n' | sed 's/\\/\\\\/g; s/"/\\"/g')
  printf '{"ts":"%s","event":"codex-consult-gate","decision":"%s","reason":"%s"}\n' \
    "$NOW" "$decision" "$reason" >> "$LEDGER" 2>/dev/null
}

# -- Per-call ack ----------------------------------------------------------
if [ "${CODEX_CONSULT_ACK:-0}" = "1" ]; then
  R=$(printf '%s' "${CODEX_CONSULT_ACK_REASON:-no-reason}" | tr -d '\n\r' | head -c 300)
  log_row "ack" "$R"
  exit 0
fi

# -- Parse target path -----------------------------------------------------
PAYLOAD=""
[ ! -t 0 ] && PAYLOAD="$(cat 2>/dev/null || true)"
FILE_PATH=""
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi
[ -z "$FILE_PATH" ] && FILE_PATH="${TOOL_INPUT_file_path:-}"
[ -z "$FILE_PATH" ] && exit 0
REL_PATH="${FILE_PATH#"$REPO_ROOT"/}"

# -- Memory-scope carve-out (2026-07-31; scoped NARROWER than blueprint-check's
# blanket v2.39.20 out-of-repo guard to avoid an edit-outside-then-mv-in
# bypass): ~/.claude/** (memory files, session state) can never match a repo
# whitelist and was blocked by accident. All other out-of-repo paths still gate.
case "$FILE_PATH" in
  "$HOME"/.claude/*) log_row "pass" "memory-scope path=${FILE_PATH}"; exit 0 ;;
esac
# W1-T13 (d12): hook-owned staging only — session scratchpads + peer-review
# temp files. Deliberately NARROW (dual G1 review rejected blanket /tmp), and
# paths containing '..' never take this exit (T13 codex fold: glob match on a
# traversal path can resolve outside staging).
case "$FILE_PATH" in
  *..*) : ;;
  /private/tmp/claude-*/*|/tmp/codex-*|/tmp/deepseek-*)
    log_row "pass" "hook-owned-staging path=${FILE_PATH}"; exit 0 ;;
esac

# -- Session-scoped marker resolution (2026-07-30 marker-race fix) ----------
# Markers are read via marker-lib: session dir .claude/sessions/<sid>/ first,
# with self-only adoption of an unstamped or self-stamped legacy global. A
# foreign-stamped global (a concurrent session's state) is IGNORED — this
# closes the cross-session consult leak where session A's codex-consulted
# satisfied session B's D3+ gate (root-cause doc §2, codex-consulted row).
# Sourced defensively (flow-gate.sh pattern): this script runs under `set -u`;
# a lib error must degrade to the legacy path, never abort the hook.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$PAYLOAD" || true
  set -u
fi
_ccg_marker_read() {
  if command -v sutra_marker_read >/dev/null 2>&1; then
    sutra_marker_read "$1" 2>/dev/null; return $?
  fi
  # lib missing: legacy global (fail-open on infrastructure, not on discipline)
  cat "$REPO_ROOT/.claude/$1" 2>/dev/null
}

# -- Whitelist: docs / ledgers / ephemeral state are not substantive edits --
case "$REL_PATH" in
  .claude/*|.enforcement/*|.analytics/*)            exit 0 ;;
  holding/checkpoints/*|holding/state/*)            exit 0 ;;
  holding/TODO.md|*/TODO.md|*/BACKLOG.md)           exit 0 ;;
  */CHANGELOG.md|*/MEMORY.md|MEMORY.md)             exit 0 ;;
  *.lock|*.log|*.jsonl)                             exit 0 ;;
  *.md.bak|*~)                                      exit 0 ;;
esac

# -- Depth gate: only bite at Depth >= 3 -----------------------------------
DEPTH_CONTENT="$(_ccg_marker_read depth-registered)" || DEPTH_CONTENT=""
DEPTH_N=""
[ -n "$DEPTH_CONTENT" ] && DEPTH_N=$(printf '%s' "$DEPTH_CONTENT" | grep -oE 'DEPTH=[0-9]+' 2>/dev/null | head -1 | cut -d= -f2)
# Unknown/unparseable depth -> do not block (the depth gate owns that failure).
[ -z "$DEPTH_N" ] && exit 0
[ "$DEPTH_N" -lt 3 ] 2>/dev/null && exit 0

# -- Already satisfied this turn? (session-scoped; foreign global ignored) --
_ccg_marker_read codex-consulted >/dev/null 2>&1 && { log_row "pass" "consult-marker-present"; exit 0; }

# -- W1-T13 (d9): persistent consult-ledger fallback ------------------------
# A consult whose completion raced the turn boundary (background run; marker
# wiped by reset-turn-markers) still authorizes ONCE: same session, fresh
# (<1800s), consume-once via the never-wiped consumed ledger. T13 codex folds:
# sid validated before regex use; consumed check is fixed-string (grep -F).
# Known looseness (pinned, single-user CLI): two truly parallel checks could
# both pass before either stamp lands — accepted at G1 scale, flock at W6.
CCG_CONSULTS="$REPO_ROOT/.enforcement/codex-consults.jsonl"
CCG_CONSUMED="$REPO_ROOT/.enforcement/codex-consult-consumed.jsonl"
_CCG_SID="${CLAUDE_CODE_SESSION_ID:-}"
case "$_CCG_SID" in *[!A-Za-z0-9-]*|'') _CCG_SID="" ;; esac
if [ -n "$_CCG_SID" ] && [ -f "$CCG_CONSULTS" ]; then
  _CCG_NOW=$(date +%s)
  _CCG_ROW=$(grep -F "\"sid\":\"$_CCG_SID\"" "$CCG_CONSULTS" 2>/dev/null | tail -1)
  _CCG_RTS=$(printf '%s' "$_CCG_ROW" | grep -oE '"ts":[0-9]+' | head -1 | cut -d: -f2)
  if [ -n "$_CCG_RTS" ] && [ $((_CCG_NOW - _CCG_RTS)) -lt 1800 ] \
     && ! grep -qF "\"sid\":\"$_CCG_SID\",\"ts\":$_CCG_RTS" "$CCG_CONSUMED" 2>/dev/null; then
    printf '{"sid":"%s","ts":%s,"consumed_at":%s}\n' "$_CCG_SID" "$_CCG_RTS" "$_CCG_NOW" >> "$CCG_CONSUMED" 2>/dev/null || true
    log_row "pass" "consult-carryover-consumed ts=$_CCG_RTS"
    exit 0
  fi
fi

# -- Degradation: codex binary absent -> pass (never brick a codex-less box) -
# Re-checked EVERY call (codex challenge P2 "sticky" fix): no persisted
# codex-unavailable marker, so a machine that later installs codex begins
# enforcing immediately, and one that removes it stops -- state tracks reality
# instead of a one-time snapshot.
if ! command -v codex >/dev/null 2>&1; then
  log_row "degrade" "codex-binary-absent"
  exit 0
fi

# -- codex present + D3+ + no consult + not whitelisted -> HARD block -------
log_row "block" "depth${DEPTH_N}-no-consult path=${REL_PATH}"
{
  echo "CODEX-CONSULT GATE (HARD, D63): Depth ${DEPTH_N} Edit/Write requires a codex consult first."
  echo "  File: $REL_PATH"
  echo "  Satisfy it by running a REAL consult -- /core:codex-sutra (consult|challenge|review)."
  echo "  A successful codex run writes .claude/codex-consulted (via codex-consult-marker.sh),"
  echo "  which clears this gate for the rest of the turn. Then re-attempt the Edit/Write."
  echo "  NOTE: CODEX_CONSULT_ACK=1 works only for Bash tool calls -- it CANNOT attach to an"
  echo "  Edit/Write tool call. For Edit/Write, consult for real or use the kill-switch:"
  echo "  Disable: CODEX_CONSULT_DISABLED=1  or  touch ~/.codex-consult-disabled"
} >&2
exit 2
