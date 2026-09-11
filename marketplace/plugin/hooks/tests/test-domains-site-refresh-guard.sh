#!/usr/bin/env bash
# Regression test for marketplace/plugin/hooks/domains-site-refresh.sh — the never-shrink guard (2.263.1).
# PROTO-000: mechanism ships with test.  BUILD-LAYER: L0.
# Usage: bash marketplace/plugin/hooks/tests/test-domains-site-refresh-guard.sh
# Isolation: per-case mktemp repo (CLAUDE_PROJECT_DIR), registry (SUTRA_NATIVE_HOME) and a STUB
# generator under CLAUDE_PLUGIN_ROOT/lib/domains_page.py — the real generator is never invoked,
# so the cases pin the HOOK's contract, not the renderer's. trap cleanup.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/domains-site-refresh.sh"
FAIL=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }
TMPROOT=$(mktemp -d -t domains-guard-test.XXXXXX)
cleanup() { [ -n "${TMPROOT:-}" ] && [ -d "$TMPROOT" ] && rm -rf "$TMPROOT"; }
trap cleanup EXIT

# The stub honours both hook modes: OUT --export-registry --tenant T  and  OUT --site --label X --tenant T.
# STUB_PAGES (env) = space-separated basenames the --site mode emits.
write_stub() {
  local root="$1"
  mkdir -p "$root/lib"
  cat > "$root/lib/domains_page.py" <<'PY'
import os, sys
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
if "--export-registry" in sys.argv:
    open(os.path.join(out, "registry.json"), "w").write('{"stub": true}\n')
    sys.exit(0)
for name in os.environ.get("STUB_PAGES", "").split():
    open(os.path.join(out, name), "w").write("<html>%s</html>\n" % name)
open(os.path.join(out, "index.html"), "w").write("<html>index</html>\n")
PY
}

# One case = one repo + one registry + one stub. Returns the case dir.
make_case() {
  local name="$1" kit_rows="$2"
  local c="$TMPROOT/$name"
  mkdir -p "$c/repo/site" "$c/repo/.claude" "$c/kit/domains" "$c/kit/charters" "$c/plugin"
  git init -q --bare "$c/remote.git"
  ( cd "$c/repo" && git init -q && git config user.name test && git config user.email test@example.com \
      && git remote add origin "$c/remote.git" )
  printf 'SITE_DIR=site\nLABEL=Departments\nTENANT=T-local\n' > "$c/repo/.claude/domains-autopublish"
  printf '<html>a</html>\n' > "$c/repo/site/dref-a.html"
  printf '<html>b</html>\n' > "$c/repo/site/dref-b.html"
  printf '<html>c</html>\n' > "$c/repo/site/C-1.html"
  printf 'old-stamp\n' > "$c/repo/site/.registry-stamp"
  local i=0
  : > "$c/kit/domains/INDEX.jsonl"
  while [ "$i" -lt "$kit_rows" ]; do
    printf '{"event":"domain_minted","ref":"dref-%s","name":"d%s","tenant_id":"T-local"}\n' "$i" "$i" >> "$c/kit/domains/INDEX.jsonl"
    printf '{"ref":"dref-%s","name":"d%s"}\n' "$i" "$i" > "$c/kit/domains/dref-$i.json"
    i=$((i + 1))
  done
  printf '{"id":"C-1"}\n' > "$c/kit/charters/C-1.json"
  write_stub "$c/plugin"
  ( cd "$c/repo" && git add -A && git commit -q -m seed )
  printf '%s' "$c"
}

run_hook() {
  local c="$1"
  ( cd "$c/repo" && CLAUDE_PROJECT_DIR="$c/repo" SUTRA_NATIVE_HOME="$c/kit" CLAUDE_PLUGIN_ROOT="$c/plugin" \
      STUB_PAGES="${STUB_PAGES:-}" GIT_TERMINAL_PROMPT=0 bash "$HOOK" </dev/null >/dev/null 2>&1 )
  return $?
}
site_sum() { ( cd "$1/repo/site" && cat dref-a.html dref-b.html C-1.html .registry-stamp | shasum -a 256 | cut -d' ' -f1 ); }
commits() { ( cd "$1/repo" && git rev-list --count HEAD ); }

