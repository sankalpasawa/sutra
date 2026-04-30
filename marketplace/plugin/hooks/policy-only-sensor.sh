#!/bin/bash
# D30 — Policy Ships With Mechanism (portfolio sensor)
#
# Direction:    D30 (soft; upgrade_to_hard_at: phase-3)
# Event:        Stop (session-end) + on-demand CLI
# Enforcement:  SOFT — reports findings; never exits non-zero
# Extends:      D13 cascade
#
# Scans:
#   (1) sutra/state/system.yaml directions[] where enforcement: hard.
#       For each, the mechanism field MUST name a .sh that actually exists
#       in one of the known hook directories (holding/hooks, .claude/hooks,
#       .claude/hooks/sutra). sutra/package/hooks was retired 2026-04-23
#       (archived to sutra/archive/package-v1.2.1-retired/hooks/) and is
#       no longer an active search target.
#   (2) Repo-wide grep for the literal token `POLICY-ONLY since YYYY-MM-DD`.
#       If any marker is older than window (default 604800s = 7d), flag it.
#
# Output: markdown-ish report to stdout when findings exist; silent otherwise.
# Log:    .enforcement/d30-policy-only.log (append-only audit trail)
#
# Override: D30_WINDOW=<seconds> (default 604800)
#           D30_SILENT=1 to suppress stdout (log-only)
#
# Test:    sutra/package/tests/test-d30-policy-only-sensor.sh

set -uo pipefail

# Customer-box guard: this sensor reads sutra/state/system.yaml which only
# exists on Asawa-internal repos. Silent return on customer boxes.
if [ -r "${CLAUDE_PLUGIN_ROOT:-}/lib/is_customer_box.sh" ]; then
  . "${CLAUDE_PLUGIN_ROOT}/lib/is_customer_box.sh"
  is_customer_box && exit 0
fi

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
STATE="$REPO_ROOT/sutra/state/system.yaml"
LOG_DIR="$REPO_ROOT/.enforcement"
LOG="$LOG_DIR/d30-policy-only.log"
WINDOW="${D30_WINDOW:-604800}"
NOW=$(date +%s)
mkdir -p "$LOG_DIR"

# tmp-file fallback chain: $TMPDIR → /tmp → $REPO_ROOT/.enforcement/ (writable
# last resort). Codex flagged /tmp as potentially unwritable in sandboxed
# runtime contexts (P1 2026-04-17). A silent mktemp failure would make the
# sensor invisible — unacceptable for a governance hook that ships with D30.
TMPBASE="${TMPDIR:-/tmp}"
TMP=$(mktemp "$TMPBASE/d30-findings-XXXX" 2>/dev/null \
   || mktemp "$LOG_DIR/d30-findings-XXXX" 2>/dev/null)
if [ -z "$TMP" ] || [ ! -w "$TMP" ]; then
  echo "D30 SENSOR ERROR: could not create tmp file (tried $TMPBASE, $LOG_DIR)" >&2
  exit 0  # SOFT: surface error, never block
fi
trap 'rm -f "$TMP"' EXIT

# ── Check 1: every `enforcement: hard` direction names an extant hook ────────
if [ -f "$STATE" ]; then
  REPO_ROOT="$REPO_ROOT" STATE="$STATE" python3 - >> "$TMP" <<'PY'
import os, re
root = os.environ["REPO_ROOT"]
state_path = os.environ["STATE"]
search_dirs = [
    "holding/hooks",
    ".claude/hooks",
    ".claude/hooks/sutra",
    # sutra/package/hooks retired 2026-04-23 (archived to
    # sutra/archive/package-v1.2.1-retired/hooks/). No longer searched.
]
try:
    text = open(state_path).read()
except Exception:
    raise SystemExit(0)

