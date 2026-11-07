#!/bin/bash
# Sign "Sutra Pro.app" INSIDE OUT (D123). The order and its reasons are those of the old Sutra's make-dmg.sh, which signs an Electron app that
# carries its own CPython with the same Developer ID certificate:
#
#   SIGN_IDENTITY="Developer ID Application: ..." scripts/sign_desktop_app.sh "build/Sutra Pro.app"
#   scripts/sign_desktop_app.sh "build/Sutra Pro.app"        # ad hoc ("-"): runs on the Mac that signed it, nothing more
#
# Environment (all optional): SIGN_IDENTITY (default "-", ad hoc), SIGN_TIMESTAMP=none (skip the secure timestamp, which needs the network:
# for a local run), SIGN_RUNTIME=1 (the hardened runtime for an ad hoc signature too; a Developer ID signature always has it).
#
# codesign seals a bundle's contents into the bundle's own signature, so anything nested that is signed AFTER the outer bundle breaks it. --deep
# is deprecated for exactly that and is not used: every code object is signed explicitly, deepest first, the app last.
#
#   1. every Mach-O file of the Python (Contents/Resources/python): the interpreter with entitlements.python.plist, the libraries and extension modules plain
#   2. every Mach-O file under Contents/Frameworks, deepest first, EXCEPT a framework's own binary (Versions/A/<Name>): that one is signed with its
#      Versions/A bundle. Signing the bare file is what produced "code object is not signed at all" on the Electron framework
#   3. the helper apps (GPU, renderer, plug-in), then the frameworks at their Versions/A bundle, with entitlements.electron.plist
#   4. the app, then `codesign --verify --deep --strict`
#
# FAILURES ARE NOT SWALLOWED: each is collected with its first lines of output, all are printed, and the script exits 1 before it signs the app.
# bash 3.2 is what macOS ships: no mapfile, no associative arrays, no ${var,,}, and an empty array is expanded with ${a[@]+"${a[@]}"} under set -u.
set -euo pipefail

APP="${1:-}"
if [ -z "$APP" ] || [ ! -d "$APP/Contents/MacOS" ]; then
  echo "usage: sign_desktop_app.sh <path to Sutra Pro.app>" >&2
  exit 2
fi
APP="${APP%/}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ENT_ELECTRON="$HERE/../desktop/entitlements.electron.plist"
ENT_PYTHON="$HERE/../desktop/entitlements.python.plist"
for f in "$ENT_ELECTRON" "$ENT_PYTHON"; do [ -f "$f" ] || { echo "error: $f is missing" >&2; exit 2; }; done
[ -d "$APP/Contents/Resources/python" ] || { echo "error: $APP has no Contents/Resources/python: build it with scripts/build_desktop_app.py" >&2; exit 2; }

IDENTITY="${SIGN_IDENTITY:--}"
BASE=(--force --sign "$IDENTITY")
if [ "$IDENTITY" != "-" ]; then
  BASE+=(--options runtime)
  if [ "${SIGN_TIMESTAMP:-secure}" = "none" ]; then BASE+=(--timestamp=none); else BASE+=(--timestamp); fi
elif [ "${SIGN_RUNTIME:-0}" = "1" ]; then
  BASE+=(--options runtime)
fi
if [ "$IDENTITY" = "-" ]; then echo "signing ad hoc"; else echo "signing as: $IDENTITY"; fi

FAILS=()
sign() {   # sign <path> [entitlements file]
  local path="$1" entitlements="${2:-}" out
  local args=("${BASE[@]}")
  if [ -n "$entitlements" ]; then args+=(--entitlements "$entitlements"); fi
  if ! out="$(codesign "${args[@]}" "$path" 2>&1)"; then
    FAILS+=("$path: $(printf '%s' "$out" | head -2 | tr '\n' ' ')")
    return 1
  fi
  return 0
}

is_macho() { file -b "$1" | grep -q Mach-O; }

