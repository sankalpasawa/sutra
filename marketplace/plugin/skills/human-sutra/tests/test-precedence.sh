#!/bin/bash
# tests/test-precedence.sh — DIRECT > QUERY > ASSERT precedence
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

# Compound: ASSERT + DIRECT → principal=DIRECT, mixed_acts=[ASSERT]
assert_field "you missed Y, fix it" "verb" "DIRECT"
# Compound: QUERY + DIRECT → principal=DIRECT
assert_field "should I ship X? do it now" "verb" "DIRECT"
# Pure QUERY (no DIRECT verb words) → principal=QUERY
assert_field "what is the status?" "verb" "QUERY"
# Pure ASSERT → principal=ASSERT
assert_field "this is wrong" "verb" "ASSERT"

summary
