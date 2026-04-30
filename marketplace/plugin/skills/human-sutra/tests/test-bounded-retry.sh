#!/bin/bash
# tests/test-bounded-retry.sh — Stage 1 FAIL → CLARIFY (1x) → proceed-or-refuse
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

CLASSIFY="$DIR/../scripts/classify.sh"

# Vague input → STAGE-1-FAIL on first pass
out1=$(printf 'do that thing' | bash "$CLASSIFY" 2>/dev/null)
verb1=$(printf '%s' "$out1" | jq -r '.verb')
assert_equals "$verb1" "STAGE-1-FAIL" "vague input → Stage 1 FAIL"

# Retry counter at 0 initially
retry1=$(printf '%s' "$out1" | jq -r '.retry_counter')
assert_equals "$retry1" "0" "initial retry counter is 0"

# After 1 CLARIFY emission, retry counter increments
out2=$(printf 'do that thing' | RETRY_COUNT=1 bash "$CLASSIFY" 2>/dev/null)
saturation=$(printf '%s' "$out2" | jq -r '.retry_saturated')
assert_equals "$saturation" "true" "retry saturated after 1 attempt"

# Reversible → proceed-on-assumption emitted
proceed_action=$(printf '%s' "$out2" | jq -r '.bounded_retry_action // "none"')
assert_equals "$proceed_action" "proceed-on-assumption" "reversible vague → proceed"

# Irreversible vague stays blocked
out3=$(printf 'do that thing' | RETRY_COUNT=1 IRREVERSIBLE_HINT=1 bash "$CLASSIFY" 2>/dev/null)
refuse_action=$(printf '%s' "$out3" | jq -r '.bounded_retry_action // "none"')
assert_equals "$refuse_action" "refuse-and-escalate" "irreversible vague → refuse"

summary
