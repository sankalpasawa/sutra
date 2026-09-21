#!/usr/bin/env bash
# =============================================================================
# beta-smoke.sh -- the automated look at a built Sutra Beta (founder D82,
# 2026-09-21: "I don't want any manual look ... do that automatically in beta
# and then push out to main as well. No human involvement.")
# =============================================================================
# What the founder used to do by hand between the beta and the stable tag
# (release-checklist.md checks 3 and 7), done by this script on THIS Mac:
#
#   1. fetch    the DMG for this machine's architecture from the GitHub
#               prerelease of the beta tag, with its .sha256
#   2. checksum shasum -a 256 -c against the published .sha256
#   3. gate     xcrun stapler validate (the notarization ticket is stapled)
#               + spctl --assess (Gatekeeper accepts it, no dialog would show)
#   4. install  mount the DMG, copy "Sutra Beta.app" to a scratch folder,
#               unmount; read the bundle's version and channel marker
#   5. launch   start the app (its own port 8331, its own ~/.sutra-ui-beta
#               data), wait for the backend's own health answer
#   6. walk     the panel serves, the panel token is minted, and the Shadow
#               surfaces answer (status, settings, missions, feed) -- the
#               programmatic stand-in for "open Shadow home and look"
#   7. quit     stop what we started; the port must close
#
# Every step is a PASS/FAIL line; the verdict is the last line; exit 0 only on
# PASS. A row goes to .enforcement/beta-smoke.jsonl (repo-local, never
# committed) so a promotion can be traced to the smoke that allowed it.
#
# Usage:
#   scripts/beta-smoke.sh vX.Y.Z-beta.N-desktop
#
# Escape hatches, each audited in the row, none the default:
#   SUTRA_SMOKE_ALLOW_UNSTAPLED=1   accept an ad-hoc (unsigned) build
#   SUTRA_SMOKE_KEEP=1              leave the app running and the folder behind
#   SUTRA_SMOKE_BOOT_WAIT_S=N       seconds to wait for the backend (180)
# =============================================================================
set -uo pipefail

APP_NAME="Sutra Beta"
BETA_PORT=8331
HEALTH="http://127.0.0.1:$BETA_PORT/api/org/health"

# ---- pure helpers (unit-tested by test-release-desktop.sh, sourced with
# ---- BETA_SMOKE_LIB=1 so nothing below the banner runs) ---------------------
smoke_arch() {                       # smoke_arch <uname -m> -> arm64 | x86_64
  case "${1:-}" in arm64|aarch64) printf 'arm64' ;; x86_64|amd64) printf 'x86_64' ;; *) return 1 ;; esac
}
smoke_asset_for() {                  # smoke_asset_for <arch> -> Sutra-<arch>.dmg
  printf 'Sutra-%s.dmg' "${1:-}"
}
smoke_version_of() {                 # smoke_version_of <beta-tag> -> X.Y.Z, or nothing
  printf '%s' "${1:-}" | sed -nE 's/^v([0-9]+\.[0-9]+\.[0-9]+)-beta\.[0-9]+-desktop$/\1/p'
}
# the walk: every route the smoke must see answer 200
SMOKE_ROUTES="/ /api/state /api/shadow/status /api/shadow/settings /api/shadow/missions /api/shadow/feed /api/sessions"

if [ "${BETA_SMOKE_LIB:-0}" = 1 ]; then return 0 2>/dev/null || exit 0; fi

# =============================================================================
TAG="${1:-}"
[ -n "$TAG" ] || { echo "usage: scripts/beta-smoke.sh vX.Y.Z-beta.N-desktop" >&2; exit 2; }
VERSION="$(smoke_version_of "$TAG")"
[ -n "$VERSION" ] || { echo "beta-smoke: '$TAG' is not a beta tag" >&2; exit 2; }
BOOT_WAIT_S="${SUTRA_SMOKE_BOOT_WAIT_S:-180}"     # a cold start can take ~85 s (checklist check 3)

_fails=0; _rows=""
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; _rows="$_rows{\"step\":\"$2\",\"pass\":true},"; }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; _rows="$_rows{\"step\":\"$2\",\"pass\":false},"; _fails=$((_fails+1)); }
note(){ printf '        %s\n' "$1"; }

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
for t in gh curl hdiutil shasum spctl; do command -v "$t" >/dev/null 2>&1 || { echo "beta-smoke: $t is required" >&2; exit 2; }; done
ARCH="$(smoke_arch "$(uname -m)")" || { echo "beta-smoke: unsupported architecture $(uname -m)" >&2; exit 2; }
DMG="$(smoke_asset_for "$ARCH")"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/beta-smoke.XXXXXX")"
MNT="$WORK/mnt"; APPDIR="$WORK/app"; mkdir -p "$MNT" "$APPDIR"
LAUNCHED_PID=""

