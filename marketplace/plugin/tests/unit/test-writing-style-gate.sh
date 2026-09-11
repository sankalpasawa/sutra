#!/bin/bash
# Unit test: hooks/writing-style-gate.sh — the HARD Stop floor for core:writing-style.
#
# Builds a synthetic repo (.claude/sutra-project.json + transcript) and feeds a Stop
# payload. Asserts block vs pass on stdout, ledger rows, guards, revoke scopes, audience
# downgrade, self-compliance (skill text + block reason never trip the gate), the
# deterministic revoke matcher in per-turn-discipline-prompt.sh, and mode bits.

set -u
PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
GATE="$PLUGIN/hooks/writing-style-gate.sh"
PROMPT_HOOK="$PLUGIN/hooks/per-turn-discipline-prompt.sh"
SKILL="$PLUGIN/skills/writing-style/SKILL.md"
DEFAULTS="$PLUGIN/sutra-defaults.json"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }

command -v jq >/dev/null 2>&1      || { echo "SKIP: jq not installed"; exit 0; }
command -v python3 >/dev/null 2>&1 || { echo "SKIP: python3 not installed"; exit 0; }

# make_env <project_name> <user_text> <assistant_text...> -> temp dir (each extra arg = one text block)
make_env(){
  local proj="$1" user="$2"; shift 2
  local D; D=$(mktemp -d)
  mkdir -p "$D/.claude/sessions/t1" "$D/.enforcement"
  printf '{"project_id":"test","project_name":"%s"}\n' "$proj" > "$D/.claude/sutra-project.json"
  {
    python3 -c 'import json,sys; print(json.dumps({"type":"user","message":{"role":"user","content":sys.argv[1]}}))' "$user"
    for t in "$@"; do
      python3 -c 'import json,sys; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":sys.argv[1]}]}}))' "$t"
    done
  } > "$D/transcript.jsonl"
  echo "$D"
}
# run <dir> [active] -> OUT (stdout), RC
OUT=""; RC=0
run(){
  local D="$1" active="${2:-false}"
  OUT=$(printf '{"session_id":"t1","transcript_path":"%s","stop_hook_active":%s}' "$D/transcript.jsonl" "$active" \
    | CLAUDE_PROJECT_DIR="$D" CLAUDE_PLUGIN_ROOT="$PLUGIN" WRITING_STYLE_SKILL="$SKILL" WRITING_STYLE_DEFAULTS="$DEFAULTS" \
      HOME="$D" bash "$GATE" 2>/dev/null); RC=$?
}
blocked(){ printf '%s' "$OUT" | grep -q '"decision": *"block"'; }
last_row(){ tail -1 "$1/.enforcement/writing-style.jsonl" 2>/dev/null; }

CLEAN='Bug in auth middleware: token expiry check uses `<` not `<=`. Fix applied in src/auth.py. Confidence: high.'

