#!/bin/bash
# tests/test-translation.sh — Input Routing TYPE → 9-cell verb
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

CLASSIFY="$DIR/../scripts/classify.sh"

# Translation: question → IN-QUERY
out=$(IR_TYPE=question bash "$CLASSIFY" "what is X?" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r .verb)" "QUERY" "question → QUERY"

# feedback → IN-ASSERT
out=$(IR_TYPE=feedback bash "$CLASSIFY" "this is wrong" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r .verb)" "ASSERT" "feedback → ASSERT"

# direction → IN-DIRECT
out=$(IR_TYPE=direction bash "$CLASSIFY" "always do X" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r .verb)" "DIRECT" "direction → DIRECT"

# task → IN-DIRECT
out=$(IR_TYPE=task bash "$CLASSIFY" "build X" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r .verb)" "DIRECT" "task → DIRECT"

# new-concept → QUERY by default
out=$(IR_TYPE=new-concept bash "$CLASSIFY" "what about Y?" 2>/dev/null)
verb=$(printf '%s' "$out" | jq -r .verb)
case "$verb" in QUERY|ASSERT) echo "ok - new-concept → $verb (acceptable)";; *) echo "not ok - new-concept → $verb (expected QUERY|ASSERT)";; esac

summary
