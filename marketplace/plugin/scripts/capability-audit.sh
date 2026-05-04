#!/usr/bin/env bash
# capability-audit.sh — Recurring drift detector for the capability-axis charter (D43).
#
# WHAT: Walks the "Asawa runs / fleet doesn't" disciplines and reports a 4-state
# matrix per discipline: present_in_runtime / declared_in_policy / wired_for_activation
# / mapped_in_CSM. Surfaces gaps the dormant 2026-05-01 fleet-parity audit table
# (sutra/CURRENT-VERSION.md:143-154) listed without an instrument behind it.
#
# WHY: One-shot audits decay. A script keeps the truth current and seeds the
# pre-commit/CI registry diff gate (CAPABILITY-MAP.md TODO #1).
#
# HOW: codex consult 2026-05-04 ADVISORY (3) folded — separates the four states
# rather than emitting a flat gap list; reads CURRENT-VERSION.md backlog table
# as one of six sources; safe to run repeatedly (read-only on plugin tree).
#
# Build-layer: L1 (single-instance:asawa). Promote-to: plugin/scripts/ by 2026-06-01.

set -euo pipefail

ROOT="${ROOT:-${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"
# Asawa-mode gate (L0 promotion): silently exit on T4 fleet per file-presence check
[ -f "$ROOT/holding/CAPABILITY-MAP.md" ] || exit 0
PLUGIN="$ROOT/sutra/marketplace/plugin"
DEFAULTS_JSON="$PLUGIN/sutra-defaults.json"
HOOKS_JSON="$PLUGIN/hooks/hooks.json"
SKILLS_DIR="$PLUGIN/skills"
HOOKS_DIR="$PLUGIN/hooks"
CSM="$ROOT/holding/CAPABILITY-MAP.md"
TS_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TS_DAY="$(date -u +%Y-%m-%d)"
OUT_TXT="$ROOT/.analytics/capability-audit-${TS_DAY}.txt"
OUT_JSONL="$ROOT/holding/state/capability-map-audit.jsonl"

mkdir -p "$ROOT/.analytics"

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq required" >&2; exit 127; }

# ---- Source-of-truth disciplines ----
# Format: name|description|defaults_jq_path|skill_or_hook_path|hooks_json_grep|csm_grep
# defaults_jq_path: jq filter under .per_turn_blocks or top-level (use "" if N/A)
# skill_or_hook_path: relative to $PLUGIN (use "" if N/A)
# hooks_json_grep: literal string grep in hooks.json (use "" if N/A)
# csm_grep: cap-### or topic literal to grep in CAPABILITY-MAP.md
#
# Top 5 per-turn blocks already shipping (cap-001..005, sanity row):
DISCIPLINES_SHIPPED=(
  "input_routing|Input Routing block|.per_turn_blocks.input_routing|skills/input-routing||cap-001"
  "depth_estimation|Depth + Estimation|.per_turn_blocks.depth_estimation|skills/depth-estimation||cap-002"
  "blueprint|BLUEPRINT block|.per_turn_blocks.blueprint|skills/blueprint|blueprint|cap-003"
  "readability_gate|Readability Gate (skill)|.output_discipline|skills/readability-gate||cap-004"
  "output_trace|Output Trace|.per_turn_blocks.output_trace|skills/output-trace||cap-005"
)

# 10-row dormant fleet-parity backlog from sutra/CURRENT-VERSION.md:143-154
DISCIPLINES_BACKLOG=(
  "right_effort|Karpathy Right-Effort discipline|.right_effort|||cap-108"
  "skill_explanation|Skill-explain card hook nudge|.skill_explanation|skills/skill-explain||cap-109"
  "subagent_dispatch|Subagent dispatch contract briefing|.subagent_dispatch|hooks/subagent-dispatch-brief.sh|subagent-dispatch-brief|cap-110"
  "readability_gate_nudge|Readability Gate hook nudge|.output_discipline||readability|cap-111"
  "customer_focus_first|Customer Focus First (Doctrine P0)|.customer_focus_first|||cap-112"
  "highlight_decisions|Highlight decisions (ASCII box)|.output_discipline.highlight_decisions|||cap-113"
  "no_fabrication|No fabrication (truthfulness/attribution)|.no_fabrication|||cap-114"
  "table_shape|Table Shape (Impact + Effort columns)|.output_discipline.table_shape|||cap-115"
  "process_discipline|Process Discipline (PROTO-006)|.process_discipline_proto006|||cap-116"
  "csm_at_creation|Capability Map (D43) at-creation hook||hooks/csm-classification-pretooluse.sh||cap-117"
  "no_invented_human_ops|No invented human-ops mechanisms (proposals only)|.no_invented_human_ops_mechanisms|||cap-118"
)

check_runtime() {
  local path="$1"
  [ -z "$path" ] && { echo "n/a"; return; }
  [ -e "$PLUGIN/$path" ] && echo "YES" || echo "NO"
}

check_policy() {
  local jq_path="$1"
  [ -z "$jq_path" ] && { echo "n/a"; return; }
  jq -e "$jq_path" "$DEFAULTS_JSON" >/dev/null 2>&1 && echo "YES" || echo "NO"
}

