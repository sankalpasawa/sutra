#!/bin/bash
# scripts/classify.sh — classify a turn input into 9-cell × 3-tag schema
# Input: $1 or stdin
# Output: JSON to stdout
# Task 2.3 — H↔Sutra Layer v1.0 (charter f65725a, ADR-001 b88b7cc)
#
# Mid-phase fold 2026-05-01 (codex-sutra session 019de1c4-2b41-7931-80b7-b22e797668ff,
# verdict CHANGES-REQUIRED → CONVERGED). See:
#   .enforcement/codex-reviews/2026-05-01-h-sutra-v1.0-mid-phase-fold-consult.md
# Folds:
#   R1 — STAGE-1-FAIL is last-resort; only fires when no verb otherwise assigned
#   R2 — DIRECT keyed off STRONG imperatives only; bare "do" no longer fires
#        DIRECT (avoids "what do we…" / "how do I…" / "do we…" false positives)
#   R3 — ASSERT broadened with safe negation/error idioms only; epistemic
#        markers (i think / i feel / seems / appears) intentionally NOT added
#        per codex P1 — too aggressive without tighter clause-order rule.
#   R4 — handled in tests/lib.sh assert_grep (no -f precondition)

set -u

INPUT="${1:-$(cat 2>/dev/null)}"
IR_TYPE="${IR_TYPE:-}"
RETRY_COUNT="${RETRY_COUNT:-0}"
IRREVERSIBLE_HINT="${IRREVERSIBLE_HINT:-0}"

# Lowercased input for inspection (regex stays case-insensitive via -i too).
LC=$(printf '%s' "$INPUT" | tr '[:upper:]' '[:lower:]')

# ── DIRECT detection (R2 fold) ────────────────────────────────────────────────
# STRONG imperative signals only. Bare "do" excluded — too many query frames
# ("what do…", "how do…", "do we…") collide with imperative use.
# Strong tokens: explicit action verbs + imperative scaffolds.
STRONG_DIRECT_RE='\b(fix|build|run|push|delete|add|create|edit|write|modify|publish|deploy|ship|redesign|stimulate|reroute|update|bump|patch|fold|reset|drop|merge|tag|release|install|remove|rename|move|copy|implement|refactor|clean|reformat|document|commit|amend|revert|cherry-pick|rebase|pull|fetch|clone|init|configure|enable|disable)\b'
IMPERATIVE_FRAME_RE='\b(please|let.?s|remind me to|kindly)\b'
# Explicit "do not / don.t / dont" → still DIRECT (negation of imperative).
NEGATED_IMPERATIVE_RE='\b(do not|don.?t|dont)\b'
has_direct=0
if printf '%s' "$LC" | grep -qE "$STRONG_DIRECT_RE"; then has_direct=1; fi
if [ "$has_direct" = "0" ] && printf '%s' "$LC" | grep -qE "$IMPERATIVE_FRAME_RE"; then has_direct=1; fi
if [ "$has_direct" = "0" ] && printf '%s' "$LC" | grep -qE "$NEGATED_IMPERATIVE_RE"; then has_direct=1; fi

# ── QUERY detection ───────────────────────────────────────────────────────────
QUERY_RE='\b(what|how|why|when|where|which|who|should|status)\b|\?$'
has_query=0
if printf '%s' "$LC" | grep -qE "$QUERY_RE"; then has_query=1; fi

# ── ASSERT detection (R3 fold — safe expansion only) ──────────────────────────
# Codex P1: do NOT add epistemic markers (i think / i feel / seems / appears).
# Safe expansion: negation idioms + claim words.
ASSERT_RE='\b(missed|wrong|incorrect|missing|broken|error|errors|errored|failed|fails|didnt|didn.?t|wasnt|wasn.?t|isnt|isn.?t|cant|can.?t|shouldnt|shouldn.?t|wouldnt|wouldn.?t|never|not yet)\b'
has_assert=0
if printf '%s' "$LC" | grep -qE "$ASSERT_RE"; then has_assert=1; fi

# ── Translation table: Input Routing TYPE → preferred verb ────────────────────
case "$IR_TYPE" in
  question)    VERB=QUERY ;;
  feedback)    VERB=ASSERT ;;
  direction)   VERB=DIRECT ;;
  task)        VERB=DIRECT ;;
  new-concept) VERB=QUERY ;;
  *)           VERB="" ;;
esac

# ── Apply ADR-001 precedence: DIRECT > QUERY > ASSERT ─────────────────────────
# Translation table verb is the PREFERRED path. Direct-content matches override
# only when stronger (DIRECT regex hits regardless of IR_TYPE = direction
# already produces DIRECT). For mixed-acts: principal = highest precedence; the
# others go into mixed_acts.
MIXED_ACTS_TMP=()
if [ "$has_direct" = "1" ]; then
  VERB=DIRECT
  [ "$has_query" = "1" ] && MIXED_ACTS_TMP+=("QUERY")
  [ "$has_assert" = "1" ] && MIXED_ACTS_TMP+=("ASSERT")
