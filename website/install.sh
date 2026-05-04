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
#   0. (macOS only) Ensures Xcode Command Line Tools are installed before any
#      git invocation. On a fresh Mac /usr/bin/git is a stub that triggers a
#      GUI dialog on first use; without this pre-flight, marketplace add
#      fails with a cryptic rc=1. Polls until CLT is ready (max 20 min) or
#      gives clean re-run instructions on timeout.
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
#  10. Runs `sutra start` against the target directory — handles the telemetry
#      consent prompt + writes .claude/sutra-project.json — OUTSIDE of claude
#      so the user gets one prompt during install, not a nested prompt
#      inside their first claude session.
#  11. Auto-launches `claude` in the target directory. Founder direction
#      2026-05-04 ("include sutra start and start claude. Include them by
#      default"). Robust handoff: `stty sane` + full /dev/tty reattach for
#      stdin/stdout/stderr before exec — closes the keystroke-drop hang
#      observed under macOS Terminal.app. --no-launch opts out.
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
SUTRA_VERSION="0.5.0"  # this installer's version (NOT the plugin's — see header)
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
NO_LAUNCH=0
TOTAL_STEPS=8

if [[ "${SUTRA_INSTALL_VERBOSE:-0}" == "1" ]]; then
  set -x
fi

# -----------------------------------------------------------------------------
# ANSI color palette — modeled on Native installer (sutra/website/native/install.sh)
#
# Auto-disabled when neither stdout nor stderr is a TTY (piped logs) or when
# NO_COLOR is set (https://no-color.org). Most prints go to stderr so we
# enable colors if EITHER channel is interactive — codex P2-A fold (gating
# only on `-t 1` would wrongly disable colors when stdout is redirected but
# stderr stays interactive, which is the common `... 2>&1 | tee` shape).
# -----------------------------------------------------------------------------
if { [ -t 1 ] || [ -t 2 ]; } && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'
  C_DIM=$'\033[2m'
  C_BOLD=$'\033[1m'
  C_GOLD=$'\033[38;5;179m'
  C_BLUE=$'\033[38;5;75m'
  C_GREEN=$'\033[38;5;78m'
  C_RED=$'\033[38;5;203m'
  C_GREY=$'\033[38;5;245m'
else
  C_RESET= C_DIM= C_BOLD= C_GOLD= C_BLUE= C_GREEN= C_RED= C_GREY=
fi

