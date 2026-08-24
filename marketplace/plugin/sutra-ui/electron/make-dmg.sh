#!/usr/bin/env bash
# RELEASES DO NOT COME FROM THIS SCRIPT ANY MORE (founder direction 2026-08-24).
#
# .github/workflows/release-dmg.yml owns every published DMG. It builds both
# arches on native runners, signs and notarizes with the repo's Apple secrets,
# and uploads Sutra-<arch>.dmg plus a per-arch .sha256. Push a v* tag to
# sankalpasawa/sutra and it runs. Nothing else may create or upload a release
# asset.
#
# This is not a style preference; it was measured. A hand-built release for
# v2.220.2 was created at 09:08 and CI replaced both DMGs at 09:26/09:28 with
# different checksums -- so ~15 minutes of local notarization was wasted, and
# for 18 minutes the published release carried assets no pipeline had built.
# The workflow already said "do not also upload them by hand"; it said it in a
# file that only CI reads, which is why it kept happening.
#
# THIS SCRIPT IS STILL CORRECT FOR LOCAL WORK: --skip-notarize to build a DMG
# for installing and testing on this machine. That is its only remaining job.
# make-dmg.sh -- build the installable Sutra.dmg.
#
#   bundle-runtime.sh   ->  payload/   (CPython + deps + the plugin)
#   THIS SCRIPT         ->  dist/Sutra-<version>-<arch>.dmg
#
# The DMG is a drag-to-Applications installer. What lands is self-sufficient:
# the app runs the panel out of its own Resources, and installs the Claude Code
# plugin on first launch. No Python, no Node, no network, no Xcode on the
# target machine.
#
# SIGNING, and why this script has two modes
# ------------------------------------------
# Gatekeeper on any Mac other than the one that built it will refuse an
# unsigned app ("Sutra is damaged and can't be opened"). Clearing that properly
# needs a DEVELOPER ID APPLICATION certificate plus notarization by Apple.
#
#   * If a "Developer ID Application" identity is in the keychain, this script
#     signs with it, submits to Apple, waits, and staples the ticket. The result
#     opens with a normal double-click anywhere.
#   * If there is not one, it signs AD-HOC and says so, loudly, at the end. The
#     DMG works, but a first launch on another Mac needs right-click -> Open.
#
# An "Apple Development" certificate is NOT a substitute: it cannot be
# notarized and it is not accepted by Gatekeeper off the development machine.
#
# Notarization credentials, in the order they are tried:
#   1. a keychain profile:  xcrun notarytool store-credentials sutra ...
#      then:                SUTRA_NOTARY_PROFILE=sutra ./make-dmg.sh
#   2. App Store Connect API key:
#      SUTRA_NOTARY_KEY=/path/AuthKey_X.p8 SUTRA_NOTARY_KEY_ID=... SUTRA_NOTARY_ISSUER=...
#   3. Apple ID + app-specific password:
#      SUTRA_APPLE_ID=... SUTRA_APPLE_PASSWORD=... SUTRA_TEAM_ID=...
#
# Usage:
#   ./make-dmg.sh                 # host arch
#   ./make-dmg.sh --arch x86_64
#   ./make-dmg.sh --skip-notarize # sign, don't submit (fast iteration)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI="$(cd "$HERE/.." && pwd)"
APP_NAME="Sutra"
BUNDLE_ID="os.sutra.ui"
PAYLOAD="$HERE/payload"
DIST="$HERE/dist"
ENTITLEMENTS="$HERE/entitlements.plist"
ARCH="$(uname -m)"
SKIP_NOTARIZE=0

die()  { printf '\nmake-dmg: %s\n' "$*" >&2; exit 2; }
step() { printf '\n== %s\n' "$*"; }
NOTES=()
note() { NOTES+=("$*"); }

while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:-}"; shift 2 ;;
    --skip-notarize) SKIP_NOTARIZE=1; shift ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
