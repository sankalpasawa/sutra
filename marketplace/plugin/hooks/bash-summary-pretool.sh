#!/usr/bin/env bash
# bash-summary-pretool.sh — Plain-English summary for Bash permission prompts
#
# BUILD-LAYER: L0 (fleet)
# Source:      FEEDBACK-LOG 2026-04-24 — external user, routed via founder
# Plan:        holding/research/2026-04-24-permission-summary-plan.md
# Target:      Sutra plugin v1.4.0
#
# Charter:     sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md § Part 4
# Principles:  P7 (Human Is the Final Authority — "makes trade-off visible")
#              P11 (Human Confidence Through Clarity)
# Holding:     holding/HUMAN-AI-INTERACTION.md (P7, P11 sections link back here)
#
# ⚠ When editing this hook, update the registry entry in the charter (Part 4)
#   AND add a TODO to holding/TODO.md referencing 'bash-summary-pretool' stem.
#   See cascade-check.sh D13 / charter Part 4 "Cascade rule".
#
# Event:       PreToolUse on Bash
# Behavior:    ALWAYS exit 0 (never blocks). Emits a plain-English summary via
#              JSON hookSpecificOutput.permissionDecisionReason, which Claude
#              Code surfaces inline with the approval dialog.
# Two-stage:   (v0) rules-based verb matcher — ~80% coverage, <10ms, zero cost
#              (v1) LLM fallback — Haiku call when rules return unknown OR the
#                   command is composed (pipes / subshells / heredoc / &&). Cached.
#
# Kill-switches:
#   SUTRA_BASH_SUMMARY=0              → whole hook disabled; exit 0 silently
#   SUTRA_PERMISSION_LLM=0            → rules-only mode; no LLM fallback
#   ~/.sutra-bash-summary-disabled    → file kill-switch (mirrors .rtk-disabled)
#
# Failure mode: any error path exits 0 silently; better no summary than wrong/blocked.

set -uo pipefail

# ─── Kill-switches ──────────────────────────────────────────────────────────
if [ "${SUTRA_BASH_SUMMARY:-1}" = "0" ] || [ -f "$HOME/.sutra-bash-summary-disabled" ]; then
  exit 0
fi

# ─── Read JSON payload from stdin ───────────────────────────────────────────
_JSON=""
if [ ! -t 0 ]; then
  _JSON=$(cat)
fi
[ -z "$_JSON" ] && exit 0

# ─── Extract the Bash command ───────────────────────────────────────────────
CMD=""
if command -v jq >/dev/null 2>&1; then
  CMD=$(printf '%s' "$_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  CMD=$(printf '%s' "$_JSON" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi
[ -z "$CMD" ] && exit 0

# ─── Normalize: strip leading env-var prefixes (FOO=bar BAZ=qux <cmd>) ──────
CMD_CLEAN=$(printf '%s' "$CMD" | sed -E 's/^[[:space:]]*([A-Z_][A-Z0-9_]*=[^[:space:]]*[[:space:]]+)*//')

# ─── Detect composed commands (triggers LLM fallback) ───────────────────────
_is_composed() {
  case "$1" in
    *'|'*|*'&&'*|*';'*|*'$('*|*'`'*|*'<<'*|*'<<<'*) return 0 ;;
  esac
  return 1
}

# ─── Escape text for safe JSON output ───────────────────────────────────────
_json_escape() {
  printf '%s' "$1" \
    | sed 's/\\/\\\\/g' \
    | sed 's/"/\\"/g' \
    | tr '\n' ' ' \
    | tr '\r' ' ' \
    | tr '\t' ' '
}

# ─── Extract first positional argument after the verb ──────────────────────
_first_arg() {
  printf '%s' "$1" \
    | awk '{ for (i=2; i<=NF; i++) if ($i !~ /^-/) { print $i; exit } }'
}

# ─── Extract host from URL (best-effort) ───────────────────────────────────
_url_host() {
  printf '%s' "$1" | sed -E 's~^https?://([^/]+).*~\1~; s~^ftp://([^/]+).*~\1~'
}

