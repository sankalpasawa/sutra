# Core Algorithm — Definition Charter

| Field | Definition |
|---|---|
| Unit | Sutra / Core Algorithm (department) |
| Charter kind | **Definition Charter**, not a cross-cutting initiative charter |
| Status | Department charter established; experimental reference, not deployed runtime |
| DRI | Core Algorithm department (accountable human owner to be assigned) |
| Created | 2026-11-08 |
| Scope | Sutra-wide reasoning contract, extension interface, evaluation and J2 adapter specifications |

## Purpose

Maintain a **small, versioned, evidence-aware computational kernel** that reconciles accepted goals with observed reality by deriving needs from approved knowledge, selecting adequate Methods under constraints, executing only authorized effects, verifying outcomes independently and recording evidence. Allow domain knowledge, Methods, policies, optimizers and learning strategies to evolve as extensions without silent changes to trusted behavior.

## Accountabilities

1. **Meaning and Need Formation:** Specify typed goal contracts, rule-grounded AND/OR condition refinement, truth/evidence scope and explicit missing-semantics outcomes. New obligations arise from standing goals plus approved rules and relevant evidence changes—not from an empty prompt.
2. **Resolution and Adaptation:** Specify recursive Method search, alternative plan evaluation, shared prerequisites, minimal graph changes, stop states and bounded candidate construction. Separate required goal conditions from Method-specific prerequisites.
3. **Governed Execution:** Define interfaces for provider commitments, authority checks, nonfungible resource budgets, idempotency and independently verified effects. Enforce an action boundary; the reference lab implements **local simulation only**.
4. **Memory, Trace and Learning:** Own versioned run traces, provenance, selective dependency invalidation and candidate-only learning. No autonomous promotion of Methods, rules, validators or Core releases.
5. **Compatibility and Evidence:** Define adapters and acceptance tests for J2 `atom/1` / `map/1`, Native graph/charter primitives and future production effect receipts, without rewriting existing J2 semantics.

## In scope / out of scope

| In scope | Explicitly out of scope |
|---|---|
| Kernel specification, executable reference, regression suite and interfaces | Product-specific domain truths without an accepted source |
| Versioned domain/Method pack contracts and evaluation rules | Authorizing protected external effects or granting its own permissions |
| Need formation, planning, verified result semantics | Unreviewed algorithm self-replacement, automatic release approval |
| Proposal-only capability construction and structural candidates | Claiming production J2 integration, live deployments or Native v1-v5 stage-gate completion |
| Cross-team contracts with Experience, Assembly and Runtime/Evidence teams | Moving private Native material into public mirrors without explicit approval |

## Inputs → Outputs

Input contract: `Goal + Knowledge + Observations + Methods/Providers + Policy/Authority/Budgets`, with tenant/domain scope, source versions and stop limits.

Output contract: `proven satisfaction | evidence query | selected bounded plan | permitted effect with independent receipt | scoped proposal | explicit blocker`, plus decisions, trace, cost ledger, test evidence and release identity. A plan or simulated success does not prove an external outcome.

## Non-negotiable invariants

- Unknown is neither TRUE nor FALSE; a failed checker is not evidence that the external proposition is FALSE.
- A derived condition must cite an approved applicable rule and its input bindings; no rule means `SEMANTICS_MISSING` / `SEMANTICS_UNAPPROVED`.
- No action without eligible provider, scoped grant and available nonfungible resources. Never infer authorization from expected benefit.
- Do not count shared prerequisites twice; reject cycles; preserve tenant isolation and dependency-based evidence invalidation.
- No Method candidate self-promotion or Core code self-mutation; protected changes require independently verified tests and an external approval path.
- Immutable, provenance-linked Run record; do not rewrite history after rule upgrades.
- Real-world completion requires independent external evidence, not a local receipt.

## Acceptance evidence

| Outcome | Current reference evidence | Required before promotion |
|---|---|---|
| Add domain nuance without kernel change | 25 synthetic recorded scenarios against one kernel hash | Held-out domains and independent need labels |
| Block unjustified actions | Unknown/authority/provider/resource counterexamples | Real policy enforcement and independently witnessed external effects |
| Reproduce reference algorithm | 54/54 unit + 31/31 independent model-record checks | Original historical Core v0.2.2 source and sealed baseline recovered for head-to-head comparison |
| Method formation | Contract assembled from seeded components, marked `PROPOSED_ONLY` | Generic independent constructor, hidden tests and release authority |
| J2 compatibility | `atom/1`-shaped read-only projection only | Real J2 `atom/1` / `map/1` run, verification and recovery |
| Native maturity | Not claimed | Native's independently witnessed v1 FOLLOW → v5 DISTRIBUTE stage gates |

## Boundaries with other units

The **Core Algorithm** owns reasoning semantics and reference tests. Experience owns intent capture and explanation. Domain experts/Knowledge owners approve domain meaning and sources. Assembly owns capability construction and Work-Atom compilation. Runtime/Controls owns real scheduling, effects, resources and authority enforcement. Evidence/Audit owners verify claims independently. Current Native's Identity, Adaptation, Priority, Coordination and Audit roles are reusable roles, not mandatory kernel stages.

## Initiative participation

- `os/charters/TOKENS.md` — contributor: measured resource vector/cost semantics (not an approved joint workplan).
- `os/charters/SPEED.md` — contributor: incremental re-evaluation and method selection (not an approved joint workplan).
- `os/charters/OPERATIONALIZATION.md` — contributor: future J2 adapter and independently verified effects (not an approved joint workplan).

## Governance and termination

No self-authorization or unreviewed release. Canon changes to Native require the existing Native charter/ADR approval process. This charter's departmental assignment can change through review; the released historical source and test evidence remain immutable. The department can be retired/merged only with an explicit replacement owner for its contracts, regression suite and provenance.
