#!/usr/bin/env bash
# dispatch-gate.sh — WDP W6-T50 per FROZEN LLD-DISPATCH-GATE (+ marker-path
# amendment 2026-08-04: .sutra/dispatch/<sid>/dispatch-record, because Bash
# writes to .claude/ roll back). HARD, every unit: mutation targets must be
# covered by the FROZEN marker envelope — never atom.json's live touches
# (post-bind widening changes nothing, G3 deepseek fold).
#
# Contract with the dispatcher: source this file, call dispatch_gate_check
# with tool name + targets; it sets DISPATCH_GATE_VERDICT=ALLOW|BLOCK and
# DISPATCH_GATE_REASON. Dispatcher converts BLOCK to exit 2. This script
# never exits the caller (defensive-source pattern like marker-lib).
#
# Fail-open ONLY on missing tooling (jq/matcher unavailable — cannot evaluate
# at all). Everything about the MARKER is fail-closed: absent, unreadable,
# unbound, malformed, session-drift all BLOCK — dual consult converged (codex +
# deepseek, 2026-08-04): read-error fail-open is attacker-controllable state
# (chmod 000 the marker would bypass the envelope entirely).
# Kill-switch: ~/.dispatch-gate-disabled (founder revoke only).
# Verdicts journal to .enforcement/dispatch-gate.jsonl via controlled writer.

_DG_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
_DG_REPO="$(git rev-parse --show-toplevel 2>/dev/null || echo "$_DG_ROOT")"
_DG_SID="${CLAUDE_CODE_SESSION_ID:-nosession}"
_DG_MARKER="$_DG_ROOT/.sutra/dispatch/$_DG_SID/dispatch-record"
_DG_JOURNAL="${DISPATCH_GATE_JOURNAL_OVERRIDE:-$_DG_ROOT/.enforcement/dispatch-gate.jsonl}"

# Shared matcher — ONE implementation with the fixtures (risk #10).
_DG_SP="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/hooks/lib/sutra-paths.sh}"
[ -n "$_DG_SP" ] && [ -f "$_DG_SP" ] || _DG_SP="$_DG_REPO/holding/hooks/lib/sutra-paths.sh"
. "$_DG_SP" 2>/dev/null || true
. "${SUTRA_LIB:-$_DG_REPO/holding/hooks/lib}/touches-match.sh" 2>/dev/null || true
# Controlled writer for the journal (optional; direct append fallback keeps
# the gate functional if the lib is absent — journaling never blocks work).
. "${SUTRA_LIB:-$_DG_REPO/holding/hooks/lib}/wdp-ledger.sh" 2>/dev/null || true

_dg_journal() { # $1=verdict $2=reason $3=tool $4=target
  local row
  row=$(jq -nc --arg v "$1" --arg r "$2" --arg t "$3" --arg p "$4" --arg s "$_DG_SID" \
    '{v:1, kind:"gate", verdict:$v, reason:$r, tool:$t, target:$p, session_id:$s, ts:(now|floor)}' 2>/dev/null) || return 0
  mkdir -p "$(dirname "$_DG_JOURNAL")" 2>/dev/null || return 0
  printf '%s\n' "$row" >> "$_DG_JOURNAL" 2>/dev/null || true
}

