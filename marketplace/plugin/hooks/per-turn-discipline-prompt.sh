#!/usr/bin/env bash
# per-turn-discipline-prompt.sh — D40 G1 governance-parity hook
#
# Event: UserPromptSubmit
# Behavior: emit a soft hint reminding the model to emit Input Routing + Depth
#           on every turn (including pure-question turns where Edit/Write hooks
#           don't fire).
#
# Per codex CHANGES-REQUIRED fold (v1.0.1, 2026-04-30): hook now CONSUMES
# sutra-defaults.json at runtime via jq, instead of hardcoding reminder text.
# This makes sutra-defaults.json the actual canonical policy surface (D40 G6),
# not just documentation.
#
# Per codex caveat (D40 verdict): hook-injects-prompt is SOFT GUIDANCE ONLY.
# Failure modes: prompt dilution, collision, token bloat, cosmetic emission,
# subagent drift. Backed by deterministic Edit/Write hooks elsewhere.
#
# Kill-switches (any one disables):
#   ~/.sutra-defaults-disabled        (all D40 defaults)
#   ~/.per-turn-discipline-disabled   (this hook only)
#   SUTRA_DEFAULTS_DISABLED=1
#
# Fail-open: exit 0 always (never block the user prompt).

set -u

# Kill-switches
[ -f "$HOME/.sutra-defaults-disabled" ] && exit 0
[ -f "$HOME/.per-turn-discipline-disabled" ] && exit 0
[ -n "${SUTRA_DEFAULTS_DISABLED:-}" ] && exit 0

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo ".")}"

# Fresh-install gate: stay silent until the user has run /core:start (which
# writes .claude/sutra-project.json with their profile). Before that, the
# reminder is non-actionable noise — they don't yet know what Input Routing /
# Depth blocks ARE. After /core:start, the doctrine doc is on their disk and
# the reminder becomes a useful nudge. Kill-switch: SUTRA_DISCIPLINE_PRE_ACTIVATION=1.
if [ -z "${SUTRA_DISCIPLINE_PRE_ACTIVATION:-}" ] && [ ! -f "$REPO_ROOT/.claude/sutra-project.json" ]; then
  exit 0
fi

DEFAULTS_DIR="${CLAUDE_PLUGIN_ROOT:-$REPO_ROOT/sutra/marketplace/plugin}"
DEFAULTS_JSON="$DEFAULTS_DIR/sutra-defaults.json"

# Fallback path: json or jq missing → minimal reminder
if [ ! -r "$DEFAULTS_JSON" ] || ! command -v jq >/dev/null 2>&1; then
  printf '\n[Sutra defaults · D40] Per-turn discipline: emit Input Routing + Depth blocks. See SUTRA-DEFAULTS.md.\n  (sutra-defaults.json or jq unavailable — using fallback reminder)\n\n' >&2
  exit 0
fi

