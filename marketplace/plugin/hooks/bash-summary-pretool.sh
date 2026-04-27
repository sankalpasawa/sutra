#!/usr/bin/env bash
# bash-summary-pretool.sh — Outcome-in-product-terms summary for Bash
# permission prompts. Fires ONLY when the command would actually prompt
# the user (i.e., is not in Sutra's allow-list).
#
# BUILD-LAYER: L0 (fleet)
# Version:     v1.15.0 (supersedes v1.14.0 rules-primary hybrid)
# Source:      FEEDBACK-LOG 2026-04-24 — external user + founder format correction
#
# Charter:     sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md § Part 4
# Principles:  P7 (Human Is the Final Authority — "makes trade-off visible")
#              P11 (Human Confidence Through Clarity)
#
# ─── What v1.15.0 changes vs v1.14.0 ───────────────────────────────────────
# - Firing scope narrowed: commands in Sutra's allow-list are SKIPPED entirely
#   (they auto-approve via permission-gate.sh — no prompt would appear, no
#   summary needed).
# - Format: "what changes in YOUR world" (outcome, product-level) instead of
#   "will delete X and Y" (mechanism, transcription-level). First-person
#   agent voice + bash-jargon prose were both wrong for non-technical users.
# - LLM becomes primary path; rules table replaced with a single generic
#   fallback line for when LLM is unavailable.
# - Context enrichment: LLM prompt includes the current task slug + cwd so
#   the summary can tie back to the user's original goal, not just the
#   command in isolation.
#
# ─── Behavior ──────────────────────────────────────────────────────────────
# ALWAYS exits 0. Never blocks. Emits JSON hookSpecificOutput.permission-
# DecisionReason, which Claude Code surfaces inline with the approval dialog.
#
# ─── Kill-switches ─────────────────────────────────────────────────────────
# SUTRA_BASH_SUMMARY=0              → whole hook disabled; exit 0 silently
# SUTRA_PERMISSION_LLM=0            → rules-fallback-only (no Haiku call)
# ~/.sutra-bash-summary-disabled    → file kill-switch

set -uo pipefail

# ─── Kill-switches ─────────────────────────────────────────────────────────
if [ "${SUTRA_BASH_SUMMARY:-1}" = "0" ] || [ -f "$HOME/.sutra-bash-summary-disabled" ]; then
  exit 0
fi

# ─── Read JSON payload from stdin ──────────────────────────────────────────
_JSON=""
if [ ! -t 0 ]; then
  _JSON=$(cat)
fi
[ -z "$_JSON" ] && exit 0

# ─── Extract the Bash command ──────────────────────────────────────────────
CMD=""
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -z "$CMD" ] && exit 0

# ─── Normalize: strip leading env-var prefixes (FOO=bar BAZ=qux <cmd>) ─────
CMD_CLEAN=$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]*([A-Z_][A-Z0-9_]*=[^[:space:]]*[[:space:]]+)*//')

# ─── Allow-list fast-path ──────────────────────────────────────────────────
# If the command would be auto-approved by permission-gate.sh (v1.13.0),
# no permission dialog appears — so no summary is needed. Skip the work.
# These patterns mirror permission-gate.sh's scope, kept in sync manually.
# Codex round 3 fix: mirror env-shadowing guard from permission-gate.sh to
# prevent decision drift. If primitives are shadowed, don't skip the summary.
_bash_summary_compositional_re='ls|cat|head|tail|wc|echo|printf|pwd|date|whoami|which|basename|dirname|realpath|grep|cut|uniq|tr|column'

_bash_summary_env_shadowing() {
  if env | grep -qE "^BASH_FUNC_(${_bash_summary_compositional_re})(%%|\(\))=" 2>/dev/null; then
    return 0
  fi
  local name
  for name in ls cat head tail wc echo printf pwd date whoami which basename dirname realpath grep cut uniq tr column; do
    if declare -F "$name" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

_is_allowlisted() {
  local cmd="$1"
  case "$cmd" in
    # Sutra bin dispatcher and its subcommands
    sutra|'sutra '*) return 0 ;;
    # Sutra plugin script invocations
    'bash '*'/sutra/marketplace/plugin/'*) return 0 ;;
    'bash '*'${CLAUDE_PLUGIN_ROOT}'*) return 0 ;;
    # Plugin management
    'claude plugin marketplace update '*) return 0 ;;
    'claude plugin update '*) return 0 ;;
    'claude plugin uninstall '*) return 0 ;;
    # Safe filesystem prep for governance dirs
    'mkdir -p .claude'*|'mkdir -p .enforcement'*|'mkdir -p .context'*) return 0 ;;
    # Read-only introspection (rtk-prefixed git commands pass through too)
    'rtk '*) return 0 ;;
  esac

  # Tier 1.5 compositional-read fast-path (v2.4+). Parity with permission-gate.sh
  # so the summary is also skipped when the command would auto-approve.
  # MUST apply the same env-shadowing guard — codex round 3.
  if _bash_summary_env_shadowing; then
    return 1
  fi
  local helper="${CLAUDE_PLUGIN_ROOT:-}/lib/sh_lex_check.py"
  if [ -f "$helper" ] && command -v python3 >/dev/null 2>&1; then
    local r
    local _to2=""
    if command -v timeout >/dev/null 2>&1; then _to2="timeout 2"
    elif command -v gtimeout >/dev/null 2>&1; then _to2="gtimeout 2"
    fi
    r=$(printf '%s' "$cmd" | $_to2 python3 "$helper" 2>/dev/null | jq -r '.safe // false' 2>/dev/null)
    [ "$r" = "true" ] && return 0
  fi

  # Tier 1.6 Trust Mode (v2.5+) — mirrors permission-gate. If trust-mode
  # auto-approves, the user sees no prompt, so skip summary entirely.
  local trust_helper="${CLAUDE_PLUGIN_ROOT:-}/lib/sh_trust_mode.py"
  if [ -f "$trust_helper" ] && command -v python3 >/dev/null 2>&1; then
    local _to3=""
    if command -v timeout >/dev/null 2>&1; then _to3="timeout 2"
    elif command -v gtimeout >/dev/null 2>&1; then _to3="gtimeout 2"
    fi
    local p
    p=$(printf '%s' "$cmd" | $_to3 python3 "$trust_helper" 2>/dev/null | jq -r 'if .prompt == false then "false" else "true" end' 2>/dev/null)
    [ "$p" = "false" ] && return 0
  fi
  return 1
}

