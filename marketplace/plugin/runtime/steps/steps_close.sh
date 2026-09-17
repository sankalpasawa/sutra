#!/usr/bin/env bash
# steps_close.sh - native:steps_close, pipeline id stop.steps_close, Stop,
# phase "post" (Sutra Runtime, adherence row 1).
#
# Closes the turn's step ledger: recomputes every step's status one last
# time, records whether the model pasted the STEP TRACE into its reply
# (trace_pasted, never blocking - codex P2-2 / DeepSeek P2-5 fold), and
# writes the closed{} summary the next turn's trace reports as "Last turn".
#
# CONTRACT (D-A9): flag off -> nothing. Never emits stdout. Always exits 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/steps_close.sh

trap 'exit 0' EXIT

main() {
  set +u
  _cl_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_cl_root" ] || return 0
  for _f in hooks/marker-lib.sh runtime/ledger.sh runtime/flags.sh runtime/lib/artifact.sh runtime/lib/steps.sh; do
    [ -f "$_cl_root/$_f" ] && . "$_cl_root/$_f"
  done
  set -u
  command -v sutra_flag_adherence >/dev/null 2>&1 || return 0
  command -v sutra_steps_compute >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  sutra_flag_adherence
  [ "$SUTRA_ADHERENCE_MODE" = "off" ] && return 0

  _CL_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _CL_EVENT="${SUTRA_EVENT:-Stop}"
  _CL_STEP="${SUTRA_STEP_ID:-stop.steps_close}"
  _CL_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"; case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true
  _CL_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_CL_SID" ] || return 0
  [ "$_CL_TURN" != "unknown" ] || return 0
  _CL_PATH="$(sutra_steps_path "$_CL_PROJ" "$_CL_SID" "$_CL_TURN")"
  [ -f "$_CL_PATH" ] || { _cl_row close '{"result":"no-ledger"}'; return 0; }
  OPENED="$(jq -r '.opened_ts // 0' "$_CL_PATH" 2>/dev/null)"; case "$OPENED" in ''|*[!0-9]*) OPENED=0 ;; esac

  # The reply text: stdin first, transcript tail as the fallback (same as
  # markers_diff.sh).
  RESPONSE_TEXT="$(printf '%s' "$STDIN_RAW" | jq -r '.last_assistant_message // empty' 2>/dev/null)"
  if [ -z "$RESPONSE_TEXT" ]; then
    _tp="$(printf '%s' "$STDIN_RAW" | jq -r '.transcript_path // empty' 2>/dev/null)"
    if [ -n "$_tp" ] && [ -f "$_tp" ]; then
      RESPONSE_TEXT="$(tail -c 262144 "$_tp" 2>/dev/null | jq -R -s -r '
        split("\n") | map(select(length>0)) | map(try fromjson catch empty)
        | map(select(.type=="assistant"))
        | if length == 0 then "" else
            (last | (.message.content // []) | map(select(.type=="text") | .text) | join("\n"))
          end' 2>/dev/null)"
    fi
  fi
  PASTED=false
  _t8="$(printf '%s' "$_CL_TURN" | head -c 8)"
  printf '%s' "$RESPONSE_TEXT" | grep -qF "STEP TRACE turn $_t8" && PASTED=true

  STEPS_JSON="$(sutra_steps_compute "$_CL_PROJ" "$_CL_SID" "$_CL_TURN" "$OPENED")"
  [ -n "$STEPS_JSON" ] || return 0
  STEPS_JSON="$(printf '%s' "$STEPS_JSON" | jq -c 'map(if .id == "close" then .status = "done" | .detail = "closed at Stop" else . end)' 2>/dev/null)"

  _upd="$(jq -c --argjson steps "$STEPS_JSON" --argjson pasted "$PASTED" --arg ts "$NOW_TS" '
    .steps = $steps
    | .closed = {
        ts: ($ts|tonumber),
        done: ([.steps[] | select(.status == "done" or .status == "open")] | length),
        pending: ([.steps[] | select(.status == "pending" or .status == "missing")] | length),
        refused: ([.mutations[] | select(.decision == "deny")] | length),
        warned: ([.mutations[] | select(.decision == "warn")] | length),
        trace_pasted: $pasted }' "$_CL_PATH" 2>/dev/null)"
  [ -n "$_upd" ] || return 0
  sutra_steps_write "$_CL_PATH" "$_upd"
  _cl_row close "$(printf '%s' "$_upd" | jq -c '.closed' 2>/dev/null)"
  return 0
}

_cl_row() {  # <kind-suffix> <extra-json-object>
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  _r="$(jq -nc --arg ev "${_CL_EVENT:-Stop}" --arg t "${_CL_TURN:-unknown}" --arg s "${_CL_STEP:-stop.steps_close}" \
        --arg ts "${NOW_TS:-0}" --arg k "steps_$1" --argjson x "$2" \
    '{kind:$k, event:$ev, turn_id:$t, step_id:$s, ts:$ts} + ($x | if has("ts") then .record_ts = .ts | del(.ts) else . end)' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$_r"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$_r"
}

main "$@" || true
exit 0
