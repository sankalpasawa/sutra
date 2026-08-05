#!/usr/bin/env bash
# wdp-ledger.sh — WDP W5-T45 per FROZEN LLD-LEDGER-REPORT. Controlled writer
# for the dispatch ledger: EXACTLY ONE printf-append per row, jq-validated,
# rows < 4KB (POSIX atomic-append assumption, local fs, single-user CLI —
# oversize rows REJECTED, never split). This library is the controlled-writer
# seed for W6-T51: when T51 lands, direct writes to the ledger die and every
# writer routes here.
# Callers: sutra-dispatch (decision/bind/escalation), sutra-atom (outcome
# join on close/abandon), dispatch-gate (W6).

WDP_LEDGER_MAX_ROW=4096

_wdp_ledger_path() {
  local root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  printf '%s' "${DISPATCH_LEDGER_OVERRIDE:-$root/.sutra/dispatch-ledger.jsonl}"
}

# dispatch_ledger_append <json-row>
# rc 0 written; rc 2 rejected (invalid/oversize/multi-doc); rc 1 infra.
dispatch_ledger_append() {
  local row="$1" ledger
  [ -n "$row" ] || { echo "wdp-ledger: REJECTED — empty row" >&2; return 2; }
  # One JSON object, exactly one document (jq -s guards trailing docs).
  printf '%s' "$row" | jq -es 'length == 1 and (.[0] | type == "object")' >/dev/null 2>&1 \
    || { echo "wdp-ledger: REJECTED — row is not a single JSON object" >&2; return 2; }
  # BYTE length, not chars — ${#row} miscounts under multibyte locales (codex P1).
  local row_bytes; row_bytes=$(printf '%s' "$row" | LC_ALL=C wc -c | tr -d ' ')
  [ "$row_bytes" -lt "$WDP_LEDGER_MAX_ROW" ] \
    || { echo "wdp-ledger: REJECTED — row ${row_bytes}B >= ${WDP_LEDGER_MAX_ROW}B cap" >&2; return 2; }
  case "$row" in *$'\n'*) echo "wdp-ledger: REJECTED — embedded newline" >&2; return 2 ;; esac
  ledger="$(_wdp_ledger_path)"
  mkdir -p "$(dirname "$ledger")" || return 1
  # THE one write. Append-only; no truncation path exists in this library.
  printf '%s\n' "$row" >> "$ledger" || { echo "wdp-ledger: write failed" >&2; return 1; }
  return 0
}

# dispatch_outcome_append <atom-id> <status> <attempt> <verify-exit>
# Joins an atom close/abandon event to the dispatch ledger. Reads the session
# dispatch marker; no marker or unbound/mismatched atom_id -> rc 0, NO row
# (dogfood-safe: unbound atoms are legal pre-W6). Marker present + matching
# -> outcome row appended via dispatch_ledger_append.
dispatch_outcome_append() {
  local atom_id="$1" status="$2" attempt="${3:-0}" vexit="${4:-}"
  local root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  local sid="${CLAUDE_CODE_SESSION_ID:-nosession}"
  local marker="$root/.sutra/dispatch/$sid/dispatch-record"
  [ -f "$marker" ] || return 0
  local bound unit
  bound=$(grep -E '^ATOM_ID=' "$marker" 2>/dev/null | head -1 | cut -d= -f2-)
  [ "$bound" = "$atom_id" ] || return 0
  unit=$(grep -E '^UNIT=' "$marker" 2>/dev/null | head -1 | cut -d= -f2-)
  dispatch_ledger_append "$(jq -nc --arg a "$atom_id" --arg u "$unit" --arg s "$sid" \
    --arg st "$status" --arg at "$attempt" --arg ve "$vexit" \
    '{v:1, kind:"outcome", atom_id:$a, unit:$u, session_id:$s, result:$st,
      attempt:($at|tonumber? // 0), verify_exit:($ve|tonumber? // null), ts:(now|floor)}')"
}
