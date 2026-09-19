#!/usr/bin/env bash
# artifact.sh - typed-artifact validation for the adherence step ledger
# (Sutra Runtime, adherence row 1, brief D-A3 + D-A8).
#
# An artifact is a JSON file the model writes for a judgment step. The
# runtime never trusts its content as evidence of substance (ADR-040); it
# checks shape, identity and the minimum constraints that make a hollow
# file mechanically detectable (codex P1-3, DeepSeek P2-4, 2026-09-16):
#
#   common   turn_id == current turn, session_id == sid, producer == "model",
#            step == <kind>, unit is a string >= 10 chars,
#            ts is a number >= the ledger's opened_ts (a re-hashed identical
#            prompt cannot reuse an older turn's artifact - DeepSeek P1-2)
#   lens     axes[] and pick[] non-empty arrays of strings >= 3 chars,
#            pick is a subset of axes, direction in DOWN|UP|ACROSS
#   cynefin  domain in clear|complicated|complex|chaotic, shape string
#            >= 20 chars, human_gate boolean
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/artifact.sh

# sutra_artifact_check <file> <kind> <turn_id> <sid> <opened_ts>
#   prints "ok" and returns 0, or prints one reason and returns 1.
sutra_artifact_check() {
  _ac_file="$1"; _ac_kind="$2"; _ac_turn="$3"; _ac_sid="$4"; _ac_opened="${5:-0}"
  case "$_ac_opened" in ''|*[!0-9]*) _ac_opened=0 ;; esac
  if [ ! -f "$_ac_file" ]; then
    printf 'missing'
    return 1
  fi
  _ac_depth="${SUTRA_ARTIFACT_DEPTH:-0}"; case "$_ac_depth" in ''|*[!0-9]*) _ac_depth=0 ;; esac
  _ac_out="$(jq -r --arg kind "$_ac_kind" --arg turn "$_ac_turn" --arg sid "$_ac_sid" --argjson opened "$_ac_opened" --argjson depth "$_ac_depth" '
    def trim: if type == "string" then gsub("^[[:space:]]+|[[:space:]]+$"; "") else . end;
    def str(n): (type == "string") and ((trim | length) >= n);
    def strarr(n): (type == "array") and (length >= 1) and (all(.[]; str(n)));
    if (type != "object") then "not-an-object"
    elif (.turn_id != $turn) then "stale-turn (turn_id must be \($turn))"
    elif (.session_id != $sid) then "wrong-session"
    elif (.producer != "model") then "producer-must-be-model"
    elif (.step != $kind) then "step-must-be-\($kind)"
    elif ((.unit | str(10)) | not) then "unit-under-10-chars"
    elif ((.ts | type) != "number") then "ts-missing"
    elif (.ts < $opened) then "ts-before-turn-open (ts must be >= \($opened))"
    elif ($kind == "lens") then
      if ((.axes | strarr(3)) | not) then "axes-empty-or-short"
      elif ((.pick | strarr(3)) | not) then "pick-empty-or-short"
      elif (((.pick | map(trim)) - (.axes | map(trim))) | length) > 0 then "pick-not-subset-of-axes"
      elif ((.direction // "") | trim | IN("DOWN","UP","ACROSS") | not) then "direction-not-DOWN-UP-ACROSS"
      else "ok" end
    elif ($kind == "cynefin") then
      if ((.domain // "") | trim | IN("clear","complicated","complex","chaotic") | not) then "domain-not-clear-complicated-complex-chaotic"
      elif ((.shape | str(20)) | not) then "shape-under-20-chars"
      elif ((.human_gate | type) != "boolean") then "human_gate-not-boolean"
      else "ok" end
    # row 6 (brief s3.3): blueprint - steps with runnable verifies; the word
    # list is a first filter, the runtime running the cmd at Stop is the test
    elif ($kind == "blueprint") then
      # the word list is a first filter (DeepSeek row-6 bypass 2 added the shell
      # no-ops); the real test is the runtime running the cmd at Stop and the
      # reviewer reading what it checked
      def trivial: (tostring | ascii_downcase | trim) as $t | ($t | IN("", "works", "passes", "done", "no errors", "it runs", "ok", "success", "manual", "check", "verify", "test", "true", "false", ":", "exit 0", "exit", "echo ok", "echo done", "echo", "test -z \"$(true)\"", "test 1", "[ 1 ]", "[ 0 ]") or ($t | test("^(true|false|:|exit [0-9]+|echo .*|\\[ +\\]|test( +-[a-z])? *)$")));
      def vok: (type == "object") and ((.kind // "") | IN("cmd","manual")) and (if .kind == "cmd" then ((.cmd | str(3)) and ((.cmd | trivial) | not)) else true end);
      if ((.doing | str(10)) | not) then "doing-under-10-chars"
      elif ((.steps | type) != "array" or (.steps | length) < 1) then "steps-empty"
      elif ((.steps | all(.[]; (type == "object") and (.do | str(5)) and (.verify | vok))) | not) then "step-verify-not-cmd-or-manual"
      elif ($depth >= 3 and ((.steps | all(.[]; .verify.kind == "cmd")) | not)) then "verify-must-be-cmd-at-depth-3-plus"
      elif ((.output | str(10)) | not) then "output-under-10-chars"
      elif ((.verified_by | vok) | not) then "verified_by-not-cmd-or-manual"
      elif ((.stops_if | str(5)) | not) then "stops_if-under-5-chars"
      else "ok" end
    elif ($kind == "build_layer") then
      if ((.layer // "") | trim | IN("L1","L2") | not) then "layer-not-L1-L2"
      elif ((.target_path | str(3)) | not) then "target_path-missing"
      elif (.layer == "L1" and (((.promote_to | str(3)) and (.owner | str(3)) and (.acceptance | str(10)) and ((.promote_by // "") | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))) | not)) then "L1-needs-promote_to-promote_by-owner-acceptance"
      elif (.layer == "L2" and ((((.why_not_l0_kind // "") | trim) == "instance-only") and (.why_not_l0_reason | str(10)) | not)) then "L2-needs-why_not_l0_kind-instance-only-and-reason"
      else "ok" end
    elif ($kind == "placement") then
      if (((.domain_ref // "") | test("^dref-[0-9a-f]{8,}$")) | not) then "domain_ref-not-dref"
      elif (((.charter_id // "") | test("^C-[0-9a-f]{8,}$")) | not) then "charter_id-not-C"
      elif ((.reason | str(10)) | not) then "reason-under-10-chars"
      elif ((.confidence | type) != "number" or .confidence < 0 or .confidence > 1) then "confidence-not-0-to-1"
      else "ok" end
    elif ($kind == "depth") then
      if ((.depth | type) != "number" or .depth < 1 or .depth > 5 or (.depth | floor) != .depth) then "depth-not-1-to-5"
      elif ((.reason | str(10)) | not) then "reason-under-10-chars"
      else "ok" end
    else "unknown-kind" end
  ' "$_ac_file" 2>/dev/null)"
  if [ -z "$_ac_out" ]; then
    printf 'unparseable'
    return 1
  fi
  printf '%s' "$_ac_out"
  [ "$_ac_out" = "ok" ]
}
