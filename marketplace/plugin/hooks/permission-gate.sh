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
# ADR-003 §4 telemetry: also sets MATCHED_TOOL_CLASS + MATCHED_TOOL_FAMILY +
# MATCHED_DECISION_BASIS. tool_family is null for non-MCP rows.
MATCHED_PATTERN=""
MATCHED_TOOL_CLASS=""
MATCHED_TOOL_FAMILY=""
MATCHED_DECISION_BASIS=""

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


# ---- ADR-003: MCP Trust Mode (v2.17.0+) ----
# Calls lib/mcp_trust_mode.py with the PermissionRequest payload on stdin.
# Returns "auto-approve" if the helper says prompt=false; "no match" otherwise.
_match_mcp() {
  local helper="${CLAUDE_PLUGIN_ROOT:-}/lib/mcp_trust_mode.py"
  [ -f "$helper" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1

  local _to=""
  if command -v timeout >/dev/null 2>&1; then _to="timeout 2"
  elif command -v gtimeout >/dev/null 2>&1; then _to="gtimeout 2"
  fi

  local out
  out=$(printf '%s' "$_JSON" | $_to python3 "$helper" 2>/dev/null) || return 1
  [ -z "$out" ] && return 1

  local prompt category
  prompt=$(printf '%s' "$out" | jq -r 'if .prompt == false then "false" else "true" end' 2>/dev/null)
  if [ "$prompt" = "false" ]; then
    category=$(printf '%s' "$out" | jq -r '.category // "mcp-allowlist"' 2>/dev/null)
    MATCHED_PATTERN="${TOOL}"
    MATCHED_DECISION_BASIS="$category"
    MATCHED_TOOL_CLASS="mcp"
    return 0
  fi
  return 1
}

# ---- ADR-003: First-time Edit/Write inside cwd (v2.17.0+) ----
# Auto-approves Edit/Write to paths inside cwd-tree EXCEPT entries in the
# prompt-list (secrets, deploy/CI configs, repo metadata).
_match_first_time_edit() {
  local f="$1"
  local root="${CLAUDE_PROJECT_DIR:-$(pwd)}"

  # Resolve to a path relative to cwd-tree.
  case "$f" in
    /*)
      case "$f" in
        "$root"/*) f="${f#$root/}" ;;
        *) return 1 ;;  # outside cwd → fall through to prompt
      esac
      ;;
  esac

  # Defense: reject path traversal.
  case "$f" in *..*) return 1 ;; esac

  # Prompt-list (overrides allow).
  case "$f" in
    .claude/settings*.json|.claude/settings*.local.json) return 1 ;;
    .env|.env.*|*/.env|*/.env.*) return 1 ;;
    .git/*|*/.git/*) return 1 ;;
    .npmrc|*/.npmrc|.pypirc|*/.pypirc) return 1 ;;
    *credentials.json|*/credentials.json|*secrets.yaml|*/secrets.yaml|*.secret*|*/.secret*) return 1 ;;
    .github/workflows/*|.circleci/*|.gitlab-ci.yml|*/.gitlab-ci.yml) return 1 ;;
    vercel.json|fly.toml|render.yaml|netlify.toml) return 1 ;;
    docker-compose*.yml|docker-compose*.yaml|*/docker-compose*.yml|*/docker-compose*.yaml) return 1 ;;
    k8s/*|*/k8s/*|helm/*/values*.yml|helm/*/values*.yaml|*/helm/*/values*.yml|*/helm/*/values*.yaml) return 1 ;;
    .terraform/*|*/.terraform/*|*.tfvars|*.tf) return 1 ;;
    Pulumi.*|*/Pulumi.*) return 1 ;;
    wrangler.toml|railway.json|firebase.json) return 1 ;;
    cloudbuild.yaml|app.yaml) return 1 ;;
    supabase/*|*/supabase/*) return 1 ;;
  esac

  # Allow.
  MATCHED_PATTERN="${TOOL}(${f})"
  MATCHED_DECISION_BASIS="first-time-edit-allow"
  MATCHED_TOOL_CLASS="edit-first-time"
  return 0
}

# ---- Trust Mode (v2.5+; sole Bash matcher post-v2.7.0) ----
# After Tier 1 falls through (no narrow allowlist match), Trust Mode
# auto-approves EVERYTHING except commands matching one of the prompt
# categories (git catastrophic = force-push + clean -f*; privilege;
# recursive-delete unsafe paths; disk/system; fetch-and-exec;
# remote/shared-state with gh refined to delete-class only).
# Helper: lib/sh_trust_mode.py. v2.7.0 removed the v2.4 Tier 1.5
# compositional matcher + env-shadowing guard as superseded residue.
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
      MATCHED_TOOL_CLASS="bash"
      MATCHED_DECISION_BASIS="tier-1"
    elif _match_bash_trust_mode "$CMD"; then
      MATCHED_TOOL_CLASS="bash"
      MATCHED_DECISION_BASIS="trust-mode-allowlist"
    else
      exit 0
    fi
    ;;
  Write|Edit|MultiEdit)
    [ -z "$FILE" ] && exit 0
    if _match_write "$FILE"; then
      MATCHED_TOOL_CLASS="write"
      MATCHED_DECISION_BASIS="tier-1"
    elif _match_first_time_edit "$FILE"; then
      :   # ADR-003: first-time edit inside cwd-tree (sets vars internally)
    else
      exit 0
    fi
    ;;
  mcp__*)
    # ADR-003: MCP tool auto-approve via lib/mcp_trust_mode.py
    if _match_mcp; then
      :   # mcp_trust_mode helper sets MATCHED_PATTERN + tool_class + basis
      # ADR-003 §4: parse tool_family from mcp__<server>__<tool>
      _family="${TOOL#mcp__}"; _family="${_family%%__*}"
      case "$_family" in
        claude_ai_Slack)            MATCHED_TOOL_FAMILY="slack" ;;
        claude_ai_Gmail)            MATCHED_TOOL_FAMILY="gmail" ;;
        claude_ai_Apollo_io)        MATCHED_TOOL_FAMILY="apollo" ;;
        claude_ai_Atlassian_Rovo)   MATCHED_TOOL_FAMILY="atlassian" ;;
        claude_ai_HubSpot)          MATCHED_TOOL_FAMILY="hubspot" ;;
        claude_ai_Google_Drive)     MATCHED_TOOL_FAMILY="drive" ;;
        claude_ai_Google_Calendar)  MATCHED_TOOL_FAMILY="calendar" ;;
        claude_ai_Read_ai)          MATCHED_TOOL_FAMILY="read_ai" ;;
        playwright)                 MATCHED_TOOL_FAMILY="playwright" ;;
        context7)                   MATCHED_TOOL_FAMILY="context7" ;;
        *)                          MATCHED_TOOL_FAMILY="unknown" ;;
      esac
    else
      exit 0
    fi
    ;;
  *)
    exit 0
    ;;
esac

# ---- we have a match: emit allow decision + persist rule ----
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null || true
# ADR-003 §4: row schema includes tool_class · tool_family (null for non-MCP) ·
# decision_basis. jq used to emit proper null when MATCHED_TOOL_FAMILY is empty.
jq -nc \
  --argjson ts "$(date +%s)" \
  --arg tool "$TOOL" \
  --arg pattern "$MATCHED_PATTERN" \
  --arg tool_class "$MATCHED_TOOL_CLASS" \
  --arg tool_family "$MATCHED_TOOL_FAMILY" \
  --arg decision_basis "$MATCHED_DECISION_BASIS" \
  '{
    ts: $ts,
    tool: $tool,
    pattern: $pattern,
    decision: "allow",
    persisted: true,
    tool_class: $tool_class,
    tool_family: (if $tool_family == "" then null else $tool_family end),
    decision_basis: $decision_basis
  }' >> "$REPO_ROOT/.enforcement/permission-gate.jsonl" 2>/dev/null || true

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
