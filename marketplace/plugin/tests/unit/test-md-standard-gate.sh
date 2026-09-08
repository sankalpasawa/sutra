#!/bin/bash
# Unit test: hooks/md-standard-gate.sh v2.0 — PostToolUse .md gate for core:writing-style section 7.
# Builds a throwaway git repo and asserts: MD-1/MD-2 hard for new files, MD-3 box art (ASCII + unicode,
# fence-aware), MD-4 duplicate H1, MD-5 SKILL.md line cap (new hard, tracked no-growth ratchet),
# MD-A2 untagged fence advisory, tracked files advisory, exempt paths silent, submodule-safe root.

set -u
PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
GATE="$PLUGIN/hooks/md-standard-gate.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  OK  $1"; }
no(){ FAIL=$((FAIL+1)); echo "  XX  $1"; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not installed"; exit 0; }

R=$(mktemp -d); cd "$R" || exit 1
git init -q . && git config user.email t@t && git config user.name t
mkdir -p docs skills/x holding/skills archive
GOOD='# Title

Purpose line.

- **status**: v1
- **updated**: 2026-09-08

## Body

```text
x
```

provenance: {author: t, date: 2026-09-08}
'
RC=0; ERR=""
run(){ ERR=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$R/$1" | CLAUDE_PROJECT_DIR="$R" HOME="$R" bash "$GATE" 2>&1 >/dev/null); RC=$?; }

printf '%s' "$GOOD" > docs/good.md; run docs/good.md
[ "$RC" -eq 0 ] && ok "compliant new file -> pass" || no "good file rc=$RC: $ERR"

printf '# T\n\nno meta here\n' > docs/bad.md; run docs/bad.md
[ "$RC" -eq 2 ] && ok "new file missing META + PROV -> exit 2" || no "expected 2 got $RC"
printf '%s' "$ERR" | grep -q 'MD-1' && printf '%s' "$ERR" | grep -q 'MD-2' && ok "both rule ids named" || no "rule ids missing: $ERR"
printf '%s' "$ERR" | grep -q 'core:writing-style' && ok "message cites core:writing-style" || no "message cites old standard"

printf '%s\n+------+\n| x |\n+------+\n' "$GOOD" > docs/art.md; run docs/art.md
[ "$RC" -eq 2 ] && ok "ASCII box art outside a fence -> exit 2 (MD-3)" || no "art expected 2 got $RC"
printf '%s\n┌────────┐\n│ x │\n└────────┘\n' "$GOOD" > docs/uart.md; run docs/uart.md
[ "$RC" -eq 2 ] && ok "unicode box art outside a fence -> exit 2 (MD-3)" || no "unicode art expected 2 got $RC"
printf '%s\n```text\n+------+\n| x |\n+------+\n```\n' "$GOOD" > docs/fart.md
# provenance must stay in the tail: re-append it after the fenced box
printf 'provenance: {author: t, date: 2026-09-08}\n' >> docs/fart.md; run docs/fart.md
[ "$RC" -eq 0 ] && ok "fenced box art -> pass" || no "fenced art rc=$RC: $ERR"

printf '%s\n# Second H1\n\nprovenance: {author: t, date: 2026-09-08}\n' "$GOOD" > docs/h1.md; run docs/h1.md
[ "$RC" -eq 2 ] && ok "two H1 -> exit 2 (MD-4)" || no "two H1 expected 2 got $RC"
printf '%s\n```bash\n# a comment, not a heading\n```\nprovenance: {author: t, date: 2026-09-08}\n' "$GOOD" > docs/h1f.md; run docs/h1f.md
[ "$RC" -eq 0 ] && ok "# inside a fence is not an H1" || no "fenced # counted: $ERR"

printf -- '---\nname: x\n---\n\n# x\n\ntext\n\nprovenance: {author: t, date: 2026-09-08}\n' > skills/x/SKILL.md; run skills/x/SKILL.md
[ "$RC" -eq 0 ] && ok "frontmatter-only metadata accepted (MD-1 predicate unchanged)" || no "frontmatter rejected: $ERR"

printf '%s' "$GOOD" > docs/untagged.md; printf '```\nraw\n```\nprovenance: {author: t, date: 2026-09-08}\n' >> docs/untagged.md; run docs/untagged.md
[ "$RC" -eq 0 ] && ok "untagged fence on a new file -> advisory only (until 2026-10-08)" || no "untagged fence blocked: $ERR"
printf '%s' "$ERR" | grep -q 'MD-A2' && ok "advisory names MD-A2" || no "no MD-A2 advisory"

python3 -c 'print("# Big\n\n- **status**: v1\n\n" + "\n".join("line %d" % i for i in range(251)) + "\n\nprovenance: {author: t, date: 2026-09-08}")' > skills/x/SKILL.md; run skills/x/SKILL.md
[ "$RC" -eq 2 ] && ok "new 256-line SKILL.md -> exit 2 (MD-5)" || no "line cap expected 2 got $RC"

# tracked files: advisory, except the MD-5 no-growth ratchet
printf '# T\n\nno meta\n' > docs/tracked.md; git add docs/tracked.md && git commit -qm t
run docs/tracked.md
[ "$RC" -eq 0 ] && ok "tracked file missing META -> advisory exit 0" || no "tracked expected 0 got $RC"
printf '%s' "$ERR" | grep -q 'advisory' && ok "advisory message emitted" || no "no advisory message"
python3 -c 'print("# Big\n\n- **status**: v1\n\n" + "\n".join("line %d" % i for i in range(260)) + "\n\nprovenance: {author: t, date: 2026-09-08}")' > skills/x/SKILL.md; git add skills/x/SKILL.md && git commit -qm big
python3 -c 'print("# Big\n\n- **status**: v1\n\n" + "\n".join("line %d" % i for i in range(259)) + "\n\nprovenance: {author: t, date: 2026-09-08}")' > skills/x/SKILL.md; run skills/x/SKILL.md
[ "$RC" -eq 0 ] && ok "tracked SKILL.md over cap but shrinking -> pass" || no "shrinking file blocked: $ERR"
python3 -c 'print("# Big\n\n- **status**: v1\n\n" + "\n".join("line %d" % i for i in range(261)) + "\n\nprovenance: {author: t, date: 2026-09-08}")' > skills/x/SKILL.md; run skills/x/SKILL.md
[ "$RC" -eq 2 ] && ok "tracked SKILL.md over cap and growing -> exit 2 (no-growth ratchet)" || no "growth not blocked rc=$RC"

printf 'junk\n' > archive/old.md; run archive/old.md
[ "$RC" -eq 0 ] && ok "exempt path (archive) -> silent" || no "exempt path blocked"
printf 'junk\n' > README.md; run README.md
[ "$RC" -eq 0 ] && ok "README.md exempt" || no "README blocked"
grep -c '"hook":"md-standard-gate"' .enforcement/md-standard.jsonl >/dev/null 2>&1 && ok "ledger written" || no "no ledger"

# submodule-safe root: the file's own repo decides tracked-ness, not the CWD's repo
OUTER=$(mktemp -d); mkdir -p "$OUTER/inner"; ( cd "$OUTER" && git init -q . ) ; ( cd "$OUTER/inner" && git init -q . && git config user.email t@t && git config user.name t && printf '# T\n\nno meta\n' > f.md && git add f.md && git commit -qm t )
ERR=$(printf '{"tool_name":"Write","tool_input":{"file_path":"%s"}}' "$OUTER/inner/f.md" | CLAUDE_PROJECT_DIR="$OUTER" HOME="$OUTER" bash "$GATE" 2>&1 >/dev/null); RC=$?
[ "$RC" -eq 0 ] && ok "file tracked by an inner repo is not treated as NEW from the outer CWD" || no "submodule file promoted to HARD: $ERR"
rm -rf "$OUTER"

cd / && rm -rf "$R"
echo ""
echo "md-standard-gate: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
