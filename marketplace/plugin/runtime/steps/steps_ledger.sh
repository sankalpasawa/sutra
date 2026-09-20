#!/usr/bin/env bash
# steps_ledger.sh - native:steps_ledger, pipeline id ups.steps_ledger, phase
# "post", registered AFTER ups.markers_write (Sutra Runtime, adherence row 1).
#
# Opens the turn's step ledger at .sutra/turn/<sid>/<turn>.steps.json from
# the facts file, the session markers, the artifacts, the atom ledger and the
# tests marker, and emits ONE additionalContext object carrying the STEP
# TRACE - the visible log of which step ran (founder direction 2026-09-16).
#
# CONTRACT (brief D-A1, D-A9): flag off -> nothing on stdout, no rows, no
# file. Flag on|warn -> one JSON object on stdout, ledger rows, the file.
# Always exits 0. bash 3.2.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/steps_ledger.sh

trap 'exit 0' EXIT

main() {
  set +u
  _sl_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_sl_root" ] || return 0
  for _f in hooks/marker-lib.sh runtime/ledger.sh runtime/flags.sh runtime/lib/prompt.sh runtime/lib/artifact.sh runtime/lib/steps.sh; do
    [ -f "$_sl_root/$_f" ] && . "$_sl_root/$_f"
  done
  set -u
  command -v sutra_flag_adherence >/dev/null 2>&1 || return 0
  command -v sutra_steps_compute >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  sutra_flag_adherence
  [ "$SUTRA_ADHERENCE_MODE" = "off" ] && return 0

  _SL_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _SL_EVENT="${SUTRA_EVENT:-UserPromptSubmit}"
  _SL_STEP="${SUTRA_STEP_ID:-ups.steps_ledger}"
  _SL_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"; case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true
  PROMPT="$(printf '%s' "$STDIN_RAW" | jq -r '.prompt // empty' 2>/dev/null)"
  command -v sutra_prompt_synthetic >/dev/null 2>&1 || return 0
  if sutra_prompt_synthetic "$PROMPT"; then
    _sl_row skip '{"reason":"synthetic"}'
    return 0
  fi
  _SL_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_SL_SID" ] || { _sl_row skip '{"reason":"no-session"}'; return 0; }
  [ "$_SL_TURN" != "unknown" ] || { _sl_row skip '{"reason":"no-turn"}'; return 0; }

  _sl_dir="$_SL_PROJ/.sutra/turn/$_SL_SID"
  mkdir -p "$_sl_dir" 2>/dev/null
  _SL_PATH="$(sutra_steps_path "$_SL_PROJ" "$_SL_SID" "$_SL_TURN")"

  # sutra-turn hashes the turn id from sid + prompt text, so a repeated prompt
  # ("continue", "go") REUSES the id. Two cases (workflow review P1, 2026-09-17):
  #   ledger exists, closed == null -> a mid-turn re-run: keep opened_ts, merge
  #   ledger exists, closed != null -> a NEW occurrence: rotate the old ledger
  #     and artifacts aside, open fresh, so lens/cynefin must be re-authored
  OPENED="$NOW_TS"
  if [ -f "$_SL_PATH" ]; then
    if [ "$(jq -r 'if .closed == null then "open" else "closed" end' "$_SL_PATH" 2>/dev/null)" = "closed" ]; then
      _rot="$(jq -r '.closed.ts // 0' "$_SL_PATH" 2>/dev/null)"; case "$_rot" in ''|*[!0-9]*) _rot=0 ;; esac
      mv -f "$_SL_PATH" "$_sl_dir/$_SL_TURN.steps.prev$_rot.json" 2>/dev/null
      for _k in lens cynefin tests review; do
        _ap="$_sl_dir/$_SL_TURN.$_k.json"
        [ -f "$_ap" ] && mv -f "$_ap" "$_sl_dir/$_SL_TURN.$_k.prev$_rot.json" 2>/dev/null
      done
      for _lf in "$_sl_dir/lane-logs/$_SL_TURN".*; do
        [ -e "$_lf" ] || continue
        case "$_lf" in *.prev*) continue ;; esac
        mv -f "$_lf" "$_lf.prev$_rot" 2>/dev/null
      done
      _sl_row rotate "$(jq -nc --arg t "$_rot" '{reason:"repeated-prompt-after-close", prev_closed_ts:$t}')"
    else
      _prev="$(jq -r '.opened_ts // empty' "$_SL_PATH" 2>/dev/null)"
      case "$_prev" in ''|*[!0-9]*) ;; *) OPENED="$_prev" ;; esac
    fi
  fi

  UNIT="$(printf '%s' "$PROMPT" | tr '\n\r\t' '   ' | LC_ALL=C tr -cd ' -~' | head -c 80)"
  STEPS_JSON="$(sutra_steps_compute "$_SL_PROJ" "$_SL_SID" "$_SL_TURN" "$OPENED")"
  [ -n "$STEPS_JSON" ] || return 0

  # Previous turn's summary (the newest OTHER ledger in this session).
  LAST=""
  _last_file="$(ls -t "$_sl_dir"/*.steps.json 2>/dev/null | grep -v "/$_SL_TURN.steps.json" | head -1)"
  if [ -n "$_last_file" ]; then
    LAST="$(jq -r 'if .closed != null then "Last turn: \(.closed.done)/11 done, refused \(.closed.refused), trace_pasted=\(.closed.trace_pasted), fills_left=\(.closed.fills_left // 0)" else "Last turn: not closed" end' "$_last_file" 2>/dev/null)"
    # Row 2: the runtime lanes finish after that turn's Stop; read their files now.
    _prev_turn="$(basename "$_last_file" .steps.json)"
    # Row 6: the blueprint's verify commands ran at that Stop (sealed file only)
    if [ -f "$_sl_dir/$_prev_turn.verifies.json" ]; then
      if command -v sutra_seal_verify >/dev/null 2>&1 && sutra_seal_verify "$_sl_dir/$_prev_turn.verifies.json"; then
        LAST="$LAST, verifies=$(jq -r '"\(.passed // 0) pass/\(.failed // 0) fail/\(.skipped // 0) manual"' "$_sl_dir/$_prev_turn.verifies.json" 2>/dev/null)"
      else
        LAST="$LAST, verifies=$(jq -r '.status // "?"' "$_sl_dir/$_prev_turn.verifies.json" 2>/dev/null) (unsealed)"
      fi
    fi
    if [ -f "$_sl_dir/$_prev_turn.review.json" ]; then
      LAST="$LAST, review=$(jq -r '"\(.status)\(if .verdict != null then ":" + .verdict else "" end)"' "$_sl_dir/$_prev_turn.review.json" 2>/dev/null)"
    fi
    if [ -f "$_sl_dir/$_prev_turn.tests.json" ]; then
      LAST="$LAST, tests=$(jq -r '"\(.status)\(if .exit != null then " exit=" + (.exit|tostring) else "" end)"' "$_sl_dir/$_prev_turn.tests.json" 2>/dev/null)"
    fi
  fi

  # A re-run of the same turn MERGES: mutations and closed{} already recorded
  # survive, only mode and the step rows refresh (DeepSeek round-2 P1-5).
  LEDGER=""
  if [ -f "$_SL_PATH" ]; then
    LEDGER="$(jq -c --arg mode "$SUTRA_ADHERENCE_MODE" --argjson steps "$STEPS_JSON" \
      '.mode = $mode | .steps = $steps | .mutations = (.mutations // []) ' "$_SL_PATH" 2>/dev/null)"
  fi
  if [ -n "$LEDGER" ]; then
    sutra_steps_write "$_SL_PATH" "$LEDGER"
  else
    # Row 2 baseline for the turn's diff (a stash commit of the worktree as it
    # is NOW, or HEAD) and the fresh file: the shared open (2.286.3), the same
    # one the gate uses when this step was killed at the prompt.
    sutra_steps_open_ledger "$_SL_PROJ" "$_SL_SID" "$_SL_TURN" "$SUTRA_ADHERENCE_MODE" "$OPENED" "$UNIT" || return 0
  fi

  DONE_N="$(printf '%s' "$STEPS_JSON" | jq -r '[.[] | select(.status == "done" or .status == "open")] | length' 2>/dev/null)"
  _sl_row open "$(jq -nc --arg d "${DONE_N:-0}" --arg p "$_SL_PATH" '{done:($d|tonumber), path:$p}')"

  TRACE="$(sutra_steps_render "$_SL_PATH")"
  LENS_REL="$(sutra_artifact_rel "$_SL_SID" "$_SL_TURN" lens)"
  CYN_REL="$(sutra_artifact_rel "$_SL_SID" "$_SL_TURN" cynefin)"
  VERB_MODE="Refused"; [ "$SUTRA_ADHERENCE_MODE" = "warn" ] && VERB_MODE="Warned (not refused)"
  # Rows 3 + 5 (2026-09-17): the rendered block stack from facts, and the two
  # judgment prompts for whichever of lens / cynefin is still pending.
  STACK="$(sutra_steps_render_stack "$_SL_PROJ/.sutra/turn/$_SL_SID/$_SL_TURN.facts.json" "$_SL_PROJ/.claude/sessions/$_SL_SID/placement-registered")"
  LENS_ST="$(printf '%s' "$STEPS_JSON" | jq -r '.[] | select(.id == "lens") | .status' 2>/dev/null)"
  CYN_ST="$(printf '%s' "$STEPS_JSON" | jq -r '.[] | select(.id == "cynefin") | .status' 2>/dev/null)"
  BP_ST="$(printf '%s' "$STEPS_JSON" | jq -r '.[] | select(.id == "blueprint") | .status' 2>/dev/null)"
  BP_REL="$(sutra_artifact_rel "$_SL_SID" "$_SL_TURN" blueprint)"
  PROMPTS="$(sutra_steps_prompts "${LENS_ST:-pending}" "${CYN_ST:-pending}" "${BP_ST:-pending}")"
  TAIL="$VERB_MODE until 5, 6 and 7 exist for this turn (mode=$SUTRA_ADHERENCE_MODE; rules R1-R9 in runtime/rules/gates.json). Write them with the Write tool, turn_id=$_SL_TURN session_id=$_SL_SID ts>=$OPENED:
  $LENS_REL  {turn_id,session_id,producer:\"model\",step:\"lens\",unit(>=10 chars),axes:[>=1 strings],pick:[subset of axes],direction:DOWN|UP|ACROSS,ts}
  $CYN_REL  {turn_id,session_id,producer:\"model\",step:\"cynefin\",unit,domain:clear|complicated|complex|chaotic,shape(>=20 chars),human_gate:bool,ts}
  $BP_REL  {turn_id,session_id,producer:\"model\",step:\"blueprint\",unit,doing,steps:[{do,verify:{kind:cmd|manual,cmd}}],output,verified_by:{kind,cmd},stops_if,ts} (verify cmd = a shell check the runtime runs at Stop; at depth 3+ every step needs one)
A new path with no placement match also needs TURN.placement.json; a holding-side implementation path needs TURN.build_layer.json; a governance path at depth 3+ needs a sealed review verdict.
Paste the STEP TRACE block above verbatim into your reply, after the Depth block. Table on demand: bin/sutra-steps latest."
  [ -n "$LAST" ] && TAIL="$TAIL
$LAST"

  CTX="$STACK

$TRACE
$TAIL"
  [ -n "$PROMPTS" ] && CTX="$CTX

$PROMPTS"
  # Budget (pipeline.json budgets.context.render_chars_max, default 7000):
  # drop order prompts, then stack, never the trace.
  _budget="$(jq -r '.budgets.context.render_chars_max // 7000' "$_sl_root/runtime/pipeline.json" 2>/dev/null)"; case "$_budget" in ''|*[!0-9]*) _budget=7000 ;; esac
  if [ "${#CTX}" -gt "$_budget" ]; then
    _sl_row drop '{"dropped":"prompts"}'
    CTX="$STACK

$TRACE
$TAIL"
  fi
  if [ "${#CTX}" -gt "$_budget" ]; then
    _sl_row drop '{"dropped":"stack"}'
    CTX="$TRACE
$TAIL"
  fi
  jq -nc --arg ev "$_SL_EVENT" --arg ctx "$CTX" '{hookSpecificOutput:{hookEventName:$ev, additionalContext:$ctx}}' 2>/dev/null
  return 0
}

_sl_row() {  # <kind-suffix> <extra-json-object>
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  _r="$(jq -nc --arg ev "${_SL_EVENT:-UserPromptSubmit}" --arg t "${_SL_TURN:-unknown}" --arg s "${_SL_STEP:-ups.steps_ledger}" \
        --arg ts "${NOW_TS:-0}" --arg k "steps_$1" --argjson x "$2" \
    '{kind:$k, event:$ev, turn_id:$t, step_id:$s, ts:$ts} + $x' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$_r"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$_r"
}

main "$@" || true
exit 0
