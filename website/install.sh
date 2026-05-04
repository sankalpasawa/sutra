#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# sutra install.sh — one-line end-to-end onboarding for Sutra OS on Claude Code
#
# Usage:
#   curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash
#   curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash -s -- -y
#   curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash -s -- -d ~/work/foo
#
# What it does (idempotent — safe to re-run):
#   1. Picks a project directory (default ./sutra). If it already exists,
#      asks (S)tay / (N)ew name / (A)bort. Override via -d <dir> or
#      $SUTRA_TARGET_DIR; -y reuses silently.
#   2. Detects OS (macOS / Linux). Windows users get pointed at WSL2.
#   3. Detects shell (zsh / bash) to pick the right rc file.
#   4. Installs Claude Code if missing (via Anthropic's installer).
#   5. Ensures $HOME/.local/bin is on PATH (idempotent rc edit).
#   6. Adds the Sutra marketplace: `claude plugin marketplace add sankalpasawa/sutra`
#      (refreshes cache to latest catalog so re-runs pull the newest core@sutra).
#   7. Installs or UPDATES the plugin: `claude plugin install core@sutra`
#      (already-installed → `claude plugin update core@sutra`).
#   8. Writes a sentinel at ~/.sutra/installed-via-script so the SessionStart
#      hook auto-activates /core:start on the first session in this project.
#   9. Merges the Sutra permission allowlist into ~/.claude/settings.local.json.
#  10. Launches `claude` inside the chosen directory. The SessionStart hook
#      fires /core:start; the just-installed plugin loads from cache. No
#      manual /reload-plugins needed.
#
# Re-run semantics (founder direction 2026-05-04, "the person might have used
# it once, so you re-run everything"): every step is idempotent. Folder exists
# → ask. Marketplace exists → continue + refresh. Plugin exists → update to
# latest. Sentinel re-armed. Permissions deduped. Then exec claude fresh.
#
# Environment:
#   SUTRA_TARGET_DIR=<path>   Override target directory (default ./sutra)
#   SUTRA_INSTALL_VERBOSE=1   Print every step (set -x)
#
# Flags (after `bash -s --`):
#   -d, --dir <path>   Target directory (overrides $SUTRA_TARGET_DIR + default)
#   -y, --yes          Non-interactive: reuse existing dir, skip claude launch
#   -h, --help         Print this header and exit
#
# Version: 0.2.0  (label only — `claude plugin install` always pulls the latest
#                  catalog version; pin is informational. Plugin: v2.19.0+.)
# Source:  https://github.com/sankalpasawa/sutra (served at https://sankalpasawa.github.io/sutra/install.sh)
# License: MIT
# -----------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------
SUTRA_VERSION="0.2.0"  # this installer's version (NOT the plugin's — see header)
SUTRA_MARKETPLACE="sankalpasawa/sutra"   # source spec for `marketplace add` (GitHub path)
SUTRA_MARKETPLACE_NAME="sutra"           # registered name in Claude (from marketplace.json .name)
SUTRA_PLUGIN="core@sutra"
SUTRA_HOME="${HOME}/.sutra"
SUTRA_INSTALL_SENTINEL="${SUTRA_HOME}/installed-via-script"
CLAUDE_SETTINGS_DIR="${HOME}/.claude"
CLAUDE_SETTINGS_FILE="${CLAUDE_SETTINGS_DIR}/settings.local.json"
CURRENT_STEP="init"
LAST_CMD=""

# Target-directory selection state (resolved in step_select_target)
TARGET_DIR=""
NON_INTERACTIVE=0
TOTAL_STEPS=7

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
# TTY availability — `[ -e /dev/tty ]` is NOT enough
#
# Codex review 2026-05-04: the character device may exist (and `ls -l` shows
# it) but be unopenable in headless contexts: `ssh -T host`, CI runners,
# containers without `--tty` allocation, sandboxed exec environments. The
# only reliable test is to actually open it. We do this in a subshell so a
# failed open exits the subshell (returning non-zero) without killing us.
# -----------------------------------------------------------------------------
has_tty() {
  ( exec 9</dev/tty ) 2>/dev/null
}