stop_app() {
  [ -n "$LAUNCHED_PID" ] || return 0
  kill -TERM -- "-$LAUNCHED_PID" 2>/dev/null; sleep 2
  kill -KILL -- "-$LAUNCHED_PID" 2>/dev/null
}
cleanup() {
  if [ "${SUTRA_SMOKE_KEEP:-0}" != 1 ]; then
    stop_app
    hdiutil detach "$MNT" -quiet 2>/dev/null || true
    rm -rf "$WORK"
  else
    note "kept: $WORK (SUTRA_SMOKE_KEEP=1)"
  fi
}
trap cleanup EXIT

printf '\n\033[1mBETA SMOKE %s on this Mac (%s)\033[0m\n' "$TAG" "$ARCH"

# ---- 1. fetch ---------------------------------------------------------------
if gh release download "$TAG" -p "$DMG" -p "$DMG.sha256" -D "$WORK" >/dev/null 2>&1 && [ -s "$WORK/$DMG" ] && [ -s "$WORK/$DMG.sha256" ]; then
  ok "fetch: $DMG and its .sha256 from the $TAG prerelease" fetch
else
  bad "fetch: could not download $DMG + .sha256 for $TAG (is the build finished?)" fetch
fi

# ---- 2. checksum ------------------------------------------------------------
if [ -s "$WORK/$DMG" ] && (cd "$WORK" && shasum -a 256 -c "$DMG.sha256" >/dev/null 2>&1); then
  ok "checksum: shasum -a 256 -c $DMG.sha256 -> OK" checksum
else
  bad "checksum: $DMG does not match its published .sha256" checksum
fi

# ---- 3. notarization --------------------------------------------------------
if [ -s "$WORK/$DMG" ] && xcrun stapler validate "$WORK/$DMG" >/dev/null 2>&1; then
  ok "staple: the notarization ticket is stapled to $DMG" staple
elif [ "${SUTRA_SMOKE_ALLOW_UNSTAPLED:-0}" = 1 ]; then
  ok "staple: NOT stapled, accepted by SUTRA_SMOKE_ALLOW_UNSTAPLED=1 (audited)" staple
else
  bad "staple: xcrun stapler validate failed -- every downloader would meet 'Apple could not verify'" staple
fi

# ---- 4. install -------------------------------------------------------------
APP=""
if [ -s "$WORK/$DMG" ] && hdiutil attach "$WORK/$DMG" -nobrowse -readonly -mountpoint "$MNT" -quiet 2>/dev/null; then
  src="$(find "$MNT" -maxdepth 1 -name "*.app" | head -1)"
  if [ -n "$src" ] && cp -R "$src" "$APPDIR/" 2>/dev/null; then
    APP="$APPDIR/$(basename "$src")"
    ok "install: $(basename "$src") copied from the DMG" install
  else
    bad "install: no .app on the mounted DMG" install
  fi
  hdiutil detach "$MNT" -quiet 2>/dev/null || true
else
  bad "install: could not mount $DMG" install
fi

if [ -n "$APP" ]; then
  bv="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist" 2>/dev/null)"
  if [ "$bv" = "$VERSION" ]; then ok "bundle: CFBundleShortVersionString $bv == $VERSION" version
  else bad "bundle: CFBundleShortVersionString '$bv' != tag version $VERSION" version; fi
  ch="$(cat "$APP/Contents/Resources/channel" 2>/dev/null)"
  if [ "$ch" = beta ]; then ok "bundle: channel marker is beta (own port $BETA_PORT, own data)" channel
  else bad "bundle: channel marker is '$ch', not beta -- this is not the coexisting app" channel; fi
  if spctl --assess --type execute "$APP" >/dev/null 2>&1; then
    ok "gatekeeper: spctl accepts $(basename "$APP") -- no 'could not verify' dialog" gatekeeper
  elif [ "${SUTRA_SMOKE_ALLOW_UNSTAPLED:-0}" = 1 ]; then
    ok "gatekeeper: spctl rejects, accepted by SUTRA_SMOKE_ALLOW_UNSTAPLED=1 (audited)" gatekeeper
  else
    bad "gatekeeper: spctl --assess rejects $(basename "$APP")" gatekeeper
  fi
