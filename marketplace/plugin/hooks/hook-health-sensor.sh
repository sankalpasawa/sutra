#!/usr/bin/env bash
# hook-health-sensor.sh — Cross-session hook health report. Exit 0 always.
LOG="$(cd "$(dirname "$0")" && pwd)/hook-log.jsonl"
NOW=$(date +%s); WEEK_AGO=$((NOW - 604800))
if [ ! -f "$LOG" ]; then
  echo "═══ HOOK HEALTH SENSOR ═══"; echo "No hook-log.jsonl found."; echo "═══════════════════════════"; exit 0
fi
REPORT=$(jq -r --argjson c "$WEEK_AGO" 'select(.ts >= $c)' "$LOG" | jq -s '
  (length) as $t | (map(select(.status=="pass"))|length) as $p |
  {s:{total:$t,pass:$p,rate:(if $t>0 then($p*100/$t)else 0 end)},
   h:(group_by(.hook)|map({hook:.[0].hook, last_ts:(map(.ts)|max),
      avg_ms:((map(.ms//0)|add)/length),
      tail:(sort_by(.ts)|[.[-3:][]|.status]),
      err:(sort_by(.ts)|last|.error//"")}))}' 2>/dev/null)
[ -z "$REPORT" ] && REPORT='{"s":{"total":0,"pass":0,"rate":0},"h":[]}'
TOTAL=$(echo "$REPORT"|jq '.s.total')
RATE=$(echo "$REPORT"|jq '.s.rate|floor')
BROKEN=$(echo "$REPORT"|jq -r '
  [.h[]|select((.tail|length>=3)and(.tail|all(.=="fail")))]|
  if length==0 then "  (none)" else map("  ✗ \(.hook) — last error: \"\(.err)\"")|join("\n") end')
SLOW=$(echo "$REPORT"|jq -r '
  [.h[]|select(.avg_ms>100)]|
  if length==0 then "  (none)" else map("  ⚠ \(.hook) — avg: \(.avg_ms|floor)ms")|join("\n") end')
DORMANT=$(echo "$REPORT"|jq -r --argjson c "$WEEK_AGO" '
  [.h[]|select(.last_ts<$c)]|
  if length==0 then "  (none)" else map("  ? \(.hook)")|join("\n") end')
cat <<EOF
═══ HOOK HEALTH SENSOR ═══
Period: last 7 days
Total executions: $TOTAL
Pass rate: ${RATE}%

BROKEN (3+ consecutive failures):
$BROKEN

SLOW (avg >100ms):
$SLOW

DORMANT (no fires in 7d):
$DORMANT

═══════════════════════════
EOF
exit 0

# ============================================================================
# ## Operationalization
# (Auto-appended on D38 wave-6 plugin promotion — lightweight default; replace
# with concrete metrics when this hook gets attention.)
#
# ### 1. Measurement mechanism
# Hook events emit to .enforcement/build-layer-ledger.jsonl or hook-specific
# log when relevant; no dedicated metric until usage observed.
# ### 2. Adoption mechanism
# Activated via plugin distribution from sutra/marketplace/plugin/hooks/.
# ### 3. Monitoring / escalation
# Surface error/anomaly rate to Asawa CEO weekly until baseline established.
# ### 4. Iteration trigger
# Tighten or loosen after 14 days of fleet observation.
# ### 5. DRI
# Asawa CEO (Sutra Forge per D31).
# ### 6. Decommission criteria
# Retire when capability supersedes via newer hook or absorbed into a
# composite gate. Currently no decommission planned.
# ============================================================================
