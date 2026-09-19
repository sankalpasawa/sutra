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
  # every written payload: Write content, Edit new_string, MultiEdit edits[],
  # NotebookEdit new_source (workflow wf_1dc20d5c P2-1)
  CONTENT="$(printf '%s' "$STDIN_RAW" | jq -r '[.tool_input.content, .tool_input.new_string, (.tool_input.edits[]?.new_string), .tool_input.new_source] | map(select(. != null)) | join("\n")' 2>/dev/null)"
  EXTRA_PATH="$(printf '%s' "$STDIN_RAW" | jq -r '.tool_input.path // .tool_input.pattern // empty' 2>/dev/null)"
  _t8="$(printf '%s' "$_AG_TURN" | head -c 8)"

  # -- R9: runtime-owned paths (2.285.1, brief ADHERENCE-ROW6 s3.6, D-A15) ----
  # The override file, the flag and kill files, the seal dir and the session
  # stamp belong to the runtime. No tool may TARGET them (file_path), WRITE
  # them from a command or from written content (a redirect or a mutating verb
  # on the line that names them), or touch the seal dir at all. A doc, a test
  # or a grep that merely mentions a name is not a mutation of it (workflow
  # wf_1dc20d5c P1-5). Checked before the orphan/bootstrap returns so a
  # missing ledger never opens the door.
  RO_HIT=""
  { [ -n "$FILE_PATH" ] && sutra_steps_runtime_owned "$FILE_PATH"; } && RO_HIT=1
  [ -z "$RO_HIT" ] && [ -n "$COMMAND" ] && sutra_steps_runtime_owned_write "$COMMAND" && RO_HIT=1
  # a test suite's fixtures name the flag files under a private HOME by design;
  # the file's own path is still refused if it IS a runtime-owned path (row 6)
  # no carve-out for test files (workflow row-6 P1-3: a one-line "test" that
  # deletes the flag files, then a plain sh run, switched the gate off). The
  # plugin's own suites build the flag names from parts so their fixtures
  # pass this scan honestly. Written CONTENT is scanned in content mode: the
  # switch, override, seal and stamp names in a write shape; the ledger and
  # lane names only as Bash targets (workflow P2-3).
  [ -z "$RO_HIT" ] && [ -n "$CONTENT" ] && sutra_steps_runtime_owned_write "$CONTENT" content && RO_HIT=1
  [ -z "$RO_HIT" ] && [ -n "$EXTRA_PATH" ] && printf '%s' "$EXTRA_PATH" | grep -q '\.sutra-runtime/' && RO_HIT=1
  if [ -n "$RO_HIT" ]; then
    _ro_target="$FILE_PATH"; [ -n "$_ro_target" ] || _ro_target="$(printf '%s' "$COMMAND" | tr '\n\r\t' '   ' | LC_ALL=C tr -cd ' -~' | head -c 120)"
    RO_REASON="RUNTIME-OWNED PATH (D-A15, mode $SUTRA_ADHERENCE_MODE): $TOOL names the runtime's own switch, override file, key or session stamp (~/.sutra-overrides, ~/.sutra-runtime-adherence*, ~/.sutra-runtime-markers*, ~/.sutra-runtime-disabled, ~/.sutra-runtime/, .sutra/turn/<sid>/opened). No tool call may read, write or mention them; the founder edits them in a terminal outside Claude, and an override written inside a session is ignored until the next one."
    if [ "$SUTRA_ADHERENCE_MODE" = "on" ]; then
      _ag_row decision "$(jq -nc --arg t "$TOOL" --arg x "$_ro_target" '{decision:"deny", reason:"runtime-owned", tool:$t, target:$x}')"
      [ "$_AG_TURN" != "unknown" ] && [ -f "$(sutra_steps_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN")" ] && _AG_PATH="$(sutra_steps_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN")" && _ag_mutation "$TOOL" "$_ro_target" deny '["runtime-owned"]'
      jq -nc --arg ev "$_AG_EVENT" --arg r "$RO_REASON" --arg sm "[sutra $_t8] REFUSED $TOOL: runtime-owned path" \
        '{hookSpecificOutput:{hookEventName:$ev, permissionDecision:"deny", permissionDecisionReason:$r}, systemMessage:$sm}' 2>/dev/null
    else
      _ag_row decision "$(jq -nc --arg t "$TOOL" --arg x "$_ro_target" '{decision:"warn", reason:"runtime-owned", tool:$t, target:$x}')"
      jq -nc --arg r "$RO_REASON" '{systemMessage:("[warn] " + $r)}' 2>/dev/null
    fi
    return 0
  fi

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
      sutra_steps_exempt_path "$FILE_PATH" "$_AG_SID" && KIND=exempt
      # 2.285.1: a script body (shebang) is never exempt, whatever the path (brief s3.6).
      case "$CONTENT" in '#!'*) KIND=mutation ;; esac ;;
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
  # Live progress (founder, 2026-09-17: "it should also print when each of the
  # steps is done"): every status that changed since the last look is printed
  # as one systemMessage line, which the host shows in the terminal.
  TRANS=""
  STEPS_JSON="$(sutra_steps_compute "$_AG_PROJ" "$_AG_SID" "$_AG_TURN" "$OPENED")"
  if [ -n "$STEPS_JSON" ]; then
    TRANS="$(jq -r --argjson new "$STEPS_JSON" '
      [ .steps[] as $o | ($new[] | select(.id == $o.id)) as $n
        | select($n.status != $o.status)
        | (if $n.status == "done" or $n.status == "open" then "\($n.id) \($n.status)" else "\($n.id) \($o.status) -> \($n.status)" end)
          + (if ($n.detail // "") != "" and $n.status != "pending" then " (" + ($n.detail | tostring | if length > 40 then .[0:37] + "..." else . end) + ")" else "" end) ]
      | join("  |  ")' "$_AG_PATH" 2>/dev/null)"
    _upd="$(jq -c --argjson steps "$STEPS_JSON" '.steps = $steps' "$_AG_PATH" 2>/dev/null)"
    [ -n "$_upd" ] && sutra_steps_write "$_AG_PATH" "$_upd"
  fi
  _t8="$(printf '%s' "$_AG_TURN" | head -c 8)"
  [ -n "$TRANS" ] && _ag_row transition "$(jq -nc --arg t "$TRANS" '{transitions:$t}')"

  if [ "$KIND" != "mutation" ]; then
    [ "$KIND" = "exempt" ] && _ag_mutation "$TOOL" "$TARGET" exempt '[]'
    [ -n "$TRANS" ] && jq -nc --arg m "[sutra $_t8] $TRANS" '{systemMessage:$m}' 2>/dev/null
    return 0
  fi

  # -- row 6: the rules table --------------------------------------------------
  # runtime/rules/gates.json declares every rule; this evaluates them all on
  # every call and names every unmet rule in ONE deny (D-A13). A gate decision
  # reads only the ledger, the turn artifacts, the tool input, the path
  # category table and the override file (D-A10). No gates.json -> the row-1
  # pair (lens, cynefin) is the whole table.
  RULES="$_ag_root/runtime/rules/gates.json"
  _ag_ctx_kind="mutation"; [ "$TOOL" = "Task" ] || [ "$TOOL" = "Agent" ] && _ag_ctx_kind="subagent"
  if [ "$TOOL" = "Bash" ] && printf '%s' "$COMMAND" | grep -qE '(^|[;&|[:space:]])(mv|rm|git[[:space:]]+(mv|rm)|find[[:space:]][^|;]*-delete)([[:space:]]|$)'; then _ag_ctx_kind="structural"; fi
  DEPTH_N="$(printf '%s' "$STEPS_JSON" | jq -r '.[] | select(.id == "depth") | .detail' 2>/dev/null | grep -oE '^[0-9]+' | head -1)"; case "$DEPTH_N" in ''|*[!0-9]*) DEPTH_N=0 ;; esac
  _ag_dp="$(sutra_artifact_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN" depth)"
  if [ -f "$_ag_dp" ] && [ "$(sutra_artifact_check "$_ag_dp" depth "$_AG_TURN" "$_AG_SID" "$OPENED")" = "ok" ]; then
    _ag_dm="$(jq -r '.depth // 0' "$_ag_dp" 2>/dev/null)"; case "$_ag_dm" in ''|*[!0-9]*) _ag_dm=0 ;; esac
    [ "$_ag_dm" -gt "$DEPTH_N" ] && DEPTH_N="$_ag_dm"
  fi
  PATHCAT="none"; NEW_PATH=false
  if [ -n "$FILE_PATH" ]; then
    PATHCAT="$(sutra_steps_path_category "$FILE_PATH" "$_AG_PROJ" "$RULES")"
    [ -e "$FILE_PATH" ] || NEW_PATH=true
  elif [ "$TOOL" = "Bash" ]; then
    # every Bash MUTATION is judged by the most governed path it names
    # (workflow row-6 P1-1: `printf x > holding/bin/x.sh`, tee, cp, sed -i,
    # patch and heredocs write files just like the Write tool), and its
    # redirect / tee / cp targets count as new paths when they do not exist.
    # The MOST governed category wins (DeepSeek P1-1): holding-impl (needs an
    # artifact) > legacy-hard > shared-runtime > plugin-runtime.
    PATHCAT="$(printf '%s' "$COMMAND" | tr ' \t' '\n\n' | grep -E '^[A-Za-z0-9_./~-]+$' | while IFS= read -r _w; do sutra_steps_path_category "$_w" "$_AG_PROJ" "$RULES"; echo; done \
      | awk 'BEGIN{r["holding-impl"]=4; r["legacy-hard"]=3; r["shared-runtime"]=2; r["plugin-runtime"]=1} r[$0]>best{best=r[$0]; c=$0} END{if (c!="") print c}')"
    [ -n "$PATHCAT" ] || PATHCAT="none"
    for _tgt in $(printf '%s' "$COMMAND" | tr -d '"'"'"'' | grep -oE '(>>?|tee( +-a)?|cp +[^ ]+|install +[^ ]+) *[A-Za-z0-9_./~-]+' | sed -E 's/^.* *([A-Za-z0-9_./~-]+)$/\1/' | grep -vE '^/dev/'); do
      case "$_tgt" in /*) _abs="$_tgt" ;; *) _abs="$_AG_PROJ/$_tgt" ;; esac
      [ -e "$_abs" ] || NEW_PATH=true
    done
  fi
  # a missing depth fact never relaxes a rule (DeepSeek row-6 P1-3): the
  # artifact checks then assume the strictest depth
  [ "$DEPTH_N" -gt 0 ] || DEPTH_N=5
  # the placement marker counts only when the ENGINE wrote it (SOURCE=engine,
  # placement-resolve.sh); a model-written marker is a model-writable file and
  # no evidence (workflow row-6 P1-2) - the model's answer to a no-match is
  # the placement artifact
  PL_UNRESOLVED=true
  _ag_pl="$_AG_PROJ/.claude/sessions/$_AG_SID/placement-registered"
  if [ -f "$_ag_pl" ] && [ "$(sed -n 's/^SOURCE=//p' "$_ag_pl" 2>/dev/null | head -1)" = "engine" ] \
     && [ "$(sed -n 's/^DOMAIN_REF=//p' "$_ag_pl" 2>/dev/null | head -1 | tr -d ' ')" != "unresolved" ] \
     && [ -n "$(sed -n 's/^DOMAIN_REF=//p' "$_ag_pl" 2>/dev/null | head -1)" ]; then PL_UNRESOLVED=false; fi
  LANE=false; sutra_steps_lane_configured && LANE=true
  CTX="$(jq -nc --arg kind "$_ag_ctx_kind" --arg tool "$TOOL" --arg cat "$PATHCAT" --argjson depth "$DEPTH_N" --argjson newp "$NEW_PATH" --argjson plu "$PL_UNRESOLVED" --argjson lane "$LANE" \
    '{kind:$kind, tool:$tool, path_category:$cat, depth:$depth, new_path:$newp, placement_unresolved:$plu, lane_configured:$lane, runtime_owned:false}' 2>/dev/null)"

  # which rules apply to this call (jq decides from `when`; R9 was handled above)
  APPLY="$(jq -r --argjson ctx "$CTX" '
    .rules[] | select(.id != "R9")
    | select((.when.kind // ["any"]) as $k | ($k | index("any")) != null or ($k | index($ctx.kind)) != null)
    | select((.when.path_category // null) as $pc | $pc == null or ($pc | index($ctx.path_category)) != null)
    | select((.when.depth_min // 0) <= $ctx.depth)
    | select((.when.new_path // null) as $np | $np == null or $np == $ctx.new_path)
    | select((.when.placement_unresolved // null) as $pu | $pu == null or $pu == $ctx.placement_unresolved)
    | select((.when.lane_configured // null) as $lc | $lc == null or $lc == $ctx.lane_configured)
    | [.id, .decision, ((.needs // []) | join(",")), ((.needs_any // []) | join(",")), ((.reason // .note // "") | gsub("[\\n\\u001f]"; " "))] | join("")' "$RULES" 2>/dev/null)"
  # unit separator, not tab: `read` collapses a run of tabs, so an empty needs
  # column would shift the reason into needs_any (the runtime's own TSV gotcha)
  _US="$(printf '\037')"
  if [ -z "$APPLY" ] && [ ! -f "$RULES" ]; then
    APPLY="R5${_US}deny${_US}artifact:lens,artifact:cynefin${_US}${_US}the turn's judgment artifacts"
  fi
  # a PRESENT but unparseable rules file fails closed (workflow row-6 regress
  # lens): the legacy gates may already be collapsed for this event
  if [ -f "$RULES" ] && ! jq -e '(.rules | type) == "array" and (.rules | length) > 0' "$RULES" >/dev/null 2>&1; then
    APPLY="RULES${_US}deny${_US}never${_US}${_US}runtime/rules/gates.json is present but unparseable; nothing decides until it parses"
  fi

  # _ag_need <entry> -> 0 met / 1 unmet; sets _ag_why
  _ag_need() {
    _ag_why=""
    case "$1" in
      step:*)   _n="${1#step:}"; _s="$(printf '%s' "$STEPS_JSON" | jq -r --arg n "$_n" '.[] | select(.id == $n) | .status' 2>/dev/null)"
                # "missing" is the runtime's own gap (no facts file: markers flag
                # off, or the step failed) - never the model's; it does not refuse
                # (codex P2-4 bootstrap semantics), the ledger row records it.
                case "$_s" in done|open|missing) return 0 ;; esac; _ag_why="step $_n is $_s"; return 1 ;;
      artifact:*) _k="${1#artifact:}"
                _r="$(SUTRA_ARTIFACT_DEPTH="$DEPTH_N" sutra_artifact_check "$(sutra_artifact_path "$_AG_PROJ" "$_AG_SID" "$_AG_TURN" "$_k")" "$_k" "$_AG_TURN" "$_AG_SID" "$OPENED")"
                [ "$_r" = "ok" ] && return 0
                _ag_why="$(sutra_artifact_rel "$_AG_SID" "$_AG_TURN" "$_k") ($_r) $(jq -r --arg k "$_k" '.artifacts[$k].hint // ""' "$RULES" 2>/dev/null)"; return 1 ;;
      review:sealed)
                # one predicate for every verdict, this turn's included: done, a
                # real verdict, fresh, corroborated, sealed, newest two ledgers
                # (workflow row-6 P1-5)
                [ -n "$(sutra_steps_latest_review "$_AG_PROJ" "$_AG_SID" "$NOW_TS")" ] && return 0
                _ag_why="no sealed, corroborated review verdict for this or the previous turn"; return 1 ;;
      override:*) _o="${1#override:}"; case " ${SUTRA_OVERRIDES_APPLIED:-} " in *" $_o "*) return 0 ;; esac
                _ag_why="override $_o not applied from a pre-session ~/.sutra-overrides"; return 1 ;;
      never)    _ag_why="refused by rule"; return 1 ;;
      ''|none)  return 0 ;;
      *)        _ag_why="unknown need $1"; return 1 ;;
    esac
  }

  UNMET=""; UNMET_IDS=""; DECISION="allow"; WARN_ONLY=1
  while IFS="$_US" read -r _rid _rdec _rneeds _rany _rreason; do
    [ -n "${_rid:-}" ] || continue
    _met=1; _why_all=""
    _old_ifs="$IFS"; IFS=','
    for _e in $_rneeds; do IFS="$_old_ifs"; [ -n "$_e" ] || continue
      if ! _ag_need "$_e"; then _met=0; _why_all="$_why_all
    - $_ag_why"; fi
      IFS=','; done; IFS="$_old_ifs"
    if [ -n "$_rany" ]; then
      _any=0; _why_any=""; _old_ifs="$IFS"; IFS=','
      for _e in $_rany; do IFS="$_old_ifs"; [ -n "$_e" ] || continue
        if _ag_need "$_e"; then _any=1; else _why_any="$_why_any
    - $_ag_why"; fi
        IFS=','; done; IFS="$_old_ifs"
      [ "$_any" = "1" ] || { _met=0; _why_all="$_why_all (one of:)$_why_any"; }
    fi
    if [ "$_met" = "0" ]; then
      UNMET="$UNMET
  $_rid $_rreason:$_why_all"
      UNMET_IDS="$UNMET_IDS $_rid"
      case "$_rdec" in deny) DECISION="deny"; WARN_ONLY=0 ;; warn) [ "$DECISION" = "allow" ] && DECISION="warn" ;; esac
    fi
  done <<EOF
$APPLY
EOF
  UNMET_IDS="$(printf '%s' "$UNMET_IDS" | sed 's/^ //')"
  _ag_row rules "$(jq -nc --argjson ctx "$CTX" --arg unmet "$UNMET_IDS" --arg d "$DECISION" '{context:$ctx, unmet:$unmet, decision:$d}' 2>/dev/null)"
  _td_file="$_AG_PROJ/.sutra/turn/$_AG_SID/$_AG_TURN.truthdiff.jsonl"
  [ -d "$(dirname "$_td_file")" ] && jq -nc --arg s "pre.adherence_gate" --arg d "$DECISION" --arg r "$UNMET_IDS" --arg ev "$_AG_EVENT" --arg t "$TOOL" \
    '{ts:(now|floor), source:"rules", step:$s, event:$ev, tool:$t, rc:"0", decision:$d, reason:$r}' >> "$_td_file" 2>/dev/null

  if [ "$DECISION" = "allow" ]; then
    _ag_mutation "$TOOL" "$TARGET" allow '[]'
    [ -n "$TRANS" ] && jq -nc --arg m "[sutra $_t8] $TRANS" '{systemMessage:$m}' 2>/dev/null
    return 0
  fi

  MISSING_JSON="$(printf '%s' "$UNMET_IDS" | tr ' ' '\n' | jq -R . | jq -sc .)"
  REASON="ADHERENCE GATE (rules, mode $SUTRA_ADHERENCE_MODE): $TOOL on $TARGET is refused until every rule below is met. Unmet:$UNMET
Write each artifact with the Write tool, then retry (one batch fixes the turn). turn_id=$_AG_TURN session_id=$_AG_SID ts>=$OPENED depth=$DEPTH_N path_category=$PATHCAT
Trace: bin/sutra-steps latest. Truth-diff: bin/sutra-steps truthdiff."

  _sm=""; [ -n "$TRANS" ] && _sm="[sutra $_t8] $TRANS
"
  if [ "$SUTRA_ADHERENCE_MODE" = "on" ] && [ "$DECISION" = "deny" ]; then
    _ag_mutation "$TOOL" "$TARGET" deny "$MISSING_JSON"
    jq -nc --arg ev "$_AG_EVENT" --arg r "$REASON" --arg sm "${_sm}[sutra $_t8] REFUSED $TOOL: unmet $UNMET_IDS" \
      '{hookSpecificOutput:{hookEventName:$ev, permissionDecision:"deny", permissionDecisionReason:$r}, systemMessage:$sm}' 2>/dev/null
  else
    _ag_mutation "$TOOL" "$TARGET" warn "$MISSING_JSON"
    jq -nc --arg r "$REASON" --arg sm "$_sm" '{systemMessage:($sm + "[warn] " + $r)}' 2>/dev/null
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
