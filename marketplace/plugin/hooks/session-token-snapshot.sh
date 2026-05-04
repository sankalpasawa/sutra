#!/usr/bin/env bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/hooks/session-token-snapshot.sh
# TS=2026-05-04
# Sutra OS — Session Token Snapshot (SessionStart event)
# Captures boot context size per company and appends one `boot` record to
# holding/TOKEN-TELEMETRY-LOG.jsonl (Asawa) or .sutra/token-telemetry.jsonl
# (T2/T3/T4 fleet). Wires Tokens charter cost-component #1 ("boot tokens")
# into Layer A telemetry.
#
# Promoted L1->L0 in D38 Wave D 2026-05-04 per codex consult 1777875522
# (PASS on 3-promote framing). Promotion-from: holding/hooks/session-token-
# snapshot.sh (founder approval charter KR4 2026-04-23).
#
# Charter:  sutra/os/charters/TOKENS.md (§3 Drivers, §7 Telemetry)
# Contract: holding/departments/analytics/TELEMETRY-CONTRACT.md §7
# Schema:   holding/departments/analytics/token-telemetry.schema.json (v1)
#
# Emits ONE JSONL record of event type `boot` with:
#   - tokens_boot        = byte_sum / 4 proxy (proxy=true)
#   - files_loaded       = list of relative paths that exist
#   - files_sizes_bytes  = map of path -> byte count
#   - company            = derived from CWD (env override available)
#   - session_id         = from SessionStart JSON stdin or env fallback
#
# Behavior:
#   - Bash, set -euo pipefail
#   - Reads SessionStart JSON from stdin if present; otherwise no-op fallback
#     (still writes a record with a synthesized session_id)
#   - Graceful: any failure -> silent exit 0 (SessionStart must never block)
#
# Env overrides (tests + fleet customization):
#   TOKEN_TELEMETRY_LOG     - override log destination
#   CLAUDE_PROJECT_DIR      - repo root (test isolation)
#   TOKEN_SNAPSHOT_COMPANY  - force company value (bypass CWD detection;
#                             T4 fleet should set this in their settings.json)
# ---------------------------------------------------------------------------

set -euo pipefail

