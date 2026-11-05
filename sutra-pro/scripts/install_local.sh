#!/bin/sh
# Install Sutra Pro on this Mac the way D88 says, and prove the INSTALLED copy works (GAP-INSTALL, G17).
#
#   sh scripts/install_local.sh               build the wheel, check it, install it with `uv tool`, then verify the installed command
#   sh scripts/install_local.sh --dry-run     print the steps and do nothing (no build, no install, no files)
#
# Steps: uv build --wheel -> scripts/check_wheel.py -> uv tool install --reinstall <wheel> (non-editable: the wheel must carry every
# data file, D86) -> verify with a throw-away data folder, so ~/.sutra-pro is never touched by the check:
#   sutra-pro --help, sutra-pro doctor --offline, then an offline start on a free port that must answer /api/health inside
#   20 s, serve the Home page, accept one chat message, and stop with `sutra-pro stop`.
# It prints the installed version and the data folder (~/.sutra-pro, unless SUTRA_DATA_DIR says otherwise when you run the app).
#
# Environment: SUTRA_DIST_DIR (where the wheel is built; default ./dist), SUTRA_INSTALL_START_WAIT (seconds the offline start may
# take; default 20), and uv's own UV_TOOL_DIR / UV_TOOL_BIN_DIR (where the tool goes). Exit 0 all fine, 1 a step failed, 2 usage.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
DIST=${SUTRA_DIST_DIR:-$HERE/dist}
WAIT=${SUTRA_INSTALL_START_WAIT:-20}
DRY=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h | --help)
      sed -n '2,/^set -eu/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "install_local.sh: unknown argument '$arg' (try --help)" >&2
      exit 2
      ;;
  esac
done

say() { echo "install_local.sh: $*"; }
fail() {
  echo "install_local.sh: FAILED: $*" >&2
  exit 1
}

if [ "$DRY" = 1 ]; then
  say "dry run: nothing is built, installed or written. The steps would be:"
  say "  1. uv build --wheel --out-dir $DIST $HERE"
  say "  2. check_wheel.py $DIST/sutra_pro-*.whl   (every package-data glob, the sutra-pro command, the distribution name)"
  say "  3. uv tool install --reinstall $DIST/sutra_pro-*.whl   (non-editable, D88)"
  say "  4. sutra-pro --help"
  say "  5. sutra-pro doctor --offline   (on a throw-away data folder)"
  say "  6. sutra-pro --offline --no-browser --port <free>   (must answer /api/health within ${WAIT} s)"
  say "  7. GET /api/health, GET /, POST one chat message"
  say "  8. sutra-pro stop"
  say "  then it prints the installed version and the data folder ($HOME/.sutra-pro)."
  command -v uv >/dev/null 2>&1 || say "note: 'uv' is not installed here; a real run needs it (https://docs.astral.sh/uv/)."
  exit 0
fi

command -v uv >/dev/null 2>&1 || fail "'uv' is not installed (https://docs.astral.sh/uv/)"
command -v curl >/dev/null 2>&1 || fail "'curl' is not installed"

# ---- 1. build ------------------------------------------------------------------------------------------------------------------
had_build=0
[ -d "$HERE/build" ] && had_build=1
mkdir -p "$DIST"
rm -f "$DIST"/sutra_pro-*.whl      # a stale wheel must never be the one that gets installed
say "building the wheel into $DIST"
uv build --wheel --out-dir "$DIST" "$HERE" || fail "uv build"
[ "$had_build" = 0 ] && rm -rf "$HERE/build"     # setuptools' scratch folder; leave the tree as it was
set -- "$DIST"/sutra_pro-*.whl
[ "$#" = 1 ] && [ -f "$1" ] || fail "expected exactly one wheel in $DIST, found: $*"
WHEEL=$1

