#!/usr/bin/env bash
# markers_write.sh - native:markers_write, pipeline id ups.markers_write,
# phase "post" (Sutra Runtime MVP-1). Computes the four per-turn governance
# markers (input-routed, depth-registered, flow-classified,
# flow-type-resolved) deterministically from classify.sh /
# workflow-type-match.sh / flow-factors.sh and writes them via
# sutra_marker_set, plus one .facts.json evidence file.
#
# See runtime/steps/README.md for the full step contract. Decisions: BRIEF.md
# D1, D3, D5-D16, D20.
#
# CONTRACT: nothing on stdout, nothing on stderr, always exit 0 (D12). Every
# diagnostic is a ledger row via sutra_ledger_write (D13). bash 3.2
# compatible - this file sources hooks/marker-lib.sh, which is bash, so it
# cannot itself be POSIX sh (BRIEF.md section 1 Rule).
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/markers_write.sh

trap 'exit 0' EXIT

main() {
  set +u
  _mw_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_mw_root" ] && [ -f "$_mw_root/hooks/marker-lib.sh" ] && . "$_mw_root/hooks/marker-lib.sh"
  [ -n "$_mw_root" ] && [ -f "$_mw_root/runtime/ledger.sh" ] && . "$_mw_root/runtime/ledger.sh"
  [ -n "$_mw_root" ] && [ -f "$_mw_root/runtime/flags.sh" ] && . "$_mw_root/runtime/flags.sh"
  [ -n "$_mw_root" ] && [ -f "$_mw_root/runtime/lib/prompt.sh" ] && . "$_mw_root/runtime/lib/prompt.sh"
  set -u

  # Own tools missing -> nothing this step can safely do. Never crash, never
  # print (D12): just stand down.
  command -v sutra_marker_set >/dev/null 2>&1 || return 0
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  command -v sutra_flag_markers >/dev/null 2>&1 || return 0
  command -v sutra_sha256_string >/dev/null 2>&1 || return 0

  # -- identity: this step's own env (D3), with ledger-init as a fallback so
  # the row shape is never malformed even outside a full sutra-turn run.
  _MW_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _MW_EVENT="${SUTRA_EVENT:-${SUTRA_LEDGER_EVENT:-UserPromptSubmit}}"
  _MW_STEP="${SUTRA_STEP_ID:-ups.markers_write}"
  _MW_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"
  case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true

  # -- step 1: resolve the flag; marker_flag is written EVERY run (D13). ----
  sutra_flag_markers
  _mw_row_flag "$SUTRA_MARKERS_MODE" "$SUTRA_MARKERS_SOURCE"

  if [ "$SUTRA_MARKERS_MODE" = "off" ]; then
    _mw_row_skip "*" "flag-off"
    return 0
  fi

  # -- step 2: synthetic-turn guard, byte-for-byte with reset-turn-markers.sh
  # guards 1 and 2 (D7). Guard order matches: flag-off is checked first
  # (case 2), synthetic second (case 12) - a synthetic prompt on an ON turn
  # still gets exactly one skip.
  # The pattern list lives in runtime/lib/prompt.sh since adherence row 1
  # (two notification shapes were missing here; shared so it cannot drift).
  PROMPT=$(printf '%s' "$STDIN_RAW" | jq -r '.prompt // empty' 2>/dev/null)
  if command -v sutra_prompt_synthetic >/dev/null 2>&1; then
    if sutra_prompt_synthetic "$PROMPT"; then
      _mw_row_skip "*" "synthetic"
      return 0
    fi
  else
    case "$PROMPT" in
      "")
        _mw_row_skip "*" "synthetic"
        return 0
        ;;
      *"<system-reminder>"*|\
      *"PreToolUse:"*"hook additional context"*|\
      *"was modified, either by the user or by a linter"*|\
      *"READ-BEFORE-EDIT REMINDER"*|\
      *"task tools haven't been used recently"*|\
      *"<local-command-caveat>"*|\
      *"<task-notification>"*|\
      *"[SYSTEM NOTIFICATION"*)
        _mw_row_skip "*" "synthetic"
        return 0
        ;;
    esac
  fi

  # -- step 3: session id / marker dir must be establishable. -------------
  _MW_SID="$(_sutra_sid 2>/dev/null)"
  _MW_MDIR="$(sutra_marker_dir 2>/dev/null)"
  if [ -z "$_MW_SID" ] || [ -z "$_MW_MDIR" ] || [ ! -d "$_MW_MDIR" ]; then
    _mw_row_skip "*" "no-session"
    return 0
  fi

  PROMPT_SHA="$(sutra_sha256_string "$PROMPT")"

  # -- step 4: classify.sh (bash; no python3 needed) - D11 guard. ---------
  CLASSIFY_OUT="$(bash "$_mw_root/skills/human-sutra/scripts/classify.sh" "$PROMPT" 2>/dev/null)"
  CLASSIFY_RC=$?
  CLASSIFY_TSV=""
  if [ "$CLASSIFY_RC" -eq 0 ] && [ -n "$CLASSIFY_OUT" ]; then
    CLASSIFY_TSV="$(printf '%s' "$CLASSIFY_OUT" | jq -r \
      '[(.verb // "UNKNOWN"), (.timing // "unknown"), (.channel // "unknown"),
        (.reversibility // "unknown"), (.decision_risk // "unknown")] | @tsv' 2>/dev/null)"
  fi
  if [ -z "$CLASSIFY_TSV" ]; then
    CLASSIFY_FAILED=1
    VERB=UNKNOWN; TIMING=unknown; CHANNEL=unknown; REV=unknown; RISK=unknown
    CLASSIFY_JSON=null
    _mw_row_source_failed "classify.sh" "$CLASSIFY_RC"
  else
    CLASSIFY_FAILED=0
    IFS=$'\t' read -r VERB TIMING CHANNEL REV RISK <<< "$CLASSIFY_TSV"
    CLASSIFY_JSON="$CLASSIFY_OUT"
  fi

  case "$VERB" in
    QUERY)  TYPE=question ;;
    DIRECT) TYPE=direction ;;
    ASSERT) TYPE=feedback ;;
    *)      TYPE=task ;;
  esac

  # -- step 5: workflow-type-match.sh (python3 heredoc) - D11 guard. ------
  WTM_OUT=""
  WTM_RC=1
  if [ -n "$_mw_root" ] && [ -x "$_mw_root/bin/workflow-type-match.sh" ]; then
    WTM_OUT="$(CLAUDE_PROJECT_DIR="$_MW_PROJ" CLAUDE_PLUGIN_ROOT="$_mw_root" \
      bash "$_mw_root/bin/workflow-type-match.sh" "$PROMPT" 2>/dev/null)"
    WTM_RC=$?
  fi
  WTM_LINE1="$(printf '%s' "$WTM_OUT" | head -1)"
  if [ "$WTM_RC" -ne 0 ] || [ -z "$WTM_LINE1" ]; then
    WTM_DEGRADED=1
    WTM_LINE1="RESOLUTION=CONSTRUCT SCOPE=none SCORE=0"
    _mw_row_source_failed "workflow-type-match.sh" "$WTM_RC"
  else
    WTM_DEGRADED=0
  fi
  WTM_RESOLUTION="$(printf '%s' "$WTM_LINE1" | sed -n 's/^RESOLUTION=\([^ ]*\).*/\1/p')"
  WTM_SCOPE="$(printf '%s' "$WTM_LINE1" | sed -n 's/.*SCOPE=\([^ ]*\).*/\1/p')"
  WTM_SCORE="$(printf '%s' "$WTM_LINE1" | sed -n 's/.*SCORE=\([0-9-]*\).*/\1/p')"
  case "$WTM_SCORE" in ''|*[!0-9-]*) WTM_SCORE=0 ;; esac

  # -- step 6: flow-factors.sh (python3 heredoc) - D11 guard. -------------
  FF_OUT=""
  FF_RC=1
  if [ -n "$_mw_root" ] && [ -x "$_mw_root/bin/flow-factors.sh" ]; then
    FF_OUT="$(bash "$_mw_root/bin/flow-factors.sh" "$PROMPT" 2>/dev/null)"
    FF_RC=$?
  fi
  FF_TSV=""
  if [ "$FF_RC" -eq 0 ] && [ -n "$FF_OUT" ]; then
    FF_TSV="$(printf '%s' "$FF_OUT" | jq -r \
      '[(.unit_factors.steps_est // 0), (.unit_factors.mutation_verbs // 0)] | @tsv' 2>/dev/null)"
  fi
  if [ -z "$FF_TSV" ]; then
    FF_DEGRADED=1
    STEPS_EST=0; MUTATION_VERBS=0
    FACTORS_JSON=null
    _mw_row_source_failed "flow-factors.sh" "$FF_RC"
  else
    FF_DEGRADED=0
    IFS=$'\t' read -r STEPS_EST MUTATION_VERBS <<< "$FF_TSV"
    FACTORS_JSON="$FF_OUT"
  fi
  case "$STEPS_EST" in ''|*[!0-9]*) STEPS_EST=0 ;; esac
  case "$MUTATION_VERBS" in ''|*[!0-9]*) MUTATION_VERBS=0 ;; esac

  # -- step 7: depth rubric (D9), deterministic. ---------------------------
  IS_COMPANY=0
  _mw_profile="$_MW_PROJ/.claude/sutra-project.json"
  if [ -f "$_mw_profile" ]; then
    _mw_prof_val="$(jq -r '.profile // empty' "$_mw_profile" 2>/dev/null)"
    [ "$_mw_prof_val" = "company" ] && IS_COMPANY=1
  fi

  if [ "$IS_COMPANY" = "1" ]; then
    DEPTH=5; RUBRIC=profile-company
  elif [ "$VERB" = "QUERY" ]; then
    DEPTH=1; RUBRIC=verb-query
  elif [ "$VERB" = "ASSERT" ]; then
    DEPTH=2; RUBRIC=verb-assert
  elif [ "$VERB" = "DIRECT" ]; then
    if [ "$FF_DEGRADED" = "1" ]; then
      DEPTH=3; RUBRIC=direct-degraded
    elif [ "$STEPS_EST" -ge 3 ] || [ "$MUTATION_VERBS" -ge 2 ]; then
      DEPTH=4; RUBRIC=direct-steps
    elif [ "$MUTATION_VERBS" -ge 1 ]; then
      DEPTH=3; RUBRIC=direct-mutation
    else
      DEPTH=2; RUBRIC=default
    fi
  else
    DEPTH=2; RUBRIC=default
  fi

  # -- step 8: TASK slug (D8): first 6 tokens > 2 chars, lowercased,
  # [a-z0-9] joined by '-', max 40 chars, fallback "turn".
  SLUG="$(_mw_slug "$PROMPT")"

  # -- step 9: the four bodies (D8, D10). ----------------------------------
  DEPTH_BODY="$(printf 'DEPTH=%s TASK=%s TS=%s\nSESSION=%s\nRUBRIC=%s\nSOURCE=runtime\nSTEP=%s\nTURN=%s' \
    "$DEPTH" "$SLUG" "$NOW_TS" "$_MW_SID" "$RUBRIC" "$_MW_STEP" "$_MW_TURN")"

  INPUT_ROUTED_BODY="$(printf 'TYPE=%s\nVERB=%s\nTASK=%s\nSESSION=%s\nTS=%s\nSOURCE=runtime\nSTEP=%s\nTURN=%s' \
    "$TYPE" "$VERB" "$SLUG" "$_MW_SID" "$NOW_TS" "$_MW_STEP" "$_MW_TURN")"

  FLOW_CLASSIFIED_BODY="$(printf 'TYPE=%s\nVERB=%s\nSESSION=%s\nFIRED_BY=runtime\nTS=%s\nCELL=INBOUND.%s\nTIMING=%s\nCHANNEL=%s\nREV=%s\nRISK=%s\nSOURCE=runtime\nSTEP=%s\nTURN=%s' \
    "$TYPE" "$VERB" "$_MW_SID" "$NOW_TS" "$VERB" "$TIMING" "$CHANNEL" "$REV" "$RISK" "$_MW_STEP" "$_MW_TURN")"

  FLOW_TYPE_RESOLVED_BODY="$WTM_LINE1
