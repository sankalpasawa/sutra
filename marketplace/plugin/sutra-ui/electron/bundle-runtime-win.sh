#!/usr/bin/env bash
# bundle-runtime-win.sh -- build the WINDOWS payload/ for the Sutra .exe.
#
# The Windows counterpart of bundle-runtime.sh. Runs in Git Bash on a
# `windows-latest` GitHub runner (curl + tar are present; rsync/unzip are NOT,
# so this uses cp + rm and tar-extracts the node .zip via Windows' bundled
# bsdtar). Produces payload/ with the SAME shape resolveRuntime expects, except
# the Windows interpreter layout has no bin/ symlinks:
#
#     payload/python/python.exe        (astral-sh/python-build-standalone, msvc)
#     payload/node/node.exe            (nodejs.org win-x64)
#     payload/plugin/...               (the Sutra plugin tree, deps installed)
#     payload/wincompat/...            (POSIX import shims, put on PYTHONPATH win)
#     payload/STAMP                    (diagnostics)
#
# Versions are pinned to match the macOS bundle so the two channels ship the
# same interpreter and node. x64 only for now (arm64-Windows CPython from
# python-build-standalone is far less proven -- deferred).
set -euo pipefail

die() { printf 'bundle-runtime-win: %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s ==\n' "$*"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI="$(cd "$HERE/.." && pwd)"                 # marketplace/plugin/sutra-ui
PLUGIN="$(cd "$UI/.." && pwd)"               # marketplace/plugin
PAYLOAD="$HERE/payload"
CACHE="$HERE/.cache-win"
mkdir -p "$CACHE"

PY_VERSION="${SUTRA_PY_VERSION:-3.12.14}"
PBS_TAG="${SUTRA_PBS_TAG:-20260901}"
NODE_VERSION="${SUTRA_NODE_VERSION:-24.20.0}"
ARCH="x64"

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v tar  >/dev/null 2>&1 || die "tar not found (need Windows bsdtar)"

rm -rf "$PAYLOAD"
mkdir -p "$PAYLOAD"

# --------------------------------------------------------------------------
# 1. CPython (python-build-standalone, install_only, msvc x64)
# --------------------------------------------------------------------------
step "python $PY_VERSION (x86_64-pc-windows-msvc)"
PY_TARBALL="cpython-${PY_VERSION}+${PBS_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PY_TARBALL}"
if [ ! -f "$CACHE/$PY_TARBALL" ]; then
  curl -fL --retry 3 -o "$CACHE/$PY_TARBALL.part" "$PY_URL" || die "python download failed: $PY_URL"
  mv "$CACHE/$PY_TARBALL.part" "$CACHE/$PY_TARBALL"
fi
# Checksum-verify against the release SHA256SUMS (fail closed on a bad download).
SUMS="$CACHE/SHA256SUMS-$PBS_TAG"
[ -f "$SUMS" ] || curl -fsL --retry 3 -o "$SUMS" \
  "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/SHA256SUMS" \
  || die "could not fetch SHA256SUMS for $PBS_TAG"
want="$(grep " ${PY_TARBALL}\$" "$SUMS" | awk '{print $1}' | head -1)"
[ -n "$want" ] || die "SHA256SUMS does not list $PY_TARBALL -- refusing an unverified interpreter"
got="$(sha256sum "$CACHE/$PY_TARBALL" | awk '{print $1}')"
[ "$want" = "$got" ] || die "python checksum mismatch: want $want got $got"
tar -xzf "$CACHE/$PY_TARBALL" -C "$PAYLOAD"    # -> payload/python/python.exe
PY="$PAYLOAD/python/python.exe"
[ -f "$PY" ] || die "expected $PY after extract; layout changed?"
"$PY" --version || die "bundled python does not run"

# --------------------------------------------------------------------------
# 2. The plugin tree (panel + Claude Code plugin), then its Python deps
# --------------------------------------------------------------------------
step "plugin payload"
mkdir -p "$PAYLOAD/plugin"
cp -R "$PLUGIN"/. "$PAYLOAD/plugin"/ || die "copying the plugin failed"
# Prune what the mac rsync excludes -- dev/build artifacts that must not ship.
rm -rf \
  "$PAYLOAD/plugin/sutra-ui/.venv" \
  "$PAYLOAD/plugin/sutra-ui/electron/node_modules" \
  "$PAYLOAD/plugin/sutra-ui/electron/dist" \
  "$PAYLOAD/plugin/sutra-ui/electron/dist-win" \
  "$PAYLOAD/plugin/sutra-ui/electron/payload" \
  "$PAYLOAD/plugin/sutra-ui/electron/.cache-win"
find "$PAYLOAD/plugin" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$PAYLOAD/plugin" -type f -name '*.pyc' -delete 2>/dev/null || true
[ -f "$PAYLOAD/plugin/sutra-ui/app.py" ] || die "payload has no sutra-ui/app.py"
[ -f "$PAYLOAD/plugin/.claude-plugin/plugin.json" ] || die "payload has no plugin manifest"

step "python deps"
REQ="$UI/requirements.txt"
[ -f "$REQ" ] || die "no requirements.txt at $REQ"
"$PY" -m pip install --quiet --no-input --upgrade pip || true
"$PY" -m pip install --quiet --no-input -r "$REQ" || die "pip install failed (a Windows wheel may be missing)"

# --------------------------------------------------------------------------
# 3. Node (nodejs.org win-x64 zip; bsdtar extracts .zip)
# --------------------------------------------------------------------------
step "node $NODE_VERSION (win-x64)"
NODE_ZIP="node-v${NODE_VERSION}-win-x64.zip"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ZIP}"
if [ ! -f "$CACHE/$NODE_ZIP" ]; then
  curl -fL --retry 3 -o "$CACHE/$NODE_ZIP.part" "$NODE_URL" || die "node download failed: $NODE_URL"
  mv "$CACHE/$NODE_ZIP.part" "$CACHE/$NODE_ZIP"
