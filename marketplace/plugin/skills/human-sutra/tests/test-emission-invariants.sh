#!/bin/bash
# tests/test-emission-invariants.sh — Stage-3-only emission + OUT-QUERY guardrails + negatives
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

CLASSIFY="$DIR/../scripts/classify.sh"

# Stage-3-only emission: classifier output flags emission stage
out=$(printf 'add slack connector' | bash "$CLASSIFY" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r '.emission_stage')" "STAGE_3" "emission only at Stage 3"

# Negative: DIRECT path on reversible action does NOT emit OUT-QUERY
out=$(printf 'add slack connector' | bash "$CLASSIFY" 2>/dev/null)
emit_type=$(printf '%s' "$out" | jq -r '.stage_3_emission_type')
assert_equals "$emit_type" "OUT-ASSERT" "DIRECT+reversible → OUT-ASSERT (not OUT-QUERY)"

# Positive: irreversible DIRECT → OUT-QUERY with all 3 guardrails
out=$(printf 'push v1.0.1 to origin/main' | bash "$CLASSIFY" 2>/dev/null)
emit_type=$(printf '%s' "$out" | jq -r '.stage_3_emission_type')
assert_equals "$emit_type" "OUT-QUERY" "DIRECT+irreversible → OUT-QUERY"

# Guardrails on OUT-QUERY: named-var, why, one-turn-answerable
guardrails=$(printf '%s' "$out" | jq -r '.out_query_guardrails')
for g in named_var why one_turn_answerable; do
  assert_grep <(printf '%s' "$guardrails") "\"$g\":\"required\"" "OUT-QUERY guardrail $g required"
done

# Negative: ASSERT path → OUT-ASSERT (acknowledgment), not OUT-QUERY
out=$(printf 'this is wrong' | bash "$CLASSIFY" 2>/dev/null)
emit_type=$(printf '%s' "$out" | jq -r '.stage_3_emission_type')
assert_equals "$emit_type" "OUT-ASSERT" "ASSERT path → OUT-ASSERT (no leakage to OUT-QUERY)"

# No Stage 1 or Stage 2 leakage: classifier never sets stage_1_emit or stage_2_emit fields
out=$(printf 'add X' | bash "$CLASSIFY" 2>/dev/null)
assert_equals "$(printf '%s' "$out" | jq -r '.stage_1_emit // "absent"')" "absent" "no Stage 1 emit field"
assert_equals "$(printf '%s' "$out" | jq -r '.stage_2_emit // "absent"')" "absent" "no Stage 2 emit field"

summary
