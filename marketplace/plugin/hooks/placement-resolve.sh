#!/bin/bash
# placement-resolve.sh -- computes THIS turn's address and hands the model the
# exact line to emit (ADR-028, the last mile).
#
# Event: UserPromptSubmit
#
# WHY THIS EXISTS: without it, the model composes the PLACEMENT line from
# imagination every turn. The block looks identical either way, which is what
# makes the failure so easy to miss — a mandatory governance block whose content
# means nothing. This hook runs the real engine and injects the real answer, so
# the model transcribes rather than invents.
#
# READ-ONLY BY DESIGN. At prompt time the only evidence is the utterance. Minting
# a Domain from an utterance alone would create one per novel phrasing and shred
# the tree within a day. So this classifies against the EXISTING tree only; when
# nothing matches it says so plainly and leaves minting to the moment work
# actually touches paths.
#
# Fail-open on every infrastructure error: a governance helper must never block
# a user's prompt because python was missing or the registry was unreadable.

set -u

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_ROOT" ] && exit 0

[ -n "${PLACEMENT_DISABLED:-}" ] && exit 0
[ -f "$REPO_ROOT/.claude/placement-disabled" ] && exit 0
[ -f "$HOME/.placement-disabled" ] && exit 0

PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ENGINE="$PLUGIN_DIR/lib/placement_engine.py"
RENDER="$PLUGIN_DIR/lib/placement-render.sh"
[ -f "$ENGINE" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

PAYLOAD=$(cat 2>/dev/null || true)
PROMPT=$(printf '%s' "$PAYLOAD" | jq -r '.prompt // empty' 2>/dev/null)
[ -z "$PROMPT" ] && exit 0                       # synthetic turn — not real work

# Skip synthetic/system turns (same list the marker reset guards on)
case "$PROMPT" in
  *"<system-reminder>"*|*"<local-command-caveat>"*|*"hook additional context"*) exit 0 ;;
esac

UTT=$(printf '%s' "$PROMPT" | head -c 600 | tr -d '\000')

RESULT=$(cd "$REPO_ROOT" && PLACEMENT_TENANT="${PLACEMENT_TENANT:-T-local}" \
         python3 "$ENGINE" classify "$UTT" 2>/dev/null)
[ -z "$RESULT" ] && exit 0

RESOLVED=$(printf '%s' "$RESULT" | jq -r '.resolved // false' 2>/dev/null)

if [ "$RESOLVED" = "true" ]; then
  LINE=$(printf '%s' "$RESULT" | bash "$RENDER" 2>/dev/null | head -1)
  CONF=$(printf '%s' "$RESULT" | jq -r '.confidence' 2>/dev/null)
  REF=$(printf '%s' "$RESULT" | jq -r '.domain_ref' 2>/dev/null)
  CID=$(printf '%s' "$RESULT" | jq -r '.charter.id // ""' 2>/dev/null)
  # Grounding mandate (founder 2026-07-30): the resolved domain's charter rides
  # into every turn so the work is framed by — and answerable to — the charter
  # it runs under, not just tagged with an address.
  CTITLE=$(printf '%s' "$RESULT" | jq -r '.charter.title // ""' 2>/dev/null)
  CPROMISE=$(printf '%s' "$RESULT" | jq -r '.charter.promise // ""' 2>/dev/null | head -c 300)
  GROUND=""
  if [ -n "$CTITLE" ]; then
    GROUND=$(printf '\nGROUNDING — this turn runs under Charter "%s": %s\nFrame the work by this charter; cite the domain in recommendations; if the\nwork contradicts the charter'"'"'s purpose, say so rather than proceeding silently.\n' \
             "$CTITLE" "$CPROMISE")
  fi
  BODY=$(printf 'The placement engine resolved THIS turn to a real address.\nEmit this line VERBATIM as your PLACEMENT block — do not compose your own:\n\n  %s\n\n  (domain_ref=%s confidence=%s — engine output, read-only match, nothing minted)\n%s' \
         "$LINE" "$REF" "$CONF" "$GROUND")
  mkdir -p "$REPO_ROOT/.claude" 2>/dev/null
  printf 'DOMAIN_REF=%s\nCHARTER_ID=%s\nORIGIN=matched\nCONFIDENCE=%s\nSOURCE=engine\nTS=%s\n' \
    "$REF" "$CID" "$CONF" "$(date +%s)" > "$REPO_ROOT/.claude/placement-registered" 2>/dev/null
else
  REASON=$(printf '%s' "$RESULT" | jq -r '.reason // "unknown"' 2>/dev/null)
  BODY=$(printf 'The placement engine could NOT resolve this turn to an existing domain (reason: %s).\nSay so plainly in your PLACEMENT block rather than inventing a path, e.g.:\n\n  PLACEMENT: unresolved (%s) — address assigned when this work touches files\n\nDo NOT fabricate a D-path. An honest "unresolved" is correct; an invented\naddress is the exact failure this feature exists to remove.\n' \
         "$REASON" "$REASON")
  # I-P3 (codex F7.1, 2026-07-30): an unresolved DECLARATION is still a
  # declaration. Without this marker, hard mode turns "engine could not match
  # the utterance" into a blocked Edit — never-blocks violated by the hook
  # layer while the engine honoured it. Unresolved is recorded, work proceeds,
  # and the real address lands when the work touches actual paths.
  mkdir -p "$REPO_ROOT/.claude" 2>/dev/null
  printf 'DOMAIN_REF=unresolved\nCHARTER_ID=unresolved\nORIGIN=unresolved\nREASON=%s\nCONFIDENCE=0.0\nSOURCE=engine\nTS=%s\n' \
    "$REASON" "$(date +%s)" > "$REPO_ROOT/.claude/placement-registered" 2>/dev/null
fi

jq -nc --arg c "$(printf '\n[Placement · ADR-028]\n%s\n' "$BODY")" \
  '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$c}}' 2>/dev/null
exit 0
