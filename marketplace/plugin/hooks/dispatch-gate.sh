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

# Libraries — ONE matcher implementation with the fixtures (risk #10). The
# plugin's own hooks/lib wins: it is immutable relative to the repo being
# gated. Repo-local holding/hooks/lib is a fallback for the holding checkout
# only (codex P2 2026-09-10: repository contents must never override the
# libraries that decide enforcement).
_DG_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/lib"
[ -f "$_DG_LIB/touches-match.sh" ] || _DG_LIB="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/hooks/lib}"
{ [ -n "$_DG_LIB" ] && [ -f "$_DG_LIB/touches-match.sh" ]; } || _DG_LIB="${SUTRA_LIB:-$_DG_REPO/holding/hooks/lib}"
. "$_DG_LIB/sutra-paths.sh" 2>/dev/null || true
. "$_DG_LIB/touches-match.sh" 2>/dev/null || true
# Controlled writer for the journal (optional; direct append fallback keeps
# the gate functional if the lib is absent — journaling never blocks work).
. "$_DG_LIB/wdp-ledger.sh" 2>/dev/null || true
# Workflow-run evidence (transcript-derived; G5=A workflow floor).
. "$_DG_LIB/wf-evidence.sh" 2>/dev/null || true

_dg_journal() { # $1=verdict $2=reason $3=tool $4=target
  local row
  row=$(jq -nc --arg v "$1" --arg r "$2" --arg t "$3" --arg p "$4" --arg s "$_DG_SID" \
    '{v:1, kind:"gate", verdict:$v, reason:$r, tool:$t, target:$p, session_id:$s, ts:(now|floor)}' 2>/dev/null) || return 0
  mkdir -p "$(dirname "$_DG_JOURNAL")" 2>/dev/null || return 0
  printf '%s\n' "$row" >> "$_DG_JOURNAL" 2>/dev/null || true
}

# _dg_model_alias <policy-model-id> -> the Agent tool's alias for it, or EMPTY
# when the id is unknown. Callers MUST treat empty as BLOCK, never as "skip the
# check": a fallback that silently allows would invert this file's fail-closed
# posture, which blocks on every other malformed-authority state (absent marker,
# unreadable marker, unbound marker, session mismatch, non-open atom, malformed
# WORKROOT). An unknown MODEL= in the frozen record is malformed authority too.
#
# HARDCODED ON PURPOSE. The obvious design reads an agent_alias field out of
# routing-policy.json, but that file is itself a mutation TARGET inside ordinary
# dispatch envelopes, i.e. model-writable: sourcing the comparison operand from
# it would let a unit widen its own model authority by editing one line. The
# frozen record supplies one operand; this table — which changes only when the
# gate itself is edited — supplies the other. (codex consult 2026-09-08, P2.)
#
# The namespace mismatch this closes: the Agent tool's `model` parameter takes
# {fable,opus,sonnet,haiku}; the policy catalog uses full ids. Before this, the
# comparison put those two namespaces against each other directly, so EVERY
# pinned Agent call BLOCKed and only an UNPINNED one passed — the gate punished
# the correct behavior and rewarded inheriting the session model. Evidence: all
# three Agent rows ever journaled to .enforcement/dispatch-gate.jsonl —
# model=claude-haiku-4-5 BLOCK, model=opus BLOCK, probe="-" ALLOW.
_dg_model_alias() {
  case "${1:-}" in
    claude-fable-5)   echo "fable" ;;
    claude-opus-5)    echo "opus" ;;
    claude-sonnet-5)  echo "sonnet" ;;
    claude-haiku-4-5) echo "haiku" ;;
    *)                echo "" ;;
  esac
}