[ "$ARCH" = "aarch64" ] && ARCH="arm64"
# THREE spellings of the same CPU, and they are not interchangeable:
#   uname / python-build-standalone  ->  x86_64   (what bundle-runtime.sh stamps)
#   electron-packager                ->  x64      (it rejects "x86_64" outright)
#   the DMG filename                 ->  x86_64   (what a human recognises)
case "$ARCH" in
  arm64)  PKG_ARCH="arm64" ;;
  x86_64) PKG_ARCH="x64" ;;
  *) die "unsupported arch: $ARCH (arm64 or x86_64)" ;;
esac

[ "$(uname -s)" = "Darwin" ] || die "macOS only"
command -v npx      >/dev/null 2>&1 || die "npx not found -- install Node 18+"
command -v hdiutil  >/dev/null 2>&1 || die "hdiutil not found"
command -v codesign >/dev/null 2>&1 || die "codesign not found -- install the Xcode command line tools"
[ -d "$HERE/node_modules" ] || die "run: (cd $HERE && npm install)"
[ -f "$ENTITLEMENTS" ] || die "missing $ENTITLEMENTS"

# ---------------------------------------------------------------- payload --
step "payload"
if [ ! -f "$PAYLOAD/STAMP" ]; then
  die "no payload. Build it first:
    $HERE/bundle-runtime.sh --arch $ARCH"
