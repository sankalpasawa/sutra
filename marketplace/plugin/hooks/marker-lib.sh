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
# 2026-07-30 SELF-ONLY ADOPTION (marker-race root cause, see
# holding/research/2026-07-30-marker-race-root-cause.md): the adopt-on-read bridge
# previously copied ANY legacy global into the reading session's dir — including a
# concurrent peer's (confirmed contamination 13:00:46Z: c2360700's placement marker
# adopted into 460a284f). Now a global twin is adopted ONLY when its SESSION= field
# is absent (legacy unstamped writer) or equals this session's sid. Foreign-stamped
# globals are IGNORED, logged to .enforcement/marker-contamination.jsonl, and never
# adopted — regardless of SUTRA_MARKER_ADOPT.
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

# Extract the SESSION= owner stamp from a marker file. Empty output = unstamped.
# Matches the stamp anywhere in the file (some schemas are single-line KV rows).
_sutra_marker_owner() { grep -o 'SESSION=[A-Za-z0-9_-]*' "$1" 2>/dev/null | head -1 | cut -d= -f2; }

# Append one JSONL contamination row. Best-effort: NEVER fails the calling gate —
# every path is 2>/dev/null || true and the function always returns 0.
_sutra_contamination_log() {
  local root; root="$(_sutra_root)"
  {
    mkdir -p "$root/.enforcement" &&
    printf '{"ts":%s,"sid":"%s","foreign_sid":"%s","marker":"%s"}\n' \
      "$(date +%s)" "$(_sutra_sid)" "$2" "$1" \
      >> "$root/.enforcement/marker-contamination.jsonl"
  } 2>/dev/null || true
  return 0
}

# WRITE. Session dir is authoritative. During migration it ALSO writes the legacy
# global path so that readers not yet migrated still find the marker.
# TODO[p1-dropglobal]: set SUTRA_MARKER_DUALWRITE=0 (then delete) once every reader
# uses sutra_marker_has.
#
# 2026-07-30: stamps SESSION=<sid> and TS=<epoch> into the content when the caller
# omitted them (idempotent — an existing SESSION=/TS= field anywhere in the body is
# respected, never double-stamped). The stamp is what lets self-only adoption and
# ownership-aware reset distinguish this session's globals from a peer's.
sutra_marker_set()  {
  local dir name body t g sid nl
  dir="$(sutra_marker_dir)"; name="$1"; shift; body="$*"
  sid="$(_sutra_sid)"; nl=$'\n'
  if ! printf '%s' "$body" | grep -Eq '(^|[^[:alnum:]_])SESSION=' 2>/dev/null; then
    body="${body:+${body}${nl}}SESSION=${sid}"
  fi
  if ! printf '%s' "$body" | grep -Eq '(^|[^[:alnum:]_])TS=' 2>/dev/null; then
    body="${body:+${body}${nl}}TS=$(date +%s)"
  fi
  t="$dir/.$name.tmp.$$"
  printf '%s\n' "$body" > "$t" && mv -f "$t" "$dir/$name"
  if [ "${SUTRA_MARKER_DUALWRITE:-1}" = "1" ]; then
    g="$(_sutra_global "$name")"; printf '%s\n' "$body" > "$g.tmp.$$" 2>/dev/null && mv -f "$g.tmp.$$" "$g" 2>/dev/null || true
  fi
}
# Pinned API name (ADR-029 worker contract, 2026-07-30): sutra_marker_write is
# the contract verb; it IS sutra_marker_set (same args, exit code, and output).
sutra_marker_write(){ sutra_marker_set "$@"; }

# READ-PRESENCE. Session dir is authoritative and is checked first.
#
# TRANSITIONAL ADOPTION (TODO[p1-dropglobal]) — deliberate, bounded deviation from
# strict "no global read". A legacy global marker is ADOPTED into the session dir
# and then passes, instead of being read in place forever.
#
# SELF-ONLY (2026-07-30): adoption requires the global's SESSION= field to be
# ABSENT (unstamped legacy writer — nobody else can prove ownership either, and
# an un-migrated CLAUDE.md govblock install would otherwise be bricked) or EQUAL
# to this session's sid (our own dual-written twin finding its way home). A
# foreign-stamped global is a concurrent peer's state: adopting it is exactly the
# cross-session contamination confirmed 2026-07-30 13:00:46Z. Foreign => skip
# adoption, return miss (gate blocks honestly), log one JSONL row. This holds
# regardless of SUTRA_MARKER_ADOPT — no flag value ever adopts foreign state.
#
# Strict mode: SUTRA_MARKER_ADOPT=0 disables adoption entirely -> pure fail-closed.
# Flip that default once the govblock migration has landed fleet-wide.
sutra_marker_has()  {
  local d g owner sid; d="$(sutra_marker_dir)"
  [ -f "$d/$1" ] && return 0
  [ "${SUTRA_MARKER_ADOPT:-1}" = "1" ] || return 1
  g="$(_sutra_global "$1")"
  [ -f "$g" ] || return 1
  owner="$(_sutra_marker_owner "$g")"
  sid="$(_sutra_sid)"
  if [ -n "$owner" ] && [ "$owner" != "$sid" ]; then
    _sutra_contamination_log "$1" "$owner"
    return 1
  fi
  cp "$g" "$d/$1" 2>/dev/null || return 1
  return 0
}
# READ-CONTENT. Same authority + self-only adoption as sutra_marker_has (it
# delegates): session-dir content if present, else the global twin only when
# unstamped or self-stamped. Foreign-stamped => miss (non-zero, no output).
sutra_marker_read() {
  sutra_marker_has "$1" || return 1
  cat "$(sutra_marker_dir)/$1" 2>/dev/null
}
sutra_marker_path() { printf '%s/%s' "$(sutra_marker_dir)" "$1"; }

# RESET (self-only). Wipes THIS session's dir, and clears a legacy global twin
# ONLY when its SESSION= stamp equals this session's sid. NEVER deletes an
# unstamped global (could be a peer on an un-migrated govblock — its owner is
# unprovable, so it is left for its writer's own turn lifecycle) and NEVER a
# foreign-stamped one (that peer's own reset clears it). This replaces the
# pre-2026-07-30 behavior that removed the global twin unconditionally for every
# marker present in the session dir — which deleted peers' last-writer-wins
# globals and was one of the three race bridges in the root-cause doc.
#
# Self-stamped adoption loop-back is still closed (the D2 concern the old
# unconditional delete existed for): our own dual-written twin carries our
# SESSION= stamp (sutra_marker_set stamps every write), so it IS deleted here and
# cannot be re-adopted next turn.
sutra_marker_reset_own(){
  local d f n g owner sid; d="$(sutra_marker_dir)"; sid="$(_sutra_sid)"
  [ -d "$d" ] || return 0
  for f in "$d"/*; do
    [ -e "$f" ] || continue
    n="$(basename "$f")"
    g="$(_sutra_global "$n")"
    [ -f "$g" ] || continue
    owner="$(_sutra_marker_owner "$g")"
    if [ -n "$owner" ] && [ "$owner" = "$sid" ]; then
      rm -f "$g" 2>/dev/null
    fi
  done
  rm -f "$d"/* 2>/dev/null
}
# Backward-compatible name (bin/sutra-marker reset, older hooks). Delegates to the
# self-only semantics — the old cross-session global delete is retired.
sutra_marker_reset(){ sutra_marker_reset_own; }
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
