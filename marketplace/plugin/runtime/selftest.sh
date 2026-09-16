#!/bin/sh
# selftest.sh - the runtime's install check.
#
# WHY. Every step in runtime/pipeline.json is a shim onto a legacy hook
# script. If one of those scripts is missing from the install, or shipped
# without its exec bit, the runtime discovers it mid-turn - as a failed step
# in a ledger nobody is reading. This file answers the question BEFORE a turn:
# is every script this pipeline promises to run actually present, executable,
# is the runtime's one hard dependency (jq) on PATH, and is the registry
# snapshot the whole kill-switch depends on still there and still in step with
# the spec?
#
# TWO WAYS IN.
#   sourced   bin/sutra-turn sources this file and calls sutra_selftest_run
#             for `sutra-turn --selftest`.
#   direct    sh runtime/selftest.sh [--root <plugin_root>] [--spec <pipeline>]
#             so the tests can point it at a fixture without a sutra-turn.
#
# WHAT ok= COUNTS. UNIQUE shim scripts, not steps: the registry registers some
# scripts more than once, so counting steps would report a script twice and
# make the number meaningless as an install check. Both numbers are DERIVED
# from the files at run time (jq over the spec and over the registry snapshot)
# and are deliberately not quoted as constants here - a number written into
# this comment is stale the next time a registration lands.
#
# hooks.json.step3 - THE FILE THE KILL-SWITCH DEPENDS ON. Once hooks.json is
# collapsed onto sutra-turn, the ONLY surviving description of what the legacy
# host used to run is hooks/hooks.json.step3. The kill-switch path
# (SUTRA_RUNTIME_DISABLED=1, ~/.sutra-runtime-disabled, a failed jq probe)
# replays that registry, spec-check.sh judges completeness and order against
# it, and validate-hook-paths.sh is the only other reader. Nothing else
# asserted the file even exists, so this check does:
#   MISSING-STEP3   the snapshot is gone           -> the kill-switch is dead
#   BAD-STEP3       the snapshot does not parse    -> the kill-switch is dead
#   STEP3-COUNT     its registration count and the spec's step count differ
#                   -> a registration was added or removed on one side only,
#                      and the collapsed registry is now lying about the fleet
# All three are fail>0, and all three are the kind of drift that is otherwise
# invisible until the day the kill-switch is pulled.
#
# RED FIXTURE. runtime/tests/mode644/ is a pipeline whose one shim is 0644.
# Pointing this file at it MUST report fail>0 - that is how we know the
# exec-bit assert is a real assert and not decoration.
#
# POSIX sh + jq. No bashisms, no GNU coreutils, no python.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/selftest.sh

