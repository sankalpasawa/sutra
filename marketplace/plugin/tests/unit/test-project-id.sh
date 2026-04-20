#!/bin/bash
# Unit test: lib/project-id.sh — install_id + project_id determinism.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
source "$PLUGIN_ROOT/lib/project-id.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# 1) install_id length == 16 hex
ID1=$(compute_install_id "1.0.0")
[ "${#ID1}" -eq 16 ] && _ok "install_id length 16" || _no "install_id length $(printf %s "$ID1" | wc -c) != 16"

# 2) install_id stable for same inputs
ID1b=$(compute_install_id "1.0.0")
[ "$ID1" = "$ID1b" ] && _ok "install_id deterministic" || _no "install_id varied: $ID1 vs $ID1b"

# 3) install_id differs per version
ID2=$(compute_install_id "2.0.0")
[ "$ID1" != "$ID2" ] && _ok "install_id version-sensitive" || _no "install_id collision across versions"

# 4) project_id length == 12
cd "$PLUGIN_ROOT"
PID=$(compute_project_id)
[ "${#PID}" -eq 12 ] && _ok "project_id length 12" || _no "project_id length $(printf %s "$PID" | wc -c) != 12"

# 5) project_id stable in same repo
PID2=$(compute_project_id)
[ "$PID" = "$PID2" ] && _ok "project_id deterministic" || _no "project_id varied"

# 6) project_id fallback (no git remote)
cd "$(mktemp -d)"
PID_FB=$(compute_project_id)
[ "${#PID_FB}" -eq 12 ] && _ok "project_id fallback length 12" || _no "fallback length wrong: $PID_FB"

echo ""
echo "test-project-id: $PASS passed, $FAIL failed"
exit $FAIL