# v1.1: pass runtime_path so skills/ entries get auto-discovery treatment.
# Skills under sutra/marketplace/plugin/skills/ are auto-discovered by Claude Code
# via SKILL.md description on UserPromptSubmit — they don't need explicit
# hooks.json entries. v1.0 incorrectly showed A=NO for these (false negative).
check_activation() {
  local needle="$1"
  local runtime_path="${2:-}"
  if [ -z "$needle" ]; then
    if [ -n "$runtime_path" ] && [[ "$runtime_path" == skills/* ]] && [ -d "$PLUGIN/$runtime_path" ]; then
      echo "auto"
    else
      echo "n/a"
    fi
    return
  fi
  grep -q "$needle" "$HOOKS_JSON" && echo "YES" || echo "NO"
}

check_csm() {
  local cap_id="$1"
  [ -z "$cap_id" ] && { echo "n/a"; return; }
  grep -q "^| $cap_id " "$CSM" && echo "YES" || echo "NO"
}

# v1.1: derive cap status from CAPABILITY-MAP.md table column
check_status() {
  local cap_id="$1"
  [ -z "$cap_id" ] && { echo "?"; return; }
  awk -F'|' -v id=" $cap_id " '$2==id {gsub(/^ +| +$/,"",$5); print $5; exit}' "$CSM" | head -c 12
}

emit_row() {
  local row="$1"
  IFS='|' read -r name desc def_path runtime_path hooks_grep cap_id <<< "$row"
  local R P A C S
  R=$(check_runtime "$runtime_path")
  P=$(check_policy "$def_path")
  A=$(check_activation "$hooks_grep" "$runtime_path")
  C=$(check_csm "$cap_id")
  S=$(check_status "$cap_id")
  printf "| %-9s | %-44s | %-4s | %-3s | %-4s | %-3s | %-12s |\n" "$cap_id" "$desc" "$R" "$P" "$A" "$C" "$S"
}

{
  echo "# Capability Axis Audit — $TS_UTC (v1.1: skill auto-discovery + Status column)"
  echo "# Source-of-truth disciplines + dormant fleet-parity backlog from sutra/CURRENT-VERSION.md:143-154"
  echo "# Matrix per codex 2026-05-04 ADVISORY (R/P/A/C) + v1.1 Status column from CSM table:"
  echo "#   R = present_in_runtime  (file exists in plugin/)"
  echo "#   P = declared_in_policy  (key present in sutra-defaults.json)"
  echo "#   A = wired_for_activation (referenced in hooks.json; 'auto' = skill auto-discovery)"
  echo "#   C = mapped_in_CSM       (cap-### row in CAPABILITY-MAP.md)"
  echo "#   Status = bucket-status from CAPABILITY-MAP.md table (shipping/proposed/etc.)"
  echo
  echo "## Sanity row (5 already-shipping per-turn blocks)"
  echo "## v1.1 fix: skill auto-discovery now shown as A=auto instead of A=NO"
  echo
  printf "| %-9s | %-44s | %-4s | %-3s | %-4s | %-3s | %-12s |\n" "cap-id" "Discipline" "R" "P" "A" "C" "Status"
  printf "|-%-9s-|-%-44s-|-%-4s-|-%-3s-|-%-4s-|-%-3s-|-%-12s-|\n" "$(printf '%.0s-' {1..9})" "$(printf '%.0s-' {1..44})" "----" "---" "----" "---" "------------"
  for row in "${DISCIPLINES_SHIPPED[@]}"; do emit_row "$row"; done
  echo
  echo "## Dormant fleet-parity backlog (10 disciplines from CURRENT-VERSION.md:143-154)"
  echo "## After v2.15.0 promotion of right_effort, expect cap-108 P=YES; rest mostly NO"
  echo
  printf "| %-9s | %-44s | %-4s | %-3s | %-4s | %-3s | %-12s |\n" "cap-id" "Discipline" "R" "P" "A" "C" "Status"
  printf "|-%-9s-|-%-44s-|-%-4s-|-%-3s-|-%-4s-|-%-3s-|-%-12s-|\n" "$(printf '%.0s-' {1..9})" "$(printf '%.0s-' {1..44})" "----" "---" "----" "---" "------------"
  for row in "${DISCIPLINES_BACKLOG[@]}"; do emit_row "$row"; done
  echo
  echo "## Findings summary"
  echo "1. Disciplines with R=NO P=YES → schema declared but no runtime emitter (theater)"
  echo "2. Disciplines with R=YES P=NO → orphaned hooks/skills not in policy schema"
  echo "3. Disciplines with all NO except C=NO → memory-only Asawa-side; no fleet path yet"
  echo "4. Disciplines with C=NO → not mapped in CSM (visibility gap)"
  echo
  echo "## Known governance debt (out of script scope)"
  echo "- (Resolved 2026-05-04) D# collision: ## D43 (OUT-DIRECT) renumbered to D46; ## D44 (PERMISSIONS) renumbered to D47. ADR-002 + ADR-003 D-direction bindings updated. CHANGELOG historical refs preserved."
} | tee "$OUT_TXT"

# Append a single audit-run row to the JSONL audit log
audit_jsonl_row=$(jq -nc \
  --arg ts "$TS_UTC" \
  --arg out "$OUT_TXT" \
  --arg n "${#DISCIPLINES_BACKLOG[@]}" \
  '{ts:$ts, action:"AUDIT_RUN", actor:"asawa", note:"capability-axis audit run; \($n)-row backlog matrix written to \($out)", cap_id:null, direction:"D43", script:"holding/scripts/capability-audit.sh", output:$out}')
echo "$audit_jsonl_row" >> "$OUT_JSONL"

echo
echo "Audit text:  $OUT_TXT"
echo "Audit jsonl: $OUT_JSONL (appended 1 row)"
