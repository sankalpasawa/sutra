---
part-id: L6
bucket: doc-layers
template: L13-release-note-style
parity-source: §14
parity-source-sha256: 0f0c51b02f1eaa1c0ef6e2672fd56697986c3d65b15f0f1990832992208c4731
status: DRAFT v1
authored: 2026-05-09
---

# L6: PRD (Product Requirements Document) + Evidence Log

## Purpose (what this layer answers)

What Native is building, for whom, why, with what success criteria — plus an Evidence Log appendix grounding the PRD in research, interview quotes, observed pain points, and assumption log. Per holding/PRODUCT-DOC-STANDARD.md §3 / L6: "what we are building, for whom, why, with what success criteria … Evidence Log appendix (REQUIRED): without this, folklore creeps into the PRD."

Native §14 ratified v1.1 — 18 capability blocks identified; v1 ships every block as stub minimum (P3); top-5 get full impl per §14.15.2 (B9 closed-loop artifact · B7 pre/post LLM validation · 7d lifecycle orchestrator · B5 explanation control · B18 person formation).

## Producer

Founder + PM. Per holding/PRODUCT-DOC-STANDARD.md §3 / L6 (`Owner: Founder + PM`). Native instance NATIVE-ENGINE.md §14 status: "claude-drafted from canon + directions + memory + agent research; founder reviewed in-session; all goals/risks/metrics/JTBD/non-goals/solution-overview accepted; Q1/Q4/Q5/Q6/Q8 founder signoff complete per codex consult round-3 gate".

## Consumer

- L8 Feature Spec authors (PRD gates feature scope; §14.15.2 outcome-ordering drives §16 sequence)
- L9-L10 Tech Spec + ADR authors (PRD lock precedes tech work per holding/PRODUCT-DOC-STANDARD.md §6 default-gating rule)
- L12 Roadmap author (roadmap derived from PRD + Features + OKRs)
- Codex review (PRD codex-consults gate before implementation; round-3 ratified v1.1)
- Founder (PRD is the single integrative artifact for "what we ship")

## Cadence

Per major requirement shift. Per holding/PRODUCT-DOC-STANDARD.md §3 / L6 (`Cadence: per major requirement shift`) and §8 ("Per major requirement shift: rewrite L6 PRD + L7 PRFAQ").

## Ratification rules

- DRAFT → RATIFIED requires founder direct ratification per holding/PRODUCT-DOC-STANDARD.md §7.
- HARD gate per holding/PRODUCT-DOC-STANDARD.md §6 default-gating: "L6 PRD must exist before L8 Features start. L8 Features must exist before L9-10 Tech work starts."
- Evidence Log is REQUIRED appendix per holding/PRODUCT-DOC-STANDARD.md §3 / L6 — Native §14.11 satisfies.
- Required PRD sections per L6 spec: Problem · Persona · JTBD (Christensen/Ulwick metric statements) · Job Story (Intercom format) · Goals · Non-goals · Solution overview · Risks · Success metrics · Open questions · Evidence Log. Native §14.1-§14.11 satisfies all 11.
- Codex consult gate per D40 G2 (codex consult before any Depth ≥ 3 edit) — Native §14 went through codex round-3.
- §14.10 founder signoff on Q1/Q4/Q5/Q6/Q8 explicitly noted as ratification trace per §14 v1.1 status.

## Native instance (where this layer lives in canon)

`sutra/os/engines/NATIVE-ENGINE.md` §14 (PRD — L6 per holding/PRODUCT-DOC-STANDARD.md). Sub-sections: §14.0 Concise PRD · §14.1 Problem · §14.2 Persona · §14.3 JTBD · §14.4 Job Story · §14.5 Goals · §14.6 Non-goals · §14.7 Solution Overview · §14.8 Risks · §14.9 Success Metrics · §14.10 Open Questions · §14.11 Evidence Log · §14.12 §10-§13 derivation note · §14.13 Foundation Index · §14.14 Process for Continuous Evolution · §14.15 Implementation Kickoff Framework · §14.16 TODO Sweep.

## References

- holding/PRODUCT-DOC-STANDARD.md §3 (15-layer pipeline) + §3 L6 specification + §4 tier-inheritance + §5 Native exception (D54 canon discipline) + §6 population workflow (gating rule) + §7 status rules + §8 maintenance cadence
- NATIVE-ENGINE.md §14 (PRD) — Native realization of L6
- NATIVE-ENGINE.md §14.11 Evidence Log — required appendix
- NATIVE-ENGINE.md §14.15.2 outcome-ordering — drives Top-5 §16 Feature Spec sequence
- Asawa-authored PRD template influenced by Google-style PM/design docs; JTBD per Christensen+Ulwick; Job Story per Intercom/Klement per holding/PRODUCT-DOC-STANDARD.md §2 anchors