# ---- 2. look inside the wheel --------------------------------------------------------------------------------------------------
PY=""
if [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
else
  prefix=$(git -C "$HERE" rev-parse --show-prefix 2>/dev/null || true)
  common=$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  [ -n "$common" ] && [ -x "$(dirname "$common")/${prefix%/}/.venv/bin/python" ] && PY="$(dirname "$common")/${prefix%/}/.venv/bin/python"
fi
say "checking the wheel ($WHEEL)"
if [ -n "$PY" ]; then
  "$PY" "$HERE/scripts/check_wheel.py" "$WHEEL" --root "$HERE" || fail "check_wheel.py found a problem in the wheel"
else
  uv run --no-project --python ">=3.11" python "$HERE/scripts/check_wheel.py" "$WHEEL" --root "$HERE" || fail "check_wheel.py found a problem in the wheel"
fi

# ---- 3. install ----------------------------------------------------------------------------------------------------------------
say "installing it with uv tool (non-editable)"
uv tool install --reinstall "$WHEEL" || fail "uv tool install"
BIN=$(uv tool dir --bin)
SP="$BIN/sutra-pro"
[ -x "$SP" ] || fail "the command was not installed at $SP"

# ---- 4. verify the installed copy, on a throw-away data folder, with a clean environment -----------------------------------------
for name in $(env | sed 's/=.*//' | grep -E '^(SUTRA_|J2_|STUDIO_)' || true); do
  [ "$name" = SUTRA_DIST_DIR ] || [ "$name" = SUTRA_INSTALL_START_WAIT ] || unset "$name"
done
TMP=$(mktemp -d "${TMPDIR:-/tmp}/sutra-install.XXXXXX")
LOG="$TMP/server.log"
PID=""
cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    "$SP" stop >/dev/null 2>&1 || true     # the server is the subshell's child: ask it to end; then the subshell ends by itself
    pkill -P "$PID" 2>/dev/null || true
    kill "$PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT
SUTRA_DATA_DIR="$TMP/data"
SUTRA_ENV_FILE="$TMP/none.env"
export SUTRA_DATA_DIR SUTRA_ENV_FILE

fail_with_log() {
  echo "install_local.sh: FAILED: $*" >&2
  [ -f "$LOG" ] && { echo "---- last lines of the server's output ----" >&2; tail -n 30 "$LOG" >&2; }
  exit 1
}

say "verify: sutra-pro --help"
"$SP" --help | grep -q "usage: sutra-pro" || fail "'sutra-pro --help' did not print its usage"

say "verify: sutra-pro doctor --offline"
"$SP" doctor --offline || fail "'sutra-pro doctor --offline' reported a failed check"

say "verify: offline start (up to ${WAIT} s)"
# a subshell owns the server, so the shell's "Terminated" job notice (a normal stop is SIGTERM) goes into the log, not the screen
( "$SP" --offline --no-browser --port 0; true ) >"$LOG" 2>&1 &
PID=$!
URL=""
i=0
limit=$((WAIT * 5))
while [ "$i" -lt "$limit" ]; do
  kill -0 "$PID" 2>/dev/null || fail_with_log "the server ended before it was ready"
  URL=$(sed -n 's|.*running at \(http://127\.0\.0\.1:[0-9]*\)/.*|\1|p' "$LOG" | head -n 1)
  if [ -n "$URL" ] && curl -fsS --max-time 2 "$URL/api/health" 2>/dev/null | grep -Eq '"ok": ?true'; then
    break
  fi
  URL=""
  i=$((i + 1))
  sleep 0.2
done
[ -n "$URL" ] || fail_with_log "the server did not answer /api/health within ${WAIT} s"
say "verify: it answers on $URL"

PAGE="$TMP/home.html"
curl -fsS --max-time 10 "$URL/" -o "$PAGE" || fail_with_log "GET / failed"
grep -q 'id="sutra-boot"' "$PAGE" || fail_with_log "the Home page does not carry its boot block"
TOKEN=$(grep -o '"token": *"[^"]*"' "$PAGE" | head -n 1 | cut -d '"' -f 4)
[ -n "$TOKEN" ] || fail_with_log "the Home page carries no token"

CODE=$(curl -sS --max-time 10 -o "$TMP/post.json" -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H "X-Sutra-Token: $TOKEN" \
  -d '{"text":"hello from the install check"}' "$URL/api/chats/cs_org/messages") || fail_with_log "posting a chat message failed"
[ "$CODE" = 202 ] || fail_with_log "posting a chat message answered $CODE (expected 202): $(cat "$TMP/post.json")"
say "verify: one chat message accepted; waiting for its turn to end"
i=0
while [ "$i" -lt "$limit" ]; do
  curl -fsS --max-time 5 -H "X-Sutra-Token: $TOKEN" "$URL/api/chats/cs_org/messages" -o "$TMP/messages.json" || fail_with_log "listing the chat failed"
  if grep -q 'hello from the install check' "$TMP/messages.json" && ! grep -Eq '"state": ?"pending"' "$TMP/messages.json"; then
    break
  fi
  i=$((i + 1))
  sleep 0.2
done
[ "$i" -lt "$limit" ] || fail_with_log "the chat turn did not end within ${WAIT} s"

say "verify: sutra-pro stop"
"$SP" stop || fail_with_log "'sutra-pro stop' failed"
j=0
while kill -0 "$PID" 2>/dev/null && [ "$j" -lt 100 ]; do
  j=$((j + 1))
  sleep 0.2
done
kill -0 "$PID" 2>/dev/null && fail_with_log "the server is still running after 'sutra-pro stop'"
{ wait "$PID"; } 2>/dev/null || true     # reap it quietly (the shell would announce the SIGTERM)
PID=""

# ---- 5. report -----------------------------------------------------------------------------------------------------------------
VERSION=$(uv tool list 2>/dev/null | sed -n 's/^sutra-pro v\{0,1\}\([^ ]*\).*/\1/p' | head -n 1)
say "OK: sutra-pro ${VERSION:-(version unknown)} is installed at $SP"
say "your data folder is $HOME/.sutra-pro (the check above used a throw-away folder and left it alone)"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) say "note: $BIN is not on your PATH; run 'uv tool update-shell' and open a new terminal" ;;
esac
say "start it with: sutra-pro      remove it with: sh scripts/uninstall_local.sh"
