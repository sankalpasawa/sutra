#!/usr/bin/env bash
# wf-evidence.sh — Workflow-run evidence from the session transcript (G5=A).
#
# The Workflow tool is INVISIBLE to PreToolUse/PostToolUse hooks in this
# harness (scout-verified across 3 sessions, two independent no-matcher
# catch-alls, zero sightings) — so the floor's evidence is the TRANSCRIPT,
# which the harness writes and the model cannot author into: a workflow
# COMPLETION arrives as a type:"user" row whose message.content is a plain
# STRING carrying the <task-notification> envelope. Assistant prose is
# type:"assistant"; Bash output lives in list-shaped tool_result blocks —
# neither matches, so an echo'd lookalike cannot count (verified live against
# this repo's own transcripts, 2026-08-25).
#
# Shared by sutra-atom (snapshot at open) and dispatch-gate.sh (live count).
# Sourced defensively; never exits the caller.

# wf_transcript_path <project-root> <session-id>
#   The PINNED transcript path — never a glob (a resumed session creates a
#   second file; dual-lane consult: glob = wrong-file evidence).
wf_transcript_path() {
  local root="${1:-}" sid="${2:-}"
  { [ -n "$root" ] && [ -n "$sid" ]; } || { echo ""; return 0; }
  printf '%s/.claude/projects/%s/%s.jsonl\n' "$HOME" "$(printf '%s' "$root" | tr '/' '-')" "$sid"
}

# wf_completion_count <transcript-path>
#   Prints the number of harness-written Workflow COMPLETION notifications
#   (completions, not invocations — a denied or interrupted Workflow call
#   must not satisfy the floor; codex fold 2026-08-25), or -1 when the
#   transcript cannot be evaluated. CALLERS FAIL CLOSED ON -1: the model can
#   Bash-delete files under ~/.claude/projects, so unavailable-means-open
#   would be a one-line evasion (both consult lanes, convergent).
wf_completion_count() {
  local t="${1:-}"
  { [ -n "$t" ] && [ -r "$t" ]; } || { echo -1; return 0; }
  command -v jq >/dev/null 2>&1 || { echo -1; return 0; }
  local n
  n=$(jq -s '[ .[]
        | select(.type == "user")
        | (.message.content // empty)
        | select(type == "string")
        | select(contains("<task-notification>")
                 and contains("Dynamic workflow")
                 and contains("completed")) ] | length' "$t" 2>/dev/null) || { echo -1; return 0; }
  case "$n" in ''|*[!0-9]*) echo -1 ;; *) echo "$n" ;; esac
}
