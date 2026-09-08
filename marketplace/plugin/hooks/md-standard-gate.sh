#!/usr/bin/env bash
# md-standard-gate.sh — PostToolUse Edit|Write gate for the LLM-first markdown rules
# Standard of record: plugin skill core:writing-style, section 7 (skills/writing-style/SKILL.md), v2.0.
# History: writing-llm-md v1.1 (2026-08-05, codex-consulted) -> promoted L0 2026-08-25 -> folded into
# core:writing-style 2026-09-08 (D71). Evaluates ONLY the single changed path handed to the hook.
# Policy: HARD (exit 2) for NEW (untracked) .md in enforced paths on MD-1..MD-5; tracked files get
# an advisory warning, except MD-5 (skills/*/SKILL.md or holding/skills/*.md growing past 250 lines).
# Checks: MD-1 META block | MD-2 PROV footer | MD-3 box art (ASCII or unicode, fence-aware)
#         MD-4 more than one H1 (fence-aware) | MD-5 SKILL.md line cap | MD-A2 untagged fence (advisory)
# Kill: ~/.md-standard-disabled | MD_STANDARD_ACK=1 (Bash-attached). Ledger: .enforcement/md-standard.jsonl
set -uo pipefail

STD_VERSION="2.0"
[ -f "$HOME/.md-standard-disabled" ] && exit 0
[ "${MD_STANDARD_ACK:-}" = "1" ] && exit 0

INPUT=$(cat 2>/dev/null || true)
FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$FILE" ] && exit 0
case "$FILE" in *.md) ;; *) exit 0 ;; esac
# Canonicalize (macOS: /var vs /private/var symlink would dodge the repo-prefix check)
FDIR=$(cd "$(dirname "$FILE")" 2>/dev/null && pwd -P) && FILE="$FDIR/$(basename "$FILE")"

# Resolve the repo that OWNS the file (nearest git toplevel of its directory), not the CWD's
# repo: a file inside a submodule is tracked by the submodule, and the outer repo's ls-files
# would report it as untracked and wrongly promote every edit to HARD (found 2026-09-08).
REPO=$(git -C "$FDIR" rev-parse --show-toplevel 2>/dev/null) || exit 0
case "$FILE" in "$REPO"/*) ;; *) exit 0 ;; esac
REL=${FILE#"$REPO"/}

# Exempt doc classes with their own schemas + noise/telemetry paths (generalized fleet-wide)
case "$REL" in
  TODO.md|*/TODO.md|checkpoints/*|*/checkpoints/*|.obsidian/*|archive/*|*/archive/*|website/*|*/website/*) exit 0 ;;
  .claude/*|.enforcement/*|.tmp/*|.context/*|node_modules/*|*/node_modules/*) exit 0 ;;
  README.md|*/README.md|CLAUDE.md|*/CLAUDE.md|MEMORY.md|CHANGELOG.md|*/CHANGELOG.md) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

NEW=0
git -C "$REPO" ls-files --error-unmatch "$REL" >/dev/null 2>&1 || NEW=1

VIOL=(); ADV=()
# MD-1 / MD-2 (predicates unchanged since v1.1, except: case-insensitive so the ADR shape
# "**Status**: Accepted" counts as metadata — every new ADR was blocked before 2026-09-08)
head -15 "$FILE" | grep -qiE '\*\*(status|updated)\*\*|^---$' || VIOL+=("MD-1 META missing metadata block (R1)")
tail -12 "$FILE" | grep -q 'provenance:' || VIOL+=("MD-2 PROV missing provenance footer (R10)")

