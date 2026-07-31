#!/usr/bin/env bash
# PreToolUse hook: blocks Write/Edit until input has been classified.
# Fires on: Write, Edit
# 2026-07-30 (marker-race fix, root-cause doc §2 input-routed row): reads the
# PreToolUse stdin JSON for tool_name / file_path / session_id — the argv form
# is kept as a fallback for legacy invocations. Previously this gate was
# argv-only and structurally could not see a session id; the marker read is now
# routed through marker-lib (session dir .claude/sessions/<sid>/input-routed,
# with self-only adoption of an unstamped or self-stamped legacy global).

TOOL_NAME="${1:-}"
FILE_PATH="${2:-}"

PAYLOAD=""
[ ! -t 0 ] && PAYLOAD="$(cat 2>/dev/null)"
if [ -n "$PAYLOAD" ] && command -v jq >/dev/null 2>&1; then
  [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null)
  [ -z "$FILE_PATH" ] && FILE_PATH=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
fi

# Only gate Write and Edit
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# Repo-boundary guard (2026-07-31; mirrors the codex-consult-gate v2.58.1
# memory-scope carve-out, generalized): a file_path OUTSIDE the project dir
# (e.g. ~/.claude/** memory files, session state, cross-repo notes) can never
# match a repo whitelist and is not this repo's turn discipline to gate.
# In-repo paths and empty/unresolvable paths still fall through to the gate.
if [[ -n "$FILE_PATH" && "$FILE_PATH" != "$REPO_ROOT"/* ]]; then
  exit 0
fi

# Governance-marker self-whitelist (2026-07-31): a gate must never block the
# Write of the very marker that satisfies it. The 2026-07-31 double-brick
# incidents: this gate blocked the Write tool's write of
# .claude/sessions/<sid>/input-routed (and depth-registered) -- the exact
# marker whose absence caused the block -- an unrecoverable loop unless the
# model fell back to Bash printf. Session-dir marker paths and the legacy
# global marker twins exit 0 here.
case "$FILE_PATH" in
  */.claude/sessions/*) exit 0 ;;
  */.claude/*-registered|*/.claude/input-routed) exit 0 ;;
esac

# Whitelist: system-maintenance paths skip classification
if echo "$FILE_PATH" | grep -qE '(memory/|checkpoints/|\.lock|TODO\.md)'; then
  exit 0
fi

# Check for classification marker (per-turn; wiped by reset-turn-markers.sh on
# UserPromptSubmit). Convention aligned with .claude/depth-registered and
# .claude/blueprint-registered. Prior path /tmp/asawa-input-classified-${SID}
# was broken — no writer existed in any skill or hook (2026-05-10 root-cause fix
# during SOFT-to-HARD blanket flip; founder direction Option A).
# (REPO_ROOT resolved above, at the repo-boundary guard.)
MARKER="$REPO_ROOT/.claude/input-routed"

# Session-scoped marker read via marker-lib (defensive sourcing, flow-gate.sh
# pattern): a foreign-stamped legacy global can no longer satisfy this gate.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  . "$_MARKER_LIB" 2>/dev/null || true
  command -v sutra_sid_from_stdin >/dev/null 2>&1 && { sutra_sid_from_stdin "$PAYLOAD" || true; }
fi

if command -v sutra_marker_read >/dev/null 2>&1; then
  sutra_marker_read input-routed >/dev/null 2>&1 && exit 0
elif [[ -f "$MARKER" ]]; then
  # lib missing: legacy global (fail-open on infrastructure, not on discipline)
  exit 0
fi

# Override path (honor-system; audit-logged)
if [[ "${INPUT_ROUTING_ACK:-0}" == "1" ]]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  REASON=$(printf '%s' "${INPUT_ROUTING_ACK_REASON:-no-reason}" | tr -d '"\\' | tr '\n\r' '  ')
  printf '{"ts":%s,"event":"input-routing-override","reason":"%s"}\n' "$(date +%s)" "$REASON" \
    >> "$REPO_ROOT/.enforcement/input-routing-overrides.jsonl"
  exit 0
fi

cat >&2 <<EOF
BLOCKED: emit Input Routing block before Edit/Write (CLAUDE.md Mandatory Blocks).
Required: INPUT / TYPE / EXISTING HOME / ROUTE / FIT CHECK / ACTION lines.
Then write marker via Bash (Write tool is itself blocked by this hook):
  printf "TS=%s TASK=<slug>\n" "\$(date +%s)" > .claude/input-routed
Override (one call): INPUT_ROUTING_ACK=1 INPUT_ROUTING_ACK_REASON='<why>' <tool>
EOF
exit 2

# ============================================================================
# ## Operationalization
# (Auto-appended on D38 wave-6 plugin promotion — lightweight default; replace
# with concrete metrics when this hook gets attention.)
#
# ### 1. Measurement mechanism
# Hook events emit to .enforcement/build-layer-ledger.jsonl or hook-specific
# log when relevant; no dedicated metric until usage observed.
# ### 2. Adoption mechanism
# Activated via plugin distribution from sutra/marketplace/plugin/hooks/.
# ### 3. Monitoring / escalation
# Surface error/anomaly rate to Asawa CEO weekly until baseline established.
# ### 4. Iteration trigger
# Tighten or loosen after 14 days of fleet observation.
# ### 5. DRI
# Asawa CEO (Sutra Forge per D31).
# ### 6. Decommission criteria
# Retire when capability supersedes via newer hook or absorbed into a
# composite gate. Currently no decommission planned.
# ============================================================================