fi
PAYLOAD_ARCH="$(sed -n 's/.*"arch": *"\([^"]*\)".*/\1/p' "$PAYLOAD/STAMP")"
[ "$PAYLOAD_ARCH" = "$ARCH" ] || die "payload was built for $PAYLOAD_ARCH but this run targets $ARCH.
  Rebuild it:  $HERE/bundle-runtime.sh --arch $ARCH"
VERSION="$(sed -n 's/.*"plugin_version": *"\([^"]*\)".*/\1/p' "$PAYLOAD/STAMP")"
[ -n "$VERSION" ] || VERSION="0.0.0"
echo "  plugin $VERSION, $PAYLOAD_ARCH, $(du -sh "$PAYLOAD" | awk '{print $1}')"

# ------------------------------------------------------------------- icon --
step "icon"
MARK_SVG="$UI/assets/sutra-app-icon.svg"
[ -f "$MARK_SVG" ] || MARK_SVG="$UI/../../../website/sutra-mark.svg"
make_icon() {   # make_icon <svg> <out.icns>
  local svg="$1" out="$2" ws iconset px name spec
  [ -f "$svg" ] || return 1
  command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1 || return 1
  ws="$(mktemp -d "${TMPDIR:-/tmp}/sutra-icon.XXXXXX")" || return 1
  iconset="$ws/$APP_NAME.iconset"; mkdir -p "$iconset"
  sips -s format png -z 1024 1024 "$svg" --out "$ws/base.png" >/dev/null 2>&1 \
    || { rm -rf "$ws"; return 1; }
  for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
              "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
              "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
    px="${spec%% *}"; name="${spec#* }"
    sips -z "$px" "$px" "$ws/base.png" --out "$iconset/$name.png" >/dev/null 2>&1 \
      || { rm -rf "$ws"; return 1; }
  done
  iconutil -c icns "$iconset" -o "$out" >/dev/null 2>&1 || { rm -rf "$ws"; return 1; }
  rm -rf "$ws"; [ -s "$out" ]
}
mkdir -p "$HERE/build"
if make_icon "$MARK_SVG" "$HERE/build/$APP_NAME.icns"; then
  echo "  built build/$APP_NAME.icns from $(basename "$MARK_SVG")"
else
  note "could not rasterise $MARK_SVG -- the bundle keeps whatever icon build/ already had"
fi

# ------------------------------------------------------------------ pack ---
step "package"
rm -rf "$DIST/$APP_NAME-darwin-$PKG_ARCH"
# --no-install: without it a missing local binary makes npx DOWNLOAD and run the
# deprecated legacy electron-packager from the registry -- remote code during a
# release build. --extra-resource is what puts the payload in Contents/Resources.
( cd "$HERE" && npx --no-install electron-packager . "$APP_NAME" \
    --platform=darwin --arch="$PKG_ARCH" --out=dist --overwrite \
    --app-bundle-id="$BUNDLE_ID" --app-version="$VERSION" \
    --icon=build/"$APP_NAME".icns --prune=true \
    --extra-resource=payload \
    --ignore='^/payload($|/)' --ignore='^/dist($|/)' --ignore='^/build($|/)' \
) >/dev/null || die "electron-packager failed"
APP="$DIST/$APP_NAME-darwin-$PKG_ARCH/$APP_NAME.app"
[ -d "$APP" ] || die "no bundle at $APP"
[ -x "$APP/Contents/Resources/payload/python/bin/python3" ] \
  || die "the payload did not make it into the bundle"
echo "  $APP  ($(du -sh "$APP" | awk '{print $1}'))"

# The bundled interpreter must run FROM ITS INSTALLED LOCATION, not just from
# the build tree -- a relocatable python that lost its stdlib in the copy fails
# here rather than on a stranger's Mac.
#
# CROSS-BUILDING: an x86_64 interpreter on an Apple Silicon host only runs under
# Rosetta. When Rosetta is absent the check CANNOT run, and the honest move is to
# say so rather than either failing a good build or printing a pass we did not
# earn. The structural checks above still apply, and CI builds each arch on its
# own runner where this check does run for real.
HOST_ARCH="$(uname -m)"
if [ "$ARCH" = "$HOST_ARCH" ] || arch -"$([ "$ARCH" = x86_64 ] && echo x86_64 || echo arm64)" \
     /usr/bin/true >/dev/null 2>&1; then
  "$APP/Contents/Resources/payload/python/bin/python3" -c \
    'import fastapi, uvicorn, websockets, sys; print("  bundled python %s ok" % sys.version.split()[0])' \
    || die "the bundled interpreter cannot import its dependencies from inside the .app"
else
  note "Could not RUN the $ARCH interpreter on this $HOST_ARCH host (no Rosetta), so the
    bundled-import check was skipped for this build. Structure and signature were
    still verified. Install Rosetta (softwareupdate --install-rosetta) or build
    this arch on its own machine to get the runtime check too."
  echo "  bundled python: import check skipped (cannot execute $ARCH here)"
fi

# ------------------------------------------------------------------ sign ---
step "sign"
IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null \
  | sed -n 's/.*"\(Developer ID Application: [^"]*\)".*/\1/p' | head -1)"
if [ -n "$IDENTITY" ]; then
  echo "  identity: $IDENTITY"
  SIGN_ARGS=(--force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY")
else
  DEV_ID="$(security find-identity -v -p codesigning 2>/dev/null \
    | sed -n 's/.*"\(Apple Development: [^"]*\)".*/\1/p' | head -1)"
  if [ -n "$DEV_ID" ]; then
    note "Found only an APPLE DEVELOPMENT certificate ($DEV_ID). That cannot be
    notarized and Gatekeeper rejects it off this machine, so the build signed
    AD-HOC instead. For a double-click-anywhere DMG you need a Developer ID
    Application certificate (Apple Developer Program, \$99/yr)."
  else
    note "No signing certificate found -- signed AD-HOC."
  fi
  echo "  ad-hoc (codesign -s -)"
  SIGN_ARGS=(--force --options runtime --entitlements "$ENTITLEMENTS" --sign -)
fi

# INSIDE OUT. codesign seals a bundle's contents into its own signature, so any
# nested binary signed AFTER the outer app invalidates that signature. --deep is
# deprecated for exactly this reason and is not trusted here: every nested code
# object is signed explicitly, deepest first, then the outer app.
#
# FAILURES ARE NOT SWALLOWED. An earlier version ended every inner codesign with
# `|| true`, so a framework that refused to sign was silent until the final
# --verify said "code object is not signed at all" with no clue which step had
# failed. That is exactly what happened on the first x86_64 build.
SIGN_FAILS=()
sign_one() {   # sign_one <path> <label>
  local out
  if ! out="$(codesign "${SIGN_ARGS[@]}" "$1" 2>&1)"; then
    SIGN_FAILS+=("$2: $1
      $(printf '%s' "$out" | head -2)")
    return 1
  fi
  return 0
}

signed=0
while IFS= read -r f; do
  sign_one "$f" "payload" && signed=$((signed + 1))
done < <(find "$APP/Contents/Resources/payload" \( -perm -u+x -o -name '*.dylib' -o -name '*.so' \) -type f \
         | while read -r f; do file -b "$f" | grep -q Mach-O && printf '%s\n' "$f"; done)
echo "  signed $signed Mach-O files in the payload"

# EVERY Mach-O file under Frameworks, recursively, BEFORE any bundle that
# contains it. This includes the ones buried inside a framework --
# Versions/A/Libraries/*.dylib and Versions/A/Helpers/chrome_crashpad_handler --
# which signing the framework bundle does NOT cover and which make the framework
# itself refuse to sign ("code object is not signed at all In subcomponent: ...").
#
# Only the x86_64 build hit this. Apple Silicon REQUIRES every arm64 binary to
# carry at least an ad-hoc signature to execute at all, so the arm64 Electron
# download arrives pre-signed; the x64 one does not have to be, and is not.
#
# Two rules make this work, and both were learned the hard way:
#   DEEPEST FIRST. find returns directory order, which put "Electron Framework"
#     (the framework's own binary) before "Helpers/chrome_crashpad_handler"
#     underneath it -- so the parent was signed while a child was still
#     unsigned, and codesign rejected it. Sorting by path depth, descending,
#     guarantees a child is always signed before anything that contains it.
#   NEVER SIGN A FRAMEWORK'S MAIN BINARY DIRECTLY. Versions/A/<Name> is the
#     framework's executable; it is signed as part of signing the Versions/A
#     BUNDLE further down. Signing the bare file is what produced the confusing
#     "code object is not signed at all" on the framework itself.
loose=0
while IFS= read -r lib; do
  # skip <X>.framework/Versions/<V>/<X>
  base="$(basename "$lib")"
  case "$lib" in
    *"/$base.framework/Versions/"*"/$base") continue ;;
  esac
  sign_one "$lib" "nested" && loose=$((loose + 1))
done < <(find "$APP/Contents/Frameworks" -type f \
           \( -perm -u+x -o -name '*.dylib' -o -name '*.node' \) \
         | while read -r f; do file -b "$f" | grep -q Mach-O && printf '%s\n' "$f"; done \
         | awk -F/ '{print NF"\t"$0}' | sort -rn -k1,1 | cut -f2-)

# Then the helper .app bundles that contain some of them.
helpers=0
while IFS= read -r helper; do
  sign_one "$helper" "helper" && helpers=$((helpers + 1))
done < <(find "$APP/Contents/Frameworks" -maxdepth 2 -name '*.app' 2>/dev/null)

# A .framework is signed at its VERSIONED bundle (Versions/A), not at the
# symlink-topped directory: codesign on the outer path is what silently did
# nothing and left "Electron Framework.framework" unsigned.
frameworks=0
while IFS= read -r fw; do
  target="$fw"
  [ -d "$fw/Versions/A" ] && target="$fw/Versions/A"
  sign_one "$target" "framework" && frameworks=$((frameworks + 1))
done < <(find "$APP/Contents/Frameworks" -maxdepth 1 -name '*.framework' 2>/dev/null)
echo "  signed $loose nested binaries, $helpers helper apps, $frameworks frameworks"

if [ ${#SIGN_FAILS[@]} -gt 0 ]; then
  printf '\nmake-dmg: %d nested code objects would not sign:\n' "${#SIGN_FAILS[@]}" >&2
  for f in "${SIGN_FAILS[@]}"; do printf '  %s\n' "$f" >&2; done
  die "refusing to ship a bundle with unsigned components"
fi

codesign "${SIGN_ARGS[@]}" "$APP" || die "signing the app bundle failed"
codesign --verify --deep --strict --verbose=1 "$APP" 2>&1 | sed 's/^/  /' \
  || die "the signature does not verify"

# macOS ships bash 3.2, which has no `mapfile`, so the credential arguments are
# assembled by direct array assignment rather than read from a subshell.
NARGS=()
if [ -n "${SUTRA_NOTARY_PROFILE:-}" ]; then
  NARGS=(--keychain-profile "$SUTRA_NOTARY_PROFILE")
elif [ -n "${SUTRA_NOTARY_KEY:-}" ] && [ -n "${SUTRA_NOTARY_KEY_ID:-}" ] \
     && [ -n "${SUTRA_NOTARY_ISSUER:-}" ]; then
  NARGS=(--key "$SUTRA_NOTARY_KEY" --key-id "$SUTRA_NOTARY_KEY_ID"
         --issuer "$SUTRA_NOTARY_ISSUER")
elif [ -n "${SUTRA_APPLE_ID:-}" ] && [ -n "${SUTRA_APPLE_PASSWORD:-}" ] \
     && [ -n "${SUTRA_TEAM_ID:-}" ]; then
  NARGS=(--apple-id "$SUTRA_APPLE_ID" --password "$SUTRA_APPLE_PASSWORD"
         --team-id "$SUTRA_TEAM_ID")
fi

# ------------------------------------------------- notarize the APP itself --
# The ticket has to be stapled to the .app, not only to the disk image.
#
# Stapling the DMG alone is enough for Gatekeeper WHEN IT CAN REACH APPLE: the
# app copied out of the image carries no ticket of its own, and acceptance then
# depends on an online check. Measured on a real download:
#
#     spctl (app, quarantined)  -> accepted, source=Notarized Developer ID
#     stapler validate (app)    -> "does not have a ticket stapled to it"
#
# That second line is the gap. A first launch with no network -- on a plane, a
# locked-down machine, a fresh laptop before wifi -- has nothing local to prove
# notarization with. Stapling the app closes it, at the cost of one extra
# submission per build.
#
# The app is submitted as a ZIP because notarytool does not accept a bare
# .app directory; the ticket is then stapled to the .app, and the DMG built
# AROUND the already-stapled app below.
# Notarization is a RELEASE act, and releases come from CI. Refuse it here
# rather than document a preference: the "do not build releases by hand" note
# already existed in release-dmg.yml and did not stop three hand-built releases,
# because a comment in a file only CI reads cannot stop anyone. A guard can.
#
# CI sets SUTRA_RELEASE_CI=1. On a workstation, notarizing produces an artifact
# that either goes nowhere or races the pipeline for the same asset name -- both
# of which happened. Local builds want --skip-notarize; Gatekeeper does not gate
# a locally built app, so nothing is lost.
if [ "$SKIP_NOTARIZE" != "1" ] && [ "${SUTRA_RELEASE_CI:-0}" != "1" ]; then
  die "notarization here is disabled: releases are built by
  .github/workflows/release-dmg.yml on a v* tag pushed to sankalpasawa/sutra.
  For a local build use --skip-notarize. To override deliberately, set
  SUTRA_RELEASE_CI=1 -- and know that CI will overwrite whatever you upload."
fi

if [ -n "$IDENTITY" ] && [ "$SKIP_NOTARIZE" != "1" ] && [ ${#NARGS[@]} -gt 0 ]; then
  step "notarize the app"
  APP_ZIP="$DIST/$APP_NAME-app-$ARCH.zip"
  rm -f "$APP_ZIP"
  /usr/bin/ditto -c -k --keepParent "$APP" "$APP_ZIP" \
    || die "could not zip the app for notarization"
  if xcrun notarytool submit "$APP_ZIP" "${NARGS[@]}" --wait; then
    xcrun stapler staple "$APP" \
      && echo "  ticket stapled to $APP_NAME.app" \
      || note "the app was notarized but could not be stapled; the DMG ticket still applies online"
  else
    note "notarizing the APP failed -- continuing to the DMG, which is submitted
    separately. The app inside will validate online but not offline."
  fi
  rm -f "$APP_ZIP"
  # Stapling rewrites the bundle, so re-verify before it is packaged.
  codesign --verify --deep --strict "$APP" >/dev/null 2>&1 \
    || die "the app signature broke while stapling"
fi

# ------------------------------------------------------------------- dmg ---
step "dmg"
mkdir -p "$DIST"
DMG="$DIST/$APP_NAME-$VERSION-$ARCH.dmg"
rm -f "$DMG"
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sutra-dmg.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT
cp -R "$APP" "$STAGE_DIR/$APP_NAME.app"
ln -s /Applications "$STAGE_DIR/Applications"     # the drag target
cat > "$STAGE_DIR/READ ME FIRST.txt" <<TXT
Sutra $VERSION ($ARCH)

1. Drag Sutra to Applications.
2. Open it.

The app carries its own Python: you do not need Python, Node, Xcode or a
network connection. On first launch it also installs the Sutra plugin for
Claude Code into ~/.claude, and tells you every path it wrote.

It serves a panel on http://127.0.0.1:8330 -- loopback only, never the network.
It refuses to start if ANTHROPIC_API_KEY is set, so it always bills your Max
plan rather than the per-token API.

If macOS says "Apple could not verify Sutra is free of malware", this build is
not notarized yet. That dialog offers only [Done] and [Move to Bin] -- do NOT
move it to the bin. Click Done, then:

    System Settings > Privacy & Security > scroll to Security
    > "Open Anyway" next to Sutra

Once per machine. (Right-click > Open stopped working in macOS 15.)
TXT
hdiutil create -volname "$APP_NAME $VERSION" -srcfolder "$STAGE_DIR" \
  -ov -format UDZO "$DMG" >/dev/null || die "hdiutil failed"
[ -n "$IDENTITY" ] && { codesign --force --timestamp --sign "$IDENTITY" "$DMG" >/dev/null 2>&1 \
  || note "could not sign the DMG itself"; }
echo "  $DMG  ($(du -sh "$DMG" | awk '{print $1}'))"

# -------------------------------------------------------------- notarize ---
step "notarize"
NOTARIZED=0
if [ "$SKIP_NOTARIZE" = "1" ]; then
  note "--skip-notarize: not submitted to Apple."
elif [ -z "$IDENTITY" ]; then
  note "Not notarized: notarization requires a Developer ID signature, and this
    build is ad-hoc. The DMG installs and runs; a first launch on another Mac
    needs right-click -> Open (once)."
elif [ ${#NARGS[@]} -eq 0 ]; then
  note "Not notarized: no credentials. Set SUTRA_NOTARY_PROFILE (after
    'xcrun notarytool store-credentials'), or SUTRA_NOTARY_KEY/_KEY_ID/_ISSUER,
    or SUTRA_APPLE_ID/_PASSWORD/_TEAM_ID, and re-run."
else
  echo "  submitting to Apple (this takes a few minutes)"
  if xcrun notarytool submit "$DMG" "${NARGS[@]}" --wait; then
    xcrun stapler staple "$DMG" && NOTARIZED=1 || note "notarized, but stapling failed"
  else
    note "notarytool rejected the submission -- see the log above.
    Diagnose with:  xcrun notarytool log <submission-id>"
  fi
fi

# ---------------------------------------------------------------- verdict --
step "summary"
echo "  dmg        $DMG"
echo "  size       $(du -sh "$DMG" | awk '{print $1}')"
echo "  arch       $ARCH"
echo "  signed     $([ -n "$IDENTITY" ] && echo "Developer ID" || echo "ad-hoc")"
echo "  notarized  $([ "$NOTARIZED" = 1 ] && echo yes || echo no)"
if [ "$NOTARIZED" = 1 ]; then
  spctl -a -t open --context context:primary-signature -v "$DMG" 2>&1 | sed 's/^/  gatekeeper /' || true
fi
if [ ${#NOTES[@]} -gt 0 ]; then
  echo
  echo "notes:"
  for n in "${NOTES[@]}"; do echo "  - $n"; done
fi