# ─── v0 rules matcher ──────────────────────────────────────────────────────
# Sets: SUMMARY, DANGEROUS (0|1), MATCHED (0|1)
_rules_match() {
  local cmd="$1"
  SUMMARY=""
  DANGEROUS=0
  MATCHED=0

  # ⚠ Highest-priority destructive patterns (check first)
  case "$cmd" in
    'sudo rm -rf /'*|'rm -rf /'|'rm -rf / '*)
      SUMMARY="⚠ CATASTROPHIC — attempts to delete the entire system root. Do NOT approve."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'rm -rf '*|'rm -Rf '*|'rm -fr '*|'rm -fR '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="⚠ DESTRUCTIVE — will delete '${target}' and everything inside it. This cannot be undone."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'rm -r '*|'rm -R '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="⚠ will delete the folder '${target}' and everything inside it."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'rm '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will delete the file '${target}'."
      MATCHED=1; return 0 ;;
  esac

  # curl | sh / wget | bash — pipe-to-shell is destructive regardless of rules table
  case "$cmd" in
    *'curl '*'|'*' sh'*|*'curl '*'|'*' bash'*|*'wget '*'|'*' sh'*|*'wget '*'|'*' bash'*)
      local url host
      url=$(printf '%s' "$cmd" | grep -oE 'https?://[^ |]+' | head -1)
      host=$(_url_host "$url")
      SUMMARY="⚠ DESTRUCTIVE — downloads a script from '${host}' and runs it immediately as shell. Anything in that script will execute on your machine."
      DANGEROUS=1; MATCHED=1; return 0 ;;
  esac

  # git destructive / common
  case "$cmd" in
    'git reset --hard'*)
      SUMMARY="⚠ DESTRUCTIVE — will discard all uncommitted changes in your git working tree."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'git clean -f'*|'git clean -fd'*|'git clean -fdx'*)
      SUMMARY="⚠ DESTRUCTIVE — will permanently delete untracked files from your git tree."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'git push --force'*|'git push -f'*|'git push --force-with-lease'*)
      SUMMARY="⚠ will force-push to the remote, overwriting remote history."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'git push'*)
      SUMMARY="will push your local commits to the remote repository."
      MATCHED=1; return 0 ;;
    'git clone '*)
      local url host
      url=$(printf '%s' "$cmd" | awk '{for(i=2;i<=NF;i++) if($i !~ /^-/){print $i; exit}}')
      host=$(_url_host "$url")
      [ -z "$host" ] && host="$url"
      SUMMARY="will clone a repository from '${host}' into a local folder."
      MATCHED=1; return 0 ;;
    'git commit'*)
      SUMMARY="will save a snapshot of your staged changes to your local git history."
      MATCHED=1; return 0 ;;
    'git pull'*)
      SUMMARY="will download new commits from the remote and merge them into your branch."
      MATCHED=1; return 0 ;;
    'git checkout -- '*|'git restore '*)
      SUMMARY="⚠ will discard changes in the listed files, reverting them to the last committed version."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'git add '*)
      SUMMARY="will stage the listed files for the next commit."
      MATCHED=1; return 0 ;;
    'git status'*|'git log'*|'git diff'*|'git blame'*|'git show'*|'git branch'*|'git remote'*)
      SUMMARY="will read git repository information (read-only)."
      MATCHED=1; return 0 ;;
  esac

  # dd / disk / device-level — catastrophic
  case "$cmd" in
    'dd '*|'sudo dd '*)
      SUMMARY="⚠ DESTRUCTIVE — disk-level write. 'dd' can wipe entire drives. Verify the target device before approving."
      DANGEROUS=1; MATCHED=1; return 0 ;;
  esac
  if printf '%s' "$cmd" | grep -qE '>[[:space:]]*/dev/'; then
    SUMMARY="⚠ DESTRUCTIVE — writes directly to a system device. Can corrupt drives or hardware state."
    DANGEROUS=1; MATCHED=1; return 0
  fi

  # sudo wrapper (non-dd already handled)
  case "$cmd" in
    'sudo '*)
      local inner
      inner=$(printf '%s' "$cmd" | sed -E 's/^sudo[[:space:]]+//')
      SUMMARY="⚠ runs with admin privileges: ${inner}"
      DANGEROUS=1; MATCHED=1; return 0 ;;
  esac

  # Network
  case "$cmd" in
    'curl '*)
      local url host
      url=$(printf '%s' "$cmd" | grep -oE 'https?://[^ ]+' | head -1)
      host=$(_url_host "$url")
      [ -z "$host" ] && host="(unspecified host)"
      SUMMARY="will download data from '${host}'."
      MATCHED=1; return 0 ;;
    'wget '*)
      local url host
      url=$(printf '%s' "$cmd" | grep -oE 'https?://[^ ]+' | head -1)
      host=$(_url_host "$url")
      [ -z "$host" ] && host="(unspecified host)"
      SUMMARY="will download a file from '${host}'."
      MATCHED=1; return 0 ;;
    'ssh '*)
      local host
      host=$(_first_arg "$cmd")
      SUMMARY="will connect to the remote machine '${host}' over SSH."
      MATCHED=1; return 0 ;;
    'scp '*|'rsync '*)
      SUMMARY="will copy files between machines over the network."
      MATCHED=1; return 0 ;;
  esac

  # Filesystem (benign)
  case "$cmd" in
    'mkdir '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will create the folder '${target}'."
      MATCHED=1; return 0 ;;
    'cp '*)
      SUMMARY="will copy files to a new location (the original stays in place)."
      MATCHED=1; return 0 ;;
    'mv '*)
      SUMMARY="will move (or rename) files. The original location will no longer have them."
      MATCHED=1; return 0 ;;
    'chmod '*)
      local target
      target=$(printf '%s' "$cmd" | awk '{print $NF}')
      SUMMARY="will change permissions on '${target}' (who can read/write/execute it)."
      MATCHED=1; return 0 ;;
    'chown '*)
      SUMMARY="will change file ownership (which user/group the file belongs to)."
      MATCHED=1; return 0 ;;
    'touch '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will create an empty file at '${target}' (or update its timestamp if it exists)."
      MATCHED=1; return 0 ;;
    'ln -s '*|'ln '*)
      SUMMARY="will create a link (shortcut) pointing to another file."
      MATCHED=1; return 0 ;;
    'tar '*|'zip '*|'unzip '*)
      SUMMARY="will pack or unpack files into/from an archive."
      MATCHED=1; return 0 ;;
  esac

  # Read-only
  case "$cmd" in
    'cat '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will read the contents of '${target}' (read-only)."
      MATCHED=1; return 0 ;;
    'head '*|'tail '*|'less '*|'more '*)
      SUMMARY="will display file contents on screen (read-only)."
      MATCHED=1; return 0 ;;
    'ls '*|'ls'|'ll '*|'ll')
      SUMMARY="will list files in a folder (read-only)."
      MATCHED=1; return 0 ;;
    'pwd'|'whoami'|'date'|'hostname')
      SUMMARY="will print a small piece of system info (read-only)."
      MATCHED=1; return 0 ;;
    'find '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will search for files inside '${target}' (read-only)."
      MATCHED=1; return 0 ;;
    'grep '*|'rg '*|'ag '*)
      SUMMARY="will search for text inside files (read-only)."
      MATCHED=1; return 0 ;;
  esac

  # Redirection — check >> (append) BEFORE > (overwrite) so >> isn't misread as >
  if printf '%s' "$cmd" | grep -qE '>>[[:space:]]*[^ &]+$'; then
    local target
    target=$(printf '%s' "$cmd" | sed -E 's/.*>>[[:space:]]*([^ ]+)[[:space:]]*$/\1/')
    SUMMARY="will append text to '${target}' (keeps existing contents)."
    MATCHED=1; return 0
  fi
  if printf '%s' "$cmd" | grep -qE '[^>]>[[:space:]]*[^ &>]+$'; then
    local target
    target=$(printf '%s' "$cmd" | sed -E 's/.*[^>]>[[:space:]]*([^ ]+)[[:space:]]*$/\1/')
    SUMMARY="⚠ will write text to '${target}' — any existing contents will be overwritten."
    DANGEROUS=1; MATCHED=1; return 0
  fi

  # Python
  case "$cmd" in
    'python '*-c*|'python3 '*-c*)
      SUMMARY="will run a short snippet of Python code inline."
      MATCHED=1; return 0 ;;
    'python '*|'python3 '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will run the Python script '${target}'."
      MATCHED=1; return 0 ;;
    'pip install '*|'pip3 install '*|'pip install --'*)
      SUMMARY="will install one or more Python packages (downloads from PyPI)."
      MATCHED=1; return 0 ;;
    'pip uninstall '*|'pip3 uninstall '*)
      SUMMARY="will uninstall one or more Python packages."
      MATCHED=1; return 0 ;;
  esac

  # Node / npm / yarn / pnpm / bun
  case "$cmd" in
    'npm install'*|'npm i '*|'yarn add '*|'pnpm add '*|'bun add '*|'bun install'*)
      SUMMARY="will install one or more Node.js packages (downloads from the registry)."
      MATCHED=1; return 0 ;;
    'npm run '*|'yarn '*|'pnpm '*|'bun run '*)
      SUMMARY="will run a script defined in package.json."
      MATCHED=1; return 0 ;;
    'node '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will run the Node.js script '${target}'."
      MATCHED=1; return 0 ;;
  esac

  # Package managers (system)
  case "$cmd" in
    'brew install '*)
      SUMMARY="will install a Homebrew package on your Mac."
      MATCHED=1; return 0 ;;
    'brew uninstall '*|'brew remove '*)
      SUMMARY="will uninstall a Homebrew package."
      MATCHED=1; return 0 ;;
    'apt install '*|'apt-get install '*|'yum install '*|'dnf install '*|'pacman -S '*)
      SUMMARY="⚠ will install a system package (requires admin privileges)."
      DANGEROUS=1; MATCHED=1; return 0 ;;
  esac

  # Process control
  case "$cmd" in
    'kill -9 '*|'kill -KILL '*)
      SUMMARY="⚠ DESTRUCTIVE — will forcibly terminate a running process (no chance to save state)."
      DANGEROUS=1; MATCHED=1; return 0 ;;
    'kill '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will ask process ${target} to stop (it may clean up first)."
      MATCHED=1; return 0 ;;
    'pkill '*|'killall '*)
      SUMMARY="⚠ will terminate all processes matching a name."
      DANGEROUS=1; MATCHED=1; return 0 ;;
  esac

  # Open / editor
  case "$cmd" in
    'open '*)
      local target
      target=$(_first_arg "$cmd")
      SUMMARY="will open '${target}' in the default application."
      MATCHED=1; return 0 ;;
    'code '*)
      SUMMARY="will open files in Visual Studio Code."
      MATCHED=1; return 0 ;;
  esac

  # Echo / printf
  case "$cmd" in
    'echo '*)
      SUMMARY="will print text to the terminal (no file changes)."
      MATCHED=1; return 0 ;;
    'printf '*)
      SUMMARY="will print formatted text to the terminal."
      MATCHED=1; return 0 ;;
  esac

  return 0
}

