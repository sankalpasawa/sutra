#!/bin/bash
# Sutra plugin — identity.sh (v1.9.0+)
# Captures user + machine identity for the manifest.json > identity block.
#
# Design: single tier ("attributed") applied to every install with telemetry_optin=true.
# Users opt out entirely by flipping telemetry_optin=false in .claude/sutra-project.json.
#
# Fields:
#   git_user_name, git_user_email_hash, github_login, github_id,
#   hostname_hash, os_name, os_version, os_pretty, arch, shell_name,
#   locale, tz, captured_at, captured_by_version
#
# Fallback chain for name:  git → gh → GECOS → $USER
# Fallback chain for email: git → $EMAIL → gh public
# Every capture step is best-effort; nothing fails the caller.
#
# Usage:
#   source identity.sh
#   capture_identity <plugin_version>    → emits JSON to stdout
#   identity_is_stale <path> [max_age_s] → returns 0 if file older than max_age (default 7d)

set -u

# ─── Helpers ──────────────────────────────────────────────────────────

_have() { command -v "$1" >/dev/null 2>&1; }

# sha256 of $2, first $1 hex chars. Empty on total fallback failure.
_identity_hash() {
  local n="${1:-16}"
  local input="${2:-}"
  [ -z "$input" ] && return 0
  local hash=""
  if _have python3; then
    hash=$(printf '%s' "$input" | python3 -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest())" 2>/dev/null)
  fi
  if [ -z "$hash" ] && _have shasum; then
    hash=$(printf '%s' "$input" | shasum -a 256 2>/dev/null | cut -d' ' -f1)
  fi
  if [ -z "$hash" ] && _have sha256sum; then
    hash=$(printf '%s' "$input" | sha256sum 2>/dev/null | cut -d' ' -f1)
  fi
  printf '%s' "${hash:0:$n}"
}

# JSON-escape a value for inline embedding. Uses python3 when available
# (handles all unicode + escape rules); falls back to a minimal sed.
_json_escape() {
  local v="${1:-}"
  if [ -z "$v" ]; then
    printf 'null'
    return
  fi
  if _have python3; then
    printf '%s' "$v" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null
  else
    # Minimal fallback: escape backslash, double-quote, newline, tab
    local esc
    esc=$(printf '%s' "$v" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' ' | tr '\t' ' ')
    printf '"%s"' "$esc"
  fi
}

# ─── Individual capture functions (each returns empty on miss) ────────

_cap_git_name() {
  _have git || return 0
  # Try global first, then any scope (local/system) as fallback
  local v
  v=$(git config --global --get user.name 2>/dev/null | head -1)
  [ -z "$v" ] && v=$(git config --get user.name 2>/dev/null | head -1)
  printf '%s' "$v"
}

_cap_git_email() {
  _have git || return 0
  local v
  v=$(git config --global --get user.email 2>/dev/null | head -1)
  [ -z "$v" ] && v=$(git config --get user.email 2>/dev/null | head -1)
  printf '%s' "$v"
}

_cap_gh_login() {
  _have gh || return 0
  # Non-blocking: gh may prompt or hit network; cap to 3s.
  if _have timeout; then
    timeout 3 gh api user --jq .login 2>/dev/null
  else
    gh api user --jq .login 2>/dev/null
  fi
}

_cap_gh_id() {
  _have gh || return 0
  if _have timeout; then
    timeout 3 gh api user --jq .id 2>/dev/null
  else
    gh api user --jq .id 2>/dev/null
  fi
}

_cap_gh_name() {
  _have gh || return 0
  if _have timeout; then
    timeout 3 gh api user --jq '.name // empty' 2>/dev/null
  else
    gh api user --jq '.name // empty' 2>/dev/null
  fi
}

# GECOS full-name fallback (macOS `id -F`, linux getent)
_cap_system_fullname() {
  if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && _have id; then
    id -F "$USER" 2>/dev/null | head -1
  elif _have getent; then
    getent passwd "$USER" 2>/dev/null | cut -d: -f5 | cut -d, -f1
  fi
}

# Full identify_user chain: git → gh → GECOS → $USER → empty
_identify_user_name() {
  local v
  v=$(_cap_git_name); [ -n "$v" ] && { printf '%s' "$v"; return; }
  v=$(_cap_gh_name);  [ -n "$v" ] && { printf '%s' "$v"; return; }
  v=$(_cap_system_fullname); [ -n "$v" ] && { printf '%s' "$v"; return; }
  printf '%s' "${USER:-}"
}

_identify_user_email() {
  local v
  v=$(_cap_git_email); [ -n "$v" ] && { printf '%s' "$v"; return; }
  v="${EMAIL:-}";      [ -n "$v" ] && { printf '%s' "$v"; return; }
  # gh only returns email if user's email is PUBLIC on GitHub
  if _have gh; then
    if _have timeout; then
      v=$(timeout 3 gh api user --jq '.email // empty' 2>/dev/null)
    else
      v=$(gh api user --jq '.email // empty' 2>/dev/null)
    fi
    [ -n "$v" ] && [ "$v" != "null" ] && { printf '%s' "$v"; return; }
  fi
  printf ''
}

_cap_hostname() {
  local v
  v=$(hostname 2>/dev/null); [ -n "$v" ] && { printf '%s' "$v"; return; }
  printf '%s' "${HOST:-${HOSTNAME:-}}"
}

_cap_os_name() { uname -s 2>/dev/null; }

_cap_os_version() {
  if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && _have sw_vers; then
    sw_vers -productVersion 2>/dev/null
  else
    uname -r 2>/dev/null
  fi
}