# Wrap everything so any unexpected error ends in exit 0 (never block session).
main() {
  local REPO_ROOT LOG_FILE COMPANY TS SESSION_ID
  local STDIN_PAYLOAD=""
  local files_loaded_json="[]"
  local files_sizes_json="{}"
  local total_bytes=0
  local tokens_boot=0
  local proxy="true"

  REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

  # Default log destination: holding/TOKEN-TELEMETRY-LOG.jsonl when running
  # in asawa-holding; .sutra/token-telemetry.jsonl elsewhere (fleet-safe).
  if [ -n "${TOKEN_TELEMETRY_LOG:-}" ]; then
    LOG_FILE="$TOKEN_TELEMETRY_LOG"
  elif [ -d "$REPO_ROOT/holding" ]; then
    LOG_FILE="$REPO_ROOT/holding/TOKEN-TELEMETRY-LOG.jsonl"
  else
    LOG_FILE="$REPO_ROOT/.sutra/token-telemetry.jsonl"
  fi

  # --- 1. Company detection -------------------------------------------------
  # Precedence: explicit env > submodule path segment > known portfolio name >
  # repo directory basename (fleet-safe fallback for any T4 user).
  if [ -n "${TOKEN_SNAPSHOT_COMPANY:-}" ]; then
    COMPANY="$TOKEN_SNAPSHOT_COMPANY"
  else
    local base
    base="$(basename "$REPO_ROOT" 2>/dev/null || echo "")"
    case "$base" in
      asawa-holding|holding|"") COMPANY="asawa" ;;
      sutra|dayflow|maze|ppr|billu|paisa) COMPANY="$base" ;;
      *)
        # Fleet-safe fallback: walk CWD segments looking for known portfolio
        # company; otherwise USE the directory basename verbatim (T4 clients
        # get their actual repo name as the company tag, not "asawa").
        case ":$REPO_ROOT:" in
          *":sutra:"*|*"/sutra/"*|*"/sutra") COMPANY="sutra" ;;
          *"/dayflow"*) COMPANY="dayflow" ;;
          *"/maze"*) COMPANY="maze" ;;
          *"/ppr"*) COMPANY="ppr" ;;
          *"/billu"*) COMPANY="billu" ;;
          *"/paisa"*) COMPANY="paisa" ;;
          *) COMPANY="$base" ;;
        esac
        ;;
    esac
  fi

  # --- 2. SessionStart stdin (optional) -------------------------------------
  # Claude Code passes a JSON payload with session_id + transcript_path.
  # We only need session_id; everything else is fallback.
  if [ ! -t 0 ]; then
    STDIN_PAYLOAD="$(cat 2>/dev/null || true)"
  fi

  SESSION_ID=""
  if [ -n "$STDIN_PAYLOAD" ]; then
    if command -v jq >/dev/null 2>&1; then
      SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null || true)
    fi
    if [ -z "$SESSION_ID" ]; then
      SESSION_ID=$(printf '%s' "$STDIN_PAYLOAD" | \
        sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)
    fi
  fi
  if [ -z "$SESSION_ID" ]; then
    SESSION_ID="${CLAUDE_SESSION_ID:-auto-$(date +%s)-$$}"
  fi

  # --- 3. Boot-context byte accounting --------------------------------------
  # Cost component #1 per CLAUDE.md Tokens Snapshot:
  #   CLAUDE.md + MEMORY.md + enabled plugin skill descriptions.
  # We measure BYTES (deterministic, cheap) and derive tokens via /4 proxy.
  local candidates=(
    "$REPO_ROOT/CLAUDE.md"
    "$REPO_ROOT/.claude/CLAUDE.md"
    "$REPO_ROOT/.claude/MEMORY.md"
    "$HOME/.claude/CLAUDE.md"
    "$HOME/.claude/MEMORY.md"
  )

  # Project-scoped auto-memory (Claude Code layout)
  local proj_key
  proj_key="$(printf '%s' "$REPO_ROOT" | sed 's|/|-|g')"
  if [ -n "$proj_key" ]; then
    local proj_mem="$HOME/.claude/projects/${proj_key}/memory/MEMORY.md"
    # Some installs drop the leading '-' when the path starts with /
    local proj_mem_alt="$HOME/.claude/projects/-${proj_key#-}/memory/MEMORY.md"
    candidates+=("$proj_mem" "$proj_mem_alt")
  fi

  # Enabled-plugin skill descriptions: walk ~/.claude/plugins/cache/*/skills/*/SKILL.md
  # (best-effort; non-fatal if directory absent). Bounded to 500 files to keep
  # SessionStart cost trivial.
  local plugin_skill_files=()
  if [ -d "$HOME/.claude/plugins/cache" ]; then
    # shellcheck disable=SC2207
    plugin_skill_files=( $(find "$HOME/.claude/plugins/cache" -maxdepth 5 -type f -name 'SKILL.md' 2>/dev/null | head -500) )
  fi

  # Assemble JSON for files_loaded + files_sizes_bytes as we go.
  local first_loaded=1 first_size=1
  local loaded_buf="" sizes_buf=""

  append_file() {
    local path="$1"
    if [ ! -r "$path" ]; then
      return 0
    fi
    local size rel
    size=$(wc -c < "$path" 2>/dev/null | tr -d ' ' || echo 0)
    if [ -z "$size" ] || [ "$size" -le 0 ] 2>/dev/null; then
      return 0
    fi
    total_bytes=$(( total_bytes + size ))
    # Relative when under repo, else keep absolute (Layer A is local-only).
    rel="${path#$REPO_ROOT/}"
    local rel_esc
    rel_esc=$(printf '%s' "$rel" | sed 's/\\/\\\\/g; s/"/\\"/g')
    if [ $first_loaded -eq 1 ]; then
      loaded_buf="\"$rel_esc\""
      first_loaded=0
    else
      loaded_buf="$loaded_buf,\"$rel_esc\""
    fi
    if [ $first_size -eq 1 ]; then
      sizes_buf="\"$rel_esc\":$size"
      first_size=0
    else
      sizes_buf="$sizes_buf,\"$rel_esc\":$size"
    fi
  }

  local f
  for f in "${candidates[@]}"; do
    append_file "$f"
  done
  for f in "${plugin_skill_files[@]}"; do
    append_file "$f"
  done

  files_loaded_json="[$loaded_buf]"
  files_sizes_json="{$sizes_buf}"

  # Bytes -> tokens via /4 heuristic (charter §3: "file_bytes / 4").
  if [ "$total_bytes" -gt 0 ] 2>/dev/null; then
    tokens_boot=$(( total_bytes / 4 ))
  else
    tokens_boot=0
  fi

  # --- 4. Emit JSONL record -------------------------------------------------
  TS=$(date +%s)
  local session_esc company_esc
  session_esc=$(printf '%s' "$SESSION_ID" | sed 's/\\/\\\\/g; s/"/\\"/g')
  company_esc=$(printf '%s' "$COMPANY"    | sed 's/\\/\\\\/g; s/"/\\"/g')

  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

  # Matches schema v1: schema_version, ts, event=boot, session_id, company,
  # task_id=null, depth=null, arm=n/a, tokens_boot, files_loaded,
  # files_sizes_bytes, path_origin=SessionStart-hook, proxy=true,
  # compaction_count=0.
  printf '{"schema_version":1,"ts":%s,"event":"boot","session_id":"%s","company":"%s","task_id":null,"depth":null,"arm":"n/a","tokens_boot":%s,"files_loaded":%s,"files_sizes_bytes":%s,"path_origin":"SessionStart-hook","proxy":%s,"compaction_count":0}\n' \
    "$TS" "$session_esc" "$company_esc" "$tokens_boot" \
    "$files_loaded_json" "$files_sizes_json" "$proxy" \
    >> "$LOG_FILE"

  return 0
}

# Hard guarantee: never bubble a failure up to SessionStart.
main 2>/dev/null || true
exit 0