# ─── v1 LLM fallback ────────────────────────────────────────────────────────
_llm_summarize() {
  local cmd="$1"
  local cache_dir="$HOME/.sutra/permission-summary-cache"
  local cache_key cache_file

  # Rate limit: skip if last call <500ms ago
  local last_call_file="$cache_dir/.last-call"
  mkdir -p "$cache_dir" 2>/dev/null
  if [ -f "$last_call_file" ]; then
    local last now delta_ms
    last=$(cat "$last_call_file" 2>/dev/null || echo 0)
    now=$(date +%s)
    delta_ms=$(( (now - last) * 1000 ))
    if [ "$delta_ms" -lt 500 ]; then
      return 1
    fi
  fi

  # Cache key = md5 of command
  cache_key=$(printf '%s' "$cmd" | md5 -q 2>/dev/null || printf '%s' "$cmd" | md5sum 2>/dev/null | awk '{print $1}')
  [ -z "$cache_key" ] && return 1
  cache_file="$cache_dir/$cache_key.txt"

  # Cache hit
  if [ -f "$cache_file" ]; then
    cat "$cache_file"
    return 0
  fi

  # Check LLM availability — prefer `claude` CLI; fall back to generic message
  if ! command -v claude >/dev/null 2>&1; then
    return 1
  fi

  # Update last-call timestamp
  date +%s > "$last_call_file" 2>/dev/null

  # Tight prompt — 1-2 sentences, plain English, flag danger
  local prompt result
  prompt="Summarize this shell command for a non-technical user in 1-2 plain-English sentences. If the command is destructive or high-risk (delete, format, overwrite, admin, network execution), start the summary with '⚠ DESTRUCTIVE —'. Do NOT include the command itself in your output. Just the summary.

Command: ${cmd}

Summary:"

  # Best-effort: 5s timeout, fail silently
  result=$(printf '%s' "$prompt" | timeout 5 claude --print --model claude-haiku-4-5-20251001 2>/dev/null | head -c 400)
  if [ -n "$result" ]; then
    printf '%s' "$result" > "$cache_file" 2>/dev/null
    printf '%s' "$result"
    return 0
  fi
  return 1
}

