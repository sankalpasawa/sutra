#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# PreToolUse Dispatcher — Single-process execution of ALL PreToolUse checks
# ═══════════════════════════════════════════════════════════════════════════════
# Replaces individual hook registrations for Edit|Write with one shell process.
# Runs checks sequentially; exits with the FIRST non-zero exit code if any
# check blocks. All warnings/messages are always emitted.
#
# Individual scripts kept in holding/hooks/ for reference but are no longer
# registered as separate hooks.
# ═══════════════════════════════════════════════════════════════════════════════

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"
HOOK_LOG="$REPO_ROOT/holding/hooks/hook-log.jsonl"
FILE_PATH="$TOOL_INPUT_file_path"
TOOL_NAME="${TOOL_NAME:-}"  # "Edit" or "Write"

# Claude Code ≥ ~1.0 passes tool_input as JSON on stdin instead of env vars.
# Read stdin JSON and extract fields when env vars are missing. 2026-04-15 fix.
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _STDIN_JSON=$(cat)
  if [ -n "$_STDIN_JSON" ]; then
    # Parse JSON robustly — prefer jq if available (handles escaped quotes,
    # unicode, nested structures correctly). Fall back to naïve sed for
    # zero-dep environments (degraded correctness).
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_STDIN_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
      [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$_STDIN_JSON" | jq -r '.tool_name // empty' 2>/dev/null)
      _BASH_CMD_RAW=$(printf '%s' "$_STDIN_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
      # PROTO-004: intended post-edit content for Write/Edit (codex fix 2026-04-16)
      _WRITE_CONTENT=$(printf '%s' "$_STDIN_JSON" | jq -r '.tool_input.content // empty' 2>/dev/null)
      _EDIT_NEW_STRING=$(printf '%s' "$_STDIN_JSON" | jq -r '.tool_input.new_string // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_STDIN_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
      [ -z "$TOOL_NAME" ] && TOOL_NAME=$(printf '%s' "$_STDIN_JSON" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
      _BASH_CMD_RAW=""
      _WRITE_CONTENT=""
      _EDIT_NEW_STRING=""
    fi
    # For Bash tool calls, derive a mutation target from the command text.
    # Uses jq-extracted _BASH_CMD_RAW when available. Integration test
    # 2026-04-16 task C + codex round N.
    if [ "$TOOL_NAME" = "Bash" ] && [ -z "$FILE_PATH" ] && [ -n "$_BASH_CMD_RAW" ]; then
      # Scrape the first path-like target after > or >> (output redirection).
      # Strips surrounding quotes. Codex P2 fix: ignore /dev/ and /tmp/ pipes
      # so harmless `grep x >/dev/null` doesn't trigger gates.
      _CAND=$(printf '%s' "$_BASH_CMD_RAW" | sed -E -n 's/.*[^>0-9]>+[[:space:]]*"?([^[:space:]"]+)"?.*/\1/p' | head -1)
      if [ -z "$_CAND" ]; then
        _CAND=$(printf '%s' "$_BASH_CMD_RAW" | grep -oE 'sed -i[^[:space:]]*[[:space:]]+.+' | awk '{print $NF}' | tr -d "'\"")
      fi
      # Filter out /dev/* and known non-file sinks
      case "$_CAND" in
        /dev/*|/tmp/*|/var/*) _CAND="" ;;
      esac
      FILE_PATH="$_CAND"
      # Resolve relative paths against CLAUDE_PROJECT_DIR if present
      if [ -n "$FILE_PATH" ] && [ "${FILE_PATH#/}" = "$FILE_PATH" ] && [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
        FILE_PATH="$CLAUDE_PROJECT_DIR/$FILE_PATH"
      fi
    fi
  fi
fi

# Track first blocking exit code
BLOCK_CODE=0

# ms-resolution wall-clock helper (slowness #1, 2026-04-16). Prior timer used
# `date +%s` which rounds to whole seconds — all sub-second hook durations
# logged as ms=0, invisible for profiling. Order of preference:
#   (1) bash 5+ $EPOCHREALTIME      — in-process, no fork (~0ms overhead)
#   (2) gdate +%s%3N                — coreutils on macOS (single fork)
#   (3) python3 time.time()*1000    — portable fork (~10-20ms overhead)
#   (4) date +%s * 1000             — last-resort second resolution
_now_ms() {
  if [ -n "${EPOCHREALTIME:-}" ]; then
    # EPOCHREALTIME = "1776336429.123456" — take first 13 chars after strip
    local _er="${EPOCHREALTIME/./}"
    printf '%s\n' "${_er:0:13}"
  elif command -v gdate >/dev/null 2>&1; then
    gdate +%s%3N
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import time; print(int(time.time()*1000))'
  else
    echo $(( $(date +%s) * 1000 ))
  fi
}

# Logging helper: log_hook HOOK_NAME STATUS [ERROR_MSG] START_MS
# START_MS must come from _now_ms (not date +%s).
log_hook() {
  local _name="$1" _status="$2" _error="$3" _start="$4"
  local _end
  _end=$(_now_ms)
  local _ms=$(( _end - _start ))
  if [ "$_status" = "FAIL" ]; then
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"PreToolUse\",\"status\":\"FAIL\",\"error\":\"$_error\",\"ms\":$_ms}" >> "$HOOK_LOG"
  else
    echo "{\"ts\":$(date +%s),\"hook\":\"$_name\",\"event\":\"PreToolUse\",\"status\":\"PASS\",\"ms\":$_ms}" >> "$HOOK_LOG"
  fi
}

# ─── Check 1: Session Boundary Enforcement ────────────────────────────────────
# Source: .claude/hooks/enforce-boundaries.sh
# CEO of Asawa can edit everything — passthrough.
# (Currently a no-op; kept as a slot for future boundary logic)
_start1=$(_now_ms)
log_hook "SessionBoundary" "PASS" "" "$_start1"

# ─── Check 2: Version Governance (D24) ────────────────────────────────────────
# Source: holding/hooks/version-governance.sh
# Soft: reminds when editing a company's os/ directory
_start2=$(_now_ms)
_check2_status="PASS"
_check2_error=""
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    */dayflow/os/*|*/maze/os/*|*/ppr/os/*|*/jarvis/os/*)
      COMPANY=$(echo "$FILE_PATH" | grep -oE '(dayflow|maze|ppr|jarvis)' | head -1)
      echo "Warning: Per D24: Editing $COMPANY OS files: $FILE_PATH"
      echo "Is this a sanctioned update? PULL (company CEO decides) or PUSH (Asawa override)?"
      ;;
  esac
fi
log_hook "VersionGovernance-D24" "$_check2_status" "$_check2_error" "$_start2"

# ─── Write-only checks (skip for Edit on existing files) ─────────────────────
if [ "$TOOL_NAME" = "Write" ] || [ ! -f "$FILE_PATH" ]; then

  # ─── Check 3: Architecture Awareness (D4) ─────────────────────────────────
  # Source: holding/hooks/architecture-awareness.sh
  # Soft: reminds to check SYSTEM-MAP.md when creating new files
  _start3=$(_now_ms)
  _check3_status="PASS"
  _check3_error=""
  if [ -n "$FILE_PATH" ] && [ ! -f "$FILE_PATH" ]; then
    echo "Warning: Per D4: Creating new file: $FILE_PATH"
    echo "Was SYSTEM-MAP.md consulted? Does this fit existing architecture?"
    echo "Check holding/SYSTEM-MAP.md before proceeding."
  fi
  log_hook "ArchitectureAwareness-D4" "$_check3_status" "$_check3_error" "$_start3"

  # ─── Check 4: New Path Detector (PROTO-001) ──────────────────────────────
  # Source: holding/hooks/new-path-detector.sh
  # Soft: flags files in directories not listed in SYSTEM-MAP.md
  _start4=$(_now_ms)
  _check4_status="PASS"
  _check4_error=""
  if [ -n "$FILE_PATH" ] && [ ! -f "$FILE_PATH" ]; then
    DIR_PATH=$(dirname "$FILE_PATH")
    DIR_NAME=$(basename "$DIR_PATH")

    if [ -n "$REPO_ROOT" ]; then
      REL_PATH="${FILE_PATH#$REPO_ROOT/}"
      REL_DIR="${DIR_PATH#$REPO_ROOT/}"
    else
      REL_PATH="$FILE_PATH"
      REL_DIR="$DIR_PATH"
    fi

    SYSTEM_MAP="$REPO_ROOT/holding/SYSTEM-MAP.md"

    if [ -f "$SYSTEM_MAP" ]; then
      if ! grep -q "$REL_DIR\|$DIR_NAME/" "$SYSTEM_MAP" 2>/dev/null; then
        echo ""
        echo "PROTO-001: New path detected outside SYSTEM-MAP.md"
        echo "  File: $REL_PATH"
        echo "  Dir:  $REL_DIR"
        echo ""
        echo "  This directory is not in holding/SYSTEM-MAP.md."
        echo "  Per PROTO-001 (Structure Before Creation):"
        echo "    1. Does this content already have a home in an existing directory?"
        echo "    2. If not, document WHY existing structures don't fit."
        echo "    3. Update SYSTEM-MAP.md after creating."
        echo ""
      else
        echo ""
        echo "PROTO-001: Creating new file in mapped directory: $REL_PATH"
        echo "  Confirm: does this fit the purpose of $REL_DIR per SYSTEM-MAP.md?"
        echo ""
      fi
    fi
  fi
  log_hook "NewPathDetector-PROTO001" "$_check4_status" "$_check4_error" "$_start4"

fi

# ─── Check 5: Keys in Env Vars Only (PROTO-004) ───────────────────────────────
# HARD (2026-04-16 I-14 ladder, codex P1 fix): block (exit 2) if the INCOMING
# post-edit content introduces a hardcoded API key / secret pattern.
#   - Write: check tool_input.content (the new file contents)
#   - Edit:  check tool_input.new_string (the replacement text)
# This lets remediation edits (removing a secret) pass — only edits that
# INTRODUCE a secret are blocked. .env files are exempt.
# Override: SECRET_OVERRIDE=1 with SECRET_OVERRIDE_REASON (e.g., test fixture).
# Also supports env-var fallback (TOOL_INPUT_content, TOOL_INPUT_new_string)
# for tests that don't feed stdin JSON.
_start5=$(_now_ms)
if [ -n "$FILE_PATH" ]; then
  # Exclude .env files (those ARE env vars)
  case "$FILE_PATH" in
    *.env|*.env.*)
      : ;;
    *)
      # Pick the incoming content based on tool type
      _INCOMING=""
      case "$TOOL_NAME" in
        Write)
          _INCOMING="${_WRITE_CONTENT:-${TOOL_INPUT_content:-}}"
          ;;
        Edit)
          _INCOMING="${_EDIT_NEW_STRING:-${TOOL_INPUT_new_string:-}}"
          ;;
      esac
      # Grep the incoming content for the secret pattern
      if [ -n "$_INCOMING" ] && \
         printf '%s' "$_INCOMING" | grep -qiE '(api_key|secret_key|password|token)[[:space:]]*[:=][[:space:]]*["\x27][A-Za-z0-9_\-]{20,}'; then
        # Explicit deferral override (mirror of I-14 / D13 pattern)
        if [ "${SECRET_OVERRIDE:-0}" = "1" ]; then
          _REASON_RAW="${SECRET_OVERRIDE_REASON:-no-reason-given}"
          REASON=$(printf '%s' "$_REASON_RAW" | tr -d '"\\' | tr '\n\r' '  ')
          mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
          echo "{\"ts\":$(date +%s),\"event\":\"secret-override\",\"file\":\"${FILE_PATH#$REPO_ROOT/}\",\"reason\":\"$REASON\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
          echo "PROTO-004 override accepted (SECRET_OVERRIDE): $REASON"
        else
          echo ""
          echo "BLOCKED — PROTO-004 secrets gate (HARD)"
          echo "  File:   ${FILE_PATH#$REPO_ROOT/}"
          echo "  Tool:   $TOOL_NAME"
          echo "  Incoming content introduces a hardcoded API key / secret / token."
          echo "  Rule: keys must live in env vars, never in source."
          echo ""
          echo "  Fix: use process.env / os.environ / \$VAR in the new_string/content;"
          echo "       put the actual value in a .env file (gitignored)."
          echo ""
          echo "  Override (intentional, e.g. test fixture with fake key):"
          echo "    SECRET_OVERRIDE=1 SECRET_OVERRIDE_REASON='<why>' <tool call>"
          echo ""
          _SAFE_PATH=$(printf '%s' "${FILE_PATH#$REPO_ROOT/}" | tr -d '"\\' | tr '\n\r' '  ')
          mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
          echo "{\"ts\":$(date +%s),\"event\":\"secret-block\",\"file\":\"$_SAFE_PATH\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
          log_hook "KeysInEnvVars-PROTO004" "FAIL" "incoming content has hardcoded secret" "$_start5"
          BLOCK_CODE=2
          exit $BLOCK_CODE
        fi
      fi
      ;;
  esac
fi
log_hook "KeysInEnvVars-PROTO004" "PASS" "" "$_start5"

# ─── Check 6: Self-Assess Before Foundational Work (PROTO-005) ────────────────
# SOFT: remind when editing foundational docs
_start6=$(_now_ms)
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    *ARCHITECTURE*|*DESIGN*|*FRAMEWORK*|*DOCTRINE*|*OPERATING-MODEL*|*HUMAN-AGENT*)
      echo "PROTO-005: Foundational document being edited: $(basename "$FILE_PATH")"
      echo "  Self-assess: do you have sufficient context for this change?"
      echo "  Consider: research done? Implications modeled? Downstream impacts?"
      ;;
  esac
fi
log_hook "SelfAssess-PROTO005" "PASS" "" "$_start6"

# ─── Check 7: Process Discipline (PROTO-006) ──────────────────────────────────
# SOFT: remind that process exists before ad-hoc work
_start7=$(_now_ms)
# No blocking — this is a behavioral reminder handled by CLAUDE.md depth system
# Also covers: PROTO-000 (ship with implementation), PROTO-003 (free tier first),
# PROTO-010 (version focus), PROTO-015 (verify before commit), PROTO-016 (root cause)
# These are memory/behavior-enforced, not hook-enforced. Listed here for verify-connections.sh traceability.
log_hook "ProcessDiscipline-PROTO006" "PASS" "" "$_start7"

# ─── Check 8: Narration Is Not Artifact (PROTO-009) ──────────────────────────
# SOFT: when writing to os/ directories, remind that files must be artifacts
_start8=$(_now_ms)
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    */os/features/*|*/os/engines/*|*/os/findings/*|*/os/protocols/*)
      echo "PROTO-009: Writing to OS directory. This must be an artifact, not narration."
      echo "  The file must stand alone — another agent reading it should understand without context."
      ;;
  esac
fi
log_hook "NarrationNotArtifact-PROTO009" "PASS" "" "$_start8"

# ─── Check 9: Input Routing Verification (D28) ───────────────────────────────
# HARD: require routing classification before deliverable edits.
# Whitelist is intentionally narrow — memory writes NO LONGER skip this check,
# because new directions typically land as memory first (root cause of 2026-04-15 miss).
# Marker: .claude/input-routed (cleared on UserPromptSubmit → per-turn enforcement)
_start9=$(_now_ms)
_check9_status="PASS"
_routing_missing=0
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    "$REPO_ROOT/.claude/"*|*/holding/checkpoints/*|*/holding/hooks/hook-log*|*/holding/TODO.md|*/holding/ESTIMATION-LOG*|*.lock)
      # Minimal whitelist: repo-internal system-maintenance paths only.
      # User's ~/.claude/.../memory/ is NOT whitelisted — that was the 2026-04-15 bypass.
      ;;
    *)
      ROUTING_MARKER="$REPO_ROOT/.claude/input-routed"
      if [ ! -f "$ROUTING_MARKER" ]; then
        echo ""
        echo "BLOCKED — INPUT ROUTING MISSING (D28)"
        echo "  Per CLAUDE.md Input Routing (Level 2), emit before any Write/Edit:"
        echo "    INPUT: [founder statement]"
        echo "    TYPE: direction | task | feedback | new concept | question"
        echo "    EXISTING HOME: [where this lives, or 'none']"
        echo "    ROUTE: [which protocol handles this]"
        echo "    FIT CHECK: [what changes in existing architecture]"
        echo "    ACTION: [proposed action]"
        echo "  Then: echo \$(date +%s) > .claude/input-routed"
        echo ""
        mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
        echo "{\"ts\":$(date +%s),\"miss\":\"routing\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
        _check9_status="FAIL"
        _routing_missing=1
      fi
      ;;
  esac
fi
log_hook "InputRouting" "$_check9_status" "" "$_start9"
[ "$_routing_missing" = "1" ] && [ "$BLOCK_CODE" = "0" ] && BLOCK_CODE=1

# ─── Check 10: Depth Block Verification (D2/D9/D26) ──────────────────────────
# HARD: require depth/estimation block before deliverable edits.
#
# Marker contract (2026-04-17 upgrade — presence→value):
#   Canonical:  DEPTH=N TASK=<slug> TS=<unix>   where N ∈ {1..5}
#   Back-compat (old test format): "N <ts> <task>"  (space-separated, first token 1..5)
#   Migration grace: bare unix timestamp (10+ digits, old format) → treat as DEPTH=3 + warn
#   Anything else → BLOCK with helpful message
#
# Tier escalation: files under sutra/, holding/hooks/, or .claude/ (outside the
# whitelist) additionally require DEPTH >= 5. The sutra-deploy-depth5 marker
# (Check 11) remains the dedicated escape hatch for Sutra→company deploys.
_start10=$(_now_ms)
_check10_status="PASS"
_depth_missing=0
_DEPTH_VALUE=""   # populated on successful parse; consumed by Check 10b
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    "$REPO_ROOT/.claude/"*|*/holding/checkpoints/*|*/holding/hooks/hook-log*|*/holding/TODO.md|*/holding/ESTIMATION-LOG*|*.lock)
      ;;
    *)
      DEPTH_MARKER="$REPO_ROOT/.claude/depth-registered"
      DEPTH_MARKER_ALT="$REPO_ROOT/.claude/depth-assessed"
      _MARKER_FILE=""
      if [ -f "$DEPTH_MARKER" ]; then
        _MARKER_FILE="$DEPTH_MARKER"
      elif [ -f "$DEPTH_MARKER_ALT" ]; then
        _MARKER_FILE="$DEPTH_MARKER_ALT"
      fi

      if [ -z "$_MARKER_FILE" ]; then
        echo ""
        echo "BLOCKED — DEPTH BLOCK MISSING (D2/D9/D26)"
        echo "  Emit before any Write/Edit:"
        echo "    TASK: \"[what you're about to do]\""
        echo "    DEPTH: X/5"
        echo "    EFFORT: [time], [files]"
        echo "    COST: ~\$X (~Y% of \$200 plan)"
        echo "    IMPACT: [what this changes]"
        echo "  Then (new format):"
        echo "    echo \"DEPTH=N TASK=<slug> TS=\$(date +%s)\" > .claude/depth-registered"
        echo ""
        mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
        echo "{\"ts\":$(date +%s),\"miss\":\"depth\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
        _check10_status="FAIL"
        _depth_missing=1
      else
        # Parse marker contents. Read first non-empty line, strip CR.
        _MARKER_RAW=$(head -1 "$_MARKER_FILE" 2>/dev/null | tr -d '\r')
        _PARSED_DEPTH=""
        _PARSE_WARNING=""

        # Form 1: canonical "DEPTH=N TASK=... TS=..."
        if [ -z "$_PARSED_DEPTH" ]; then
          _tmp=$(printf '%s' "$_MARKER_RAW" | sed -n -E 's/.*(^|[[:space:]])DEPTH=([1-5])([[:space:]]|$).*/\2/p' | head -1)
          [ -n "$_tmp" ] && _PARSED_DEPTH="$_tmp"
        fi

        # Form 2: legacy "N <ts> <task>" — first whitespace-delimited token is 1..5
        if [ -z "$_PARSED_DEPTH" ]; then
          _first=$(printf '%s' "$_MARKER_RAW" | awk '{print $1}')
          case "$_first" in
            1|2|3|4|5) _PARSED_DEPTH="$_first" ;;
          esac
        fi

        # Form 3: migration grace — bare unix timestamp (10+ consecutive digits, no DEPTH=)
        if [ -z "$_PARSED_DEPTH" ]; then
          if printf '%s' "$_MARKER_RAW" | grep -qE '^[[:space:]]*[0-9]{10,}[[:space:]]*$'; then
            _PARSED_DEPTH="3"
            _PARSE_WARNING="legacy-bare-timestamp"
            echo "Warning: depth marker has legacy bare-timestamp format; defaulting DEPTH=3. Use 'DEPTH=N TASK=<slug> TS=<unix>'."
          fi
        fi

        if [ -z "$_PARSED_DEPTH" ]; then
          echo ""
          echo "BLOCKED — DEPTH MARKER MALFORMED (D2/D9/D26)"
          echo "  File: .claude/$(basename "$_MARKER_FILE")"
          echo "  Contents: $_MARKER_RAW"
          echo "  Expected format:"
          echo "    DEPTH=N TASK=<slug> TS=<unix>        (N ∈ {1,2,3,4,5})"
          echo "  Fix:"
          echo "    echo \"DEPTH=5 TASK=my-task TS=\$(date +%s)\" > .claude/depth-registered"
          echo ""
          mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
          _SAFE_RAW=$(printf '%s' "$_MARKER_RAW" | tr -d '"\\' | tr '\n\r' '  ')
          echo "{\"ts\":$(date +%s),\"miss\":\"depth-malformed\",\"file\":\"$FILE_PATH\",\"marker\":\"$_SAFE_RAW\"}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
          _check10_status="FAIL"
          _depth_missing=1
        else
          _DEPTH_VALUE="$_PARSED_DEPTH"
          # Tier escalation: protected paths require DEPTH >= 5.
          # Scope: sutra/, holding/hooks/ (excluding hook-log which is in whitelist above),
          #        and .claude/ (but .claude/ under REPO_ROOT was already whitelisted,
          #        so this catches cross-repo .claude/ writes).
          _needs_5=0
          case "$FILE_PATH" in
            */sutra/*|*/holding/hooks/*|*/.claude/*)
              _needs_5=1 ;;
          esac
          if [ "$_needs_5" = "1" ] && [ "$_DEPTH_VALUE" -lt 5 ]; then
            echo ""
            echo "BLOCKED — PROTECTED PATH REQUIRES DEPTH 5 (D2/D26)"
            echo "  File:  $FILE_PATH"
            echo "  Depth registered: $_DEPTH_VALUE/5"
            echo "  Paths under sutra/, holding/hooks/, or .claude/ require DEPTH=5."
            echo "  Fix:"
            echo "    echo \"DEPTH=5 TASK=<slug> TS=\$(date +%s)\" > .claude/depth-registered"
            echo ""
            mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
            echo "{\"ts\":$(date +%s),\"miss\":\"depth-too-low\",\"file\":\"$FILE_PATH\",\"depth\":$_DEPTH_VALUE}" >> "$REPO_ROOT/.enforcement/routing-misses.log"
            _check10_status="FAIL"
            _depth_missing=1
          fi
        fi
      fi
      ;;
  esac
fi
log_hook "DepthBlock" "$_check10_status" "" "$_start10"
[ "$_depth_missing" = "1" ] && [ "$BLOCK_CODE" = "0" ] && BLOCK_CODE=1

# ─── Check 11: Sutra → Company Deploy Depth Gate (D27) ───────────────────────
# HARD: any edit touching sutra/ OR a company os/ submodule path must declare Depth 5.
# Marker: .claude/sutra-deploy-depth5 (cleared on UserPromptSubmit).
_start11=$(_now_ms)
_check11_status="PASS"
_sutra_missing=0
if [ -n "$FILE_PATH" ]; then
  case "$FILE_PATH" in
    */sutra/*|*/dayflow/os/*|*/maze/os/*|*/ppr/os/*|*/jarvis/os/*|*/billu/os/*|*/paisa/os/*)
      SUTRA_DEPTH5_MARKER="$REPO_ROOT/.claude/sutra-deploy-depth5"
      if [ ! -f "$SUTRA_DEPTH5_MARKER" ]; then
        echo ""
        echo "BLOCKED — SUTRA→COMPANY DEPLOY REQUIRES DEPTH 5 (D27)"
        echo "  File: $FILE_PATH"
        echo "  Per founder direction 2026-04-15: implementing/deploying Sutra into any"
        echo "  portfolio company runs at Depth 5 (exhaustive). Emit full Depth-5 block:"
        echo "    TASK, DEPTH: 5/5, EFFORT (incl. downstream deps), COST, IMPACT (cross-company)"
        echo "  Verify-connections.sh, per-company impact list, test mechanism shipped."
        echo "  Then: echo \$(date +%s) > .claude/sutra-deploy-depth5"
        echo ""
        mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
        echo "{\"ts\":$(date +%s),\"miss\":\"sutra-depth5\",\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$REPO_ROOT/.enforcement/sutra-deploys.log"
        _check11_status="FAIL"
        _sutra_missing=1
      else
        echo "{\"ts\":$(date +%s),\"event\":\"sutra-deploy\",\"depth\":5,\"file\":\"$FILE_PATH\",\"tool\":\"$TOOL_NAME\"}" >> "$REPO_ROOT/.enforcement/sutra-deploys.log"
      fi
      ;;
  esac
fi
log_hook "SutraDeployDepth5-D27" "$_check11_status" "" "$_start11"
[ "$_sutra_missing" = "1" ] && BLOCK_CODE=2

# ─── Exit ─────────────────────────────────────────────────────────────────────
exit $BLOCK_CODE
