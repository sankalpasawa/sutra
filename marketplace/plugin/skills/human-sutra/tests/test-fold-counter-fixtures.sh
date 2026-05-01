#!/bin/bash
# tests/test-fold-counter-fixtures.sh — codex-mandated counter-fixtures
#
# Created 2026-05-01 per codex consult session 019de1c4-2b41-7931-80b7-b22e797668ff
# Q5: "Add counter-fixtures around auxiliary 'do' and epistemic ASSERT markers
# to lock in the heuristic-surface fixes (R2, R3) and prevent regression."
#
# Two failure modes the fold must not introduce:
#   1. Auxiliary "do" mis-classified as DIRECT (the original R2 hole).
#   2. Epistemic stance ("I think", "seems") accidentally promoted to ASSERT
#      (the R3 over-broadening codex P1'd against).
#
# Precedence reminder (ADR-001): DIRECT > QUERY > ASSERT for mixed acts. So
# "do we ship today?" is DIRECT (because "ship") with mixed_acts=[QUERY],
# NOT QUERY. The auxiliary-"do" guard is about not letting BARE "do" alone
# act as DIRECT — it is not about overriding strong action verbs that happen
# to appear in an interrogative frame.
#
# v1.0 known limitations (not tested here; deferred to v1.1 instrumentation
# learnings per charter "Visibility Before Influence"):
#   - Past-tense narration of action verbs ("the deploy failed" → DIRECT not
#     ASSERT) — classifier sees "deploy" before reading clause structure.
#   - Noun-vs-verb ambiguity ("the build is broken" → DIRECT not ASSERT) —
#     "build" is a strong-DIRECT lemma whether noun or verb.
# Both fold under v1.1 once instrumentation shows real-world frequency.

set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

# ── 1. Auxiliary "do" alone must NOT trigger DIRECT ───────────────────────────
# Bare "do we / do you / do they" without an accompanying strong verb is
# interrogative scaffolding, not imperative. Examples chosen to NOT include
# strong-DIRECT lemmas, so QUERY wins.
assert_field "do we have access?" "verb" "QUERY"
assert_field "what do the logs show?" "verb" "QUERY"
assert_field "why do we need this?" "verb" "QUERY"
assert_field "do they have permission?" "verb" "QUERY"
# Bare "do that thing" with referent → STAGE-1-FAIL (last-resort), not DIRECT
assert_field "do that thing" "verb" "STAGE-1-FAIL"

# ── 2. Imperative scaffolds DO trigger DIRECT ─────────────────────────────────
# "please", "let's/lets", "remind me to", "kindly" — these MUST keep firing.
assert_field "please ship the patch" "verb" "DIRECT"
assert_field "let's redesign the diagram" "verb" "DIRECT"
assert_field "lets fix the bug" "verb" "DIRECT"
assert_field "remind me to clean up next week" "verb" "DIRECT"
assert_field "kindly publish the release" "verb" "DIRECT"

# ── 3. Negated imperative ("do not / don't") DOES trigger DIRECT ──────────────
# Codex Q3 explicitly: "do not / don't" are directives syntactically.
assert_field "do not deploy to prod yet" "verb" "DIRECT"
assert_field "don't push that branch" "verb" "DIRECT"
assert_field "dont rebase main" "verb" "DIRECT"

# ── 4. Strong-DIRECT verbs win precedence even in interrogative frames ────────
# Per ADR-001 DIRECT > QUERY > ASSERT — when a clear action verb appears in
# a question, DIRECT is the principal_act, QUERY recorded as mixed_acts.
assert_field "do we ship today?" "verb" "DIRECT"
assert_field "how do I push to origin?" "verb" "DIRECT"

# ── 5. Epistemic stance markers do NOT auto-promote to ASSERT ─────────────────
# Codex P1: "i think / i feel / seems / appears" are too aggressive without
# tighter clause-order. The classifier resolves these by the OTHER tokens.
# "I think we should ship" → "ship" matches DIRECT regex → DIRECT.
assert_field "I think we should ship" "verb" "DIRECT"
# "I feel like this might break" → no DIRECT/ASSERT trigger; default QUERY.
assert_field "I feel like this might break" "verb" "QUERY"
# "Seems fine to me" → "fine" no trigger; default QUERY.
assert_field "Seems fine to me" "verb" "QUERY"

# ── 6. ASSERT-trigger words still fire ASSERT correctly (R3 safe expansion) ───
# Words that are unambiguously ASSERT-only (not also DIRECT verb lemmas).
assert_field "this is wrong" "verb" "ASSERT"
assert_field "didnt get it" "verb" "ASSERT"
assert_field "you missed the row" "verb" "ASSERT"
assert_field "the tests errored" "verb" "ASSERT"

summary
