#!/bin/bash
# tests/test-fixture-classification.sh — runs classifier against 13 fixtures
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

FIXTURES="$DIR/fixtures.json"
[ -f "$FIXTURES" ] || { echo "fixtures.json missing"; exit 2; }

NUM=$(jq '.fixtures | length' "$FIXTURES")
for i in $(seq 0 $((NUM-1))); do
  input=$(jq -r ".fixtures[$i].input" "$FIXTURES")
  expected_verb=$(jq -r ".fixtures[$i].verb" "$FIXTURES")
  assert_field "$input" "verb" "$expected_verb"
done

summary
