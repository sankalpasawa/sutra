#!/bin/bash
# sutra/marketplace/plugin/lib/privacy-sanitize.sh
# Sutra Privacy v2.0 — signals-not-content derivation + secondary scrub + write-layer gate
#
# Design (per codex DIRECTIVE-ID 1777036275 CHANGES-REQUIRED absorbed):
#   - derive_signal()  : PRIMARY defense — allowlist-only, metadata-derived signal
#   - scrub_text()     : SECONDARY guardrail — regex strip (paths, secrets, tokens)
#   - privacy_gate()   : honors SUTRA_TELEMETRY=0 opt-out + SUTRA_FEEDBACK_CONSENT state
#   - signal_write()   : routes signal to disk (consent) or in-memory (no consent) or skip (opt-out)
#   - sutra_safe_write : atomic temp+rename, 0600 perms, symlink-refusal, fail-closed
#   - sutra_safe_append: flock-guarded (where available), 0600 perms, symlink-refusal

set -u

SUTRA_HOME="${SUTRA_HOME:-$HOME/.sutra}"
SUTRA_FEEDBACK_AUTO="${SUTRA_FEEDBACK_AUTO:-$SUTRA_HOME/feedback/auto}"
SUTRA_FEEDBACK_MANUAL="${SUTRA_FEEDBACK_MANUAL:-$SUTRA_HOME/feedback/manual}"
SUTRA_CONSENT_FILE="${SUTRA_CONSENT_FILE:-$SUTRA_HOME/consent}"
SUTRA_MEM_COUNTER="${SUTRA_MEM_COUNTER:-/tmp/sutra-mem-$(id -u 2>/dev/null || echo 0)}"

privacy_gate() {
  if [ "${SUTRA_TELEMETRY:-1}" = "0" ]; then return 2; fi
  if [ "${SUTRA_LEGACY_TELEMETRY:-0}" = "1" ]; then return 2; fi
  local consent="${SUTRA_FEEDBACK_CONSENT:-}"
  if [ -z "$consent" ] && [ -f "$SUTRA_CONSENT_FILE" ]; then
    consent=$(head -1 "$SUTRA_CONSENT_FILE" 2>/dev/null | tr -d '[:space:]')
  fi
  if [ "$consent" = "granted" ]; then return 0; fi
  return 1
}

derive_signal() {
  local category="${1:-}"
  local subcategory="${2:-}"
  local delta="${3:-1}"
  case "$category" in
    override|hook_block|tool_fail|abandonment|correction) ;;
    *) echo "derive_signal: rejected category '$category'" >&2; return 1 ;;
  esac
  if ! printf '%s' "$subcategory" | grep -qE '^[a-zA-Z0-9_-]+$'; then
    echo "derive_signal: rejected subcategory (non-alphanumeric)" >&2
    return 1
  fi
  if ! printf '%s' "$delta" | grep -qE '^-?[0-9]+$'; then
    echo "derive_signal: rejected delta (non-integer)" >&2
    return 1
  fi
  local day
  day=$(date -u +%Y-%m-%d)
  printf '{"day":"%s","category":"%s","sub":"%s","delta":%d}\n' "$day" "$category" "$subcategory" "$delta"
}

scrub_text() {
  local text="${1:-}"
  [ -z "$text" ] && return 0
  text=$(printf '%s' "$text" | sed -E 's|/Users/[^/[:space:]]+|<HOME>|g; s|/home/[^/[:space:]]+|<HOME>|g; s|/tmp/[a-zA-Z0-9._-]+|<TMP>|g')
  text=$(printf '%s' "$text" | sed -E 's|-----BEGIN OPENSSH PRIVATE KEY-----|<SSH-KEY>|g; s|-----BEGIN [A-Z ]+-----|<PEM-BEGIN>|g; s|-----END [A-Z ]+-----|<PEM-END>|g')
  text=$(printf '%s' "$text" | sed -E 's|eyJ[a-zA-Z0-9_=-]{10,}\.[a-zA-Z0-9_=-]{10,}\.[a-zA-Z0-9_=-]{10,}|<JWT>|g')
  text=$(printf '%s' "$text" | sed -E 's|[Bb]earer [a-zA-Z0-9._-]{16,}|Bearer <REDACTED>|g')
  text=$(printf '%s' "$text" | sed -E 's|[A-Z_]{3,}=[a-zA-Z0-9+/=_-]{16,}|<KEY=REDACTED>|g')
  text=$(printf '%s' "$text" | sed -E 's|https://[^:/[:space:]]+:[^@[:space:]]+@|https://<CREDS>@|g')
  text=$(printf '%s' "$text" | sed -E 's#(postgres|postgresql|mysql|mongodb\+srv|mongodb|redis|amqp|amqps)://[^[:space:]"]+#<DB-URI>#g')
  text=$(printf '%s' "$text" | sed -E 's|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}|<EMAIL>|g')
  printf '%s' "$text"
}

