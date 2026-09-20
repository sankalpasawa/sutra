#!/usr/bin/env bash
# blueprint_progress.sh - native:blueprint_progress, pipeline id
# post.blueprint_progress, PostToolUse, phase "post" (Sutra Runtime, adherence
# row 6.2, 2026-09-20).
#
# Founder (2026-09-17): "it should also print when each of the steps is done";
# (2026-09-20): "Can you print whether it ran those internal steps as well?"
# The 11 ledger steps already print on every flip (adherence_gate.sh). This
# step does the same for the BLUEPRINT'S OWN steps: after every tool call it
# runs the verify command of each step not yet passed (kind cmd, in the
# project dir, 1.5 s each, 3 s per call in total), records the result in
# <turn>.progress.json, and prints one systemMessage line the moment a step
# flips to done:
#
#   [sutra <t8>] blueprint step 2/3 done: implement SlidingWindowLimiter ...
#
# Truth stays with the Stop lane: <turn>.verifies.json (sealed, 120 s budget)
# is the record; progress.json is a live hint and never marks a step done
# in the ledger's 11 rows. A command that does not finish in 1.5 s is marked
# "slow" once and left to the Stop lane; a kind:manual verify is "manual".
#
# Surface (DeepSeek 2.286.1 P2-5): the Stop lane runs each verify once per
# turn; this step runs the NOT-YET-PASSED ones after every tool call, so a
# model-written command can execute many times per turn instead of once. No
# new command is ever run (only the blueprint's own verifies, the same text
# the Stop lane runs), each run is capped at 1.5 s, and the allowlisted
# runners of CODIFICATION-COMPLETION-PLAN section 1 narrow what both lanes
# will run. Elapsed time of every run counts against the 3 s call budget
# (P1-1); a timed-out command's children are killed with it (P1-3).
#
# CONTRACT (D-A9): flag off -> nothing. Emits at most one JSON object on
# stdout ({systemMessage}). Always exits 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/blueprint_progress.sh

trap 'exit 0' EXIT

