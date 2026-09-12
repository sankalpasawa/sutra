#!/bin/bash
# creation-guard.sh — D74 complete creation + closed vocabulary (Directory Program phase G, 2026-09-11)
# Event: PreToolUse on Edit|Write for a path that does not exist yet (a creation).
# Also callable as: creation-guard.sh --check <repo-relative-path>   (used by creation-stop-check.sh)
#
# For every NEW path it answers four questions and reports what is missing:
#   domain    — is there a department that owns this path? (placement marker DOMAIN_REF, or a CHARTER.md /
#               README.md declaring a department up the tree, or a rule in .claude/creation-guard-rules.json)
#   charter   — is there a charter it answers to? (placement marker CHARTER_ID, or a CHARTER.md up the tree,
#               or the new file IS a CHARTER.md)
#   placement — has this turn been placed? (.claude/sessions/<sid>/placement-registered with a DOMAIN_REF)
#   kind      — does the artifact fit a known kind? If not: NEW KIND event -> NEW-THING-PROTOCOL section 2a
#
# Mode: <repo>/.claude/creation-guard-mode = hard | warn. Default WARN (report, exit 0). hard: exit 2 when a
# dimension is missing or the kind is new. Kill-switch: ~/.creation-guard-disabled (founder revoke only; every
# skip is audit-logged). Fail-open on tooling errors (no jq -> sed; no git -> whitelist only).
set -u
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SID="${CLAUDE_CODE_SESSION_ID:-}"
LOG="$ROOT/.sutra/creation-guard.jsonl"; [ -d "$ROOT/holding/hooks" ] && LOG="$ROOT/holding/hooks/hook-log.jsonl"
MODE=warn; [ -r "$ROOT/.claude/creation-guard-mode" ] && MODE=$(tr -d '[:space:]' < "$ROOT/.claude/creation-guard-mode"); case "$MODE" in hard|warn) ;; *) MODE=warn;; esac
now(){ date +%s; }
jesc(){ printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\n\r'; }
logrow(){ mkdir -p "$(dirname "$LOG")" 2>/dev/null; printf '{"hook":"creation-guard","ts":%s,"session":"%s","path":"%s","result":"%s","missing":"%s","kind":"%s","mode":"%s"}\n' "$(now)" "$(jesc "$SID")" "$(jesc "$1")" "$2" "$3" "$4" "$MODE" >> "$LOG" 2>/dev/null || true; }
CHECK_ONLY=0; FILE_PATH=""
if [ "${1:-}" = "--check" ]; then CHECK_ONLY=1; FILE_PATH="$ROOT/${2:?path}"; else
  if [ ! -t 0 ]; then J=$(cat); if command -v jq >/dev/null 2>&1; then FILE_PATH=$(printf '%s' "$J" | jq -r '.tool_input.file_path // empty' 2>/dev/null); else FILE_PATH=$(printf '%s' "$J" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1); fi; fi
fi
[ -z "$FILE_PATH" ] && exit 0
case "$FILE_PATH" in /*) ;; *) FILE_PATH="$ROOT/$FILE_PATH";; esac
[ "$CHECK_ONLY" = 0 ] && [ -e "$FILE_PATH" ] && exit 0
case "$FILE_PATH" in "$ROOT"/*) REL="${FILE_PATH#$ROOT/}";; *) exit 0;; esac
case "$REL" in .claude/*|.tmp/*|.enforcement/*|.analytics/*|.sutra/*|holding/state/*|holding/checkpoints/*|node_modules/*|.git/*|*.lock|*/__pycache__/*) exit 0;; esac
if [ -f "$HOME/.creation-guard-disabled" ]; then logrow "$REL" "skipped-kill-switch" "" "" ; exit 0; fi
MISSING=""
PM="$ROOT/.claude/sessions/$SID/placement-registered"; DREF=""; CID=""
if [ -n "$SID" ] && [ -r "$PM" ]; then DREF=$(sed -n 's/^DOMAIN_REF=//p' "$PM" | head -1); CID=$(sed -n 's/^CHARTER_ID=//p' "$PM" | head -1); fi
case "$DREF" in ""|unresolved) MISSING="$MISSING placement";; esac
d=$(dirname "$REL"); DOM_HIT=""; CH_HIT=""
while :; do
  [ -f "$ROOT/$d/CHARTER.md" ] && { CH_HIT="$d/CHARTER.md"; DOM_HIT="${DOM_HIT:-$d}"; }
  [ -z "$DOM_HIT" ] && [ -f "$ROOT/$d/README.md" ] && grep -qiE '^# .*department|^\*\*Owning question\*\*|^\*\*Department\*\*' "$ROOT/$d/README.md" 2>/dev/null && DOM_HIT="$d"
  [ "$d" = "." ] && break; d=$(dirname "$d")
done
if [ -z "$DOM_HIT" ] && [ -r "$ROOT/.claude/creation-guard-rules.json" ]; then
  if command -v jq >/dev/null 2>&1; then
    DOM_HIT=$(jq -r --arg p "$REL" '.rules[]? | .prefix as $pre | select($p | startswith($pre)) | .domain' "$ROOT/.claude/creation-guard-rules.json" 2>/dev/null | head -1)
  else
    while IFS='|' read -r pre dom; do case "$REL" in "$pre"*) DOM_HIT="$dom"; break;; esac; done < <(tr -d '\n' < "$ROOT/.claude/creation-guard-rules.json" | grep -o '"prefix"[[:space:]]*:[[:space:]]*"[^"]*"[^}]*"domain"[[:space:]]*:[[:space:]]*"[^"]*"' | sed -E 's/"prefix"[[:space:]]*:[[:space:]]*"([^"]*)".*"domain"[[:space:]]*:[[:space:]]*"([^"]*)"/\1|\2/')
  fi
fi
case "$DREF" in ""|unresolved) ;; *) DOM_HIT="${DOM_HIT:-placement:$DREF}";; esac
[ -z "$DOM_HIT" ] && MISSING="$MISSING domain"
# A rules row may carry the charter too (2.265.6): a routine's output folder (a scheduled audit, an eval run) has no
# session placement and no CHARTER.md up its tree, so the rule declares which charter its files answer to.
if [ -z "$CH_HIT" ] && [ -r "$ROOT/.claude/creation-guard-rules.json" ]; then
  CH_RULE=""
  if command -v jq >/dev/null 2>&1; then
    CH_RULE=$(jq -r --arg p "$REL" '.rules[]? | .prefix as $pre | select($p | startswith($pre)) | .charter // empty' "$ROOT/.claude/creation-guard-rules.json" 2>/dev/null | head -1)
  else
    while IFS='|' read -r pre ch; do case "$REL" in "$pre"*) CH_RULE="$ch"; break;; esac; done < <(tr -d '\n' < "$ROOT/.claude/creation-guard-rules.json" | grep -o '"prefix" *: *"[^"]*"[^}]*"charter" *: *"[^"]*"' | sed -E 's/.*"prefix" *: *"([^"]*)".*"charter" *: *"([^"]*)".*/\1|\2/')
  fi
  [ -n "$CH_RULE" ] && CH_HIT="rule:$CH_RULE"
fi
case "$(basename "$REL")" in CHARTER.md) CH_HIT="${CH_HIT:-self}";; esac
[ -z "$CH_HIT" ] && [ -n "$CID" ] && CH_HIT="placement:$CID"
[ -z "$CH_HIT" ] && MISSING="$MISSING charter"
b=$(basename "$REL"); KIND=""
case "$REL" in
  */runs/*.json|*/runs/*.jsonl|*/triage-runs/*.log) KIND=ledger;;
  */hooks/*.sh) KIND=hook;; */bin/*|*/scripts/*) KIND=cli;; */tests/*|*test_*|*-test.sh|*.test.*) KIND=test;; */decisions/ADR-*|ADR-*|*/ADR-*) KIND=adr;;
  */os/engines/*.md|*/engines/*.md) KIND=engine;; */plans/*.md) KIND=plan;; */PROTOCOLS.md|*PROTO-[0-9]*) KIND=protocol;; */FOUNDER-DIRECTIONS.md|FOUNDER-DIRECTIONS.md) KIND=direction;;
  */os/charters/*.md) KIND=charter;; */sutra-ui/static/*|*/sutra-ui/*.html|*/electron/*) KIND=app;;
esac
if [ -z "$KIND" ]; then case "$b" in
  SKILL.md) KIND=skill;; CHARTER.md) KIND=charter;; *.md|*.txt|*.rst|*.pdf) KIND=doc;; *.py|*.ts|*.js|*.mjs|*.tsx|*.swift|*.css|*.sh|*.gs) KIND=code;;
  *.sql) KIND=sql;; *.json|*.yaml|*.yml|*.toml|*.plist) KIND=policy;; *.jsonl|*.log|*.csv|*.eval) KIND=ledger;; *.html) KIND=page;; *) KIND="";; esac; fi
if [ -z "$KIND" ]; then
  MSG="NEW KIND DETECTED: '$REL' fits none of the artifact kinds (app, page, cli, code, sql, engine, hook, skill, policy, ledger, test, doc, plan, adr, charter, protocol, direction).
  This is an event for the founder, not a silent addition (D74). Route: holding/NEW-THING-PROTOCOL.md section 2a FIT CHECK.
  Say what it is, why it fits nothing, and wait for the ruling before creating it."
  logrow "$REL" "new-kind" "$MISSING" "none"
  if [ "$MODE" = hard ]; then echo "CREATION GUARD (HARD): $MSG" >&2; exit 2; else echo "CREATION GUARD (WARN, new kind): $MSG" >&2; exit 0; fi
fi
if [ -n "$MISSING" ]; then
  MSG="new $KIND '$REL' is missing:$MISSING
  Complete creation (D74): a new thing brings its domain, charter and placement with it.
    domain    -> is there a department dir with CHARTER.md/README.md above it, or a rule in .claude/creation-guard-rules.json?
    charter   -> which charter does it answer to (placement marker CHARTER_ID or a CHARTER.md up the tree)?
    placement -> emit the PLACEMENT line and write .claude/sessions/<sid>/placement-registered first.
  Mode file: .claude/creation-guard-mode (hard|warn). Kill-switch: touch ~/.creation-guard-disabled (founder revoke only, audited)."
  logrow "$REL" "missing" "$MISSING" "$KIND"
  if [ "$MODE" = hard ]; then echo "CREATION GUARD (HARD): $MSG" >&2; exit 2; else echo "CREATION GUARD (WARN): $MSG" >&2; fi
else
  logrow "$REL" "complete" "" "$KIND"
fi
[ "$CHECK_ONLY" = 0 ] && [ -n "$SID" ] && { mkdir -p "$ROOT/.claude/sessions/$SID" 2>/dev/null; echo "$REL" >> "$ROOT/.claude/sessions/$SID/creation-guard-seen" 2>/dev/null; }
exit 0
