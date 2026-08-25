#!/usr/bin/env bash
# md-standard-gate.sh — PostToolUse Edit|Write gate for the LLM-first markdown standard
# Standard of record: plugin skill writing-llm-md (skills/writing-llm-md/SKILL.md), v1.1.
# Promoted from asawa-holding L1 2026-08-25 (W1 parity; original codex-consulted 2026-08-05).
# Policy: HARD (exit 2) only for NEW (untracked) .md in enforced paths; tracked files get
# an advisory warning. Evaluates ONLY the single changed path handed to the hook.
set -uo pipefail

STD_VERSION="1.1"
[ -f "$HOME/.md-standard-disabled" ] && exit 0
[ "${MD_STANDARD_ACK:-}" = "1" ] && exit 0

INPUT=$(cat 2>/dev/null || true)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0
case "$FILE" in *.md) ;; *) exit 0 ;; esac
# Canonicalize (macOS: /var vs /private/var symlink would dodge the repo-prefix check)
FDIR=$(cd "$(dirname "$FILE")" 2>/dev/null && pwd -P) && FILE="$FDIR/$(basename "$FILE")"

REPO=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
case "$FILE" in "$REPO"/*) ;; *) exit 0 ;; esac
REL=${FILE#"$REPO"/}

# Exempt doc classes with their own schemas + noise/telemetry paths (generalized fleet-wide)
case "$REL" in
  TODO.md|*/TODO.md|*/checkpoints/*|.obsidian/*|*/archive/*|*/website/*) exit 0 ;;
  .claude/*|.enforcement/*|.tmp/*|.context/*|node_modules/*|*/node_modules/*) exit 0 ;;
  README.md|*/README.md|CLAUDE.md|*/CLAUDE.md|MEMORY.md|CHANGELOG.md|*/CHANGELOG.md) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

NEW=0
git -C "$REPO" ls-files --error-unmatch "$REL" >/dev/null 2>&1 || NEW=1

VIOL=()
head -15 "$FILE" | grep -qE '\*\*(status|updated)\*\*|^---$' || VIOL+=("META missing metadata block (R1)")
tail -12 "$FILE" | grep -q 'provenance:' || VIOL+=("PROV missing provenance footer (R10)")
ART=$(awk 'BEGIN{f=0} /^[[:space:]]*```/{f=!f; next} f==0 && /\+[-=]{6,}\+/{n++} END{print n+0}' "$FILE")
[ "${ART:-0}" -ge 2 ] && VIOL+=("ART ASCII box art (R4) — use mermaid + edge-list twin")

[ ${#VIOL[@]} -eq 0 ] && exit 0

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SEV=advisory; [ "$NEW" = "1" ] && SEV=hard
RULES=$(IFS=';'; printf '%s' "${VIOL[*]}" | tr '"' "'")
mkdir -p "$REPO/.enforcement" 2>/dev/null || true
printf '{"hook":"md-standard-gate","std":"%s","path":"%s","new":%s,"severity":"%s","rules":"%s","ts":"%s"}\n' \
  "$STD_VERSION" "$REL" "$NEW" "$SEV" "$RULES" "$TS" >> "$REPO/.enforcement/md-standard.jsonl" 2>/dev/null || true

if [ "$NEW" = "1" ]; then
  {
    echo "BLOCKED — md-standard-gate (writing-llm-md v$STD_VERSION): NEW .md violates the LLM-first standard:"
    for v in "${VIOL[@]}"; do echo "  - $v"; done
    echo "  Standard: Sutra plugin skill writing-llm-md (invoke it, fix the sections, rewrite)."
    echo "  Override: MD_STANDARD_ACK=1 (Bash-attached) or touch ~/.md-standard-disabled"
  } >&2
  exit 2
fi

echo "md-standard-gate (advisory, ratchet window): $REL — ${VIOL[*]} — standard: plugin skill writing-llm-md" >&2
exit 0
