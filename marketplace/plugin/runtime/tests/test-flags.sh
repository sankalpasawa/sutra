#!/usr/bin/env bash
# test-flags.sh - runtime/flags.sh: sutra_flag_markers resolves the D1 marker
# flag into SUTRA_MARKERS_MODE and SUTRA_MARKERS_SOURCE.
#
# PRECEDENCE UNDER TEST (BRIEF.md D1, section 4 cases F1-F6):
#   ~/.sutra-runtime-markers-disabled   beats everything -> off / disabled
#   SUTRA_RUNTIME_MARKERS (env)         beats the file    -> <value> / env
#   ~/.sutra-runtime-markers (file)     one line on|shadow|off
#   absent                              -> off / default
#   any other value (file or env)       -> off / invalid
#   HOME unset or empty                 -> off / no-home, NEVER a crash, and
#                                          per D1 no filesystem read at all
#
#   F1 absent                       -> off / default
#   F2 file "on"                    -> on / file
#   F3 file "shadow"                -> shadow / file
#   F4 file "bogus"                 -> off / invalid
#   F5 env "off" beats file "on"    -> off / env
#   F6 disabled file beats env "on" -> off / disabled
# Plus two supplementary cases (not brief-numbered; D1's own no-crash clause,
# and the review lens question "a $HOME unset?"): HOME entirely unset, and
# HOME explicitly set to the empty string.
#
# Each case runs in a FRESH `env -i` child (PATH plus exactly the one
# HOME/SUTRA_RUNTIME_MARKERS this case sets) so nothing this test harness
# itself is running under - including any real ~/.sutra-runtime-markers on
# the developer's machine - can leak into a result.
#
# bash 3.2 compatible: no associative arrays, no ${var,,}, no mapfile.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-flags.sh

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
FLAGS="$PLUGIN_ROOT/runtime/flags.sh"

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }
is() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1: expected [$3] got [$2]"; fi; }

if ! command -v jq >/dev/null 2>&1; then
  fail "jq required to run this test"
  echo "failed=$failed"
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/sutra-test-flags.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f "$FLAGS" ]; then
  fail "runtime/flags.sh does not exist yet at $FLAGS (step lane not landed; every case below is contract-only)"
  echo "failed=$failed"
  exit 1
fi

if bash -n "$FLAGS" 2>"$WORK/bashsyn.err"; then
  pass "runtime/flags.sh parses clean under bash -n"
else
  fail "runtime/flags.sh fails bash -n: $(cat "$WORK/bashsyn.err")"
fi
if sh -n "$FLAGS" 2>"$WORK/shsyn.err"; then
  pass "runtime/flags.sh parses clean under sh -n (Rule: sourced by sh and bash alike)"
else
  fail "runtime/flags.sh fails sh -n: $(cat "$WORK/shsyn.err")"
fi

# probe.sh: sources flags.sh, calls sutra_flag_markers, prints MODE then
# SOURCE on their own lines. Written once, reused by every case and by both
# the bash and the sh probe below it.
cat > "$WORK/probe.sh" <<PROBE
. "$FLAGS"
sutra_flag_markers
printf '%s\n%s\n' "\${SUTRA_MARKERS_MODE:-<unset>}" "\${SUTRA_MARKERS_SOURCE:-<unset>}"
PROBE

# run_flag_case <label> <home|UNSET> <env_value_or_empty>
# HOME="UNSET" means HOME is absent from the child's environment entirely
# (env -i with no HOME= assignment at all); HOME="" means HOME is present
# and explicitly empty. Sets MODE and SOURCE.
run_flag_case() {
  _lbl="$1"; _home="$2"; _envval="$3"
  if [ "$_home" = "UNSET" ]; then
    if [ -n "$_envval" ]; then
      OUT="$(env -i PATH="$PATH" SUTRA_RUNTIME_MARKERS="$_envval" bash "$WORK/probe.sh" 2>"$WORK/$_lbl.err")"
    else
      OUT="$(env -i PATH="$PATH" bash "$WORK/probe.sh" 2>"$WORK/$_lbl.err")"
    fi
  else
    if [ -n "$_envval" ]; then
      OUT="$(env -i PATH="$PATH" HOME="$_home" SUTRA_RUNTIME_MARKERS="$_envval" bash "$WORK/probe.sh" 2>"$WORK/$_lbl.err")"
    else
      OUT="$(env -i PATH="$PATH" HOME="$_home" bash "$WORK/probe.sh" 2>"$WORK/$_lbl.err")"
    fi
  fi
  RC=$?
  MODE="$(printf '%s\n' "$OUT" | sed -n '1p')"
  SOURCE="$(printf '%s\n' "$OUT" | sed -n '2p')"
  if [ -s "$WORK/$_lbl.err" ]; then
    fail "$_lbl: sutra_flag_markers wrote to stderr: $(cat "$WORK/$_lbl.err")"
  fi
  if [ "$RC" -ne 0 ]; then
    fail "$_lbl: probe exited $RC (want 0 - the flag resolver must never itself fail the turn)"
  fi
}

