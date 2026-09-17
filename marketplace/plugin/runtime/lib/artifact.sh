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
  _ac_out="$(jq -r --arg kind "$_ac_kind" --arg turn "$_ac_turn" --arg sid "$_ac_sid" --argjson opened "$_ac_opened" '
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
    else "unknown-kind" end
  ' "$_ac_file" 2>/dev/null)"
  if [ -z "$_ac_out" ]; then
    printf 'unparseable'
    return 1
  fi
  printf '%s' "$_ac_out"
  [ "$_ac_out" = "ok" ]
}