fi
NODE_SUM="$(curl -fsL --retry 3 "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" \
  | grep " ${NODE_ZIP}\$" | awk '{print $1}' | head -1)" || true
if [ -n "$NODE_SUM" ]; then
  got="$(sha256sum "$CACHE/$NODE_ZIP" | awk '{print $1}')"
  [ "$NODE_SUM" = "$got" ] || die "node checksum mismatch: want $NODE_SUM got $got"
fi
tmp="$CACHE/node-extract"; rm -rf "$tmp"; mkdir -p "$tmp"
tar -xf "$CACHE/$NODE_ZIP" -C "$tmp"          # -> node-v<ver>-win-x64/
mkdir -p "$PAYLOAD/node"
cp -R "$tmp/node-v${NODE_VERSION}-win-x64"/. "$PAYLOAD/node"/ || die "staging node failed"
[ -f "$PAYLOAD/node/node.exe" ] || die "payload has no node/node.exe"

# --------------------------------------------------------------------------
# 4. wincompat import shims (put FIRST on PYTHONPATH on Windows by main.js)
# --------------------------------------------------------------------------
step "wincompat shims"
cp -R "$HERE/wincompat" "$PAYLOAD/wincompat" || die "copying wincompat shims failed"
[ -f "$PAYLOAD/wincompat/fcntl.py" ] || die "wincompat/fcntl.py missing"

# --------------------------------------------------------------------------
# 5. STAMP
# --------------------------------------------------------------------------
step "stamp"
PLUGIN_VERSION="$("$PY" -c "import json;print(json.load(open(r'$PAYLOAD/plugin/.claude-plugin/plugin.json')).get('version','0.0.0'))" 2>/dev/null || echo 0.0.0)"
cat > "$PAYLOAD/STAMP" <<STAMP
{
  "plugin_version": "$PLUGIN_VERSION",
  "python": "$PY_VERSION",
  "node": "$NODE_VERSION",
  "pbs_tag": "$PBS_TAG",
  "arch": "$ARCH",
  "platform": "win32",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
STAMP
cat "$PAYLOAD/STAMP"

step "summary"
du -sh "$PAYLOAD" 2>/dev/null | sed 's/^/  total  /' || true
echo "next: npx electron-builder --win"
