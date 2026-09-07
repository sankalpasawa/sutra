#!/usr/bin/env bash
# bundle-runtime.sh -- vendor everything the .app needs to run on a machine that
# has NOTHING installed: no Python, no Node, no Xcode tools, no network.
#
# install.sh solves a different problem. It points the app at THIS checkout and
# builds a venv from the machine's own python3 -- correct for a developer, and
# impossible for someone who downloaded a DMG. This script produces the payload
# that makes the .app self-sufficient:
#
#   payload/
#     python/        a relocatable CPython (astral-sh/python-build-standalone)
#                    with fastapi/uvicorn/websockets ALREADY installed into it
#     plugin/        the Sutra plugin tree: sutra-ui + lib + hooks + skills
#     STAMP          what this payload is, for the app's about/diagnostics and
#                    for provision.js to compare against an installed plugin
#
# electron-packager's --extra-resource puts this inside
# Sutra.app/Contents/Resources, and the app runs the panel STRAIGHT OUT OF the
# bundle -- no staging copy, no first-run pip. Nothing is fetched at install
# time: an offline Mac must go from DMG to running panel.
#
# (install.sh's staged runtime under Application Support exists because a
# CHECKOUT can live in a TCC-protected folder like ~/Desktop. A .app in
# /Applications reading its own Resources has no such problem, so the DMG path
# skips staging entirely. main.js prefers the bundle and falls back to the
# staged copy, so both installs keep working.)
#
# Usage:
#   ./bundle-runtime.sh                 # host arch
#   ./bundle-runtime.sh --arch x86_64   # cross-build the Intel payload
#   ./bundle-runtime.sh --clean
#
# Downloads are cached under ~/.cache/sutra-bundle so a rebuild is offline too.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI="$(cd "$HERE/.." && pwd)"              # marketplace/plugin/sutra-ui
PLUGIN="$(cd "$UI/.." && pwd)"            # marketplace/plugin
PAYLOAD="$HERE/payload"
CACHE="${SUTRA_BUNDLE_CACHE:-$HOME/.cache/sutra-bundle}"

PY_VERSION="${SUTRA_PY_VERSION:-3.12.13}"
PBS_TAG="${SUTRA_PBS_TAG:-20260804}"
ARCH="$(uname -m)"

die() { printf 'bundle-runtime: %s\n' "$*" >&2; exit 2; }
step() { printf '\n== %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --arch) ARCH="${2:-}"; [ -n "$ARCH" ] || die "--arch needs a value"; shift 2 ;;
    --clean) rm -r -f "$PAYLOAD"; echo "removed $PAYLOAD"; exit 0 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

case "$ARCH" in
  arm64|aarch64) PBS_ARCH="aarch64-apple-darwin"; ARCH="arm64" ;;
  x86_64)        PBS_ARCH="x86_64-apple-darwin" ;;
  *) die "unsupported arch: $ARCH (arm64 or x86_64)" ;;
esac

[ "$(uname -s)" = "Darwin" ] || die "macOS only -- this builds a .app payload"
command -v curl >/dev/null 2>&1 || die "curl not found"
command -v rsync >/dev/null 2>&1 || die "rsync not found"

mkdir -p "$CACHE"
rm -r -f "$PAYLOAD"
mkdir -p "$PAYLOAD"

# --------------------------------------------------------------------------
# 1. relocatable CPython
#
# install_only_stripped is the runtime-only, debug-symbol-free build: ~40MB
# extracted instead of ~180MB, and it is the variant python-build-standalone
# documents for redistribution. The archive is verified against the checksum
# the release publishes beside it -- a bundled interpreter is the most
# security-sensitive thing in this DMG and must never be taken on trust.
# --------------------------------------------------------------------------
step "python $PY_VERSION ($PBS_ARCH)"
TARBALL="cpython-${PY_VERSION}+${PBS_TAG}-${PBS_ARCH}-install_only_stripped.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${TARBALL}"
if [ ! -s "$CACHE/$TARBALL" ]; then
  echo "downloading $TARBALL"
  curl -fL --retry 3 -o "$CACHE/$TARBALL.part" "$URL" \
    || die "download failed: $URL"
  mv "$CACHE/$TARBALL.part" "$CACHE/$TARBALL"
else
  echo "cached: $CACHE/$TARBALL"
