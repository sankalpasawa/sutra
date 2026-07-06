#!/bin/bash
# Regression test for #62 — `sutra feedback --public` usable from non-TTY.
#   --yes (or -y) confirms non-interactively (automation / Claude Code ! / pipelines);
#   the interactive read is EOF-safe (empty stdin cancels cleanly, never hangs);
#   piped 'yes' still posts, piped 'y' cancels (the `yes`-emits-"y" gotcha --yes solves).
#
# Uses a MOCK gh so no real GitHub issue is ever created.
set -u
FB="$(cd "$(dirname "$0")/../.." && pwd)/scripts/feedback.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

MB=$(mktemp -d)
cat > "$MB/gh" <<'GH'
#!/bin/bash
case "$1 $2" in
  "auth status") exit 0 ;;
  "issue create") echo "MOCK_GH_POSTED"; echo "https://github.com/mock/1"; exit 0 ;;
  *) exit 0 ;;
esac
GH
chmod +x "$MB/gh"
trap 'rm -rf "$MB"' EXIT

# Body must clear the content-quality gate (needs real prose, not a short/hi-entropy string).
BODY="descriptive feedback body about the non interactive confirm gap for issue sixty two"

# run <stdin> <args...> -> echoes combined output
run(){ local input="$1"; shift; local H; H=$(mktemp -d)
  printf '%s' "$input" | env PATH="$MB:$PATH" HOME="$H" CLAUDE_PROJECT_DIR="$H" bash "$FB" "$@" 2>&1
  rm -rf "$H"; }
posted(){ printf '%s' "$1" | grep -q "MOCK_GH_POSTED"; }

OUT=$(run "" --public --yes "$BODY")
posted "$OUT" && ok "--yes + no stdin -> posts (automation path)" || no "--yes did not post"

OUT=$(run "" --public -y "$BODY")
posted "$OUT" && ok "-y short flag -> posts" || no "-y did not post"

OUT=$(run "" --public "$BODY")
posted "$OUT" && no "no --yes + empty stdin wrongly posted" || ok "no --yes + EOF stdin -> cancels cleanly (EOF-safe)"

OUT=$(run "yes
" --public "$BODY")
posted "$OUT" && ok "no --yes + piped 'yes' -> posts (stdin read)" || no "piped 'yes' did not post"

OUT=$(run "y
" --public "$BODY")
posted "$OUT" && no "piped 'y' wrongly posted" || ok "no --yes + piped 'y' -> cancels (y != yes; why --yes exists)"

echo ""
echo "feedback-nontty-confirm: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
