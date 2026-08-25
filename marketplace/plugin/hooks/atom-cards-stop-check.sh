#!/usr/bin/env bash
#
# atom-cards-stop-check.sh — Stop floor: if a Work-Atom TRANSITIONED this turn
# (opened / closed / refused / abandoned), the assistant's final visible response
# text MUST contain the matching atom card label. Founder direction 2026-08-01:
# the cards are shown TO THE USER before and after, as a hard gate — tool-output
# rendering alone does not reach the reading surface.
# Blocks via {"decision":"block"} JSON (flow-stop-check pattern), once per turn
# (stop_hook_active loop guard). FAIL-OPEN on every parse error.
# Codex 2026-08-01: visible-text parser (skip thinking/tool blocks), 1s boundary
# grace, terminal-specific labels, sid-scoped (subagent atoms not parent's duty).
# Test override: ATOM_CARDS_TURN_START=<epoch> replaces input-routed mtime.
# v2 2026-08-07 (finding a7c4rdsfloor, codex consult P1-conditional): v1 grepped
# only the LAST assistant text message, so (a) cards echoed before a later tool
# call were invisible, and (b) under non-flushing harnesses (Fable 5: text
# reaches the transcript only at end of turn) the last text was the PREVIOUS
# turn's -> false block with cards on screen (5 redos 2026-08-04). Now: scan ALL
# this-turn assistant text (entries with no/unparseable timestamp = current,
# fail-open); if NOTHING from this turn has flushed, allow + audit-log
# atom_cards_unverifiable_flush_lag (charter: fail-open when the response is
# unseeable; the old block released on redo anyway, so it was pure tax).
# Visible-but-lacking still blocks. Codex P1 (model-written marker = forgeable
# gate) resolved by having NO marker path; trusted-producer evidence
# (WRITER=sutra-atom + nonce) is the L0-promotion hardening.

set -u

STDIN_JSON=""
[ ! -t 0 ] && STDIN_JSON="$(cat 2>/dev/null || true)"
command -v jq >/dev/null 2>&1 || exit 0
[ -f "$HOME/.atom-floor-disabled" ] && exit 0
[ "${ATOM_FLOOR_DISABLED:-0}" = "1" ] && exit 0

# Loop guard — the redo pass always releases.
[ "$(printf '%s' "$STDIN_JSON" | jq -r '.stop_hook_active // false' 2>/dev/null)" = "true" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
SID="$(printf '%s' "$STDIN_JSON" | jq -r '.session_id // empty' 2>/dev/null)"
[ -z "$SID" ] && SID="${CLAUDE_CODE_SESSION_ID:-}"
[ -z "$SID" ] && exit 0
STATE="$ROOT/.sutra/atoms/$SID"
[ -d "$STATE" ] || exit 0

# Turn start: session-dir mtime (reset-turn-markers wipes it EVERY UserPromptSubmit,
# so it moves on quiet turns too — fixes false blocks when no bash call rewrote
# input-routed); fallback input-routed for migration [codex]. 1s grace. Test override.
TURN_START="${ATOM_CARDS_TURN_START:-}"
if [ -z "$TURN_START" ]; then
  if [ -d "$ROOT/.claude/sessions/$SID" ]; then
    TURN_START=$(stat -f %m "$ROOT/.claude/sessions/$SID" 2>/dev/null || stat -c %Y "$ROOT/.claude/sessions/$SID" 2>/dev/null)
  fi
  if [ -z "$TURN_START" ] && [ -f "$ROOT/.claude/input-routed" ]; then
    TURN_START=$(stat -f %m "$ROOT/.claude/input-routed" 2>/dev/null || stat -c %Y "$ROOT/.claude/input-routed" 2>/dev/null)
  fi
  [ -z "$TURN_START" ] && exit 0
fi
TURN_START=$((TURN_START - 1))

# Which card labels does this turn owe? Literal labels, exactly as the CLI
# renders them: "ATOM OPEN" / "ATOM CLOSED" / "ATOM ABANDONED" / "ATOM REFUSED".
# (sid-scoped; terminal-specific [codex Q3])
NEED=""
for f in "$STATE"/a-*/atom.json; do
  [ -f "$f" ] || continue
  read -r ts_open ts_closed status lr_ts <<EOF2
$(jq -r '[(.ts_open // 0), (.ts_closed // 0), .status, (.verify.last_result.ts // 0)] | @tsv' "$f" 2>/dev/null)
EOF2
  [ -z "${ts_open:-}" ] && continue
  [ "$ts_open" -ge "$TURN_START" ] 2>/dev/null && NEED="$NEED|ATOM OPEN"
  if [ "${ts_closed:-0}" -ge "$TURN_START" ] 2>/dev/null; then
    case "$status" in
      closed)    NEED="$NEED|ATOM CLOSED" ;;
      abandoned) NEED="$NEED|ATOM ABANDONED" ;;
    esac
  fi
  # Verify-failure: verify ran this turn but atom still open.
  if [ "$status" = "open" ] && [ "${lr_ts:-0}" -ge "$TURN_START" ] 2>/dev/null; then
    NEED="$NEED|VERIFY FAILED"
  fi