# Fence-aware scan in one pass: box art (ASCII +---+ or unicode U+2500-U+259F), H1 count,
# untagged fence openers. Fences: ``` or ~~~ toggle; an opener is tagged when text follows the marks.
# python3 when present (macOS awk cannot match UTF-8 glyph ranges); awk ASCII-only fallback otherwise.
if command -v python3 >/dev/null 2>&1; then
SCAN=$(python3 - "$FILE" <<'PY'
import re, sys
art = h1 = untagged = 0; f = False
for ln in open(sys.argv[1], encoding="utf-8", errors="replace"):
    s = ln.rstrip("\n")
    m = re.match(r"^\s*(\x60{3}|~{3})(.*)$", s)   # \x60 = backtick; literal backticks break bash 3.2 inside $( <<'PY' )
    if m:
        if not f:
            f = True
            if m.group(2).strip() == "": untagged += 1
        else:
            f = False
        continue
    if f: continue
    if re.search(r"\+[-=]{6,}\+", s) or re.search(r"[─-▟]", s): art += 1
    if s.startswith("# "): h1 += 1
print(art, h1, untagged)
PY
)
else
SCAN=$(awk '
  BEGIN { f=0; art=0; h1=0; untagged=0 }
  /^[[:space:]]*(```|~~~)/ {
    if (f==0) { f=1; s=$0; sub(/^[[:space:]]*(```|~~~)/, "", s); if (s ~ /^[[:space:]]*$/) untagged++ }
    else { f=0 }
    next
  }
  f==0 && /\+[-=]{6,}\+/ { art++ }
  f==0 && /^# / { h1++ }
  END { printf "%d %d %d", art, h1, untagged }' "$FILE")
fi
ART=${SCAN%% *}; REST=${SCAN#* }; H1=${REST%% *}; UNTAGGED=${REST#* }
[ "${ART:-0}" -ge 2 ] && VIOL+=("MD-3 ART box art in a file (R4) — fence a template spec or use mermaid + edge list")
[ "${H1:-0}" -gt 1 ] && VIOL+=("MD-4 H1 count $H1 (R5: exactly one H1)")
[ "${H1:-0}" -eq 0 ] && ADV+=("MD-4 no H1 (R5)")
[ "${UNTAGGED:-0}" -ge 1 ] && ADV+=("MD-A2 $UNTAGGED untagged code fence(s) (R12; HARD for new files from 2026-10-08)")

# MD-5 line cap on skill files: new -> hard; tracked -> hard only when growing past the cap
case "$REL" in
  skills/*/SKILL.md|*/skills/*/SKILL.md|holding/skills/*.md|*/holding/skills/*.md)
    LINES=$(wc -l < "$FILE" | tr -d ' ')
    CAP=250
    if [ "$LINES" -gt "$CAP" ]; then
      if [ "$NEW" = "1" ]; then
        VIOL+=("MD-5 $LINES lines > $CAP (M8)")
      else
        OLD=$(git -C "$REPO" show "HEAD:$REL" 2>/dev/null | wc -l | tr -d ' ')
        if [ "${OLD:-0}" -lt "$LINES" ]; then
          VIOL+=("MD-5 $LINES lines > $CAP and grew from $OLD (M8 no-growth ratchet)")
          NEW=1   # promote to hard: the only tracked-file HARD, file class is unambiguous
        fi
      fi
    fi ;;
esac

[ ${#VIOL[@]} -eq 0 ] && [ ${#ADV[@]} -eq 0 ] && exit 0

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SEV=advisory; [ "$NEW" = "1" ] && [ ${#VIOL[@]} -gt 0 ] && SEV=hard
RULES=$(IFS=';'; printf '%s' "${VIOL[*]:-}${ADV[*]:+;${ADV[*]}}" | tr '"' "'")
mkdir -p "$REPO/.enforcement" 2>/dev/null || true
printf '{"hook":"md-standard-gate","std":"%s","path":"%s","new":%s,"severity":"%s","rules":"%s","ts":"%s"}\n' \
  "$STD_VERSION" "$REL" "$NEW" "$SEV" "$RULES" "$TS" >> "$REPO/.enforcement/md-standard.jsonl" 2>/dev/null || true

if [ "$SEV" = "hard" ]; then
  {
    echo "BLOCKED — md-standard-gate (core:writing-style section 7, v$STD_VERSION): NEW .md violates the file rules:"
    for v in "${VIOL[@]}"; do echo "  - $v"; done
    for v in "${ADV[@]:-}"; do [ -n "$v" ] && echo "  - advisory: $v"; done
    echo "  Standard: skills/writing-style/SKILL.md section 7 (R1-R12). Fix the sections, rewrite."
    echo "  Override: MD_STANDARD_ACK=1 (Bash-attached) or touch ~/.md-standard-disabled"
  } >&2
  exit 2
fi

echo "md-standard-gate (advisory): $REL — ${VIOL[*]:-}${ADV[*]:+ ${ADV[*]}} — standard: core:writing-style section 7" >&2
exit 0