if _is_allowlisted "$CMD_CLEAN"; then
  exit 0
fi

# ─── Gather context for the LLM prompt ─────────────────────────────────────
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
CWD="${PWD:-$(pwd)}"
TASK_SLUG=""
if [ -n "$REPO_ROOT" ] && [ -f "$REPO_ROOT/.claude/depth-registered" ]; then
  # Extract TASK=<slug> from the marker line
  TASK_SLUG=$(grep -oE 'TASK=[^ ]+' "$REPO_ROOT/.claude/depth-registered" 2>/dev/null | head -1 | sed 's/^TASK=//')
fi
[ -z "$TASK_SLUG" ] && TASK_SLUG="(unknown)"

# Compact cwd: show last 2 path components for readability
CWD_SHORT=$(printf '%s' "$CWD" | awk -F/ '{ n=NF; if (n>=2) print $(n-1)"/"$n; else print $0 }')

# ─── Escape text for safe JSON output ──────────────────────────────────────
_json_escape() {
  printf '%s' "$1" \
    | sed 's/\\/\\\\/g' \
    | sed 's/"/\\"/g' \
    | tr '\n' ' ' \
    | tr '\r' ' ' \
    | tr '\t' ' '
}

# ─── Danger-tag heuristic (cheap, pre-LLM) ─────────────────────────────────
# Pre-mark catastrophic/destructive patterns so the LLM prompt can be told
# to lead with 🚨 or ⚠️ reliably, without depending on the model to infer it.
_danger_tag() {
  local cmd="$1"
  case "$cmd" in
    'sudo rm -rf /'|'rm -rf /'|'rm -rf / '*) echo "🚨"; return ;;
    'rm -rf '*|'rm -Rf '*|'rm -fr '*|'rm -fR '*) echo "⚠️"; return ;;
    'dd '*|'sudo dd '*) echo "⚠️"; return ;;
    'git reset --hard'*|'git clean -f'*) echo "⚠️"; return ;;
    'git push --force'*|'git push -f'*) echo "⚠️"; return ;;
    *'curl '*'|'*' sh'*|*'curl '*'|'*' bash'*|*'wget '*'|'*' sh'*|*'wget '*'|'*' bash'*) echo "⚠️"; return ;;
    'sudo '*) echo "⚠️"; return ;;
    'kill -9 '*|'pkill '*|'killall '*) echo "⚠️"; return ;;
  esac
  echo ""
}

DANGER_PREFIX=$(_danger_tag "$CMD_CLEAN")