echo "=== Case 1: registry smaller than the published site -> refused before both lanes ==="
c=$(make_case one 1); before=$(site_sum "$c"); n0=$(commits "$c")
STUB_PAGES="dref-a.html dref-b.html C-1.html" run_hook "$c"; rc=$?
[ "$rc" -eq 0 ] && pass "hook exits 0" || fail "hook exit $rc (must never block a turn)"
[ "$(site_sum "$c")" = "$before" ] && pass "published pages + stamp byte-unchanged" || fail "site changed"
[ ! -f "$c/repo/site/registry.json" ] && pass "fast lane skipped (no registry.json)" || fail "fast lane ran"
[ ! -f "$c/repo/.claude/domains-refresh-last" ] && [ ! -f "$c/repo/.claude/domains-fastlane-last" ] \
  && pass "no refresh/fastlane stamps written" || fail "a stamp was written"
grep -q "registry has 1 domain rows but the published site has 2" "$c/repo/.claude/domains-refresh.err" 2>/dev/null \
  && pass "err names the count mismatch" || fail "err missing or wrong: $(cat "$c/repo/.claude/domains-refresh.err" 2>/dev/null)"
[ "$(commits "$c")" = "$n0" ] && pass "no commit" || fail "a commit was made"

echo "=== Case 2: registry big enough but the regen would drop a published page -> refused ==="
c=$(make_case two 3); before=$(site_sum "$c"); n0=$(commits "$c")
STUB_PAGES="dref-a.html C-1.html" run_hook "$c"; rc=$?
[ "$rc" -eq 0 ] && pass "hook exits 0" || fail "hook exit $rc"
[ "$(site_sum "$c")" = "$before" ] && pass "published pages + stamp byte-unchanged" || fail "site changed"
grep -q "would drop 1 published page(s): dref-b.html" "$c/repo/.claude/domains-refresh.err" 2>/dev/null \
  && pass "err names the missing basename" || fail "err missing or wrong: $(cat "$c/repo/.claude/domains-refresh.err" 2>/dev/null)"
[ ! -f "$c/repo/.claude/domains-refresh-last" ] && pass "no refresh stamp" || fail "refresh stamp written"
[ "$(commits "$c")" = "$n0" ] && pass "no full-regen commit (fast lane may commit registry.json only)" \
  || { ( cd "$c/repo" && git log -1 --format=%s | grep -q "fast-lane" ) && pass "only the fast-lane commit exists" || fail "a full-regen commit was made"; }

echo "=== Case 3: regen keeps every published page (superset) -> published, stamp == FP, HEAD +1 ==="
c=$(make_case three 3); n0=$(commits "$c")
STUB_PAGES="dref-a.html dref-b.html dref-new.html C-1.html" run_hook "$c"; rc=$?
[ "$rc" -eq 0 ] && pass "hook exits 0" || fail "hook exit $rc"
[ -f "$c/repo/site/dref-new.html" ] && pass "new page published" || fail "new page missing"
[ -f "$c/repo/site/dref-b.html" ] && [ -f "$c/repo/site/C-1.html" ] && pass "existing pages preserved (overlay, no delete)" || fail "a page vanished"
FP=$( { cat "$c/kit/domains/INDEX.jsonl" "$c"/kit/domains/*.json "$c"/kit/charters/*.json ; } | shasum -a 256 | cut -d' ' -f1)
[ "$(cat "$c/repo/site/.registry-stamp")" = "$FP" ] && pass "stamp equals the registry fingerprint" || fail "stamp != FP"
[ -f "$c/repo/.claude/domains-refresh-last" ] && pass "refresh stamp written" || fail "no refresh stamp"
( cd "$c/repo" && git log -1 --format=%s | grep -q "auto-refresh from registry drift" ) && pass "auto-refresh commit is HEAD" || fail "HEAD is not the auto-refresh commit"
[ ! -s "$c/repo/.claude/domains-refresh.err" ] && pass "err cleared on success" || fail "err not cleared: $(cat "$c/repo/.claude/domains-refresh.err")"

echo
[ "$FAIL" -eq 0 ] && { echo "ALL PASS"; exit 0; } || { echo "FAILURES"; exit 1; }