echo "=== WS-1 banned phrases: used vs quoted ==="
D=$(make_env other "fix the bug" "Great question! The bug is in auth."); run "$D"
blocked && ok "glaze phrase in prose -> block" || no "expected block: $OUT"
printf '%s' "$OUT" | grep -q 'GLAZE' && ok "block reason names the group" || no "reason lacks group"
rm -rf "$D"
D=$(make_env other "fix the bug" 'The gate bans `great question` in prose.'); run "$D"
blocked && no "backticked phrase blocked (false positive)" || ok "backticked phrase -> pass"; rm -rf "$D"
D=$(make_env other "fix the bug" 'The banned list includes "great question" and "hope this helps".'); run "$D"
blocked && no "double-quoted phrase blocked (false positive)" || ok "double-quoted phrase -> pass"; rm -rf "$D"
D=$(make_env other "fix the bug" "$CLEAN

In summary, the fix is small."); run "$D"
blocked && ok "trailing summary opener -> block" || no "expected block on SUMMARY"; rm -rf "$D"
D=$(make_env other "fix the bug" "$CLEAN Hope this helps!"); run "$D"
blocked && ok "filler closer -> block" || no "expected block on CLOSER"; rm -rf "$D"

echo "=== NARRATE judged on the final block only ==="
D=$(make_env other "fix the bug" "Let me read the file." "$CLEAN"); run "$D"
blocked && no "mid-turn progress line blocked" || ok "narration in a non-final block -> pass"; rm -rf "$D"
D=$(make_env other "fix the bug" "$CLEAN" "Let me now explain the fix."); run "$D"
blocked && ok "narration in the final block -> block" || no "expected block on NARRATE"; rm -rf "$D"

echo "=== WS-2 glyphs ==="
D=$(make_env other "show the tree" "Layout: ┌──┐ box here."); run "$D"
blocked && ok "box-drawing glyph in prose -> block" || no "expected block on GLYPH"; rm -rf "$D"
D=$(make_env other "show the tree" "Layout:
\`\`\`text
┌──┐
└──┘
\`\`\`
Done."); run "$D"
blocked && no "fenced glyph blocked (false positive)" || ok "fenced glyph -> pass"; rm -rf "$D"
D=$(make_env other "score" "Name ▓▓▓▓▓▓░░░░ 0.6 GREEN"); run "$D"
blocked && ok "block-element bar in prose -> block (ASCII only)" || no "expected block on bar glyph"; rm -rf "$D"

echo "=== WS-3 budget ==="
LONG61=$(python3 -c 'print("\n".join("line %d of prose that says something" % i for i in range(61)))')
LONG45=$(python3 -c 'print("\n".join("line %d of prose that says something" % i for i in range(45)))')
D=$(make_env other "report" "$LONG61"); run "$D"
blocked && ok "61 prose lines -> block" || no "expected block on BUDGET"; rm -rf "$D"
D=$(make_env other "report" "$LONG45"); run "$D"
blocked && no "45 lines blocked" || ok "45 prose lines -> pass"
last_row "$D" | grep -q 'WS-A1' && ok "45 lines -> advisory ledger row" || no "no WS-A1 row: $(last_row "$D")"; rm -rf "$D"
GOV='[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]
INPUT: fix the bug
TYPE: task
+-- FLOW ----------------------------------------------------------+
| Unit: let me fix the bug                                          |
| [1] TYPE: task                                                    |
+------------------------------------------------------------------+
TASK: "fix"
DEPTH: 2/5
'"$LONG45"
D=$(make_env other "fix" "$GOV"); run "$D"
blocked && no "governance blocks counted or judged" || ok "governance header/fields/box stripped -> pass"; rm -rf "$D"

echo "=== WS-4 task tables ==="
TT='| # | Task | Owner |
|---|---|---|
| 1 | fix a | me |
| 2 | fix b | me |
| 3 | fix c | me |'
D=$(make_env other "plan" "$TT"); run "$D"
blocked && ok "task table without Impact/Effort -> block" || no "expected block on TASK-TABLE"; rm -rf "$D"
TT2='| # | Area/Task | Impact (who/what changes) | Effort (time, files) |
|---|---|---|---|
| 1 | fix a | users | 1h |
| 2 | fix b | ops | 2h |
| 3 | fix c | me | 3h |'
D=$(make_env other "plan" "$TT2"); run "$D"
blocked && no "compliant task table blocked" || ok "task table with Impact + Effort -> pass"; rm -rf "$D"
TT3='| Item | Status | Owner |
|---|---|---|
| a | done | me |
| b | done | me |
| c | open | me |'
D=$(make_env other "status" "$TT3"); run "$D"
blocked && no "inventory table blocked" || ok "generic-header table -> pass"; rm -rf "$D"

echo "=== WS-5 ask-to-run: pinned vs fleet ==="
D=$(make_env asawa-holding "deploy" "Please run npm test on your side."); run "$D"
blocked && ok "ask-to-run in pinned project -> block" || no "expected block in pinned project"; rm -rf "$D"
D=$(make_env other "deploy" "Please run npm test on your side."); run "$D"
blocked && no "ask-to-run blocked outside pinned" || ok "ask-to-run in fleet project -> advisory"; rm -rf "$D"

echo "=== 2026-09-11 folds: phrasing variants ==="
for t in "You'll need to run the migration yourself." "Run this on your end and paste the output."; do
  D=$(make_env asawa-holding "deploy" "$t"); run "$D"
  blocked && ok "ask-to-run variant -> block: $t" || no "expected block: $t"; rm -rf "$D"
done
for t in "$CLEAN Feel free to reach out." "$CLEAN If you have any questions, ping me." "$CLEAN Good luck with the rollout." "TL;DR: the fix is small." "In short, done." "Good point. The fix is small." "Spot on. Applied." "Sorry about that, fixed." "Understood. Applied." "Next, I'll explain the fix."; do
  D=$(make_env other "fix the bug" "$t"); run "$D"
  blocked && ok "variant -> block: $t" || no "expected block: $t"; rm -rf "$D"
done
for t in "The if you have any questions branch is dead code." "The command prints good luck with no newline." "I love this approach because it is O(1)." "Overall, the complexity is O(n log n)."; do
  D=$(make_env other "fix the bug" "$t"); run "$D"
  blocked && no "technical prose blocked (false positive): $t" || ok "technical prose -> pass: $t"; rm -rf "$D"
done

echo "=== 2026-09-11 folds: counting ==="
Q61=$(python3 -c 'print("\n".join("\"quoted line %d of prose\"" % i for i in range(61)))')
D=$(make_env other "report" "$Q61"); run "$D"
blocked && ok "61 fully quoted lines still count -> block" || no "quoted lines uncounted"; rm -rf "$D"
DASH61=$(python3 -c 'print("\n".join("-- note %d of prose that says something" % i for i in range(61)))')
D=$(make_env other "report" "$DASH61"); run "$D"
blocked && ok "61 dash-prefixed prose lines count -> block" || no "dash lines uncounted"; rm -rf "$D"
LBL61=$(python3 -c 'print("\n".join("OS: " + ("padded field %d " % i) * 12 for i in range(61)))')
D=$(make_env other "report" "$LBL61"); run "$D"
blocked && ok "61 over-long label lines count -> block" || no "label padding uncounted"; rm -rf "$D"
LBL30=$(python3 -c 'print("\n".join("OS: field %d" % i for i in range(30)))')
D=$(make_env other "report" "$LBL30"); run "$D"
last_row "$D" | grep -q '"lines":0' && ok "30 one-line fields are not counted" || no "fields counted: $(last_row "$D")"; rm -rf "$D"
LBL110=$(python3 -c 'print("\n".join("OS: field %d" % i for i in range(110)))')
D=$(make_env other "report" "$LBL110"); run "$D"
blocked && ok "110 one-line fields: the 65 past the 45th count -> block" || no "field flood uncounted"; rm -rf "$D"
D=$(make_env other "fix" "Scale: great question, 2 files"); run "$D"
blocked && ok "phrase inside a field value -> block" || no "field value not judged"; rm -rf "$D"
D=$(make_env other "fix" "INPUT: you're absolutely right about that"); run "$D"
blocked && no "INPUT paraphrase judged" || ok "INPUT field never judged -> pass"; rm -rf "$D"

echo "=== 2026-09-11 folds: glyph ranges ==="
D=$(make_env other "list" "■ first item, ● second"); run "$D"
blocked && ok "geometric glyph in prose -> block" || no "geometric glyph passed"; rm -rf "$D"
D=$(make_env other "list" "Progress ⣿⣿⣿⡀ 0.7"); run "$D"
blocked && ok "braille glyph in prose -> block" || no "braille glyph passed"; rm -rf "$D"

echo "=== 2026-09-11 folds: pipe-less GFM table ==="
TT4='# | Task | Owner
--|--|--
1 | fix a | me
2 | fix b | me
3 | fix c | me'
D=$(make_env other "plan" "$TT4"); run "$D"
blocked && ok "pipe-less task table without Impact/Effort -> block" || no "pipe-less table passed"; rm -rf "$D"

echo "=== v1.2 guards lens: sinks are prose ==="
D=$(make_env other "report" '```text
Great question! Hope this helps!'); run "$D"
blocked && ok "unterminated fence no longer swallows the turn -> block" || no "unclosed fence still a sink"; rm -rf "$D"
D=$(make_env other "report" "+--------------------------------------------+
Great question! In summary, hope this helps!"); run "$D"
blocked && ok "unterminated box no longer swallows the turn -> block" || no "unclosed box still a sink"; rm -rf "$D"
BOX40=$(python3 -c 'print("+-- NOTE ----+\n" + "\n".join("| line %d of prose inside a box |" % i for i in range(70)) + "\n+------------+")')
D=$(make_env other "report" "$BOX40"); run "$D"
blocked && ok "70-line box counts past its 24th line -> block" || no "over-long box uncounted"; rm -rf "$D"
D=$(make_env other "report" "> Great question! Hope this helps!"); run "$D"
blocked && ok "blockquoted banned phrase -> block" || no "blockquote still exempt"; rm -rf "$D"
BQ61=$(python3 -c 'print("\n".join("> quoted line %d of prose that says something" % i for i in range(61)))')
D=$(make_env other "report" "$BQ61"); run "$D"
blocked && ok "61 blockquote lines count -> block" || no "blockquote lines uncounted"; rm -rf "$D"
D=$(make_env other "report" "[OS-1·OS-2 Great question! In summary, hope this helps! ]"); run "$D"
blocked && ok "header-shaped wrapper is prose -> block" || no "fake header still exempt"; rm -rf "$D"
D=$(make_env other "report" "[INBOUND·DIRECT · TIMING:now · CHANNEL:in-band · REV:reversible · RISK:low]
$CLEAN"); run "$D"
blocked && no "real H-Sutra header blocked" || ok "real H-Sutra header still exempt"; rm -rf "$D"
D=$(make_env other "report" "[STAGE-1-FAIL · CLARIFY · attempt:1/1]
$CLEAN"); run "$D"
blocked && no "stage-1 header blocked" || ok "stage-1 header still exempt"; rm -rf "$D"
D=$(make_env other "fix" "OS: In summary, the fix is small"); run "$D"
blocked && ok "anchored row applies to a field value -> block" || no "field value laundering survives"; rm -rf "$D"
LONG1=$(python3 -c 'print("this sentence repeats to make one giant line. " * 300)')
D=$(make_env other "report" "$LONG1"); run "$D"
blocked && ok "one 13,000-char line weighs 60+ lines -> block" || no "giant line counted as one"; rm -rf "$D"
D=$(make_env other "fix the bug" 'The right closing line is "Hope this helps, let me know if anything else comes up and feel free to reach out any time."'); run "$D"
blocked && ok "quoted span over 80 chars is judged -> block" || no "long quoted span still blanked"; rm -rf "$D"
D=$(make_env other "fix the bug" 'The fix: `Great question! In summary, done.`'); run "$D"
blocked && ok "punctuated inline code is judged -> block" || no "sentence inside backticks still blanked"; rm -rf "$D"
D=$(make_env other "check my email integration" "Great question! Happy to help. Hope this helps!"); run "$D"
blocked && ok "bare noun 'email' no longer downgrades the audience -> block" || no "audience still demoted by a noun"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); printf '{"project_id":"t","project_name":"renamed","writing_style":"advisory"}\n' > "$D/.claude/sutra-project.json"
T=$(mktemp -d); mv "$D" "$T/asawa-holding"; D="$T/asawa-holding"; run "$D"
blocked && ok "pinned status from the directory name survives a renamed project file" || no "renaming project_name un-pinned the repo"; rm -rf "$T"
D=$(make_env other "x" "Great question!"); touch "$D/.enforcement/writing-style.jsonl"; rm -f "$D/.claude/sutra-project.json"; run "$D"
blocked && ok "missing project file with an existing ledger stays activated -> block" || no "removing sutra-project.json silenced the gate"; rm -rf "$D"

echo "=== v1.2 false-negative lens: phrasing and glyphs ==="
for t in "Good question. The bug is in auth." "You're exactly right." "Sorry! The earlier patch was wrong." "My bad on the last diff." "Sure - the fix is in auth.py." "$CLEAN Thanks for flagging that." "$CLEAN Ping me if you need anything else." "$CLEAN Let me know." "Cheers!" "Summary: token check off by one." "Net net: the token check is off." "Big picture: the check is inverted." "As discussed, the token check is fixed." "Here's what I'll do next: rewrite it." "Well done spotting the regression."; do
  D=$(make_env other "fix the bug" "$t"); run "$D"
  blocked && ok "variant -> block: $t" || no "expected block: $t"; rm -rf "$D"
done
for t in 'Run `npm test` to confirm.' "Run the suite and paste the output here." "Verify by running the migration on your machine."; do
  D=$(make_env asawa-holding "deploy" "$t"); run "$D"
  blocked && ok "ask-to-run variant (pinned) -> block: $t" || no "expected block: $t"; rm -rf "$D"
done
for t in "Sure enough, the cache was stale." "Run 3 of 5 passed." "Good work items are small." "It is a good idea to pin versions." "The upshot field is unused."; do
  D=$(make_env other "fix the bug" "$t"); run "$D"
  blocked && no "technical prose blocked (false positive): $t" || ok "technical prose -> pass: $t"; rm -rf "$D"
done
for t in "parse → validate → emit" "• parse • validate • emit" "Done ✔ tests ✘ lint" "🟢 api 🔴 worker" "① first ② second"; do
  D=$(make_env other "list" "$t"); run "$D"
  blocked && ok "glyph -> block: $t" || no "glyph passed: $t"; rm -rf "$D"
done
TT5='| # | Action | Owner |
|---|---|---|
| 1 | rotate keys | ops |
| 2 | patch auth | me |
| 3 | rerun suite | me |'
D=$(make_env other "plan" "$TT5"); run "$D"
blocked && ok "Action/Owner table without Impact/Effort -> block" || no "action table passed"; rm -rf "$D"
TT6='Next steps:
| # | Item | Owner |
|---|---|---|
| 1 | rotate keys | ops |
| 2 | patch auth | me |
| 3 | rerun suite | me |'
D=$(make_env other "plan" "$TT6"); run "$D"
blocked && ok "table under a 'Next steps:' lead-in -> block" || no "lead-in table passed"; rm -rf "$D"
TT7='| Task | Notes on impact and effort |
|---|---|
| a | x |
| b | y |
| c | z |'
D=$(make_env other "plan" "$TT7"); run "$D"
blocked && ok "impact and effort in one cell do not count -> block" || no "single-cell impact/effort passed"; rm -rf "$D"

echo "=== guards ==="
D=$(make_env other "x" "Great question!"); run "$D" true
blocked && no "stop_hook_active still blocked" || ok "stop_hook_active -> pass (one redo max)"
last_row "$D" | grep -q 'stop_hook_active' && ok "ledger records the skip" || no "no skip row"; rm -rf "$D"
D=$(make_env other "x"); run "$D"
blocked && no "empty turn blocked" || ok "empty assistant text -> pass"
last_row "$D" | grep -q 'unverifiable_flush_lag' && ok "flush-lag ledger row" || no "no flush-lag row: $(last_row "$D")"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); rm -f "$D/.claude/sutra-project.json"; run "$D"
blocked && no "fresh install blocked" || ok "no sutra-project.json -> silent"
[ -f "$D/.enforcement/writing-style.jsonl" ] && no "fresh install wrote a ledger" || ok "fresh install writes nothing"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); printf 'REASON=demo of the phrase\nSESSION=t1\n' > "$D/.claude/sessions/t1/writing-style-ack"; run "$D"
blocked && no "ack marker ignored" || ok "audited ack marker -> pass"
last_row "$D" | grep -q '"override"' && ok "override is ledgered" || no "override row missing"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); run "$D"
printf '{"project_id":"t","project_name":"other","writing_style":"advisory"}\n' > "$D/.claude/sutra-project.json"; run "$D"
blocked && no "per-project advisory ignored" || ok "per-project writing_style: advisory -> pass"; rm -rf "$D"
D=$(make_env asawa-holding "x" "Great question!"); printf '{"project_id":"t","project_name":"asawa-holding","writing_style":"advisory"}\n' > "$D/.claude/sutra-project.json"; run "$D"
blocked && ok "pinned project ignores opt-down" || no "pinned project honored opt-down"; rm -rf "$D"

echo "=== revoke scopes (dotfile) ==="
D=$(make_env other "x" "Great question! ┌┐"); printf 'SCOPE=candor\nSESSION=t1\n' > "$D/.claude/sessions/t1/.writing-style-revoked"; run "$D"
printf '%s' "$OUT" | grep -q 'GLAZE' && no "candor revoke still judged GLAZE" || ok "SCOPE=candor skips GLAZE"
printf '%s' "$OUT" | grep -q 'GLYPH' && ok "SCOPE=candor still blocks glyphs" || no "glyph not blocked under candor revoke"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); printf 'SCOPE=all\nSESSION=t1\n' > "$D/.claude/sessions/t1/.writing-style-revoked"; run "$D"
blocked && no "SCOPE=all still blocked" || ok "SCOPE=all -> whole gate advisory"; rm -rf "$D"
D=$(make_env other "x" "$LONG61"); printf 'SCOPE=minimize\nSESSION=t1\n' > "$D/.claude/sessions/t1/.writing-style-revoked"; run "$D"
blocked && no "SCOPE=minimize still enforced budget" || ok "SCOPE=minimize lifts the budget"; rm -rf "$D"