sutra_safe_write() {
  local target="${1:?sutra_safe_write: target required}"
  local content="${2:-}"
  if [ -L "$target" ]; then echo "sutra_safe_write: refusing symlink target $target" >&2; return 1; fi
  local parent; parent=$(dirname "$target")
  if [ -L "$parent" ]; then echo "sutra_safe_write: refusing symlinked parent $parent" >&2; return 1; fi
  if ! mkdir -p "$parent" 2>/dev/null; then echo "sutra_safe_write: cannot create parent $parent" >&2; return 1; fi
  chmod 0700 "$parent" 2>/dev/null
  local tmp="$target.tmp.$$"
  (umask 0077; printf '%s' "$content" > "$tmp") 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
  chmod 0600 "$tmp" 2>/dev/null
  mv -f "$tmp" "$target" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
  return 0
}

sutra_safe_append() {
  local target="${1:?sutra_safe_append: target required}"
  local line="${2:-}"
  if [ -L "$target" ]; then echo "sutra_safe_append: refusing symlink target" >&2; return 1; fi
  local parent; parent=$(dirname "$target")
  if [ -L "$parent" ]; then echo "sutra_safe_append: refusing symlinked parent" >&2; return 1; fi
  mkdir -p "$parent" 2>/dev/null
  chmod 0700 "$parent" 2>/dev/null
  (umask 0077
    if command -v flock >/dev/null 2>&1; then
      (
        flock -x 200
        printf '%s\n' "$line" >> "$target"
        chmod 0600 "$target" 2>/dev/null
      ) 200>"$target.lock"
      rm -f "$target.lock" 2>/dev/null
    else
      printf '%s\n' "$line" >> "$target"
      chmod 0600 "$target" 2>/dev/null
    fi
  )
  return 0
}

signal_write() {
  privacy_gate
  local gate=$?
  case "$gate" in
    2) return 0 ;;
    1)
      local line
      line=$(derive_signal "$@") || return 0
      mkdir -p "$(dirname "$SUTRA_MEM_COUNTER")" 2>/dev/null
      (umask 0077; printf '%s\n' "$line" >> "$SUTRA_MEM_COUNTER" 2>/dev/null)
      chmod 0600 "$SUTRA_MEM_COUNTER" 2>/dev/null
      return 0
      ;;
    0)
      local line
      line=$(derive_signal "$@") || return 0
      local day_file="$SUTRA_FEEDBACK_AUTO/$(date -u +%Y-%m-%d).jsonl"
      sutra_safe_append "$day_file" "$line" || return 0
      return 0
      ;;
  esac
}

sutra_grant_consent() {
  mkdir -p "$SUTRA_HOME" 2>/dev/null
  chmod 0700 "$SUTRA_HOME" 2>/dev/null
  (umask 0077
    printf 'granted\n' > "$SUTRA_CONSENT_FILE.tmp.$$"
    chmod 0600 "$SUTRA_CONSENT_FILE.tmp.$$" 2>/dev/null
    mv -f "$SUTRA_CONSENT_FILE.tmp.$$" "$SUTRA_CONSENT_FILE"
  )
}

sutra_retention_cleanup() {
  local days="${1:-${SUTRA_RETENTION_DAYS:-30}}"
  [ -d "$SUTRA_FEEDBACK_AUTO" ] || return 0
  find "$SUTRA_FEEDBACK_AUTO" -type f -name '*.jsonl' -mtime +"$days" -delete 2>/dev/null
  local marker="$SUTRA_HOME/retention-last-run"
  (umask 0077; date -u +%Y-%m-%dT%H:%M:%SZ > "$marker" 2>/dev/null)
  chmod 0600 "$marker" 2>/dev/null
}
