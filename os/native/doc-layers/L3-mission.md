---
part-id: L3
bucket: doc-layers
template: L13-release-note-style
parity-source: §12
parity-source-sha256: 57ee76e16216d9dc5630392b6f55c77ca95452e58a1f27525a770af238fcde25
status: DRAFT v1
authored: 2026-05-09
---

# L3: Mission (present operating promise)

## Purpose (what this layer answers)

Present-tense, 1-sentence statement of what Native does for whom TODAY. Per holding/PRODUCT-DOC-STANDARD.md §3 / L3: "present-tense, 1-sentence statement of what the product does for whom TODAY. Format: 1 sentence. Action verb + audience + outcome."

Native's mission statement (NATIVE-ENGINE.md §12.2): operating system that runs alongside a manager-IC day-to-day — executing projects, picking one-off tasks, surfacing decisions, learning taste/decision-style/voice, personalizing thinking, carrying picked work through analysis → decision → build → operationalize → auto-run.

## Producer

Founder. Per holding/PRODUCT-DOC-STANDARD.md §3 / L3 (`Owner: Founder`). Native instance NATIVE-ENGINE.md §12 status: "claude-drafted from founder high-level capability list 2026-05-09 + §14 PRD problem statement; founder reviewed in-session; Q11/Q12/Q13/Q14 answered + Q12 P7-tightening applied per codex consult round-3".

## Consumer

- Founder (north star for what Native is doing TODAY vs aspirational)
- Claude / codex / subagent dispatches (mission-coherence gate — does this action serve the mission?)
- L6 PRD problem statement author (mission is the present-tense baseline; PRD scopes the gap)
- T4 fleet operators on first-install (read mission to verify fit with their work)

## Cadence

Yearly review. Per holding/PRODUCT-DOC-STANDARD.md §3 / L3 (`Cadence: yearly review`) and §8 ("Yearly: re-examine L1 Philosophy + L2 Vision + L3 Mission").

## Ratification rules

- DRAFT → RATIFIED requires founder direct ratification per holding/PRODUCT-DOC-STANDARD.md §7.
- Must compress to ONE sentence per L3 spec. Native §12.2 satisfies — single sentence covering all 7 founder capabilities from §12.1 verbatim list.
- Mission CHANGES are case-by-case via ADR-NNN per NATIVE-ENGINE.md §14.14.5 ("§11 Vision · §12 Mission · §13 Strategy Map · §14 PRD — CASE-BY-CASE via new ADR-NNN").
- Capability gaps (§16 feature specs) tracked per founder capability per NATIVE-ENGINE.md §12.3 capability map.

## Native instance (where this layer lives in canon)

`sutra/os/engines/NATIVE-ENGINE.md` §12 (Mission — L3 per holding/PRODUCT-DOC-STANDARD.md). Sub-sections §12.1 founder voice verbatim · §12.2 mission statement · §12.3-§12.X capability map + multi-round founder voice + capability extensions (§12.5-§12.42+).

## References

- holding/PRODUCT-DOC-STANDARD.md §3 (15-layer pipeline) + §3 L3 specification + §4 tier-inheritance + §5 Native exception (D54 canon discipline) + §7 status rules + §8 maintenance cadence
- NATIVE-ENGINE.md §12 (Mission) — Native realization of L3
- NATIVE-ENGINE.md §12.3 capability map → primitives (`../primitives/*.md`) + §16 feature gaps (queued)
- NATIVE-ENGINE.md §12.4 Q11-Q14 founder review questions (answered)
- Drucker + HBS mission-statement pattern per holding/PRODUCT-DOC-STANDARD.md §2 anchors
