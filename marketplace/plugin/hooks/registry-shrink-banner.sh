#!/bin/bash
# registry-shrink-banner.sh — the department registry can only grow; say it loudly when it did not.
#
# Direction:    RCA 2026-09-11: 68 domain files were deleted and nobody noticed for
#               two hours. The engine never deletes a domain file (retire keeps it,
#               I-D5), so the count of domains/dref-*.json is monotonic by design.
#               A drop means something outside the engine removed files.
# Event:        SessionStart (banner), and `--check` for the governance audit.
# Baseline:     one file PER REGISTRY HOME: ~/.sutra-native/registry-baseline-<hash>.json
#               where <hash> = sha of realpath($SUTRA_NATIVE_HOME or default). A temp
#               registry can therefore never raise or alarm against the real one's
#               baseline (codex P3, 2026-09-11). REGISTRY_BASELINE_FILE overrides the
#               path. Grow-only: raised whenever the live count is higher. `--rebase`
#               resets it to the live count after a deliberate, founder-approved removal.
# Alert:        live < baseline - max(5, 10% of baseline)  -> ASCII box on stdout,
#               row appended to <repo>/.enforcement/registry-shrink.jsonl, exit 1 in
#               --check mode. The newest backup from pytest-isolation-guard.sh is named.
# Kill-switch:  touch ~/.registry-shrink-banner-disabled
# Test:         hooks/tests/test-registry-shrink-banner.sh

set -uo pipefail
[ -e "$HOME/.registry-shrink-banner-disabled" ] && exit 0

MODE="${1:-banner}"
REG="${SUTRA_NATIVE_HOME:-$HOME/.sutra-native/user-kit}"
[ -d "$REG/domains" ] || exit 0
REG_REAL=$(cd "$REG" 2>/dev/null && pwd -P) || exit 0
HASH=$(printf '%s' "$REG_REAL" | shasum 2>/dev/null | cut -c1-12)
BASE="${REGISTRY_BASELINE_FILE:-$HOME/.sutra-native/registry-baseline-${HASH:-default}.json}"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LEDGER="$REPO_ROOT/.enforcement/registry-shrink.jsonl"

live=$(find "$REG/domains" -maxdepth 1 -name 'dref-*.json' 2>/dev/null | wc -l | tr -d ' ')
live=${live:-0}
now=$(date +%s)

json() { # $1=count $2=ts $3=home [$4=baseline $5=backup]  -> one JSON object on stdout
  if command -v jq >/dev/null 2>&1; then
    jq -nc --argjson c "$1" --argjson t "$2" --arg h "$3" --argjson b "${4:-0}" --arg k "${5:-}" \
      '{count:$c,ts:$t,home:$h} + (if $b > 0 then {baseline:$b,live:$c,backup:$k} else {} end)'
  else
    C="$1" T="$2" H="$3" B="${4:-0}" K="${5:-}" python3 -c 'import json,os
o={"count":int(os.environ["C"]),"ts":int(os.environ["T"]),"home":os.environ["H"]}
if int(os.environ["B"])>0: o.update(baseline=int(os.environ["B"]),live=o["count"],backup=os.environ["K"])
print(json.dumps(o))'
  fi
}
write_base() { mkdir -p "$(dirname "$BASE")"; json "$1" "$now" "$REG_REAL" > "$BASE"; }
read_base() { # prints count, or 0 when absent / wrong home
  [ -f "$BASE" ] || { echo 0; return; }
  if command -v jq >/dev/null 2>&1; then
    jq -r --arg h "$REG_REAL" 'if .home == $h then (.count // 0) else 0 end' "$BASE" 2>/dev/null || echo 0
  else
    H="$REG_REAL" python3 -c 'import json,os,sys
try: o=json.load(open(sys.argv[1]))
except Exception: print(0); sys.exit()
print(o.get("count",0) if o.get("home")==os.environ["H"] else 0)' "$BASE" 2>/dev/null || echo 0
  fi
}

if [ "$MODE" = "--rebase" ]; then
  write_base "$live"; echo "[Registry] baseline for $REG_REAL rebased to $live domains"; exit 0
fi

base=$(read_base); base=${base:-0}
if [ "$base" = 0 ] || [ "$live" -gt "$base" ]; then
  write_base "$live"
  [ "$MODE" = banner ] && echo "[Registry] departments on disk: $live (baseline ${base:-0} -> $live)"
  exit 0
fi

tol=$(( base / 10 )); [ "$tol" -lt 5 ] && tol=5
if [ "$live" -lt $(( base - tol )) ]; then
  backup=$(ls -1t "$HOME/.sutra-native/backups" 2>/dev/null | grep -E '^user-kit-.*\.tgz$' | head -1)
  [ -n "$backup" ] && backup="$HOME/.sutra-native/backups/$backup"
  mkdir -p "$(dirname "$LEDGER")" 2>/dev/null
  json "$live" "$now" "$REG_REAL" "$base" "${backup:-}" >> "$LEDGER" 2>/dev/null
  cat <<EOF
+-- REGISTRY SHRANK ------------------------------------------------+
| domains/dref-*.json: baseline $base, now $live (engine never deletes)
| home:   $REG_REAL
| backup: ${backup:-none found under ~/.sutra-native/backups}
| Something outside the engine removed files. Do NOT run test suites
| against this home. Restore from the backup or the census snapshot,
| then: registry-shrink-banner.sh --rebase
+-------------------------------------------------------------------+
EOF
  [ "$MODE" = "--check" ] && exit 1
  exit 0
fi
[ "$MODE" = banner ] && echo "[Registry] departments on disk: $live (baseline $base)"
exit 0