# -----------------------------------------------------------------------------
# Output helpers (no emojis per house style; stderr for logs unless noted)
# -----------------------------------------------------------------------------
say()  { printf '%s\n' "$*"; }                                                                # stdout, no prefix
log()  { printf '%s[sutra]%s %s\n' "$C_GREY" "$C_RESET" "$*" >&2; }                           # routine info
ok()   { printf '%s[sutra]%s %s ok %s %s\n' "$C_GREY" "$C_RESET" "$C_GREEN" "$C_RESET" "$*" >&2; }
warn() { printf '%s[sutra]%s %swarn%s %s\n' "$C_GREY" "$C_RESET" "$C_GOLD" "$C_RESET" "$*" >&2; }
die()  { printf '%s[sutra]%s %sfail%s %s\n' "$C_GREY" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2; exit 1; }
step() { CURRENT_STEP="$1"; printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$1" "$C_RESET" >&2; }
hr()   { printf '%s%s%s\n' "$C_GREY" "------------------------------------------------------------" "$C_RESET" >&2; }

# -----------------------------------------------------------------------------
# ASCII banner — printed once at the start of main(). Doubles as version-label
# clarification: "installer script v0.3.0 · plugin: latest from marketplace"
# closes founder confusion (2026-05-04, "why does it say 0.2.0?") that 0.x
# refers to the installer, not the Sutra plugin (currently v2.27.0+).
# -----------------------------------------------------------------------------
banner() {
  printf '%s' "$C_GOLD"
  cat <<'BANNER'

   ____        _
  / ___| _   _| |_ _ __ __ _
  \___ \| | | | __| '__/ _` |
   ___) | |_| | |_| | | (_| |
  |____/ \__,_|\__|_|  \__,_|
BANNER
  printf '%s\n' "$C_RESET"
  printf '  %sSutra OS%s — chief of staff for founders building with Claude Code.\n' \
    "$C_BOLD" "$C_RESET"
  printf '  %sinstaller script v%s · will install latest %score@sutra%s from marketplace%s\n\n' \
    "$C_GREY" "$SUTRA_VERSION" "$C_GOLD" "$C_GREY" "$C_RESET"
}

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
# macOS Command Line Tools pre-flight
#
# On a fresh Mac, /usr/bin/git is a stub. The first `git` invocation triggers
# a GUI dialog asking the user to install Command Line Tools (CLT). Without
# this pre-flight, marketplace add (Step 3) calls `git clone` internally and
# the user gets a confusing dialog mid-install with rc=1 if they don't
# complete it. Detect missing CLT up-front, trigger the install with clear
# scope/size messaging, and poll until ready.
#
# Detection uses `xcode-select -p` (cheap, no side effects) — NOT `git
# --version`, which itself triggers the dialog and would defeat the purpose.
#
# No-op on Linux + when CLT or full Xcode is already present. Honors
# NON_INTERACTIVE (-y) by failing loudly instead of triggering a GUI dialog
# that nobody is there to accept.
# -----------------------------------------------------------------------------
ensure_macos_clt() {
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  if xcode-select -p >/dev/null 2>&1; then
    return 0
  fi

  if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
    die "macOS Command Line Tools missing — required for git. Run: xcode-select --install (wait for GUI to finish), then re-run this installer."
  fi

  log ""
  warn "macOS Command Line Tools not detected (required for git)."
  log "  Marketplace add calls 'git clone' under the hood; without CLT it"
  log "  would fail mid-install with a cryptic GUI dialog. Triggering the"
  log "  CLT install now."
  log ""
  log "  Size:   ~700 MB download · ~2-3 GB installed · 5-15 min"
  log "  Scope:  CLT only (git, clang, make) — NOT full Xcode IDE (~15 GB)"
  log "  After:  install resumes automatically when CLT finishes."
  log ""

  # Triggers the GUI dialog and returns immediately. Non-zero return is
  # informational (e.g. CLT already installed — we already checked, so this
  # case is rare; or no GUI subsystem on a headless Mac).
  xcode-select --install 2>&1 | sed 's/^/[sutra]   /' >&2 || true

  log ""
  log "Polling for CLT completion (every 15s, max 20 min)..."
  log "  Accept the GUI dialog. Ctrl+C is safe — re-running this installer is idempotent."
  log ""

  local i=0
  local max=80   # 80 * 15s = 20 min
  while [[ ${i} -lt ${max} ]]; do
    if xcode-select -p >/dev/null 2>&1; then
      ok "Command Line Tools ready: $(xcode-select -p)"
      return 0
    fi
    sleep 15
    i=$((i+1))
    if [[ $((i % 4)) -eq 0 ]]; then
      printf '%s[sutra]   waiting... %dm elapsed (max 20m)%s\n' "${C_GREY}" $((i/4)) "${C_RESET}" >&2
    fi
  done

  warn "Timed out waiting for Command Line Tools (20 min)."
  warn "  Once the GUI install finishes, re-run:"
  warn "    curl -fsSL https://sankalpasawa.github.io/sutra/install.sh | bash"
  die "aborting — re-run after CLT install completes."
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
  -y, --yes          Non-interactive: reuse existing dir, skip sutra start + claude launch
                     (precedence: -y always wins — automation safety)
  --no-launch        Skip the auto-launch step (still runs sutra start). Use when
                     you want to inspect the install before opening claude, or
                     when curl|bash → exec claude misbehaves on your terminal.
  -h, --help         Print this help and exit

Environment:
  SUTRA_TARGET_DIR=<path>   Override target directory (default ./sutra)
  SUTRA_INSTALL_VERBOSE=1   Print every step (set -x)

What it does (idempotent — safe to re-run):
  1. Picks ./sutra (or -d <path>); if it exists, asks (S)tay / (N)ew / (A)bort.
  2. Installs Claude Code if missing (Anthropic installer).
  3. Adds the Sutra marketplace (refreshes cache to latest catalog).
  4. Installs OR updates the core@sutra plugin.
  5. Writes the first-run sentinel.
  6. Merges the Sutra permission allowlist into ~/.claude/settings.local.json.
  7. Runs `sutra start` (telemetry consent + project onboarding outside claude).
  8. Auto-launches `claude` in the target directory (founder direction
     2026-05-04 "include them by default"). Robust hand-off via stty sane +
     full /dev/tty re-attach. Skip with --no-launch.

Re-runs safely from any state: marketplace already added → continues + refreshes;
plugin already installed → updates to latest; sentinel re-armed; permissions deduped.

Source: https://github.com/sankalpasawa/sutra
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--yes) NON_INTERACTIVE=1 ;;
      --no-launch) NO_LAUNCH=1 ;;
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
    ok "Created: ${TARGET_DIR}"
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
          ok "Created: ${TARGET_DIR}"
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
    ok "Claude Code already installed ($(command -v claude))."
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
    ok "Marketplace added: ${SUTRA_MARKETPLACE}"
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
    ok "Plugin installed: ${SUTRA_PLUGIN}"
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
    [[ -n "${latest_version}" ]] && ok "Active core@sutra version: v${latest_version}"
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
    ok "Allowlist merged into ${CLAUDE_SETTINGS_FILE} (via jq)."
  elif command -v python3 >/dev/null 2>&1; then
    log "jq not found — using python3 to merge JSON."
    if write_settings_with_python "${CLAUDE_SETTINGS_FILE}"; then
      ok "Allowlist merged into ${CLAUDE_SETTINGS_FILE} (via python3)."
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
  ok "Sentinel written: ${SUTRA_INSTALL_SENTINEL}"
}