elif [ "$has_query" = "1" ]; then
  VERB=QUERY
  [ "$has_assert" = "1" ] && MIXED_ACTS_TMP+=("ASSERT")
elif [ "$has_assert" = "1" ]; then
  VERB=ASSERT
fi

# Fallback: no IR_TYPE and no content match → default QUERY (preserves prior behavior)
[ -z "$VERB" ] && VERB=QUERY

# ── Stage 1 confidence gate (R1 fold — last resort) ───────────────────────────
# Only trigger STAGE-1-FAIL when the utterance is short AND uses an unanchored
# referent AND no verb signal otherwise fired. Honors codex: "Stage-1
# ambiguity should be a last-resort fallback, not a higher-precedence override."
WORD_COUNT=$(printf '%s' "$INPUT" | wc -w | tr -d ' ')
HAS_REFERENT=$(printf '%s' "$LC" | grep -qE '\b(it|that|this|thing|stuff)\b' && echo 1 || echo 0)
NO_VERB_SIGNAL=$([ "$has_direct" = "0" ] && [ "$has_query" = "0" ] && [ "$has_assert" = "0" ] && echo 1 || echo 0)
STAGE_1_FAIL=false
if [ "$WORD_COUNT" -lt 4 ] && [ "$HAS_REFERENT" = "1" ] && [ "$NO_VERB_SIGNAL" = "1" ]; then
  VERB=STAGE-1-FAIL
  STAGE_1_FAIL=true
fi

# ── Reversibility — irreversible-domain denylist ──────────────────────────────
REVERSIBILITY=reversible
if printf '%s' "$LC" | grep -qE '\b(push|publish|send|email|delete|drop|rm -rf|force-push|reset --hard|deploy.*prod|to origin|--force)\b'; then
  REVERSIBILITY=irreversible
fi
[ "$IRREVERSIBLE_HINT" = "1" ] && REVERSIBILITY=irreversible

# ── Decision risk ─────────────────────────────────────────────────────────────
RISK=low
[ "$REVERSIBILITY" = "irreversible" ] && RISK=high
printf '%s' "$LC" | grep -qE '\b(auth|secret|payment|legal|compliance|prod|production)\b' && RISK=high

# ── Tense ─────────────────────────────────────────────────────────────────────
TENSE=null
printf '%s' "$LC" | grep -qE '\b(was|did|happened|shipped|yesterday|earlier|past)\b' && TENSE=past
printf '%s' "$LC" | grep -qE '\b(is|now|currently|right now|status)\b' && TENSE=present
printf '%s' "$LC" | grep -qE '\b(will|plan|future|next|tomorrow|going to)\b' && TENSE=future

# ── Timing ────────────────────────────────────────────────────────────────────
TIMING=now
printf '%s' "$LC" | grep -qE '\b(later|tomorrow|next week|in.*weeks?|remind|schedule)\b' && TIMING=later

# ── Channel default ───────────────────────────────────────────────────────────
CHANNEL=in-band

# ── Bounded retry — Stage 1 FAIL after 1 attempt → proceed-or-refuse ──────────
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

# ── Emission stage (always Stage 3) ───────────────────────────────────────────
EMISSION_STAGE=STAGE_3

# ── Expected emission type ────────────────────────────────────────────────────
if [ "$STAGE_1_FAIL" = "true" ] && [ "$RETRY_SATURATED" = "false" ]; then
  EMIT_TYPE=OUT-QUERY
elif [ "$VERB" = "DIRECT" ] && [ "$REVERSIBILITY" = "irreversible" ]; then
  EMIT_TYPE=OUT-QUERY
elif [ "$VERB" = "ASSERT" ]; then
  EMIT_TYPE=OUT-ASSERT
else
  EMIT_TYPE=OUT-ASSERT
fi

# ── OUT-QUERY guardrails ──────────────────────────────────────────────────────
GUARDRAILS='{"named_var":"required","why":"required","one_turn_answerable":"required"}'

# ── Build mixed_acts JSON array ───────────────────────────────────────────────
MIXED_JSON="[]"
if [ "${#MIXED_ACTS_TMP[@]}" -gt 0 ]; then
  MIXED_JSON=$(printf '"%s",' "${MIXED_ACTS_TMP[@]}" | sed 's/,$//')
  MIXED_JSON="[$MIXED_JSON]"
fi

# ── Output JSON ───────────────────────────────────────────────────────────────
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
  "stage_3_emission_type": "$EMIT_TYPE",
  "expected_emission_type": "$EMIT_TYPE",
  "out_query_guardrails": $GUARDRAILS,
  "ir_type": "$IR_TYPE"
}
EOF
