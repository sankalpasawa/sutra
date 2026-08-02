#!/bin/bash
# Unit test: v2.34.0 (D53 fleet phase) Context7 banner detect + recommend.
#
# Codex P2-3 fold (consult thread 019dfd37, 2026-05-06): test 3 branches —
#   1. context7@claude-plugins-official installed → "enabled — latest …"
#   2. installed_plugins.json present, context7 absent → "recommended — claude plugin install …"
#   3. installed_plugins.json missing → "recommended — claude plugin install …" (default fallback)

set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"

WORK=$(mktemp -d)
PASS=0
FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Helper: invoke cmd_banner with HOME pointed at a temp dir + a deterministic
# project json. Capture stdout + stderr.
run_banner() {
  local fake_home="$1"
  local proj_dir="$WORK/proj-$$-$RANDOM"
  mkdir -p "$proj_dir/.claude"
  cat > "$proj_dir/.claude/sutra-project.json" <<'JSON'
{
  "install_id": "test-bcid",
  "project_id": "test-bpid",
  "project_name": "banner-context7-test",
  "first_seen": "2026-05-06T00:00:00Z",
  "sutra_version": "2.34.0",
  "telemetry_optin": false,
  "profile": "project"
}
JSON
  # cmd_banner reads PROJECT_JSON=".claude/sutra-project.json" relative to
  # cwd (lib doesn't cd; production callers cd first). Subshell so cwd
  # change doesn't leak.
  ( cd "$proj_dir" && \
    HOME="$fake_home" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$proj_dir" \
    bash "$PLUGIN_ROOT/scripts/_sutra_project_lib.sh" banner 2>&1 )
}

# ─── CASE 1: context7 installed → "enabled" line ──────────────────────
echo "── CASE 1: context7 installed → enabled line"
H1="$WORK/home-installed"
mkdir -p "$H1/.claude/plugins"
cat > "$H1/.claude/plugins/installed_plugins.json" <<'JSON'
{
  "version": 2,
  "plugins": {
    "context7@claude-plugins-official": [
      {"scope":"user","installPath":"/fake/path","version":"1.0.0","installedAt":"2026-05-06T00:00:00Z","lastUpdated":"2026-05-06T00:00:00Z"}
    ]
  }
}
JSON
OUT1=$(run_banner "$H1")
echo "$OUT1" | grep -q "Context7:" && _ok "case 1: Context7 line present" || _no "case 1: Context7 line missing"
echo "$OUT1" | grep -q "enabled — latest library/framework docs available" && _ok "case 1: 'enabled' status when installed" || _no "case 1: expected 'enabled' status; got: $(echo "$OUT1" | grep -i context7)"
echo "$OUT1" | grep -q "claude plugin install context7" && _no "case 1: install command leaked when already installed" || _ok "case 1: no install command when already installed"

# ─── CASE 2: installed_plugins.json present, context7 absent → recommend ───
echo "── CASE 2: installed_plugins.json present, context7 absent → recommend"
H2="$WORK/home-absent"
mkdir -p "$H2/.claude/plugins"
cat > "$H2/.claude/plugins/installed_plugins.json" <<'JSON'
{
  "version": 2,
  "plugins": {
    "some-other-plugin@some-marketplace": [
      {"scope":"user","installPath":"/fake","version":"0.1","installedAt":"2026-05-06T00:00:00Z","lastUpdated":"2026-05-06T00:00:00Z"}
    ]
  }
}
JSON
OUT2=$(run_banner "$H2")
echo "$OUT2" | grep -q "Context7:" && _ok "case 2: Context7 line present" || _no "case 2: Context7 line missing"
echo "$OUT2" | grep -q "recommended — claude plugin install context7@claude-plugins-official" && _ok "case 2: 'recommended' + install command when absent" || _no "case 2: expected 'recommended' line; got: $(echo "$OUT2" | grep -i context7)"
echo "$OUT2" | grep -q "enabled — latest" && _no "case 2: leaked 'enabled' when not installed" || _ok "case 2: no 'enabled' status when not installed"

# ─── CASE 3: installed_plugins.json missing → recommend (default fallback) ───
echo "── CASE 3: registry missing → recommend (default fallback)"
H3="$WORK/home-no-registry"
mkdir -p "$H3/.claude"  # no plugins/ dir at all
OUT3=$(run_banner "$H3")
echo "$OUT3" | grep -q "Context7:" && _ok "case 3: Context7 line present" || _no "case 3: Context7 line missing"
echo "$OUT3" | grep -q "recommended — claude plugin install context7@claude-plugins-official" && _ok "case 3: 'recommended' default when registry missing" || _no "case 3: expected 'recommended' default; got: $(echo "$OUT3" | grep -i context7)"

# ─── CASE 4: project-scope-only entry → recommended (codex P2-1 fold) ───
echo "── CASE 4: context7 at project scope only → recommended"
H4="$WORK/home-project-scope"
mkdir -p "$H4/.claude/plugins"
cat > "$H4/.claude/plugins/installed_plugins.json" <<'JSON'
{
  "version": 2,
  "plugins": {
    "context7@claude-plugins-official": [
      {"scope":"project","projectPath":"/some/project","installPath":"/fake","version":"1.0.0","installedAt":"2026-05-06T00:00:00Z","lastUpdated":"2026-05-06T00:00:00Z"}
    ]
  }
}
JSON
OUT4=$(run_banner "$H4")
echo "$OUT4" | grep -q "recommended — claude plugin install context7@claude-plugins-official" && _ok "case 4: project-scope-only stays 'recommended' (user-scope check)" || _no "case 4: project-scope incorrectly elevated to 'enabled'; got: $(echo "$OUT4" | grep -i context7)"

# ─── CASE 5: go.sh banner duplication (codex P2-2 fold) ───────────────
echo "── CASE 5: go.sh banner also surfaces Context7"
H5="$WORK/home-go"
mkdir -p "$H5/.claude/plugins"
cat > "$H5/.claude/plugins/installed_plugins.json" <<'JSON'
{
  "version": 2,
  "plugins": {
    "context7@claude-plugins-official": [
      {"scope":"user","installPath":"/fake","version":"1.0.0","installedAt":"2026-05-06T00:00:00Z","lastUpdated":"2026-05-06T00:00:00Z"}
    ]
  }
}
JSON
proj5="$WORK/proj-go"
mkdir -p "$proj5/.claude"
# Pre-seed sutra-project.json so go.sh skips full onboard side effects
cat > "$proj5/.claude/sutra-project.json" <<'JSON'
{
  "install_id": "go-test",
  "project_id": "go-test",
  "project_name": "go-banner-test",
  "first_seen": "2026-05-06T00:00:00Z",
  "sutra_version": "2.34.0",
  "telemetry_optin": true,
  "consent_version": "2.33"
}
JSON
# go.sh banner runs after onboard + jq-toggle; capture its output. SUTRA_HOME
# isolated so push.sh would not actually hit the network.
OUT5=$( cd "$proj5" && \
  HOME="$H5" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" CLAUDE_PROJECT_DIR="$proj5" \
  SUTRA_HOME="$proj5/.sutra" SUTRA_AUTO_OPTIN=1 \
  bash "$PLUGIN_ROOT/scripts/go.sh" 2>&1 )
echo "$OUT5" | grep -q "Context7:" && _ok "case 5: go.sh banner shows Context7 line" || _no "case 5: go.sh missing Context7; out: $OUT5"
echo "$OUT5" | grep -q "enabled — latest library/framework docs available" && _ok "case 5: go.sh 'enabled' status with user-scope install" || _no "case 5: wrong status; out: $(echo "$OUT5" | grep -i context7)"

# ─── Cleanup + report ─────────────────────────────────────────────────
rm -rf "$WORK"
echo ""
echo "test-banner-context7: $PASS passed, $FAIL failed"
exit "$FAIL"