# 1. the Python
python_files=0
while IFS= read -r -d '' file; do
  if is_macho "$file"; then
    entitlements=""
    case "$file" in */python/bin/*) entitlements="$ENT_PYTHON" ;; esac
    if sign "$file" "$entitlements"; then python_files=$((python_files + 1)); fi
  fi
done < <(find "$APP/Contents/Resources/python" -type f \( -name '*.so' -o -name '*.dylib' -o -perm -u+x \) -print0)
echo "  python: signed $python_files Mach-O files"

# 2. everything under Frameworks that is not a bundle, deepest first
nested=0
while IFS= read -r file; do
  base="$(basename "$file")"
  case "$file" in *"/$base.framework/Versions/"*"/$base") continue ;; esac
  entitlements=""
  case "$file" in *.dylib|*.node) ;; *) entitlements="$ENT_ELECTRON" ;; esac
  if sign "$file" "$entitlements"; then nested=$((nested + 1)); fi
done < <(find "$APP/Contents/Frameworks" -type f \( -perm -u+x -o -name '*.dylib' -o -name '*.node' \) \
           | while IFS= read -r candidate; do if is_macho "$candidate"; then printf '%s\n' "$candidate"; fi; done \
           | awk -F/ '{print NF"\t"$0}' | sort -rn -k1,1 | cut -f2-)

# 3. the helper apps, then the frameworks (at Versions/A, not at the symlink-topped directory)
helpers=0
while IFS= read -r -d '' helper; do
  if sign "$helper" "$ENT_ELECTRON"; then helpers=$((helpers + 1)); fi
done < <(find "$APP/Contents/Frameworks" -maxdepth 2 -name '*.app' -print0)
frameworks=0
while IFS= read -r -d '' framework; do
  target="$framework"
  if [ -d "$framework/Versions/A" ]; then target="$framework/Versions/A"; fi
  if sign "$target" ""; then frameworks=$((frameworks + 1)); fi
done < <(find "$APP/Contents/Frameworks" -maxdepth 1 -name '*.framework' -print0)
echo "  electron: signed $nested nested binaries, $helpers helper apps, $frameworks frameworks"

if [ "${#FAILS[@]}" -gt 0 ]; then
  echo "error: ${#FAILS[@]} code objects would not sign:" >&2
  for failure in "${FAILS[@]}"; do echo "  $failure" >&2; done
  exit 1
fi

# 4. the app
sign "$APP" "$ENT_ELECTRON" || { echo "error: signing the app failed: ${FAILS[0]}" >&2; exit 1; }
codesign --verify --deep --strict --verbose=1 "$APP"

# 5. the audit: what notarization checks, checked here in seconds instead of after a round trip to Apple. EVERY Mach-O file in the app (found by
# what it is, not by its name or its mode, so a file the passes above did not look at is found too) must be signed with the hardened runtime, and a
# release signature must carry a secure timestamp. One unsigned file is a rejected submission.
if [ "$IDENTITY" != "-" ] || [ "${SIGN_RUNTIME:-0}" = "1" ]; then
  total=0
  bad=0
  while IFS= read -r file; do
    total=$((total + 1))
    info="$(codesign -d --verbose=2 "$file" 2>&1 || true)"
    case "$info" in
      *"flags="*"(runtime)"*|*"flags="*",runtime"*) ;;
      *) echo "  not signed with the hardened runtime: $file" >&2; bad=$((bad + 1)); continue ;;
    esac
    if [ "$IDENTITY" != "-" ] && [ "${SIGN_TIMESTAMP:-secure}" != "none" ]; then
      case "$info" in *"Timestamp="*) ;; *) echo "  no secure timestamp: $file" >&2; bad=$((bad + 1)) ;; esac
    fi
  # `file` names a universal (two-architecture) binary once per architecture: "<path> (for architecture x86_64):<tab>Mach-O ..."
  done < <(find "$APP" -type f -print0 | xargs -0 file --no-pad 2>/dev/null | grep -a 'Mach-O' \
             | sed -E 's/( \(for architecture [^)]*\))?:[[:space:]]+Mach-O.*$//' | sort -u)
  if [ "$bad" -gt 0 ]; then
    echo "error: $bad of $total Mach-O files would be rejected by notarization" >&2
    exit 1
  fi
  echo "  audit: all $total Mach-O files carry the hardened runtime$([ "${SIGN_TIMESTAMP:-secure}" != "none" ] && [ "$IDENTITY" != "-" ] && echo ' and a secure timestamp')"
fi
echo "signed $APP"
