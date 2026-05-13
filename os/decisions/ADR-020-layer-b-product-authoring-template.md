# ADR-020 — Layer-B Product authoring template (what every new Product PRD must include)

## Status

PROPOSED 2026-05-13 (R10 visual gaps audit fix · Bucket 4). Pending R11 codex + deepseek review. Anchored by PRD §1.4.4 multi-product Layer-B taxonomy.

## Context

Per PRD §1.4 Product Hierarchy + §1.4.4 Layer-B products, Native is a multi-product platform. CoS is one Layer-B Product (the first, flagship). Future Layer-B Products (Senior Expert · Project Manager · others TBD) sit at the same layer.

Without an authoring template, each new Layer-B Product PRD becomes a guess about which sections to include. R10 audit flagged this: "no authoring template saying what spec sections a new Layer-B product must add to canon" (codex D4 [P1] + deepseek D4 [P2]).

ADR-020 specifies the MINIMUM SECTIONS every new Layer-B Product PRD must include for canon coherence.

## Decision

A new Layer-B Product PRD MUST include the following section set (modeled on the CoS PRD at `holding/website/native/product-prd-native-v1.html` but specific to the new Product):

### Required sections (every Layer-B Product PRD)

| # | Section | Purpose | Example (CoS) |
|---|---------|---------|---------------|
| 1 | **§A Idea** | Problem · Persona · Anti-persona · Vision · Differentiation · Scope · Task taxonomy · Actor taxonomy · Skill modes | §A in CoS PRD |
| 2 | **§B Pillars** | This product's pillars (the operator demands this product addresses; analog of CoS B1-B5) | §2.B B1-B5 in CoS |
| 3 | **§B Needs cluster** | This product's needs grouping (analog of CoS 24 needs across 5 pillars) | §2.B needs in CoS |
| 4 | **§Operator surface contract** | Capability bullets per pillar — what operator OBSERVES (per `feedback_prd_what_not_how.md` Cagan) | §2.B per-pillar 6-block in CoS |
| 5 | **§Acceptance criteria** | Per-pillar acceptance + product-level acceptance + falsification tests | §2.B acceptance + §C.5 in CoS |
| 6 | **§HOW preferences** | Per-product HOW defaults (which dimensions tune differently — e.g., Senior Expert may use higher detailing-first; Project Manager may use longer cascading) | §3 HOW dimensions specialized per product |
| 7 | **§Layer-B claims on Native** | Which Native primitives / events / surfaces this product uses; which it does NOT use; what NEW capabilities (if any) this product requires | §4 Native Platform sections referenced from CoS |
| 8 | **§Distribution + onboarding** | Tier-by-tier install responsibility (per §6.3.1 matrix); operator onboarding journey specific to this product | §6 Distribution sections specialized |
| 9 | **§Observability** | Per-pillar metrics + accuracy KPI + operator satisfaction signals (per §7.1.A analog) | §7 Observability specialized |
| 10 | **§Open questions** | Open questions for THIS product's future (analog of §C.6 FQ1-FQ3) | §C.6 in CoS |
| 11 | **§Resilience contract** | Operator-visible failure behavior — which shared hardstops (HS-1..HS-8) specialize for this product; any product-specific hardstops beyond the shared 8; recovery + escalation contract per pillar (analog of §4.10 in CoS) | §4.10 in CoS |
| 12 | **§Activation + versioning** | Per-product version strategy (v1/v1.5/v2 scope); deferred-capability activation gates for any v2+ tag in this product PRD (analog of §1.4.5 + §C.1 in CoS); cutover plan when product graduates v1→v1.5→v2 | §1.4.5 + §C.1 in CoS |

### Required canon additions per new Layer-B Product

| # | Canon location | What lives there |
|---|----------------|------------------|
| 1 | `sutra/os/decisions/ADR-NNN-<product>-pattern.md` | Per-product specialization of ADR-018 (NOT a re-author). See §Pattern ADR layering below for the boundary rule. |
| 2 | `sutra/os/native/blocks/<product-block-NNN>.md` | L8 Feature specs for this product's blocks (analog of B1-B18 for CoS) |
| 3 | `sutra/os/native/open-questions/Q-NNN.md` | Per-product open questions if any extend canon-level questions |
| 4 | (optional) `sutra/os/native/pillars/P-NNN.md` | NEW pillar files ONLY if this product introduces canon-level doctrine not yet in P1-P14 |

### What's SHARED across all Layer-B Products (do NOT re-spec)