SESSION=$_MW_SID
TS=$NOW_TS
SOURCE=runtime
STEP=$_MW_STEP
TURN=$_MW_TURN"
  [ "$WTM_DEGRADED" = "1" ] && FLOW_TYPE_RESOLVED_BODY="$FLOW_TYPE_RESOLVED_BODY
DEGRADED=python3"

  # -- step 10: write, per mode (D6, D15). ---------------------------------
  M_INPUT_ROUTED="skipped:narrated"
  M_DEPTH_REGISTERED="skipped:narrated"
  M_FLOW_CLASSIFIED="skipped:narrated"
  M_FLOW_TYPE_RESOLVED="skipped:narrated"

  if [ "$SUTRA_MARKERS_MODE" = "on" ]; then
    if _mw_should_write "input-routed"; then
      sutra_marker_set input-routed "$INPUT_ROUTED_BODY"
      _mw_row_write "input-routed" "on"; M_INPUT_ROUTED=written
    else
      _mw_row_skip "input-routed" "narrated"
    fi
    if _mw_should_write "depth-registered"; then
      sutra_marker_set depth-registered "$DEPTH_BODY"
      _mw_row_write "depth-registered" "on"; M_DEPTH_REGISTERED=written
    else
      _mw_row_skip "depth-registered" "narrated"
    fi
    if _mw_should_write "flow-classified"; then
      sutra_marker_set flow-classified "$FLOW_CLASSIFIED_BODY"
      _mw_row_write "flow-classified" "on"; M_FLOW_CLASSIFIED=written
    else
      _mw_row_skip "flow-classified" "narrated"
    fi
    if _mw_should_write "flow-type-resolved"; then
      sutra_marker_set flow-type-resolved "$FLOW_TYPE_RESOLVED_BODY"
      _mw_row_write "flow-type-resolved" "on"; M_FLOW_TYPE_RESOLVED=written
    else
      _mw_row_skip "flow-type-resolved" "narrated"
    fi
  else
    # shadow (D15): real markers untouched, unconditional shadow copies.
    _mw_shadow_dir="$_MW_PROJ/.sutra/shadow/markers/$_MW_SID/$_MW_TURN"
    mkdir -p "$_mw_shadow_dir" 2>/dev/null
    _mw_shadow_write "$_mw_shadow_dir" "input-routed" "$INPUT_ROUTED_BODY"; M_INPUT_ROUTED=shadow
    _mw_shadow_write "$_mw_shadow_dir" "depth-registered" "$DEPTH_BODY"; M_DEPTH_REGISTERED=shadow
    _mw_shadow_write "$_mw_shadow_dir" "flow-classified" "$FLOW_CLASSIFIED_BODY"; M_FLOW_CLASSIFIED=shadow
    _mw_shadow_write "$_mw_shadow_dir" "flow-type-resolved" "$FLOW_TYPE_RESOLVED_BODY"; M_FLOW_TYPE_RESOLVED=shadow
  fi

  # -- step 11: facts file (D14), modes on + shadow only. ------------------
  MARKERS_JSON="{\"input-routed\":\"$M_INPUT_ROUTED\",\"depth-registered\":\"$M_DEPTH_REGISTERED\",\"flow-classified\":\"$M_FLOW_CLASSIFIED\",\"flow-type-resolved\":\"$M_FLOW_TYPE_RESOLVED\"}"

  _mw_deg_items=""
  if [ "$CLASSIFY_FAILED" = "1" ]; then _mw_deg_items="\"classify.sh\""; fi
  if [ "$WTM_DEGRADED" = "1" ]; then
    if [ -n "$_mw_deg_items" ]; then _mw_deg_items="$_mw_deg_items,\"workflow-type-match.sh\""; else _mw_deg_items="\"workflow-type-match.sh\""; fi
  fi
  if [ "$FF_DEGRADED" = "1" ]; then
    if [ -n "$_mw_deg_items" ]; then _mw_deg_items="$_mw_deg_items,\"flow-factors.sh\""; else _mw_deg_items="\"flow-factors.sh\""; fi
  fi
  DEGRADED_JSON="[$_mw_deg_items]"

  FACTS_JSON="$(jq -n \
    --arg turn_id "$_MW_TURN" --arg session_id "$_MW_SID" --arg mode "$SUTRA_MARKERS_MODE" \
    --arg prompt_sha256 "$PROMPT_SHA" --arg type "$TYPE" --arg slug "$SLUG" \
    --arg resolution "$WTM_RESOLUTION" --arg scope "$WTM_SCOPE" --argjson score "$WTM_SCORE" \
    --argjson resolve_degraded "$([ "$WTM_DEGRADED" = "1" ] && printf true || printf false)" \
    --argjson depth_n "$DEPTH" --arg rubric "$RUBRIC" \
    --argjson classify "$CLASSIFY_JSON" --argjson factors "$FACTORS_JSON" \
    --argjson markers "$MARKERS_JSON" --argjson degraded "$DEGRADED_JSON" \
    '{turn_id:$turn_id, session_id:$session_id, mode:$mode, prompt_sha256:$prompt_sha256,
      classify:$classify,
      resolve:{resolution:$resolution, scope:$scope, score:$score, degraded:$resolve_degraded},
      factors:$factors,
      depth:{n:$depth_n, rubric:$rubric},
      type:$type, slug:$slug, markers:$markers, degraded:$degraded}' 2>/dev/null)"

  if [ -n "$FACTS_JSON" ]; then
    _mw_facts_dir="$_MW_PROJ/.sutra/turn/$_MW_SID"
    mkdir -p "$_mw_facts_dir" 2>/dev/null
    _mw_facts_tmp="$_mw_facts_dir/.$_MW_TURN.facts.json.tmp.$$"
    _mw_facts_path="$_mw_facts_dir/$_MW_TURN.facts.json"
    if printf '%s\n' "$FACTS_JSON" > "$_mw_facts_tmp" 2>/dev/null; then
      mv -f "$_mw_facts_tmp" "$_mw_facts_path" 2>/dev/null
    fi
  fi

  return 0
}

