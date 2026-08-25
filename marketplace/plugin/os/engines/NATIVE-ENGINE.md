<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/engines/NATIVE-ENGINE.md (D54). Do not edit here. -->
# Sutra — Native Engine (INDEX)

**Status**: RATIFIED v2 (2026-05-09 — Phase 12.2 cutover landed; was 1888-line monolithic doc → 116-line INDEX). Pre-cutover snapshot tag: `pre-engine-rewrite` on Sutra HEAD. Pre-cutover archive: `holding/research/_archive/native-v1.x/INDEX-shadow-pre-cutover.md`. (14d decommission window + Phase 13 gate RETIRED 2026-05-12 per founder direction — canon writes resume normally; see MIGRATION-PLAN.md §3 Phase 13 + §6 retirement banners.)
**Canon scope**: this INDEX + 113 part files under `sutra/os/native/<bucket>/` + 14 ADRs at `sutra/os/decisions/ADR-004..017`. All three together = Native v1 canon.
**Governance**: per D54 (Native canon-only), forward writes route via `holding/skills/updating-native-canon.md`. Forbidden paths: `holding/research/*native*.md` + `holding/plans/native-*.md`. Migration: `sutra/os/native/MIGRATION-PLAN.md` (RATIFIED v1.1).
**Reading order**: start with §3 Bucket Map, then §4 §-anchor Remap to find the topic you came for, then §6 Reading Order for first-pass coverage.

---

## 1. What is Native?

Native is Sutra's runtime engine — typed primitives + 26 EngineEvents + 6 surfaces + 8 hardstops + 24 product blocks + 14 pillars, executing operator-declared workflows against a multi-tenant audit-durable substrate. The product layer (PRD / vision / mission / strategy / metrics / impl phases) lives alongside as L1-L14 founder-doc layers per `holding/PRODUCT-DOC-STANDARD.md`.

## 2. Canon shape (post-decomp)

113 part files in 11 buckets + 14 ADRs + this INDEX. No content lives only in the INDEX — the INDEX points; the part files hold.

## 3. Bucket Map

