#!/bin/bash
# Unit test: hooks/cascade-check.sh
#
# Regression test for v2.10.1 — block diagnostics MUST go to stderr so Claude
# Code's PostToolUse hook protocol can surface them. Prior versions echoed to
# stdout, leaving callers with the cryptic "No stderr output" wrapper message.
#
# Also covers the v2.10.1 whitelist alignment (CLAUDE.md "no advisory, no
# block" tracking artifacts: research/state/checkpoints/.enforcement/.analytics
# /.claude/sutra/archive). These paths must exit 0 silently — they are not
# governance-policy changes that demand cascade TODOs.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
HOOK="$PLUGIN_ROOT/hooks/cascade-check.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Helper: invoke hook with a fake JSON payload, capture stdout + stderr + exit.
_invoke() {
  local file_path="$1"
  printf '%s' "{\"tool_input\":{\"file_path\":\"$file_path\"}}" \
    | bash "$HOOK" 1>/tmp/cc-test-stdout 2>/tmp/cc-test-stderr
  echo $?
}

# ── 1) Whitelisted paths exit 0 silently ─────────────────────────────────────
for p in \
  "/repo/holding/research/2026-04-22-foo.md" \
  "/repo/holding/state/system.yaml" \
  "/repo/holding/checkpoints/2026-05-01.json" \
  "/repo/holding/hooks/hook-log.jsonl" \
  "/repo/.enforcement/routing-misses.log" \
  "/repo/.analytics/metrics.jsonl" \
  "/repo/.claude/depth-registered" \
  "/repo/sutra/archive/old-charter.md" \
  "/repo/holding/TODO.md" \
  "/repo/dayflow/BACKLOG.md"
do
  rc=$(_invoke "$p")
  size_out=$(wc -c < /tmp/cc-test-stdout | tr -d ' ')
  size_err=$(wc -c < /tmp/cc-test-stderr | tr -d ' ')
  if [ "$rc" = "0" ] && [ "$size_out" -eq 0 ] && [ "$size_err" -eq 0 ]; then
    _ok "whitelist exit 0 silent: $(basename "$p" | head -c 32)"
  else
    _no "whitelist not-silent (rc=$rc, stdout=$size_out, stderr=$size_err): $p"
  fi
done

# ── 2) Non-whitelisted holding/ path → BLOCK with stderr-only diagnostic ─────
rc=$(_invoke "/repo/holding/SYSTEM-MAP.md")
out_size=$(wc -c < /tmp/cc-test-stdout | tr -d ' ')
err_text=$(cat /tmp/cc-test-stderr)
if [ "$rc" = "2" ]; then _ok "blocked path exits 2"; else _no "blocked path expected exit 2, got $rc"; fi
if [ "$out_size" -eq 0 ]; then _ok "blocked path stdout is empty"; else _no "blocked path leaked $out_size bytes to stdout"; fi
if echo "$err_text" | grep -q "BLOCKED — D13 cascade gate"; then
  _ok "blocked path stderr contains BLOCKED header"
else
  _no "blocked path stderr missing BLOCKED header"
fi
if echo "$err_text" | grep -q "CASCADE_ACK"; then
  _ok "blocked path stderr contains override hint"
else
  _no "blocked path stderr missing override hint"
fi

# ── 3) Non-whitelisted holding/ path with CASCADE_ACK → exit 0 on stdout ─────
TMP_REPO=$(mktemp -d); trap 'rm -rf "$TMP_REPO"' EXIT
mkdir -p "$TMP_REPO/.enforcement"
rc=$(CASCADE_ACK=1 CASCADE_ACK_REASON="test override 12345" CLAUDE_PROJECT_DIR="$TMP_REPO" \
  bash -c "printf '%s' '{\"tool_input\":{\"file_path\":\"$TMP_REPO/holding/governance/PRINCIPLES.md\"}}' | bash $HOOK 1>/tmp/cc-test-stdout 2>/tmp/cc-test-stderr; echo \$?")
if [ "$rc" = "0" ]; then
  _ok "CASCADE_ACK override → exit 0"
else
  _no "CASCADE_ACK override expected exit 0, got $rc"
fi

# ── 4) No file_path → exit 0 silently (defensive) ────────────────────────────
rc=$(printf '%s' '{}' | bash "$HOOK" 1>/tmp/cc-test-stdout 2>/tmp/cc-test-stderr; echo $?)
sz_o=$(wc -c </tmp/cc-test-stdout | tr -d ' '); sz_e=$(wc -c </tmp/cc-test-stderr | tr -d ' ')
if [ "$rc" = "0" ] && [ "$sz_o" -eq 0 ] && [ "$sz_e" -eq 0 ]; then
  _ok "no file_path → exit 0 silent"
else
  _no "no file_path expected exit 0 silent, got rc=$rc stdout=$sz_o stderr=$sz_e"
fi

# ── 5) Path outside holding/ + sutra/layer2-operating-system/ → exit 0 ───────
rc=$(_invoke "/repo/dayflow/src/login.tsx")
sz_o=$(wc -c </tmp/cc-test-stdout | tr -d ' '); sz_e=$(wc -c </tmp/cc-test-stderr | tr -d ' ')
if [ "$rc" = "0" ] && [ "$sz_o" -eq 0 ] && [ "$sz_e" -eq 0 ]; then
  _ok "non-governance path → exit 0 silent"
else
  _no "non-governance path expected exit 0 silent, got rc=$rc stdout=$sz_o stderr=$sz_e"
fi

rm -f /tmp/cc-test-stdout /tmp/cc-test-stderr

TOTAL=$((PASS+FAIL))
echo ""
echo "  $PASS/$TOTAL passed"
exit "$FAIL"