fi
# Checksums are ONE manifest per release (SHA256SUMS), not a sidecar per asset.
SUMS="$CACHE/SHA256SUMS-$PBS_TAG"
if [ ! -s "$SUMS" ]; then
  curl -fsL --retry 3 -o "$SUMS.part" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/SHA256SUMS" \
    || die "could not fetch SHA256SUMS for release $PBS_TAG"
  mv "$SUMS.part" "$SUMS"
fi
want="$(awk -v f="$TARBALL" '$2 == f || $2 == "*"f {print $1}' "$SUMS" | head -1)"
[ -n "$want" ] || die "SHA256SUMS for $PBS_TAG does not list $TARBALL -- refusing to bundle an unverified interpreter"
got="$(shasum -a 256 "$CACHE/$TARBALL" | awk '{print $1}')"
[ "$want" = "$got" ] || die "checksum mismatch for $TARBALL
    published: $want
    got:       $got
  Delete $CACHE/$TARBALL and re-run."
echo "checksum ok ($want)"

tar xzf "$CACHE/$TARBALL" -C "$PAYLOAD"
[ -d "$PAYLOAD/python" ] || die "archive did not contain python/"
PY="$PAYLOAD/python/bin/python3"
[ -x "$PY" ] || die "no interpreter at $PY"
echo "  $("$PY" -V 2>&1)"

# --------------------------------------------------------------------------
# 2. dependencies, installed INTO the bundled interpreter at BUILD time
#
# Not shipped as a wheelhouse to install on first launch. Installing at build
# time removes the entire class of first-run failures -- no pip, no resolver,
# no network, no compiler, no half-written venv to recover from -- and it means
# codesign covers every .so that will ever be imported, which is what a
# notarized, hardened-runtime app requires.
#
# Resolved with the bundled interpreter itself when the target arch matches the
# host, so the wheels are exactly the ones it would pick. Cross-building goes
# through an explicit --platform install into the same prefix.
# --------------------------------------------------------------------------
step "dependencies"
REQ="$UI/requirements.txt"
[ -f "$REQ" ] || die "no requirements.txt at $REQ"
SITE="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
if [ "$ARCH" = "$(uname -m | sed 's/aarch64/arm64/')" ]; then
  "$PY" -m pip install --quiet --no-input -r "$REQ" || die "pip install failed"
else
  PYTAG="${PY_VERSION%.*}"
  PLAT="macosx_11_0_$([ "$ARCH" = arm64 ] && echo arm64 || echo x86_64)"
  "$PY" -m pip install --quiet --no-input -r "$REQ" --target "$SITE" --upgrade \
    --only-binary=:all: --platform "$PLAT" --python-version "$PYTAG" \
    || die "cross-arch pip install failed for $PLAT"
fi
# Prove it imports NOW, in the build, rather than shipping a DMG that discovers
# a missing dependency on a stranger's machine.
"$PY" - <<'PYEOF' || die "bundled interpreter cannot import the runtime deps"
import importlib
for m in ("fastapi", "uvicorn", "websockets", "httpx", "bs4", "numpy"):
    mod = importlib.import_module(m)
    print("  %s %s" % (m, getattr(mod, "__version__", "?")))
PYEOF
# Byte-code is compiled here too: the bundle is read-only once signed, so a
# first launch that tried to write .pyc would silently fall back to recompiling
# every import, every time.
"$PY" -m compileall -q "$SITE" >/dev/null 2>&1 || true
# pip's own caches and the test suites are dead weight in a shipped bundle.
find "$PAYLOAD/python" -type d -name '__pycache__' -path '*/pip/*' -prune -exec rm -rf {} + 2>/dev/null || true
find "$PAYLOAD/python" -type d -name 'test' -o -type d -name 'tests' 2>/dev/null | grep -E 'lib/python3\.[0-9]+/(test|.*/tests?)$' | xargs rm -rf 2>/dev/null || true

# --------------------------------------------------------------------------
# 3. the plugin tree -- the panel AND the Claude Code plugin, one payload
#
# sutra-ui lives INSIDE the plugin, and org_api.py resolves its engine as
# parents[1]/"lib", so the directory shape is load-bearing: copy the plugin
# whole rather than flattening it. Excludes keep the developer's venv, the
# Electron toolchain and this payload itself out of the bundle.
# --------------------------------------------------------------------------
step "plugin payload"
mkdir -p "$PAYLOAD/plugin"
rsync -a --delete \
  --exclude 'sutra-ui/.venv/' \
  --exclude 'sutra-ui/electron/node_modules/' \
  --exclude 'sutra-ui/electron/node_modules' \
  --exclude 'sutra-ui/electron/dist/' \
  --exclude 'sutra-ui/electron/payload/' \
  --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.git/' --exclude '.DS_Store' \
  "$PLUGIN"/ "$PAYLOAD/plugin"/ || die "staging the plugin failed"