# -----------------------------------------------------------------------------
# Argument parsing — flags after `bash -s --`
# -----------------------------------------------------------------------------
print_help() {
  # Embedded heredoc — under `curl ... | bash -s -- -h`, $0 is "bash" and
  # the script body is read from stdin (already consumed). Reading $0 with
  # awk/sed would print the bash binary, not this header. Constant text is
  # the only reliable form. Keep this in sync with the comment header above.
  cat <<'USAGE'
Sutra installer — one-line end-to-end onboarding for Sutra OS on Claude Code

Usage:
  curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash
  curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash -s -- -y
  curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash -s -- -d ~/work/foo

Flags (after `bash -s --`):
  -d, --dir <path>   Target directory (overrides $SUTRA_TARGET_DIR + default ./sutra)
  -y, --yes          Non-interactive: reuse existing dir, skip claude launch
  -h, --help         Print this help and exit

Environment:
  SUTRA_TARGET_DIR=<path>   Override target directory (default ./sutra)
  SUTRA_INSTALL_VERBOSE=1   Print every step (set -x)

What it does (idempotent — safe to re-run):
  1. Picks ./sutra (or -d <path>); if it exists, asks (S)tay / (N)ew / (A)bort.
  2. Installs Claude Code if missing (Anthropic installer).
  3. Adds the Sutra marketplace (refreshes cache to latest catalog).
  4. Installs OR updates the core@sutra plugin.
  5. Writes the first-run sentinel; the SessionStart hook auto-fires /core:start.
  6. Merges the Sutra permission allowlist into ~/.claude/settings.local.json.
  7. Launches `claude` inside the chosen directory (skipped under -y / no claude / no tty).

Re-runs safely from any state: marketplace already added → continues + refreshes;
plugin already installed → updates to latest; sentinel re-armed; permissions deduped.

Source: https://github.com/sankalpasawa/sutra
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--yes) NON_INTERACTIVE=1 ;;
      -d|--dir)
        shift
        # Reject empty AND reject flag-shaped next tokens (e.g. `-d --yes`)
        # so a missing argument is loud instead of silently swallowing the
        # next flag as the directory name.
        [[ -n "${1:-}" ]] || die "-d/--dir requires a path argument."
        [[ "${1}" == -* ]] && die "-d/--dir got a flag (${1}), expected a path."
        TARGET_DIR="$1"
        ;;
      -h|--help)
        print_help
        exit 0
        ;;
      *)
        die "unknown flag: $1 — try -h for help."
        ;;
    esac
    shift
  done

  # Resolve precedence: -d flag > $SUTRA_TARGET_DIR > default ./sutra
  if [[ -z "${TARGET_DIR}" ]]; then
    TARGET_DIR="${SUTRA_TARGET_DIR:-${PWD}/sutra}"
  fi

  # Resolve to absolute path (no tilde or relative).
  case "${TARGET_DIR}" in
    /*) ;;
    "~"|"~/"*) TARGET_DIR="${HOME}${TARGET_DIR#\~}" ;;
    *) TARGET_DIR="${PWD}/${TARGET_DIR}" ;;
  esac
}

# -----------------------------------------------------------------------------
# Step 1 — pick the project directory
#
# Founder direction 2026-05-04: "if the folder already exists, ask the user if
# they want to go into the same folder or update into a new folder."
#
# Behavior:
#   * doesn't exist            → mkdir + cd
#   * exists, NON_INTERACTIVE  → reuse silently
#   * exists, interactive      → prompt (S)tay / (N)ew name / (A)bort
#
# /dev/tty is required for interactive prompts under `curl ... | bash` (the
# pipe owns stdin). If /dev/tty is unavailable (CI / non-tty container), we
# default to silent reuse — the only safe non-destructive choice — and warn.
# -----------------------------------------------------------------------------
step_select_target() {
  step "Step 1/${TOTAL_STEPS}: project directory"

  if [[ ! -e "${TARGET_DIR}" ]]; then
    mkdir -p "${TARGET_DIR}"
    log "Created: ${TARGET_DIR}"
  else
    if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
      log "Folder exists, reusing (non-interactive): ${TARGET_DIR}"
    elif ! has_tty; then
      warn "No usable /dev/tty (headless / CI / container) — reusing existing folder: ${TARGET_DIR}"
      warn "  (re-run with -d <path> to install into a different directory)"
    else
      log "Folder already exists: ${TARGET_DIR}"
      printf '[sutra] (S)tay in this folder / (N)ew folder name / (A)bort? [S/n/a] ' >&2
      local reply=""
      read -r reply </dev/tty || reply="s"
      case "${reply:-s}" in
        [Aa]*)
          die "aborted at directory selection."
          ;;
        [Nn]*)
          local new_name=""
          printf '[sutra] new folder name (relative to %s, or absolute path): ' "${PWD}" >&2
          read -r new_name </dev/tty || new_name=""
          [[ -z "${new_name}" ]] && die "no name given — aborting."
          # Re-resolve with the same precedence as parse_args.
          case "${new_name}" in
            /*)        TARGET_DIR="${new_name}" ;;
            "~"|"~/"*) TARGET_DIR="${HOME}${new_name#\~}" ;;
            *)         TARGET_DIR="${PWD}/${new_name}" ;;
          esac
          if [[ -e "${TARGET_DIR}" ]]; then
            die "${TARGET_DIR} also exists — re-run and pick another name."
          fi
          mkdir -p "${TARGET_DIR}"
          log "Created: ${TARGET_DIR}"
          ;;
        *)
          log "Reusing existing folder: ${TARGET_DIR}"
          ;;
      esac
    fi
  fi

  cd "${TARGET_DIR}"
  log "cwd: ${PWD}"
}

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
  step "Step 2/${TOTAL_STEPS}: Claude Code"
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
  step "Step 3/${TOTAL_STEPS}: marketplace add"
  local out rc=0
  out="$(claude plugin marketplace add "${SUTRA_MARKETPLACE}" 2>&1)" || rc=$?

  if [[ ${rc} -eq 0 ]]; then
    log "Marketplace added: ${SUTRA_MARKETPLACE}"
  elif printf '%s' "${out}" | grep -iqE 'already (added|exists|present)|duplicate'; then
    log "Marketplace already added — continuing."
  else
    printf '%s\n' "${out}" >&2
    die "marketplace add failed (rc=${rc})."
  fi

  # Always refresh the marketplace cache after add. Without this, a returning
  # user (whose cache pre-dates the latest release) gets the cached version of
  # core@sutra at install/update time, not the actual latest. Idempotent.
  log "Refreshing marketplace cache to latest catalog…"
  # Update by registered name (from marketplace.json .name), not the GitHub source
  # spec — `claude plugin marketplace update` rejects the latter with "not found".
  if ! claude plugin marketplace update "${SUTRA_MARKETPLACE_NAME}" 2>&1 | sed 's/^/[sutra]   /' >&2; then
    warn "marketplace update returned non-zero (continuing — install/update step may still pull latest)."
  fi
}

# -----------------------------------------------------------------------------
# Step 3 — plugin install (idempotent)
# -----------------------------------------------------------------------------
step_plugin_install() {
  step "Step 4/${TOTAL_STEPS}: plugin install or update"
  local out rc=0
  out="$(claude plugin install "${SUTRA_PLUGIN}" 2>&1)" || rc=$?

  if [[ ${rc} -eq 0 ]]; then
    log "Plugin installed: ${SUTRA_PLUGIN}"
  elif printf '%s' "${out}" | grep -iqE 'already (installed|present)'; then
    # Returning user — bump to whatever the just-refreshed marketplace cache
    # advertises. Without this, the user keeps whatever version was on disk,
    # which is exactly the bug founder reported (curl|bash kept stale plugin).
    log "Plugin already installed — updating to latest…"
    local up_out up_rc=0
    up_out="$(claude plugin update "${SUTRA_PLUGIN}" 2>&1)" || up_rc=$?
    printf '%s\n' "${up_out}" | sed 's/^/[sutra]   /' >&2
    if [[ ${up_rc} -ne 0 ]]; then
      warn "plugin update returned non-zero (rc=${up_rc}) — your local plugin may still be at a prior version. Try: claude plugin update ${SUTRA_PLUGIN}"
    fi
  else
    printf '%s\n' "${out}" >&2
    die "plugin install failed (rc=${rc})."
  fi

  # Final visibility: print the version we ended up at so users see what they got.
  local plugin_dir="${HOME}/.claude/plugins/cache/sutra/core"
  if [[ -d "${plugin_dir}" ]]; then
    local latest_version
    latest_version=$(ls -1 "${plugin_dir}" 2>/dev/null | sort -V | tail -1)
    [[ -n "${latest_version}" ]] && log "Active core@sutra version: v${latest_version}"
  fi
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

write_settings_with_python() {
  # Python 3 ships with macOS (>= 12, via /usr/bin/python3 stub) and most Linux
  # distros, so this covers the common returning-user case where jq is missing
  # and ~/.claude/settings.local.json already exists from prior Claude Code use.
  local settings_file="$1"
  local tmp
  tmp="$(mktemp "${settings_file}.XXXXXX")"
  local allow_json
  allow_json="$(sutra_allow_entries_json)"

  if ! python3 - "${settings_file}" "${tmp}" "${allow_json}" <<'PY'
import json, os, sys
src, dst, add_json = sys.argv[1], sys.argv[2], sys.argv[3]
add_entries = json.loads(add_json)

if os.path.exists(src) and os.path.getsize(src) > 0:
    try:
        with open(src) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"existing {src} is not valid JSON: {e}\n")
        sys.exit(2)
else:
    data = {}

if not isinstance(data, dict):
    sys.stderr.write(f"{src} root is not a JSON object\n")
    sys.exit(2)

perms = data.setdefault("permissions", {})
if not isinstance(perms, dict):
    sys.stderr.write(".permissions exists but is not an object\n")
    sys.exit(2)

allow = perms.setdefault("allow", [])
if not isinstance(allow, list):
    sys.stderr.write(".permissions.allow exists but is not an array\n")
    sys.exit(2)

seen = set(allow)
for item in add_entries:
    if item not in seen:
        allow.append(item)
        seen.add(item)
perms["allow"] = allow

with open(dst, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
  then
    rm -f "${tmp}"
    return 1
  fi
  mv "${tmp}" "${settings_file}"
  return 0
}

write_settings_fresh() {
  # Last-resort fallback: only safe when no existing file. Used when neither
  # jq nor python3 is available AND settings.local.json doesn't yet exist.
  local settings_file="$1"
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
  step "Step 6/${TOTAL_STEPS}: permissions allowlist"
  mkdir -p "${CLAUDE_SETTINGS_DIR}"

  if command -v jq >/dev/null 2>&1; then
    write_settings_with_jq "${CLAUDE_SETTINGS_FILE}"
    log "Allowlist merged into ${CLAUDE_SETTINGS_FILE} (via jq)."
  elif command -v python3 >/dev/null 2>&1; then
    log "jq not found — using python3 to merge JSON."
    if write_settings_with_python "${CLAUDE_SETTINGS_FILE}"; then
      log "Allowlist merged into ${CLAUDE_SETTINGS_FILE} (via python3)."
    else
      die "JSON merge failed. Install jq (brew install jq / apt-get install jq) and re-run, or manually paste the snippet from https://github.com/sankalpasawa/sutra/blob/main/marketplace/plugin/PERMISSIONS.md"
    fi
  elif [[ ! -s "${CLAUDE_SETTINGS_FILE}" ]]; then
    warn "Neither jq nor python3 found — writing fresh settings file."
    write_settings_fresh "${CLAUDE_SETTINGS_FILE}"
    log "Allowlist written to ${CLAUDE_SETTINGS_FILE}."
  else
    die "Neither jq nor python3 found, and ${CLAUDE_SETTINGS_FILE} already exists. Install one of: jq (brew install jq / apt-get install jq) or python3, then re-run. Or manually paste the snippet from https://github.com/sankalpasawa/sutra/blob/main/marketplace/plugin/PERMISSIONS.md"
  fi
}

# -----------------------------------------------------------------------------
# Step 4 — sentinel for first-session auto-activation
#
# Runs BEFORE step_write_permissions on purpose: if permissions writing
# hard-fails (no jq + no python3), the sentinel still exists, so the user's
# next Claude Code session auto-fires /core:start and they get a usable
# experience even from a partial install.
# -----------------------------------------------------------------------------
step_write_sentinel() {
  step "Step 5/${TOTAL_STEPS}: first-run sentinel"
  mkdir -p "${SUTRA_HOME}"
  date +%s > "${SUTRA_INSTALL_SENTINEL}"
  log "Sentinel written: ${SUTRA_INSTALL_SENTINEL}"
}

# -----------------------------------------------------------------------------
# Step 7 — launch Claude Code inside the chosen directory
#
# Founder direction 2026-05-04: "you directly launch it." The folder selection
# in step 1 was the consent moment; do not ask a second time. Skip only when:
#   * NON_INTERACTIVE (-y) — caller is scripting, return control with hint
#   * `claude` not on PATH — install must have failed silently; warn + hint
#   * /dev/tty unavailable — exec'ing claude without a TTY would hang
#
# We `exec </dev/tty` to re-attach stdin (the curl pipe owns stdin until now)
# and then `exec claude` so the script process is replaced — claude inherits a
# clean process tree and the install pipe terminates cleanly. After exec the
# script does not return.
# -----------------------------------------------------------------------------
step_launch_claude() {
  step "Step 7/${TOTAL_STEPS}: launch Claude Code"

  local hint_cmd="cd ${TARGET_DIR} && claude"

  if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
    log "Non-interactive (-y) — skipping launch."
    log "  Next: ${hint_cmd}"
    return 0
  fi

  if ! command -v claude >/dev/null 2>&1; then
    warn "claude not on PATH after install — open a new terminal, then:"
    warn "  ${hint_cmd}"
    return 0
  fi

  if ! has_tty; then
    warn "No usable /dev/tty (headless / CI / container) — cannot launch claude."
    warn "  Next: ${hint_cmd}"
    return 0
  fi

  log "Launching Claude Code in ${TARGET_DIR}."
  log "  /core:start auto-fires on the first session via the sentinel."
  log ""

  # Reattach to TTY (curl|bash owns stdin) and exec claude so the script
  # process is replaced — clean handoff, no orphan bash hanging around.
  # has_tty above already proved /dev/tty is openable, so the redirect
  # below cannot hard-fail the script. Trap chain is dropped on exec(),
  # which is fine: the script's only on-disk state (sentinel, settings)
  # was committed in earlier steps.
  cd "${TARGET_DIR}"
  exec </dev/tty
  exec claude
}

# -----------------------------------------------------------------------------
# Final banner — only printed when launch is skipped (NON_INTERACTIVE / no
# claude / no tty). When `exec claude` succeeds in step_launch_claude, this
# is never reached.
# -----------------------------------------------------------------------------
print_banner() {
  CURRENT_STEP="banner"
  cat <<BANNER

--------------------------------------------------------------------
Sutra installed.

Project directory: ${TARGET_DIR}

Open Claude Code there:

    cd ${TARGET_DIR} && claude

First session will auto-activate Sutra (/core:start). Subsequent
sessions are silent. Re-running this installer is safe — marketplace
+ plugin will update to the latest catalog version.

Docs:     https://github.com/sankalpasawa/sutra
Support:  https://github.com/sankalpasawa/sutra/issues
--------------------------------------------------------------------
BANNER
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  parse_args "$@"

  CURRENT_STEP="preflight"
  log "Sutra installer v${SUTRA_VERSION}"
  local os
  os="$(detect_os)"
  log "OS: ${os}"
  log "Shell rc: $(detect_shell_rc)"
  log "Target dir: ${TARGET_DIR}"

  step_select_target
  step_install_claude
  step_marketplace_add
  step_plugin_install
  # Sentinel BEFORE permissions: if step_write_permissions hard-fails (e.g.
  # neither jq nor python3 available), the sentinel is already written so the
  # next Claude Code session still auto-activates /core:start. Without this,
  # a partial install leaves the user with a fully-functional plugin but no
  # auto-activation, and they get the full pre-activation governance noise on
  # every turn forever (vinit#8 evidence + asawa@Rameshs report 2026-05-01).
  step_write_sentinel
  step_write_permissions
  # Print the fallback banner THEN attempt to exec claude. If the launch
  # exec's, the banner is the user's last printed reference. If the launch
  # is skipped (-y / no claude / no tty), the banner is the explicit hint.
  print_banner
  step_launch_claude
}

main "$@"
