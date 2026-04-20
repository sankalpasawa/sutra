#!/bin/bash
# Sutra: project-id.sh — compute install_id + project_id.
# Per codex review 2026-04-20: reuse TELEMETRY-CONTRACT.md spec for install_id,
# add project_id for repo-level grouping.
#
# install_id = sha256(HOME + sutra_version)[:16]
# project_id = sha256(git-remote-url)[:12], fallback sha256(realpath(cwd)+USER)[:12]

_sha256_short() {
  local n="$1" input="$2"
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$input" | shasum -a 256 | awk -v n="$n" '{print substr($1,1,n)}'
  else
    printf '%s' "$input" | sha256sum | awk -v n="$n" '{print substr($1,1,n)}'
  fi
}

compute_install_id() {
  local version="${1:-unknown}"
  _sha256_short 16 "${HOME}:${version}"
}

compute_project_id() {
  local remote
  remote=$(git config --get remote.origin.url 2>/dev/null || echo "")
  if [ -n "$remote" ]; then
    remote=$(printf '%s' "$remote" | sed -E 's|^(https?://\|git@)||; s|\.git$||; s|:|/|; s|/$||')
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
