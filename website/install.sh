#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# sutra install.sh — one-command installer for Sutra OS on Claude Code
#
# Usage:
#   curl -fsSL https://sutra.os/install.sh | bash
#
# What it does (idempotent — safe to re-run):
#   1. Detects OS (macOS / Linux). Windows users get pointed at WSL2.
#   2. Detects shell (zsh / bash) to pick the right rc file.
#   3. Installs Claude Code if missing (via Anthropic's installer).
#   4. Ensures $HOME/.local/bin is on PATH (idempotent rc edit).
#   5. Adds the Sutra marketplace: `claude plugin marketplace add sankalpasawa/sutra`.
#   6. Installs the plugin: `claude plugin install core@sutra`.
#   7. Merges the Sutra permission allowlist into ~/.claude/settings.local.json.
#   8. Writes a sentinel at ~/.sutra/installed-via-script so the SessionStart
#      hook can auto-activate /core:start on the first session.
#
# Environment:
#   SUTRA_INSTALL_VERBOSE=1   Print every step (set -x)
#
# Version: 0.1.0 (draft)
# Source:  https://github.com/sankalpasawa/sutra (served at https://sutra.os/install.sh)
# License: MIT
# -----------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------
SUTRA_VERSION="0.2.0"  # installer script version; plugin currently ships at v2.8.11
SUTRA_MARKETPLACE="sankalpasawa/sutra"
SUTRA_PLUGIN="core@sutra"
SUTRA_HOME="${HOME}/.sutra"
SUTRA_INSTALL_SENTINEL="${SUTRA_HOME}/installed-via-script"
CLAUDE_SETTINGS_DIR="${HOME}/.claude"
CLAUDE_SETTINGS_FILE="${CLAUDE_SETTINGS_DIR}/settings.local.json"
CURRENT_STEP="init"
LAST_CMD=""

if [[ "${SUTRA_INSTALL_VERBOSE:-0}" == "1" ]]; then
  set -x
fi

# -----------------------------------------------------------------------------
# Output helpers (no emojis per house style; stderr for logs)
# -----------------------------------------------------------------------------
log()  { printf '[sutra] %s\n' "$*" >&2; }
warn() { printf '[sutra][warn] %s\n' "$*" >&2; }
die()  { printf '[sutra][error] %s\n' "$*" >&2; exit 1; }
step() { CURRENT_STEP="$1"; log "--- $1 ---"; }

# -----------------------------------------------------------------------------
# Error trap — shows which step died and the last command's exit code.
# -----------------------------------------------------------------------------
on_error() {
  local ec=$?
  printf '\n[sutra][error] Install failed.\n' >&2
  printf '[sutra][error]   step: %s\n' "${CURRENT_STEP}" >&2
  printf '[sutra][error]   exit: %s\n' "${ec}" >&2
  printf '[sutra][error]   last: %s\n' "${LAST_CMD:-<unknown>}" >&2
  printf '[sutra][error] Re-run with SUTRA_INSTALL_VERBOSE=1 for detail.\n' >&2
  exit "${ec}"
}
trap 'LAST_CMD=${BASH_COMMAND}' DEBUG
trap on_error ERR

# -----------------------------------------------------------------------------
# OS + shell detection
# -----------------------------------------------------------------------------
detect_os() {
  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo unknown)"
  case "${uname_s}" in
    Darwin)  echo "macos" ;;
    Linux)   echo "linux" ;;
    MINGW*|MSYS*|CYGWIN*)
      die "Windows shells are not supported. Install WSL2 (https://learn.microsoft.com/windows/wsl/install) and re-run this script inside an Ubuntu WSL shell."
      ;;
    *)
      die "Unsupported OS: ${uname_s}. Sutra installs on macOS and Linux. Windows users: use WSL2."
      ;;
  esac
}

detect_shell_rc() {
  # Prefer the shell that invoked this script's parent, else $SHELL, else bash.
  local shell_name="${SHELL:-/bin/bash}"
  shell_name="$(basename "${shell_name}")"
  case "${shell_name}" in
    zsh)
      # zsh honors $ZDOTDIR if set.
      local zdot="${ZDOTDIR:-${HOME}}"
      echo "${zdot}/.zshrc"
      ;;
    bash)
      # macOS: prefer .bash_profile; Linux: .bashrc.
      if [[ "$(detect_os)" == "macos" && -f "${HOME}/.bash_profile" ]]; then
        echo "${HOME}/.bash_profile"
      elif [[ -f "${HOME}/.bashrc" ]]; then
        echo "${HOME}/.bashrc"
      else
        echo "${HOME}/.bashrc"
      fi
      ;;
    *)
      # Fall back to profile; user can relocate.
      echo "${HOME}/.profile"
      ;;
  esac
}

