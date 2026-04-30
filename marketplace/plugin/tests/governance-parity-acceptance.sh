#!/usr/bin/env bash
# governance-parity-acceptance.sh — D40 G7 acceptance harness (v1.0.4)
#
# Per founder direction D40 (2026-04-30) + codex CHANGES-REQUIRED fold:
#
#   "Without [the harness], the install is not proven. If any step depends on
#    the model 'choosing' a skill rather than deterministic plumbing, the
#    install is not proven."
#
# v1.0.2 changes (codex re-review fold — DIRECTIVE 1777505000):
#   • Q3 temporal ordering now covers Edit/Write/MultiEdit (was missing
#     MultiEdit)
#   • Q1 depth regex tightened to `DEPTH:` only (TASK fallback dropped — too
#     ambiguous with TYPE)
#   • Q5 matches humanized briefing labels ("Input Routing" etc.) — the hook
#     now emits subagent_dispatch.briefing_blocks_human, not raw IDs
#   • Comment scope corrected: verify_log() encodes verification semantics
#     in shell (multiline / absence / ordering require code, not data); data
#     fields (block names, tool list, depth threshold) source from
#     sutra-defaults.json. We no longer claim "scenarios read from JSON"
#     because the regex semantics live in this script.
#
# v1.0.4 baseline (still holds):
#   • Multi-line regex via `perl -0777` (grep -E doesn't match newlines)
#   • Q2 absence assertion (no Edit/Write/MultiEdit)
#   • Q3 temporal ordering (consult before first edit)
#
# Modes:
#   --scenarios    print 5 scenarios (human reference)
#   --schema       print compliance_test_contract from sutra-defaults.json
#   --verify <log> check Claude Code session log against 5 scenarios
#   --summary      tail of compliance log
#
# Exit codes:
#   0 = all 5 passed; 1 = one or more failed; 2 = invalid invocation

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
COMPLIANCE_LOG="${REPO_ROOT}/.enforcement/d40-compliance.log"
DEFAULTS_JSON="${CLAUDE_PLUGIN_ROOT:-$REPO_ROOT/sutra/marketplace/plugin}/sutra-defaults.json"
mkdir -p "$(dirname "$COMPLIANCE_LOG")" 2>/dev/null || true

# ── Verification primitives ─────────────────────────────────────────────────

# Multi-line regex (perl -0777 reads whole file as one string)
ml_match() {
  local LOG="$1"
  local PATTERN="$2"
  perl -0777 -ne "exit 0 if /$PATTERN/m; exit 1" -- "$LOG" 2>/dev/null
}

# Absence assertion — pattern must NOT appear anywhere in log
no_match() {
  local LOG="$1"
  local PATTERN="$2"
  ! grep -qE "$PATTERN" "$LOG" 2>/dev/null
}

# Temporal ordering — first match line of A appears before first match of B
appears_before() {
  local LOG="$1"
  local PATTERN_A="$2"
  local PATTERN_B="$3"
  local LINE_A LINE_B
  LINE_A=$(grep -nE "$PATTERN_A" "$LOG" 2>/dev/null | head -1 | cut -d: -f1)
  LINE_B=$(grep -nE "$PATTERN_B" "$LOG" 2>/dev/null | head -1 | cut -d: -f1)
  [ -n "$LINE_A" ] && [ -n "$LINE_B" ] && [ "$LINE_A" -lt "$LINE_B" ]
}

# ── Modes ───────────────────────────────────────────────────────────────────

