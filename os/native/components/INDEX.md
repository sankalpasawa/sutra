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

Two additions, both legal under existing rules: (1) the **Exposure Contract**, a cross-cutting facet declared by every block (see matrix below); (2) the **UI Kit**, which renders those projections inside the existing **UI block**. Zero new §1.0 blocks, zero new arrow types. Reads gated by the Authority+Tenancy wrap.

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

One row per §1.0 block: what it exposes to the operator, which component renders it, and the truth-class of that data (ADR-023 Decision 1b). **Bold component = v1 scope.**

| Block | Operator-visible projection | Component | Truth-class |
|---|---|---|---|
| Authority + Tenancy | domain tree + subdomains · charter viewer · trust-ladder position · tenant switcher | **C2** | authoritative (registry) |
| Orchestration | EMERGE proposal inbox · routing decisions · confirm-backs | **C1** (proposals) | eventually-consistent |
| (Authority gate) | pending approvals `E-<id>` | **C1** | eventually-consistent |
| System of Process | live executions · step progress · failures | **C3** | ephemeral (live) |
| System of Record | audit replay · decision-provenance browser | C-future | authoritative |
| External World | connector status | C-future | mixed |
| Host | session status · skill-mode indicator (SM1-SM3) | C-future | ephemeral |
| Compute | token / resource usage | C-future | mixed |
| UI | UI-local state only (active tenant · unread count · verbosity prefs) | n/a (renderer) | local |

**v1 = C1 · C2 · C3.** All C-components inherit **P6** (default-quiet · operator-tunable verbosity · no surface inversion) — stated once here, governs every component (ADR-023 Decision 4).

## HLD prerequisite surfaced by this work (canon gap)

The **UI block has no canon part-file**. The §1.0.1 UI-block behavior — F.x trust gates (F.1 ask-before-acting, F.2 reversibility tags, F.5 ask-vs-act), G.x error surfaces (G.2 plain-words failures), M1-M6 modalities — lives ONLY in the frozen monolith `holding/website/native/master/index.html` §2.F. Components that cite this behavior (C1 cites F.x; C3 cites G.2) currently have NO canonical anchor. **Prerequisite before LLD lock:** migrate the UI block (§2.F / #so-ui) into a canon part-file, then re-point component citations at it. Until then, C1/C3 cite the frozen monolith via ADR-023 Context, flagged in their open gaps.

## LLD members (GATED behind HLD lock)

| ID | Component | Status | Dual-lane (codex+deepseek) |
|---|---|---|---|
| [C1](C1-approval-inbox.md) | Approval Inbox | DRAFT, PARKED | PASS-WITH-MODIFY — provenance (F.x), P6 line, L8 sections |
| [C2](C2-charter-domain-browser.md) | Charter + Domain Browser | DRAFT, PARKED | PASS-WITH-MODIFY — P6 line, tenant_id sourcing |
| [C3](C3-whats-running-board.md) | What's-Running Board | DRAFT, PARKED | PASS-WITH-MODIFY — fixed: step_completed, no step-total, state=success, G.2 re-sourced |

LLD is unparked only after the founder locks this HLD and the UI-block canon prerequisite is resolved.
