---
part-id: P16
bucket: pillars
template: L1-pov
parity-source: FOUNDER-DIRECTIONS.md §D10 + TEST-IN-PRODUCTION.md proof ledger + test-in-production-check.sh
parity-source-sha256: 2eb7f1ba40fcd547a454c271409938b01e82e99bb3c3b6463cef1e8647dbdf26
status: DRAFT v1
authored: 2026-06-12
---

# P16: Test everything in production

## Pillar statement

> No protocol, primitive, or system artifact ships without deployment to a real company and validation through a real feature. Per FOUNDER-DIRECTIONS.md D10 (founder verbatim): *"Whenever you create something at Asawa/Sutra level, it has to be immediately tested by real life."* A part without production proof is EXPERIMENTAL by definition and may not graduate to TESTED.

## What this rules in

- A required PROOF field on every shipped part: **Company / Feature / What-it-caught / Date** — ported verbatim from the TEST-IN-PRODUCTION.md ledger schema (ENFORCEMENT: HARD; no proof = EXPERIMENTAL, cannot graduate).
- A Stop/session-end sensor that diffs newly added spec/canon files against the proof ledger and warns on gaps — production shape: `test-in-production-check.sh` (plugin) + the inlined Stop-event check in `dispatcher-stop.sh` warning "New system artifacts created but not tested in production", enumerating each file.
- Gating the EXPERIMENTAL→TESTED state transition on a ledger row, so the gate and the doctrine are one mechanism — aligns with Native's existing dogfood-gated promotion (`../impl-phases/phase-E-ship-iterate.md`: founder-dogfoods before promotion; T1/T2 dogfood evidence).
- A live proof-status table per protocol/part as the observable surface of the invariant.

## What this rules out

- Shipping a protocol/primitive validated only by review, tests-in-isolation, or authoring-time reasoning — real-life validation through a real feature is the bar.
- Speculative parts with no consuming company or feature (composes with D15: every protocol triggered by real incident).
- Graduating an EXPERIMENTAL part on elapsed time or author confidence instead of a proof row.
- Label drift between sensor and doctrine going unrecorded — production carries a known internal "D1" label drift in the hook header; behavior matches D10. Port the lesson: sensor labels must trace to the doctrine ID.

## Falsification test

**If a part-file or protocol reaches shipped/TESTED status with no proof row (company + real feature + what-it-caught + date) in the proof ledger → P16 broken.** (Falsification test newly authored from the production behavior contract — no §10.3 row exists; P16 is a post-cutover gap-fill.)

## Doctrine inheritance (from L0)

P16 is not in the §10.4 doctrine-tension table (authored post-cutover as a canon gap-fill); no tension is logged. Inheritance via L0 generally — Customer Focus First (`./P0-customer-focus-first.md`): production proof is the only evidence an output actually served a real reader. Alignment with the Dynamic test is direct (the system learns from what production catches, not from what authors predict).

(If a tension exists in practice but is not in §10.4, this is a gap to surface via future ADR rather than invent inline.)

## References

- holding/FOUNDER-DIRECTIONS.md §D10 — doctrine + founder verbatim (production evidence).
- holding/TEST-IN-PRODUCTION.md — governing ledger: rule, PROOF schema, EXPERIMENTAL/TESTED graduation (production evidence).
- holding/DIRECTION-ENFORCEMENT.md row D10 — TRIGGER/CHECK/ENFORCEMENT (SOFT session-end sensor)/STATUS ACTIVE (production evidence).
- sutra/marketplace/plugin/hooks/test-in-production-check.sh — Stop-event sensor logic (production evidence; carries D1 label drift, behavior matches D10).
- holding/hooks/dispatcher-stop.sh — inlined Stop-event check (production evidence).
- `../impl-phases/phase-E-ship-iterate.md` — dogfood mechanics this pillar makes doctrinal (cross-bucket; mechanics NOT duplicated here).
- `./P0-customer-focus-first.md` — doctrine parent.
- Parity-source deviation: canon GAP — content does not exist in NATIVE-ENGINE.md; parity-source anchors point at the production source docs per MIGRATION-PLAN §9 limitation #2.