- All 14 canonical pillars (P1-P14)
- All 10 primitives (Domain · Charter · Workflow · Step · Trigger · ExecutionResult · EngineEvent · Tenant · Approval · DecisionProvenance)
- All 26 EngineEvents
- All 6 surfaces (ROUTE · RUN · GATE · EMERGE · AUDIT · TENANT)
- All 8 hardstops (HS-1..HS-8) — operator-visible failure behavior baseline
- ADR-018 agentic-systems-pattern — operator-in-loop + deterministic-surface-stochastic-core INVARIANT (the WHAT)
- ADR-019 design ↔ product ↔ tech bridge

### Pattern ADR layering (ADR-018 ↔ ADR-NNN boundary)

R11 codex P2 flagged this layering as previously ambiguous. The boundary rule, made explicit:

| Layer | ADR | What it carries | Audience |
|---|---|---|---|
| **Shared invariant** | **ADR-018** (single source-of-truth) | The agentic-systems-pattern itself: operator-in-loop on consequential decisions + deterministic guardrails around stochastic reasoning. Does NOT name specific decisions or guardrails. | All Layer-B Products inherit unchanged. |
| **Per-product specialization** | **ADR-NNN-<product>-pattern.md** (one per Product) | Specialization of ADR-018 for THIS Product: (a) enumerate which decisions THIS Product gates to operator vs auto-executes, (b) the specific deterministic guardrails THIS Product adds beyond ADR-018's baseline, (c) any product-specific HOW preference (per §HOW preferences section). | This Product's PRD readers + Forge implementers. |

**Litmus tests** (use these when authoring ADR-NNN to stay on the right side of the boundary):

- WRONG: ADR-NNN re-states "operator-in-loop on consequential decisions" — that's ADR-018's job; ADR-NNN inherits it.
- RIGHT: ADR-NNN says "for SeniorExpert, 'consequential' = any external-spend > $X OR any client-comms; auto-executes only research/synthesis tasks; deterministic guardrail: every decision row carries a verification-citation."
- WRONG: ADR-NNN says "use deterministic guardrails" — already ADR-018.
- RIGHT: ADR-NNN names the specific guardrails (e.g., "ProjectManager: every milestone update MUST be diff-reconciled against the immediately prior milestone; no overwrite without operator sign-off").

Boundary self-check: if a sentence in ADR-NNN would still be TRUE if you swapped "this Product" for any other Layer-B Product, it belongs in ADR-018, not ADR-NNN. Move it up.

## Consequences

### Future Layer-B Products inherit canon

When Senior Expert or Project Manager PRD is authored, it specifies sections 1-10 above + adds the 1-4 canon files. It does NOT re-author the 14 pillars / 10 primitives / 26 events / 6 surfaces / 8 hardstops — those are platform-shared.

### Cross-product coherence

Operator using two Layer-B Products under the same Native instance sees consistent hardstop behavior (HS-1..HS-8 are the same), consistent Authority gates (D.6 model), consistent audit (DecisionProvenance schema same). Each product adds its own pillars + operator surface.

### v1.5 deployment authority

Per PRD §1.4.3, operator self-serves binding for approved Products at v1.5. The Product catalog includes only Products that meet the §1.4.4 authority gate + complete ADR-020 authoring template.

### v2+ third-party Products

Third-party Layer-B Product developers (per §1.4.3 v2+) must satisfy ADR-020 template + canon-ADR authoring + codex+deepseek review of the Product PRD before marketplace listing.

## Open questions

- **OQ-020-1**: Cross-product Charter sharing — if an operator has both CoS and Senior Expert deployed, can a single Charter scope both? Or one Charter per Product? Defer to first concrete second-product spec.
- **OQ-020-2**: HOW preference inheritance — does each Product specialize from a base HOW or compose its own from scratch? Likely specialize (avoid divergence).
- **OQ-020-3**: Operator switching between products — UX for "I'm working with CoS now, then Senior Expert" — single conversational thread? Per-product context? Defer to UX research.

## References

- PRD §1.4 Product Hierarchy + §1.4.4 Layer-B products
- PRD §1.4.3 Deployment authority (extended to cover Products in R10)
- [ADR-018 agentic-systems-pattern](ADR-018-agentic-systems-pattern.md)
- [ADR-019 design-product-tech-bridge](ADR-019-design-product-tech-bridge.md)
- `feedback_prd_what_not_how.md` (Cagan: PRD body = operator-facing WHAT)
- R10 codex consult D4 [P1]: "no authoring template" — this ADR is the fix

## Authoring

claude-drafted via R10 Bucket 4 under R10 visual-gaps-audit-fix. R11 codex + deepseek review pending.
