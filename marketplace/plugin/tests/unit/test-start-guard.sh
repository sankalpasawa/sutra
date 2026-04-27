#!/bin/bash
# Unit test: scripts/start.sh project-root guard (v2.1.1).
#
# Regression test for fleet-reported bug (2026-04-25): running /core:start from
# $HOME wrote governance into ~/.claude/CLAUDE.md and recorded project_name as
# the OS username. start.sh must refuse to activate in home/non-project dirs
# unless --force is passed. Idempotent re-runs on an initialized project are
# always allowed.
#
# Cases 7-8 cover codex-review findings:
#   P1 — .git-as-file (worktrees/submodules) must count as project marker
#   P2 — symlinks to $HOME must not bypass the guard (canonical path compare)
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
START="$PLUGIN_ROOT/scripts/start.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

TMPROOT=$(mktemp -d)
trap 'rm -rf "$TMPROOT"' EXIT

# --- 1) refuses when PROJECT_ROOT is exactly $HOME ---
FAKE_HOME="$TMPROOT/home"
mkdir -p "$FAKE_HOME"
OUT=$(cd "$FAKE_HOME" && HOME="$FAKE_HOME" CLAUDE_PROJECT_DIR="$FAKE_HOME" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 2 ] && echo "$OUT" | grep -q "refusing to activate"; then
  _ok "refuses when PROJECT_ROOT == \$HOME (exit 2 with message)"
else
  _no "expected exit 2 + refusal message when PROJECT_ROOT == \$HOME, got rc=$RC"
fi
if [ ! -f "$FAKE_HOME/.claude/sutra-project.json" ]; then
  _ok "did not write sutra-project.json when refusing"
else
  _no "wrote sutra-project.json despite refusal (home-dir poisoning)"
fi
if [ ! -f "$FAKE_HOME/.claude/CLAUDE.md" ]; then
  _ok "did not write CLAUDE.md when refusing"
else
  _no "wrote CLAUDE.md despite refusal (governance poisoning)"
fi

# --- 2) refuses in arbitrary non-project dir (no project markers) ---
NOPROJ="$TMPROOT/not-a-project"
mkdir -p "$NOPROJ"
OUT=$(cd "$NOPROJ" && HOME="$TMPROOT/home" CLAUDE_PROJECT_DIR="$NOPROJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 2 ] && echo "$OUT" | grep -q "refusing to activate"; then
  _ok "refuses in non-project dir (no .git / package.json / pyproject.toml / etc)"
else
  _no "expected exit 2 in non-project dir, got rc=$RC"
fi

# --- 3) --force bypasses the guard ---
FORCED="$TMPROOT/forced"
mkdir -p "$FORCED"
OUT=$(cd "$FORCED" && HOME="$TMPROOT/home" CLAUDE_PROJECT_DIR="$FORCED" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" --force 2>&1)
RC=$?
if [ "$RC" -eq 0 ] || [ -f "$FORCED/.claude/sutra-project.json" ]; then
  _ok "--force bypasses guard (activation proceeds)"
else
  _no "--force did not bypass guard, rc=$RC"
fi

# --- 4) proceeds when .git/ exists (real project) ---
GITPROJ="$TMPROOT/git-proj"
mkdir -p "$GITPROJ/.git"
OUT=$(cd "$GITPROJ" && HOME="$TMPROOT/home" CLAUDE_PROJECT_DIR="$GITPROJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$GITPROJ/.claude/sutra-project.json" ]; then
  _ok "proceeds in dir with .git/ (real project)"
else
  _no "expected success in git project, got rc=$RC"
fi

# --- 5) proceeds when package.json exists (node project) ---
NODEPROJ="$TMPROOT/node-proj"
mkdir -p "$NODEPROJ"
echo '{}' > "$NODEPROJ/package.json"
OUT=$(cd "$NODEPROJ" && HOME="$TMPROOT/home" CLAUDE_PROJECT_DIR="$NODEPROJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$NODEPROJ/.claude/sutra-project.json" ]; then
  _ok "proceeds in dir with package.json (node project)"
else
  _no "expected success in node project, got rc=$RC"
fi

# --- 6) idempotent: proceeds on re-run even in $HOME if already initialized ---
REINIT="$TMPROOT/reinit-home"
mkdir -p "$REINIT/.claude"
cat > "$REINIT/.claude/sutra-project.json" <<EOF
{"install_id":"x","project_id":"y","project_name":"reinit","sutra_version":"2.1.0","telemetry_optin":true,"first_seen":"2026-04-25T00:00:00Z"}
EOF
OUT=$(cd "$REINIT" && HOME="$REINIT" CLAUDE_PROJECT_DIR="$REINIT" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 0 ]; then
  _ok "idempotent re-run on initialized project succeeds even if PROJECT_ROOT == \$HOME"
else
  _no "re-run on initialized project failed, rc=$RC"
fi

# --- 7) .git-as-file (worktree/submodule) counts as project marker ---
# Codex P1 regression: original -d .git check missed worktrees where .git is a FILE.
WTPROJ="$TMPROOT/worktree-proj"
mkdir -p "$WTPROJ"
echo "gitdir: /tmp/fake-gitdir" > "$WTPROJ/.git"
OUT=$(cd "$WTPROJ" && HOME="$TMPROOT/home" CLAUDE_PROJECT_DIR="$WTPROJ" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 0 ] && [ -f "$WTPROJ/.claude/sutra-project.json" ]; then
  _ok "proceeds when .git is a FILE (worktree/submodule pointer)"
else
  _no ".git-as-file not recognized — worktrees/submodules refused, rc=$RC"
fi

# --- 8) symlink to $HOME still refused (canonical path comparison) ---
# Codex P2 regression: raw string compare bypassable via $HOME symlink tricks.
FAKE_HOME2="$TMPROOT/home2"
mkdir -p "$FAKE_HOME2"
SYMLINKED="$TMPROOT/home-symlink"
ln -s "$FAKE_HOME2" "$SYMLINKED"
OUT=$(cd "$SYMLINKED" && HOME="$FAKE_HOME2" CLAUDE_PROJECT_DIR="$SYMLINKED" CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" bash "$START" 2>&1)
RC=$?
if [ "$RC" -eq 2 ] && echo "$OUT" | grep -q "refusing to activate"; then
  _ok "refuses when PROJECT_ROOT is a symlink resolving to \$HOME"
else
  _no "symlink-to-\$HOME bypass still works, rc=$RC"
fi

echo ""
echo "  $PASS passed, $FAIL failed"
exit "$FAIL"