[ -f "$PAYLOAD/plugin/sutra-ui/app.py" ] || die "payload has no sutra-ui/app.py"
[ -f "$PAYLOAD/plugin/lib/placement_engine.py" ] || die "payload has no lib/placement_engine.py"
[ -f "$PAYLOAD/plugin/.claude-plugin/plugin.json" ] || die "payload has no plugin manifest"

# --------------------------------------------------------------------------
# 3b. SilverBullet sidecar binary -- the Files screen's engine (sb_sidecar.py).
#
# Pinned version + sha256, fail-closed: a tampered or drifted download must
# never ship. The zip's inner binary is named `silverbullet`; the payload
# renames it to the path sb_sidecar._bundled_binary() resolves. Offline DMG
# rule holds: the download is cached like the CPython tarball.
# --------------------------------------------------------------------------
step "silverbullet sidecar"
SB_VERSION="2.10.0"
case "$ARCH" in
  arm64)  SB_ZIP="silverbullet-server-darwin-aarch64.zip"
          SB_SHA256="3625a3c3b6fcdc1ca1bdbe57559c41c97b3bc642613d8d8d32d40013df648bc1" ;;
  x86_64) SB_ZIP="silverbullet-server-darwin-x86_64.zip"
          SB_SHA256="fd5aac2b006b8b58e38be5ee447441bec8a95f325c436814eb2d6eba8f468b41" ;;
esac
if [ -n "${SB_SHA256:-}" ]; then
  SB_URL="https://github.com/silverbulletmd/silverbullet/releases/download/${SB_VERSION}/${SB_ZIP}"
  mkdir -p "$CACHE"
  [ -f "$CACHE/$SB_ZIP" ] || curl -fsSL -o "$CACHE/$SB_ZIP" "$SB_URL" || die "silverbullet download failed"
  echo "$SB_SHA256  $CACHE/$SB_ZIP" | shasum -a 256 -c - >/dev/null 2>&1 \
    || die "silverbullet sha256 mismatch -- refusing to ship an unverified binary"
  mkdir -p "$PAYLOAD/sb"
  unzip -o -q "$CACHE/$SB_ZIP" silverbullet -d "$PAYLOAD/sb" || die "silverbullet unzip failed"
  mv -f "$PAYLOAD/sb/silverbullet" "$PAYLOAD/sb/silverbullet-server"
  chmod 0755 "$PAYLOAD/sb/silverbullet-server"
else
  # No pinned hash for this arch yet: build proceeds WITHOUT the sidecar and
  # the Files screen falls back to first-use download (sb_sidecar.ensure_binary,
  # itself fail-closed). Say so loudly rather than shipping silently less.
  echo "  !! no pinned SilverBullet sha256 for $ARCH -- payload ships without sidecar"
fi

# --------------------------------------------------------------------------
# 4. STAMP -- what the app compares against the staged copy to decide whether
#    a re-stage is needed. Content-addressed, so an edited checkout produces a
#    different stamp and the next launch re-stages instead of running stale code.
# --------------------------------------------------------------------------
step "stamp"
PLUGIN_VERSION="$("$PY" -c "
import json,sys
print(json.load(open('$PAYLOAD/plugin/.claude-plugin/plugin.json')).get('version','0.0.0'))" 2>/dev/null || echo 0.0.0)"
TREE_SHA="$(find "$PAYLOAD/plugin" -type f -print0 | sort -z \
  | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"
cat > "$PAYLOAD/STAMP" <<STAMP
{
  "plugin_version": "$PLUGIN_VERSION",
  "python": "$PY_VERSION",
  "pbs_tag": "$PBS_TAG",
  "arch": "$ARCH",
  "tree_sha256": "$TREE_SHA",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
STAMP
cat "$PAYLOAD/STAMP" | sed 's/^/  /'

step "summary"
du -sh "$PAYLOAD" | sed 's/^/  total  /'
for d in python plugin; do du -sh "$PAYLOAD/$d" | sed 's/^/  /'; done
echo
echo "next:  ./make-dmg.sh"
