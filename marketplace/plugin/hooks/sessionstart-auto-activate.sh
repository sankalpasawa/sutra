#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# sessionstart-auto-activate.sh — one-shot first-run /core:start activator
#
# MANUAL FOLLOW-UP: register in hooks.json under "SessionStart" event before
# release. Suggested entry (sibling of update-banner.sh):
#
#   {
#     "type": "command",
#     "command": "${CLAUDE_PLUGIN_ROOT}/hooks/sessionstart-auto-activate.sh",
#     "timeout": 10
#   }
#
# What this hook does:
#   - Fires on every SessionStart, but only ACTS on the first session after
#     `install.sh` wrote the sentinel at ~/.sutra/installed-via-script.
#   - If the current project already ran /core:start (detected by
#     .claude/sutra-project.json), do nothing — preserves the user's prior
#     choice of entry project.
#   - Else: run `sutra start` via an absolute path to the plugin's bin/sutra
#     (NEVER via bare `sutra` — Finding #12 alias-collision risk) and, on
#     success, delete the sentinel so future sessions are silent.
#   - Failures are logged but NEVER block session start (exit 0 always).
#
# Design notes:
#   - Absolute-path invocation: resolved from $CLAUDE_PLUGIN_ROOT (Claude Code
#     sets this for every hook execution). Fallback search for common plugin
#     cache locations if the env var is missing (defensive only).
#   - One-shot semantics: the sentinel is removed on success so this hook
#     becomes a no-op on every subsequent session — zero prompt flood.
#   - No emoji in banner per house style.
# -----------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

SUTRA_HOME="${HOME}/.sutra"
SENTINEL="${SUTRA_HOME}/installed-via-script"
LOG_FILE="${SUTRA_HOME}/auto-activate.log"
PROJECT_MARKER=".claude/sutra-project.json"

# Always exit 0 from this hook — never block session start. A trap ensures
# that even unexpected failures don't propagate a non-zero exit code.
trap 'exit 0' ERR

mkdir -p "${SUTRA_HOME}" 2>/dev/null || true

log_line() {
  # Best-effort append to auto-activate.log. Never fails the hook.
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "${LOG_FILE}" 2>/dev/null || true
}

# --- Gate 1: sentinel present? ------------------------------------------------
if [[ ! -f "${SENTINEL}" ]]; then
  # Not a fresh install — silent no-op. Do NOT log (keeps log file clean).
  exit 0
fi

# --- Gate 2: current project already onboarded? -------------------------------
# Claude Code runs hooks from the session's working directory.
if [[ -f "${PWD}/${PROJECT_MARKER}" ]]; then
  log_line "skip: ${PROJECT_MARKER} already present in ${PWD}"
  exit 0
fi

# --- Resolve absolute path to bin/sutra --------------------------------------
resolve_sutra_bin() {
  # Prefer the env var Claude Code sets for hook execution.
  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -x "${CLAUDE_PLUGIN_ROOT}/bin/sutra" ]]; then
    printf '%s' "${CLAUDE_PLUGIN_ROOT}/bin/sutra"
    return 0
  fi

  # Defensive fallback — search common plugin cache locations. Stop on first hit.
  local candidate
  for candidate in \
    "${HOME}/.claude/plugins/cache/sankalpasawa/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/cache/sutra/plugin/bin/sutra" \
    "${HOME}/.claude/plugins/marketplaces/sankalpasawa/sutra/marketplace/plugin/bin/sutra"
  do
    if [[ -x "${candidate}" ]]; then
      printf '%s' "${candidate}"
      return 0
    fi
  done

  return 1
}

SUTRA_BIN="$(resolve_sutra_bin || true)"
if [[ -z "${SUTRA_BIN}" ]]; then
  log_line "fail: could not resolve bin/sutra (CLAUDE_PLUGIN_ROOT=${CLAUDE_PLUGIN_ROOT:-unset})"
  # Never block session start.
  exit 0
fi

# --- Run `sutra start` --------------------------------------------------------
log_line "start: ${SUTRA_BIN} start (cwd=${PWD})"

# Capture both streams; append to log. If the binary writes prompts meant for
# the user, Claude Code will surface them in the session — that's acceptable on
# first run (it IS the activation moment).
if "${SUTRA_BIN}" start >>"${LOG_FILE}" 2>&1; then
  log_line "ok: sutra start succeeded"
  # One-shot: remove sentinel so future sessions are silent.
  rm -f "${SENTINEL}" 2>/dev/null || log_line "warn: could not remove ${SENTINEL}"
  printf 'Sutra activated (first-run auto).\n' >&2
else
  rc=$?
  log_line "fail: sutra start exited ${rc}"
  # Leave the sentinel in place so a subsequent session can retry.
fi

exit 0