| Bucket | Count | What it holds | First file (anchor) |
|---|---:|---|---|
| [pillars/](../native/pillars/) | 14 | Doctrine — P1-P14 POVs, falsification tests, doctrine inheritance from §10.4 | [P1-artifact-first.md](../native/pillars/P1-artifact-first.md) |
| [primitives/](../native/primitives/) | 10 | Typed primitives — Domain, Charter, Workflow, Step, Trigger, ExecutionResult, EngineEvent, Tenant, DecisionProvenance, Approval | [workflow.md](../native/primitives/workflow.md) |
| [events/](../native/events/) | 26 | EngineEvent type catalog — schemas, emitters, consumers, ordering invariants, replayability | [workflow_started.md](../native/events/workflow_started.md) |
| [surfaces/](../native/surfaces/) | 6 | Surfaces — ROUTE, RUN, GATE, EMERGE, AUDIT, TENANT — interfaces + invariants + integration points | [ROUTE.md](../native/surfaces/ROUTE.md) |
| [hardstops/](../native/hardstops/) | 8 | HARD-STOP conditions HS-1..HS-8 — fail-modes + recovery paths | [HS-1-reflexive-check.md](../native/hardstops/HS-1-reflexive-check.md) |
| [blocks/](../native/blocks/) | 24 | Product feature blocks B1-B18 + sub-blocks 7a-7e + F1 — L8 Feature Specs | [B9-closed-loop-artifact.md](../native/blocks/B9-closed-loop-artifact.md) |
| [open-questions/](../native/open-questions/) | 11 | Q1-Q11 — research-log entries with default-if-unanswered + ratification log (all 11 ANSWERED 2026-05-09) | (see directory) |
| [doc-layers/](../native/doc-layers/) | 8 | Founder-owned doc layers L1/L2/L3/L4/L6/L7/L11/L14 — purpose + producer + consumer + cadence | [L1-philosophy.md](../native/doc-layers/L1-philosophy.md) |
| [impl-phases/](../native/impl-phases/) | 5 | §14.15.1 Phase A-E — gate + duration + DRI + acceptance criteria + dependencies | (see directory) |
| [metrics/](../native/metrics/) | 1 | North Star — OHS/wk (operator-hours-saved per week) | [north-star-ohs-per-week.md](../native/metrics/north-star-ohs-per-week.md) |
| [arch-blocks/](../native/arch-blocks/) | 1+7 | §1.0 architecture blocks — UI authored (DRAFT); Host/Orchestration/SoP/SoR/Authority+Tenancy/Compute/External-World SEED-pending; per ADR-024 | [ui.md](../native/arch-blocks/ui.md) |
| [components/](../native/components/) | 4 | UI Kit — HLD (INDEX: placement + exposure matrix) + LLD component specs C1-C3 (Approval Inbox, Charter+Domain Browser, What's-Running Board); render-only, per ADR-023 | [INDEX.md](../native/components/INDEX.md) |
| ADRs | 20 | Decision rationale — `sutra/os/decisions/ADR-004..023` (004-017 v1 canon; 018-023 post-cutover) | [ADR-004-registry-and-effector-split.md](../decisions/ADR-004-registry-and-effector-split.md) |

## 4. §-Anchor Remap (pre-decomp section → post-decomp home)

Use this table when something cites "per NATIVE-ENGINE.md §X.Y" written before the Phase 12.2 cutover.

| Pre-decomp anchor | Topic | Post-decomp home |
|---|---|---|
| §1 Purpose | Engine purpose statement | this INDEX §1 |
| §2 Primitives | 10 typed primitives | [primitives/](../native/primitives/) (10 files) |
| §3.1 Engine API | TypeScript signatures | runtime code (not canon-doc); see `sutra/marketplace/plugin/lib/native/` |
| §3.2 EngineEvent catalog | 26 event types | [events/](../native/events/) (26 files) |
| §3.3 CLI subcommands | `bin/sutra-native` | runtime code; see `sutra/marketplace/plugin/bin/sutra-native` |
| §3.4 Approval utterances | approval / reject / modify lexicon | [primitives/approval.md](../native/primitives/approval.md) |
| §3.5 Authoritative state | markdown vs code | [ADR-008-markdown-vs-code-authoritative-state.md](../decisions/ADR-008-markdown-vs-code-authoritative-state.md) |
| §4 Invariants (I-1..I-N) | runtime invariants | inline citations across [events/](../native/events/) + [primitives/](../native/primitives/); I-14 = terminal-event set |
| §5 Integrations | host-LLM, telemetry sink, cadence | [ADR-005](../decisions/ADR-005-host-llm-host-selection.md) + [ADR-013](../decisions/ADR-013-telemetry-sink-fsync-jsonl.md) + [ADR-017](../decisions/ADR-017-cron-daemon-cadence-tick.md) |
| §6.1-§6.4 Operations | telemetry / tenant / replica / cadence | [ADR-013](../decisions/ADR-013-telemetry-sink-fsync-jsonl.md) + [ADR-006](../decisions/ADR-006-tenant-isolation-domain-field.md) + [ADR-016](../decisions/ADR-016-replica-as-isolated-user-kit.md) + [ADR-017](../decisions/ADR-017-cron-daemon-cadence-tick.md) |
| §6.5 on_failure machinery | rollback / continue / abort policy | [ADR-011](../decisions/ADR-011-on-failure-policy-five-set.md) + [events/workflow_rollback_started.md](../native/events/workflow_rollback_started.md) + sibling rollback events |
| §6.6 Approval ledger | approval persistence | [primitives/approval.md](../native/primitives/approval.md) + [ADR-009](../decisions/ADR-009-approval-gate-primitive.md) |
| §6.7 Per-step timeout | timeout enforcement | [primitives/step.md](../native/primitives/step.md) |
| §6.8 Recovery | crash recovery | [hardstops/](../native/hardstops/) (HS-1..HS-8) |
| §6.9 HARD-STOP HS-1..HS-8 | hardstop catalog | [hardstops/](../native/hardstops/) (8 files) |
| §7 Threat Model | STRIDE + cross-tenant + reflexive-modify | [hardstops/](../native/hardstops/) + [ADR-006](../decisions/ADR-006-tenant-isolation-domain-field.md) |
| §8 Open Seams | known gaps for v2+ | [open-questions/](../native/open-questions/) (11 files) |
| §10 Philosophy / POV (L1) | foundational worldview | [doc-layers/L1-philosophy.md](../native/doc-layers/L1-philosophy.md) + [pillars/](../native/pillars/) (14 files) |
| §10.2 Pillars table | 14 pillar statements | [pillars/](../native/pillars/) (P1-P14) |
| §10.3 Falsification tests | per-pillar empirical falsifier | inline in each [pillars/](../native/pillars/) file |
| §10.4 Doctrine inheritance | upstream doctrines | inline in each [pillars/](../native/pillars/) file |
| §11 Vision + N* (L2) | 5-year picture + N* metric | [doc-layers/L2-vision.md](../native/doc-layers/L2-vision.md) + [metrics/north-star-ohs-per-week.md](../native/metrics/north-star-ohs-per-week.md) |
| §12 Mission (L3) | 1-year mission statement | [doc-layers/L3-mission.md](../native/doc-layers/L3-mission.md) |
| §13 Strategy Map (L4) | Wardley + competitive + bets | [doc-layers/L4-strategy.md](../native/doc-layers/L4-strategy.md) |
| §14 PRD (L6) | full PRD per Google/Cagan format | [doc-layers/L6-prd.md](../native/doc-layers/L6-prd.md) — also: published HTML at `holding/website/native/product-prd-2026-05-09-v2.html` (operator-observable v2) |
| §14.7 Solution Overview | surfaces overview | [surfaces/](../native/surfaces/) (6 files) |
| §14.10 Open Questions | Q1-Q10 + §12.4 Q11 | [open-questions/](../native/open-questions/) (11 files; ANSWERED 2026-05-09) |
| §14.13 Foundation Index | full canon table | this INDEX (you are here) |
| §14.14 Process | continuous evolution | `sutra/os/native/MIGRATION-PLAN.md` + future migration plans |
| §14.15.1 Phase A-E | impl roadmap | [impl-phases/](../native/impl-phases/) (5 files) |
| §14.15.2 Top-5 v1 outcome blocks | B9 + B7 + 7d + B5 + B18 | [blocks/](../native/blocks/) (24 files; 5 named flagged in each block's "v1 outcome" header) |
| §14.16 TODO Sweep | aggregated feature backlog | [blocks/](../native/blocks/) (subset; remaining items live as future blocks) |

## 5. ADR Map

| ID | Topic | When to read |
|---|---|---|
| [ADR-004](../decisions/ADR-004-registry-and-effector-split.md) | Registry + effector split | Native architecture overview |
| [ADR-005](../decisions/ADR-005-host-llm-host-selection.md) | Host-LLM selection | running workflows |
| [ADR-006](../decisions/ADR-006-tenant-isolation-domain-field.md) | Tenant isolation | multi-tenant operations |
| [ADR-007](../decisions/ADR-007-decision-provenance-schema.md) | DecisionProvenance schema | replay + audit |
| [ADR-008](../decisions/ADR-008-markdown-vs-code-authoritative-state.md) | Markdown vs code authoritative state | reading authoritative state |
| [ADR-009](../decisions/ADR-009-approval-gate-primitive.md) | Approval primitive | gate flows |
| [ADR-010](../decisions/ADR-010-organic-emergence-propose-approve.md) | Organic emergence | pattern-detection / proposals |
| [ADR-011](../decisions/ADR-011-on-failure-policy-five-set.md) | failure_policy 5-set | rollback / continue / abort |
| [ADR-012](../decisions/ADR-012-pnc-typed-parser-over-prose.md) | Typed parser over prose | Pre/Post-Node Check (PNC) |
| [ADR-013](../decisions/ADR-013-telemetry-sink-fsync-jsonl.md) | 3-channel audit durability | telemetry sink design |
| [ADR-014](../decisions/ADR-014-depth-router-via-workflow.md) | Depth router via workflow | depth routing |
| [ADR-015](../decisions/ADR-015-standalone-h-sutra-in-native.md) | H-Sutra in Native | governance integration |
| [ADR-016](../decisions/ADR-016-replica-as-isolated-user-kit.md) | Replica as isolated user-kit | dev / test isolation |
| [ADR-017](../decisions/ADR-017-cron-daemon-cadence-tick.md) | Cron daemon cadence | cadence scheduling |
| [ADR-018](../decisions/ADR-018-agentic-systems-pattern.md) | Agentic systems pattern | designing agent loops |
| [ADR-019](../decisions/ADR-019-design-product-tech-bridge.md) | Design↔product↔tech bridge | doc-layer navigation |
| [ADR-020](../decisions/ADR-020-layer-b-product-authoring-template.md) | Layer-B product authoring template | product authoring (PROPOSED) |
| [ADR-021](../decisions/ADR-021-sutra-plugin-host-residency.md) | Sutra plugin host residency | plugin placement in §1.0 schema |
| [ADR-022](../decisions/ADR-022-full-loop-six-mechanisms.md) | Full-loop six mechanisms | roadmap: record→system + organic growth |
| [ADR-023](../decisions/ADR-023-platform-ui-kit-exposure-contract.md) | Platform UI Kit + exposure contract | operator-facing governance UI |
| [ADR-024](../decisions/ADR-024-arch-block-canon-fork.md) | §1.0 arch-block canon fork (PROPOSED) | migrating architecture blocks into canon |
| [ADR-030](../decisions/ADR-030-four-problem-types.md) | Four Problem Types — T1 missing operationalisation · T2 the answer · T3 the workflow · T4 the question (doctrine lens, unwired) | classifying a unit at intake by what is missing; orthogonal to the Cynefin lens + ADR-026 workflow type |
| [ADR-031](../decisions/ADR-031-eval-engine.md) | Eval Engine — atom checks become standing eval cases, re-run nightly via Inspect AI + shared verify-runner; decay + verify-quality measurable (Accepted 2026-08-07) | re-checking finished work, regression diff on change, judge-lane grading of fuzzy checks |

## 6. Reading Order

For first-pass coverage of Native canon:

1. **Doctrine first** — read [pillars/P1-artifact-first.md](../native/pillars/P1-artifact-first.md) through P14 (~30 min) to internalize the POV.
2. **Primitives second** — read [primitives/workflow.md](../native/primitives/workflow.md) + step + execution-result + engine-event (~20 min) for the data-shape vocabulary.
3. **Events third** — skim [events/](../native/events/) catalog (26 files); deep-read the 5 lifecycle events (workflow_started / step_started / step_complete / workflow_completed / workflow_failed) (~20 min).
4. **Surfaces fourth** — read [surfaces/ROUTE.md](../native/surfaces/ROUTE.md) + RUN + GATE + EMERGE + AUDIT + TENANT (~30 min) for runtime topology.
5. **Hardstops fifth** — read all 8 [hardstops/](../native/hardstops/) (~20 min) for fail-mode boundaries.
6. **Blocks sixth** — read top-5 v1 outcome blocks: [B9](../native/blocks/B9-closed-loop-artifact.md) + B7 + 7d + B5 + B18 (~40 min) for what gets shipped first.
7. **Doc-layers seventh** — read [L1](../native/doc-layers/L1-philosophy.md) → L2 → L3 → L4 → L6 to ladder from POV to PRD.
8. **ADRs as needed** — consult [ADR-004..017](../decisions/) when implementing the corresponding subsystem.
9. **Open questions for v2 planning** — read [open-questions/](../native/open-questions/) when designing v2 features.

## 7. Governance Rules

- **D54 canon-only**: forward Native writes go to this INDEX, the 11 bucket directories, or the ADR directory. Forbidden: `holding/research/*native*.md`, `holding/plans/native-*.md`. Decision-tree skill: `holding/skills/updating-native-canon.md`.
- **MIGRATION-PLAN authority**: `sutra/os/native/MIGRATION-PLAN.md` (RATIFIED v1.1) is the operating contract for canon-shape evolution. (Phase 13 decommission gate RETIRED 2026-05-12 — see MIGRATION-PLAN.md §3 Phase 13 + §6 retirement banners; hook script deleted same day.)
- **Connectedness audit**: `holding/scripts/native-connectedness-audit.sh` — run before any cutover or major restructure to verify bucket completeness + link integrity + orphan-detection.
- **Codex review per change**: per PROTO-019 + D40 G2, every part-file authoring or amendment requires codex `consult` mode review at ADVISORY-or-better verdict before merge.
- **No new monolithic engine doc**: this INDEX is the only sutra/os/engines/NATIVE-ENGINE.md content post-cutover. Do not append new content here — append to the appropriate bucket file and (if needed) update the §-anchor remap row.

---

**Last updated**: 2026-05-13 — Phase 12.2 cutover landed 2026-05-09; Phase 13 decommission gate RETIRED 2026-05-12 per founder direction (14d window dropped; canon writes resume normally). Pre-cutover snapshot at git tag `pre-engine-rewrite`.