# Consume canonical surface (D40 G6 — single source of truth).
# v2.15.1 systemic fix (founder direction "systemically fix it"): the prior
# pattern (v2.14.1 BLUEPRINT-not-showing → v2.15.0 four disciplines → this
# H-Sutra-not-showing) all had the same root cause: hook reminder phrased as
# "skill: X" form, which the model interpreted as "invoke skill X" rather
# than "emit this text directly." When skill auto-discovery didn't fire,
# the block was silently skipped. v2.15.1 changes phrasing to imperative —
# every reminder line now explicitly states the emission contract (direct
# text vs. skill-invocation) and uses verb forms like "MUST emit" rather
# than parenthetical hints.
# v2.15.1 also reads .per_turn_blocks.human_sutra_header from sutra-defaults
# instead of hardcoding (closes v2.14.1 deferred TODO).
HS_FORMAT=$(jq -r '.per_turn_blocks.human_sutra_header.format' "$DEFAULTS_JSON" 2>/dev/null)
HS_FAIL=$(jq -r '.per_turn_blocks.human_sutra_header.format_stage_1_fail' "$DEFAULTS_JSON" 2>/dev/null)
IR_FIELDS=$(jq -r '.per_turn_blocks.input_routing.fields | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
IR_SKILL=$(jq -r '.per_turn_blocks.input_routing.skill' "$DEFAULTS_JSON" 2>/dev/null)
DEPTH_FIELDS=$(jq -r '.per_turn_blocks.depth_estimation.fields_pre | join(", ")' "$DEFAULTS_JSON" 2>/dev/null)
DEPTH_SKILL=$(jq -r '.per_turn_blocks.depth_estimation.skill' "$DEFAULTS_JSON" 2>/dev/null)
BP_FIELDS=$(jq -r '.per_turn_blocks.blueprint.fields | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
BP_SKILL=$(jq -r '.per_turn_blocks.blueprint.skill' "$DEFAULTS_JSON" 2>/dev/null)
BL_FIELDS=$(jq -r '.per_turn_blocks.build_layer.fields | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
BL_HOOK=$(jq -r '.per_turn_blocks.build_layer.hook' "$DEFAULTS_JSON" 2>/dev/null)
OT_FORMAT=$(jq -r '.per_turn_blocks.output_trace.format' "$DEFAULTS_JSON" 2>/dev/null)
OT_SKILL=$(jq -r '.per_turn_blocks.output_trace.skill' "$DEFAULTS_JSON" 2>/dev/null)
# -- PLACEMENT (ADR-028). The compact one-liner is the mandatory shape; the
#    ancestor tree renders only on mint. Enforcement mode is read live from the
#    repo so the prompt tells the truth about whether this repo is warn or hard.
PL_COMPACT=$(jq -r '.per_turn_blocks.placement.shapes.compact // empty' "$DEFAULTS_JSON" 2>/dev/null | sed 's/  *—.*$//')
PL_PROMOTE=$(jq -r '.per_turn_blocks.placement.enforcement_ladder.promote_after_compliant_turns // 50' "$DEFAULTS_JSON" 2>/dev/null)
PL_MODE="warn"
if [ -n "${REPO_ROOT:-}" ] && [ -f "$REPO_ROOT/.claude/placement-mode" ]; then
  PL_MODE=$(tr -d '[:space:]' < "$REPO_ROOT/.claude/placement-mode" 2>/dev/null)
  case "$PL_MODE" in hard|warn) ;; *) PL_MODE="warn" ;; esac
fi
DEPTH_THRESHOLD=$(jq -r '.consult_policy.depth_threshold' "$DEFAULTS_JSON" 2>/dev/null)
CONSULT_TOOLS=$(jq -r '.consult_policy.applies_to_tools | join("/")' "$DEFAULTS_JSON" 2>/dev/null)
KILL_FILE=$(jq -r '.kill_switches.per_turn_discipline_prompt.file' "$DEFAULTS_JSON" 2>/dev/null)
# v2.15.0: 3 governance disciplines added to nudge — skill-explain card,
# readability gate, Karpathy right-effort. Each was Asawa-side memory or
# defaults-schema-only with no T4 visibility. Founder direction: "ship
# everything to clients" (2026-05-01).
SE_LINES=$(jq -r '.skill_explanation.template_lines | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
SE_SKILL=$(jq -r '.skill_explanation.skill' "$DEFAULTS_JSON" 2>/dev/null)
RG_PRACTICES=$(jq -r '[.output_discipline | to_entries[] | select(.value == true) | .key] | join(", ")' "$DEFAULTS_JSON" 2>/dev/null)
RG_SKILL=$(jq -r '.output_discipline.skill' "$DEFAULTS_JSON" 2>/dev/null)
RE_PRINCIPLES=$(jq -r '.right_effort.principles_short | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
RE_TOOLS=$(jq -r '.right_effort.applies_before | join("/")' "$DEFAULTS_JSON" 2>/dev/null)
FLOW_TYPES=$(jq -r '(.per_turn_blocks.flow.applies_to_turn_types // []) | join(" / ")' "$DEFAULTS_JSON" 2>/dev/null)
FLOW_SUBST=$(jq -r '(.per_turn_blocks.flow.applies_if_substantive // []) | join("/")' "$DEFAULTS_JSON" 2>/dev/null)
FLOW_SKILL=$(jq -r '.per_turn_blocks.flow.skill // "core:flow"' "$DEFAULTS_JSON" 2>/dev/null)

# Emit derived reminder (changes if json changes). v2.15.1 systemic fix:
# imperative phrasing — every line states emission mode explicitly (DIRECT
# TEXT vs. skill-invocation). The "(skill: X)" parenthetical was ambiguous
# and caused the model to skip blocks when skill auto-discovery didn't
# fire. Now each reminder makes the contract clear with verbs like "MUST
# emit literal text" or "MUST invoke <skill>". Mirrors what
# skills/human-sutra/SKILL.md documents — duplicated here so T4 model
# gets the same imperative without needing CLAUDE.md governance context.
_sutra_per_turn_block() {
  printf '\n[Sutra defaults · D40 v1.0.3] Per-turn block stack — MUST emit in this order:\n'
  printf '\n'
  printf '  TOPIC-GATING FORBIDDEN. Emit the full per-turn discipline blocks for every user input,\n'
  printf '  regardless of topic. Personal, research, lifestyle, emotional, chitchat, greetings —\n'
  printf '  every input receives the same block stack. For lightweight inputs, keep block CONTENT\n'
  printf '  minimal (one-word fields ok) but PRESENCE is mandatory. Structure universality, not\n'
  printf '  depth universality. Founder direction: "sutra for anything and everything" (D45-cand).\n'
  printf '\n'
  printf '  1. H-SUTRA HEADER     MUST emit as FIRST line of response — literal bracketed text, NOT a skill invocation:\n'
  printf '                        Format: %s\n' "${HS_FORMAT:-[<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]}"
  printf '                        On Stage-1 fail: %s\n' "${HS_FAIL:-[STAGE-1-FAIL · CLARIFY · attempt:1/1]}"
  printf '  2. INPUT ROUTING      MUST emit literal block with fields: %s\n' "${IR_FIELDS:-INPUT/TYPE/...}"
  printf '  3. DEPTH + ESTIMATION MUST emit literal block with fields: %s\n' "${DEPTH_FIELDS:-TASK/DEPTH/...}"
  printf '  4. BLUEPRINT          MUST emit literal block IF tool calls planned (Edit/Write/Bash/Agent). Fields: %s\n' "${BP_FIELDS:-Doing/Steps/Scale/Stops if/Switch}"
  printf '                        The EMITTED BLOCK IS THE CONTRACT (v3, 2026-07-27). No marker to write: the hooks\n'
  printf '                        read the block in your response text. On foundational paths (charters, protocols,\n'
  printf '                        FOUNDER-DIRECTIONS, engine specs) blueprint-check.sh also requires a concrete\n'
  printf '                        "Output looks like:" + a runnable "Verified by:" (+ inline Verify: on every Step\n'
  printf '                        at D3+). Ordinary files are floored at Stop by per-turn-hard-gate.sh.\n'
  printf '  5. BUILD-LAYER marker MUST emit IF editing D38 paths (sutra/marketplace/plugin/** etc). Fields: %s\n' "${BL_FIELDS:-LAYER/SCOPE/TARGET-PATH/...}"
  printf '  6. PLACEMENT          MUST emit literal one-line block (ADR-028) — every unit of work carries an address:\n'
  printf '                        %s\n' "${PL_COMPACT:-PLACEMENT: D0 > D3 <name> > D3.D2 <name> | \"<charter title>\"}"
  printf '                        Expand to the full ancestor tree ONLY when a Domain or Charter was minted this turn.\n'
  printf '                        The system decides the taxonomy — never ask the operator, never block on a missing\n'
  printf '                        domain: if nothing matches, mint under the deepest matching ancestor and continue.\n'
  printf '                        THEN write .claude/placement-registered via the WRITE TOOL. Enforcement is %s\n' "${PL_MODE:-warn}"
  printf '                        in this repo (promotes to HARD after %s compliant turns).\n' "${PL_PROMOTE:-50}"
  printf '  7. ... tool calls (Edit / Write / Bash / Agent) ...\n'
  printf '  8. OUTPUT TRACE       MUST emit literal one-liner: %s\n' "${OT_FORMAT:-> route: <skill> > <domain> > <nodes> > <terminal>}"
  printf '\n  FLOW ACTIVATION (EVERY input, D61 amended 2026-06-15) -- after Input Routing sets the TYPE:\n'
  printf '  MUST emit the FLOW block as LITERAL TEXT every turn (the way Input Routing / the H-Sutra header are\n'
  printf '  literal text -- NOT a Skill call). This is the firing, and it is what makes Flow as reliable as Input\n'
  printf '  Routing: a hook can nudge + floor a miss, but NO hook can force a Skill on the first pass. The block\n'
  printf '  reports the honest resolved spine for THIS unit:\n'
  printf '    [1] TYPE/cell  [2] FOLLOW <skill>|CONSTRUCT  [3] steps  [4] inner: lens/cynefin/factors  [5] mode  [6] close\n'
  printf '  Then write the flow markers (.claude/flow-classified, flow-type-resolved) via the WRITE TOOL\n'
  printf '  (Claude Code rolls back Bash writes to .claude/) so the floors read real state.\n'
  printf '  Invoke the FULL %s Skill (deep recursive spine) ONLY for substantive/multi-step/ambiguous work (%s) --\n' "${FLOW_SKILL:-core:flow}" "${FLOW_SUBST:-multi_step/ambiguous_shape/unknown_how/heavy}"
  printf '  not every trivial turn. Inline block = per-turn floor; Skill = deep mode.\n'
  printf '  HONESTY BAR: state what ACTUALLY resolved -- an honest 1-step ATOM block on a trivial turn is correct;\n'
  printf '  do NOT claim a recursive walk / cynefin / factors you did not run (that is the theater D61 forbids).\n'
  printf '  Floors (not the firing): flow-gate.sh (PreToolUse Edit/Write+Task) + flow-stop-check.sh (Stop, no-tool turns), HARD fleet-wide.\n'
  printf '\n  Conditionals (apply when triggered):\n'
  printf '  - Codex consult: IF Depth >= %s with %s planned → invoke %s skill BEFORE the Edit\n' "${DEPTH_THRESHOLD:-3}" "${CONSULT_TOOLS:-Edit/Write/MultiEdit}" "${CONSULT_SKILL:-core:codex-sutra}"
  printf '  - Skill-explain: BEFORE invoking any Skill, emit 4-line card with: %s\n' "${SE_LINES:-SKILL/WHAT/WHY/EXPECT/ASKS}"
  printf '  - Readability gate: format output per: %s\n' "${RG_PRACTICES:-tables_preferred_over_prose, numbers_preferred_over_adjectives, decisions_in_ascii_boxes}"
  printf '  - Right-effort (Karpathy): BEFORE %s, apply: %s\n' "${RE_TOOLS:-Edit/Write}" "${RE_PRINCIPLES:-think first / simpler-alt / surgical scope / verify-loop}"
  printf '\n  Canonical schema: %s/sutra-defaults.json  (human-readable: SUTRA-DEFAULTS.md)\n' "$DEFAULTS_DIR"
  printf '  Kill-switch: touch %s\n\n' "${KILL_FILE:-~/.per-turn-discipline-disabled}"
}

# ── Emission path (2026-07-27 root-cause fix) ───────────────────────────────
# This block used to be written to STDERR (`} >&2`). Per the Claude Code hook
# contract, for UserPromptSubmit ONLY STDOUT is added to the model's context:
#
#   "For most events, stdout is written to the debug log but not shown in the
#    transcript. The exceptions are UserPromptSubmit, UserPromptExpansion and
#    SessionStart, where stdout is added as context that Claude can see and
#    act on."
#
# stderr on exit 0 is not shown to the model at all. So for the entire life of
# this hook the per-turn contract — H-Sutra, Input Routing, Depth, BLUEPRINT,
# Build-Layer, FLOW ACTIVATION — was emitted into a stream the model cannot
# read. Flow fired only where CLAUDE.md happened to restate it; T4 fleet
# clients (no CLAUDE.md governance) received nothing at all. That is the root
# cause of the flow-gate / flow-stop-check block volume, NOT model indiscipline.
#
# Fix: emit as hookSpecificOutput.additionalContext on stdout, which Claude
# Code wraps in a system-reminder and inserts alongside the submitted prompt.
# Fail-open to stderr when jq is unavailable (no worse than the old behavior).
# FAIL-OPEN CONTRACT: this hook must never fail a user turn and must never
# emit anything to stdout except the single JSON object. Any jq failure (NUL
# byte in the block, OOM, malformed arg) degrades to the old stderr path
# rather than exiting non-zero or emitting a partial payload — a truncated
# object on stdout is worse than none, since Claude Code would drop the whole
# hookSpecificOutput and silently reinstate the original bug.
_BLOCK_TEXT="$(_sutra_per_turn_block)"
_JSON_OUT=""
if command -v jq >/dev/null 2>&1; then
  _JSON_OUT="$(jq -nc --arg ctx "$_BLOCK_TEXT" \
    '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$ctx}}' 2>/dev/null)" || _JSON_OUT=""
fi
if [ -n "$_JSON_OUT" ]; then
  printf '%s\n' "$_JSON_OUT"
else
  printf '%s' "$_BLOCK_TEXT" >&2
fi

# STDOUT LOCK: everything after this point is diagnostics or side-effects and
# must NOT reach fd 1 — stray output would concatenate onto the JSON above and
# invalidate it. Redirect fd 1 to fd 2 for the remainder of the script so any
# present or future stdout write lands on stderr instead of corrupting the
# payload. (DeepSeek consult 2026-07-27, finding 1.)
exec 1>&2

# ──────────────────────────────────────────────────────────────────────────
# H-Sutra classification — v2 (D49 codex round-1..5 fold, 2026-05-06).
#
# Refactored: canonical classify+write logic moved to the shared library at
# `lib/h-sutra-classify-and-write.sh`. This wrapper handles ONLY:
#   - stdin JSON parse (prompt + session_id)
#   - SUTRA_HSUTRA_LOG_PATH env override → Asawa override → default fallback
#   - sourcing the lib + calling h_sutra_classify_and_write
#
# Behavioral parity with v1:
#   - same row schema (15 fields + optional input_text), now also emits .risk
#     alias for native predicate.ts:97 consumer
#   - same dedupe (tail-grep last 10 turn_ids)
#   - same mkdir-based locks (per-turn arbitration + per-log dedupe)
#   - same fail-open semantics (exit 0 on infra failure)
# Adds:
#   - per-turn arbitration lock so co-installed core+native produce ONE row
#   - sanitized session_id + bounded length + age-based stale-lock recovery
#   - SUTRA_HSUTRA_LOG_PATH env override (round-3 P1-2 fold; existing Native
#     consumer contract at h-sutra-connector.ts:54)
#
# Source: D49 entry in holding/FOUNDER-DIRECTIONS.md (2026-05-06).
# ──────────────────────────────────────────────────────────────────────────

# Single H-Sutra env break-glass (D49 codex review P2-B fold) — honored by
# BOTH core and native wrappers so the advertised single override actually
# disables H-Sutra producer in co-installed setups, not just standalone
# native. Loud-log on use.
if [ -n "${SUTRA_HSUTRA_FORCE_DISABLE:-}" ]; then
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  printf '[%s] [h-sutra-core] DISABLED via SUTRA_HSUTRA_FORCE_DISABLE=1\n' "$TS" >&2
  exit 0
fi

# Shared lib — function-only; sourcing has no side effects.
HSUTRA_LIB="$DEFAULTS_DIR/lib/h-sutra-classify-and-write.sh"
if [ ! -r "$HSUTRA_LIB" ]; then
  printf '[h-sutra] lib missing at %s — row skipped.\n' "$HSUTRA_LIB" >&2
  exit 0
fi
# shellcheck source=../lib/h-sutra-classify-and-write.sh
. "$HSUTRA_LIB"

HSUTRA_INPUT_JSON=""
if [ ! -t 0 ]; then
  HSUTRA_INPUT_JSON=$(cat 2>/dev/null || true)
fi
HSUTRA_PROMPT=""
HSUTRA_SESSION_ID=""
if [ -n "$HSUTRA_INPUT_JSON" ]; then
  HSUTRA_PROMPT=$(printf '%s' "$HSUTRA_INPUT_JSON" | jq -r '.prompt // empty' 2>/dev/null || true)
  HSUTRA_SESSION_ID=$(printf '%s' "$HSUTRA_INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || true)
fi
[ -z "$HSUTRA_PROMPT" ] && exit 0

HSUTRA_CLASSIFIER="$DEFAULTS_DIR/skills/human-sutra/scripts/classify.sh"
if [ ! -r "$HSUTRA_CLASSIFIER" ]; then
  printf '[h-sutra] classifier missing at %s — row skipped.\n' "$HSUTRA_CLASSIFIER" >&2
  exit 0
fi

# Log path resolution — env override > Asawa override > default
if [ -n "${SUTRA_HSUTRA_LOG_PATH:-}" ]; then
  HSUTRA_LOG="$SUTRA_HSUTRA_LOG_PATH"
elif [ -f "$REPO_ROOT/holding/state/interaction/log.jsonl" ]; then
  HSUTRA_LOG="$REPO_ROOT/holding/state/interaction/log.jsonl"
else
  HSUTRA_LOG="$REPO_ROOT/.sutra/h-sutra.jsonl"
fi

h_sutra_classify_and_write "$HSUTRA_PROMPT" "$HSUTRA_CLASSIFIER" "$HSUTRA_LOG" "$HSUTRA_SESSION_ID" || true

# ──────────────────────────────────────────────────────────────────────────
# FLOW FIRING — deterministic, hook-side (2026-07-27, D61 amendment 3)
#
# Previously the flow markers were written by the MODEL, on instruction. That
# instruction went to stderr and never arrived (see the emission-path note
# above), so the markers were frequently absent and the floors fired on turns
# that had in fact walked the spine.
#
# The classifier already runs on every real prompt, one line up, and derives a
# speech-act verb deterministically. That is enough to write the classify
# marker without asking the model for anything. Flow now FIRES by construction:
# stage 1 (classify) is executed by this hook, every turn, before the model
# acts. Stage 2 (resolve) is left PENDING for the model to refine — a hook
# cannot know whether an existing workflow type FOLLOWs or steps must be
# CONSTRUCTed.
#
# Markers are SESSION-SCOPED (.claude/flow-<name>-<SID>), matching the pattern
# codex-directive-detect.sh already uses. Concurrent sessions in one repo were
# clobbering each other's single-slot markers — observed live 2026-07-27, where
# a foreign session's content (older TS, different UNIT) overwrote this
# session's marker mid-turn and produced a spurious flow-stop-block.
#
# Fail-open throughout: every write is `|| true`. A marker that fails to write
# degrades to the pre-existing behavior (floor fires, model re-walks), never to
# a failed turn.
# Scheme A (marker-lib) is the single marker authority as of 2026-07-27. The flat
# `.claude/<name>-<sid>` suffix scheme this hook originally wrote is DELETED — see
# project_marker_scheme_reconcile. marker-lib dual-writes the legacy global path
# during migration, so readers not yet on sutra_marker_has still find these.
# Sourced defensively: `set -u` is active (line 25) and a stray RETURN trap or an
# unbound var inside a sourced file would otherwise abort the whole hook mid-turn.
# A governance hook must never fail the user's turn — degrade, never die.
_MARKER_LIB="$(dirname "$0")/marker-lib.sh"
if [ -f "$_MARKER_LIB" ]; then
  set +u
  . "$_MARKER_LIB" || true
  sutra_sid_from_stdin "$HSUTRA_INPUT_JSON" || true
  set -u
fi
_FLOW_SID=$(printf '%s' "$HSUTRA_SESSION_ID" | tr -cd 'a-zA-Z0-9_-' | head -c 64)
[ -z "$_FLOW_SID" ] && _FLOW_SID="no-sid"

_FLOW_VERB=$(bash "$HSUTRA_CLASSIFIER" "$HSUTRA_PROMPT" 2>/dev/null \
  | jq -r '.verb // empty' 2>/dev/null)

# verb -> Flow TYPE. classify.sh derives verb reliably; its ir_type field is an
# echoed INPUT, not a derived output, so it is deliberately not used here.
case "$_FLOW_VERB" in
  QUERY)  _FLOW_TYPE="question"  ;;
  DIRECT) _FLOW_TYPE="direction" ;;
  ASSERT) _FLOW_TYPE="feedback"  ;;
  *)      _FLOW_TYPE="task"      ;;