done
[ -z "$NEED" ] && exit 0

# Visible assistant text from THIS TURN — concatenate ALL text blocks (skip
# thinking/tool) across every this-turn assistant entry [v2]. Entries with no
# or unparseable timestamp count as current (fail-open; real Claude Code
# transcripts always stamp ISO timestamps).
TRANSCRIPT="$(printf '%s' "$STDIN_JSON" | jq -r '.transcript_path // empty' 2>/dev/null)"
[ -f "$TRANSCRIPT" ] || exit 0
TURN_TEXT=$(jq -rs --argjson start "$TURN_START" '
  def fresh: (.timestamp // "") as $t
    | if $t == "" then true
      else (($t | sub("\\.[0-9]+Z$"; "Z") | (try fromdateiso8601 catch null)) as $e
            | if $e == null then true else ($e >= $start) end)
      end;
  [ .[] | select(.type=="assistant") | select(fresh)
    | (.message.content // []) | map(select(.type=="text") | .text) | join("\n")
    | select(length > 0) ] | join("\n")' "$TRANSCRIPT" 2>/dev/null) || exit 0

if [ -z "$TURN_TEXT" ]; then
  ANY_TEXT=$(jq -rs '[ .[] | select(.type=="assistant")
      | (.message.content // []) | map(select(.type=="text") | .text) | join("\n")
      | select(length > 0) ] | last // ""' "$TRANSCRIPT" 2>/dev/null) || exit 0
  [ -z "$ANY_TEXT" ] && exit 0   # fail-open: cannot see any response
  # Non-flushing harness (Fable 5): older turns' text exists but nothing from
  # THIS turn has reached the transcript yet, so the card check is
  # unsatisfiable, not violated. Charter says fail-open when the response is
  # unseeable — and v1's block here released on the redo pass anyway (pure
  # tax). Allow, but audit-log so the fallback rate stays reviewable [codex].
  NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mkdir -p "$ROOT/.enforcement" 2>/dev/null
  printf '{"ts":"%s","event":"atom_cards_unverifiable_flush_lag","session":"%s","labels":"%s","turn_start":%s,"note":"no this-turn assistant text in transcript at Stop; card check unverifiable; allowed per fail-open charter"}\n' \
    "$NOW_ISO" "$SID" "$(printf '%s' "$NEED" | tr '|' ' ')" "$TURN_START" \
    >> "$ROOT/.enforcement/atom-gate.jsonl" 2>/dev/null
  exit 0
fi

MISSING=""
OLD_IFS="$IFS"; IFS='|'
for label in $NEED; do
  [ -z "$label" ] && continue
  printf '%s' "$TURN_TEXT" | grep -qF "$label" || MISSING="$MISSING$label; "
done
IFS="$OLD_IFS"
[ -z "$MISSING" ] && exit 0

jq -n --arg m "$MISSING" \
  '{decision:"block",
    reason:("ATOM CARDS floor: atom(s) transitioned this turn but the response does not show the card(s) to the user: " + $m + "Re-emit the card blocks (verbatim, from the sutra-atom output) in your visible response text, then stop again.")}'
exit 0