echo "=== audience downgrade ==="
D=$(make_env other "draft the client email for the launch" "Happy to help with your launch!"); run "$D"
blocked && no "customer copy blocked" || ok "customer-copy ask downgrades PLEASANT -> pass"
last_row "$D" | grep -q '"audience":"customer"' && ok "audience ledgered" || no "audience not ledgered"; rm -rf "$D"
D=$(make_env other "fix" "Happy to help!"); printf 'AUDIENCE=customer\nSESSION=t1\n' > "$D/.claude/sessions/t1/writing-style-audience"; run "$D"
blocked && no "audience marker ignored" || ok "AUDIENCE=customer marker -> pass"; rm -rf "$D"

echo "=== self-compliance ==="
# The whole skill pasted as chat prose is over the line budget by design (M7 says put it in a
# file); with the budget lifted, no PHRASE or GLYPH in the skill text may trip the gate.
D=$(make_env other "explain the style" "$(cat "$SKILL")"); printf 'SCOPE=minimize\nSESSION=t1\n' > "$D/.claude/sessions/t1/.writing-style-revoked"; run "$D"
blocked && no "the skill text trips its own gate: $(printf '%s' "$OUT" | head -c 300)" || ok "SKILL.md text as prose -> no phrase/glyph hit"; rm -rf "$D"
D=$(make_env other "x" "Great question!"); run "$D"
REASON=$(printf '%s' "$OUT" | jq -r '.reason' 2>/dev/null)
[ "$(printf '%s' "$REASON" | wc -l | tr -d ' ')" -le 12 ] && ok "block reason <= 12 lines" || no "block reason too long"
printf '%s' "$REASON" | LC_ALL=C grep -q '[^ -~]' && no "block reason has non-ASCII" || ok "block reason is ASCII"
rm -rf "$D"
D=$(make_env other "x" "$REASON"); run "$D"
blocked && no "block reason trips the gate" || ok "block reason passes the gate"; rm -rf "$D"
for s in caveman anti-glaze-tone readability-gate writing-llm-md; do
  D=$(make_env other "x" "$(cat "$PLUGIN/skills/$s/SKILL.md")"); run "$D"
  blocked && no "stub $s trips the gate" || ok "stub $s passes the gate"; rm -rf "$D"
