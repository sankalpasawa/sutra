#!/bin/sh
# overrides.sh - the ONE override file (adherence row 4, 2026-09-17).
#
# ~/.sutra-overrides, KEY=VALUE per line, '#' comments. Every governance gate
# used to have its own ACK env var and reason var; a founder could not see in
# one place what was switched off. This file is that place. sutra-turn applies
# it once per event before step 0: each whitelisted KEY is exported for the
# run unless the environment already carries it (an explicit env var wins),
# one ledger row names the keys applied, and one audit row lands in
# <project>/.enforcement/overrides.jsonl. Nothing here can grant more than the
# env var could: the gates keep their own audit rows and reason checks.
#
# POSIX sh (sourced by bin/sutra-turn, which is sh). No file is read when HOME
# is unset (hermetic / corpus runs).
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/overrides.sh

SUTRA_OVERRIDE_KEYS="CODEX_CONSULT_ACK CODEX_CONSULT_ACK_REASON BLUEPRINT_ACK BLUEPRINT_ACK_REASON FLOW_ACK FLOW_ACK_REASON PER_TURN_HARD_ACK PER_TURN_HARD_ACK_REASON BUILD_LAYER_ACK BUILD_LAYER_ACK_REASON STRUCTURE_FIRST_ACK STRUCTURE_FIRST_ACK_REASON PROTO005_ACK RTK_SKIP SUTRA_TEST_GATE_ACK SUTRA_RUNTIME_MARKERS SUTRA_RUNTIME_ADHERENCE SUTRA_RUNTIME_DISABLED SUTRA_STEP_TIMEOUT_SCALE DISPATCH_FOUNDER_APPROVAL"

# sutra_overrides_path -> prints the file path, or nothing when HOME is unset.
sutra_overrides_path() {
  [ -n "${HOME:-}" ] || return 1
  printf '%s/.sutra-overrides' "$HOME"
}

# sutra_overrides_apply <project_dir> <session_id>: export the whitelisted
# keys, write the rows. Sets SUTRA_OVERRIDES_APPLIED to the space-joined keys.
sutra_overrides_apply() {
  SUTRA_OVERRIDES_APPLIED=""
  _so_file="$(sutra_overrides_path 2>/dev/null)" || return 0
  [ -f "$_so_file" ] || return 0
  _so_keys=""
  while IFS= read -r _so_line || [ -n "$_so_line" ]; do
    case "$_so_line" in ''|'#'*) continue ;; esac
    _so_key="${_so_line%%=*}"
    _so_val="${_so_line#*=}"
    [ "$_so_key" = "$_so_line" ] && continue          # no '='
    _so_key="$(printf '%s' "$_so_key" | tr -d '[:space:]')"
    _so_val="$(printf '%s' "$_so_val" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case " $SUTRA_OVERRIDE_KEYS " in
      *" $_so_key "*) ;;
      *) continue ;;                                   # not a known override: ignored, never exported
    esac
    # An explicit environment variable wins over the file. The key is
    # whitelisted above, so the eval only ever expands a known name; the value
    # is never evaluated (export KEY=VALUE, DeepSeek round-3 P1-5).
    if eval "[ -n \"\${$_so_key:-}\" ]"; then continue; fi
    export "$_so_key=$_so_val"
    _so_keys="$_so_keys $_so_key"
  done < "$_so_file"
  _so_keys="${_so_keys# }"
  [ -n "$_so_keys" ] || return 0
  SUTRA_OVERRIDES_APPLIED="$_so_keys"
  command -v sutra_ledger_note >/dev/null 2>&1 && sutra_ledger_note override_file "applied from $_so_file: $_so_keys"
  if [ -n "${1:-}" ] && [ -d "$1" ]; then
    mkdir -p "$1/.enforcement" 2>/dev/null
    _so_ts="$(date +%s 2>/dev/null)"; case "$_so_ts" in ''|*[!0-9]*) _so_ts=0 ;; esac
    if command -v jq >/dev/null 2>&1; then
      _so_row="$(jq -nc --argjson ts "$_so_ts" --arg s "${2:-}" --arg f "$_so_file" --arg k "$_so_keys" '{ts:$ts,session:$s,file:$f,keys:$k}' 2>/dev/null)"
    else
      _so_row="$(printf '{"ts":%s,"session":"%s","file":"%s","keys":"%s"}' "$_so_ts" "$(printf '%s' "${2:-}" | tr -cd 'A-Za-z0-9_-')" "$(printf '%s' "$_so_file" | tr -d '"\\')" "$_so_keys")"
    fi
    { printf '%s\n' "$_so_row" >> "$1/.enforcement/overrides.jsonl"; } 2>/dev/null
  fi
  return 0
}