# sutra_selftest_run [plugin_root] [pipeline_json]
# Prints any MISSING/NOT-EXEC/MISSING-DEP/MISSING-STEP3/BAD-STEP3/STEP3-COUNT
# detail lines, then one summary line "ok=<n> fail=<m>". Returns 0 when
# fail=0, 1 otherwise.
sutra_selftest_run() {
  _ss_root="${1:-${CLAUDE_PLUGIN_ROOT:-}}"
  if [ -z "$_ss_root" ]; then
    _ss_root="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
  fi
  _ss_spec="${2:-$_ss_root/runtime/pipeline.json}"
  _ss_ok=0
  _ss_fail=0

  # Dependency assert: jq is the runtime's only hard dependency.
  if command -v jq >/dev/null 2>&1 && printf '{}' | jq -e . >/dev/null 2>&1; then
    :
  else
    printf 'MISSING-DEP jq\n'
    _ss_fail=$((_ss_fail + 1))
    printf 'ok=%s fail=%s\n' "$_ss_ok" "$_ss_fail"
    return 1
  fi

  if [ ! -f "$_ss_spec" ]; then
    printf 'MISSING-SPEC %s\n' "$_ss_spec"
    _ss_fail=$((_ss_fail + 1))
    printf 'ok=%s fail=%s\n' "$_ss_ok" "$_ss_fail"
    return 1
  fi
  if ! jq -e . "$_ss_spec" >/dev/null 2>&1; then
    printf 'BAD-SPEC %s\n' "$_ss_spec"
    _ss_fail=$((_ss_fail + 1))
    printf 'ok=%s fail=%s\n' "$_ss_ok" "$_ss_fail"
    return 1
  fi

  # --- the registry snapshot the kill-switch replays ------------------------
  # Counts on BOTH sides are derived with jq, never compared against a literal
  # written here: pipeline.json is one step per registration, so the two
  # numbers are the same number read out of two files, and any difference is
  # drift between the spec and the snapshot.
  _ss_step3="$_ss_root/hooks/hooks.json.step3"
  if [ ! -f "$_ss_step3" ]; then
    printf 'MISSING-STEP3 %s\n' "$_ss_step3"
    _ss_fail=$((_ss_fail + 1))
  elif ! jq -e . "$_ss_step3" >/dev/null 2>&1; then
    printf 'BAD-STEP3 %s\n' "$_ss_step3"
    _ss_fail=$((_ss_fail + 1))
  else
    _ss_regs="$(jq '[.hooks[]?[]?.hooks[]?] | length' "$_ss_step3" 2>/dev/null)"
    _ss_steps="$(jq '[.events[]?[]?] | length' "$_ss_spec" 2>/dev/null)"
    case "${_ss_regs:-x}${_ss_steps:-x}" in
      *x*) printf 'STEP3-COUNT unreadable (registrations=%s steps=%s)\n' \
             "${_ss_regs:-?}" "${_ss_steps:-?}"
           _ss_fail=$((_ss_fail + 1)) ;;
      *)
        if [ "$_ss_regs" -ne "$_ss_steps" ]; then
          printf 'STEP3-COUNT %s registrations in %s vs %s steps in %s\n' \
            "$_ss_regs" "$_ss_step3" "$_ss_steps" "$_ss_spec"
          _ss_fail=$((_ss_fail + 1))
        fi ;;
    esac
  fi

  _ss_list="${TMPDIR:-/tmp}/sutra-selftest-$$-shims"
  # One line per UNIQUE shim script, path relative to the plugin root.
  jq -r '[.events[][]? | .impl // ""
          | select(startswith("shim:")) | sub("^shim:";"")]
         | unique | .[]' "$_ss_spec" 2>/dev/null > "$_ss_list"

  if [ ! -s "$_ss_list" ]; then
    printf 'NO-SHIMS %s\n' "$_ss_spec"
    rm -f "$_ss_list" 2>/dev/null || true
    _ss_fail=$((_ss_fail + 1))
    printf 'ok=%s fail=%s\n' "$_ss_ok" "$_ss_fail"
    return 1
  fi

  while IFS= read -r _ss_s; do
    [ -n "$_ss_s" ] || continue
    if [ ! -f "$_ss_root/$_ss_s" ]; then
      printf 'MISSING  %s\n' "$_ss_s"
      _ss_fail=$((_ss_fail + 1))
    elif [ ! -x "$_ss_root/$_ss_s" ]; then
      printf 'NOT-EXEC %s\n' "$_ss_s"
      _ss_fail=$((_ss_fail + 1))
    else
      _ss_ok=$((_ss_ok + 1))
    fi
  done < "$_ss_list"
  rm -f "$_ss_list" 2>/dev/null || true

  printf 'ok=%s fail=%s\n' "$_ss_ok" "$_ss_fail"
  [ "$_ss_fail" -eq 0 ]
}

# Direct invocation. When this file is sourced, $0 is the sourcing program, so
# the guard below only fires when it is run as a program itself.
case "${0##*/}" in
  selftest.sh)
    _ss_argroot=''
    _ss_argspec=''
    while [ $# -gt 0 ]; do
      case "$1" in
        --root)   _ss_argroot="${2:-}"; shift 2 ;;
        --root=*) _ss_argroot="${1#--root=}"; shift ;;
        --spec)   _ss_argspec="${2:-}"; shift 2 ;;
        --spec=*) _ss_argspec="${1#--spec=}"; shift ;;
        -h|--help)
          printf 'usage: selftest.sh [--root <plugin_root>] [--spec <pipeline.json>]\n'
          exit 0 ;;
        *)
          printf 'selftest.sh: unknown argument: %s\n' "$1" >&2
          exit 2 ;;
      esac
    done
    sutra_selftest_run "$_ss_argroot" "${_ss_argspec:-}"
    exit $?
    ;;
esac