# ─── Main dispatch ──────────────────────────────────────────────────────────
SUMMARY=""; DANGEROUS=0; MATCHED=0
_rules_match "$CMD_CLEAN"

# If rules didn't match OR command is composed, try LLM fallback
if [ "$MATCHED" = "0" ] || _is_composed "$CMD_CLEAN"; then
  if [ "${SUTRA_PERMISSION_LLM:-1}" != "0" ]; then
    LLM_RESULT=$(_llm_summarize "$CMD_CLEAN" 2>/dev/null || true)
    if [ -n "$LLM_RESULT" ]; then
      SUMMARY="$LLM_RESULT"
      case "$LLM_RESULT" in *'⚠'*|*'DESTRUCTIVE'*|*'destructive'*) DANGEROUS=1 ;; esac
      MATCHED=1
    fi
  fi
  # Final fallback — rules miss + LLM unavailable/disabled
  if [ "$MATCHED" = "0" ]; then
    SUMMARY="This command does something Sutra couldn't auto-summarize. Ask someone technical to review the raw command below before approving."
    MATCHED=1
  fi
fi

# ─── Log to enforcement channel ────────────────────────────────────────────
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}"
if [ -n "$REPO_ROOT" ]; then
  mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null
  VERB=$(printf '%s' "$CMD_CLEAN" | awk '{print $1}')
  SAFE_VERB=$(printf '%s' "$VERB" | tr -d '"\\' | tr '\n\r' '  ' | head -c 50)
  TS=$(date +%s)
  echo "{\"ts\":$TS,\"event\":\"bash-summary\",\"verb\":\"$SAFE_VERB\",\"matched_rule\":$MATCHED,\"dangerous\":$DANGEROUS,\"summary_len\":${#SUMMARY}}" \
    >> "$REPO_ROOT/.enforcement/bash-summary.jsonl" 2>/dev/null
