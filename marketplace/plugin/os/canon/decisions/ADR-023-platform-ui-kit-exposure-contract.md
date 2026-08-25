<!-- MIRROR (read-only distribution copy). Canonical: sutra/os/decisions/ADR-023-platform-ui-kit-exposure-contract.md. -->
# ADR-023: Platform UI Kit + Per-Block Exposure Contract

**Status**: Accepted (founder direction 2026-06-13; dual-lane reviewed — codex + deepseek both PASS-WITH-MODIFY, placement CONFIRMED; 4 convergent modifications absorbed below)
**Date**: 2026-06-13
**Context anchor**: founder direction 2026-06-13 (expose governance — domains/subdomains/charters/what-is-running — as operator-facing UI; per-block user-facing exposure; core UI components as a platform layer). Evidence of the gap: master doc §1.4 names Charter Console + Workforce Status with zero spec; §1.4.3 rules "small UI panels don't" pass the Module test yet defines no category for them; canon has 0 hits for console/dashboard/browser across 113 part-files; gate.md §14.7 declares the founder-notification channel an unspecified runtime choice.

## Context

Native's operator-facing surface in canon is CLI/file-minimal: 2 commands (`sutra-native tenant list`, `sutra-native run <id>`), 3 utterances (`approve E-<id>`, `reject E-<id> <reason>`, `approve P-<id>`), pending-approval JSON files, raw per-Tenant JSONL logs. The interaction model is well-specified (UI block: Channels/Ask/Receive, M1-M6 modalities, M5 approval card, F.2 reversibility tags, F.3 audit replay, 4 operator-visible states) — but no component layer renders governance state, and no category exists for UI units below Module granularity.

## Decision 1 — PLACEMENT (decided first, per founder; both reviewers CONFIRMED)

§1.0 stays locked; no new block (ADR-021 precedent). The capability splits into two halves with different homes:

| Half | Nature | Architectural home | Canon home |
|---|---|---|---|
| **Exposure Contract** | engine-side, per-block typed declaration: which of the block's state may surface to the operator, as named read-only projections | metadata on each of the 8 §1.0 blocks (analogous to the pillar×block matrix) | new "Operator exposure" section in each relevant part-file + one summary matrix (follow-up work orders) |
| **Reference UI Kit** | render-side component library — a **reference implementation**, not the only allowable rendering | **Layer-A deliverable** where Layer-A means OWNERSHIP / SPECIFICATION / DISTRIBUTION (a design system), **consumed by products through the UI block's Receive part** | this ADR + component specs as work orders |

**Render-only boundary (load-bearing canon, per both reviewers M1):** the UI Kit is **NOT a runtime participant** — not a scheduler, not a state owner, not a new engine surface, mutates no domain state. It is a platform-provided render library consumed by products/modules through the existing UI block. "Layer-A" denotes who owns/ships/specs it, NOT a runtime block; it requires no ninth §1.0 block.

## Decision 1b — Operator Read Model (absorbed from codex M2 + deepseek F2, the CRITICAL finding)

Components do NOT read "System of Record" purely — that overclaims audit-grade truth for live operational state. v1 reads project over a typed **Operator Read Model** sourced from three places, each field tagged by truth-class:

| Source | Truth-class | Examples |
|---|---|---|
| System of Record events | **authoritative / durable** | settled approvals, completed executions, decision-provenance, charter registry |
| Orchestration pending-state | **eventually-consistent** | pending approvals, EMERGE proposals, confirm-backs in flight |
| System of Process runtime | **ephemeral** | live execution status, step progress, not-yet-recorded failures |

**Dependency, stated honestly:** full-fidelity Approval Inbox + What's-Running Board require **ADR-022 #1 (SoR truth upgrade)** to land first. v1.0 MAY ship with degraded fidelity (ephemeral fields flagged "live, not yet durable") until SoR captures all required state. The read model is read-only; the only write-backs remain the existing `approve`/`reject` utterance paths.

