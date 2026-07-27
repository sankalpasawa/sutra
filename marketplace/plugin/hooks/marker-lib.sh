#!/usr/bin/env bash
# marker-lib.sh — session-scoped governance markers (P1 concurrency fix).
#
# Markers live under .claude/sessions/<session-id>/ so two agent sessions in one
# repo never share a path (no cross-session reset-wipe, no clobber). See
# holding/research/2026-07-27-sutra-concurrency-systemic-review.md.
#
# DESIGN (DeepSeek 2026-07-27 MODIFY absorbed): PURE session-scoping — set/has/
# read/reset all operate ONLY on the current session's dir, so a turn-reset makes
# has() correctly return false (per-turn semantics hold). No shared "default"
# (falls back to CLAUDE_PID -> per-process-distinct). Atomic writes. GC excludes
# the current session. Migrate each marker's writer + reader TOGETHER (lockstep);
# untouched markers stay on their legacy global path and behave as before.

_sutra_sid() {
  if [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then printf '%s' "$CLAUDE_CODE_SESSION_ID"; return; fi
  if [ -n "${CLAUDE_SESSION_ID:-}" ];      then printf '%s' "$CLAUDE_SESSION_ID"; return; fi
  if [ -n "${1:-}" ];                      then printf 'sid-%s' "$1"; return; fi
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
