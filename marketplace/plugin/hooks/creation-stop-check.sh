#!/bin/bash
# creation-stop-check.sh — Stop-time floor for D74 complete creation (Directory Program phase G).
# Finds files created this session that the PreToolUse guard never saw (Bash, subagents, scripts) and runs the
# same four-dimension check on each. hard mode: exit 2 (the turn cannot end with an unaddressed creation).
# warn mode: prints the list. The subagent brief creation-check-brief.md tells the model what to do with it.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; SID="${CLAUDE_CODE_SESSION_ID:-}"
MODE=warn; [ -r "$ROOT/.claude/creation-guard-mode" ] && MODE=$(tr -d '[:space:]' < "$ROOT/.claude/creation-guard-mode"); case "$MODE" in hard|warn) ;; *) MODE=warn;; esac
LOG="$ROOT/.sutra/creation-guard.jsonl"; [ -d "$ROOT/holding/hooks" ] && LOG="$ROOT/holding/hooks/hook-log.jsonl"
if [ -f "$HOME/.creation-guard-disabled" ]; then mkdir -p "$(dirname "$LOG")" 2>/dev/null; printf '{"hook":"creation-stop-check","ts":%s,"session":"%s","result":"skipped-kill-switch","mode":"%s"}\n' "$(date +%s)" "$SID" "$MODE" >> "$LOG" 2>/dev/null; exit 0; fi
GIT=git; command -v $GIT >/dev/null 2>&1 || exit 0
SEEN="$ROOT/.claude/sessions/$SID/creation-guard-seen"
NEW=$(cd "$ROOT" && $GIT status --porcelain --untracked-files=all 2>/dev/null | sed -n -e 's/^?? //p' -e 's/^A  //p' -e 's/^AM //p')
# session baseline: only files touched since this session's dir was created count as this session's creations
SDIR="$ROOT/.claude/sessions/$SID"; START=0
if [ -d "$SDIR" ]; then START=$(stat -f %B "$SDIR" 2>/dev/null || stat -c %Y "$SDIR" 2>/dev/null || echo 0); fi
mt(){ stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0; }
[ -z "$NEW" ] && exit 0
BAD=""; N=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  case "$p" in .claude/*|.tmp/*|.enforcement/*|.analytics/*|.sutra/*|holding/state/*|holding/checkpoints/*|node_modules/*|*.lock|*/__pycache__/*) continue;; esac
  case "$p" in */) continue;; esac
  if [ -r "$SEEN" ] && grep -qxF "$p" "$SEEN" 2>/dev/null; then continue; fi
  [ "$START" -gt 0 ] && [ "$(mt "$ROOT/$p")" -lt "$START" ] && continue   # pre-existing untracked file, not this session's creation
  OUT=$("$(dirname "$0")/creation-guard.sh" --check "$p" 2>&1 >/dev/null); rc=$?
  if [ $rc -ne 0 ] || printf '%s' "$OUT" | grep -q 'missing:\|NEW KIND'; then N=$((N+1)); BAD="$BAD
  - $p :: $(printf '%s' "$OUT" | head -1 | cut -c1-160)"; fi
done <<< "$NEW"
[ $N -eq 0 ] && exit 0
MSG="CREATION CHECK: $N file(s) created this turn outside the PreToolUse guard (Bash, subagent or script) and missing a dimension:$BAD
  Every creation brings its domain, charter, placement and artifact kind (D74). Fix the missing dimension or route a NEW KIND to holding/NEW-THING-PROTOCOL.md section 2a.
  Brief for the checking subagent: hooks/creation-check-brief.md. Mode file: .claude/creation-guard-mode (hard|warn)."
if [ "$MODE" = hard ]; then echo "$MSG" >&2; exit 2; else echo "$MSG (WARN)" >&2; exit 0; fi