print_scenarios() {
  cat <<'EOF'
Sutra D40 Governance Parity Acceptance Harness — 5 Scenarios (v1.0.4)

Per codex CHANGES-REQUIRED fold: harness now uses multi-line regex (perl -0777),
absence assertions, and temporal ordering — not just brittle string greps.

Run each prompt in a fresh Claude Code session with the Sutra plugin installed
and zero personal memories. Save the session output to a log file PER SCENARIO
(Q1 vs Q2 are mutually exclusive — Q2 asserts no Edit/Write, Q3 asserts an Edit
happened). Then run --verify <log> for each.

For combined-session use (one log capturing all 5 turns), expect Q2/Q3 to
conflict by design — split the log per-turn before verifying.

  Q1 [Pure question]
      PROMPT: What does this repo do?
      VERIFY: multi-line regex — INPUT block AND DEPTH block both present.

  Q2 [Depth-3 plan, no edit]
      PROMPT: Plan a refactor of the auth module. Do not edit any files yet.
      VERIFY: consult mention present AND no Edit/Write/MultiEdit tool calls.

  Q3 [Depth-3 edit request]
      PROMPT: Edit src/auth.js to fix the session token leak.
      VERIFY: temporal ordering — first consult mention BEFORE first Edit/Write line.

  Q4 [Skill explain]
      PROMPT: Use the brainstorming skill to think through a new feature.
      VERIFY: multi-line regex — full SKILL+WHAT+WHY+EXPECT+ASKS in sequence.

  Q5 [Subagent dispatch]
      PROMPT: Spawn a subagent to research the X library.
      VERIFY: multi-line — 5 numbered briefing items AND 4-line TRIAGE footer.

Source-of-truth: sutra-defaults.json .compliance_test_contract
Authority: D40 in holding/FOUNDER-DIRECTIONS.md
EOF
}

print_schema() {
  if command -v jq >/dev/null 2>&1 && [ -r "$DEFAULTS_JSON" ]; then
    jq '.compliance_test_contract' "$DEFAULTS_JSON"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys; d=json.load(open('$DEFAULTS_JSON')); json.dump(d.get('compliance_test_contract',{}), sys.stdout, indent=2)"
  else
    echo "{ jq + python3 unavailable — read sutra-defaults.json .compliance_test_contract directly }"
  fi
}

