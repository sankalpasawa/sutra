---
part-id: L4
bucket: doc-layers
template: L13-release-note-style
parity-source: §13
parity-source-sha256: 6965dff71d90fbe398d7ba1fbdafb81cbb3ed4e442b8547e947d7cea3bb91f9d
status: DRAFT v1
authored: 2026-05-09
---

# L4: Strategy Map (HOW — winning shape)

## Purpose (what this layer answers)

HOW Native wins — Wardley map of value chain + evolution stage; build/buy/host boundary; competitive positioning; defensible position (5-year); strategic bets + anti-bets. Per holding/PRODUCT-DOC-STANDARD.md §3 / L4: "how the product wins. Wardley map of value chain + evolution stage; build/buy/host boundary; competitive positioning."

## Producer

Founder. Per holding/PRODUCT-DOC-STANDARD.md §3 / L4 (`Owner: Founder`). Native instance NATIVE-ENGINE.md §13 status: "claude-drafted from agent A3 external landscape + A4 framework picks + founder voice; founder reviewed in-session; Wardley map + Build/Buy/Host + competitive positioning + 5-yr defensible position + strategic bets + anti-bets all accepted".

## Consumer

- Founder (decision frame for Build vs Buy vs Host across capabilities)
- Eng lead / claude / codex (architectural decisions inherit Build/Buy/Host boundaries from §13.2)
- L8 Feature Spec authors (every new feature checked against "is this on a Build/Buy/Host line?")
- L10 ADR authors (architecture decisions reference §13 strategy bets)
- T4 fleet operators (read positioning to set expectations vs competitors)

## Cadence

6-month review. Per holding/PRODUCT-DOC-STANDARD.md §3 / L4 (`Cadence: 6-month review`).

## Ratification rules

- DRAFT → RATIFIED requires founder direct ratification per holding/PRODUCT-DOC-STANDARD.md §7.
- Strategy CHANGES are case-by-case via ADR-NNN per NATIVE-ENGINE.md §14.14.5 (e.g., ADR-018 Native-v2-roadmap per holding/PRODUCT-DOC-STANDARD.md §5 mapping).
- Required artifacts per holding/PRODUCT-DOC-STANDARD.md §3 / L4: Wardley map (anchor=user need; X=genesis→commodity) + 1-page narrative + competitive comp table. Native §13.1-§13.6 satisfies — §13.1 Wardley ASCII · §13.2 Build/Buy/Host · §13.3 competitive positioning · §13.4 defensible position · §13.5 strategic bets · §13.6 anti-bets.
- Build/Buy/Host changes (e.g., flipping a HOST → BUILD) require explicit ADR.

## Native instance (where this layer lives in canon)

`sutra/os/engines/NATIVE-ENGINE.md` §13 (Strategy Map — L4 per holding/PRODUCT-DOC-STANDARD.md). Sub-sections §13.1 Wardley map · §13.2 Build/Buy/Host boundaries · §13.3 Competitive positioning · §13.4 Defensible position (5-year) · §13.5 Strategic bets · §13.6 Anti-bets. Per holding/PRODUCT-DOC-STANDARD.md §5 alternate mapping: L4 also expressible as ADR-018 (strategy decision record).

## References

- holding/PRODUCT-DOC-STANDARD.md §3 (15-layer pipeline) + §3 L4 specification + §4 tier-inheritance + §5 Native exception (D54 canon discipline) + §7 status rules + §8 maintenance cadence
- NATIVE-ENGINE.md §13 (Strategy Map) — Native realization of L4
- NATIVE-ENGINE.md §13.2 Build/Buy/Host — cross-ref to primitives (`../primitives/*.md`) for Build-tier items
- NATIVE-ENGINE.md §13.5 strategic bets — gating downstream L10 ADRs
- Wardley Mapping (Simon Wardley) + Geoffrey Moore "Crossing the Chasm" per holding/PRODUCT-DOC-STANDARD.md §2 anchors
