#!/usr/bin/env bash
# Sutra Override Audit Helper -- shared writer for governance overrides.
# Spec:    sutra/state/OVERRIDE-SCHEMA.md (v1)
# Schema:  sutra/state/override-schema.json (draft-07)
#
# This is the SOLE serializer for governance-bypass audit records.
# Callers must NOT hand-roll JSON; sanitization + JSON-escape live here.
#
# Public API:
#   accept_override <alias> <gate> <hook> <reason> [original_gate_severity] [mode] [file]
#       -> exit 0 if accepted (audit row written + override applies)
#       -> exit 1 if rejected (caller must enforce gate as if no override)
#
#   mint_token <alias>
#       -> prints a single-use hex token ID, writes marker file under
#          .claude/override-tokens/<id>. Caller passes via "${ALIAS}_TOKEN" env var.
#
# Sourcing:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/override-audit.sh"
#   (when sourced from holding/hooks/cascade-check.sh etc., adjust path accordingly)
#
# Resilience: if the helper sub-shell crashes, the calling gate gets exit !=0
# and re-asserts the deny path. We never silently swallow override failures.

set -u

# ─── Resolve repo root + audit log path ──────────────────────────────────────
_oa_repo_root() {
  printf '%s' "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
}

_oa_audit_log() {
  printf '%s/.enforcement/override-audit.jsonl' "$(_oa_repo_root)"
}

# ─── Reason validation (reject, do not strip — codex review fix 2026-04-18) ──
# Accept printable text. Reject only CR/LF/NUL — these break JSONL line boundaries.
# Quotes, backslashes, punctuation pass through and get JSON-escaped at write.
_oa_reason_valid() {
  local reason="$1"
  [ -z "$reason" ] && return 1
  [ ${#reason} -gt 500 ] && return 1
  # CR/LF detection. NUL is impossible in bash strings (NUL terminates), so any
  # NUL in the operator's input would already have truncated the value at the
  # variable assignment boundary. We only need to reject CR/LF here.
  case "$reason" in
    *$'\r'*|*$'\n'*) return 1 ;;
  esac
  return 0
}

# ─── Nonce + actor + company derivation ──────────────────────────────────────
_oa_nonce() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 6
  elif [ -e /dev/urandom ]; then
    head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n'
  else
    printf '%012x' "$(( RANDOM * RANDOM * RANDOM ))"
  fi
}

_oa_actor() {
  local f="$(_oa_repo_root)/.claude/active-role"
  if [ -f "$f" ]; then
    head -1 "$f" | tr -d '\r\n' || echo unknown
  else
    echo unknown
  fi
}

_oa_company() {
  local root="$(_oa_repo_root)"
  case "$root" in
    */asawa-holding) printf '%s' "holding" ;;
    *) printf '%s' "$(basename "$root")" ;;
  esac
}

# ─── STRICT mode: token mint + consume ───────────────────────────────────────
mint_token() {
  local alias="${1:-_unspecified}"
  local root="$(_oa_repo_root)"
  local dir="$root/.claude/override-tokens"
  mkdir -p "$dir" 2>/dev/null
  local id
  if command -v openssl >/dev/null 2>&1; then
    id="$(openssl rand -hex 8)"
  elif [ -e /dev/urandom ]; then
    id="$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  else
    id="$(printf '%016x' "$(( RANDOM * RANDOM * RANDOM * RANDOM ))")"
  fi
  printf '%s|%s\n' "$alias" "$(date +%s)" > "$dir/$id"
  printf '%s\n' "$id"
}

# Returns 0 if token valid + alias-matched + within TTL; consumes (deletes) it.
# Returns 1 otherwise.
_oa_consume_token() {
  local alias="$1"
  local token="$2"
  local ttl="${3:-60}"
  local root="$(_oa_repo_root)"
  local dir="$root/.claude/override-tokens"
  local f="$dir/$token"

  [ -z "$token" ] && return 1
  [ ! -f "$f" ] && return 1

  # Format: "<alias>|<ts>"
  local content
  content="$(head -1 "$f" 2>/dev/null)"
  local stored_alias="${content%|*}"
  local stored_ts="${content##*|}"

  [ "$stored_alias" != "$alias" ] && { rm -f "$f"; return 1; }

  # Expiry check
  local now
  now="$(date +%s)"
  if [ -n "$stored_ts" ] && [ "$stored_ts" -gt 0 ] 2>/dev/null; then
    if [ $(( now - stored_ts )) -gt "$ttl" ]; then
      rm -f "$f"
      return 1
    fi
  fi

  rm -f "$f"
  return 0
}