# _dg_codex_model <raw-command> -> echoes the pinned model, or one of the
# sentinels __RESUME__ / __PARSE_FAIL__ / __NOT_CODEX__, or empty for "no pin".
# argv-tokenized on purpose (codex P2, 2026-08-28): shell `case` on a command
# string false-BLOCKs on heredocs, comments and scrubber pipelines, and
# false-ALLOWs through quoting. Handles all four spellings codex confirmed
# against codex-cli 0.139.0: -m X, -mX, --model X, --model=X.
_dg_codex_model() {
  command -v python3 >/dev/null 2>&1 || { printf '__PARSE_FAIL__'; return 0; }
  python3 - "$1" 2>/dev/null <<'_PYEOF'
import shlex, sys, os
try:
    a = shlex.split(sys.argv[1])
except ValueError:
    print("__PARSE_FAIL__"); raise SystemExit
idx = [i for i, t in enumerate(a) if os.path.basename(t) == "codex"]
if not idx:
    print("__NOT_CODEX__"); raise SystemExit
rest = a[idx[0] + 1:]
if rest[:2] == ["exec", "resume"]:
    print("__RESUME__"); raise SystemExit
model = ""
j = 0
while j < len(rest):
    t = rest[j]
    if t in ("-m", "--model"):
        if j + 1 < len(rest):
            model = rest[j + 1]; j += 2; continue
    elif t.startswith("--model="):
        model = t[len("--model="):]
    elif t.startswith("-m") and len(t) > 2:
        model = t[2:]
    j += 1
print(model)
_PYEOF
}

