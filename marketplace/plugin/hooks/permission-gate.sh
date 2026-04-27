#!/bin/bash
# PERMISSION-GATE — meta-permission for Sutra plugin.
# PermissionRequest hook: auto-approves Sutra-scope patterns AND persists the
# matched rule to project .claude/settings.local.json so the next invocation
# bypasses this hook entirely (Claude Code's native allow-list catches it).
#
# Charter: sutra/os/charters/PERMISSIONS.md
# Mechanism: returns {decision: {behavior: allow, updatedPermissions: [...]}}
#            per Claude Code PermissionRequest hook contract (docs 2026-04-24).
#
# DEFAULT-ON (UX hook, not governance — D32's default-off rule doesn't apply).
#
# Kill-switch: touch ~/.sutra-permissions-disabled  OR  SUTRA_PERMISSIONS_DISABLED=1
# Fail-open: any error / malformed input → exit 0 silently → normal prompt flow.

set -u

# ---- kill-switches ----
[ -e "$HOME/.sutra-permissions-disabled" ] && exit 0
[ "${SUTRA_PERMISSIONS_DISABLED:-}" = "1" ] && exit 0

# ---- stdin guard ----
if [ -t 0 ]; then exit 0; fi
_JSON=$(cat 2>/dev/null || true)
[ -z "$_JSON" ] && exit 0

# ---- parse input ----
if command -v jq >/dev/null 2>&1; then
  TOOL=$(printf '%s' "$_JSON" | jq -r '.tool_name // empty' 2>/dev/null)
  CMD=$(printf '%s' "$_JSON"  | jq -r '.tool_input.command // empty' 2>/dev/null)
  FILE=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
else
  exit 0
fi

[ -z "$TOOL" ] && exit 0

# ---- defense: reject shell combinators that widen scope ----
_has_combinator() {
  local c="$1"
  # Reject: shell separators, pipes, cmd-subst, redirections, backgrounding.
  case "$c" in
    *';'*|*'&&'*|*'||'*|*'|'*|*'`'*|*'$('*|*'>'*|*'<'*|*'&'*) return 0 ;;
  esac
  # Reject control characters (newlines, CR, tab-as-separator etc.).
  if printf '%s' "$c" | LC_ALL=C tr -d '\011\040' | LC_ALL=C grep -q '[[:cntrl:]]' 2>/dev/null; then
    return 0
  fi
  # Reject explicit shell/interpreter sneak-ins.
  case "$c" in
    *'bash -c'*|*'sh -c'*|*'zsh -c'*|*'eval '*|*'exec '*) return 0 ;;
  esac
  return 1
}

# ---- match logic: returns 0 if in scope, 1 otherwise. Sets MATCHED_PATTERN. ----
MATCHED_PATTERN=""

