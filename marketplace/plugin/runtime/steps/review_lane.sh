#!/usr/bin/env bash
# review_lane.sh - native:review_lane, pipeline id stop.review_lane, Stop,
# phase "post" (adherence row 2, 2026-09-17).
#
# When the turn mutated repository files (per the step ledger's allow/exempt
# rows outside .sutra/, .claude/, .enforcement/ and memory), the RUNTIME runs
# the two lanes the model used to choose to run:
#   tests   the project's declared test_command (.claude/sutra-project.json)
#   review  a second-lane review of the turn's diff (DeepSeek by default,
#           $SUTRA_REVIEW_LANE_CMD overrides: <cmd> <prompt-file> <out-file>)
# Both run DETACHED (the Stop cap is 320 s, a review takes minutes) and write
# their verdicts to .sutra/turn/<sid>/<turn>.tests.json / .review.json plus
# the session marker deepseek-consulted (SOURCE=runtime). The next turn's
# STEP TRACE reports them; the codex-consult gate accepts the marker. The
# model never writes these files.
#
# CONTRACT (D-A9): flag off -> nothing. Never emits stdout. Always exits 0.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/steps/review_lane.sh

trap 'exit 0' EXIT

main() {
  set +u
  _rl_root="${CLAUDE_PLUGIN_ROOT:-}"
  [ -n "$_rl_root" ] || return 0
  for _f in hooks/marker-lib.sh runtime/ledger.sh runtime/flags.sh runtime/lib/artifact.sh runtime/lib/steps.sh; do
    [ -f "$_rl_root/$_f" ] && . "$_rl_root/$_f"
  done
  set -u
  command -v sutra_flag_adherence >/dev/null 2>&1 || return 0
  command -v sutra_steps_path >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  sutra_flag_adherence
  [ "$SUTRA_ADHERENCE_MODE" = "off" ] && return 0

  _RL_TURN="${SUTRA_TURN_ID:-${SUTRA_LEDGER_TURN:-unknown}}"
  _RL_EVENT="${SUTRA_EVENT:-Stop}"
  _RL_STEP="${SUTRA_STEP_ID:-stop.review_lane}"
  _RL_PROJ="${CLAUDE_PROJECT_DIR:-.}"
  NOW_TS="$(date +%s 2>/dev/null)"; case "$NOW_TS" in ''|*[!0-9]*) NOW_TS=0 ;; esac

  STDIN_RAW="$(cat 2>/dev/null)"
  sutra_sid_from_stdin "$STDIN_RAW" 2>/dev/null || true
  _RL_SID="$(_sutra_sid 2>/dev/null)"
  [ -n "$_RL_SID" ] || return 0
  [ "$_RL_TURN" != "unknown" ] || return 0
  _RL_PATH="$(sutra_steps_path "$_RL_PROJ" "$_RL_SID" "$_RL_TURN")"
  [ -f "$_RL_PATH" ] || { _rl_row skip '{"reason":"no-ledger"}'; return 0; }

  # -- did this turn mutate repository files? -------------------------------
  # Edit/Write rows count by path (state dirs excluded); Bash rows count when
  # the gate allowed or warned them (an exempt Bash row is a governance CLI or
  # an artifact write). Warn-mode rows count too (workflow review P2).
  MUT_N="$(jq -r '
    [ .mutations[]? | select(.decision == "allow" or .decision == "exempt" or .decision == "warn")
      | select((.target // "") != "")
      | select(if .tool == "Bash" then (.decision != "exempt")
               elif (.tool == "Edit" or .tool == "Write" or .tool == "MultiEdit" or .tool == "NotebookEdit")
                 then ((.target // "") | test("(^|/)\\.sutra/|(^|/)\\.claude/|(^|/)\\.enforcement/|/memory/[^/]*\\.md$|(^|/)\\.analytics/") | not)
               else false end) ] | length' "$_RL_PATH" 2>/dev/null)"
  case "$MUT_N" in ''|*[!0-9]*) MUT_N=0 ;; esac
  if [ "$MUT_N" -eq 0 ]; then
    _rl_row skip '{"reason":"no-repo-mutation"}'
    return 0
  fi

  _rl_dir="$_RL_PROJ/.sutra/turn/$_RL_SID"
  TESTS_OUT="$_rl_dir/$_RL_TURN.tests.json"
  REVIEW_OUT="$_rl_dir/$_RL_TURN.review.json"
  LOG_DIR="$_rl_dir/lane-logs"; mkdir -p "$LOG_DIR" 2>/dev/null
  # A lane file older than this ledger's open belongs to an earlier occurrence
  # of the same turn id (repeated prompt): treat it as absent (workflow P1).
  OPENED="$(jq -r '.opened_ts // 0' "$_RL_PATH" 2>/dev/null)"; case "$OPENED" in ''|*[!0-9]*) OPENED=0 ;; esac
  for _lf in "$TESTS_OUT" "$REVIEW_OUT"; do
    if [ -f "$_lf" ] && [ "$(jq -r '(.ts // 0) | tonumber? // 0' "$_lf" 2>/dev/null)" -lt "$OPENED" ]; then
      mv -f "$_lf" "$_lf.stale$OPENED" 2>/dev/null
    fi
  done

  # -- lane 1: tests (the declared test command, detached) -----------------
  # -- row 6 (brief s3.3, workflow P2-1): the blueprint's verify commands RUN
  # here, detached, each under the project dir with a 120 s budget; the
  # sealed <turn>.verifies.json carries one exit code per step and the next
  # turn's "Last turn" line reports them. A verify the runtime cannot run
  # (kind manual) is recorded as skipped, never as passed.
  BP_FILE="$_rl_dir/$_RL_TURN.blueprint.json"
  if [ -f "$BP_FILE" ] && jq -e '.steps | type == "array" and length > 0' "$BP_FILE" >/dev/null 2>&1; then
    VERIFIES_OUT="$_rl_dir/$_RL_TURN.verifies.json"
    jq -nc --arg ts "$NOW_TS" '{lane:"verifies",status:"running",ts:($ts|tonumber)}' > "$VERIFIES_OUT" 2>/dev/null
    _rl_detach_verifies "$_RL_PROJ" "$BP_FILE" "$VERIFIES_OUT" "$LOG_DIR/$_RL_TURN.verifies.log"
    _rl_row verifies "$(jq -c '{status:"started", steps:(.steps|length), runnable:([.steps[] | select(.verify.kind == "cmd")] | length)}' "$BP_FILE" 2>/dev/null)"
  fi

  TEST_CMD=""
  [ -f "$_RL_PROJ/.claude/sutra-project.json" ] && TEST_CMD="$(jq -r '.test_command // empty' "$_RL_PROJ/.claude/sutra-project.json" 2>/dev/null)"
  if [ -z "$TEST_CMD" ]; then
    jq -nc --arg ts "$NOW_TS" '{lane:"tests",status:"no-test-command",exit:null,ts:($ts|tonumber)}' > "$TESTS_OUT" 2>/dev/null
    _rl_row tests '{"status":"no-test-command"}'
  elif [ ! -f "$TESTS_OUT" ]; then
    jq -nc --arg ts "$NOW_TS" --arg cmd "$TEST_CMD" '{lane:"tests",status:"running",cmd:$cmd,exit:null,ts:($ts|tonumber)}' > "$TESTS_OUT" 2>/dev/null
    _rl_detach "$_RL_PROJ" "$TEST_CMD" "$LOG_DIR/$_RL_TURN.tests.log" "$TESTS_OUT" tests
    _rl_row tests "$(jq -nc --arg cmd "$TEST_CMD" '{status:"started",cmd:$cmd}')"
  fi

  # -- lane 2: review of the turn's diff (detached) ------------------------
  if [ ! -f "$REVIEW_OUT" ]; then
    DIFF_FILE="$LOG_DIR/$_RL_TURN.diff"
    # THE TURN'S diff (workflow review P1): against the baseline steps_ledger
    # recorded at open (a `git stash create` commit of the worktree, or HEAD), so
    # commits made inside the turn are included and pre-existing dirt excluded;
    # restricted to the ledger's file targets when there are any, with the
    # turn's own new untracked files appended, then the 400 KB cap.
    BASE="$(jq -r '.git_base // ""' "$_RL_PATH" 2>/dev/null)"
    [ -n "$BASE" ] && git -C "$_RL_PROJ" rev-parse -q --verify "$BASE^{commit}" >/dev/null 2>&1 || BASE=""
    TARGETS="$(jq -r --arg proj "$_RL_PROJ/" '.mutations[]? | select(.tool != "Bash") | select(.decision == "allow" or .decision == "warn") | (.target // "") | select(. != "") | ltrimstr($proj)' "$_RL_PATH" 2>/dev/null | grep -v '^/' | sort -u)"
    {
      if [ -n "$BASE" ]; then
        if [ -n "$TARGETS" ]; then
          printf '%s\n' "$TARGETS" | while IFS= read -r _t; do [ -n "$_t" ] || continue
            if git -C "$_RL_PROJ" ls-files --error-unmatch -- "$_t" >/dev/null 2>&1 || git -C "$_RL_PROJ" cat-file -e "$BASE:$_t" 2>/dev/null; then
              git -C "$_RL_PROJ" diff --no-color "$BASE" -- "$_t" 2>/dev/null
            elif [ -f "$_RL_PROJ/$_t" ]; then
              git -C "$_RL_PROJ" diff --no-color --no-index -- /dev/null "$_t" 2>/dev/null
            fi
          done
        else
          git -C "$_RL_PROJ" diff --no-color "$BASE" 2>/dev/null
        fi
      else
        git -C "$_RL_PROJ" diff --no-color 2>/dev/null; git -C "$_RL_PROJ" diff --cached --no-color 2>/dev/null
      fi
    } | head -c 400000 > "$DIFF_FILE" 2>/dev/null
    if [ ! -s "$DIFF_FILE" ]; then
      jq -nc --arg ts "$NOW_TS" '{lane:"review",status:"empty-diff",verdict:null,ts:($ts|tonumber)}' > "$REVIEW_OUT" 2>/dev/null
      _rl_row review '{"status":"empty-diff"}'
    else
      PROMPT_FILE="$LOG_DIR/$_RL_TURN.review-prompt.txt"
      UNIT="$(jq -r '.unit // ""' "$_RL_PATH" 2>/dev/null | head -c 200)"
      {
        printf 'You are the second review lane of a governance runtime. Review this diff for defects (correctness, portability to bash 3.2 and macOS, silent failure, contract breaks). Answer in this exact shape:\nVERDICT: PASS | CHANGES-REQUIRED\nP1 (must fix): numbered, each with the failing input and the concrete fix\nP2 (should fix): numbered\nUnit of work: %s\n\nDIFF:\n' "$UNIT"
        cat "$DIFF_FILE"
      } > "$PROMPT_FILE" 2>/dev/null
      REVIEW_CMD="${SUTRA_REVIEW_LANE_CMD:-$_rl_root/runtime/lib/deepseek-review.sh}"
      jq -nc --arg ts "$NOW_TS" --arg cmd "$REVIEW_CMD" '{lane:"review",status:"running",cmd:$cmd,verdict:null,ts:($ts|tonumber)}' > "$REVIEW_OUT" 2>/dev/null
      _rl_detach_review "$_RL_PROJ" "$REVIEW_CMD" "$PROMPT_FILE" "$LOG_DIR/$_RL_TURN.review.md" "$REVIEW_OUT" "$_RL_SID" "$_RL_TURN"
      _rl_row review "$(jq -nc --arg cmd "$REVIEW_CMD" '{status:"started",cmd:$cmd}')"
    fi
  fi
  return 0
}

# _rl_detach <proj> <cmd> <log> <out-json> <lane>: run the command in the
# background, fully detached from the Stop hook's process group, and write
# the result json when it finishes.
_rl_detach() {
  ( cd "$1" 2>/dev/null || exit 1
    nohup sh -c '
      out="$1"; log="$2"; cmd="$3"; root="$4"
      [ -d "$(dirname "$out")" ] || exit 0
      # test_command is the project owner'"'"'s own shell command (the sutra-test-gate
      # contract); running it as a shell command is the point
      sh -c "$cmd" > "$log" 2>&1; rc=$?
      ts=$(date +%s)
      printf "{\"lane\":\"tests\",\"status\":\"done\",\"cmd\":%s,\"exit\":%s,\"ts\":%s,\"log\":%s}\n" \
        "$(printf "%s" "$cmd" | jq -R .)" "$rc" "$ts" "$(printf "%s" "$log" | jq -R .)" > "$out.tmp" && mv -f "$out.tmp" "$out"
      # row 6 (D-A14): seal the verdict; an unsealed file is not evidence
      [ -f "$root/runtime/lib/seal.sh" ] && { . "$root/runtime/lib/seal.sh"; sutra_seal_file "$out"; } 2>/dev/null
    ' _ "$4" "$3" "$2" "$_rl_root" </dev/null >/dev/null 2>&1 &
  )
}

# _rl_detach_review <proj> <cmd> <prompt> <out-md> <out-json> <sid> <turn>
_rl_detach_review() {
  ( cd "$1" 2>/dev/null || exit 1
    nohup sh -c '
      cmd="$1"; prompt="$2"; md="$3"; out="$4"; sid="$5"; turn="$6"; proj="$7"
      [ -d "$(dirname "$out")" ] || exit 0
      # the review command is a PATH to an executable (DeepSeek round-3 P1-1: no
      # nested sh -c, so a path with spaces or metacharacters is passed as-is)
      "$cmd" "$prompt" "$md" </dev/null >/dev/null 2>&1; rc=$?
      verdict=$(grep -m1 -oE "VERDICT: *(PASS|CHANGES-REQUIRED)" "$md" 2>/dev/null | sed "s/VERDICT: *//")
      [ -n "$verdict" ] || verdict="NO-VERDICT"
      ts=$(date +%s)
      # marker first, json second: the json is what readers wait on
      if [ "$rc" -eq 0 ] && [ "$verdict" != "NO-VERDICT" ]; then
        mkdir -p "$proj/.claude/sessions/$sid" 2>/dev/null
        printf "LANE=deepseek\nVERDICT=%s\nTURN=%s\nSESSION=%s\nTS=%s\nSOURCE=runtime\n" "$verdict" "$turn" "$sid" "$ts" > "$proj/.claude/sessions/$sid/deepseek-consulted" 2>/dev/null
      fi
      printf "{\"lane\":\"review\",\"status\":\"done\",\"exit\":%s,\"verdict\":%s,\"file\":%s,\"turn\":%s,\"ts\":%s}\n" \
        "$rc" "$(printf "%s" "$verdict" | jq -R .)" "$(printf "%s" "$md" | jq -R .)" "$(printf "%s" "$turn" | jq -R .)" "$ts" > "$out.tmp" && mv -f "$out.tmp" "$out"
      # row 6 (D-A14): seal the verdict; an unsealed file is not evidence
      root="$8"; [ -f "$root/runtime/lib/seal.sh" ] && { . "$root/runtime/lib/seal.sh"; sutra_seal_file "$out"; } 2>/dev/null
    ' _ "$2" "$3" "$4" "$5" "$6" "$7" "$1" "$_rl_root" </dev/null >/dev/null 2>&1 &
  )
}

# _rl_detach_verifies <proj> <blueprint.json> <out-json> <log>: run every
# verify.cmd of the blueprint (kind cmd), detached, 120 s each, and write the
# sealed verifies file: {lane:"verifies", status:"done", results:[{n, kind, cmd,
# exit|null}], passed, failed, skipped, ts}.
_rl_detach_verifies() {
  ( cd "$1" 2>/dev/null || exit 1
    nohup sh -c '
      bp="$1"; out="$2"; log="$3"; root="$4"
      [ -d "$(dirname "$out")" ] || exit 0
      : > "$log"
      n=0; res="[]"
      jq -r ".steps[] | [(.verify.kind // \"manual\"), (.verify.cmd // \"\")] | @tsv" "$bp" 2>/dev/null | while IFS="	" read -r kind cmd; do
        n=$((n + 1))
        if [ "$kind" = "cmd" ] && [ -n "$cmd" ]; then
          printf "=== step %s: %s\n" "$n" "$cmd" >> "$log"
          ( sh -c "$cmd" >> "$log" 2>&1 ) & pid=$!
          i=0; while kill -0 "$pid" 2>/dev/null && [ $i -lt 120 ]; do sleep 1; i=$((i + 1)); done
          if kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null; rc=124; else wait "$pid"; rc=$?; fi
          printf "=== exit %s\n" "$rc" >> "$log"
          jq -nc --argjson n "$n" --arg c "$cmd" --argjson rc "$rc" "{n:\$n, kind:\"cmd\", cmd:\$c, exit:\$rc}"
        else
          jq -nc --argjson n "$n" --arg c "$cmd" "{n:\$n, kind:\"manual\", cmd:\$c, exit:null}"
        fi
      done > "$out.rows"
      ts=$(date +%s)
      jq -sc --argjson ts "$ts" "{lane:\"verifies\", status:\"done\", results:., passed:([.[] | select(.exit == 0)] | length), failed:([.[] | select(.exit != null and .exit != 0)] | length), skipped:([.[] | select(.exit == null)] | length), ts:\$ts}" "$out.rows" > "$out.tmp" 2>/dev/null && mv -f "$out.tmp" "$out"
      rm -f "$out.rows"
      [ -f "$root/runtime/lib/seal.sh" ] && { . "$root/runtime/lib/seal.sh"; sutra_seal_file "$out"; } 2>/dev/null
    ' _ "$2" "$3" "$4" "$_rl_root" </dev/null >/dev/null 2>&1 &
  )
}

_rl_row() {  # <kind-suffix> <extra-json-object>
  command -v sutra_ledger_write >/dev/null 2>&1 || return 0
  _r="$(jq -nc --arg ev "${_RL_EVENT:-Stop}" --arg t "${_RL_TURN:-unknown}" --arg s "${_RL_STEP:-stop.review_lane}" \
        --arg ts "${NOW_TS:-0}" --arg k "lane_$1" --argjson x "$2" \
    '{kind:$k, event:$ev, turn_id:$t, step_id:$s, ts:$ts} + $x' 2>/dev/null)"
  [ -n "$_r" ] || return 0
  sutra_ledger_write "${SUTRA_LEDGER_CANON:-}" "$_r"
  sutra_ledger_write "${SUTRA_LEDGER_FLAT:-}" "$_r"
}

main "$@" || true
exit 0