# -----------------------------------------------------------------------------
# PATH management — idempotent append of $HOME/.local/bin
# -----------------------------------------------------------------------------
ensure_path_in_rc() {
  local rc_file="$1"
  local line='export PATH="$HOME/.local/bin:$PATH"'
  local marker='# added by sutra install.sh (Claude Code PATH)'

  mkdir -p "$(dirname "${rc_file}")"
  touch "${rc_file}"

  if grep -Fq "${marker}" "${rc_file}" 2>/dev/null; then
    log "PATH entry already present in ${rc_file} — skipping."
    return 0
  fi

  if grep -Fq '$HOME/.local/bin' "${rc_file}" 2>/dev/null; then
    log "PATH to \$HOME/.local/bin already present in ${rc_file} — skipping."
    return 0
  fi

  {
    printf '\n%s\n' "${marker}"
    printf '%s\n' "${line}"
  } >> "${rc_file}"
  log "Appended PATH entry to ${rc_file}."
}

ensure_path_in_current_session() {
  case ":${PATH}:" in
    *":${HOME}/.local/bin:"*) : ;;
    *) export PATH="${HOME}/.local/bin:${PATH}" ;;
  esac
}

# -----------------------------------------------------------------------------
# Step 1 — Claude Code check/install
# -----------------------------------------------------------------------------
step_install_claude() {
  step "Step 1/5: Claude Code"
  local rc_file
  rc_file="$(detect_shell_rc)"

  if command -v claude >/dev/null 2>&1; then
    log "Claude Code already installed ($(command -v claude))."
  else
    log "Claude Code not found — installing via Anthropic installer."
    # Pipe through bash explicitly so set -e in parent shell doesn't fight sub-installer.
    if ! curl -fsSL https://claude.ai/install.sh | bash; then
      die "Claude Code install failed. See https://claude.com/claude-code for manual install."
    fi
  fi

  ensure_path_in_rc "${rc_file}"
  ensure_path_in_current_session

  if ! command -v claude >/dev/null 2>&1; then
    die "Claude Code still not on PATH after install. Open a new terminal (or run: source ${rc_file}) then re-run this installer."
  fi

  log "claude --version: $(claude --version 2>/dev/null || echo 'unknown')"
}

# -----------------------------------------------------------------------------
# Step 2 — marketplace add (idempotent)
# -----------------------------------------------------------------------------
step_marketplace_add() {
  step "Step 2/5: marketplace add"
  local out rc=0
  out="$(claude plugin marketplace add "${SUTRA_MARKETPLACE}" 2>&1)" || rc=$?

  if [[ ${rc} -eq 0 ]]; then
    log "Marketplace added: ${SUTRA_MARKETPLACE}"
    return 0
  fi

  # Common "already added" phrases — treat as success.
  if printf '%s' "${out}" | grep -iqE 'already (added|exists|present)|duplicate'; then
    log "Marketplace already added — continuing."
    return 0
  fi

  printf '%s\n' "${out}" >&2
  die "marketplace add failed (rc=${rc})."
}

# -----------------------------------------------------------------------------
# Step 3 — plugin install (idempotent)
# -----------------------------------------------------------------------------
step_plugin_install() {
  step "Step 3/5: plugin install"
  local out rc=0
  out="$(claude plugin install "${SUTRA_PLUGIN}" 2>&1)" || rc=$?

  if [[ ${rc} -eq 0 ]]; then
    log "Plugin installed: ${SUTRA_PLUGIN}"
    return 0
  fi

  if printf '%s' "${out}" | grep -iqE 'already (installed|present)'; then
    log "Plugin already installed — continuing."
    return 0
  fi

  printf '%s\n' "${out}" >&2
  die "plugin install failed (rc=${rc})."
}