_match_bash() {
  local c="$1"
  c="${c#"${c%%[![:space:]]*}"}"

  if _has_combinator "$c"; then
    return 1
  fi

  # --- Tier 1: plugin dispatcher ---
  case "$c" in
    'sutra')                     MATCHED_PATTERN='Bash(sutra)'; return 0 ;;
    'sutra '*)                   MATCHED_PATTERN='Bash(sutra:*)'; return 0 ;;
  esac

  # --- Tier 1: plugin-internal scripts/hooks ---
  case "$c" in
    'bash '"${CLAUDE_PLUGIN_ROOT:-__NOMATCH__}"/*)
      MATCHED_PATTERN='Bash(bash ${CLAUDE_PLUGIN_ROOT}/*)'; return 0 ;;
    'bash '"$HOME"'/.claude/plugins/cache/sutra/'*)
      MATCHED_PATTERN='Bash(bash ~/.claude/plugins/cache/sutra/*)'; return 0 ;;
  esac

  # --- Tier 1: Claude Code plugin lifecycle, scoped to Sutra ---
  case "$c" in
    'claude plugin marketplace update sutra')
      MATCHED_PATTERN='Bash(claude plugin marketplace update sutra)'; return 0 ;;
    'claude plugin update core'*)
      MATCHED_PATTERN='Bash(claude plugin update core*)'; return 0 ;;
    'claude plugin update sutra'*)
      MATCHED_PATTERN='Bash(claude plugin update sutra*)'; return 0 ;;
    'claude plugin uninstall core'*)
      MATCHED_PATTERN='Bash(claude plugin uninstall core*)'; return 0 ;;
    'claude plugin uninstall sutra'*)
      MATCHED_PATTERN='Bash(claude plugin uninstall sutra*)'; return 0 ;;
  esac

  # --- Tier 1: scoped mkdir for governance dirs ---
  case "$c" in
    'mkdir -p .claude'|'mkdir -p .claude/'*)
      MATCHED_PATTERN='Bash(mkdir -p .claude*)'; return 0 ;;
    'mkdir -p .enforcement'|'mkdir -p .enforcement/'*)
      MATCHED_PATTERN='Bash(mkdir -p .enforcement*)'; return 0 ;;
    'mkdir -p .context'|'mkdir -p .context/'*)
      MATCHED_PATTERN='Bash(mkdir -p .context*)'; return 0 ;;
  esac

  # --- Tier 1: scoped touch for marker files ---
  case "$c" in
    'touch .claude/depth-registered'|\
    'touch .claude/input-routed'|\
    'touch .claude/sutra-deploy-depth5'|\
    'touch .claude/build-layer-registered')
      MATCHED_PATTERN="Bash($c)"; return 0 ;;
  esac

  return 1
}


# ---- env-level shadowing guard (codex round 2 + 3) ----
# If any allowlisted primitive name is shadowed by an exported bash function
# (BASH_FUNC_name%%=() or BASH_FUNC_name()=()) OR is defined as a function in
# the hook's own shell (declare -F), refuse auto-approve. The Bash tool runs
# commands in a subshell that inherits exported functions — an attacker with
# control over env could replace ls/cat/grep/etc. Fall through to normal
# prompt so the user sees the command and manually approves.
_compositional_primitives_re='ls|cat|head|tail|wc|echo|printf|pwd|date|whoami|which|basename|dirname|realpath|grep|cut|uniq|tr|column'

_env_has_shadowing() {
  # Gate 2a: env regex (patched bash 4.3+).
  if env | grep -qE "^BASH_FUNC_(${_compositional_primitives_re})(%%|\(\))=" 2>/dev/null; then
    return 0
  fi
  # Gate 2b: declare -F universal fallback (covers legacy formats).
  local name
  for name in ls cat head tail wc echo printf pwd date whoami which basename dirname realpath grep cut uniq tr column; do
    if declare -F "$name" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

# ---- compositional matcher (Tier 1.5, v2.4+) ----
# Calls lib/sh_lex_check.py. Sets MATCHED_PATTERN on success. Fail-safe-to-
# prompt: any error returns 1 (fall-through to normal permission dialog).
_match_bash_compositional() {
  local c="$1"
  # Gate 2: env shadowing.
  if _env_has_shadowing; then
    return 1
  fi
  local helper="${CLAUDE_PLUGIN_ROOT:-}/lib/sh_lex_check.py"
  [ -f "$helper" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local out
  # Portable timeout: prefer GNU timeout (brew) or gtimeout (macOS), else run
  # without timeout (python3 shlex is fast; fail-safe if it hangs via hook timeout).
  local _to=""
  if command -v timeout >/dev/null 2>&1; then _to="timeout 2"
  elif command -v gtimeout >/dev/null 2>&1; then _to="gtimeout 2"
  fi
  out=$(printf '%s' "$c" | $_to python3 "$helper" 2>/dev/null) || return 1
  [ -z "$out" ] && return 1
  local safe pattern
  safe=$(printf '%s' "$out" | jq -r '.safe // false' 2>/dev/null)
  pattern=$(printf '%s' "$out" | jq -r '.pattern // empty' 2>/dev/null)
  if [ "$safe" = "true" ] && [ -n "$pattern" ]; then
    MATCHED_PATTERN="$pattern"
    return 0
  fi
  return 1
}

_match_write() {
  local f="$1"
  case "$f" in
    /*)
      local root="${CLAUDE_PROJECT_DIR:-}"
      [ -z "$root" ] && return 1
      case "$f" in
        "$root"/*) f="${f#$root/}" ;;
        *) return 1 ;;
      esac
      ;;
  esac
  case "$f" in *..*) return 1 ;; esac

  case "$f" in
    '.claude/depth-registered'|\
    '.claude/input-routed'|\
    '.claude/sutra-deploy-depth5'|\
    '.claude/build-layer-registered'|\
    '.claude/sutra-project.json'|\
    '.claude/sutra-estimation.log'|\
    '.claude/codex-directive-pending')
      MATCHED_PATTERN="Write($f)"; return 0 ;;
    '.claude/logs/'*)
      MATCHED_PATTERN='Write(.claude/logs/*)'; return 0 ;;
    '.enforcement/codex-reviews/'*)
      MATCHED_PATTERN='Write(.enforcement/codex-reviews/*)'; return 0 ;;
    '.context/codex-session-id')
      MATCHED_PATTERN='Write(.context/codex-session-id)'; return 0 ;;
  esac

  return 1
}


# ---- Tier 1.6 Trust Mode (v2.5+) — denylist-based fallback ----
# After Tier 1 + Tier 1.5 fall through (no narrow allowlist match), Trust
# Mode auto-approves EVERYTHING except commands matching one of the 6 prompt
# categories (git mutations, privilege, recursive delete, disk/system,
# fetch-and-exec, remote/shared-state). Helper: lib/sh_trust_mode.py.
_match_bash_trust_mode() {
  local c="$1"
  local helper="${CLAUDE_PLUGIN_ROOT:-}/lib/sh_trust_mode.py"
  [ -f "$helper" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1

  local _to=""
  if command -v timeout >/dev/null 2>&1; then _to="timeout 2"
  elif command -v gtimeout >/dev/null 2>&1; then _to="gtimeout 2"
  fi

  local out
  out=$(printf '%s' "$c" | $_to python3 "$helper" 2>/dev/null) || return 1
  [ -z "$out" ] && return 1

  local prompt pattern
  prompt=$(printf '%s' "$out" | jq -r 'if .prompt == false then "false" else "true" end' 2>/dev/null)
  if [ "$prompt" = "false" ]; then
    pattern=$(printf '%s' "$out" | jq -r '.pattern // empty' 2>/dev/null)
    [ -z "$pattern" ] && pattern="Bash(trust-mode-auto-approve)"
    MATCHED_PATTERN="$pattern"
    return 0
  fi
  return 1
}

# ---- dispatch by tool ----
case "$TOOL" in
  Bash)
    [ -z "$CMD" ] && exit 0
    if _match_bash "$CMD"; then
      :   # Tier 1: narrow allowlist (sutra, plugin lifecycle, markers)
    elif _match_bash_compositional "$CMD"; then
      :   # Tier 1.5: compositional-read strict allowlist (v2.4+)
    elif _match_bash_trust_mode "$CMD"; then
      :   # Tier 1.6: Trust Mode denylist (v2.5+)
    else
      exit 0
    fi
    ;;
  Write|Edit|MultiEdit)
    [ -z "$FILE" ] && exit 0
    _match_write "$FILE" || exit 0
    ;;
  *)
    exit 0
    ;;
esac

# ---- we have a match: emit allow decision + persist rule ----
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null || true
printf '{"ts":%s,"tool":"%s","pattern":"%s","decision":"allow","persisted":true}\n' \
  "$(date +%s)" "$TOOL" "$MATCHED_PATTERN" \
  >> "$REPO_ROOT/.enforcement/permission-gate.jsonl" 2>/dev/null || true

RULE_CONTENT="${MATCHED_PATTERN#*\(}"
RULE_CONTENT="${RULE_CONTENT%\)}"

if command -v jq >/dev/null 2>&1; then
  jq -nc \
    --arg tool "$TOOL" \
    --arg rule "$RULE_CONTENT" \
    '{
      hookSpecificOutput: {
        hookEventName: "PermissionRequest",
        decision: {
          behavior: "allow",
          updatedPermissions: [
            {
              type: "addRules",
              rules: [ { toolName: $tool, ruleContent: $rule } ],
              behavior: "allow",
              destination: "localSettings"
            }
          ]
        }
      }
    }'
else
  printf '{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}\n'
fi
exit 0

#
# ## Operationalization
#
# ### 1. Measurement mechanism
# Each hook fire appends to .enforcement/permission-gate.jsonl.
#
# ### 2. Adoption mechanism
# Registered in hooks.json under PermissionRequest (matcher: Bash|Write|Edit|MultiEdit).
# Ships default-ON in plugin v1.13.0.
#
# ### 3. Monitoring / escalation
# Warn: hit_rate <80% over 7d → allow-list incomplete.
# Breach: ≥1 founder-reported false positive → patch + post-mortem.
#
# ### 4. Iteration trigger
# New hook touches path outside Tier 1 → charter §4 update BEFORE ship.
#
# ### 5. DRI
# Plugin Marketplace dept. Charter: Sutra-OS (Asawa-CEO).
#
# ### 6. Decommission criteria
# Claude Code ships plugin-level permissions.allow bundling → migrate + retire.
