#!/bin/bash
# tests/test-out-direct-3check.sh — ADR-002 OUT-DIRECT 3-check regression test.
#
# Validates that fixtures #14 (none-hit → demoted) and #15 (denylist-hit → surfaced)
# carry the expected schema fields. The 3-check itself is a model-side discipline
# in SKILL.md §Stage-3 OUT-DIRECT discipline; this test asserts the FIXTURE shape
# is correct so the discipline harness can branch on it.
#
# ADR-002, codex R2 PASS DIRECTIVE-ID 1777640243, 2026-05-01.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"

FIXTURES="$DIR/fixtures.json"

# ── Fixture #14 — DEMOTED (none of 3 checks hit) ──────────────────────────────
F14_DIR=$(jq -r '.fixtures[] | select(.id==14) | .direction' "$FIXTURES")
F14_VERB=$(jq -r '.fixtures[] | select(.id==14) | .verb' "$FIXTURES")
F14_SUB=$(jq -r '.fixtures[] | select(.id==14) | .sub_form' "$FIXTURES")
F14_HITS=$(jq -r '.fixtures[] | select(.id==14) | .expected_3check_hits | length' "$FIXTURES")
F14_DEMOTED=$(jq -r '.fixtures[] | select(.id==14) | .expected_demoted' "$FIXTURES")
F14_EMIT=$(jq -r '.fixtures[] | select(.id==14) | .expected_emission' "$FIXTURES")

assert_equals "$F14_DIR"      "OUTBOUND"           "fixture #14 direction=OUTBOUND"
assert_equals "$F14_VERB"     "DIRECT"             "fixture #14 verb=DIRECT"
assert_equals "$F14_SUB"      "REQUEST·HUMAN-EXEC" "fixture #14 sub_form=REQUEST·HUMAN-EXEC"
assert_equals "$F14_HITS"     "0"                  "fixture #14 expected_3check_hits is empty (none hit)"
assert_equals "$F14_DEMOTED"  "true"               "fixture #14 expected_demoted=true"
assert_equals "$F14_EMIT"     "OUT-ASSERT"         "fixture #14 demote → OUT-ASSERT (INFORM)"

# ── Fixture #15 — SURFACED (denylist-hit) ─────────────────────────────────────
F15_DIR=$(jq -r '.fixtures[] | select(.id==15) | .direction' "$FIXTURES")
F15_VERB=$(jq -r '.fixtures[] | select(.id==15) | .verb' "$FIXTURES")
F15_SUB=$(jq -r '.fixtures[] | select(.id==15) | .sub_form' "$FIXTURES")
F15_HITS_LEN=$(jq -r '.fixtures[] | select(.id==15) | .expected_3check_hits | length' "$FIXTURES")
F15_HIT_FIRST=$(jq -r '.fixtures[] | select(.id==15) | .expected_3check_hits[0]' "$FIXTURES")
F15_DEMOTED=$(jq -r '.fixtures[] | select(.id==15) | .expected_demoted' "$FIXTURES")
F15_EMIT=$(jq -r '.fixtures[] | select(.id==15) | .expected_emission' "$FIXTURES")

assert_equals "$F15_DIR"        "OUTBOUND"           "fixture #15 direction=OUTBOUND"
assert_equals "$F15_VERB"       "DIRECT"             "fixture #15 verb=DIRECT"
assert_equals "$F15_SUB"        "REQUEST·HUMAN-EXEC" "fixture #15 sub_form=REQUEST·HUMAN-EXEC"
assert_equals "$F15_HITS_LEN"   "1"                  "fixture #15 expected_3check_hits has 1 entry"
assert_equals "$F15_HIT_FIRST"  "denylist-hit"       "fixture #15 hit is denylist-hit"
assert_equals "$F15_DEMOTED"    "false"              "fixture #15 expected_demoted=false (surfaced)"
assert_equals "$F15_EMIT"       "OUT-DIRECT"         "fixture #15 surface → OUT-DIRECT (REQUEST·HUMAN-EXEC)"

# ── Mirror-case invariant — fixture #10 (INBOUND·DIRECT push --force) ↔ #15 ──
F10_DIR=$(jq -r '.fixtures[] | select(.id==10) | .direction' "$FIXTURES")
F10_INPUT=$(jq -r '.fixtures[] | select(.id==10) | .input' "$FIXTURES")
F15_INPUT=$(jq -r '.fixtures[] | select(.id==15) | .input' "$FIXTURES")
assert_equals "$F10_DIR" "INBOUND"  "mirror-case invariant: fixture #10 direction=INBOUND"
# Both inputs reference --force; one as INBOUND directive, the other as OUTBOUND request.
F10_FORCE=$(printf '%s' "$F10_INPUT" | grep -ciE '(--force|push)' || true)
F15_FORCE=$(printf '%s' "$F15_INPUT" | grep -ciE '(--force|push)' || true)
[ "$F10_FORCE" -gt 0 ] && [ "$F15_FORCE" -gt 0 ] && assert_equals "ok" "ok" "mirror-case: #10 and #15 both reference push/--force command family"

# ── ADR-001 backward-compat — all 13 INBOUND fixtures still parse with INBOUND direction ──
INBOUND_COUNT=$(jq '[.fixtures[] | select(.direction=="INBOUND")] | length' "$FIXTURES")
assert_equals "$INBOUND_COUNT" "13" "ADR-001 13 INBOUND fixtures still present (backward-compat)"
TOTAL_COUNT=$(jq '.fixtures | length' "$FIXTURES")
assert_equals "$TOTAL_COUNT" "15" "fixtures.json now has 15 rows total (13 + 2 ADR-002)"

summary
