#!/bin/bash
# build-layer-check.sh — PROTO-021 + D38 BUILD-LAYER declaration gate (HARD)
#
# v2.0 (2026-04-28): D38 amendment — structured marker schema + plugin-first
# decision logic per codex consult DIRECTIVE-ID 1777362899 (verdict ADVISORY).
#
# Direction:    PROTO-021 (sutra/layer2-operating-system/PROTOCOLS.md §PROTO-021 D38 Amendment)
#               D38 (holding/FOUNDER-DIRECTIONS.md §D38)
# Event:        PreToolUse on Edit|Write|MultiEdit
# Enforcement:  HARD on D38 implementation surfaces + LEGACY-HARD set; SOFT elsewhere.
#
# ── Path categories ────────────────────────────────────────────────────────
#   WHITELIST          .claude/, .enforcement/, .analytics/, holding/checkpoints/,
#                      holding/research/, holding/state/, holding/TODO.md,
#                      holding/hooks/hook-log.jsonl, sutra/archive/, *.lock,
#                      ~/.claude/projects/**/memory/**
#   D38_PLUGIN_RUNTIME sutra/marketplace/plugin/{hooks,scripts,skills,commands,bin,lib}/**
#   D38_SHARED_RUNTIME sutra/hooks/** (git/runtime universals — codex carve-out)
#   D38_HOLDING_IMPL   holding/{hooks,scripts,skills,commands,bin}/**
#   LEGACY_HARD        holding/departments/**, holding/evolution/**,
#                      holding/FOUNDER-DIRECTIONS.md, sutra/os/charters/**,
#                      sutra/marketplace/plugin/* (top-level non-impl files)
#   SOFT               everywhere else not whitelisted
#
# ── Decision logic (HARD, exit 2 on violation) ─────────────────────────────
#   D38_PLUGIN_RUNTIME or D38_SHARED_RUNTIME:
#     LAYER must be L0; else exit 2.
#   D38_HOLDING_IMPL:
#     marker required;
#     LAYER L0 forbidden (lying);
#     L1 needs all PROMOTE_TO/PROMOTE_BY/OWNER/ACCEPTANCE non-empty + non-NONE;
#     L2 needs WHY_NOT_L0_KIND=instance-only AND WHY_NOT_L0_REASON non-empty.
#   LEGACY_HARD:
#     marker present (any content) = pass (PROTO-021 original semantics).
#   SOFT:
#     advisory only, never blocks.
#
# ── Marker schema (multi-line KV at .claude/build-layer-registered) ─────────
#   LAYER=L0|L1|L2
#   SCOPE=fleet|cohort:<name>|single-instance:<name>
#   TARGET_PATH=<abs path or normalized prefix>
#   WHY_NOT_L0_KIND=staging|instance-only
#   WHY_NOT_L0_REASON=<non-empty text>
#   PROMOTE_TO=<plugin path or NONE>
#   PROMOTE_BY=<YYYY-MM-DD or NONE>
#   OWNER=<durable role or NONE>
#   ACCEPTANCE=<non-empty or NONE>
#   TS=<unix>
#
# Backward compat: LEGACY_HARD paths accept old single-line marker
# (LAYER=N SCOPE=X TARGET=path TS=ts) — only existence checked, not parsed.
#
# ── Override ──────────────────────────────────────────────────────────────
#   BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <tool-call>
#   Logged with: actor, path, cmd, reason, ts, session_id, declared_layer,
#   override_kind. Honor-system at env-var level; not authenticated.
#
# Spec:    sutra/layer2-operating-system/PROTOCOLS.md §PROTO-021 + D38 Amendment
# Codex:   .enforcement/codex-reviews/d38-codex-consult-1777362899.md (ADVISORY)
# Design:  holding/research/2026-04-23-build-layer-protocol-design.md

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
FILE_PATH="${TOOL_INPUT_file_path:-}"