## Decision 2 — Category: component ≠ Module (with hard tests, per both reviewers M3)

Real taxonomy, not naming — enforced by tests:

| Test | Component | Module |
|---|---|---|
| Independent lifecycle / charter / authority / deployment / product identity | NO | YES |
| May own engine behavior or mutate domain state | NO | NO (composes those that don't either) |
| Renders exposure-contract projections | YES (one or more) | via its components |
| Owns workflow / navigation semantics | NO | YES |

→ Approval Inbox = component; Charter Console = Module (composes charter viewer + domain-tree browser + approval inbox). Components version as part of the UI Kit (Layer-A release track); no independent component deployment; a component MAY be promoted to Module if it later passes the §1.4.3 four-test.

## Decision 3 — Per-block exposure + field-level policy (absorbed from codex M4 + deepseek F4)

Block-level projection names are necessary but NOT sufficient — governance UI exposes sensitive cross-domain metadata. Each exposure-contract entry declares a typed row: **projection name · source block · truth-class · tenant scope · required capability/role · redaction rules · freshness/SLA · auditable(y/n)**.

| Block | Operator-visible projections |
|---|---|
| Authority + Tenancy | domain tree + subdomains · charter viewer · approval inbox · trust-ladder position · tenant switcher |
| System of Process | what's-running board (live executions, step progress, failure states) |
| System of Record | audit replay viewer · decision-provenance browser |
| Orchestration | routing decisions · EMERGE proposal inbox · confirm-backs |
| External World | connector status |
| Host | session status · skill-mode indicator (SM1-SM3) |
| Compute | token/resource usage |
| UI | UI-LOCAL state only (active tenant · channel · modality · unread-approval count · render errors · verbosity prefs) — never engine projections (codex M5) |

**Cross-domain operators:** "tenant-scoped by construction" is the default deny; a domain tree spanning subdomains across tenants requires an explicit **super-tenant / delegated read capability** (extends ADR-006 `delegates_to`), not naive per-tenant filtering that would break the hierarchy view.

## Decision 4 — v1 scope + constraints

v1 components (3): **Approval Inbox** (closes gate.md §14.7 notification gap) · **Charter + Domain Browser** (gives Charter Console its spec base) · **What's-Running Board** (gives Workforce Status its spec base). Every component inherits P6: default-quiet, operator-tunable verbosity, no surface inversion.

## Consequences

- gate.md §14.7 gap closes via Approval Inbox.
- Charter Console + Workforce Status get spec'd as compositions, not orphan names.
- Block part-files gain an "Operator exposure" section with the field-level schema above — follow-up work orders, gated on ADR-022 #1 for live-state fidelity.
- The render-only guard becomes load-bearing canon: components render, never participate in runtime; exposure contracts live engine-side; neither crosses.
- Module catalog (§1.4) unchanged; products embed kit components via their UI block.

## Dual-lane review (PROTO-019) — 2026-06-13

Both lanes **PASS-WITH-MODIFY**; **placement decision (Decision 1) explicitly CONFIRMED sound by both**; no REJECT. Four convergent modifications (raised independently by both) absorbed above:

| # | Modification | codex | deepseek | Absorbed in |
|---|---|---|---|---|
| M1 | UI Kit ≠ runtime participant; "Layer-A" = ownership/spec, not a block | F1 | F1 | Decision 1 render-only boundary |
| M2 | Replace SoR-purity claim with 3-source Operator Read Model + ADR-022 #1 dependency | F2 (critical) | F2 (critical) | Decision 1b |
| M3 | "component ≠ Module" needs hard tests or it's naming | F3 | F3 | Decision 2 test table |
| M4 | Field-level exposure policy + cross-domain/super-tenant scope | F4 | F4 | Decision 3 field schema |

deepseek-only: exposure contract needs a concrete schema (F5) → folded into Decision 3 typed row. codex-only: UI-local state is legitimate (F5) → Decision 3 UI row. Gate-log: `.enforcement/{codex,deepseek}-reviews/gate-log.jsonl`.
