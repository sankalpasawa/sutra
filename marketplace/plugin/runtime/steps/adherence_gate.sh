#!/usr/bin/env bash
# adherence_gate.sh - native:adherence_gate, pipeline id pre.adherence_gate,
# PreToolUse, phase "post", class B (Sutra Runtime, adherence row 1).
#
# For every tool call: class it (mutation | exempt | read), re-check the
# turn's lens and cynefin artifacts, update the step ledger, and - on a
# mutation with a missing or invalid artifact - emit permissionDecision deny
# (mode on) or a systemMessage (mode warn). The reason names the step, the
# exact artifact path and the schema, so the model can satisfy it in one
# Write. The artifact write itself is exempt (D-A4/D-A6): the gate can never
# refuse the write that would satisfy it.
#
# CONTRACT (D-A9): flag off -> nothing on stdout, no rows, no file changes.
# Missing ledger (UPS step timed out) -> allow + bootstrap row, never refuse
# (codex P2-4). Orphan turn -> allow + row (D-A5). Always exits 0. bash 3.2.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/adherence_gate.sh

trap 'exit 0' EXIT

main() {
  set +u
  _ag_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_ag_root" ] || return 0
  for _f in hooks/marker-lib.sh runtime/ledger.sh runtime/flags.sh runtime/lib/artifact.sh runtime/lib/steps.sh; do
    [ -f "$_ag_root/$_f" ] && . "$_ag_root/$_f"
  done
  set -u
  command -v sutra_flag_adherence >/dev/null 2>&1 || return 0
  command -v sutra_steps_compute >/dev/null 2>&1 || return 0
  command -v sutra_artifact_check >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  sutra_flag_adherence
  [ "$SUTRA_ADHERENCE_MODE" = "off" ] && return 0

  _AG_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _AG_EVENT="${SUTRA_EVENT:-PreToolUse}"
  _AG_STEP="${SUTRA_STEP_ID:-pre.adherence_gate}"
  _AG_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"; case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true
  _AG_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_AG_SID" ] || return 0
  TOOL="$(printf '%s' "$STDIN_RAW" | jq -r '.tool_name // empty' 2>/dev/null)"
  FILE_PATH="$(printf '%s' "$STDIN_RAW" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)"
  COMMAND="$(printf '%s' "$STDIN_RAW" | jq -r '.tool_input.command // empty' 2>/dev/null)"

  if [ "$_AG_TURN" = "unknown" ]; then
    _ag_row decision '{"decision":"allow","reason":"orphan-turn"}'
    return 0
  fi
  _AG_PATH="$(sutra_steps_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN")"
  if [ ! -f "$_AG_PATH" ]; then
    _ag_row decision '{"decision":"allow","reason":"bootstrap-no-ledger"}'
    return 0
  fi
  OPENED="$(jq -r '.opened_ts // 0' "$_AG_PATH" 2>/dev/null)"; case "$OPENED" in ''|*[!0-9]*) OPENED=0 ;; esac

  # -- class the call -------------------------------------------------------
  KIND=read; TARGET=""
  case "$TOOL" in
    Edit|Write|MultiEdit|NotebookEdit)
      TARGET="$FILE_PATH"; KIND=mutation
      sutra_steps_exempt_path "$FILE_PATH" "$_AG_SID" && KIND=exempt ;;
    Bash)
      # ASCII-only, so a 120-byte cut can never split a multibyte char into
      # invalid UTF-8 for jq (DeepSeek round-2 P1-8).
      TARGET="$(printf '%s' "$COMMAND" | tr '\n\r\t' '   ' | LC_ALL=C tr -cd ' -~' | head -c 120)"
      if sutra_steps_exempt_bash "$COMMAND" "$_AG_SID"; then KIND=exempt
      elif sutra_steps_bash_mutation "$COMMAND"; then KIND=mutation
      else KIND=read; fi ;;
    Task|Agent)
      TARGET="$(printf '%s' "$STDIN_RAW" | jq -r '.tool_input.description // .tool_input.subagent_type // "subagent"' 2>/dev/null | head -c 80)"
      KIND=mutation ;;
    *) KIND=read ;;
  esac

  # -- re-check the two artifacts; refresh the ledger's step rows ----------
  STEPS_JSON="$(sutra_steps_compute "$_AG_PROJ" "$_AG_SID" "$_AG_TURN" "$OPENED")"
  if [ -n "$STEPS_JSON" ]; then
    _upd="$(jq -c --argjson steps "$STEPS_JSON" '.steps = $steps' "$_AG_PATH" 2>/dev/null)"
    [ -n "$_upd" ] && sutra_steps_write "$_AG_PATH" "$_upd"
  fi

  if [ "$KIND" != "mutation" ]; then
    [ "$KIND" = "exempt" ] && _ag_mutation "$TOOL" "$TARGET" exempt '[]'
    return 0
  fi

  MISSING=""; REASONS=""
  for _k in lens cynefin; do
    _r="$(sutra_artifact_check "$(sutra_artifact_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN" "$_k")" "$_k" "$_AG_TURN" "$_AG_SID" "$OPENED")"
    if [ "$_r" != "ok" ]; then
      MISSING="$MISSING $_k"
      REASONS="$REASONS
  $_k: $(sutra_artifact_rel "$_AG_SID" "$_AG_TURN" "$_k") ($_r)"
    fi
  done
  MISSING="$(printf '%s' "$MISSING" | sed 's/^ //')"

  if [ -z "$MISSING" ]; then
    _ag_mutation "$TOOL" "$TARGET" allow '[]'
    return 0
  fi

  MISSING_JSON="$(printf '%s' "$MISSING" | tr ' ' '\n' | jq -R . | jq -sc .)"
  REASON="ADHERENCE GATE (row 1, mode $SUTRA_ADHERENCE_MODE): $TOOL on $TARGET needs the turn's judgment artifacts. Missing:$REASONS
