#!/usr/bin/env bash
# bash-summary-pretool.sh — Annotates Bash permission prompts with Trust Mode
# category text.
#
# BUILD-LAYER: L0 (fleet)
# Version:     v2.7.0
# Charter:     sutra/os/charters/PERMISSIONS.md
#
# v2.7.0 streamline (codex-converged 2026-04-28):
#   - Dropped 80 LoC of Haiku LLM summarizer path (raw + category text is
#     deterministic, free, and equivalent UX for the rare prompt that fires).
#   - Dropped 50 LoC of allowlist mirror (drift-prone duplicate of
#     permission-gate.sh logic — codex caught real drift on `rtk *` and
#     `claude plugin update *`).
#   - Dropped 30 LoC of env-shadowing guard (v2.4 residue — Trust Mode threat
#     model explicitly excludes adversarial env injection).
#   - Single source of truth: sh_trust_mode.py is the only allow-decision.
#     If Trust Mode says auto-approve, this hook exits silently.
#
# Behavior:
#   - Trust Mode says auto-approve → exit 0 silently. PermissionRequest gate
#     (permission-gate.sh) handles the actual allow + persistence.
#   - Trust Mode says prompt → emit permissionDecision:"ask" with a
#     deterministic category label + one-line hint. Raw command is shown by
#     Claude Code's prompt UI under the reason text.
#
# Kill-switches:
#   SUTRA_BASH_SUMMARY=0              → hook disabled (env)
#   ~/.sutra-bash-summary-disabled    → hook disabled (file)

set -uo pipefail

# ─── Kill-switches ─────────────────────────────────────────────────────────
[ "${SUTRA_BASH_SUMMARY:-1}" = "0" ] && exit 0
[ -f "$HOME/.sutra-bash-summary-disabled" ] && exit 0

# ─── Read JSON payload from stdin ──────────────────────────────────────────
[ -t 0 ] && exit 0
_JSON=$(cat 2>/dev/null || true)
[ -z "$_JSON" ] && exit 0

# ─── Extract Bash command ──────────────────────────────────────────────────
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -z "$CMD" ] && exit 0

# Strip leading env-var prefixes (FOO=bar BAZ=qux <cmd>)
CMD_CLEAN=$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]*([A-Z_][A-Z0-9_]*=[^[:space:]]*[[:space:]]+)*//')

# ─── Ask Trust Mode (single source of truth) ───────────────────────────────
HELPER="${CLAUDE_PLUGIN_ROOT:-}/lib/sh_trust_mode.py"
[ -f "$HELPER" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0

_TIMEOUT=""
if command -v timeout >/dev/null 2>&1; then _TIMEOUT="timeout 2"
elif command -v gtimeout >/dev/null 2>&1; then _TIMEOUT="gtimeout 2"
fi

OUT=$(printf '%s' "$CMD_CLEAN" | $_TIMEOUT python3 "$HELPER" 2>/dev/null) || exit 0
[ -z "$OUT" ] && exit 0

PROMPT=$(printf '%s' "$OUT" | jq -r '.prompt // false' 2>/dev/null)
# Trust Mode says auto-approve → no annotation. PermissionRequest gate handles allow.
[ "$PROMPT" != "true" ] && exit 0

# ─── Trust Mode says prompt: build deterministic category text ─────────────
CATEGORY=$(printf '%s' "$OUT" | jq -r '.category // "unknown"' 2>/dev/null)

case "$CATEGORY" in
  git-mutation)
    LABEL="🚨 Git catastrophic mutation"
    HINT="Rewrites remote history (force-push) or deletes untracked files irrecoverably (clean -f*)."
    ;;
  privilege)
    LABEL="🚨 Privilege escalation"
    HINT="Changes auth scope on this machine (sudo / su / doas / pkexec)."
    ;;
  recursive-delete)
    LABEL="⚠️ Recursive delete (unsafe path)"
    HINT="rm -rf on a path outside the safe-path allowlist (dist/build/node_modules/.cache/etc)."
    ;;
  disk-system)
    LABEL="🚨 Disk / system catastrophe"
    HINT="Could destroy disks, system state, or apply recursive permissions."
    ;;
  fetch-exec)
    LABEL="🚨 Fetch-and-exec"
    HINT="Pipes downloaded content directly into a shell."
    ;;
  remote-state)
    LABEL="⚠️ Remote / shared-state mutation"
    HINT="Changes resources outside this machine — repos, clusters, databases, packages."
    ;;
  *)
    LABEL="⚠️ Catastrophic"
    HINT=$(printf '%s' "$OUT" | jq -r '.reason // "Review the command before approving."' 2>/dev/null)
    ;;
esac

REASON="${LABEL}. ${HINT}"

# ─── Telemetry ─────────────────────────────────────────────────────────────
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
if [ -n "$REPO_ROOT" ]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  VERB=$(printf '%s' "$CMD_CLEAN" | awk '{print $1}' | tr -d '"\\' | tr '\n\r' '  ' | head -c 50)
  TS=$(date +%s)
  echo "{\"ts\":$TS,\"event\":\"bash-summary-v2.7\",\"verb\":\"$VERB\",\"category\":\"$CATEGORY\"}" \
    >> "$REPO_ROOT/.enforcement/bash-summary.jsonl" 2>/dev/null
fi

# ─── Emit JSON ─────────────────────────────────────────────────────────────
SAFE_REASON=$(printf '%s' "$REASON" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r\t' '   ')

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$SAFE_REASON"

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (per PROTO-000)
#
# ### 1. Measurement mechanism
# Per-fire row in .enforcement/bash-summary.jsonl: {ts, verb, category}.
# Pre-v2.7 schema added llm_used + dangerous + summary_len; dropped because
# they tracked Haiku availability (no longer applicable) and danger emoji
# (now derived from category).
#
# ### 2. Adoption mechanism
# Registered in hooks.json under PreToolUse[Bash]. Fleet receives via plugin
# auto-update on next Claude Code session.
#
# ### 3. Monitoring / escalation
# Warn: false-prompt rate >5% (commands that prompted but should auto-allow
# under Trust Mode — indicates a category mis-classification in
# sh_trust_mode.py, not in this hook).
# Breach: founder-reported wrong category text → fix the case statement here
# OR fix the category in sh_trust_mode.py.
#
# ### 4. Iteration trigger
# New prompt category added to sh_trust_mode.py → add the matching case here.
# That is the only coupling between the two files.
#
# ### 5. DRI
# Sutra marketplace department.
#
# ### 6. Decommission criteria
# Retire when Anthropic ships native permission-summary support upstream.