# ---------------------------------------------------------------------- F1 --
mkdir -p "$WORK/home1"
run_flag_case F1 "$WORK/home1" ""
is "F1 mode: flag absent -> off" "$MODE" "off"
is "F1 source: flag absent -> default" "$SOURCE" "default"

# ---------------------------------------------------------------------- F2 --
mkdir -p "$WORK/home2"
printf 'on\n' > "$WORK/home2/.sutra-runtime-markers"
run_flag_case F2 "$WORK/home2" ""
is "F2 mode: file 'on' -> on" "$MODE" "on"
is "F2 source: file 'on' -> file" "$SOURCE" "file"

# ---------------------------------------------------------------------- F3 --
mkdir -p "$WORK/home3"
printf 'shadow\n' > "$WORK/home3/.sutra-runtime-markers"
run_flag_case F3 "$WORK/home3" ""
is "F3 mode: file 'shadow' -> shadow" "$MODE" "shadow"
is "F3 source: file 'shadow' -> file" "$SOURCE" "file"

# ---------------------------------------------------------------------- F4 --
mkdir -p "$WORK/home4"
printf 'bogus\n' > "$WORK/home4/.sutra-runtime-markers"
run_flag_case F4 "$WORK/home4" ""
is "F4 mode: file 'bogus' -> off" "$MODE" "off"
is "F4 source: file 'bogus' -> invalid" "$SOURCE" "invalid"

# ---------------------------------------------------------------------- F5 --
mkdir -p "$WORK/home5"
printf 'on\n' > "$WORK/home5/.sutra-runtime-markers"
run_flag_case F5 "$WORK/home5" "off"
is "F5 mode: env 'off' beats file 'on' -> off" "$MODE" "off"
is "F5 source: env 'off' beats file 'on' -> env" "$SOURCE" "env"

# ---------------------------------------------------------------------- F6 --
mkdir -p "$WORK/home6"
: > "$WORK/home6/.sutra-runtime-markers-disabled"
run_flag_case F6 "$WORK/home6" "on"
is "F6 mode: disabled file beats env 'on' -> off" "$MODE" "off"
is "F6 source: disabled file beats env 'on' -> disabled" "$SOURCE" "disabled"

# -------------------------------------------------------- extra: no crash --
# Not brief-numbered; D1's own clause ("HOME unset or empty = off with
# source no-home, never a crash") and the portability review lens ("A $HOME
# unset?"). Kept separate from F1-F6 so a mismatch here never reads as a
# missed brief case.
run_flag_case HOME-UNSET "UNSET" ""
is "extra: HOME entirely unset -> off" "$MODE" "off"
is "extra: HOME entirely unset -> no-home" "$SOURCE" "no-home"

run_flag_case HOME-EMPTY "" ""
is "extra: HOME explicitly empty -> off" "$MODE" "off"
is "extra: HOME explicitly empty -> no-home" "$SOURCE" "no-home"

# -------------------------------------- extra: sourceable under sh(1) too --
# Rule (BRIEF.md line 11): flags.sh is "sourced by sh and bash alike". Prove
# it dynamically, not only via sh -n, by re-running the F2 case under sh.
cat > "$WORK/probe-sh.sh" <<PROBE
#!/bin/sh
. "$FLAGS"
sutra_flag_markers
printf '%s\n%s\n' "\${SUTRA_MARKERS_MODE:-<unset>}" "\${SUTRA_MARKERS_SOURCE:-<unset>}"
PROBE
OUTSH="$(env -i PATH="$PATH" HOME="$WORK/home2" sh "$WORK/probe-sh.sh" 2>"$WORK/shsource.err")"
MODESH="$(printf '%s\n' "$OUTSH" | sed -n '1p')"
SOURCESH="$(printf '%s\n' "$OUTSH" | sed -n '2p')"
if [ -s "$WORK/shsource.err" ]; then
  fail "extra: sh(1)-sourced flags.sh wrote to stderr: $(cat "$WORK/shsource.err")"
fi
is "extra: flags.sh sourced under sh(1), F2 mode still on" "$MODESH" "on"
is "extra: flags.sh sourced under sh(1), F2 source still file" "$SOURCESH" "file"

echo "failed=$failed"
[ "$failed" -eq 0 ]
