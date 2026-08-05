#!/usr/bin/env bash
# sutra-paths.sh — resolves where the dispatch runtime's assets live.
#
# The runtime runs in two places: an INSTALLED PLUGIN (every client) and this
# ORIGIN repo (Asawa, where it is developed). Assets must resolve to exactly
# one of them, and which one must be knowable rather than accidental.
#
# Codex (2026-08-05) named the failure this shape prevents: if the plugin root
# is treated as a preferred HINT with automatic origin fallback, a
# half-installed plugin silently runs origin code during dogfood — and the
# tests pass, because the origin tree is right there.
#
# So CLAUDE_PLUGIN_ROOT is AUTHORITATIVE. When it is set, every asset comes
# from under it and a missing asset is a hard failure, never a fallback.
# Origin mode applies only when no plugin root is declared at all.
#
# Exports: SUTRA_BASE, SUTRA_MODE (plugin|origin), SUTRA_LIB, SUTRA_BIN,
#          SUTRA_POLICY, SUTRA_VERIFY

_sutra_paths_init() {
  local repo
  repo="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    SUTRA_BASE="${CLAUDE_PLUGIN_ROOT%/}"
    SUTRA_MODE="plugin"
    SUTRA_LIB="$SUTRA_BASE/hooks/lib"
    SUTRA_BIN="$SUTRA_BASE/bin"
    SUTRA_POLICY="$SUTRA_BASE/os/routing-policy.json"
    SUTRA_VERIFY="$SUTRA_BIN/verify-templates"
  else
    local origin="$repo/holding"
    [ -d "$origin" ] || origin="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/holding"
    SUTRA_BASE="$origin"
    SUTRA_MODE="origin"
    SUTRA_LIB="$origin/hooks/lib"
    SUTRA_BIN="$origin/bin"
    SUTRA_POLICY="$origin/plans/dispatch-program/routing-policy.json"
    SUTRA_VERIFY="$SUTRA_BIN/verify-templates"
  fi
  export SUTRA_BASE SUTRA_MODE SUTRA_LIB SUTRA_BIN SUTRA_POLICY SUTRA_VERIFY
}

# sutra_asset <absolute-path> [--optional]
# In plugin mode a missing asset is FATAL: falling back to origin is exactly
# the silent-wrong-copy bug. In origin mode a miss is equally loud, because a
# broken dev tree should not be quiet either.
sutra_asset() {
  local p="$1" opt="${2:-}"
  if [ -e "$p" ]; then printf '%s' "$p"; return 0; fi
  [ "$opt" = "--optional" ] && return 1
  echo "sutra-paths: missing asset in ${SUTRA_MODE:-?} mode: $p" >&2
  return 1
}

_sutra_paths_init
