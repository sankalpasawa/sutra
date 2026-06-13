---
part-id: components-INDEX
bucket: components
template: HLD-overview
parity-source: ADR-023 (net-new; post-cutover canon)
status: DRAFT v1 — HLD
authored: 2026-06-13
---

# Components — Platform UI Kit (HIGH-LEVEL DESIGN)

The operator-facing governance UI. This INDEX holds the **high-level design**: where the UI Kit + Exposure Contract fit in the architecture block diagrams. The C-numbered part-files (C1, C2, C3) are the **low-level design** for individual components and are GATED behind HLD lock.

Governing decision: [ADR-023](../../decisions/ADR-023-platform-ui-kit-exposure-contract.md).

## HLD placement — 3 diagram altitudes

### Altitude 1 — §1.0 runtime schema (NO new block)

```
        +------- Authority + Tenancy wrap (gates every projection read) -------+
        |                                                                       |
 HUMAN <-> [ UI ] --> [ Host ] --> [ Daemon: Orchestration -> SoP ] --> [ SoR ] [ External World ]
            ^  ^                          |            |                  |          |
            |  +-- UI KIT renders here ---+------------+------------------+----------+
            |       (read-only projections, upward)
            |
   EXPOSURE CONTRACT = cross-cutting FACET on each of the 8 blocks
   (like the pillar x block matrix — a property, not a box)
                           [ Compute base ]
```

Two additions, both legal under existing rules: (1) the **Exposure Contract**, a cross-cutting facet each block WILL declare (see matrix — **provisional** until the §1.0 architecture blocks have canon homes, [ADR-024](../../decisions/ADR-024-arch-block-canon-fork.md)); (2) the **UI Kit**, which renders those projections inside the existing **UI block**. Zero new §1.0 blocks, zero new arrow types. Reads gated by the Authority+Tenancy wrap.

**Dual-role clarifications (dual-lane review):** the UI block is both *render host* (it hosts the UI Kit) and an *exposure subject* (it exposes UI-local state) — distinct roles, not a loop. Authority+Tenancy is both *gatekeeper* (gates every read) and *data source* (owns the domain/charter registry) — a read through the gate is access-checked; the registry it serves is the durable source. Distinct, not redundant.

### Altitude 2 — inside the UI block (§1.0.1 second-order)

```
 [ UI BLOCK ]  Channels | Ask | Receive
                                  └── Receive
                                       ├── M1-M6 modalities
                                       ├── Standing Surfaces (Daily Pulse ...)
                                       └── GOVERNANCE SURFACES  <-- UI Kit, render-only
```

The UI Kit is a new render-only area in **Receive**, a sibling of the M1-M6 modalities and Standing Surfaces. It renders; it never executes (existing render-only guard).

### Altitude 3 — product hierarchy (§1.4 Layer A/B/C/D)

```
 LAYER A PLATFORM   Native + [ UI KIT ]   <-- Layer-A deliverable (a design system)
 LAYER B PRODUCT    CoS embeds kit components in its UI block
 LAYER C MODULE     Charter Console = C2 + C1 ; Workforce Status = C3
 LAYER D DEPLOYMENT per-operator config of which surfaces show
```

## Exposure Matrix (the cross-cutting facet — chosen rendering per founder 2026-06-13)

> **PROVISIONAL** (dual-lane review 2026-06-13). This matrix asserts what each §1.0 block *will* expose, but the architecture blocks have no canon part-files yet (see arch-block fork, [ADR-024](../../decisions/ADR-024-arch-block-canon-fork.md)). It is a planning summary, not a per-block declaration, until those homes exist. The rows below are **prose; they must become a versioned, testable exposure schema** (per-field) before implementation, or policy drifts across components.

One row per §1.0 block (one row per block — the pending-approvals projection folds into Authority+Tenancy, not a separate row): what it exposes, which component renders it, truth-class (ADR-023 Decision 1b). **Bold = v1 scope.**

| Block | Operator-visible projection | Component | Truth-class |
|---|---|---|---|
| Authority + Tenancy | domain tree + subdomains · charter viewer · trust-ladder position · tenant switcher · pending approvals `E-<id>` | **C1**, **C2** | authoritative (registry) + eventually-consistent (pending) |
| Orchestration | EMERGE proposal inbox `P-<id>` · routing decisions · confirm-backs | **C1** (proposals) | eventually-consistent |
| System of Process | live executions · step progress · failures | **C3** | ephemeral (live) |
| System of Record | audit replay · decision-provenance browser | C-future | authoritative |
| External World | connector status | C-future | mixed |
| Host | session status · skill-mode indicator (SM1-SM3) | C-future | ephemeral |
| Compute | token / resource usage | C-future | mixed |
| UI | UI-local state only (active tenant · unread count · verbosity prefs) | n/a (render host) | local |

**v1 = C1 · C2 · C3.** All C-components inherit **P6** (default-quiet · operator-tunable verbosity · no surface inversion) — ADR-023 Decision 4.

### Render-only / control boundary (dual-lane must-fix)

The UI Kit RENDERS read-only projections. Where a component offers an action (C1's approve/reject), the action is NOT a component mutation — it submits an EXISTING utterance through the Ask → GATE/EMERGE path. Every action component MUST: re-check capability at action time, handle stale rows (the row changed since render), be idempotent (double-tap = one effect), and correlate to the resulting EngineEvent + DecisionProvenance for audit.

### Truth-class reconciliation (dual-lane must-fix)

When a component renders fields of different truth-class for the same entity (C1: Orchestration `pending` vs System-of-Record `settled`), **authoritative wins**: a settled SoR state overrides an eventually-consistent pending view; pending rows render with a `provisional` marker until the durable state lands. This prevents the "operator acts on a stale approved row" hazard.

## HLD prerequisite surfaced by this work (canon gap)

The **UI block has no canon part-file**. The §1.0.1 UI-block behavior — F.x trust gates (F.1 ask-before-acting, F.2 reversibility tags, F.5 ask-vs-act), G.x error surfaces (G.2 plain-words failures), M1-M6 modalities — lives ONLY in the frozen monolith `holding/website/native/master/index.html` §2.F. Components that cite this behavior (C1 cites F.x; C3 cites G.2) currently have NO canonical anchor. **Prerequisite before LLD lock:** migrate the UI block (§2.F / #so-ui) into a canon part-file, then re-point component citations at it. Until then, C1/C3 cite the frozen monolith via ADR-023 Context, flagged in their open gaps.

## LLD members (GATED behind HLD lock)

| ID | Component | Status | Dual-lane (codex+deepseek) |
|---|---|---|---|
| [C1](C1-approval-inbox.md) | Approval Inbox | DRAFT, PARKED | PASS-WITH-MODIFY — provenance (F.x), P6 line, L8 sections |
| [C2](C2-charter-domain-browser.md) | Charter + Domain Browser | DRAFT, PARKED | PASS-WITH-MODIFY — P6 line, tenant_id sourcing |
| [C3](C3-whats-running-board.md) | What's-Running Board | DRAFT, PARKED | PASS-WITH-MODIFY — fixed: step_completed, no step-total, state=success, G.2 re-sourced |

LLD stays **DRAFT (not normatively locked)** — dual-lane (CHANGES-REQUIRED, 2026-06-13) confirmed C1/C3 cannot lock until the arch-block canon fork ([ADR-024](../../decisions/ADR-024-arch-block-canon-fork.md)) resolves their F.x/G.x provenance. C2 is low-risk (durable-registry only). Unpark after ADR-024 + founder HLD lock.
