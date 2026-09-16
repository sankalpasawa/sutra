#!/usr/bin/env bash
# markers_diff.sh - native:markers_diff, pipeline id stop.markers_diff,
# phase "post" (Sutra Runtime MVP-1b). Shadow-compares what the model
# actually emitted this turn (H-Sutra header, FLOW RESOLVE line, Depth
# block) against the turn's frozen .facts.json and the four CURRENT marker
# bodies. Never blocks, never writes a marker - every finding is a ledger
# row plus two append-only evidence files (D17).
#
# See runtime/steps/README.md for the full step contract. Decisions:
# BRIEF.md D1, D3, D13, D17, D20.
#
# CONTRACT: nothing on stdout, nothing on stderr, always exit 0 (D12). bash
# 3.2 compatible (sources hooks/marker-lib.sh, which is bash).
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/markers_diff.sh

trap 'exit 0' EXIT

main() {
  set +u
  _md_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_md_root" ] && [ -f "$_md_root/hooks/marker-lib.sh" ] && . "$_md_root/hooks/marker-lib.sh"
  [ -n "$_md_root" ] && [ -f "$_md_root/runtime/ledger.sh" ] && . "$_md_root/runtime/ledger.sh"
  [ -n "$_md_root" ] && [ -f "$_md_root/runtime/flags.sh" ] && . "$_md_root/runtime/flags.sh"
  set -u

  command -v sutra_marker_has >/dev/null 2>&1 || return 0
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  command -v sutra_flag_markers >/dev/null 2>&1 || return 0

  _MD_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _MD_EVENT="${SUTRA_EVENT:-${SUTRA_LEDGER_EVENT:-Stop}}"
  _MD_STEP="${SUTRA_STEP_ID:-stop.markers_diff}"
  _MD_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"
  case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac
  MD_ANY_DIFF=0

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true

  # -- step 1: resolve the flag; marker_flag is written EVERY run (D13),
  # mirroring markers_write.sh so a reader never has to guess why a Stop
  # produced nothing.
  sutra_flag_markers
  _md_row_flag "$SUTRA_MARKERS_MODE" "$SUTRA_MARKERS_SOURCE"

  # -- step 2: the comparator itself only runs on|shadow (D17). -----------
  case "$SUTRA_MARKERS_MODE" in
    on|shadow) ;;
    *) return 0 ;;
  esac

  _MD_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_MD_SID" ] || return 0

  _MD_SHADOW_DIR="$_MD_PROJ/.sutra/shadow/markers"
  mkdir -p "$_MD_SHADOW_DIR" 2>/dev/null
  TURNS_PATH="$_MD_SHADOW_DIR/turns.jsonl"
  DIFFS_PATH="$_MD_SHADOW_DIR/diffs.jsonl"

  # -- step 3: this turn's facts file must exist and parse (D17). ---------
  _MD_FACTS="$_MD_PROJ/.sutra/turn/$_MD_SID/$_MD_TURN.facts.json"
  if [ ! -f "$_MD_FACTS" ]; then
    _md_row_facts_missing
    return 0
  fi
  _MD_FACTS_TSV="$(jq -r '
    [(.classify.verb // "UNKNOWN"), (.classify.timing // "unknown"),
     (.classify.channel // "unknown"), (.classify.reversibility // "unknown"),
     (.classify.decision_risk // "unknown"), ((.depth.n // 0) | tostring),
     (.resolve.resolution // "CONSTRUCT"), (.resolve.scope // "none")]
    | join("|")' "$_MD_FACTS" 2>/dev/null)"
  if [ -z "$_MD_FACTS_TSV" ]; then
    _md_row_facts_missing
    return 0
  fi
  IFS='|' read -r F_VERB F_TIMING F_CHANNEL F_REV F_RISK F_DEPTH F_RESOLUTION F_SCOPE <<< "$_MD_FACTS_TSV"
  case "$F_DEPTH" in ''|*[!0-9]*) F_DEPTH=0 ;; esac

  # -- step 4: the model's response text - stdin first, transcript tail
  # fallback (last 262144 bytes only, D17). ---------------------------
  RESPONSE_TEXT="$(printf '%s' "$STDIN_RAW" | jq -r '.last_assistant_message // empty' 2>/dev/null)"
  if [ -z "$RESPONSE_TEXT" ]; then
    _MD_TP="$(printf '%s' "$STDIN_RAW" | jq -r '.transcript_path // empty' 2>/dev/null)"
    if [ -n "$_MD_TP" ] && [ -f "$_MD_TP" ]; then
      RESPONSE_TEXT="$(tail -c 262144 "$_MD_TP" 2>/dev/null | jq -R -s -r '
        split("\n") | map(select(length>0)) | map(try fromjson catch empty)
        | map(select(.type=="assistant"))
        | if length == 0 then "" else
            (last | (.message.content // []) | map(select(.type=="text") | .text) | join("\n"))
          end' 2>/dev/null)"
    fi
  fi

  # -- step 5: parse the H-Sutra header. Tolerant of U+00B7 or a plain '.'
  # as the DIR/VERB separator (D17); normalise to '.' first so one sed
  # pattern covers both. Requires TIMING/CHANNEL/REV/RISK all present.
  _HDR_LINE="$(printf '%s\n' "$RESPONSE_TEXT" | grep -E '^[[:space:]]*\[.*TIMING:.*RISK:.*\]' | head -1)"
  _HDR_NORM="$(printf '%s' "$_HDR_LINE" | sed 's/·/./g')"
  _BRACKET=""
  if [ -n "$_HDR_NORM" ]; then
    _BRACKET="$(printf '%s' "$_HDR_NORM" | sed -E 's/^[^[]*\[([^]]*)\].*/\1/')"
  fi
  _DIRVERB_TOK=""
  [ -n "$_BRACKET" ] && _DIRVERB_TOK="$(printf '%s' "$_BRACKET" | awk '{print $1}')"
  _MODEL_DIR=""
  _MODEL_VERB=""
  case "$_DIRVERB_TOK" in
    *.*) _MODEL_DIR="${_DIRVERB_TOK%%.*}"; _MODEL_VERB="${_DIRVERB_TOK#*.}" ;;
  esac
  _MODEL_TIMING="$(printf '%s' "$_BRACKET" | sed -n 's/.*TIMING:\([A-Za-z0-9_-]*\).*/\1/p')"
  _MODEL_CHANNEL="$(printf '%s' "$_BRACKET" | sed -n 's/.*CHANNEL:\([A-Za-z0-9_-]*\).*/\1/p')"
  _MODEL_REV="$(printf '%s' "$_BRACKET" | sed -n 's/.*REV:\([A-Za-z0-9_-]*\).*/\1/p')"
  _MODEL_RISK="$(printf '%s' "$_BRACKET" | sed -n 's/.*RISK:\([A-Za-z0-9_-]*\).*/\1/p')"

  if [ -z "$_BRACKET" ] || [ -z "$_MODEL_DIR" ] || [ -z "$_MODEL_VERB" ] || \
     [ -z "$_MODEL_TIMING" ] || [ -z "$_MODEL_RISK" ]; then
    _md_row_header_missing
    return 0
  fi

  # -- step 6: parse the FLOW RESOLVE line (gate_field=false either way). -
  _FLOW_LINE="$(printf '%s\n' "$RESPONSE_TEXT" | grep -E 'RESOLVE:' | head -1)"
  _MODEL_RESOLUTION=""
  _MODEL_SCOPE=""
  if printf '%s' "$_FLOW_LINE" | grep -qE 'RESOLVE:[[:space:]]*FOLLOW'; then
    _mrn="$(printf '%s' "$_FLOW_LINE" | sed -n 's/.*FOLLOW[[:space:]]*\([^ (]*\).*/\1/p')"
    [ -n "$_mrn" ] && _MODEL_RESOLUTION="FOLLOW:$_mrn"
    _MODEL_SCOPE="$(printf '%s' "$_FLOW_LINE" | sed -n 's/.*scope[[:space:]]*\([A-Za-z]*\).*/\1/p')"
  elif printf '%s' "$_FLOW_LINE" | grep -qE 'RESOLVE:[[:space:]]*CONSTRUCT'; then
    _MODEL_RESOLUTION="CONSTRUCT"
    _MODEL_SCOPE="none"
  fi

  # -- step 7: parse the Depth block ("DEPTH: N/5"). -----------------------
  _DEPTH_LINE="$(printf '%s\n' "$RESPONSE_TEXT" | grep -E 'DEPTH:[[:space:]]*[0-9]+/5' | head -1)"
  _MODEL_DEPTH="$(printf '%s' "$_DEPTH_LINE" | sed -n 's/.*DEPTH:[[:space:]]*\([0-9]*\)\/5.*/\1/p')"

  # -- step 8: would_have_blocked = the CURRENT marker body is absent now -
  WHB_FLOWCLASS=true
  sutra_marker_has flow-classified >/dev/null 2>&1 && WHB_FLOWCLASS=false
  WHB_DEPTH=true
  sutra_marker_has depth-registered >/dev/null 2>&1 && WHB_DEPTH=false
  WHB_FLOWTYPE=true
  sutra_marker_has flow-type-resolved >/dev/null 2>&1 && WHB_FLOWTYPE=false

  # -- step 9: nine per-field rows (D17). ----------------------------------
  _md_field_row DIRECTION flow-classified "INBOUND"  "$_MODEL_DIR"     true  "$WHB_FLOWCLASS"
  _md_field_row VERB      flow-classified "$F_VERB"    "$_MODEL_VERB"    true  "$WHB_FLOWCLASS"
  _md_field_row TIMING    flow-classified "$F_TIMING"  "$_MODEL_TIMING"  true  "$WHB_FLOWCLASS"
  _md_field_row CHANNEL   flow-classified "$F_CHANNEL" "$_MODEL_CHANNEL" true  "$WHB_FLOWCLASS"
  _md_field_row REV       flow-classified "$F_REV"     "$_MODEL_REV"     true  "$WHB_FLOWCLASS"
  _md_field_row RISK      flow-classified "$F_RISK"    "$_MODEL_RISK"    true  "$WHB_FLOWCLASS"
  _md_depth_row
  _md_field_row RESOLUTION flow-type-resolved "$F_RESOLUTION" "$_MODEL_RESOLUTION" false "$WHB_FLOWTYPE"
  _md_field_row SCOPE      flow-type-resolved "$F_SCOPE"      "$_MODEL_SCOPE"      false "$WHB_FLOWTYPE"

  # -- step 10: one summary line per turn (D17). ---------------------------
  _md_summary="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
        --argjson any_diff "$([ "$MD_ANY_DIFF" = "1" ] && printf true || printf false)" \
    '{kind:"marker_diff_turn",event:$ev,turn_id:$t,step_id:$s,ts:$ts,header_parsed:true,any_gate_diff:$any_diff}' 2>/dev/null)"
  [ -n "$_md_summary" ] && printf '%s\n' "$_md_summary" >> "$TURNS_PATH" 2>/dev/null

  return 0
}

# -- helpers -----------------------------------------------------------------

_md_write_row() {
  [ -n "$1" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$1"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$1"
}

# _md_field_row <field> <name> <runtime> <model> <gate:true|false> <whb:true|false>
_md_field_row() {
  _mfr_eq=false
  [ -n "$4" ] && [ "$3" = "$4" ] && _mfr_eq=true
  _r="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
        --arg name "$2" --arg field "$1" --arg rt "$3" --arg md "$4" \
        --argjson eq "$_mfr_eq" --argjson gf "$5" --argjson whb "$6" \
    '{kind:"marker_diff",event:$ev,turn_id:$t,step_id:$s,ts:$ts,name:$name,field:$field,
      runtime:$rt,model:$md,equal:$eq,gate_field:$gf,would_have_blocked:$whb,header_parsed:true}' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  _md_write_row "$_r"
  if [ "$_mfr_eq" = "false" ]; then
    MD_ANY_DIFF=1
    [ "$5" = "true" ] && printf '%s\n' "$_r" >> "$DIFFS_PATH" 2>/dev/null
  fi
}

# _md_depth_row - DEPTH compares "within 1" (D17), not exact string equality.
_md_depth_row() {
  _mdd_model="$_MODEL_DEPTH"
  case "$_mdd_model" in ''|*[!0-9]*) _mdd_model="" ;; esac
  _mdd_eq=false
  if [ -n "$_mdd_model" ]; then
    _mdd_diff=$(( F_DEPTH - _mdd_model ))
    [ "$_mdd_diff" -lt 0 ] && _mdd_diff=$(( 0 - _mdd_diff ))
    [ "$_mdd_diff" -le 1 ] && _mdd_eq=true
  fi
  _r="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
        --arg name "depth-registered" --arg field "DEPTH" \
        --arg rt "$F_DEPTH" --arg md "$_MODEL_DEPTH" \
        --argjson eq "$_mdd_eq" --argjson gf true --argjson whb "$WHB_DEPTH" \
    '{kind:"marker_diff",event:$ev,turn_id:$t,step_id:$s,ts:$ts,name:$name,field:$field,
      runtime:$rt,model:$md,equal:$eq,gate_field:$gf,would_have_blocked:$whb,header_parsed:true}' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  _md_write_row "$_r"
  if [ "$_mdd_eq" = "false" ]; then
    MD_ANY_DIFF=1
    printf '%s\n' "$_r" >> "$DIFFS_PATH" 2>/dev/null
  fi
}

_md_row_flag() {
  _r="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
        --arg mode "$1" --arg source "$2" \
    '{kind:"marker_flag",event:$ev,turn_id:$t,step_id:$s,ts:$ts,mode:$mode,source:$source}' 2>/dev/null)"
  _md_write_row "$_r"
}

_md_row_facts_missing() {
  _r="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
    '{kind:"marker_diff",event:$ev,turn_id:$t,step_id:$s,ts:$ts,facts_present:false}' 2>/dev/null)"
  _md_write_row "$_r"
}

_md_row_header_missing() {
  _r="$(jq -nc --arg ev "$_MD_EVENT" --arg t "$_MD_TURN" --arg s "$_MD_STEP" --arg ts "$NOW_TS" \
    '{kind:"marker_diff",event:$ev,turn_id:$t,step_id:$s,ts:$ts,header_parsed:false}' 2>/dev/null)"
  _md_write_row "$_r"
}

main "$@" || true
exit 0
