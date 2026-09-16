#!/bin/sh
# shim.sh - run ONE legacy bash hook exactly as the host would, and report what
# it did. Sourced by bin/sutra-turn; never executed on its own.
#
# WHY. The runtime rewrite lands in waves: on day one every registered hook is
# still the real implementation, and sutra-turn is only the thing that calls
# them. "Calls them exactly as the host did" is the whole safety argument, so
# the call itself lives in one function that can be tested against a direct
# invocation (runtime/tests/test-shim.sh).
#
# WHAT "exactly as the host would" MEANS HERE
#   - the hook is invoked directly (not through `sh -c`), so $0 is the hook's
#     own path and `dirname "$0"` still finds hooks/marker-lib.sh;
#   - it reads the SAME stdin bytes as every other step of the turn (the file
#     is re-opened per step, so one hook draining stdin cannot starve the next);
#   - the environment is inherited untouched - no scrubbing, no extra vars;
#   - the working directory is inherited untouched;
#   - a wrapper entry (hooks/lib/sutra-stderr-capture.sh <hook>) is preserved,
#     because the wrapper is part of the registration, not an implementation
#     detail.
#
# TIMEOUT. macOS has no timeout(1). The cap is a background poll: the watcher
# wakes every 50 ms, exits as soon as the hook is gone, and on expiry drops a
# flag file and SIGKILLs the hook. A killed step is reported as exit 124 with
# its measured duration, and the caller skips it - never as a silent success.
#
# POSIX sh. No bashisms, no GNU coreutils, no python.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/shim.sh

# sutra_shim_cmd_display <hook> [wrapper] -> the command line, for the ledger.
sutra_shim_cmd_display() {
  if [ -n "${2:-}" ]; then printf '%s %s' "$2" "$1"; else printf '%s' "$1"; fi
}