_cap_os_pretty() {
  if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && _have sw_vers; then
    local name ver
    name=$(sw_vers -productName 2>/dev/null)
    ver=$(sw_vers -productVersion 2>/dev/null)
    [ -n "$name" ] && [ -n "$ver" ] && printf '%s %s' "$name" "$ver"
  elif [ -f /etc/os-release ]; then
    . /etc/os-release 2>/dev/null
    printf '%s' "${PRETTY_NAME:-}"
  fi
}

_cap_arch() { uname -m 2>/dev/null; }

_cap_shell_name() {
  local s="${SHELL:-}"
  [ -n "$s" ] && basename "$s" 2>/dev/null
}

_cap_locale() {
  local v="${LANG:-${LC_ALL:-${LC_CTYPE:-}}}"
  [ -n "$v" ] && { printf '%s' "$v"; return; }
  _have locale && locale 2>/dev/null | grep '^LANG=' | head -1 | cut -d= -f2 | tr -d '"'
}

_cap_tz() {
  # Abbrev + offset, e.g. "IST+0530" or "PDT-0700"
  local abbrev offset
  abbrev=$(date +%Z 2>/dev/null)
  offset=$(date +%z 2>/dev/null)
  if [ -n "$abbrev" ] && [ -n "$offset" ]; then
    printf '%s%s' "$abbrev" "$offset"
  elif [ -n "$offset" ]; then
    printf '%s' "$offset"
  fi
}

# ─── Public API ───────────────────────────────────────────────────────

# capture_identity <plugin_version>
# Emits a JSON object with all captured identity fields. No newlines in values.
capture_identity() {
  local plugin_version="${1:-unknown}"

  local name email email_hash
  name=$(_identify_user_name)
  email=$(_identify_user_email)
  email_hash=""
  [ -n "$email" ] && email_hash=$(_identity_hash 16 "$email")

  local gh_login gh_id
  gh_login=$(_cap_gh_login)
  gh_id=$(_cap_gh_id)

  local host host_hash
  host=$(_cap_hostname)
  host_hash=""
  [ -n "$host" ] && host_hash=$(_identity_hash 12 "$host")

  local os_name os_version os_pretty arch shell_name locale tz
  os_name=$(_cap_os_name)
  os_version=$(_cap_os_version)
  os_pretty=$(_cap_os_pretty)
  arch=$(_cap_arch)
  shell_name=$(_cap_shell_name)
  locale=$(_cap_locale)
  tz=$(_cap_tz)

  local captured_at
  captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  if _have python3; then
    # Pass all values via argv to avoid heredoc/escape pitfalls.
    python3 - \
      "$captured_at" "$plugin_version" \
      "$name" "$email_hash" "$gh_login" "$gh_id" \
      "$host_hash" "$os_name" "$os_version" "$os_pretty" \
      "$arch" "$shell_name" "$locale" "$tz" <<'PY'
import json, sys
a = sys.argv[1:]
def s(i):
    return a[i] if i < len(a) and a[i] != "" else None
def n(i):
    v = a[i] if i < len(a) else ""
    try:
        return int(v) if v else None
    except ValueError:
        return None
d = {
  "captured_at": s(0),
  "captured_by_version": s(1),
  "git_user_name": s(2),
  "git_user_email_hash": s(3),
  "github_login": s(4),
  "github_id": n(5),
  "hostname_hash": s(6),
  "os_name": s(7),
  "os_version": s(8),
  "os_pretty": s(9),
  "arch": s(10),
  "shell_name": s(11),
  "locale": s(12),
  "tz": s(13),
}
print(json.dumps(d, indent=2))
PY
  else
    # Minimal fallback if python3 missing (rare on modern mac/linux).
    # Numeric gh_id or null
    local gh_id_json="null"
    case "$gh_id" in
      ''|*[!0-9]*) gh_id_json="null" ;;
      *) gh_id_json="$gh_id" ;;
    esac
    cat <<JSON
{
  "captured_at": $(_json_escape "$captured_at"),
  "captured_by_version": $(_json_escape "$plugin_version"),
  "git_user_name": $(_json_escape "$name"),
  "git_user_email_hash": $(_json_escape "$email_hash"),
  "github_login": $(_json_escape "$gh_login"),
  "github_id": $gh_id_json,
  "hostname_hash": $(_json_escape "$host_hash"),
  "os_name": $(_json_escape "$os_name"),
  "os_version": $(_json_escape "$os_version"),
  "os_pretty": $(_json_escape "$os_pretty"),
  "arch": $(_json_escape "$arch"),
  "shell_name": $(_json_escape "$shell_name"),
  "locale": $(_json_escape "$locale"),
  "tz": $(_json_escape "$tz")
}
JSON
  fi
}

# identity_is_stale <path> [max_age_seconds]
# Returns 0 (stale → recapture) if file missing or older than max_age.
# Default max_age = 604800 (7 days).
identity_is_stale() {
  local path="${1:-}"
  local max_age="${2:-604800}"
  [ -z "$path" ] || [ ! -f "$path" ] && return 0
  local now mtime age
  now=$(date +%s 2>/dev/null)
  # GNU stat (linux) uses -c %Y; BSD stat (macOS) uses -f %m
  mtime=$(stat -f %m "$path" 2>/dev/null || stat -c %Y "$path" 2>/dev/null)
  [ -z "$mtime" ] && return 0
  age=$((now - mtime))
  [ "$age" -gt "$max_age" ]
}

# When sourced: functions are available. When executed directly: capture + print.
if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
  capture_identity "${1:-unknown}"
fi
