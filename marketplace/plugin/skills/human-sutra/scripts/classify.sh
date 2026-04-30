#!/bin/bash
# scripts/classify.sh — classify a turn input into 9-cell × 3-tag schema
# Input: $1 or stdin
# Output: JSON to stdout
# Task 2.3 — H↔Sutra Layer v1.0 (charter f65725a, ADR-001 b88b7cc)

set -u

INPUT="${1:-$(cat 2>/dev/null)}"
IR_TYPE="${IR_TYPE:-}"
RETRY_COUNT="${RETRY_COUNT:-0}"
IRREVERSIBLE_HINT="${IRREVERSIBLE_HINT:-0}"

# Translation table: Input Routing TYPE → verb (preferred path)
case "$IR_TYPE" in
  question)    VERB=QUERY ;;
  feedback)    VERB=ASSERT ;;
  direction)   VERB=DIRECT ;;
  task)        VERB=DIRECT ;;
  new-concept) VERB=QUERY ;;  # default; can override via intent inference
  *)           VERB="" ;;
esac

# Fallback intent inference if IR_TYPE not provided
if [ -z "$VERB" ]; then
  if printf '%s' "$INPUT" | grep -qiE '\b(do|fix|build|run|push|delete|add|create|edit|write|modify|publish|deploy|ship)\b'; then
    VERB=DIRECT
  elif printf '%s' "$INPUT" | grep -qiE '\b(what|how|why|when|where|which|who|should|status|is)\b'; then
    VERB=QUERY
  elif printf '%s' "$INPUT" | grep -qiE '\b(missed|wrong|incorrect|missing|not|never|don.t|incorrect)\b'; then
    VERB=ASSERT
  else
    VERB=QUERY  # default
  fi
fi

# Classification precedence (DIRECT > QUERY > ASSERT) for mixed acts
MIXED_ACTS_TMP=()
has_direct=0; has_query=0; has_assert=0
printf '%s' "$INPUT" | grep -qiE '\b(do|fix|build|run|push|delete|add|create|edit|write|modify|publish|deploy|ship)\b' && has_direct=1
printf '%s' "$INPUT" | grep -qiE '\b(what|how|why|when|where|which|who|should)\b' && has_query=1
printf '%s' "$INPUT" | grep -qiE '\b(missed|wrong|incorrect|missing)\b' && has_assert=1

# Apply precedence: DIRECT wins
if [ "$has_direct" = "1" ]; then
  VERB=DIRECT
  [ "$has_query" = "1" ] && MIXED_ACTS_TMP+=("QUERY")
  [ "$has_assert" = "1" ] && MIXED_ACTS_TMP+=("ASSERT")
elif [ "$has_query" = "1" ]; then
  VERB=QUERY
  [ "$has_assert" = "1" ] && MIXED_ACTS_TMP+=("ASSERT")
fi

# Stage 1 confidence gate — if input too vague (no concrete referent)
WORD_COUNT=$(printf '%s' "$INPUT" | wc -w | tr -d ' ')
HAS_REFERENT=$(printf '%s' "$INPUT" | grep -qiE '\b(it|that|this|thing|stuff)\b' && echo 1 || echo 0)
if [ "$WORD_COUNT" -lt 4 ] && [ "$HAS_REFERENT" = "1" ]; then
  VERB=STAGE-1-FAIL
  STAGE_1_FAIL=true
else
  STAGE_1_FAIL=false
fi

# Reversibility — irreversible-domain denylist
REVERSIBILITY=reversible
if printf '%s' "$INPUT" | grep -qiE '\b(push|publish|send|email|delete|drop|rm -rf|force-push|reset --hard|deploy.*prod|to origin|--force)\b'; then
  REVERSIBILITY=irreversible
fi
[ "$IRREVERSIBLE_HINT" = "1" ] && REVERSIBILITY=irreversible

# Decision risk
RISK=low
[ "$REVERSIBILITY" = "irreversible" ] && RISK=high
printf '%s' "$INPUT" | grep -qiE '\b(auth|secret|payment|legal|compliance|prod|production)\b' && RISK=high

# Tense
TENSE=null
printf '%s' "$INPUT" | grep -qiE '\b(was|did|happened|shipped|yesterday|earlier|past)\b' && TENSE=past
printf '%s' "$INPUT" | grep -qiE '\b(is|now|currently|right now|status)\b' && TENSE=present
printf '%s' "$INPUT" | grep -qiE '\b(will|plan|future|next|tomorrow|going to)\b' && TENSE=future

# Timing
TIMING=now
printf '%s' "$INPUT" | grep -qiE '\b(later|tomorrow|next week|in.*weeks?|remind|schedule)\b' && TIMING=later

# Channel default
CHANNEL=in-band

# Bounded retry — Stage 1 FAIL after 1 attempt → proceed-or-refuse
RETRY_SATURATED=false
BOUNDED_RETRY_ACTION=null
if [ "$STAGE_1_FAIL" = "true" ] && [ "$RETRY_COUNT" -ge 1 ]; then
  RETRY_SATURATED=true
  if [ "$REVERSIBILITY" = "reversible" ]; then
    BOUNDED_RETRY_ACTION=proceed-on-assumption
  else
    BOUNDED_RETRY_ACTION=refuse-and-escalate
  fi
fi

# Emission stage (always Stage 3)
EMISSION_STAGE=STAGE_3

# Expected emission type
if [ "$STAGE_1_FAIL" = "true" ] && [ "$RETRY_SATURATED" = "false" ]; then
  EMIT_TYPE=OUT-QUERY
elif [ "$VERB" = "DIRECT" ] && [ "$REVERSIBILITY" = "irreversible" ]; then
  EMIT_TYPE=OUT-QUERY
elif [ "$VERB" = "ASSERT" ]; then
  EMIT_TYPE=OUT-ASSERT
else
  EMIT_TYPE=OUT-ASSERT
fi

# OUT-QUERY guardrails
GUARDRAILS='{"named_var":"required","why":"required","one_turn_answerable":"required"}'

# Build mixed_acts JSON array
MIXED_JSON="[]"
if [ "${#MIXED_ACTS_TMP[@]}" -gt 0 ]; then
  MIXED_JSON=$(printf '"%s",' "${MIXED_ACTS_TMP[@]}" | sed 's/,$//')
  MIXED_JSON="[$MIXED_JSON]"
fi

# Output JSON
cat <<EOF
{
  "ts": "$(date -u +%FT%TZ)",
  "direction": "INBOUND",
  "verb": "$VERB",
  "principal_act": "$VERB",
  "mixed_acts": $MIXED_JSON,
  "tense": $([ "$TENSE" = "null" ] && printf 'null' || printf '"%s"' "$TENSE"),
  "timing": "$TIMING",
  "channel": "$CHANNEL",
  "reversibility": "$REVERSIBILITY",
  "decision_risk": "$RISK",
  "stage_1_fail": $STAGE_1_FAIL,
  "retry_counter": $RETRY_COUNT,
  "retry_saturated": $RETRY_SATURATED,
  "bounded_retry_action": $([ "$BOUNDED_RETRY_ACTION" = "null" ] && printf 'null' || printf '"%s"' "$BOUNDED_RETRY_ACTION"),
  "emission_stage": "$EMISSION_STAGE",
  "expected_emission_type": "$EMIT_TYPE",
  "out_query_guardrails": $GUARDRAILS,
  "ir_type": "$IR_TYPE"
}
EOF