# -----------------------------------------------------------------------------
# Step 7 — sutra start (telemetry consent + project onboarding outside claude)
#
# Founder direction 2026-05-04 ("include sutra start and start claude.
# Include them by default"): runs `bin/sutra start` against the target dir
# so onboarding happens DURING install, not as a nested prompt inside the
# user's first claude session. Idempotent — sutra start is a no-op when
# .claude/sutra-project.json already exists.
#
# Resolves the plugin's bin/sutra by globbing the install cache. Falls
# back to a soft skip with hint if the binary can't be located (cache
# layout drift, sparse install, etc.). Skipped under -y (automation) or
# when /dev/tty is unavailable (sutra start is interactive).
# -----------------------------------------------------------------------------
resolve_sutra_bin() {
  # Most common: ~/.claude/plugins/cache/sutra/core/<version>/bin/sutra
  # Take the latest version if multiple exist (last-segment sort).
  local candidate
  candidate=$(ls -1 "${HOME}/.claude/plugins/cache/sutra/core"/*/bin/sutra 2>/dev/null | sort -V | tail -1)
  if [[ -n "${candidate}" && -x "${candidate}" ]]; then
    printf '%s' "${candidate}"
    return 0
  fi
  # Defensive fallback — older / alternate cache shapes.
  for candidate in \
    "${HOME}/.claude/plugins/cache/sankalpasawa/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/cache/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/marketplaces/sankalpasawa/sutra/marketplace/plugin/bin/sutra"
  do
    [[ -x "${candidate}" ]] && { printf '%s' "${candidate}"; return 0; }
  done
  return 1
}

step_sutra_start() {
  step "Step 7/${TOTAL_STEPS}: sutra start (telemetry consent + onboarding)"

  if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
    log "Non-interactive (-y) — skipping sutra start (will fire on first claude session)."
    return 0
  fi

  local sutra_bin
  if ! sutra_bin=$(resolve_sutra_bin); then
    warn "Could not locate plugin bin/sutra — skipping sutra start."
    warn "  Run /core:start once you're inside claude to onboard the project."
    return 0
  fi

  if ! has_tty; then
    log "No usable /dev/tty — skipping interactive sutra start."
    log "  /core:start will fire on first claude session via SessionStart hook."
    return 0
  fi

  log "Resolved: ${sutra_bin}"
  log "Running sutra start in ${TARGET_DIR} (telemetry prompt may appear)..."
  log ""

  # Run from the target dir; reattach stdin to /dev/tty for the consent prompt.
  # Captures exit code; non-zero is a soft warning (claude can still run /core:start).
  if ( cd "${TARGET_DIR}" && "${sutra_bin}" start </dev/tty ); then
    ok "sutra start completed"
  else
    warn "sutra start exited non-zero — re-run /core:start inside claude if needed."
  fi
}

# -----------------------------------------------------------------------------
# Step 8 — auto-launch Claude Code (default ON; --no-launch opts out)
#
# Founder direction 2026-05-04 ("include them by default"): reverses the
# v0.3.0 print-only default. The keystroke-drop hang in v0.2.0 was caused
# by an incomplete fd handoff — `exec </dev/tty; exec claude` redirected
# only stdin (fd 0) but claude's interactive UI also uses fd 1 (output)
# and fd 2 (raw mode tcsetattr ioctl). Robust v0.4.0 handoff:
#   1. `stty sane </dev/tty` resets canonical mode + sane echo/erase
#   2. `exec claude </dev/tty >/dev/tty 2>/dev/tty` reattaches all 3 fds
#      AND replaces the script process in one syscall — claude inherits
#      a clean tty for input, output, AND control.
#
# Skipped when:
#   * NON_INTERACTIVE (-y) — automation safety
#   * NO_LAUNCH (--no-launch) — explicit opt-out
#   * claude not on PATH — install must have failed silently; print hint
#   * /dev/tty unopenable — headless / sandboxed; print hint
# -----------------------------------------------------------------------------
step_launch_claude() {
  step "Step 8/${TOTAL_STEPS}: launch Claude Code"

  local hint_cmd="cd ${TARGET_DIR} && claude"

  if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
    log "Non-interactive (-y) — skipping launch."
    log "  Next: ${hint_cmd}"
    return 0
  fi

  if [[ ${NO_LAUNCH} -eq 1 ]]; then
    log "--no-launch — skipping launch."
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

  log ""
  log "Launching Claude Code (sutra start completed; project onboarded)..."
  log "  If keystrokes don't reach claude (rare): Ctrl+C twice, then run: ${hint_cmd}"
  log ""

  # Robust handoff: stty sane resets terminal mode; the 3-fd redirect
  # AND exec happen in one syscall so claude inherits a clean tty for
  # input/output/control. Trap chain is dropped on exec(), which is fine
  # — all on-disk state (sentinel, settings, sutra-project.json) was
  # committed in earlier steps.
  cd "${TARGET_DIR}"
  stty sane </dev/tty 2>/dev/null || true
  exec claude </dev/tty >/dev/tty 2>/dev/tty
}

# -----------------------------------------------------------------------------
# Final banner — canonical "Sutra ready, here's the next step" surface
# (codex P2-C fold: this is the single source of next-step guidance;
# step_launch_claude no-ops on the default path so there's no duplication).
# Always printed unless `--launch` opts in to exec claude AND the exec
# succeeds (in which case the banner above is the user's last reference
# before claude takes over the terminal).
# -----------------------------------------------------------------------------
print_banner() {
  CURRENT_STEP="banner"
  say ""
  hr
  printf '  %s%s ok %s  %s%sSutra installed%s\n' \
    "$C_GREEN" "$C_BOLD" "$C_RESET" "$C_BOLD" "" "$C_RESET" >&2
  hr
  printf '  %sProject directory:%s %s\n\n' "$C_BOLD" "$C_RESET" "${TARGET_DIR}" >&2
  printf '  %sNext — open Claude Code in your project:%s\n\n' "$C_BOLD" "$C_RESET" >&2
  printf '    %scd %s && claude%s\n\n' "$C_GOLD" "${TARGET_DIR}" "$C_RESET" >&2
  printf '  First session auto-fires %s/core:start%s.\n' "$C_GOLD" "$C_RESET" >&2
  printf '  %sRe-running this installer is safe — marketplace + plugin update to latest.%s\n\n' \
    "$C_GREY" "$C_RESET" >&2
  printf '  %sDocs:%s     https://github.com/sankalpasawa/sutra\n' "$C_GREY" "$C_RESET" >&2
  printf '  %sSupport:%s  https://github.com/sankalpasawa/sutra/issues\n' "$C_GREY" "$C_RESET" >&2
  hr
  say ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  parse_args "$@"

  banner   # ASCII Sutra art + version-label clarification (replaces the old plain log line)

  CURRENT_STEP="preflight"
  local os
  os="$(detect_os)"
  log "OS: ${os}"
  log "Shell rc: $(detect_shell_rc)"
  log "Target dir: ${TARGET_DIR}"

  # macOS-only: ensure Xcode Command Line Tools are present BEFORE any step
  # that invokes git. Without this, marketplace add (which calls `git clone`
  # internally) would fail mid-install with a GUI dialog the user may not
  # complete in time. No-op on Linux and when CLT is already installed.
  ensure_macos_clt

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
  step_sutra_start
  # Print the banner THEN exec claude. The banner is the user's last visual
  # reference before claude takes over the terminal (under default auto-launch),
  # or their explicit hint to paste manually (under -y / --no-launch / no tty).
  print_banner
  step_launch_claude
}

main "$@"
