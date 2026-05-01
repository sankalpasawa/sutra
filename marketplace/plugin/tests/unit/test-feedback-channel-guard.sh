#!/bin/bash
# Unit test: hooks/feedback-channel-guard.sh
#
# Regression test for v2.11.1 — SUTRA_TARGET check must operate on CMD_HEAD
# (command stripped of quoted body content), not CMD_LOWER (full command).
# Prior versions false-positive-blocked any gh issue create where the body
# contained a sankalpasawa/sutra URL — even when --repo explicitly targeted
# a different repository. v2.8.8 fixed the same drift class for the ACTION
# match but missed the TARGET match.
set -u
PLUGIN_ROOT="$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")"
HOOK="$PLUGIN_ROOT/hooks/feedback-channel-guard.sh"

PASS=0; FAIL=0
_ok() { PASS=$((PASS+1)); echo "  OK  $1"; }
_no() { FAIL=$((FAIL+1)); echo "  X   $1"; }

# Helper: run hook with a given Bash command in tool_input.command, capture exit.
_run() {
  local cmd_json="$1"
  printf '%s' "{\"tool_input\":{\"command\":$cmd_json}}" \
    | bash "$HOOK" >/dev/null 2>/tmp/fcg-test-stderr
  echo $?
}

# ── 1) v2.11.1 fix: --repo points elsewhere, body has sankalpasawa/sutra URL ─
# Must EXIT 0 (not block). Prior versions blocked.
rc=$(_run '"gh issue create --repo anthropics/claude-plugins-official --title \"foo\" --body \"see https://github.com/sankalpasawa/sutra/issues/43\""')
if [ "$rc" = "0" ]; then
  _ok "v2.11.1: foreign --repo + body URL containing sankalpasawa/sutra → exit 0"
else
  _no "v2.11.1 regression: foreign --repo with body URL incorrectly blocked (exit=$rc)"
fi

# ── 2) Real Sutra target: --repo sankalpasawa/sutra → block ─────────────────
rc=$(_run '"gh issue create --repo sankalpasawa/sutra --title \"foo\" --body \"bar\""')
if [ "$rc" = "2" ]; then
  _ok "literal Sutra --repo target blocked (exit 2)"
else
  _no "literal Sutra --repo expected exit 2, got $rc"
fi

# ── 3) Sutra-targeted gh api with mutating method → block ───────────────────
rc=$(_run '"gh api repos/sankalpasawa/sutra/issues/43/comments -X POST -f body=hi"')
if [ "$rc" = "2" ]; then
  _ok "gh api POST to sankalpasawa/sutra issues blocked"
else
  _no "gh api mutating call expected exit 2, got $rc"
fi

# ── 4) Read-only gh against Sutra → exit 0 ──────────────────────────────────
rc=$(_run '"gh issue view 43 --repo sankalpasawa/sutra"')
if [ "$rc" = "0" ]; then
  _ok "read-only gh issue view (no create/comment) → exit 0"
else
  _no "read-only gh against Sutra expected exit 0, got $rc"
fi

# ── 5) Non-gh command → exit 0 ──────────────────────────────────────────────
rc=$(_run '"echo hello world"')
if [ "$rc" = "0" ]; then _ok "non-gh command → exit 0"; else _no "non-gh expected exit 0, got $rc"; fi

# ── 6) Bypass file present → exit 0 ─────────────────────────────────────────
TMP_HOME=$(mktemp -d); trap 'rm -rf "$TMP_HOME"; rm -f /tmp/fcg-test-stderr' EXIT
touch "$TMP_HOME/.sutra-feedback-guard-disabled"
rc=$(HOME="$TMP_HOME" _run '"gh issue create --repo sankalpasawa/sutra --title \"foo\""')
if [ "$rc" = "0" ]; then
  _ok "bypass file present → exit 0 (sanctioned plugin-maintenance escape)"
else
  _no "bypass file expected exit 0, got $rc"
fi

# ── 7) Bypass env var → exit 0 ──────────────────────────────────────────────
rc=$(SUTRA_FEEDBACK_GUARD_DISABLED=1 _run '"gh issue create --repo sankalpasawa/sutra --title \"foo\""')
if [ "$rc" = "0" ]; then
  _ok "bypass env var → exit 0"
else
  _no "bypass env var expected exit 0, got $rc"
fi

# ── 8) gh pr create against Sutra → block ───────────────────────────────────
rc=$(_run '"gh pr create --repo sankalpasawa/sutra --title \"foo\" --body \"bar\""')
if [ "$rc" = "2" ]; then
  _ok "gh pr create against Sutra blocked (exit 2)"
else
  _no "gh pr create expected exit 2, got $rc"
fi

# ── 9) gh issue create against external repo with NO body URL → exit 0 ──────
rc=$(_run '"gh issue create --repo torvalds/linux --title \"foo\""')
if [ "$rc" = "0" ]; then
  _ok "gh issue create on unrelated external repo → exit 0"
else
  _no "external repo issue create expected exit 0, got $rc"
fi

TOTAL=$((PASS+FAIL))
echo ""
echo "  $PASS/$TOTAL passed"
exit "$FAIL"