# ─── LLM summarizer (primary path) ─────────────────────────────────────────
_llm_summarize() {
  local cmd="$1" task="$2" cwd="$3" danger="$4"
  local cache_dir="$HOME/.sutra/permission-summary-cache"
  local cache_key cache_file last_call_file

  mkdir -p "$cache_dir" 2>/dev/null
  last_call_file="$cache_dir/.last-call"

  # Rate limit: skip LLM if last call was <500ms ago (prevent runaway in loops)
  if [ -f "$last_call_file" ]; then
    local last now
    last=$(cat "$last_call_file" 2>/dev/null || echo 0)
    now=$(date +%s)
    if [ $((now - last)) -lt 1 ]; then
      return 1
    fi
  fi

  # Cache key includes task + cmd so same cmd in different tasks cache separately
  cache_key=$(printf '%s|%s' "$task" "$cmd" | md5 -q 2>/dev/null \
    || printf '%s|%s' "$task" "$cmd" | md5sum 2>/dev/null | awk '{print $1}')
  [ -z "$cache_key" ] && return 1
  cache_file="$cache_dir/$cache_key.txt"

  # Cache hit
  if [ -f "$cache_file" ]; then
    cat "$cache_file"
    return 0
  fi

  # Check LLM availability
  if ! command -v claude >/dev/null 2>&1; then
    return 1
  fi

  date +%s > "$last_call_file" 2>/dev/null

  local prompt result
  prompt="Tell a non-technical user what will happen if they approve this shell command. Explain what changes in THEIR world — product/outcome level — NOT what the command does technically.

Current task:  ${task}
Working dir:   ${cwd}
Command:       ${cmd}

Rules:
- Answer the reader's question: \"what will my world look like after I approve this?\"
- Tie the outcome to the user's goal (the current task) when you reasonably can.
- No bash jargon. No file paths in the summary unless the path IS the product thing (e.g., 'the analytics dashboard code'). No \"I'm...\", no \"will...\", no \"Plain-English\".
- One or two sentences max.
- If destructive or irreversible, your first characters must be the danger prefix below.

Danger prefix to use (empty means no prefix): '${danger}'

Output just the summary sentence(s). No preamble, no quotes."

  result=$(printf '%s' "$prompt" | timeout 8 claude --print --model claude-haiku-4-5-20251001 2>/dev/null | head -c 400)
  if [ -n "$result" ]; then
    printf '%s' "$result" > "$cache_file" 2>/dev/null
    printf '%s' "$result"
    return 0
  fi
  return 1
}

# ─── Generic fallback (LLM unavailable or disabled) ────────────────────────
# Single line — no HOW-transcription. Just enough to tell the user "we can't
# auto-summarize this one; please look at the raw command below."
_generic_fallback() {
  if [ -n "$DANGER_PREFIX" ]; then
    echo "${DANGER_PREFIX} This command looks destructive. Review the command below carefully before approving — automated summary is unavailable right now."
  else
    echo "Sutra couldn't auto-summarize this one. Review the raw command below before approving."
  fi
}

# ─── Main dispatch ─────────────────────────────────────────────────────────
SUMMARY=""

if [ "${SUTRA_PERMISSION_LLM:-1}" != "0" ]; then
  SUMMARY=$(_llm_summarize "$CMD_CLEAN" "$TASK_SLUG" "$CWD_SHORT" "$DANGER_PREFIX" 2>/dev/null || true)
fi

if [ -z "$SUMMARY" ]; then
  SUMMARY=$(_generic_fallback)
fi

# ─── Log to enforcement channel ────────────────────────────────────────────
if [ -n "$REPO_ROOT" ]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  VERB=$(printf '%s' "$CMD_CLEAN" | awk '{print $1}')
  SAFE_VERB=$(printf '%s' "$VERB" | tr -d '"\\' | tr '\n\r' '  ' | head -c 50)
  TS=$(date +%s)
  LLM_USED=0
  [ "${SUTRA_PERMISSION_LLM:-1}" != "0" ] && [ -n "$SUMMARY" ] && LLM_USED=1
  DANGER=0
  [ -n "$DANGER_PREFIX" ] && DANGER=1
  echo "{\"ts\":$TS,\"event\":\"bash-summary-v1.15\",\"verb\":\"$SAFE_VERB\",\"llm_used\":$LLM_USED,\"dangerous\":$DANGER,\"summary_len\":${#SUMMARY},\"task\":\"$(printf '%s' "$TASK_SLUG" | tr -d '"\\' | head -c 60)\"}" \
    >> "$REPO_ROOT/.enforcement/bash-summary.jsonl" 2>/dev/null
fi

# ─── Emit JSON output (permissionDecisionReason) ───────────────────────────
SAFE_SUMMARY=$(_json_escape "$SUMMARY")

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' \
  "$SAFE_SUMMARY"

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (per PROTO-000)
#
# ### 1. Measurement mechanism
# Per-fire row in .enforcement/bash-summary.jsonl: {ts, verb, llm_used,
# dangerous, summary_len, task}. Zero rows = hook not firing OR zero
# prompt-triggering Bash calls that turn (normal when most ops are allow-listed).
#
# ### 2. Adoption mechanism
# Registered in sutra/marketplace/plugin/hooks/hooks.json under
# PreToolUse[Bash], sequenced after rtk-auto-rewrite + codex-directive-gate.
# Fleet receives via plugin auto-update on next Claude Code session.
#
# ### 3. Monitoring / escalation
# DRI (Sutra marketplace dept) reviews bash-summary.jsonl weekly.
# Warn: false-destructive rate >5%; LLM timeout rate >10%.
# Breach: user reports wrong summary in FEEDBACK-LOG → update LLM prompt.
#
# ### 4. Iteration trigger
# Revise the LLM prompt when telemetry or FEEDBACK-LOG surfaces a class of
# misreads. The allow-list fast-path mirrors permission-gate.sh — keep in
# sync whenever that hook's scope expands.
#
# ### 5. DRI
# Sutra marketplace department. Charter steward: c-human-agent-interface
# (Part 4 registry maintainer).
#
# ### 6. Decommission criteria
# Retire when Anthropic ships native permission-summary (upstream pitch); OR
# when telemetry shows <1 fire/day for 30 days across the fleet.
