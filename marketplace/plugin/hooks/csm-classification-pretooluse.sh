#!/usr/bin/env bash
# csm-classification-pretooluse.sh — CSM TODO #5 (D43) at-creation enforcement.
#
# Fires on PreToolUse Edit/Write/MultiEdit of plugin source files
# (sutra/marketplace/plugin/{skills,hooks,commands,bin}/**). For NEW files
# (not yet on disk), warns if the cap-### record isn't yet in CAPABILITY-MAP.md.
#
# Asawa-only (file gate); silent skip outside Asawa repo.
# Soft-warn, never hard-blocks — codex 2026-05-04 ADVISORY: at-creation
# enforcement should not break dev velocity during stabilization. Hard-block
# variant gated to --strict mode of csm-registry-diff-gate.sh.
#
# Override: CSM_CLASSIFICATION_ACK=1 CSM_CLASSIFICATION_ACK_REASON='<why>'
# Kill-switch: CSM_CLASSIFICATION_DISABLED=1 OR ~/.csm-classification-disabled
#
# Build-layer: L1 single-instance:asawa. Promote-to plugin/hooks/ by 2026-06-01
# (with T4-mode silent gate, parallel to csm-sessionstart-banner pattern).

set -u   # not -e: soft-fail, never block tool calls

[ "${CSM_CLASSIFICATION_DISABLED:-0}" = "1" ] && exit 0
[ -f "$HOME/.csm-classification-disabled" ] && exit 0

PROJ="${CLAUDE_PROJECT_DIR:-$PWD}"
CSM="$PROJ/holding/CAPABILITY-MAP.md"

# Asawa-mode gate
[ -f "$CSM" ] || exit 0

# Read PreToolUse payload from stdin (Claude Code passes tool_input as JSON)
PAYLOAD="$(cat 2>/dev/null || echo '{}')"

# Extract file_path
FILE_PATH=$(echo "$PAYLOAD" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)
[ -z "$FILE_PATH" ] && exit 0

# Only fire on plugin source paths.
# Codex 2026-05-04 P1 fix: path matcher must accept BOTH absolute (/abs/path/...) AND
# relative (sutra/marketplace/plugin/...) forms. Prior `*/sutra/...` pattern bypassed
# relative paths because it required at least one prefix char before the `/`.
case "$FILE_PATH" in
  *sutra/marketplace/plugin/skills/*|*sutra/marketplace/plugin/hooks/*|*sutra/marketplace/plugin/commands/*|*sutra/marketplace/plugin/bin/*) ;;
  *) exit 0 ;;
esac

# Only fire for NEW files (not yet on disk)
[ -e "$FILE_PATH" ] && exit 0

# Extract a probable identifier from the path (last path segment without extension)
SURFACE=$(basename "$FILE_PATH" | sed 's/\.[^.]*$//')

# Honor override
if [ "${CSM_CLASSIFICATION_ACK:-0}" = "1" ]; then
  REASON="${CSM_CLASSIFICATION_ACK_REASON:-(no reason)}"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) CSM_CLASSIFICATION_ACK actor=${USER:-unknown} surface=$SURFACE reason=$REASON" >> "$PROJ/.enforcement/csm-classification-overrides.log"
  exit 0
fi

# Check if surface name appears anywhere in CAPABILITY-MAP.md (loose match — soft warn)
if ! grep -qiE "$SURFACE" "$CSM" 2>/dev/null; then
  echo "[CSM·D43] WARN: new plugin surface \"$SURFACE\" ($FILE_PATH)" >&2
  echo "[CSM·D43] No matching cap-### record found in holding/CAPABILITY-MAP.md." >&2
  echo "[CSM·D43] Add a cap-### entry before/after this commit, or set:" >&2
  echo "[CSM·D43]   CSM_CLASSIFICATION_ACK=1 CSM_CLASSIFICATION_ACK_REASON='<why>'" >&2
  echo "[CSM·D43] Soft-warn only — proceeding. Hard-block in --strict mode of csm-registry-diff-gate.sh after 2026-05-15." >&2
fi

exit 0
