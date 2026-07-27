#!/usr/bin/env bash
# marker-lib.sh — session-scoped governance marker resolution.
#
# WHY: per-turn governance markers (depth-registered, input-routed, flow-*,
# blueprint-registered, build-layer-registered, codex-consulted, ...) used to
# live at repo-global paths under .claude/. Two agent sessions in the SAME repo
# shared one set of files: each session's reset wiped the OTHER's markers
# mid-task, and concurrent writes clobbered. See
# holding/research/2026-07-27-sutra-concurrency-systemic-review.md.
#
# FIX: markers live under .claude/sessions/<session-id>/ . Parallel sessions
# never share a path -> no cross-session wipe, no clobber.
#
# Sourced by hooks; mirrored by bin/sutra-marker for the agent. DeepSeek
# design-review 2026-07-27 (MODIFY) absorbed: no shared "default", atomic
# writes, GC excludes the current session.

_sutra_sid() {
  if [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then printf '%s' "$CLAUDE_CODE_SESSION_ID"; return; fi
  if [ -n "${CLAUDE_SESSION_ID:-}" ];      then printf '%s' "$CLAUDE_SESSION_ID"; return; fi
  if [ -n "${1:-}" ];                      then printf 'sid-%s' "$1"; return; fi
  if [ -n "${CLAUDE_PID:-}" ];             then printf 'pid-%s' "$CLAUDE_PID"; return; fi
  printf 'pid-%s' "$PPID"
}
_sutra_root() {
  printf '%s' "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
}
sutra_marker_dir() {
  local d; d="$(_sutra_root)/.claude/sessions/$(_sutra_sid "${1:-}")"
  mkdir -p "$d" 2>/dev/null
  printf '%s' "$d"
}
sutra_marker_set() {
  local dir name; dir="$(sutra_marker_dir)"; name="$1"; shift
  local tmp="$dir/.$name.tmp.$$"
  printf '%s\n' "$*" > "$tmp" && mv -f "$tmp" "$dir/$name"
}
sutra_marker_has()  { [ -f "$(sutra_marker_dir)/$1" ]; }
sutra_marker_read() { cat "$(sutra_marker_dir)/$1" 2>/dev/null; }
sutra_marker_path() { printf '%s/%s' "$(sutra_marker_dir)" "$1"; }
sutra_marker_reset(){ local d; d="$(sutra_marker_dir)"; rm -f "$d"/* 2>/dev/null; }
sutra_marker_gc() {
  local base cur; base="$(_sutra_root)/.claude/sessions"; [ -d "$base" ] || return 0
  cur="$(_sutra_sid)"
  find "$base" -maxdepth 1 -mindepth 1 -type d -mmin +1440 2>/dev/null | while read -r dd; do
    [ "$(basename "$dd")" = "$cur" ] && continue
    rm -rf "$dd" 2>/dev/null
  done
}