esac

mkdir -p "$REPO_ROOT/.claude" 2>/dev/null || true
if command -v sutra_marker_set >/dev/null 2>&1; then
  sutra_marker_set flow-classified \
    "$(printf 'TYPE=%s\nVERB=%s\nSESSION=%s\nFIRED_BY=hook\nTS=%s' \
       "$_FLOW_TYPE" "${_FLOW_VERB:-UNKNOWN}" "$_FLOW_SID" "$(date +%s)")" || true
  sutra_marker_set flow-type-resolved \
    "$(printf 'RESOLVE=PENDING\nSESSION=%s\nFIRED_BY=hook\nTS=%s' \
       "$_FLOW_SID" "$(date +%s)")" || true
else
  # marker-lib unavailable: fall back to the legacy global path so the floor still
  # sees a marker. Never leave the turn with no marker at all.
  printf 'TYPE=%s\nVERB=%s\nSESSION=%s\nFIRED_BY=hook\nTS=%s\n' \
    "$_FLOW_TYPE" "${_FLOW_VERB:-UNKNOWN}" "$_FLOW_SID" "$(date +%s)" \
    > "$REPO_ROOT/.claude/flow-classified" 2>/dev/null || true
  printf 'RESOLVE=PENDING\nSESSION=%s\nFIRED_BY=hook\nTS=%s\n' \
    "$_FLOW_SID" "$(date +%s)" \
    > "$REPO_ROOT/.claude/flow-type-resolved" 2>/dev/null || true
fi

mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null || true
printf '{"ts":"%s","event":"flow-fired-by-hook","session":"%s","type":"%s","verb":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_FLOW_SID" "$_FLOW_TYPE" "${_FLOW_VERB:-UNKNOWN}" \
  >> "$REPO_ROOT/.enforcement/flow-gate.jsonl" 2>/dev/null || true

exit 0
