#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# asawa join.sh — one-line onboarding for a NON-TECHNICAL operator joining
# Asawa Inc.'s working repo.
#
# Usage:
#   curl -fsSL https://sankalpasawa.github.io/sutra/join.sh | bash
#   curl -fsSL https://sankalpasawa.github.io/sutra/join.sh | bash -s -- -y
#   curl -fsSL https://sankalpasawa.github.io/sutra/join.sh | bash -s -- -h
#
# What it does (idempotent — safe to re-run any number of times):
#   1. Checks the basic tools (git, curl). On macOS, makes sure Xcode Command
#      Line Tools are usable BEFORE the first git call (fresh Macs ship a git
#      stub that pops a GUI dialog). Same pre-flight as install.sh.
#   2. Installs Claude Code if missing (Anthropic's installer), and makes sure
#      $HOME/.local/bin is on PATH.
#   3. Installs the GitHub command-line tool (gh) if missing — brew on macOS,
#      clear instructions elsewhere. Also installs rtk and jq quietly (both
#      non-fatal; jq is what the Sutra add-on's own setup needs).
#   4. Connects the operator's GitHub account (gh auth login) if not already
#      connected, explaining in plain words what is about to happen.
#   5. Downloads the company files to $HOME/Claude/asawa-holding. If they are
#      already there and are the right project, it updates instead. If the
#      folder holds something else, it stops and changes nothing.
#   6. Downloads the shared parts (git submodules), rewriting any SSH submodule
#      address to HTTPS first so an operator with no SSH key still succeeds.
#   7. Puts the operator's name and email on their changes — read automatically
#      from their GitHub account, set for THIS project only (never global).
#   8. Writes a safety setting so Claude always asks before it acts, and makes
#      sure that file can never be committed by accident.
#   9. Adds the Sutra add-on for Claude Code and runs its setup.
#  Then prints exactly one next action.
#
# It NEVER installs or loads a background job (no launchd, no launchctl, no
# cron). Nothing here schedules anything.
#
# Environment:
#   JOIN_VERBOSE=1   Print every command (set -x)
#
# Flags (after `bash -s --`):
#   -y, --yes    Don't ask anything. If the GitHub account is not already
#                connected, stop with a clear message instead of prompting.
#   -h, --help   Print this help and exit
#
# Version: 1.0.0
# Source:  https://github.com/sankalpasawa/sutra
#          (served at https://sankalpasawa.github.io/sutra/join.sh)
# License: MIT
# -----------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------
JOIN_VERSION="1.0.0"
JOIN_REPO="sankalpasawa/asawa-holding"
JOIN_REPO_CANON="github.com/sankalpasawa/asawa-holding"
JOIN_HTTPS_URL="https://github.com/sankalpasawa/asawa-holding.git"
TARGET_DIR="${HOME}/Claude/asawa-holding"

SUTRA_MARKETPLACE="sankalpasawa/sutra"   # source spec for `marketplace add`
SUTRA_MARKETPLACE_NAME="sutra"           # registered name in Claude
SUTRA_PLUGIN="core@sutra"

CURRENT_STEP="init"
LAST_CMD=""
NON_INTERACTIVE=0
TOTAL_STEPS=9

GH_LOGIN=""
GH_EMAIL=""

if [[ "${JOIN_VERBOSE:-0}" == "1" ]]; then
  set -x
fi