# Split on '    - id: DN' boundaries inside directions blocks
parts = re.split(r'(?m)^    - id: (D\d+)\n', text)
# parts = [preamble, id1, body1, id2, body2, ...]
for i in range(1, len(parts), 2):
    did = parts[i]
    body = parts[i + 1]
    # Cut body at next top-level '  <key>:' (e.g. 'retired:', 'ergonomics:')
    body = re.split(r'(?m)^  [a-z_]+:', body)[0]
    if not re.search(r'(?m)^      enforcement:\s*hard', body):
        continue
    m = re.search(r'(?m)^      mechanism:\s*(.+)', body)
    if not m:
        print(f"FAIL {did} hard direction has no mechanism field")
        continue
    mech = m.group(1).strip()
    hooks = re.findall(r'([A-Za-z0-9_\-]+\.sh)', mech)
    if not hooks:
        # Non-hook mechanism (e.g. "depth system", "agent behavior directive")
        # That is legal only for non-hook mechanisms; flag as informational.
        continue
    for h in hooks:
        found = any(os.path.exists(os.path.join(root, d, h)) for d in search_dirs)
        if not found:
            print(f"FAIL {did} mechanism references '{h}' — not found in {', '.join(search_dirs)}")
PY
fi

# ── Check 2: POLICY-ONLY markers older than window ──────────────────────────
# Pattern: "POLICY-ONLY since YYYY-MM-DD" (the canonical form this sensor watches)
grep -rnE "POLICY-ONLY[^[:digit:]]*[[:digit:]]{4}-[[:digit:]]{2}-[[:digit:]]{2}" \
  --include='*.md' --include='*.yaml' --include='*.yml' \
  --exclude-dir=.git --exclude-dir=node_modules \
  --exclude-dir=codex-reviews --exclude-dir=tmp \
  "$REPO_ROOT" 2>/dev/null | while IFS= read -r line; do
    dt=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
    [ -z "$dt" ] && continue
    # macOS vs Linux date parsing
    since=$(date -j -f "%Y-%m-%d" "$dt" "+%s" 2>/dev/null \
         || date -d "$dt" "+%s" 2>/dev/null || echo 0)
    [ "$since" = "0" ] && continue
    age=$(( NOW - since ))
    if [ "$age" -gt "$WINDOW" ]; then
      loc=$(echo "$line" | cut -d: -f1-2)
      echo "STALE $loc — POLICY-ONLY since $dt ($((age/86400))d, threshold $((WINDOW/86400))d)" >> "$TMP"
    fi
done

FINDINGS=$(wc -l < "$TMP" | tr -d ' ')
echo "$(date -u +%FT%TZ) findings=$FINDINGS window=${WINDOW}s" >> "$LOG"

if [ "$FINDINGS" -eq 0 ]; then
  exit 0  # silent green
fi

if [ "${D30_SILENT:-0}" != "1" ]; then
  echo ""
  echo "D30 SENSOR — $FINDINGS finding(s):"
  sed 's/^/  /' "$TMP"
  echo ""
  echo "  Fix: ship the missing mechanism OR mark direction 'soft' + set upgrade_to_hard_at"
  echo "  Sensor: holding/hooks/policy-only-sensor.sh  |  Log: .enforcement/d30-policy-only.log"
  echo ""
fi

# SOFT per D30 — surface but never block
exit 0

# ================================================================================
# ## Operationalization
#
# ### 1. Measurement mechanism
# Findings count in .enforcement/d30-policy-only.log (append-only). Daily tally
# surfaces in holding/ANALYTICS-PULSE.md §Enforcement. Metric: `policy_only_stale_count`
# (POLICY-ONLY markers older than D30_WINDOW seconds). Null handling: sensor silent
# when findings=0 (healthy state).
#
# ### 2. Adoption mechanism
# Registered via dispatcher-stop.sh (Stop event). CLI invocation via
# `bash holding/hooks/policy-only-sensor.sh` on demand. Propagation to companies
# deferred — currently holding-only; sutra/ plugin may vendor equivalent later.
#
# ### 3. Monitoring / escalation
# DRI reviews .enforcement/d30-policy-only.log weekly. Warn threshold: any finding
# in 7-day window. Breach: >3 stale POLICY-ONLY markers accumulated. Escalation:
# open a cascade in holding/TODO.md per D13.
#
# ### 4. Iteration trigger
# Promote to HARD enforcement when: (a) no false positives for 30 days AND
# (b) every flagged finding demonstrably got resolved. Per D30a V1 lifecycle.
#
# ### 5. DRI
# Asawa CEO (durable role). Pre-archive: Sutra Forge authoring team.
#
# ### 6. Decommission criteria
# Retire when D30 directive itself is retired OR when all enforcement is declared
# via sutra/state/system.yaml.policies[] with auto-verified mechanism pointers
# (replaces the grep-based scan with schema validation).
# ================================================================================