# Stdin-JSON fallback
if [ -z "$FILE_PATH" ] && [ ! -t 0 ]; then
  _JSON=$(cat 2>/dev/null)
  if [ -n "$_JSON" ]; then
    if command -v jq >/dev/null 2>&1; then
      FILE_PATH=$(printf '%s' "$_JSON" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    else
      FILE_PATH=$(printf '%s' "$_JSON" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
    fi
  fi
fi

[ -z "$FILE_PATH" ] && exit 0
REL_PATH="${FILE_PATH#$REPO_ROOT/}"
LEDGER="$REPO_ROOT/.enforcement/build-layer-ledger.jsonl"
MARKER="$REPO_ROOT/.claude/build-layer-registered"
mkdir -p "$REPO_ROOT/.enforcement" 2>/dev/null

# ── Whitelist ───────────────────────────────────────────────────────────────
case "$REL_PATH" in
  .claude/*|.enforcement/*|.analytics/*) exit 0 ;;
  holding/checkpoints/*|holding/TODO.md|holding/hooks/hook-log.jsonl) exit 0 ;;
  holding/research/*) exit 0 ;;
  holding/state/*) exit 0 ;;
  sutra/archive/*) exit 0 ;;
  *.lock) exit 0 ;;
esac
case "$FILE_PATH" in
  */.claude/projects/*/memory/*) exit 0 ;;
esac

# ── Path classification ─────────────────────────────────────────────────────
PATH_CATEGORY="SOFT"

# D38 PLUGIN_RUNTIME — sutra/marketplace/plugin/{hooks,scripts,skills,commands,bin,lib}/**
# 2026-05-04 (codex consult 1777875522): added `lib/` for sourced shared libraries
# (e.g., telemetry-shared-path.sh) — same L0 fleet semantics as hooks/ et al.
for _prefix in \
    sutra/marketplace/plugin/hooks/ \
    sutra/marketplace/plugin/scripts/ \
    sutra/marketplace/plugin/skills/ \
    sutra/marketplace/plugin/commands/ \
    sutra/marketplace/plugin/bin/ \
    sutra/marketplace/plugin/lib/; do
  if [[ "$REL_PATH" == "$_prefix"* ]]; then
    PATH_CATEGORY="D38_PLUGIN_RUNTIME"
    break
  fi
done

# D38 SHARED_RUNTIME — sutra/hooks/**
if [ "$PATH_CATEGORY" = "SOFT" ] && [[ "$REL_PATH" == sutra/hooks/* ]]; then
  PATH_CATEGORY="D38_SHARED_RUNTIME"
fi

# D38 HOLDING_IMPL — holding/{hooks,scripts,skills,commands,bin}/**
if [ "$PATH_CATEGORY" = "SOFT" ]; then
  for _prefix in \
      holding/hooks/ \
      holding/scripts/ \
      holding/skills/ \
      holding/commands/ \
      holding/bin/; do
    if [[ "$REL_PATH" == "$_prefix"* ]]; then
      PATH_CATEGORY="D38_HOLDING_IMPL"
      break
    fi
  done
fi

# LEGACY_HARD — existing PROTO-021 set (non-D38 paths)
if [ "$PATH_CATEGORY" = "SOFT" ]; then
  case "$REL_PATH" in
    holding/departments/*|holding/evolution/*|sutra/os/charters/*) PATH_CATEGORY="LEGACY_HARD" ;;
    sutra/marketplace/plugin/*) PATH_CATEGORY="LEGACY_HARD" ;;  # plugin top-level non-impl files
    holding/FOUNDER-DIRECTIONS.md) PATH_CATEGORY="LEGACY_HARD" ;;
  esac
fi

# ── Marker field extraction (bash 3.2 compatible — no associative arrays) ──
# Each field read via grep on the marker file. Fields default to empty string
# when missing; downstream callers must handle empty-vs-NONE explicitly.
# Schema convention: ONE KEY PER LINE — values are single-line strings.
# Multi-line values are NOT supported (reader takes the first physical line
# matching ^KEY=). If a future field needs prose, store as JSON or use a
# referenced sidecar file rather than embedded newlines.
get_marker_field() {
  local key="$1"
  [ -f "$MARKER" ] || { echo ""; return; }
  grep -E "^${key}=" "$MARKER" 2>/dev/null | head -1 | sed "s/^${key}=//"
}

M_LAYER=$(get_marker_field LAYER)
M_SCOPE=$(get_marker_field SCOPE)
M_TARGET_PATH=$(get_marker_field TARGET_PATH)
M_WHY_NOT_L0_KIND=$(get_marker_field WHY_NOT_L0_KIND)
M_WHY_NOT_L0_REASON=$(get_marker_field WHY_NOT_L0_REASON)
M_PROMOTE_TO=$(get_marker_field PROMOTE_TO)
M_PROMOTE_BY=$(get_marker_field PROMOTE_BY)
M_OWNER=$(get_marker_field OWNER)
M_ACCEPTANCE=$(get_marker_field ACCEPTANCE)
M_TS=$(get_marker_field TS)

# Backward compat: old single-line marker uses TARGET= not TARGET_PATH=
if [ -z "$M_TARGET_PATH" ]; then
  M_TARGET_PATH=$(get_marker_field TARGET)
fi

normalize_layer() {
  case "$1" in
    L0|0) echo "L0" ;;
    L1|1) echo "L1" ;;
    L2|2) echo "L2" ;;
    *) echo "INVALID" ;;
  esac
}

LAYER_NORM=$(normalize_layer "$M_LAYER")

# ── JSON-safe escape ────────────────────────────────────────────────────────
_jsafe() {
  printf '%s' "$1" | tr -d '"\\' | tr '\n\r' '  '
}

# ── Override path ───────────────────────────────────────────────────────────
if [ "${BUILD_LAYER_ACK:-0}" = "1" ]; then
  _REASON="${BUILD_LAYER_ACK_REASON:-no-reason-given}"
  _ACTOR="${USER:-unknown}"
  _SESSION_ID="${CLAUDE_SESSION_ID:-${SUTRA_SESSION_ID:-unknown}}"
  _DECLARED_LAYER="${M_LAYER:-none}"
  _TS=$(date +%s)
  _CMD="${TOOL_INPUT_command:-Edit|Write}"
  echo "{\"ts\":$_TS,\"event\":\"override\",\"path\":\"$(_jsafe "$REL_PATH")\",\"category\":\"$PATH_CATEGORY\",\"reason\":\"$(_jsafe "$_REASON")\",\"actor\":\"$(_jsafe "$_ACTOR")\",\"session_id\":\"$(_jsafe "$_SESSION_ID")\",\"declared_layer\":\"$(_jsafe "$_DECLARED_LAYER")\",\"override_kind\":\"build_layer_ack\",\"cmd\":\"$(_jsafe "$_CMD")\"}" >> "$LEDGER"
  echo "  [build-layer] override accepted (BUILD_LAYER_ACK=1): $_REASON" >&2
  exit 0
fi

# ── Block helpers ───────────────────────────────────────────────────────────
TS=$(date +%s)

block_d38() {
  local detail="$1"
  echo "{\"ts\":$TS,\"event\":\"block\",\"file\":\"$(_jsafe "$REL_PATH")\",\"category\":\"$PATH_CATEGORY\",\"detail\":\"$(_jsafe "$detail")\"}" >> "$LEDGER"
  {
    echo ""
    echo "BLOCKED — D38 plugin-first violation (exit 2)"
    echo ""
    echo "  Target:   $REL_PATH"
    echo "  Category: $PATH_CATEGORY"
    echo "  Detail:   $detail"
    echo ""
    echo "  Rule:"
    echo "    Implementation surfaces default to plugin L0. holding/{hooks,scripts,"
    echo "    skills,commands,bin}/** requires explicit L1 or L2 justification."
    echo ""
    echo "  Required marker fields at .claude/build-layer-registered (multi-line KV):"
    echo "    LAYER=L0|L1|L2"
    echo "    SCOPE=fleet|cohort:<name>|single-instance:<name>"
    echo "    TARGET_PATH=<abs path>"
    echo "    WHY_NOT_L0_KIND=staging|instance-only       (L1/L2 only)"
    echo "    WHY_NOT_L0_REASON=<non-empty>               (L1/L2 only)"
    echo "    PROMOTE_TO=<plugin path>                    (L1 only, non-NONE)"
    echo "    PROMOTE_BY=<YYYY-MM-DD>                     (L1 only, non-NONE)"
    echo "    OWNER=<durable role>                        (L1 only, non-NONE)"
    echo "    ACCEPTANCE=<non-empty>                      (L1 only, non-NONE)"
    echo "    TS=<unix>"
    echo ""
    echo "  Quick fixes:"
    echo "    - If this is universal/generic, write to:"
    echo "        sutra/marketplace/plugin/<surface>/        (Claude Code marketplace surfaces)"
    echo "        sutra/hooks/                                (git/runtime universals)"
    echo "    - If L1 staging: declare PROMOTE_TO + PROMOTE_BY + OWNER + ACCEPTANCE."
    echo "    - If L2 instance-only: declare WHY_NOT_L0_KIND=instance-only + non-empty WHY_NOT_L0_REASON."
    echo ""
    echo "  Override (one tool call, audit-logged):"
    echo "    BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<specific-reason>' <tool>"
    echo ""
    echo "  Spec:  sutra/layer2-operating-system/PROTOCOLS.md §PROTO-021 D38 Amendment"
    echo "  D38:   holding/FOUNDER-DIRECTIONS.md §D38"
    echo "  Codex: .enforcement/codex-reviews/d38-codex-consult-1777362899.md"
    echo ""
  } >&2
  exit 2
}

block_legacy_proto021() {
  echo "{\"ts\":$TS,\"event\":\"block\",\"file\":\"$(_jsafe "$REL_PATH")\",\"category\":\"LEGACY_HARD\",\"detail\":\"marker missing\"}" >> "$LEDGER"
  {
    echo ""
    echo "BLOCKED — BUILD-LAYER declaration missing (PROTO-021 HARD on legacy path)"
    echo "  File:  $REL_PATH"
    echo ""
    echo "  Emit BUILD-LAYER block + write marker before Edit/Write."
    echo "  Spec: sutra/layer2-operating-system/PROTOCOLS.md §PROTO-021"
    echo ""
    echo "  Override: BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>' <tool>"
    echo ""
  } >&2
  exit 2
}

# ── Decision logic ──────────────────────────────────────────────────────────
case "$PATH_CATEGORY" in
  D38_PLUGIN_RUNTIME|D38_SHARED_RUNTIME)
    if [ ! -f "$MARKER" ]; then
      block_d38 "marker missing — canonical plugin/runtime path requires LAYER=L0 declaration"
    fi
    if [ "$LAYER_NORM" != "L0" ]; then
      block_d38 "$PATH_CATEGORY requires LAYER=L0; got '${M_LAYER:-none}'"
    fi
    ;;

  D38_HOLDING_IMPL)
    if [ ! -f "$MARKER" ]; then
      block_d38 "marker missing — holding implementation surface requires structured BUILD-LAYER block"
    fi
    case "$LAYER_NORM" in
      L0)
        block_d38 "LAYER=L0 forbidden on holding/{hooks,scripts,skills,commands,bin}/ — file should be at sutra/marketplace/plugin/<surface>/ or sutra/hooks/"
        ;;
      L1)
        # Validate L1 fields individually (bash 3.2 — no indirect array)
        if [ -z "$M_PROMOTE_TO" ] || [ "$M_PROMOTE_TO" = "NONE" ]; then
          block_d38 "L1 staging requires non-empty PROMOTE_TO; got '${M_PROMOTE_TO:-empty}'"
        fi
        if [ -z "$M_PROMOTE_BY" ] || [ "$M_PROMOTE_BY" = "NONE" ]; then
          block_d38 "L1 staging requires non-empty PROMOTE_BY; got '${M_PROMOTE_BY:-empty}'"
        fi
        if [ -z "$M_OWNER" ] || [ "$M_OWNER" = "NONE" ]; then
          block_d38 "L1 staging requires non-empty OWNER; got '${M_OWNER:-empty}'"
        fi
        if [ -z "$M_ACCEPTANCE" ] || [ "$M_ACCEPTANCE" = "NONE" ]; then
          block_d38 "L1 staging requires non-empty ACCEPTANCE; got '${M_ACCEPTANCE:-empty}'"
        fi
        ;;
      L2)
        if [ "$M_WHY_NOT_L0_KIND" != "instance-only" ]; then
          block_d38 "L2 requires WHY_NOT_L0_KIND=instance-only; got '${M_WHY_NOT_L0_KIND:-empty}'"
        fi
        if [ -z "$M_WHY_NOT_L0_REASON" ]; then
          block_d38 "L2 requires non-empty WHY_NOT_L0_REASON"
        fi
        ;;
      *)
        block_d38 "LAYER must be L0|L1|L2 on D38 path; got '${M_LAYER:-empty}'"
        ;;
    esac
    ;;

  LEGACY_HARD)
    if [ ! -f "$MARKER" ]; then
      block_legacy_proto021
    fi
    ;;

  SOFT)
    if [ ! -f "$MARKER" ]; then
      echo "{\"ts\":$TS,\"event\":\"advisory\",\"file\":\"$(_jsafe "$REL_PATH")\",\"category\":\"SOFT\"}" >> "$LEDGER"
      echo "  [build-layer] Reminder: declare BUILD-LAYER block before Edit/Write on non-whitelisted paths." >&2
    fi
    ;;
esac

exit 0

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# `.enforcement/build-layer-ledger.jsonl` row count by event type:
#   - `block` (D38 + LEGACY_HARD)
#   - `advisory` (SOFT)
#   - `override` (BUILD_LAYER_ACK=1)
# Metrics:
#   - `d38_block_rate` = D38 block events / D38-path Edit attempts (target: <10% by day 14)
#   - `legacy_block_rate` = LEGACY_HARD block events / LEGACY_HARD-path Edit attempts
#   - `override_rate` = override events / total enforced events (target: <5% — aggressive overrides indicate path mis-classification or marker UX too painful)
# Null handling: silent when marker valid; ledger row only on enforcement event.
#
# ### 2. Adoption mechanism
# Hook registered in `.claude/settings.json` PreToolUse matcher `Edit|Write|MultiEdit`.
# Marker write pattern documented in `CLAUDE.md` §Build-Layer (multi-line KV at
# `.claude/build-layer-registered`). PROTO-021 D38 Amendment in
# `sutra/layer2-operating-system/PROTOCOLS.md` carries the canonical schema.
# Wave 1 promotes this hook to `sutra/marketplace/plugin/hooks/build-layer-check.sh`
# (L0); holding copy becomes a 4-line shim per D38 §5 mirror retirement rule.
# Promotion deadline: 2026-04-28 (this wave) or next session per founder pace.
#
# ### 3. Monitoring / escalation
# Session-end review appended by `holding/hooks/dispatcher-stop.sh` reports
# per-session L0/L1/L2 declarations + D38 block events + stale-L1 items past
# `PROMOTE_BY` date. Warn: any D38 block event in 24h window (declaration
# habit not stuck for D38 paths). Breach: >3 D38 blocks in 6h window
# (indicates either (a) legitimate D38 violations being attempted — review
# the targets; (b) path classification too aggressive — review boundaries).
# Escalation: surface in cadence-review (Asawa CEO).
#
# ### 4. Iteration trigger
# Tighten enforcement when:
#   (a) D38 block rate <5% for 7 days (markers becoming habit) → consider
#       widening D38 paths (e.g., add `holding/lib/**`).
#   (b) Override rate sustained <2% (audit log mostly clean) → consider
#       requiring authenticated override (founder-only signing, post-MVP).
# Loosen / re-classify when:
#   (a) D38 block rate >20% in first 3 days (paths wrongly classified or
#       marker UX broken) — review with codex consult.
#   (b) Override reasons cluster on a single pattern → either upgrade
#       schema to support that case or explicitly carve out.
#
# ### 5. DRI
# Asawa CEO (durable role). Per PROTO-021 §RELATES + D31, Sutra Forge owns
# authoring authority; this hook IS the Sutra Forge enforcement surface for
# both PROTO-021 (LEGACY_HARD) and D38 (PLUGIN/SHARED/HOLDING-IMPL).
#
# ### 6. Decommission criteria
# Retire holding/hooks/build-layer-check.sh when (a) plugin promotion lands
# (sutra/marketplace/plugin/hooks/build-layer-check.sh registered in plugin
# hooks.json AND shipped in a release), AND (b) holding shim TTL elapses
# (7 days max post-promotion per D38 §5). At decommission, holding file
# either becomes 4-line shim or is deleted with `.claude/settings.json`
# rewired to plugin path.
# ================================================================================
