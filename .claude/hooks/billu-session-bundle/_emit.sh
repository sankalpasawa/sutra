#!/bin/bash
# Sourced by all session-bundle hooks. Appends one validated JSONL line
# to the Billu event bus at $BILLU_HOME/events/events.jsonl (default ~/.billu).

_billu_emit() {
  # $1 = JSON object (no trailing newline). Caller is responsible for valid JSON.
  local home="${BILLU_HOME:-$HOME/.billu}"
  local bus="$home/events/events.jsonl"
  mkdir -p "$(dirname "$bus")" 2>/dev/null
  printf '%s\n' "$1" >> "$bus"
}

# Escape a string for JSON.
_billu_esc() {
  printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

# Read full stdin once into a global, then expose query helpers.
# Claude Code hooks deliver their payload as JSON on stdin; we cache it so
# multiple field lookups within one hook invocation don't drain stdin twice.
#
# IMPORTANT: each $(...) capture runs in a subshell, so a `cat` inside one
# subshell drains stdin without persisting the cache to the parent. Hook
# scripts MUST call _billu_read_stdin_json once in the parent shell (e.g.
# `_billu_read_stdin_json > /dev/null`) BEFORE any $(_billu_field ...) calls.
# The auto-slurp below handles this when _emit.sh is sourced.
_billu_read_stdin_json() {
  if [ -z "${_BILLU_STDIN_JSON+x}" ]; then
    _BILLU_STDIN_JSON="$(cat)"
  fi
  printf '%s' "$_BILLU_STDIN_JSON"
}

# Auto-slurp stdin at source-time IF stdin is not a tty (i.e. there's a pipe
# feeding us — which is exactly the case for Claude Code hooks). For
# ask-billu.sh, stdin IS a tty (or /dev/null) when invoked from the slash
# command, so the slurp is skipped and ask-billu can ignore stdin entirely.
if [ ! -t 0 ] && [ -z "${_BILLU_STDIN_JSON+x}" ]; then
  _BILLU_STDIN_JSON="$(cat)"
fi

# Get a top-level field from the stdin JSON.
# String fields are emitted as-is; non-string fields are JSON-encoded.
_billu_field() {
  local field="$1"
  _billu_read_stdin_json | python3 -c "import json,sys
d=json.load(sys.stdin)
v=d.get('$field', '')
print(v if isinstance(v,str) else json.dumps(v))" 2>/dev/null
}

# Marker file used by ask-billu.sh (which runs as a normal Bash invocation,
# NOT a hook, so it can't see the stdin JSON). SessionStart writes the
# session_id here so in-session scripts can read the canonical key back.
_billu_session_marker_file() {
  local home="${BILLU_HOME:-$HOME/.billu}"
  local proj="${CLAUDE_PROJECT_DIR:-$(pwd)}"
  local safe=$(printf '%s' "$proj" | sed 's|/|_|g; s|^_*||')
  printf '%s/state/current-session/%s.txt' "$home" "$safe"
}
