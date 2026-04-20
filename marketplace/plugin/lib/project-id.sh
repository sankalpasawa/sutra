#!/bin/bash
# Sutra: project-id.sh — compute install_id + project_id.
# Per codex review 2026-04-20: reuse TELEMETRY-CONTRACT.md spec for install_id,
# add project_id for repo-level grouping.
#
# install_id = sha256(HOME + sutra_version)[:16]
# project_id = sha256(git-remote-url)[:12], fallback sha256(realpath(cwd)+USER)[:12]

_sha256_short() {
  # Portable, defensive hash. Tries python3 first (guaranteed on macOS 13+,
  # most linux distros); falls back to shasum (macOS) then sha256sum (linux).
  # Returns empty only if all three fail.
  local n="${1:-12}"
  local input="${2:-}"
  local hash=""
  if command -v python3 >/dev/null 2>&1; then
    hash=$(printf '%s' "$input" | python3 -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())" 2>/dev/null)
  fi
  if [ -z "$hash" ] && command -v shasum >/dev/null 2>&1; then
    hash=$(printf '%s' "$input" | shasum -a 256 2>/dev/null | cut -d' ' -f1)
  fi
  if [ -z "$hash" ] && command -v sha256sum >/dev/null 2>&1; then
    hash=$(printf '%s' "$input" | sha256sum 2>/dev/null | cut -d' ' -f1)
  fi
  printf '%s' "${hash:0:$n}"
}

compute_install_id() {
  local version="${1:-unknown}"
  _sha256_short 16 "${HOME}:${version}"
}

compute_project_id() {
  local remote
  remote=$(git config --get remote.origin.url 2>/dev/null || echo "")
  if [ -n "$remote" ]; then
    # Normalize: strip scheme (https:// or git@), trailing .git, SSH colon→slash, trailing slash
    # sed -E uses | for alternation (bare, not escaped)
    remote=$(printf '%s' "$remote" | sed -E 's|^https?://||; s|^git@||; s|\.git$||; s|:|/|; s|/$||')
    _sha256_short 12 "git:${remote}"
  else
    local path
    path=$(pwd -P 2>/dev/null || pwd)
    _sha256_short 12 "path:${path}:${USER:-unknown}"
  fi
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  VER="${1:-1.0.0}"
  echo "install_id: $(compute_install_id "$VER")"
  echo "project_id: $(compute_project_id)"
fi