# -----------------------------------------------------------------------------
# Step 4 — write permission allowlist to ~/.claude/settings.local.json
#
# Allowlist mirrors sutra/marketplace/plugin/PERMISSIONS.md (v1.5.1). Keep in
# sync by regenerating this installer when PERMISSIONS.md changes.
# -----------------------------------------------------------------------------
sutra_allow_entries_json() {
  # A JSON array literal — single source of truth for the allowlist.
  cat <<'JSON'
[
  "Bash(sutra:*)",
  "Bash(sutra)",
  "Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/*:*)",
  "Bash(claude plugin marketplace update sutra)",
  "Bash(claude plugin update core:*)",
  "Bash(claude plugin uninstall core:*)",
  "Write(.claude/sutra-project.json)",
  "Write(.claude/depth-registered)",
  "Write(.claude/input-routed)",
  "Write(.claude/sutra-deploy-depth5)",
  "Write(.claude/sutra-estimation.log)",
  "Write(.claude/logs/*)",
  "Bash(mkdir -p .claude*)"
]
JSON
}

write_settings_with_jq() {
  local settings_file="$1"
  local tmp
  tmp="$(mktemp "${settings_file}.XXXXXX")"

  # Start from existing file if present, else empty object.
  if [[ -s "${settings_file}" ]]; then
    cp "${settings_file}" "${tmp}"
  else
    printf '{}\n' > "${tmp}"
  fi

  # Merge: ensure .permissions.allow is an array, union with Sutra entries, dedupe.
  local merged
  merged="$(jq --argjson add "$(sutra_allow_entries_json)" '
    .permissions = (.permissions // {})
    | .permissions.allow = (((.permissions.allow // []) + $add) | unique)
  ' "${tmp}")"

  printf '%s\n' "${merged}" > "${settings_file}"
  rm -f "${tmp}"
}

write_settings_without_jq() {
  # Safe fallback: only proceed if the file is absent or empty. Never blind-edit
  # an existing non-empty JSON without jq — too easy to corrupt.
  local settings_file="$1"
  if [[ -s "${settings_file}" ]]; then
    die "jq not found and ${settings_file} already exists. Install jq (brew install jq / apt-get install jq) and re-run, or manually paste the snippet from https://github.com/sankalpasawa/sutra/blob/main/marketplace/plugin/PERMISSIONS.md"
  fi

  # Fresh file: emit a minimal valid JSON with the Sutra allowlist.
  local allow
  allow="$(sutra_allow_entries_json)"
  cat > "${settings_file}" <<EOF
{
  "permissions": {
    "allow": ${allow}
  }
}
EOF
}

step_write_permissions() {
  step "Step 4/5: permissions allowlist"
  mkdir -p "${CLAUDE_SETTINGS_DIR}"

  if command -v jq >/dev/null 2>&1; then
    write_settings_with_jq "${CLAUDE_SETTINGS_FILE}"
    log "Allowlist merged into ${CLAUDE_SETTINGS_FILE} (via jq)."
  else
    warn "jq not found — using minimal-write fallback."
    write_settings_without_jq "${CLAUDE_SETTINGS_FILE}"
    log "Allowlist written to ${CLAUDE_SETTINGS_FILE}."
  fi
}

# -----------------------------------------------------------------------------
# Step 5 — sentinel for first-session auto-activation
# -----------------------------------------------------------------------------
step_write_sentinel() {
  step "Step 5/5: first-run sentinel"
  mkdir -p "${SUTRA_HOME}"
  date +%s > "${SUTRA_INSTALL_SENTINEL}"
  log "Sentinel written: ${SUTRA_INSTALL_SENTINEL}"
}

# -----------------------------------------------------------------------------
# Final banner
# -----------------------------------------------------------------------------
print_banner() {
  CURRENT_STEP="banner"
  cat <<'BANNER'

--------------------------------------------------------------------
Sutra installed.

Open Claude Code in any project directory:

    cd your/project && claude

First session will auto-activate Sutra. Subsequent sessions are silent.

Docs:     https://github.com/sankalpasawa/sutra
Support:  https://github.com/sankalpasawa/sutra/issues
--------------------------------------------------------------------
BANNER
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  CURRENT_STEP="preflight"
  log "Sutra installer v${SUTRA_VERSION}"
  local os
  os="$(detect_os)"
  log "OS: ${os}"
  log "Shell rc: $(detect_shell_rc)"

  step_install_claude
  step_marketplace_add
  step_plugin_install
  step_write_permissions
  step_write_sentinel
  print_banner
}

main "$@"