fi

# ---- 5. launch --------------------------------------------------------------
if [ -n "$APP" ] && [ "$_fails" = 0 ]; then
  # a Sutra Beta already running would answer for the build under test
  if curl -s -m 2 "$HEALTH" >/dev/null 2>&1; then
    note "a Sutra Beta is already running on $BETA_PORT -- stopping it first"
    pkill -f "$APP_NAME.app/Contents/MacOS/" 2>/dev/null || true
    for i in $(seq 1 20); do curl -s -m 1 "$HEALTH" >/dev/null 2>&1 || break; sleep 1; done
  fi
  bin="$APP/Contents/MacOS/$APP_NAME"
  if [ -x "$bin" ]; then
    # direct exec in its own process group, so quit takes the backend with it
    ( set -m; "$bin" >"$WORK/app.log" 2>&1 & echo $! > "$WORK/pid" )
    LAUNCHED_PID="$(cat "$WORK/pid" 2>/dev/null)"
    t0=$(date +%s); up=0
    while [ $(( $(date +%s) - t0 )) -lt "$BOOT_WAIT_S" ]; do
      if curl -s -m 2 "$HEALTH" 2>/dev/null | grep -q '"lint_scope"'; then up=1; break; fi
      sleep 2
    done
    if [ "$up" = 1 ]; then ok "launch: backend answered $HEALTH with lint_scope in $(( $(date +%s) - t0 )) s" launch
    else bad "launch: no health answer on port $BETA_PORT within ${BOOT_WAIT_S} s (see $WORK/app.log)" launch; fi
  else
    bad "launch: no executable at $bin" launch
  fi
fi

# ---- 6. walk ----------------------------------------------------------------
if [ "$_fails" = 0 ] && [ -n "$LAUNCHED_PID" ]; then
  token="$(curl -s -m 5 "http://127.0.0.1:$BETA_PORT/api/panel-token" 2>/dev/null | sed -nE 's/.*"token": *"([^"]+)".*/\1/p')"
  if [ -n "$token" ]; then ok "walk: the panel token is minted" token
  else bad "walk: /api/panel-token gave no token" token; fi
  for r in $SMOKE_ROUTES; do
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -H "x-sutra-panel: $token" "http://127.0.0.1:$BETA_PORT$r" 2>/dev/null)"
    if [ "$code" = 200 ]; then ok "walk: GET $r -> 200" "walk$r"
    else bad "walk: GET $r -> ${code:-no answer}" "walk$r"; fi
  done
fi

# ---- 7. quit ----------------------------------------------------------------
if [ -n "$LAUNCHED_PID" ] && [ "${SUTRA_SMOKE_KEEP:-0}" != 1 ]; then
  stop_app; LAUNCHED_PID=""
  closed=0
  for i in $(seq 1 15); do curl -s -m 1 "$HEALTH" >/dev/null 2>&1 || { closed=1; break; }; sleep 1; done
  if [ "$closed" = 1 ]; then ok "quit: the app we started is gone and port $BETA_PORT is closed" quit
  else bad "quit: something still answers on port $BETA_PORT after the kill" quit; fi
fi

# ---- verdict + audit row ----------------------------------------------------
verdict=PASS; [ "$_fails" = 0 ] || verdict=FAIL
mkdir -p "$ROOT/.enforcement" 2>/dev/null
printf '{"ts":"%s","tag":"%s","version":"%s","arch":"%s","host":"%s","verdict":"%s","fails":%s,"allow_unstapled":%s,"steps":[%s]}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TAG" "$VERSION" "$ARCH" "$(hostname -s 2>/dev/null)" "$verdict" "$_fails" \
  "$( [ "${SUTRA_SMOKE_ALLOW_UNSTAPLED:-0}" = 1 ] && echo true || echo false )" "${_rows%,}" \
  >> "$ROOT/.enforcement/beta-smoke.jsonl" 2>/dev/null
printf '\n\033[1mVERDICT\033[0m\n'
if [ "$verdict" = PASS ]; then printf '  \033[32mBETA SMOKE PASS\033[0m -- %s booted, answered and walked on this Mac\n' "$TAG"; exit 0; fi
printf '  \033[31mBETA SMOKE FAIL\033[0m -- %d step(s) failed; the stable tag is NOT cut\n' "$_fails"
exit 1