# Governance-CLI exemption (the recovery trap, 2026-08-28).
# atom-floor.sh exempts sutra-atom / sutra-dispatch / sutra-marker by name
# (_af_exempt_re, line 98) but this gate exempted nothing, so an UNBOUND or
# ABANDONED record blocked the very CLIs whose job is to re-bind it: the gate's
# own remediation text ("re-resolve + open + bind") was unreachable and only a
# founder kill-switch could recover the session. Observed twice in one session.
#
# The exemption is applied in dispatcher-pretool.sh, NOT here, because that is
# where the raw command is available — this gate receives target PATHS, never a
# command line, so it cannot tell a sutra-atom call from any other opaque
# mutation. The pretool now recognises the same CLI list atom-floor uses and
# emits no gated targets for them, so the no-targets early exit below covers
# them. Two gates disagreeing about what must always run is what made the trap.
#
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

  local atom_id session envelope workroot
  atom_id=$(printf '%s\n' "$mk" | grep -m1 '^ATOM_ID=' | cut -d= -f2-)
  session=$(printf '%s\n' "$mk" | grep -m1 '^SESSION=' | cut -d= -f2-)
  envelope=$(printf '%s\n' "$mk" | grep -m1 '^TOUCHES=' | cut -d= -f2-)
  workroot=$(printf '%s\n' "$mk" | grep -m1 '^WORKROOT=' | cut -d= -f2-)
  # WORKROOT (2026-08-17, codex PASS): frozen records are authority, but the
  # consumer still validates authority SHAPE — malformed WORKROOT fails closed.
  if [ -n "$workroot" ]; then
    case "$workroot" in
      /*) [ -d "$workroot" ] || { DISPATCH_GATE_VERDICT="BLOCK"
            DISPATCH_GATE_REASON="frozen WORKROOT is not a directory: $workroot — re-resolve"
            _dg_journal BLOCK "workroot-malformed" "$tool" "${1:-}"; return 0; } ;;
      *) DISPATCH_GATE_VERDICT="BLOCK"
         DISPATCH_GATE_REASON="frozen WORKROOT is not absolute: $workroot — re-resolve"
         _dg_journal BLOCK "workroot-malformed" "$tool" "${1:-}"; return 0 ;;
    esac
  fi

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

  # WORKFLOW FLOOR (HARD, founder ruling G5=A 2026-08-25; dual-lane consult
  # folded x2): a CLASS>=4 unit refuses mutation until at least one Workflow
  # COMPLETION landed in this session's transcript AFTER the bound atom
  # opened. The transcript is harness-written — the model cannot author the
  # counted rows (see wf-evidence.sh) — and an unreadable or regressed
  # transcript fails CLOSED: fail-open here is a one-line evasion via
  # Bash-deleting the file (both lanes, convergent ship-blocker).
  # Same-turn launch+mutate can false-BLOCK until the end-of-turn flush;
  # accepted by design — the retry lands next turn and a timing carve-out
  # would be a bypass with extra steps.
  # Kill-switch: ~/.workflow-floor-disabled (founder revoke only, journaled).
  local mclass
  mclass=$(printf '%s\n' "$mk" | grep -m1 '^CLASS=' | cut -d= -f2-)
  case "$mclass" in
    4|5|5+)
      if [ -f "$HOME/.workflow-floor-disabled" ]; then
        _dg_journal ALLOW "workflow-floor-killswitch" "$tool" "${1:-}"
      elif ! command -v wf_completion_count >/dev/null 2>&1; then
        _dg_journal ALLOW "fail-open:no-wf-evidence-lib" "$tool" "${1:-}"
      else
        local _wf_t _wf_live _wf_base
        _wf_t=$(wf_transcript_path "$_DG_ROOT" "$_DG_SID")
        _wf_live=$(wf_completion_count "$_wf_t")
        _wf_base=$(jq -r '.wf_evidence.completions_at_open // 0' "$af" 2>/dev/null) || _wf_base=0
        case "$_wf_base" in ''|*[!0-9]*) _wf_base=0 ;; esac
        if [ "$_wf_live" -lt 0 ]; then
          DISPATCH_GATE_VERDICT="BLOCK"
          DISPATCH_GATE_REASON="WORKFLOW FLOOR: session transcript unavailable ($_wf_t) — CLASS=$mclass requires verifiable Workflow evidence and unavailable state fails closed (kill-switch: ~/.workflow-floor-disabled, founder only)"
          _dg_journal BLOCK "workflow-transcript-unavailable" "$tool" "${1:-}"
          return 0
        fi
        if [ "$_wf_live" -lt "$_wf_base" ]; then
          DISPATCH_GATE_VERDICT="BLOCK"
          DISPATCH_GATE_REASON="WORKFLOW FLOOR: live completion count ($_wf_live) is below the atom's open snapshot ($_wf_base) — suspicious transcript state, fail-closed"
          _dg_journal BLOCK "workflow-transcript-regressed" "$tool" "${1:-}"
          return 0
        fi
        if [ "$_wf_live" -le "$_wf_base" ]; then
          DISPATCH_GATE_VERDICT="BLOCK"
          DISPATCH_GATE_REASON="WORKFLOW FLOOR: CLASS=$mclass is a heavy unit and policy G5=A (2026-08-25) requires a prior Workflow-tool orchestration run for it — run the Workflow tool, wait for its completion notification, then retry (completions now $_wf_live, at atom open $_wf_base)"
          _dg_journal BLOCK "workflow-evidence-missing" "$tool" "${1:-}"
          return 0
        fi
        _dg_journal ALLOW "workflow-floor-satisfied" "$tool" "-"
      fi
      ;;
  esac

  # Agent tool: params must match the frozen routing (weak-binding fold, G2).
  #
  # Two namespaces meet here. The frozen record holds a policy catalog id
  # (claude-opus-5); the Agent tool's `model` parameter takes an alias (opus).
  # Comparing them directly BLOCKed every pinned call and ALLOWed every unpinned
  # one — the exact inversion that made routing decorative. _dg_model_alias
  # bridges them, and an unknown id is malformed authority -> BLOCK.
  if [ "$tool" = "Agent" ]; then
    local mmodel malias mplace mprov probe vv saw_model=0
    mmodel=$(printf '%s\n' "$mk" | grep -m1 '^MODEL=' | cut -d= -f2-)
    mplace=$(printf '%s\n' "$mk" | grep -m1 '^PLACEMENT=' | cut -d= -f2-)
    mprov=$(printf '%s\n' "$mk" | grep -m1 '^PROVIDER=' | cut -d= -f2-)
    # The Agent `model` enum is Claude-only. A unit dispatched to another
    # provider has a model id that HAS no alias by construction (gpt-5.4), so
    # running the alias comparison there would block it on every Agent call —
    # a deadlock with no remediation. Provider containment therefore gates the
    # whole binding, not just the SPAWN rule (regression test case 9).
    if [ "${mprov:-claude}" != "claude" ]; then
      _dg_journal ALLOW "agent-model-non-claude-provider" "$tool" "provider=$mprov"
      return 0
    fi
    malias=$(_dg_model_alias "$mmodel")
    if [ -z "$malias" ]; then
      DISPATCH_GATE_VERDICT="BLOCK"
      DISPATCH_GATE_REASON="frozen MODEL='$mmodel' has no known Agent alias — malformed authority; re-resolve, or add the id to _dg_model_alias if the catalog gained a model"
      _dg_journal BLOCK "agent-model-unknown" "$tool" "model=$mmodel"
      return 0
    fi
    for probe in "$@"; do
      case "$probe" in
        # Sentinel from dispatcher-pretool: the call carried NO model param.
        # Needed because an absent param used to emit no probe at all, and the
        # no-targets early exit then returned ALLOW before this branch ran, so
        # unpinned spawns were structurally unreachable (codex P1, 2026-09-08).
        agent-model-absent=1) saw_model=0 ;;
        model=*) vv="${probe#model=}"
          [ -n "$vv" ] && saw_model=1
          if [ -n "$vv" ] && [ "$vv" != "$mmodel" ] && [ "$vv" != "$malias" ]; then
            DISPATCH_GATE_VERDICT="BLOCK"
            DISPATCH_GATE_REASON="Agent model '$vv' != dispatched '$mmodel' (alias '$malias') — escalate via sutra-dispatch, not ad-hoc"
            _dg_journal BLOCK "agent-model-drift" "$tool" "$probe"
            return 0
          fi ;;
      esac
    done
    # SPAWN means the routed model is NOT the one this session runs, so only an
    # explicit pin can honour the route; inheriting the session model silently
    # discards it. Scoped to PROVIDER=claude: non-claude providers are
    # inherently SPAWN (routing-policy-resolve) and do not use this model enum,
    # so a provider-agnostic rule would deadlock them (codex P2, 2026-09-08).
    if [ "$mplace" = "SPAWN" ] && [ "${mprov:-claude}" = "claude" ] && [ "$saw_model" = "0" ]; then
      DISPATCH_GATE_VERDICT="BLOCK"
      DISPATCH_GATE_REASON="unit is PLACEMENT=SPAWN routed to '$mmodel' but the Agent call pins no model — pass model='$malias' so the route is honoured instead of inheriting the session model"
      _dg_journal BLOCK "agent-model-unpinned" "$tool" "placement=SPAWN"
      return 0
    fi
    # Journal WHICH spelling was accepted, so a later pass can tighten to
    # alias-only on evidence rather than guesswork (codex P2, 2026-09-08).
    _dg_journal ALLOW "agent-params-match" "$tool" "spelling=$([ "$saw_model" = "1" ] && echo pinned || echo none)"
    return 0
  fi

  # Bash codex invocation: when the FROZEN record dispatched this unit to the
  # codex provider, the launcher MUST pin the resolved model. Without this the
  # tier is observable (codex prints it in its banner) but not enforced — a
  # dropped -m silently reverts codex to its server default, the top tier.
  # Reaches the gate as a `command=` kv probe, the same shape as the Agent
  # `model=` probe; dispatcher-pretool adds it ONLY for codex commands, so the
  # no-targets early return still covers every other read-only Bash call.
  local _dgp _dgcmd=""
  for _dgp in "$@"; do
    case "$_dgp" in command=*) _dgcmd="${_dgp#command=}" ;; esac
  done
  if [ -n "$_dgcmd" ]; then
    local _dgprov _dgwant _dggot
    _dgprov=$(printf '%s\n' "$mk" | grep -m1 '^PROVIDER=' | cut -d= -f2-)
    # Only a codex-provider unit is enforced. A codex REVIEW of Claude work is
    # review machinery, not a codex dispatch; blocking it would be policy
    # expansion, not enforcement (codex Q3).
    if [ "$_dgprov" = "codex" ]; then
      _dgwant=$(printf '%s\n' "$mk" | grep -m1 '^MODEL=' | cut -d= -f2-)
      _dggot=$(_dg_codex_model "$_dgcmd")
      if [ "$_dggot" = "__RESUME__" ] || [ "$_dggot" = "__PARSE_FAIL__" ] || [ "$_dggot" = "__NOT_CODEX__" ]; then
        : # resume keeps its session model; unparseable/non-codex fails OPEN
      elif [ "$_dggot" != "$_dgwant" ]; then
        DISPATCH_GATE_VERDICT="BLOCK"
        DISPATCH_GATE_REASON="codex model '${_dggot:-<none>}' != dispatched '$_dgwant' — the resolved tier would be ignored; pin it with -m \"$_dgwant\" or re-resolve"
        _dg_journal BLOCK "codex-model-drift" "$tool" "${_dggot:-<none>}"
        return 0
      fi
    fi
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
    # the codex `command=` probe is a kv signal, not a mutation target
    case "$t" in command=*) continue ;; esac
    verdict=$(TOUCHES_MATCH_ROOT="${workroot:-$_DG_ROOT}" touches_match "$t" 1 ${env_entries[@]+"${env_entries[@]}"})
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

# ── Target derivation — ONE implementation (codex P1, 2026-09-10) ────────────
# dispatch_gate_targets <tool> <file_path> <bash_cmd> <agent_model>
#   Fills DG_TARGETS (array) + DG_CLI_EXEMPT=0|1 the way the holding
#   orchestrator's Check 13 does. The derivation IS the security boundary, so
#   it lives here, next to the check, instead of being re-typed per caller.
#   Requires atom-floor.sh sourced first: _atom_floor_whitelisted for
#   Edit/Write, and atom_floor_check already run for Bash (it exports
#   ATOM_FLOOR_BASH_TARGETS + ATOM_FLOOR_MUTATION). Never exits the caller.
dispatch_gate_targets() {
  local tool="${1:-}" fpath="${2:-}" cmd="${3:-}" amodel="${4:-}"
  DG_TARGETS=(); DG_CLI_EXEMPT=0
  case "$tool" in
    Edit|Write|MultiEdit)
      [ -n "$fpath" ] || return 0
      case "$fpath" in
        # The dispatch record and atom files ARE the mutation authority and the
        # floor whitelists them (*.sutra/*): force them to the gate so only the
        # CLIs may write them (G6-synthesis P1). Evidence stores are M7-denied.
        *.sutra/dispatch/*|*.sutra/atoms/*) DG_TARGETS+=("$fpath") ;;
        *.sutra/*ledger*|*.enforcement/*)   DG_TARGETS+=("$fpath") ;;
        *) if type _atom_floor_whitelisted >/dev/null 2>&1 \
              && ! _atom_floor_whitelisted "$fpath"; then
             DG_TARGETS+=("$fpath")
           fi ;;
      esac ;;
    Agent|Task)
      # ALWAYS a probe: an absent model used to emit nothing, and the
      # no-targets early exit returned ALLOW before the Agent branch ran, so
      # unpinned spawns were unreachable by the gate (codex P1, 2026-09-08).
      if [ -n "$amodel" ]; then DG_TARGETS+=("model=$amodel")
      else DG_TARGETS+=("agent-model-absent=1"); fi ;;
    Bash)
      [ -n "$cmd" ] || return 0
      # Governance-CLI exemption: the CLIs write the very record this gate
      # reads, so gating them on that record is circular (recovery trap,
      # 2026-08-28). Anchored on the command word of EVERY segment — the same
      # rule atom-floor.sh applies — so `sutra-atom close; rm x` is not exempt.
      local seg all=1 re
      re='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*(command[[:space:]]+|exec[[:space:]]+|env[[:space:]]+)?((ba)?sh[[:space:]]+)?([^[:space:]]*/)?(sutra-atom|sutra-marker|sutra-dispatch|routing-policy-resolve|context-manifest|flow-ledger-append|wdp-evidence)([[:space:]]|$)'
      while IFS= read -r seg; do
        [ -z "${seg//[[:space:]]/}" ] && continue
        printf '%s' "$seg" | grep -qE "$re" || { all=0; break; }
      done < <(printf '%s\n' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" | tr ';&|\n' '\n\n\n\n')
      if [ "$all" = "1" ]; then DG_CLI_EXEMPT=1; return 0; fi
      # codex model pin probe — codex commands only, so read-only Bash keeps
      # the no-targets early return (2026-08-28).
      case "$cmd" in *codex*) DG_TARGETS+=("command=$cmd") ;; esac
      local t
      while IFS= read -r t; do
        t="${t#>>}"; t="${t#>}"
        [ -z "$t" ] && continue
        # Q: prefix = floor already proved it is one quoted path token.
        case "$t" in Q:*) DG_TARGETS+=("${t#Q:}"); continue ;; esac
        # The repo root itself (universal `cd <root>` prefix) is never a target.
        case "${t%/}" in "${_DG_ROOT%/}") continue ;; esac
        # Characters no unquoted shell word can carry mark prose, not a path.
        case "$t" in
          '~'*|*'://'*|*'$'*|*'('*|*')'*|*'{'*|*'}'*|*'`'*|*';'*|*"'"*|*'"'*)
            _dg_journal SKIP "unresolvable_token" Bash "$t"; continue ;;
        esac
        DG_TARGETS+=("$t")
      done <<< "${ATOM_FLOOR_BASH_TARGETS:-}"
      # A mutation the scanner cannot NAME still demands a bound record (G6).
      if [ ${#DG_TARGETS[@]} -eq 0 ] && [ "${ATOM_FLOOR_MUTATION:-0}" = "1" ]; then
        _dg_journal OPAQUE "unnamed_mutation" Bash "-"
        DG_TARGETS+=("::opaque-mutation::")
      fi ;;
  esac
  return 0
}

# ── Hook entrypoint (2026-09-10; codex CHANGES-REQUIRED folded) ──────────────
# hooks.json executes this file DIRECTLY as a PreToolUse hook on
# Edit|Write|Bash|Task. Until this runner existed the file was a function
# library, so every fleet install ran a silent no-op while only Asawa enforced,
# through holding/hooks/dispatcher-pretool.sh (found 2026-09-10).
#
# Mode: <repo>/.claude/dispatch-mode = hard | warn. Default WARN with NO
# auto-promotion — WDP decision D-C holds fleet-wide HARD for a founder call;
# a repo promotes itself with `echo hard > .claude/dispatch-mode`.
# Delegation: when the holding orchestrator exists in this repo it is the
# single enforcer and this runner exits 0, so no verdict is ever journaled
# twice with two enforcement meanings (codex P1).
# Fail-closed: malformed hook input (no jq, empty stdin, no tool_name) is a
# BLOCK in hard mode, never a silent allow (codex P1).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  [ -f "$_DG_ROOT/holding/hooks/dispatcher-pretool.sh" ] && exit 0
  # Redirection order matters: `< file 2>/dev/null` still prints the shell's
  # own "No such file" for a missing mode file, on every fleet call.
  _DG_MODE=""
  [ -r "$_DG_ROOT/.claude/dispatch-mode" ] && _DG_MODE=$(tr -d '[:space:]' 2>/dev/null < "$_DG_ROOT/.claude/dispatch-mode")
  case "$_DG_MODE" in hard|warn) ;; *) _DG_MODE="warn" ;; esac
  _dg_emit() { # $1=title $2=reason -> stderr; exit 2 in hard, exit 0 in warn
    if [ "$_DG_MODE" = "hard" ]; then
      {
        echo "BLOCKED — $1 (HARD): $2"
        echo "  Fix path: sutra-dispatch resolve ... && sutra-atom open ... && sutra-dispatch bind"
        echo "  Mode file: .claude/dispatch-mode (hard|warn). Kill-switch: touch ~/.dispatch-gate-disabled (founder revoke only)"
      } >&2
      exit 2
    fi
    {
      echo "$1 (WARN): $2"
      echo "  Enforcement is WARN in this repo. Promote: echo hard > .claude/dispatch-mode"
    } >&2
    exit 0
  }
  _DG_IN=$(cat 2>/dev/null || true)
  command -v jq >/dev/null 2>&1 || _dg_emit "DISPATCH GATE" "jq unavailable — hook input cannot be evaluated"
  _DG_TOOL=$(printf '%s' "$_DG_IN" | jq -r '.tool_name // empty' 2>/dev/null)
  [ -n "$_DG_TOOL" ] || _dg_emit "DISPATCH GATE" "malformed hook input (empty stdin or no tool_name)"
  case "$_DG_TOOL" in Edit|Write|MultiEdit|Bash|Agent|Task) ;; *) exit 0 ;; esac
  _DG_FILE=$(printf '%s' "$_DG_IN" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  _DG_CMD=$(printf '%s' "$_DG_IN" | jq -r '.tool_input.command // empty' 2>/dev/null)
  _DG_AMODEL=$(printf '%s' "$_DG_IN" | jq -r '.tool_input.model // empty' 2>/dev/null)
  if [ "$_DG_SID" = "nosession" ]; then
    _DG_SID=$(printf '%s' "$_DG_IN" | jq -r '.session_id // empty' 2>/dev/null)
    [ -n "$_DG_SID" ] || _DG_SID="nosession"
    _DG_MARKER="$_DG_ROOT/.sutra/dispatch/$_DG_SID/dispatch-record"
    export CLAUDE_CODE_SESSION_ID="${CLAUDE_CODE_SESSION_ID:-$_DG_SID}"
  fi
  # Floor first: path whitelist, Bash mutation scanner, open-atom verdict.
  . "$(dirname "${BASH_SOURCE[0]}")/atom-floor.sh" 2>/dev/null || true
  ATOM_FLOOR_VERDICT="allow"; ATOM_FLOOR_MUTATION=0; ATOM_FLOOR_BASH_TARGETS=""
  if type atom_floor_check >/dev/null 2>&1; then
    atom_floor_check "$_DG_TOOL" "$_DG_FILE" "$_DG_CMD" || true
  fi
  [ "${ATOM_FLOOR_VERDICT:-allow}" = "block" ] && _dg_emit "ATOM FLOOR" \
    "no open Work-Atom for session $_DG_SID — open one first: sutra-atom open --goal '<observable outcome>' --verify-template <file-exists|grep-count|named-test> --verify-arg <...>"
  dispatch_gate_targets "$_DG_TOOL" "$_DG_FILE" "$_DG_CMD" "$_DG_AMODEL"
  [ "${DG_CLI_EXEMPT:-0}" = "1" ] && exit 0
  [ "${#DG_TARGETS[@]}" -gt 0 ] || exit 0
  [ "$_DG_TOOL" = "Task" ] && _DG_TOOL="Agent"
  dispatch_gate_check "$_DG_TOOL" "${DG_TARGETS[@]}" || true
  [ "${DISPATCH_GATE_VERDICT:-ALLOW}" = "BLOCK" ] && _dg_emit "DISPATCH GATE" "${DISPATCH_GATE_REASON:-envelope violation}"
  exit 0
fi