# dispatch_gate_check <tool> <target>...
#   tool: Edit | Write | Bash | Agent
#   targets: repo-relative or absolute mutation targets (Bash: every target
#            the floor's scanner identified; Agent: "model=..." kv probes).
# Sets DISPATCH_GATE_VERDICT + DISPATCH_GATE_REASON. Never exits.
dispatch_gate_check() {
  DISPATCH_GATE_VERDICT="ALLOW"; DISPATCH_GATE_REASON=""
  local tool="${1:-}"; shift || true

  # Kill-switch (founder revoke only)
  [ -f "$HOME/.dispatch-gate-disabled" ] && { DISPATCH_GATE_REASON="kill-switch"; return 0; }

  # Cheapest early exits first (p50: read-only ops + no targets)
  [ $# -ge 1 ] || { DISPATCH_GATE_REASON="no-targets"; return 0; }    # M6: nothing to gate
  command -v jq >/dev/null 2>&1 || { DISPATCH_GATE_REASON="fail-open:no-jq"; _dg_journal ALLOW "fail-open:no-jq" "$tool" "-"; return 0; }
  command -v touches_match >/dev/null 2>&1 || { DISPATCH_GATE_REASON="fail-open:no-matcher"; _dg_journal ALLOW "fail-open:no-matcher" "$tool" "-"; return 0; }

  # Marker state: ABSENT = policy BLOCK; PRESENT-BUT-UNREADABLE = infra fail-open.
  if [ ! -e "$_DG_MARKER" ]; then
    DISPATCH_GATE_VERDICT="BLOCK"
    DISPATCH_GATE_REASON="no dispatch record — run: sutra-dispatch resolve ... && sutra-atom open ... && sutra-dispatch bind"
    _dg_journal BLOCK "marker-absent" "$tool" "${1:-}"
    return 0
  fi
  local mk
  if ! mk=$(cat "$_DG_MARKER" 2>/dev/null) || [ -z "$mk" ]; then
    DISPATCH_GATE_VERDICT="BLOCK"
    DISPATCH_GATE_REASON="dispatch record exists but is unreadable/empty — fail-closed (G5-consult); restore it: sutra-dispatch resolve + bind"
    _dg_journal BLOCK "marker-unreadable" "$tool" "${1:-}"
    return 0
  fi

  local atom_id session envelope
  atom_id=$(printf '%s\n' "$mk" | grep -m1 '^ATOM_ID=' | cut -d= -f2-)
  session=$(printf '%s\n' "$mk" | grep -m1 '^SESSION=' | cut -d= -f2-)
  envelope=$(printf '%s\n' "$mk" | grep -m1 '^TOUCHES=' | cut -d= -f2-)

  if [ -z "$atom_id" ]; then
    DISPATCH_GATE_VERDICT="BLOCK"
    DISPATCH_GATE_REASON="dispatch record not BOUND to an atom — run: sutra-dispatch bind --atom-id <id>"
    _dg_journal BLOCK "marker-unbound" "$tool" "${1:-}"
    return 0
  fi
  if [ "$session" != "$_DG_SID" ]; then
    DISPATCH_GATE_VERDICT="BLOCK"
    DISPATCH_GATE_REASON="dispatch record session '$session' != current '$_DG_SID'"
    _dg_journal BLOCK "session-mismatch" "$tool" "${1:-}"
    return 0
  fi
  # Bound atom must exist AND be open (bind checked open; close/abandon ends authority).
  local af="$_DG_ROOT/.sutra/atoms/$_DG_SID/$atom_id/atom.json"
  local astat
  astat=$(jq -r .status "$af" 2>/dev/null) || astat=""
  if [ "$astat" != "open" ]; then
    DISPATCH_GATE_VERDICT="BLOCK"
    DISPATCH_GATE_REASON="bound atom $atom_id is not open (status: ${astat:-missing})"
    _dg_journal BLOCK "atom-not-open" "$tool" "${1:-}"
    return 0
  fi

  # Agent tool: params must match the frozen routing (weak-binding fold, G2).
  if [ "$tool" = "Agent" ]; then
    local mmodel probe k vv
    mmodel=$(printf '%s\n' "$mk" | grep -m1 '^MODEL=' | cut -d= -f2-)
    for probe in "$@"; do
      case "$probe" in
        model=*) vv="${probe#model=}"
          if [ -n "$vv" ] && [ "$vv" != "$mmodel" ]; then
            DISPATCH_GATE_VERDICT="BLOCK"
            DISPATCH_GATE_REASON="Agent model '$vv' != dispatched '$mmodel' — escalate via sutra-dispatch, not ad-hoc"
            _dg_journal BLOCK "agent-model-drift" "$tool" "$probe"
            return 0
          fi ;;
      esac
    done
    _dg_journal ALLOW "agent-params-match" "$tool" "-"
    return 0
  fi

  # Edit/Write/Bash: EVERY target covered by the FROZEN envelope (pipe-joined).
  local -a env_entries=()
  local IFS='|'
  read -r -a env_entries <<< "$envelope"
  unset IFS
  local t verdict
  for t in "$@"; do
    # Opaque-mutation sentinel (G6): the dispatcher could not NAME a target, so
    # there is nothing to match against the envelope. Every marker check above
    # has already run — a bound, session-matching, open-atom record is exactly
    # the authority we can demand here. Requiring coverage too would block
    # legitimate `git reset`/installer work inside a properly bound unit.
    [ "$t" = "::opaque-mutation::" ] && continue
    verdict=$(TOUCHES_MATCH_ROOT="$_DG_ROOT" touches_match "$t" 1 ${env_entries[@]+"${env_entries[@]}"})
    if [ "$verdict" != "ALLOW" ]; then
      DISPATCH_GATE_VERDICT="BLOCK"
      DISPATCH_GATE_REASON="target '$t' outside frozen dispatch envelope [$envelope] (atom $atom_id)"
      _dg_journal BLOCK "envelope-miss" "$tool" "$t"
      return 0
    fi
  done
  _dg_journal ALLOW "covered" "$tool" "$*"
  return 0
}