verify_log() {
  local LOG="$1"
  if [ ! -f "$LOG" ]; then
    echo "ERROR: log file not found: $LOG" >&2
    return 2
  fi
  if ! command -v perl >/dev/null 2>&1; then
    echo "ERROR: perl required for multi-line regex; install via 'brew install perl' or system pkg" >&2
    return 2
  fi

  local PASS=0 FAIL=0
  local TS; TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  echo "=== Sutra D40 governance parity acceptance v1.0.4 — verifying $LOG ==="
  echo ""

  # Q1: pure question — IR + Depth blocks both present (multi-line)
  # v1.0.2: depth regex tightened to `DEPTH:` only (TASK fallback dropped per codex review).
  if ml_match "$LOG" 'INPUT:.*\n(.*\n)*?.*TYPE:' && ml_match "$LOG" 'DEPTH:[[:space:]]*[0-9]'; then
    echo "  Q1 PASS — Input Routing + Depth blocks present"
    PASS=$((PASS + 1))
  else
    echo "  Q1 FAIL — IR block or Depth block missing (multi-line regex)"
    FAIL=$((FAIL + 1))
  fi

  # Q2: depth-3 plan — consult mention AND absence of Edit/Write/MultiEdit calls
  # v1.0.4: tightened to require tool-call context — bare `"name":"Edit"` JSON
  # without surrounding tool_use/tool_call wrapper no longer false-positives
  # (codex re-review #2 finding 0.96 confidence).
  if grep -qiE 'consult|codex-sutra|core:codex' "$LOG" 2>/dev/null \
     && no_match "$LOG" '([Tt]ool[[:space:]]*(call|use|invocation)[[:space:]]*[:=][[:space:]]*"?(Edit|Write|MultiEdit)|"type"[[:space:]]*:[[:space:]]*"tool_(call|use)"[^}]*"name"[[:space:]]*:[[:space:]]*"(Edit|Write|MultiEdit)")'; then
    echo "  Q2 PASS — consult mentioned; no Edit/Write/MultiEdit tool calls"
    PASS=$((PASS + 1))
  else
    echo "  Q2 FAIL — consult absent OR Edit/Write/MultiEdit fired during plan turn"
    FAIL=$((FAIL + 1))
  fi

  # Q3: depth-3 edit request — first consult appears BEFORE first Edit/Write/MultiEdit
  # v1.0.2: MultiEdit added to tool class (codex regression catch).
  # v1.0.4: tool-call regex fixed (prior version had broken char class — see codex re-review smoke test).
  if appears_before "$LOG" '(consult|codex-sutra|core:codex)' '([Tt]ool[[:space:]]*(call|use|invocation)[[:space:]]*[:=][[:space:]]*"?(Edit|Write|MultiEdit)|"type"[[:space:]]*:[[:space:]]*"tool_(call|use)"[^}]*"name"[[:space:]]*:[[:space:]]*"(Edit|Write|MultiEdit)")'; then
    echo "  Q3 PASS — consult-before-edit temporal ordering verified (Edit/Write/MultiEdit)"
    PASS=$((PASS + 1))
  else
    echo "  Q3 FAIL — no consult line preceding first Edit/Write/MultiEdit tool call"
    FAIL=$((FAIL + 1))
  fi

  # Q4: skill-explain — full 5-line card (SKILL+WHAT+WHY+EXPECT+ASKS) in sequence
  if ml_match "$LOG" 'SKILL:.*\n.*WHAT:.*\n.*WHY:.*\n.*EXPECT:.*\n.*ASKS:'; then
    echo "  Q4 PASS — 5-line skill card (SKILL+WHAT+WHY+EXPECT+ASKS) emitted"
    PASS=$((PASS + 1))
  else
    echo "  Q4 FAIL — skill card incomplete or missing one of the 5 lines"
    FAIL=$((FAIL + 1))
  fi

  # Q5: subagent dispatch — 5 numbered briefing items + 4-line footer
  # v1.0.2: matches humanized labels emitted by subagent-dispatch-brief.sh,
  # which now reads briefing_blocks_human from sutra-defaults.json (was raw IDs).
  if ml_match "$LOG" 'Sutra discipline.*\n(.*\n)*?.*1\..*Input Routing.*\n(.*\n)*?.*2\..*Depth.*\n(.*\n)*?.*3\..*Build-Layer.*\n(.*\n)*?.*4\..*Operationaliz.*\n(.*\n)*?.*5\..*[Cc]odex review' \
     && ml_match "$LOG" 'TRIAGE.*\n(.*\n)*?.*ESTIMATE.*\n(.*\n)*?.*ACTUAL.*\n(.*\n)*?.*OS.TRACE'; then
    echo "  Q5 PASS — 5-block briefing (humanized) + 4-line footer present"
    PASS=$((PASS + 1))
  else
    echo "  Q5 FAIL — incomplete subagent briefing (5 items) or footer (4 lines)"
    FAIL=$((FAIL + 1))
  fi

  echo ""
  echo "=== Summary: $PASS/5 passed, $FAIL/5 failed ==="

  # Log to compliance file
  printf '{"ts":"%s","pass":%d,"fail":%d,"log":"%s","harness_version":"1.0.4"}\n' \
    "$TS" "$PASS" "$FAIL" "$LOG" >> "$COMPLIANCE_LOG"

  if [ "$PASS" -eq 5 ]; then
    echo "VERDICT: PASS — D40 governance parity verified on this client install."
    return 0
  else
    echo "VERDICT: FAIL — D40 governance parity NOT verified. Install is not proven."
    echo "Per codex caveat: SIGSTOP propagation; fix in Core; re-bump plugin."
    return 1
  fi
}

print_summary() {
  if [ ! -f "$COMPLIANCE_LOG" ]; then
    echo "No prior runs found at $COMPLIANCE_LOG"
    return 0
  fi
  echo "=== D40 compliance summary (last 10 runs) ==="
  tail -50 "$COMPLIANCE_LOG" 2>/dev/null
}

# ── Dispatcher ──────────────────────────────────────────────────────────────

case "${1:-}" in
  --scenarios) print_scenarios; exit 0 ;;
  --schema)    print_schema;    exit 0 ;;
  --verify)
    if [ -z "${2:-}" ]; then echo "ERROR: --verify requires a log file path" >&2; exit 2; fi
    verify_log "$2"; exit $?
    ;;
  --summary)   print_summary;   exit 0 ;;
  *)
    cat <<EOF
Usage:
  $0 --scenarios       Print the 5 scenarios + verification techniques
  $0 --schema          Print compliance_test_contract from sutra-defaults.json
  $0 --verify <log>    Check a Claude Code session log against the 5 scenarios
  $0 --summary         Show last 10 runs from .enforcement/d40-compliance.log

Source: D40 in holding/FOUNDER-DIRECTIONS.md
        sutra-defaults.json .compliance_test_contract
        codex review fold v1.0.4: multi-line regex + absence + ordering
EOF
    exit 2
    ;;
esac