fi

# ─── Emit JSON output (permissionDecisionReason) ───────────────────────────
SAFE_SUMMARY=$(_json_escape "$SUMMARY")
PREFIX="📖 Plain-English:"
[ "$DANGEROUS" = "1" ] && PREFIX="🚨 Plain-English (CAUTION):"

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s %s"}}\n' \
  "$PREFIX" "$SAFE_SUMMARY"

exit 0

# ═══════════════════════════════════════════════════════════════════════════
# ## Operationalization (per PROTO-000)
#
# ### 1. Measurement mechanism
# Per-fire row in .enforcement/bash-summary.jsonl: {ts, verb, matched_rule,
# dangerous, summary_len}. Null handling: zero rows = hook not firing (health
# check) OR no Bash calls that turn (normal).
#
# ### 2. Adoption mechanism
# Registered in sutra/marketplace/plugin/hooks/hooks.json under
# PreToolUse[Bash], sequenced after rtk-auto-rewrite + codex-directive-gate so
# blocked commands never pay the summarization cost. Shipped in plugin v1.4.0;
# every client receives on next plugin auto-update. Also registered in the
# H-Agent Interface charter (Part 4) for cross-surface cascade.
#
# ### 3. Monitoring / escalation
# DRI (Sutra marketplace dept) reviews bash-summary.jsonl weekly.
# Warn: false-destructive rate >5%; LLM timeout rate >10%.
# Breach: user reports incorrect summary in FEEDBACK-LOG → update rules table
# or LLM prompt.
#
# ### 4. Iteration trigger
# Revise rules table when a missed pattern is flagged in FEEDBACK-LOG, or when
# telemetry shows a verb hitting the generic fallback >50×/week.
#
# ### 5. DRI
# Sutra marketplace department. Operator: in-session plugin, self-served.
# Charter steward: c-human-agent-interface (Part 4 registry maintainer).
#
# ### 6. Decommission criteria
# Retire when: Anthropic ships native permission-summary feature (upstream
# pitch); OR adoption <1 fire/day for 30 days across the fleet.