# ─── Public: accept_override ─────────────────────────────────────────────────
# Args: alias gate hook reason [original_gate_severity=2] [mode=legacy] [file=]
accept_override() {
  local alias="${1:-}"
  local gate="${2:-}"
  local hook="${3:-}"
  local reason="${4:-}"
  local original_gate_severity="${5:-2}"
  local mode="${6:-legacy}"
  local file="${7:-}"
  local valid_for_seconds="${OVERRIDE_TTL:-60}"

  # 1. Required fields
  if [ -z "$alias" ] || [ -z "$gate" ] || [ -z "$hook" ]; then
    return 1
  fi

  # 2. Reason validation
  if ! _oa_reason_valid "$reason"; then
    return 1
  fi

  # 3. STRICT mode: validate single-use token
  if [ "$mode" = "strict" ]; then
    local token_var="${alias}_TOKEN"
    local token="${!token_var:-}"
    if ! _oa_consume_token "$alias" "$token" "$valid_for_seconds"; then
      return 1
    fi
  elif [ "$mode" != "legacy" ]; then
    return 1
  fi

  # 4. Build + write audit row
  local nonce ts actor company audit_log
  nonce="$(_oa_nonce)"
  ts="$(date +%s)"
  actor="$(_oa_actor)"
  company="$(_oa_company)"
  audit_log="$(_oa_audit_log)"

  mkdir -p "$(dirname "$audit_log")" 2>/dev/null

  if command -v jq >/dev/null 2>&1; then
    jq -cn \
      --arg alias "$alias" \
      --arg gate "$gate" \
      --arg hook "$hook" \
      --arg reason "$reason" \
      --arg actor "$actor" \
      --arg company "$company" \
      --arg file "$file" \
      --arg mode "$mode" \
      --arg nonce "$nonce" \
      --argjson ts "$ts" \
      --argjson schema_version 1 \
      --argjson severity "$original_gate_severity" \
      --argjson ttl "$valid_for_seconds" \
      '{
        schema_version: $schema_version,
        ts: $ts,
        override_kind: "governance_bypass",
        mode: $mode,
        alias: $alias,
        gate: $gate,
        hook: $hook,
        decision: "allow",
        original_gate_severity: $severity,
        reason: $reason,
        actor: $actor,
        company: $company,
        file: (if $file == "" then null else $file end),
        nonce: $nonce,
        valid_for_seconds: $ttl
      }' >> "$audit_log"
  else
    # Zero-jq fallback. Minimal JSON escape: reason already passed input-validate
    # (no CR/LF/NUL). We escape \ and " manually.
    local r="$reason"
    r="${r//\\/\\\\}"
    r="${r//\"/\\\"}"
    local f_field
    if [ -z "$file" ]; then
      f_field="null"
    else
      local fe="$file"
      fe="${fe//\\/\\\\}"
      fe="${fe//\"/\\\"}"
      f_field="\"$fe\""
    fi
    printf '{"schema_version":1,"ts":%s,"override_kind":"governance_bypass","mode":"%s","alias":"%s","gate":"%s","hook":"%s","decision":"allow","original_gate_severity":%s,"reason":"%s","actor":"%s","company":"%s","file":%s,"nonce":"%s","valid_for_seconds":%s}\n' \
      "$ts" "$mode" "$alias" "$gate" "$hook" "$original_gate_severity" "$r" "$actor" "$company" "$f_field" "$nonce" "$valid_for_seconds" \
      >> "$audit_log"
  fi

  return 0
}

# When invoked as a script (not sourced): expose mint_token + accept_override
# via subcommand. Used by tests + manual invocation.
if [ "${BASH_SOURCE[0]}" = "${0}" ] || [ -z "${BASH_SOURCE[0]:-}" ]; then
  cmd="${1:-}"
  shift 2>/dev/null || true
  case "$cmd" in
    mint)        mint_token "$@" ;;
    accept)      accept_override "$@" ;;
    *)
      echo "usage: $0 mint <alias>"
      echo "       $0 accept <alias> <gate> <hook> <reason> [severity] [mode] [file]"
      exit 2
      ;;
  esac
fi