Write each with the Write tool, then retry. turn_id=$_AG_TURN session_id=$_AG_SID ts>=$OPENED
  lens    {turn_id,session_id,producer:\"model\",step:\"lens\",unit(>=10 chars),axes:[>=1 strings],pick:[subset of axes],direction:DOWN|UP|ACROSS,ts}
  cynefin {turn_id,session_id,producer:\"model\",step:\"cynefin\",unit,domain:clear|complicated|complex|chaotic,shape(>=20 chars),human_gate:bool,ts}
Trace: bin/sutra-steps latest. Kill: rm ~/.sutra-runtime-adherence"

  if [ "$SUTRA_ADHERENCE_MODE" = "on" ]; then
    _ag_mutation "$TOOL" "$TARGET" deny "$MISSING_JSON"
    jq -nc --arg ev "$_AG_EVENT" --arg r "$REASON" \
      '{hookSpecificOutput:{hookEventName:$ev, permissionDecision:"deny", permissionDecisionReason:$r}}' 2>/dev/null
  else
    _ag_mutation "$TOOL" "$TARGET" warn "$MISSING_JSON"
    jq -nc --arg r "$REASON" '{systemMessage:("[warn] " + $r)}' 2>/dev/null
  fi
  return 0
}

# _ag_mutation <tool> <target> <decision> <missing-json-array>: one row in the
# ledger file and one adherence_decision ledger row.
_ag_mutation() {
  _m="$(jq -nc --arg ts "$NOW_TS" --arg tool "$1" --arg target "$2" --arg d "$3" --argjson missing "$4" \
    '{ts:($ts|tonumber), tool:$tool, target:$target, decision:$d, missing:$missing}' 2>/dev/null)"
  [ -n "$_m" ] || return 0
  _upd="$(jq -c --argjson m "$_m" '.mutations += [$m]' "$_AG_PATH" 2>/dev/null)"
  [ -n "$_upd" ] && sutra_steps_write "$_AG_PATH" "$_upd"
  _ag_row decision "$_m"
}

_ag_row() {  # <kind-suffix> <extra-json-object>
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  _r="$(jq -nc --arg ev "${_AG_EVENT:-PreToolUse}" --arg t "${_AG_TURN:-unknown}" --arg s "${_AG_STEP:-pre.adherence_gate}" \
        --arg ts "${NOW_TS:-0}" --arg k "adherence_$1" --argjson x "$2" \
    '{kind:$k, event:$ev, turn_id:$t, step_id:$s, ts:$ts} + ($x | if has("ts") then .record_ts = .ts | del(.ts) else . end)' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$_r"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$_r"
}

main "$@" || true
exit 0
