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

# 2.285.1 (brief ADHERENCE-ROW6 s3.6, workflow P1-1): the runtime's own switches
# (SUTRA_RUNTIME_MARKERS, SUTRA_RUNTIME_ADHERENCE, SUTRA_RUNTIME_DISABLED) are NOT
# override keys. The founder sets them by writing the flag files in a terminal;
# through this file one Write from inside a session could switch the gate off.
SUTRA_OVERRIDE_KEYS="CODEX_CONSULT_ACK CODEX_CONSULT_ACK_REASON BLUEPRINT_ACK BLUEPRINT_ACK_REASON FLOW_ACK FLOW_ACK_REASON PER_TURN_HARD_ACK PER_TURN_HARD_ACK_REASON BUILD_LAYER_ACK BUILD_LAYER_ACK_REASON STRUCTURE_FIRST_ACK STRUCTURE_FIRST_ACK_REASON PROTO005_ACK RTK_SKIP SUTRA_TEST_GATE_ACK SUTRA_STEP_TIMEOUT_SCALE DISPATCH_FOUNDER_APPROVAL"

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
  # 2.285.1 (brief s3.6, D-A15): the file is honoured only when it predates the
  # session. The FIRST event of a session stamps <proj>/.sutra/turn/<sid>/opened
  # whether or not an override file exists yet (workflow wf_1dc20d5c P1-2: a
  # file that appears mid-session must be newer than the stamp); the stamp is
  # a runtime-owned path the gate refuses to every tool. A file modified after
  # the stamp is ignored for the whole session, with a ledger note and an
  # audit row. Overrides therefore take effect on the NEXT session.
  _so_stamp=""
  if [ -n "${1:-}" ] && [ -n "${2:-}" ] && [ -d "$1" ]; then
    _so_dir="$1/.sutra/turn/$2"; _so_stamp="$_so_dir/opened"
    if [ ! -f "$_so_stamp" ]; then
      mkdir -p "$_so_dir" 2>/dev/null
      { date +%s > "$_so_stamp"; } 2>/dev/null
    fi
  fi
  [ -f "$_so_file" ] || return 0
  if [ -n "$_so_stamp" ]; then
    _so_open="$(cat "$_so_stamp" 2>/dev/null)"; case "$_so_open" in ''|*[!0-9]*) _so_open=0 ;; esac
    # An unreadable or zero stamp fails closed (DeepSeek 2.285.1 P1-3): it is
    # re-stamped with now and the file is ignored for this event.
    if [ "$_so_open" -le 0 ]; then
      _so_open="$(date +%s 2>/dev/null)"; case "$_so_open" in ''|*[!0-9]*) _so_open=1 ;; esac
      { printf '%s\n' "$_so_open" > "$_so_stamp"; } 2>/dev/null
      _so_mt=$((_so_open + 1))
    else
      _so_mt="$(stat -f %m "$_so_file" 2>/dev/null || stat -c %Y "$_so_file" 2>/dev/null)"; case "$_so_mt" in ''|*[!0-9]*) _so_mt=$((_so_open + 1)) ;; esac
    fi
    if [ "$_so_mt" -gt "$_so_open" ]; then
      command -v sutra_ledger_note >/dev/null 2>&1 && sutra_ledger_note override_ignored "written inside the session (mtime $_so_mt > opened $_so_open): $_so_file"
      mkdir -p "$1/.enforcement" 2>/dev/null
      _so_ts="$(date +%s 2>/dev/null)"; case "$_so_ts" in ''|*[!0-9]*) _so_ts=0 ;; esac
      { printf '{"ts":%s,"session":"%s","file":"%s","keys":"","ignored":true,"mtime":%s,"opened":%s}\n' "$_so_ts" "$(printf '%s' "$2" | tr -cd 'A-Za-z0-9_-')" "$(printf '%s' "$_so_file" | tr -d '"\\')" "$_so_mt" "$_so_open" >> "$1/.enforcement/overrides.jsonl"; } 2>/dev/null
      return 0
    fi
  fi
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
