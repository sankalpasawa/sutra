#!/usr/bin/env bash
# marker-lib.sh — session-scoped governance markers (P1 concurrency fix).
# Scheme A (dir) + FAIL-CLOSED (founder decision 2026-07-27, DeepSeek-backed;
# resolves project_marker_scheme_reconcile).
#
# Markers live under .claude/sessions/<session-id>/ so N sessions in one repo each
# get their OWN dir — concurrency is preserved (no locks, no serialization; sessions
# never block each other). FAIL-CLOSED: there is NO global fallback read. A missing
# session marker means "not done" and the gate BLOCKS; a stale global marker can
# never silently satisfy a hard gate (the D2 silent-bypass defect).
#
# Session id: CLAUDE_CODE_SESSION_ID (model Bash env) == stdin .session_id (hooks),
# both the raw session UUID -> model-write and hook-read resolve the SAME dir
# (SID-PROOF-OK 2026-07-27). Hooks call sutra_sid_from_stdin first.

_sutra_sid() {
  if [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then printf '%s' "$CLAUDE_CODE_SESSION_ID"; return; fi
  if [ -n "${CLAUDE_SESSION_ID:-}" ];      then printf '%s' "$CLAUDE_SESSION_ID"; return; fi
  if [ -n "${1:-}" ];                      then printf '%s' "$1"; return; fi
  if [ -n "${CLAUDE_PID:-}" ];             then printf 'pid-%s' "$CLAUDE_PID"; return; fi
  printf 'pid-%s' "$PPID"
}
_sutra_root() { printf '%s' "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"; }
sutra_marker_dir()  { local d; d="$(_sutra_root)/.claude/sessions/$(_sutra_sid "${1:-}")"; mkdir -p "$d" 2>/dev/null; printf '%s' "$d"; }
sutra_marker_set()  { local dir name; dir="$(sutra_marker_dir)"; name="$1"; shift; local t="$dir/.$name.tmp.$$"; printf '%s\n' "$*" > "$t" && mv -f "$t" "$dir/$name"; }
sutra_marker_has()  { [ -f "$(sutra_marker_dir)/$1" ]; }
sutra_marker_read() { cat "$(sutra_marker_dir)/$1" 2>/dev/null; }
sutra_marker_path() { printf '%s/%s' "$(sutra_marker_dir)" "$1"; }
sutra_marker_reset(){ local d; d="$(sutra_marker_dir)"; rm -f "$d"/* 2>/dev/null; }
sutra_marker_gc()   {
  local base cur; base="$(_sutra_root)/.claude/sessions"; [ -d "$base" ] || return 0; cur="$(_sutra_sid)"
  find "$base" -maxdepth 1 -mindepth 1 -type d -mmin +1440 2>/dev/null | while read -r dd; do
    [ "$(basename "$dd")" = "$cur" ] && continue; rm -rf "$dd" 2>/dev/null
  done
}
sutra_sid_from_stdin() {
  [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] && return 0
  local sid; sid=$(printf '%s' "${1:-}" | jq -r '.session_id // empty' 2>/dev/null | tr -cd 'a-zA-Z0-9_-' | head -c 64)
  [ -n "$sid" ] && export CLAUDE_CODE_SESSION_ID="$sid"; return 0
}