# sutra_shim_run <hook> <stdin_file> <stdout_file> <stderr_file> <timeout_ms> [wrapper] [tag]
# Prints "<exit> <dur_ms>" on stdout. Returns 0 always - the exit code of the
# hook is data, not a failure of the shim.
#
# <tag> disambiguates the timeout flag file. sutra-turn runs an event's steps
# CONCURRENTLY and $$ is the same in every subshell, so two steps sharing one
# hook script would otherwise share one flag and each could read the other's
# timeout as its own. The caller passes the step's seq; callers that run one
# hook at a time may omit it.
sutra_shim_run() {
  _sr_hook="$1"; _sr_in="$2"; _sr_out="$3"; _sr_err="$4"; _sr_ms="$5"
  _sr_wrap="${6:-}"; _sr_tag="${7:-0}"

  : > "$_sr_out" 2>/dev/null || true
  : > "$_sr_err" 2>/dev/null || true

  # SUTRA_STEP_TIMEOUT_SCALE - integer percent, default 100, CLAMPED TO >= 100
  # so it can only ever lengthen a budget, never shorten one (a knob that could
  # tighten a cap would be a way to silence a governance hook). The per-step
  # budget is a wall-clock cap on a hook that normally finishes in a fraction of
  # it; a harness that deliberately oversubscribes the machine - the parity
  # replayer at --jobs N, a shared CI runner - can raise it so scheduler latency
  # is not mistaken for a hung hook.
  _sr_scale="${SUTRA_STEP_TIMEOUT_SCALE:-100}"
  case "$_sr_scale" in ''|*[!0-9]*) _sr_scale=100 ;; esac
  [ "$_sr_scale" -lt 100 ] && _sr_scale=100
  _sr_ms=$(( ${_sr_ms:-5000} * _sr_scale / 100 ))
  [ "$_sr_ms" -lt 1 ] && _sr_ms=1

  if [ ! -e "$_sr_hook" ]; then
    printf 'sutra-turn: missing hook: %s\n' "$_sr_hook" >> "$_sr_err"
    printf '%s %s' 127 0
    return 0
  fi

  _sr_t0="$(sutra_now_ms)"

  if [ -n "$_sr_wrap" ]; then
    "$_sr_wrap" "$_sr_hook" < "$_sr_in" > "$_sr_out" 2> "$_sr_err" &
  else
    "$_sr_hook" < "$_sr_in" > "$_sr_out" 2> "$_sr_err" &
  fi
  _sr_pid=$!

  # The timeout flag is named after the HOOK'S OWN pid, not just $$ and the
  # step's tag. $$ is the same in every concurrently spawned step AND is reused
  # by the next sutra-turn the host starts; a watcher left over from a finished
  # run could therefore drop its flag where a later run's step was about to look
  # for it and report a phantom 124. A live pid is unique on the machine.
  #
  # IT ALSO LIVES INSIDE THE RUN'S OWN TEMP DIRECTORY when there is one. Written
  # straight into $TMPDIR it outlived a killed run: sutra-turn's cleanup trap
  # removes $TMPROOT and nothing else, so a SIGKILLed step left a sutra-shim-to-*
  # file in the shared temp root for ever. TMPROOT/TMPOWNED are sutra-turn's
  # globals (this file is SOURCED, never executed), so a standalone caller -
  # runtime/tests/test-shim.sh - still gets the TMPDIR path.
  if [ "${TMPOWNED:-0}" = "1" ] && [ -n "${TMPROOT:-}" ]; then
    _sr_flagdir="$TMPROOT"
  else
    _sr_flagdir="${TMPDIR:-/tmp}"
  fi
  _sr_flag="$_sr_flagdir/sutra-shim-to-$$-$_sr_tag-$_sr_pid-$(printf '%s' "$_sr_hook" | tr -c 'A-Za-z0-9' '-' | tail -c 32)"
  rm -f "$_sr_flag" 2>/dev/null || true

  # DEADLINE, not ticks. Counting N sleeps of 50 ms makes the effective cap
  # dilate under load: every tick forks /bin/sleep, and on a loaded box each
  # 50 ms tick cost far more, so a 600 ms budget on a 5 s hook was measured
  # holding the event for 3477 ms. The watcher now computes an absolute
  # deadline from the same clock the duration is measured with and re-reads it
  # every wake, so a slow scheduler can overshoot by at most one 50 ms nap.
  # It self-exits the moment the hook is gone, so it is never killed and never
  # prints a job-control notice.
  # The nap is a quarter of what is left (floor 50 ms, ceiling 250 ms), so the
  # clock is read a handful of times per step instead of twenty times a second,
  # and the granularity tightens to 50 ms as the deadline approaches.
  _sr_dead=$(( _sr_t0 + ${_sr_ms:-5000} ))
  (
    while :; do
      kill -0 "$_sr_pid" 2>/dev/null || exit 0
      _rem=$(( _sr_dead - $(sutra_now_ms) ))
      [ "$_rem" -le 0 ] && break
      _nap=$(( _rem / 4 ))
      [ "$_nap" -gt 250 ] && _nap=250
      [ "$_nap" -lt 50 ] && _nap=50
      [ "$_nap" -gt "$_rem" ] && _nap="$_rem"
      sleep "$(printf '%d.%03d' $(( _nap / 1000 )) $(( _nap % 1000 )))"
    done
    kill -0 "$_sr_pid" 2>/dev/null || exit 0
    : > "$_sr_flag" 2>/dev/null
    kill -9 "$_sr_pid" 2>/dev/null
    exit 0
  ) >/dev/null 2>&1 &
  _sr_wpid=$!

  wait "$_sr_pid"
  _sr_rc=$?
  # Stop the watcher the moment the hook is done. Left to notice by itself it
  # can nap for another tick past the end of this run - long enough, on a box
  # spawning thousands of hook processes, for the pid it is watching to be
  # recycled under it.
  kill "$_sr_wpid" 2>/dev/null || true
  _sr_t1="$(sutra_now_ms)"
  _sr_dur=$(( _sr_t1 - _sr_t0 ))
  [ "$_sr_dur" -lt 0 ] && _sr_dur=0

  if [ -f "$_sr_flag" ]; then
    _sr_rc=124
    rm -f "$_sr_flag" 2>/dev/null || true
  fi

  printf '%s %s' "$_sr_rc" "$_sr_dur"
  return 0
}

# sutra_shim_legacy_run <hook> <stdin_file> [wrapper]
# The kill-switch / degraded path: run the hook with the host's own plumbing -
# stdout and stderr pass straight through to sutra-turn's own streams, nothing
# is captured, nothing is merged. Prints nothing; returns the hook's exit code.
sutra_shim_legacy_run() {
  _slr_hook="$1"; _slr_in="$2"; _slr_wrap="${3:-}"
  [ -e "$_slr_hook" ] || return 0
  if [ -n "$_slr_wrap" ]; then
    "$_slr_wrap" "$_slr_hook" < "$_slr_in"
  else
    "$_slr_hook" < "$_slr_in"
  fi
  return $?
}