done

echo "=== single source: banned list ==="
python3 - "$SKILL" <<'PY' && ok "banned block extracts and every regex compiles" || no "banned block broken"
import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"<!-- banned:start -->(.*?)<!-- banned:end -->", s, re.S)
assert m, "markers missing"
n = 0
for ln in m.group(1).split("\n"):
    p = ln.split(None, 2)
    if len(p) < 3 or p[1] not in ("H", "A"): continue
    re.compile(p[2], re.I | re.M); n += 1
assert n >= 10, "too few rules: %d" % n
PY
jq -e '.output_discipline | has("banned_phrases") | not' "$DEFAULTS" >/dev/null && ok "sutra-defaults carries no second copy" || no "banned_phrases key found in sutra-defaults"

echo "=== revoke matcher (per-turn-discipline-prompt.sh) ==="
D=$(make_env other "x" "$CLEAN")
mkdir -p "$D/holding/state/interaction"
run_prompt(){ printf '{"session_id":"t1","prompt":"%s"}' "$1" | CLAUDE_PROJECT_DIR="$D" CLAUDE_PLUGIN_ROOT="$PLUGIN" HOME="$D" bash "$PROMPT_HOOK" >/dev/null 2>&1; }
run_prompt "normal mode"
grep -q '^SCOPE=compress' "$D/.claude/sessions/t1/.writing-style-revoked" 2>/dev/null && ok "'normal mode' writes SCOPE=compress dotfile" || no "revoke dotfile not written"
run_prompt "please do not switch to normal mode here"
grep -q '^SCOPE=compress' "$D/.claude/sessions/t1/.writing-style-revoked" 2>/dev/null && ok "phrase inside a sentence does not re-match (whole line only)" || no "mid-sentence phrase changed state"
run_prompt "strict mode"
[ -f "$D/.claude/sessions/t1/.writing-style-revoked" ] && no "'strict mode' did not clear the revoke" || ok "'strict mode' clears the revoke"
run_prompt "stop writing-style"
grep -q '^SCOPE=all' "$D/.claude/sessions/t1/.writing-style-revoked" 2>/dev/null && ok "'stop writing-style' -> SCOPE=all" || no "SCOPE=all not written"
touch "$D/.claude/sessions/t1/plain-marker"
if [ -f "$PLUGIN/hooks/reset-turn-markers.sh" ]; then
  printf '{"session_id":"t1","prompt":"next turn"}' | CLAUDE_PROJECT_DIR="$D" CLAUDE_PLUGIN_ROOT="$PLUGIN" HOME="$D" bash "$PLUGIN/hooks/reset-turn-markers.sh" >/dev/null 2>&1
  [ -f "$D/.claude/sessions/t1/.writing-style-revoked" ] && ok "revoke dotfile survives reset-turn-markers.sh" || no "reset wiped the revoke dotfile"
fi
rm -rf "$D"

echo "=== mode bits ==="
[ -x "$GATE" ] && ok "writing-style-gate.sh is executable" || no "gate not executable"
[ -x "$PROMPT_HOOK" ] && ok "per-turn-discipline-prompt.sh is executable" || no "prompt hook not executable"

echo ""
echo "writing-style-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