# -- helpers -----------------------------------------------------------------

# _mw_should_write <name> -> 0 (write) when the marker is absent, or its
# current body carries a whole line exactly SOURCE=runtime or FIRED_BY=hook
# (computed, not model-narrated). 1 (skip) otherwise. Reads the session-dir
# file DIRECTLY (D6) - never sutra_marker_read, so a foreign/legacy global is
# never adopted by this check.
_mw_should_write() {
  _msw_path="$_MW_MDIR/$1"
  [ -f "$_msw_path" ] || return 0
  grep -qxE 'SOURCE=runtime|FIRED_BY=hook' "$_msw_path" 2>/dev/null && return 0
  return 1
}

# _mw_shadow_write <dir> <name> <body>
_mw_shadow_write() {
  _msw_tmp="$1/.$2.tmp.$$"
  if printf '%s\n' "$3" > "$_msw_tmp" 2>/dev/null; then
    mv -f "$_msw_tmp" "$1/$2" 2>/dev/null
  fi
  _mw_row_shadow "$2" "$1/$2"
}

# _mw_slug <prompt> -> first 6 tokens (len>2) of [a-z0-9], joined by '-',
# lowercased, max 40 chars, fallback "turn" (D8).
_mw_slug() {
  _sl_raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' ' ')"
  _sl_out=""
  _sl_n=0
  for _sl_tok in $_sl_raw; do
    [ ${#_sl_tok} -gt 2 ] || continue
    if [ -z "$_sl_out" ]; then _sl_out="$_sl_tok"; else _sl_out="$_sl_out-$_sl_tok"; fi
    _sl_n=$((_sl_n + 1))
    [ "$_sl_n" -ge 6 ] && break
  done
  [ -n "$_sl_out" ] || _sl_out="turn"
  printf '%.40s' "$_sl_out"
}

# -- ledger row writers (D13). One jq -nc call each, printed to BOTH the
# canonical and flat ledger handles already in the environment.
_mw_write_row() {
  [ -n "$1" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$1"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$1"
}

_mw_row_flag() {
  _r="$(jq -nc --arg ev "$_MW_EVENT" --arg t "$_MW_TURN" --arg s "$_MW_STEP" --arg ts "$NOW_TS" \
        --arg mode "$1" --arg source "$2" \
    '{kind:"marker_flag",event:$ev,turn_id:$t,step_id:$s,ts:$ts,mode:$mode,source:$source}' 2>/dev/null)"
  _mw_write_row "$_r"
}

_mw_row_write() {
  _r="$(jq -nc --arg ev "$_MW_EVENT" --arg t "$_MW_TURN" --arg s "$_MW_STEP" --arg ts "$NOW_TS" \
        --arg name "$1" --arg mode "$2" \
    '{kind:"marker_write",event:$ev,turn_id:$t,step_id:$s,ts:$ts,name:$name,mode:$mode}' 2>/dev/null)"
  _mw_write_row "$_r"
}

_mw_row_skip() {
  _r="$(jq -nc --arg ev "$_MW_EVENT" --arg t "$_MW_TURN" --arg s "$_MW_STEP" --arg ts "$NOW_TS" \
        --arg name "$1" --arg reason "$2" \
    '{kind:"marker_skip",event:$ev,turn_id:$t,step_id:$s,ts:$ts,name:$name,reason:$reason}' 2>/dev/null)"
  _mw_write_row "$_r"
}

_mw_row_shadow() {
  _r="$(jq -nc --arg ev "$_MW_EVENT" --arg t "$_MW_TURN" --arg s "$_MW_STEP" --arg ts "$NOW_TS" \
        --arg name "$1" --arg path "$2" \
    '{kind:"marker_shadow",event:$ev,turn_id:$t,step_id:$s,ts:$ts,name:$name,path:$path}' 2>/dev/null)"
  _mw_write_row "$_r"
}

_mw_row_source_failed() {
  _msf_exit="$2"
  case "$_msf_exit" in ''|*[!0-9]*) _msf_exit=1 ;; esac
  _r="$(jq -nc --arg ev "$_MW_EVENT" --arg t "$_MW_TURN" --arg s "$_MW_STEP" --arg ts "$NOW_TS" \
        --arg tool "$1" --argjson exit "$_msf_exit" \
    '{kind:"marker_source_failed",event:$ev,turn_id:$t,step_id:$s,ts:$ts,tool:$tool,exit:$exit}' 2>/dev/null)"
  _mw_write_row "$_r"
}

main "$@" || true
exit 0