main() {
  set +u
  _bp_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_bp_root" ] || return 0
  for _f in hooks/marker-lib.sh runtime/ledger.sh runtime/flags.sh runtime/lib/artifact.sh runtime/lib/steps.sh; do
    [ -f "$_bp_root/$_f" ] && . "$_bp_root/$_f"
  done
  set -u
  command -v sutra_flag_adherence >/dev/null 2>&1 || return 0
  command -v sutra_steps_path >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  sutra_flag_adherence
  [ "$SUTRA_ADHERENCE_MODE" = "off" ] && return 0

  _BP_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _BP_EVENT="${SUTRA_EVENT:-PostToolUse}"
  _BP_STEP="${SUTRA_STEP_ID:-post.blueprint_progress}"
  _BP_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"; case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true
  _BP_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_BP_SID" ] || return 0
  [ "$_BP_TURN" != "unknown" ] || return 0
  _BP_LEDGER="$(sutra_steps_path "$_BP_PROJ" "$_BP_SID" "$_BP_TURN")"
  [ -f "$_BP_LEDGER" ] || return 0
  _BP_FILE="$(sutra_artifact_path "$_BP_PROJ" "$_BP_SID" "$_BP_TURN" blueprint)"
  [ -f "$_BP_FILE" ] || return 0
  jq -e '.steps | type == "array" and length > 0' "$_BP_FILE" >/dev/null 2>&1 || return 0
  # a blueprint older than this ledger's open belongs to an earlier turn of the same id
  OPENED="$(jq -r '.opened_ts // 0' "$_BP_LEDGER" 2>/dev/null)"; case "$OPENED" in ''|*[!0-9]*) OPENED=0 ;; esac
  _bp_ts="$(jq -r '.ts // 0' "$_BP_FILE" 2>/dev/null)"; case "$_bp_ts" in ''|*[!0-9]*) _bp_ts=0 ;; esac
  [ "$_bp_ts" -ge "$OPENED" ] || return 0

  PROG="$(sutra_artifact_path "$_BP_PROJ" "$_BP_SID" "$_BP_TURN" progress)"
  N_TOTAL="$(jq -r '.steps | length' "$_BP_FILE" 2>/dev/null)"; case "$N_TOTAL" in ''|*[!0-9]*) N_TOTAL=0 ;; esac
  [ "$N_TOTAL" -gt 0 ] || return 0
  # a blueprint rewritten since the last look (hash) restarts the progress file
  BP_HASH="$(cksum "$_BP_FILE" 2>/dev/null | awk '{print $1}')"
  if [ -f "$PROG" ] && [ "$(jq -r '.blueprint_cksum // ""' "$PROG" 2>/dev/null)" = "$BP_HASH" ]; then
    PREV="$(cat "$PROG" 2>/dev/null)"
  else
    PREV="$(jq -nc --arg t "$_BP_TURN" --arg s "$_BP_SID" --arg h "$BP_HASH" --argjson n "$N_TOTAL" --argjson ts "$NOW_TS" \
      '{turn_id:$t, session_id:$s, blueprint_cksum:$h, total:$n, done:0, steps:[range(1;$n+1) | {n:., status:"pending", attempts:0, last_exit:null, ts:null}], ts:$ts}' 2>/dev/null)"
  fi
  [ -n "$PREV" ] || return 0

  # run every step not yet done/slow/manual, 1.5 s each, 3 s per call (tenths
  # of a second; the step's pipeline budget is 4500 ms inside the host's 15 s)
  TRANS=""; BUDGET=30; SPENT=0; NEW="$PREV"
  _t8="$(printf '%s' "$_BP_TURN" | head -c 8)"
  _i=1
  while [ "$_i" -le "$N_TOTAL" ]; do
    _st="$(printf '%s' "$NEW" | jq -r --argjson i "$_i" '.steps[] | select(.n == $i) | .status' 2>/dev/null)"
    _kind="$(jq -r --argjson i "$_i" '.steps[$i-1].verify.kind // "manual"' "$_BP_FILE" 2>/dev/null)"
    _cmd="$(jq -r --argjson i "$_i" '.steps[$i-1].verify.cmd // ""' "$_BP_FILE" 2>/dev/null)"
    # the do text is printed: ASCII printable only, so no escape sequence rides in (P2-2)
    _do="$(jq -r --argjson i "$_i" '.steps[$i-1].do // ""' "$_BP_FILE" 2>/dev/null | tr '\n\r\t' '   ' | LC_ALL=C tr -cd ' -~' | head -c 60)"
    _next="$_st"; _rc=""
    if [ "$_st" = "pending" ]; then
      if [ "$_kind" != "cmd" ] || [ -z "$_cmd" ]; then
        _next="manual"
      elif [ "$SPENT" -lt "$BUDGET" ]; then
        _res="$(_bp_run "$_BP_PROJ" "$_cmd" 15)"
        _rc="${_res%% *}"; _el="${_res##* }"
        case "$_el" in ''|*[!0-9]*) _el=15 ;; esac
        SPENT=$((SPENT + _el))            # every run counts, pass or fail (P1-1)
        case "$_rc" in
          0) _next="done" ;;
          124) _next="slow" ;;
          *) _next="pending" ;;
        esac
      fi
    fi
    if [ -n "$_rc" ] || [ "$_next" != "$_st" ]; then
      NEW="$(printf '%s' "$NEW" | jq -c --argjson i "$_i" --arg s "$_next" --argjson ts "$NOW_TS" --arg rc "$_rc" \
        '.steps = (.steps | map(if .n == $i then .status = $s
             | (if $rc != "" then .attempts = ((.attempts // 0) + 1) | .last_exit = ($rc | tonumber) else . end)
             | (if $s != "pending" then .ts = $ts else . end) else . end))' 2>/dev/null)"
    fi
    if [ "$_next" != "$_st" ]; then
      case "$_next" in
        done)   _line="blueprint step $_i/$N_TOTAL done: $_do" ;;
        slow)   _line="blueprint step $_i/$N_TOTAL slow (checked at Stop): $_do" ;;
        manual) _line="blueprint step $_i/$N_TOTAL manual (never done by the runtime): $_do" ;;
        *)      _line="" ;;
      esac
      if [ -n "$_line" ]; then
        [ -n "$TRANS" ] && TRANS="$TRANS  |  "
        TRANS="$TRANS$_line"
        _bp_row step "$(jq -nc --argjson n "$_i" --arg s "$_next" --arg c "$_cmd" '{n:$n, status:$s, cmd:$c}')"
      fi
    fi
    _i=$((_i + 1))
  done
  NEW="$(printf '%s' "$NEW" | jq -c --argjson ts "$NOW_TS" '.done = ([.steps[] | select(.status == "done")] | length) | .ts = $ts' 2>/dev/null)"
  [ -n "$NEW" ] && sutra_steps_write "$PROG" "$NEW"
  [ -n "$TRANS" ] && jq -nc --arg m "[sutra $_t8] $TRANS" '{systemMessage:$m}' 2>/dev/null
  return 0
}

# _bp_run <proj> <cmd> <tenths> -> prints "<exit> <elapsed-tenths>"; exit 124
# on timeout, with the command's children killed before the shell (P1-3).
# The command is the model's own verify (allowlist and hash-freeze arrive with
# CODIFICATION-COMPLETION-PLAN section 1); it already runs at Stop with a
# 120 s budget, this is the same command with a 1.5 s one.
_bp_run() {
  ( cd "$1" 2>/dev/null || { echo "127 0"; exit 0; }
    sh -c "$2" >/dev/null 2>&1 & _p=$!
    _j=0; while kill -0 "$_p" 2>/dev/null && [ "$_j" -lt "$3" ]; do sleep 0.1; _j=$((_j + 1)); done
    if kill -0 "$_p" 2>/dev/null; then
      pkill -P "$_p" 2>/dev/null; kill "$_p" 2>/dev/null; wait "$_p" 2>/dev/null
      echo "124 $_j"; exit 0
    fi
    wait "$_p"; _r=$?
    echo "$_r $_j"; exit 0 )
}

_bp_row() {  # <kind-suffix> <extra-json-object>
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  _r="$(jq -nc --arg ev "${_BP_EVENT:-PostToolUse}" --arg t "${_BP_TURN:-unknown}" --arg s "${_BP_STEP:-post.blueprint_progress}" \
        --arg ts "${NOW_TS:-0}" --arg k "blueprint_$1" --argjson x "$2" \
    '{kind:$k, event:$ev, turn_id:$t, step_id:$s, ts:$ts} + $x' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$_r"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$_r"
}

main "$@" || true
exit 0
