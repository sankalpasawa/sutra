---
part-id: L2
bucket: doc-layers
template: L13-release-note-style
parity-source: §11
parity-source-sha256: 190a4148245d48ddee3aa6f7d3c997639e4c3743cab7344a95c12a497f87e1dd
status: DRAFT v1
authored: 2026-05-09
---

# L2: Vision + North Star Metric (5-year future state)

## Purpose (what this layer answers)

What the world looks like 5 years out IF Native wins — the far-future picture — plus the single leading-indicator North Star Metric (N*) tied to customer value. Per holding/PRODUCT-DOC-STANDARD.md §3 / L2: "what the world looks like 5 years out IF the product wins. The far-future picture." Required field is the N* metric (name + numeric target + measurement window).

Native's N* = Operator-Hours-Saved per Week (OHS/wk). See NATIVE-ENGINE.md §11.2.

## Producer

Founder. Per holding/PRODUCT-DOC-STANDARD.md §3 / L2 (`Owner: Founder`). Native instance NATIVE-ENGINE.md §11 status note: "claude-drafted from §14 PRD problem space + founder voice + agent A3 landscape; founder reviewed in-session; Vision paragraph + OHS/wk N* + leading inputs + 5-yr winning targets + v2 trigger all accepted".

## Consumer

- Founder (anchor for quarterly OKR + roadmap re-prioritization)
- L11 OKRs author (every quarter's KRs MUST move N* needle, OR explicit reason why not per L11 spec)
- L4 Strategy Map author (strategy bets are defended against 5-yr picture)
- L6 PRD §14.9 Success Metrics (PRD success metrics anchor on L2 N* per NATIVE-ENGINE.md §14.9 "anchored on L2 North Star §11")
- T4 fleet operators (read 5-yr picture to set adoption expectations)

## Cadence

Yearly review. Per holding/PRODUCT-DOC-STANDARD.md §3 / L2 (`Cadence: yearly review`) and §8 ("Yearly: re-examine L1 Philosophy + L2 Vision + L3 Mission").

## Ratification rules

- DRAFT → RATIFIED requires founder direct ratification per holding/PRODUCT-DOC-STANDARD.md §7.
- N* metric must include: Name + numeric target + measurement window per holding/PRODUCT-DOC-STANDARD.md §3 / L2 ("Required field: North Star Metric (single leading-indicator metric tied to customer value; format: name + numeric target + measurement window)"). Native §11.2 satisfies — name=OHS/wk, target=≥3 OHS/wk at 14d post-install (v1) / ≥20 OHS/wk (v3), measurement = audit-derived from auto-run lifecycle phases + operator weekly survey.
- v2 expansion trigger documented per NATIVE-ENGINE.md §11.5 ("≥3 T4 clients green for 14d, OR ≥1 T2 portfolio company blocked on Native upgrade" per D41).

## Native instance (where this layer lives in canon)

`sutra/os/engines/NATIVE-ENGINE.md` §11 (Vision + North Star Metric — L2 per holding/PRODUCT-DOC-STANDARD.md). Sub-sections §11.1 5-year vision paragraph · §11.2 N* metric block · §11.3 Leading inputs · §11.4 What "winning" looks like (5-year picture) · §11.5 v1→v2 validation trigger.

## References

- holding/PRODUCT-DOC-STANDARD.md §3 (15-layer pipeline) + §3 L2 specification + §4 tier-inheritance + §5 Native exception (D54 canon discipline) + §7 status rules + §8 maintenance cadence
- NATIVE-ENGINE.md §11 (Vision + N*) — Native realization of L2
- NATIVE-ENGINE.md §11.2 N* metric — cross-ref to `../metrics/north-star-ohs-per-week.md`
- NATIVE-ENGINE.md §14.9 Success Metrics — PRD KRs anchor here
- Sean Ellis / Amplitude North Star Playbook + Collins BHAG per holding/PRODUCT-DOC-STANDARD.md §2 anchors