# -----------------------------------------------------------------------------
# ANSI color palette — copied verbatim from install.sh lines 101-112 so the two
# scripts look identical in a terminal. Auto-disabled when neither stdout nor
# stderr is a TTY (piped logs) or when NO_COLOR is set (https://no-color.org).
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
# Output helpers — copied verbatim from install.sh lines 117-123 (say/log/ok/
# warn/die/step/hr). Same prefixes, same stderr routing, same colors, so a
# person who has seen install.sh reads this script without relearning anything.
# -----------------------------------------------------------------------------
say()  { printf '%s\n' "$*"; }                                                                # stdout, no prefix
log()  { printf '%s[join]%s %s\n' "$C_GREY" "$C_RESET" "$*" >&2; }                            # routine info
ok()   { printf '%s[join]%s %s ok %s %s\n' "$C_GREY" "$C_RESET" "$C_GREEN" "$C_RESET" "$*" >&2; }
warn() { printf '%s[join]%s %swarn%s %s\n' "$C_GREY" "$C_RESET" "$C_GOLD" "$C_RESET" "$*" >&2; }
die()  { printf '%s[join]%s %sstop%s %s\n' "$C_GREY" "$C_RESET" "$C_RED" "$C_RESET" "$*" >&2; exit 1; }
step() { CURRENT_STEP="$1"; printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$1" "$C_RESET" >&2; }
hr()   { printf '%s%s%s\n' "$C_GREY" "------------------------------------------------------------" "$C_RESET" >&2; }

# -----------------------------------------------------------------------------
# Error trap — same shape as install.sh lines 151-161. Shows which step died
# and the last command's exit code, in words a non-technical reader can relay.
# -----------------------------------------------------------------------------
on_error() {
  local ec=$?
  printf '\n[join][stopped] Setup did not finish.\n' >&2
  printf '[join][stopped]   where: %s\n' "${CURRENT_STEP}" >&2
  printf '[join][stopped]   code:  %s\n' "${ec}" >&2
  printf '[join][stopped]   last:  %s\n' "${LAST_CMD:-<unknown>}" >&2
  printf '[join][stopped] Nothing is broken. Send the four lines above to whoever gave you this link.\n' >&2
  printf '[join][stopped] You can safely run the same one-line command again at any time.\n' >&2
  exit "${ec}"
}
trap 'LAST_CMD=${BASH_COMMAND}' DEBUG
trap on_error ERR

# -----------------------------------------------------------------------------
# TTY availability — copied from install.sh lines 172-174. `[ -e /dev/tty ]` is
# NOT enough: the device can exist but be unopenable (ssh -T, CI, containers
# without a tty). The only reliable test is to actually open it, in a subshell
# so a failed open doesn't kill us.
# -----------------------------------------------------------------------------
has_tty() {
  ( exec 9</dev/tty ) 2>/dev/null
}

# -----------------------------------------------------------------------------
# Run an interactive command attached to the REAL terminal device.
#
# Same handoff install.sh uses at lines 946-966: resolve the real device with
# `tty </dev/tty` (returns /dev/ttysNNN on macOS, /dev/pts/N on Linux) and put
# all three file descriptors on it. Never put fd 1/2 on the /dev/tty ALIAS —
# macOS kqueue rejects it (EINVAL) and modern interactive CLIs crash.
# Falls back to stdin-only reattach when fd 1/2 are already real terminal fds
# (the normal `curl | bash` shape: only stdin is the pipe).
#
# Returns 97 when no terminal can be attached, so callers can fail loudly with
# a plain-language message instead of hanging.
# -----------------------------------------------------------------------------
run_on_terminal() {
  local real_tty=""
  real_tty="$(tty </dev/tty 2>/dev/null || true)"
  if [[ -n "${real_tty}" && "${real_tty}" != "not a tty" && "${real_tty}" == /dev/* && -c "${real_tty}" ]]; then
    stty sane <"${real_tty}" 2>/dev/null || true
    "$@" <"${real_tty}" >"${real_tty}" 2>"${real_tty}"
  elif [[ -t 1 && -t 2 ]]; then
    stty sane </dev/tty 2>/dev/null || true
    "$@" </dev/tty
  else
    return 97
  fi
}

# -----------------------------------------------------------------------------
# macOS Command Line Tools pre-flight — same two-stage readiness check and the
# same loud-on-failure classification as install.sh lines 205-310.
#
# On a fresh Mac /usr/bin/git is a stub; the first `git` call opens a GUI
# dialog. This script calls git directly (clone / submodules / config), so the
# pre-flight has to happen before any of that. `xcode-select -p` alone is not
# enough: after a macOS update the path can be stale and still "pass", so we
# also require `xcrun --find git` to resolve.
#
# No-op on Linux and when the tools are already usable.
# -----------------------------------------------------------------------------
_clt_ready() {
  xcode-select -p >/dev/null 2>&1 \
    && xcrun --find git >/dev/null 2>&1
}

_join_rerun_hint() {
  printf '%s' "curl -fsSL https://sankalpasawa.github.io/sutra/join.sh | bash"
}

ensure_macos_clt() {
  [[ "$(uname -s)" == "Darwin" ]] || return 0
  if _clt_ready; then
    return 0
  fi

  if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
    die "This Mac is missing Apple's developer tools, which are needed to download files. Run this in a terminal: xcode-select --install — wait for the window to finish, then run the setup line again."
  fi

  log ""
  warn "This Mac is missing Apple's free developer tools. They are needed to download the company files."
  log "  Starting that download now."
  log ""
  log "  Size:   about 700 MB to download, 2-3 GB once installed, 5-15 minutes"
  log "  What:   command line tools only, NOT the full Xcode app"
  log "  After:  this setup continues on its own"
  log ""

  local trigger_out trigger_rc=0
  trigger_out="$(xcode-select --install 2>&1)" || trigger_rc=$?
  if [[ -n "${trigger_out}" ]]; then
    printf '%s\n' "${trigger_out}" | sed 's/^/[join]   /' >&2
  fi

  if [[ ${trigger_rc} -ne 0 ]]; then
    local hint
    if printf '%s' "${trigger_out}" | grep -qiE 'not currently available|software update server|no display|cannot.*open.*window|requires.*ui|no UI'; then
      hint="this Mac has no screen attached, so the install window cannot open"
    elif printf '%s' "${trigger_out}" | grep -qiE 'already installed|already.*present'; then
      hint="the Mac says the tools are installed, but they are not working"
    else
      hint="the tools installer would not start"
    fi
    log ""
    warn "Cannot continue: ${hint}."
    warn "  Ask whoever gave you this link to run these two lines on this Mac:"
    warn "    sudo xcode-select --reset"
    warn "    sudo xcode-select --install"
    warn "  Then run the setup line again:"
    warn "    $(_join_rerun_hint)"
    die "stopping here — the developer tools have to be working first."
  fi

  log ""
  log "Waiting for Apple's tools to finish (checking every 15 seconds, up to 20 minutes)..."
  log "  Click Install in the window that appeared. Pressing Ctrl+C is safe — you can run the setup line again."
  log ""

  local i=0
  local max=80   # 80 * 15s = 20 min
  while [[ ${i} -lt ${max} ]]; do
    if _clt_ready; then
      ok "Apple's developer tools are ready."
      return 0
    fi
    sleep 15
    i=$((i+1))
    if [[ $((i % 4)) -eq 0 ]]; then
      printf '%s[join]   still waiting... %d minute(s) so far (up to 20)%s\n' "${C_GREY}" $((i/4)) "${C_RESET}" >&2
    fi
  done

  warn "Gave up waiting after 20 minutes."
  warn "  Once the Apple window finishes, run the setup line again:"
  warn "    $(_join_rerun_hint)"
  die "stopping here — run the setup line again when the Apple install is done."
}

# -----------------------------------------------------------------------------
# Argument parsing + help — same shape as install.sh lines 315-397.
#
# The help text is a constant heredoc on purpose: under `curl ... | bash -s -- -h`
# the script body arrives on stdin (already consumed) and $0 is "bash", so
# reading the header out of $0 would print the bash binary, not this file.
# -----------------------------------------------------------------------------
print_help() {
  cat <<'USAGE'
Asawa setup — gets a new person set up to work on Asawa Inc.'s files.

How to run it:
  curl -fsSL https://sankalpasawa.github.io/sutra/join.sh | bash

Options (after `bash -s --`):
  -y, --yes    Don't ask anything. If your GitHub account is not connected yet,
               this stops with a message instead of asking you to sign in.
  -h, --help   Show this text and exit.

Settings you can pass as environment variables:
  JOIN_VERBOSE=1   Show every command it runs (for troubleshooting).

What it does, in order:
  1. Checks the basic tools your computer needs.
  2. Installs Claude Code if you don't have it.
  3. Installs the GitHub command line tool if you don't have it.
  4. Connects your GitHub account (opens a sign-in page in your browser).
  5. Downloads the company files to ~/Claude/asawa-holding, or updates them
     if they are already there.
  6. Downloads the shared parts that live inside those files.
  7. Puts your name and email on your changes, read from your GitHub account.
  8. Turns on the setting that makes Claude ask you before it does anything.
  9. Adds the Sutra add-on for Claude Code.

It is safe to run this as many times as you like. It never schedules anything
to run in the background.

Where this comes from: https://github.com/sankalpasawa/sutra
USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--yes) NON_INTERACTIVE=1 ;;
      -h|--help)
        print_help
        exit 0
        ;;
      *)
        die "I don't know the option \"$1\". Run it with -h to see the options."
        ;;
    esac
    shift
  done
}

# -----------------------------------------------------------------------------
# OS detection + PATH management — copied from install.sh lines 475-550
# (detect_os, detect_shell_rc, ensure_path_in_rc, ensure_path_in_current_session).
# Claude Code installs into $HOME/.local/bin; without these the `claude`
# command is missing in the next terminal and the final instruction would not
# work.
# -----------------------------------------------------------------------------
detect_os() {
  local uname_s
  uname_s="$(uname -s 2>/dev/null || echo unknown)"
  case "${uname_s}" in
    Darwin)  echo "macos" ;;
    Linux)   echo "linux" ;;
    MINGW*|MSYS*|CYGWIN*)
      die "This setup does not run on Windows directly. Install WSL2 (https://learn.microsoft.com/windows/wsl/install), open the Ubuntu window, and run the setup line there."
      ;;
    *)
      die "This setup runs on Mac and Linux. Your computer reports \"${uname_s}\", which it does not know. Send this message to whoever gave you the link."
      ;;
  esac
}

detect_shell_rc() {
  local shell_name="${SHELL:-/bin/bash}"
  shell_name="$(basename "${shell_name}")"
  case "${shell_name}" in
    zsh)
      local zdot="${ZDOTDIR:-${HOME}}"
      echo "${zdot}/.zshrc"
      ;;
    bash)
      if [[ "$(detect_os)" == "macos" && -f "${HOME}/.bash_profile" ]]; then
        echo "${HOME}/.bash_profile"
      elif [[ -f "${HOME}/.bashrc" ]]; then
        echo "${HOME}/.bashrc"
      else
        echo "${HOME}/.bashrc"
      fi
      ;;
    *)
      echo "${HOME}/.profile"
      ;;
  esac
}

ensure_path_in_rc() {
  local rc_file="$1"
  local line='export PATH="$HOME/.local/bin:$PATH"'
  local marker='# added by asawa join.sh (Claude Code PATH)'

  mkdir -p "$(dirname "${rc_file}")"
  touch "${rc_file}"

  if grep -Fq "${marker}" "${rc_file}" 2>/dev/null; then
    log "Your terminal already knows where to find Claude Code — leaving it alone."
    return 0
  fi

  if grep -Fq '$HOME/.local/bin' "${rc_file}" 2>/dev/null; then
    log "Your terminal already knows where to find Claude Code — leaving it alone."
    return 0
  fi

  {
    printf '\n%s\n' "${marker}"
    printf '%s\n' "${line}"
  } >> "${rc_file}"
  log "Told your terminal where to find Claude Code (${rc_file})."
}

ensure_path_in_current_session() {
  case ":${PATH}:" in
    *":${HOME}/.local/bin:"*) : ;;
    *) export PATH="${HOME}/.local/bin:${PATH}" ;;
  esac
}

# -----------------------------------------------------------------------------
# Step 1 — the basic tools
#
# git and curl are hard requirements: without either, nothing below can run, so
# these fail LOUD. On macOS the Apple pre-flight above usually supplies git.
# -----------------------------------------------------------------------------
step_basic_tools() {
  step "Step 1/${TOTAL_STEPS}: checking the basic tools"

  if ! command -v curl >/dev/null 2>&1; then
    die "Your computer is missing a tool called curl, which is needed to download things. On Ubuntu or Debian run: sudo apt-get install curl. On Fedora run: sudo dnf install curl. Then run the setup line again."
  fi
  ok "curl is here."

  if ! command -v git >/dev/null 2>&1; then
    if [[ "$(detect_os)" == "macos" ]]; then
      die "Your Mac is missing a tool called git. Run this in a terminal: xcode-select --install — wait for the window to finish, then run the setup line again."
    fi
    die "Your computer is missing a tool called git, which is needed to download the company files. On Ubuntu or Debian run: sudo apt-get install git. On Fedora run: sudo dnf install git. Then run the setup line again."
  fi
  ok "git is here."
}

# -----------------------------------------------------------------------------
# Step 2 — Claude Code (same approach as install.sh lines 555-578)
#
# Fails LOUD: the single instruction printed at the end is "run claude", so a
# missing claude means the setup did not succeed.
# -----------------------------------------------------------------------------
step_install_claude() {
  step "Step 2/${TOTAL_STEPS}: Claude Code"
  local rc_file
  rc_file="$(detect_shell_rc)"

  if command -v claude >/dev/null 2>&1; then
    ok "Claude Code is already installed."
  else
    log "Claude Code is not here yet — installing it now."
    if ! curl -fsSL https://claude.ai/install.sh | bash; then
      die "Claude Code would not install. Check your internet connection and run the setup line again. If it keeps failing, the manual instructions are at https://claude.com/claude-code"
    fi
  fi

  ensure_path_in_rc "${rc_file}"
  ensure_path_in_current_session

  if ! command -v claude >/dev/null 2>&1; then
    die "Claude Code installed, but this window cannot find it yet. Close this window, open a new terminal, and run the setup line again."
  fi

  log "Claude Code version: $(claude --version 2>/dev/null || echo 'unknown')"
}

# -----------------------------------------------------------------------------
# Step 3 — GitHub command-line tool (gh), plus two quiet extras
#
# gh is a hard requirement: the company files are in a PRIVATE repository, and
# gh is what proves who you are when downloading it. Missing gh with no way to
# install it fails LOUD.
#
# rtk and jq are installed quietly and are NON-FATAL:
#   * rtk trims noisy command output (house convention).
#   * jq is what the Sutra add-on's own setup script requires; without it
#     Step 9 degrades to a warning instead of completing.
# Neither is needed for the operator to start working, so neither can stop us.
# -----------------------------------------------------------------------------
brew_install_quiet() {
  # Non-fatal, quiet brew install. Returns 0 whether or not it worked.
  local formula="$1"
  command -v brew >/dev/null 2>&1 || return 0
  if brew list --formula "${formula}" >/dev/null 2>&1; then
    return 0
  fi
  brew install "${formula}" >/dev/null 2>&1 || true
  return 0
}

step_install_gh() {
  step "Step 3/${TOTAL_STEPS}: the GitHub tool"

  if command -v gh >/dev/null 2>&1; then
    ok "The GitHub tool is already installed."
  else
    local os
    os="$(detect_os)"
    if [[ "${os}" == "macos" ]]; then
      if ! command -v brew >/dev/null 2>&1; then
        die "This Mac needs a tool called gh, and the usual installer (Homebrew) is not here. Install Homebrew from https://brew.sh and run the setup line again. Or download gh from https://cli.github.com and run the setup line again."
      fi
      log "Installing the GitHub tool (this can take a couple of minutes)..."
      if ! brew install gh >/dev/null 2>&1; then
        die "The GitHub tool would not install. Try running this yourself: brew install gh — then run the setup line again."
      fi
    else
      die "Your computer needs a tool called gh to download the company files. Instructions for your system are at https://github.com/cli/cli/blob/trunk/docs/install_linux.md — on Ubuntu or Debian it is usually: sudo apt-get install gh. Install it, then run the setup line again."
    fi
  fi

  if ! command -v gh >/dev/null 2>&1; then
    die "The GitHub tool still is not available in this window. Close this window, open a new terminal, and run the setup line again."
  fi
  ok "The GitHub tool is ready."

  # Quiet, non-fatal extras. Skipped silently when brew is not present.
  brew_install_quiet rtk
  brew_install_quiet jq
}

# -----------------------------------------------------------------------------
# Step 4 — connect the GitHub account
#
# Explains what is about to happen BEFORE the prompt appears, because the
# person reading this has probably never seen a sign-in flow in a terminal.
#
# Fails LOUD when it cannot connect: the files are private, so there is no
# version of "carry on" that works.
# -----------------------------------------------------------------------------
step_github_connect() {
  step "Step 4/${TOTAL_STEPS}: connecting your GitHub account"

  if gh auth status --hostname github.com >/dev/null 2>&1; then
    local who
    who="$(gh api user --jq '.login' 2>/dev/null || echo '')"
    if [[ -n "${who}" ]]; then
      ok "Your GitHub account is already connected (signed in as ${who})."
    else
      ok "Your GitHub account is already connected."
    fi
  else
    if [[ ${NON_INTERACTIVE} -eq 1 ]]; then
      die "Your GitHub account is not connected yet, and you asked me not to ask you anything. Run this on its own first: gh auth login — then run the setup line again."
    fi
    if ! has_tty; then
      die "Your GitHub account is not connected yet, and this window cannot ask you to sign in. Open a normal terminal window, run: gh auth login — then run the setup line again."
    fi

    log ""
    log "Next you need to sign in to GitHub, so this computer is allowed to download the company files."
    log "In a moment a short code will appear here and a sign-in page will open in your web browser."
    log "Type the code into that page, approve it, then come back to this window."
    log ""

    local auth_rc=0
    run_on_terminal gh auth login --hostname github.com --git-protocol https --web -s repo || auth_rc=$?
    if [[ ${auth_rc} -eq 97 ]]; then
      die "This window cannot show you a sign-in prompt. Open a normal terminal window, run: gh auth login — then run the setup line again."
    fi
    if [[ ${auth_rc} -ne 0 ]]; then
      die "The GitHub sign-in did not finish. You can try it on its own by running: gh auth login — then run the setup line again."
    fi

    if ! gh auth status --hostname github.com >/dev/null 2>&1; then
      die "The GitHub sign-in did not stick. Run this on its own: gh auth login — then run the setup line again."
    fi
    ok "Your GitHub account is connected."
  fi

  # Let git reuse the GitHub sign-in for downloads. Additive and idempotent —
  # it only adds a credential helper for github.com. Non-fatal: an operator who
  # already has SSH keys set up does not need it.
  gh auth setup-git --hostname github.com >/dev/null 2>&1 \
    || warn "Could not link the GitHub sign-in to git. If the download below fails, run: gh auth setup-git"
}

# -----------------------------------------------------------------------------
# Step 5 — download or update the company files
#
# Three cases, all safe:
#   * folder missing, or present but empty -> download it
#   * folder is already this project       -> update it
#   * folder is something else             -> STOP, change nothing
# -----------------------------------------------------------------------------
_normalize_remote() {
  # Reduce any GitHub address to "github.com/owner/name" so the SSH and HTTPS
  # forms of the same project compare equal.
  local u="$1"
  u="${u%/}"
  u="${u%.git}"
  case "${u}" in
    git@github.com:*)         u="github.com/${u#git@github.com:}" ;;
    ssh://git@github.com/*)   u="github.com/${u#ssh://git@github.com/}" ;;
    ssh://github.com/*)       u="github.com/${u#ssh://github.com/}" ;;
    https://*@github.com/*)   u="github.com/${u#*@github.com/}" ;;
    https://github.com/*)     u="github.com/${u#https://github.com/}" ;;
    http://github.com/*)      u="github.com/${u#http://github.com/}" ;;
  esac
  printf '%s' "${u}" | tr '[:upper:]' '[:lower:]'
}

_dir_is_empty() {
  [[ -z "$(ls -A "$1" 2>/dev/null || true)" ]]
}

_clone_repo() {
  # Prefer `gh repo clone` so the download uses the GitHub sign-in from Step 4.
  # Fall back to a plain HTTPS download if gh's copy fails — for example when
  # the account is set to use SSH but this computer has no SSH key.
  local out rc=0
  out="$(gh repo clone "${JOIN_REPO}" "${TARGET_DIR}" 2>&1)" || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    return 0
  fi
  printf '%s\n' "${out}" | sed 's/^/[join]   /' >&2
  log "First download attempt did not work — trying the other way."
  rm -rf "${TARGET_DIR}"
  rc=0
  out="$(git clone "${JOIN_HTTPS_URL}" "${TARGET_DIR}" 2>&1)" || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    return 0
  fi
  printf '%s\n' "${out}" | sed 's/^/[join]   /' >&2
  return 1
}

step_get_files() {
  step "Step 5/${TOTAL_STEPS}: the company files"

  if [[ -e "${TARGET_DIR}" && ! -d "${TARGET_DIR}" ]]; then
    die "There is already a file, not a folder, at ${TARGET_DIR}. Move or rename it, then run the setup line again. Nothing has been changed."
  fi

  if [[ -d "${TARGET_DIR}" ]] && ! _dir_is_empty "${TARGET_DIR}"; then
    if [[ ! -e "${TARGET_DIR}/.git" ]]; then
      die "The folder ${TARGET_DIR} already exists and has other things in it. To keep those files safe, nothing has been changed. Move or rename that folder, then run the setup line again."
    fi

    local remote_url remote_canon
    remote_url="$(git -C "${TARGET_DIR}" remote get-url origin 2>/dev/null || echo '')"
    remote_canon="$(_normalize_remote "${remote_url}")"

    if [[ "${remote_canon}" != "${JOIN_REPO_CANON}" ]]; then
      die "The folder ${TARGET_DIR} already holds a different project (${remote_url:-unknown}). To keep those files safe, nothing has been changed. Move or rename that folder, then run the setup line again."
    fi

    log "The company files are already here — checking for updates."
    local pull_out pull_rc=0
    pull_out="$(git -C "${TARGET_DIR}" pull --ff-only 2>&1)" || pull_rc=$?
    printf '%s\n' "${pull_out}" | sed 's/^/[join]   /' >&2
    if [[ ${pull_rc} -eq 0 ]]; then
      ok "The company files are up to date."
    else
      warn "Could not bring in the newest changes just now — usually unsaved work of your own, or no connection."
      warn "  Your files are untouched, and everything below still works."
    fi
    return 0
  fi

  # Missing, or present but empty. `git clone` wants to create the folder
  # itself, so remove an empty one first.
  if [[ -d "${TARGET_DIR}" ]]; then
    rmdir "${TARGET_DIR}" 2>/dev/null || true
  fi
  mkdir -p "$(dirname "${TARGET_DIR}")"

  log "Downloading the company files to ${TARGET_DIR} — this can take a few minutes..."
  if ! _clone_repo; then
    rm -rf "${TARGET_DIR}"
    die "The company files would not download. The two usual reasons are: your internet dropped, or your GitHub account has not been given access to this project yet. Ask whoever gave you this link to add you, then run the setup line again."
  fi
  ok "Downloaded: ${TARGET_DIR}"
}

# -----------------------------------------------------------------------------
# Step 6 — the shared parts (git submodules)
#
# The project's recorded address for its shared part uses the SSH form
# (git@github.com:...), which only works for someone who has set up an SSH key.
# A non-technical operator has not. `git submodule init` copies the recorded
# addresses into this checkout's own private settings; we rewrite those copies
# to the HTTPS form BEFORE downloading. That touches only this computer's copy
# — the project's own recorded address file is never modified, so nothing shows
# up later as an unexpected change.
#
# NON-FATAL: the main files already downloaded, and re-running fixes this.
# -----------------------------------------------------------------------------
step_shared_parts() {
  step "Step 6/${TOTAL_STEPS}: the shared parts"

  git -C "${TARGET_DIR}" submodule init >/dev/null 2>&1 || true

  local line key val newval
  while read -r line; do
    [[ -n "${line}" ]] || continue
    key="${line%% *}"
    val="${line#* }"
    case "${val}" in
      git@github.com:*)       newval="https://github.com/${val#git@github.com:}" ;;
      ssh://git@github.com/*) newval="https://github.com/${val#ssh://git@github.com/}" ;;
      *) continue ;;
    esac
    git -C "${TARGET_DIR}" config --local "${key}" "${newval}" || true
    log "Adjusted a download address so it works without extra setup."
  done < <(git -C "${TARGET_DIR}" config --local --get-regexp '^submodule\..*\.url$' 2>/dev/null || true)

  local sm_out sm_rc=0
  sm_out="$(git -C "${TARGET_DIR}" submodule update --init --recursive 2>&1)" || sm_rc=$?
  if [[ ${sm_rc} -eq 0 ]]; then
    ok "The shared parts are here."
  else
    printf '%s\n' "${sm_out}" | sed 's/^/[join]   /' >&2
    warn "Some shared parts did not download. Everything below still works, and running the setup line again usually fixes it."
  fi
}

# -----------------------------------------------------------------------------
# Step 7 — put your name on your changes
#
# Read straight from the connected GitHub account, so there is never a
# placeholder for the operator to fill in.
#
# Email resolution, in order:
#   1. `gh api user` .email — the public email on the profile. Often empty.
#   2. `gh api user/emails` primary + verified. That needs the "user"
#      permission, which this script deliberately does NOT ask for, so it
#      normally returns nothing. Tried anyway, because an operator whose
#      account was connected earlier may already have granted it.
#   3. GitHub's own no-reply address: <id>+<login>@users.noreply.github.com.
#      A real, permanent, GitHub-issued address that works for changes and
#      keeps a personal email out of the project's history.
#
# Written with `--local`, which applies to THIS project folder only — a global
# identity from some other project is never inherited or reused.
# -----------------------------------------------------------------------------
_strip_ws() {
  # Collapse away tabs, carriage returns, newlines and spaces.
  local s="$1"
  s="${s//[$'\t\r\n ']/}"
  printf '%s' "${s}"
}

_looks_like_email() {
  # Deliberately strict. When GitHub answers a request we are not allowed to
  # make, it replies with an error document on the SAME channel as a real
  # answer, so a shape check is the only thing standing between that document
  # and someone's name being set to a blob of JSON.
  case "$1" in
    ""|*[$' \t\r\n{}",']*) return 1 ;;
    *@*.*) return 0 ;;
    *) return 1 ;;
  esac
}

_resolve_github_identity() {
  local tsv="" gh_id="" probe=""

  # `|| var=""` rather than `|| true`: a failed gh call still prints its error
  # document, and `|| true` would keep it.
  tsv="$(gh api user --jq '[.login, (.id|tostring), (.email // "")] | @tsv' 2>/dev/null)" || tsv=""
  if [[ -n "${tsv}" ]]; then
    IFS=$'\t' read -r GH_LOGIN gh_id GH_EMAIL <<<"${tsv}" || true
  fi

  GH_LOGIN="$(_strip_ws "${GH_LOGIN}")"
  gh_id="$(_strip_ws "${gh_id}")"
  GH_EMAIL="$(_strip_ws "${GH_EMAIL}")"

  # Fallback for a gh build whose built-in filter cannot do @tsv.
  if [[ ! "${GH_LOGIN}" =~ ^[A-Za-z0-9-]+$ ]]; then
    GH_LOGIN="$(gh api user --jq '.login'  2>/dev/null)" || GH_LOGIN=""
    gh_id="$(gh api user --jq '.id'        2>/dev/null)" || gh_id=""
    GH_EMAIL="$(gh api user --jq '.email // ""' 2>/dev/null)" || GH_EMAIL=""
    GH_LOGIN="$(_strip_ws "${GH_LOGIN}")"
    gh_id="$(_strip_ws "${gh_id}")"
    GH_EMAIL="$(_strip_ws "${GH_EMAIL}")"
  fi

  [[ "${gh_id}" =~ ^[0-9]+$ ]] || gh_id=""
  _looks_like_email "${GH_EMAIL}" || GH_EMAIL=""

  if [[ ! "${GH_LOGIN}" =~ ^[A-Za-z0-9-]+$ ]]; then
    die "Could not read your GitHub account details. Run this on its own: gh auth login — then run the setup line again."
  fi

  # 2. Primary verified address. Needs a permission this script does not ask
  #    for, so this usually comes back empty or as an error document; both are
  #    discarded by the shape check below.
  if [[ -z "${GH_EMAIL}" ]]; then
    probe="$(gh api user/emails --jq 'map(select(.primary == true and .verified == true)) | .[0].email // ""' 2>/dev/null)" || probe=""
    probe="$(_strip_ws "${probe}")"
    if _looks_like_email "${probe}"; then
      GH_EMAIL="${probe}"
    fi
  fi

  # 3. GitHub's permanent no-reply address.
  if [[ -z "${GH_EMAIL}" ]]; then
    if [[ -n "${gh_id}" ]]; then
      GH_EMAIL="${gh_id}+${GH_LOGIN}@users.noreply.github.com"
    else
      GH_EMAIL="${GH_LOGIN}@users.noreply.github.com"
    fi
  fi

  return 0
}

step_identity() {
  step "Step 7/${TOTAL_STEPS}: putting your name on your changes"

  _resolve_github_identity

  git -C "${TARGET_DIR}" config --local user.name  "${GH_LOGIN}"
  git -C "${TARGET_DIR}" config --local user.email "${GH_EMAIL}"

  # Every downloaded shared part gets the same name, so nothing quietly falls
  # back to a leftover identity from another project.
  local line spath
  while read -r line; do
    [[ -n "${line}" ]] || continue
    spath="${line#* }"
    [[ -n "${spath}" ]] || continue
    [[ -e "${TARGET_DIR}/${spath}/.git" ]] || continue
    git -C "${TARGET_DIR}/${spath}" config --local user.name  "${GH_LOGIN}" || true
    git -C "${TARGET_DIR}/${spath}" config --local user.email "${GH_EMAIL}" || true
  done < <(git -C "${TARGET_DIR}" config --file "${TARGET_DIR}/.gitmodules" --get-regexp '^submodule\..*\.path$' 2>/dev/null || true)

  local eff_name eff_mail
  eff_name="$(git -C "${TARGET_DIR}" config user.name  2>/dev/null || echo '')"
  eff_mail="$(git -C "${TARGET_DIR}" config user.email 2>/dev/null || echo '')"
  if [[ "${eff_name}" != "${GH_LOGIN}" || "${eff_mail}" != "${GH_EMAIL}" ]]; then
    die "Could not put your name on this project. Send this line to whoever gave you the link: identity write-back mismatch in ${TARGET_DIR}."
  fi
  ok "Your changes will be signed: ${eff_name} <${eff_mail}>"
}

# -----------------------------------------------------------------------------
# Step 8 — the safety setting
#
# Writes .claude/settings.local.json with defaultMode "default", which is
# Claude Code's "ask me first" behaviour. This matters here: the project ships
# a shared .claude/settings.json that sets bypassPermissions, and a personal
# settings file overrides the shared one — so without this step a brand new
# operator would land straight in bypass mode on their first session.
#
# NEVER overwritten if it already exists: that file holds the operator's own
# preferences, and this script does not get to have an opinion about them.
#
# Checked, not assumed: this path is NOT covered by the project's own ignore
# list. It is only ignored on machines that happen to carry a personal global
# ignore rule, which a new operator will not have. So this step also adds the
# rule to this checkout's private ignore list, which lives outside the shared
# files and is therefore never committed or seen by anyone else.
# -----------------------------------------------------------------------------
step_safety_setting() {
  step "Step 8/${TOTAL_STEPS}: the safety setting"

  local settings_dir="${TARGET_DIR}/.claude"
  local settings_file="${settings_dir}/settings.local.json"
  mkdir -p "${settings_dir}"

  if [[ -e "${settings_file}" ]]; then
    log "You already have your own settings file — leaving it exactly as it is."
  else
    cat > "${settings_file}" <<'JSON'
{
  "permissions": {
    "defaultMode": "default"
  }
}
JSON
    ok "Claude will ask you first, before it does anything."
  fi

  # Make sure that personal settings file can never be sent to the company
  # project by accident. .git/info/exclude is this computer's private list; it
  # is not one of the shared files, so writing to it changes nothing for others.
  local exclude_file="${TARGET_DIR}/.git/info/exclude"
  if [[ -d "${TARGET_DIR}/.git" ]]; then
    mkdir -p "$(dirname "${exclude_file}")"
    touch "${exclude_file}"
    if ! grep -Fq '**/.claude/settings.local.json' "${exclude_file}" 2>/dev/null; then
      printf '%s\n' '**/.claude/settings.local.json' >> "${exclude_file}"
    fi
  fi

  if ! git -C "${TARGET_DIR}" check-ignore -q .claude/settings.local.json 2>/dev/null; then
    warn "Your personal settings file is not being kept out of the company project."
    warn "  It still works. Mention this to whoever gave you the link."
  fi
}

# -----------------------------------------------------------------------------
# Step 9 — the Sutra add-on for Claude Code
#
# Same three moves as install.sh lines 583-641 (marketplace add + cache
# refresh, then install-or-update) and lines 818-872 (resolve the add-on's own
# bin/sutra out of the install cache, then run its setup).
#
# Deliberate difference from install.sh: every failure here is a WARNING, not a
# stop. By this point the operator has the files, an identity and Claude Code —
# they can work. A missing add-on is a nice-to-have they fix by running the
# setup line again.
#
# `sutra start` is the non-interactive equivalent of /core:start — it contains
# no prompts at all. We pass --telemetry off explicitly so nothing is sent
# anywhere without a person choosing it, and we deliberately do NOT pass --os
# or --git-gates. Nothing anywhere in this script schedules a background job.
# -----------------------------------------------------------------------------
resolve_sutra_bin() {
  # Copied from install.sh lines 818-836.
  local candidate
  candidate=$(ls -1 "${HOME}/.claude/plugins/cache/sutra/core"/*/bin/sutra 2>/dev/null | sort -V | tail -1)
  if [[ -n "${candidate}" && -x "${candidate}" ]]; then
    printf '%s' "${candidate}"
    return 0
  fi
  for candidate in \
    "${HOME}/.claude/plugins/cache/sankalpasawa/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/cache/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/marketplaces/sankalpasawa/sutra/marketplace/plugin/bin/sutra"
  do
    [[ -x "${candidate}" ]] && { printf '%s' "${candidate}"; return 0; }
  done
  return 1
}

_tracked_changes() {
  git -C "${TARGET_DIR}" diff --name-only 2>/dev/null || true
}

step_plugin() {
  step "Step 9/${TOTAL_STEPS}: the Sutra add-on for Claude Code"

  # --- register the source + refresh the catalogue (install.sh 583-606) ------
  local out rc=0
  out="$(claude plugin marketplace add "${SUTRA_MARKETPLACE}" 2>&1)" || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    ok "Add-on source registered."
  elif printf '%s' "${out}" | grep -iqE 'already (added|exists|present)|duplicate'; then
    log "Add-on source was already registered."
  else
    printf '%s\n' "${out}" | sed 's/^/[join]   /' >&2
    warn "Could not register the add-on source. Everything else is set up; running the setup line again usually fixes this."
    return 0
  fi

  claude plugin marketplace update "${SUTRA_MARKETPLACE_NAME}" >/dev/null 2>&1 \
    || log "Could not refresh the add-on list — carrying on."

  # --- install or update (install.sh 611-641) -------------------------------
  rc=0
  out="$(claude plugin install "${SUTRA_PLUGIN}" 2>&1)" || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    ok "Add-on installed."
  elif printf '%s' "${out}" | grep -iqE 'already (installed|present)'; then
    log "Add-on was already installed — updating it."
    claude plugin update "${SUTRA_PLUGIN}" >/dev/null 2>&1 \
      || warn "Could not update the add-on. The version you already have still works."
  else
    printf '%s\n' "${out}" | sed 's/^/[join]   /' >&2
    warn "Could not install the add-on. Everything else is set up; running the setup line again usually fixes this."
    return 0
  fi

  # --- the add-on's own setup, non-interactive ------------------------------
  local sutra_bin
  if ! sutra_bin=$(resolve_sutra_bin); then
    warn "Could not find the add-on's setup script. Type /core:start once inside Claude to finish it."
    return 0
  fi

  # Note which shared files already had unsaved edits, so that if the add-on's
  # setup rewrites one we can put back exactly that file and nothing else.
  # Without this a brand new copy of the company files would show unexpected
  # changes the moment the operator opened it.
  local before after changed
  before="$(_tracked_changes)"

  local start_rc=0
  ( cd "${TARGET_DIR}" && "${sutra_bin}" start --telemetry off ) >/dev/null 2>&1 || start_rc=$?

  after="$(_tracked_changes)"
  changed="$(comm -13 \
    <(printf '%s\n' "${before}" | sort -u) \
    <(printf '%s\n' "${after}"  | sort -u) 2>/dev/null || true)"

  if [[ -n "${changed}" ]]; then
    local f
    while read -r f; do
      [[ -n "${f}" ]] || continue
      git -C "${TARGET_DIR}" checkout -- "${f}" 2>/dev/null || true
    done <<<"${changed}"
    log "Put the shared company files back exactly as they arrived."
  fi

  if [[ ${start_rc} -eq 0 ]]; then
    ok "Add-on set up."
  else
    warn "The add-on's setup did not finish. Type /core:start once inside Claude to finish it."
  fi
}

# -----------------------------------------------------------------------------
# Finish — exactly one next action, and nothing else.
# -----------------------------------------------------------------------------
print_next_action() {
  CURRENT_STEP="finish"
  say ""
  say "Copy the line below, paste it into this window, and press Enter:"
  say ""
  say "    cd ~/Claude/asawa-holding && claude"
  say ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
  parse_args "$@"

  CURRENT_STEP="preflight"
  hr
  printf '  %sSetting you up to work on Asawa Inc.%s  %s(setup script v%s)%s\n' \
    "$C_BOLD" "$C_RESET" "$C_GREY" "${JOIN_VERSION}" "$C_RESET" >&2
  printf '  %sThis takes a few minutes. It is safe to run again at any time.%s\n' \
    "$C_GREY" "$C_RESET" >&2
  hr

  detect_os >/dev/null   # stops loudly on Windows and unknown systems

  # macOS only: Apple's developer tools have to work before any git call.
  ensure_macos_clt

  step_basic_tools
  step_install_claude
  step_install_gh
  step_github_connect
  step_get_files
  step_shared_parts
  step_identity
  step_safety_setting
  step_plugin

  print_next_action
}

main "$@"
