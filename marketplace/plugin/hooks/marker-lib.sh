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
_sutra_global()     { printf '%s/.claude/%s' "$(_sutra_root)" "$1"; }

# WRITE. Session dir is authoritative. During migration it ALSO writes the legacy
# global path so that readers not yet migrated still find the marker.
# TODO[p1-dropglobal]: set SUTRA_MARKER_DUALWRITE=0 (then delete) once every reader
# uses sutra_marker_has.
sutra_marker_set()  {
  local dir name body t g
  dir="$(sutra_marker_dir)"; name="$1"; shift; body="$*"
  t="$dir/.$name.tmp.$$"
  printf '%s\n' "$body" > "$t" && mv -f "$t" "$dir/$name"
  if [ "${SUTRA_MARKER_DUALWRITE:-1}" = "1" ]; then
    g="$(_sutra_global "$name")"; printf '%s\n' "$body" > "$g.tmp.$$" 2>/dev/null && mv -f "$g.tmp.$$" "$g" 2>/dev/null || true
  fi
}

# READ. Session dir is authoritative and is checked first.
#
# TRANSITIONAL ADOPTION (TODO[p1-dropglobal]) — deliberate, bounded deviation from
# strict "no global read". A legacy global marker is ADOPTED into the session dir
# and then passes, instead of being read in place forever.
#
# Why this is NOT the D2 silent-bypass defect that fail-closed was adopted to kill:
#   D2 = global written once, reset never cleared it -> marker present FOREVER ->
#        the hard gate was permanently suspended and nobody could tell.
#   Here = reset-turn-markers clears BOTH the session dir AND the legacy global on
#        every real turn, so an adopted marker dies with its turn. There is no
#        permanent pass. The failure mode is bounded to a single turn.
#
# Why it is needed: writers and readers cannot flip atomically across the fleet. An
# install whose CLAUDE.md govblock still says `Write .claude/<name>` would otherwise
# be BRICKED the moment readers go session-only — every Edit blocked with no way to
# satisfy the gate. Adoption makes reader/writer migration order-independent.
#
# Strict mode: SUTRA_MARKER_ADOPT=0 disables adoption -> pure fail-closed. Flip that
# default once the govblock migration has landed fleet-wide.
sutra_marker_has()  {
  local d g; d="$(sutra_marker_dir)"
  [ -f "$d/$1" ] && return 0
  [ "${SUTRA_MARKER_ADOPT:-1}" = "1" ] || return 1
  g="$(_sutra_global "$1")"
  [ -f "$g" ] || return 1
  cp "$g" "$d/$1" 2>/dev/null || return 1
  return 0
}
sutra_marker_read() { cat "$(sutra_marker_dir)/$1" 2>/dev/null; }
sutra_marker_path() { printf '%s/%s' "$(sutra_marker_dir)" "$1"; }
# RESET. Clears this session's dir AND the legacy global twin of every marker that
# was in it. Clearing the twin is mandatory, not optional: with dual-write on, a
# session-only reset would leave the global copy behind and sutra_marker_has would
# ADOPT it straight back — resurrecting the marker across turns, which is exactly
# the D2 permanent-pass defect this design exists to prevent. Caught by
# marker-smoke-test ("beta marker survived its own reset") 2026-07-27.
sutra_marker_reset(){
  local d f n; d="$(sutra_marker_dir)"
  [ -d "$d" ] || return 0
  for f in "$d"/*; do
    [ -e "$f" ] || continue
    n="$(basename "$f")"
    rm -f "$(_sutra_global "$n")" 2>/dev/null
  done
  rm -f "$d"/* 2>/dev/null
}
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
