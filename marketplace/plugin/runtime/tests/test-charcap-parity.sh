#!/bin/bash
# test-charcap-parity.sh - the golden-parity prover, as a discovered suite.
#
# WHY THIS FILE EXISTS. sutra-charcap records what the legacy bash fleet does
# and replays it against sutra-turn; "the runtime is a drop-in replacement" is
# that comparison and nothing else. Until this file landed, nothing RAN it:
# tests/run-all.sh discovered no suite that called sutra-charcap and the
# release-gate workflow never invoked it, so the one prover of the whole
# rewrite gated exactly nothing. A prover nobody runs is a claim, not a test.
#
# WHAT IT ASSERTS.
#   legacy      `sutra-charcap verify --all --runner legacy --jobs 4`
#               the corpus still describes the bash fleet as it is today - a
#               hook edited without re-recording fails HERE, before parity is
#               blamed on the runtime.
#   sutra-turn  `sutra-charcap verify --all --runner sutra-turn --jobs 2` (SUTRA_CHARCAP_TURN_JOBS)
#               the runtime reproduces that corpus byte for byte, per step and
#               in the combined emit.
# Both summary blocks are printed whatever happens; the suite exits non-zero if
# either runner fails, and names which one.
#
# ISOLATION. Each run gets its own SUTRA_CHARCAP_WORK (mktemp -d, removed on
# exit). charcap locks its work dir for the run precisely because a shared dir
# makes two concurrent runs delete each other's fresh roots and invent FAILs -
# under run-all.sh and in CI this suite can be running next to anything, so it
# never borrows the default or a sibling's dir.
#
# NO CORPUS, NO OPINION. On a checkout without hooks/tests/golden (a fresh
# clone before step 7, a trimmed install) this prints "skip: no golden corpus"
# and exits 0 rather than reporting a parity failure it cannot measure.
#
# WRONG PLATFORM, NO OPINION EITHER. The corpus is macOS-recorded (BSD tools,
# /tmp -> /private/tmp, bash 3.2) and families.json says so in `recorded_on`. On
# a box whose `uname -s` differs this prints "skip: corpus recorded on <X>, this
# box is <Y>" and exits 0 - a platform diff is not a parity finding. The release
# gate pins its parity STEP to macOS; this guard covers every other caller
# (a Linux dev box, a fleet machine running tests/run-all.sh --set runtime).
#
# SUTRA_CHARCAP_PARITY_SKIP=1 skips the run and says so on stdout. It exists
# for ONE caller: the release gate runs this suite as its own named step and
# then runs tests/run-all.sh, which discovers this file too - replaying the
# whole corpus against both runners twice would double the longest job in CI
# for no new information. Every skip prints a line; a silent skip would make
# "the gate is green" unreadable.
#
# bash 3.2 compatible: no mapfile, no associative arrays. Depends on what
# charcap depends on: jq, perl, shasum.
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/tests/test-charcap-parity.sh

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
# runtime/tests/<this file> -> the plugin root is two levels up.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$HERE/../.." && pwd)}"
export CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT"

CHARCAP="$PLUGIN_ROOT/bin/sutra-charcap"
GOLDEN="${SUTRA_CHARCAP_GOLDEN:-$PLUGIN_ROOT/hooks/tests/golden}"
JOBS="${SUTRA_CHARCAP_JOBS:-4}"
# The runtime leg runs every step of an event concurrently (as the host does), so
# N parallel cases mean up to N x 29 hook processes; at 8 the box misses the hooks'
# own 3-5 s timeouts and reports spurious exit-124 diffs. 2 is green without any
# timeout scaling and finishes all 9 families in about 6 minutes.
TURN_JOBS="${SUTRA_CHARCAP_TURN_JOBS:-2}"

failed=0
fail() { echo "FAIL: $*"; failed=$((failed + 1)); }
pass() { echo "ok: $*"; }

if [ "${SUTRA_CHARCAP_PARITY_SKIP:-0}" = "1" ]; then
  echo "skip: parity suite disabled by SUTRA_CHARCAP_PARITY_SKIP=1"
  echo "  (the caller is expected to have run it as its own step)"
  echo "failed=0"
  exit 0
fi

if [ ! -d "$GOLDEN" ]; then
  echo "skip: no golden corpus"
  echo "  (looked in $GOLDEN)"
  echo "failed=0"
  exit 0
fi

# WRONG PLATFORM, NO OPINION. The corpus carries BSD-tool bytes, macOS path
# resolution (/tmp -> /private/tmp) and bash-3.2 behaviour; families.json records
# the recording box's `uname -s` in `recorded_on` for exactly this reason.
# Replaying it on a box of another kind compares two platforms, not two runners,
# and prints a wall of diffs that says nothing about parity. The release gate
# pins the parity step to macOS, but a Linux dev box or a fleet machine running
# `tests/run-all.sh --set runtime` has no such pin - so the suite carries the
# guard itself and skips, the same shape as the two skips above.
# An absent or empty `recorded_on` (a corpus recorded before the field existed)
# is not a mismatch: the suite runs, as it always did.
CORPUS_OS=""
if [ -f "$GOLDEN/families.json" ] && command -v jq >/dev/null 2>&1; then
  CORPUS_OS="$(jq -r '.recorded_on // empty' "$GOLDEN/families.json" 2>/dev/null)"
  [ "$CORPUS_OS" = "null" ] && CORPUS_OS=""
fi
HOST_OS="$(uname -s 2>/dev/null || echo unknown)"
if [ -n "$CORPUS_OS" ] && [ "$CORPUS_OS" != "$HOST_OS" ]; then
  echo "skip: corpus recorded on $CORPUS_OS, this box is $HOST_OS"
  echo "  (the expectations carry $CORPUS_OS tool output; replaying them here would"
  echo "   diff on platform, not on parity - re-record on this platform to compare)"
  echo "failed=0"
  exit 0
fi

if [ ! -x "$CHARCAP" ]; then
  fail "sutra-charcap missing or not executable at $CHARCAP"
  echo "failed=$failed"
  exit 1
fi

WORKBASE="$(mktemp -d "${TMPDIR:-/tmp}/sutra-charcap-parity.XXXXXX")" || {
  echo "FAIL: cannot create a work dir"; echo "failed=1"; exit 1
}
trap 'rm -rf "$WORKBASE"' EXIT

run_runner() {  # <runner label>
  _r="$1"
  _w="$WORKBASE/$_r"
  mkdir -p "$_w"
  _j="$JOBS"; [ "$_r" = "sutra-turn" ] && _j="$TURN_JOBS"
  echo "--- sutra-charcap verify --all --runner $_r --jobs $_j ------------"
  # charcap writes its per-family summary lines to stderr; both streams are
  # the summary block this suite promises to print.
  ( SUTRA_CHARCAP_WORK="$_w" "$CHARCAP" verify --all --runner "$_r" --jobs "$_j" 2>&1 ) \
    | sed 's/^/  /'
  _rc=${PIPESTATUS[0]}
  rm -rf "$_w"
  if [ "$_rc" -eq 0 ]; then
    pass "golden parity, runner=$_r (exit 0)"
  else
    fail "golden parity, runner=$_r (exit $_rc)"
  fi
  return 0
}

echo "plugin root: $PLUGIN_ROOT"
echo "corpus:      $GOLDEN"
run_runner legacy
run_runner sutra-turn

echo "failed=$failed"
[ "$failed" -eq 0 ]
