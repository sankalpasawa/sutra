# ADR-030 — Four Problem Types (awareness × understanding)

## Status

ACCEPTED 2026-08-03. Founder direction given in-session (dictated, no D-number minted): the awareness × understanding framing becomes part of Native documentation as the classification of "the types of problems you want."

**Doctrine lens, not a runtime contract.** No engine code, event, primitive, surface, hardstop or CLI subcommand changes as a result of this ADR. It is a diagnostic vocabulary the resolver does not yet read, and it mints no schema constant — per ADR-027 the axis set stays open, and nothing here hard-codes an enum. Wiring is named as open work in Consequences.

Codex review 2026-08-03 (PROTO-019 / D40 G2): **ADVISORY**. Five corrections were raised and all five are applied in this text — T3's scope narrowed against ADR-010, Decision 5 demoted from mechanism to interpretive rule, the DecisionProvenance claim corrected, documentation rules separated from surface contracts, and the closed-classifier reading disclaimed above.

Surfaces of record:

- This ADR (the holder).
- `sutra/os/engines/NATIVE-ENGINE.md` §5 ADR Map (the pointer).
- Operator-facing synthesis: `holding/website/native/the-system-simply.html` §The four problem types.

## Context

Native already classifies a unit of work two ways. `core:flow` applies a Cynefin lens (clear / complicated / complex / chaotic) to judge **causality**, and ADR-026 resolves a **workflow type** to judge what shape of process fits. Neither answers a third question that determines what the machine can do next:

**What is missing?**

An operator arriving with "the month-end close is painful" and an operator arriving with "I don't know which service lines make money" are not the same request. The first has a settled process and lacks execution. The second has the data and lacks anyone having asked. Same domain, same tenant, entirely different first move. Without a name for the missing artefact, the router treats both as "work" and defaults to authoring a workflow — right for one, premature for the other.

The Rumsfeld / Johari 2×2 supplies the missing axis pair. **Awareness**: is this on anyone's radar? **Understanding**: is it actually grasped? The two are independent, and each of the four resulting cells lacks a different artefact.

### Alternatives considered

- **Extend Cynefin with a fifth domain** — rejected: Cynefin answers a different question (how cause relates to effect). Bolting "missing artefact" onto it would blur two orthogonal lenses and degrade both.
- **Ship the Rumsfeld wording alone in documentation** — rejected: "unknown knowns" is not legible cold. Every type therefore carries a plain-English gloss (see Decision 3).
- **Treat all four types as automatable** — rejected as an overclaim. T4 is watch-only; the machine can shorten time-to-noticing, not manufacture the question.
- **Keep this as deck / research material only** — rejected by D54: a classification that shapes resolution is canon or it is drift.
- **Define T1→T4 as a lifecycle state transition** — rejected on codex review: canon defines no such state, and inventing one inside a doctrine ADR would smuggle a runtime change past the contract boundary. Retained as an interpretive rule instead (Decision 5).

## Decision

**Decision 1 — Four types, named by what is missing.** Every unit of work is classifiable into exactly one of four problem types at intake. The four are exhaustive by construction — two binary axes — but they are a lens for reading a unit, not an enum any component may branch on until an ADR wires them.

| Type | Cell | Gloss (travels with the name) | Missing | Intended first move |
|---|---|---|---|---|
| **T1** | known knowns | we know it, we do it by hand | operationalisation | Author or reuse the workflow; run it on the RUN surface with steps, approvals and audit. |
| **T2** | known unknowns | we know what we don't know | the answer | A bounded experiment whose purpose is to measure. What the operator then *decides* on the result is a decision like any other; where the measurement itself is stored is open work (item 3). |
| **T3** | unknown knowns | we have it, we haven't worked it out | the workflow | Surface the latent pattern, then propose a workflow for operator approval, inheriting the propose→approve **shape** of ADR-010. Scope limit below. |
| **T4** | unknown unknowns | we don't know what we don't know | the question | Watch weak signals on a cadence (ADR-017 substrate, Observability §7). No workflow is authored — the output is a surfaced question, which converts the unit to T2. |

**T3 scope limit (codex correction).** ADR-010 covers a specific detector: repeated *unmatched work* proposing a Workflow for approval. T3 inherits that decision shape — machine proposes, operator approves, the machine never self-authorises — and nothing more. General retrospective mining across the System of Record is **not** covered by ADR-010, is not authorised by this ADR, and would need its own decision record. Any claim that Native mines your whole record today is unsupported.

**Decision 2 — Orthogonal to Cynefin, not a replacement.** Problem type answers *what is missing*. The Cynefin lens answers *how cause relates to effect*. ADR-026 workflow type answers *what process shape fits*. All three may be stated for one unit. No document or surface may present problem type as a substitute for either of the others.

**Decision 3 — The gloss travels with the name (documentation rule).** Wherever a type name appears in Native documentation or operator-facing pages, its plain-English gloss appears adjacent. This binds authoring, not runtime: it is a rule about how we write, and it creates no surface contract.

**Decision 4 — Conversion, not classification, is the objective.** Type is not a permanent label on a unit. Three conversions are the work:

| Conversion | What buys it |
|---|---|
| T4 → T2 | attention: cadence watching of weak signals |
| T2 → T1 | a bounded experiment whose result is written down |
| T3 → T1 | a surfaced pattern that the operator approves as a workflow |

**Decision 5 — Interpretive rule: a T1 workflow's assumptions become suspect unless re-verified.** This is a reading rule, not a state machine. Canon defines no T1 lifecycle state and no automatic transition; this ADR does not create one. What it asserts is interpretive: thresholds, rules and counterparty behaviour drift, so a workflow that has run unexamined for a long time should be read as *possibly* blind rather than *known*. Re-verification is the counter, and the existing record and cadence machinery are where it would live if implemented. Documentation that presents the four types as a one-way ratchet into T1 is misleading and must state this caveat.

**Decision 6 — Honest ceiling.** T1 is the type Native closes today. T3 is closable only within the ADR-010 detector's scope, not as general record mining. T2 is partial: a workflow can run and record a test, a human still chooses what to test. T4 is sensing only. No page, product surface or deck may claim T4 is solved.

## Consequences

**What this enables.** Intake can state a type, which makes the first move deliberate rather than reflexive: T1 → author/run, T2 → measure, T3 → surface then propose, T4 → watch. It also gives us language for the failure we keep seeing — everything gets treated as T1 because T1 is the only type with an obvious mechanism.

**What is unchanged.** No primitive, event, surface, hardstop, trigger or CLI subcommand changes. The resolver does not read problem type. Nothing enforces it. This ADR is doctrine until wired, and the three items below are the wiring.

**Open work (unflagged, unscheduled).**

1. Wire type resolution into `core:flow` step [1] alongside the Cynefin lens, and decide whether the type is operator-declared, inferred, or both. Any component branching on type before that ADR exists is out of contract.
2. Decide whether T3 pattern surfacing extends beyond ADR-010's unmatched-work detector. If it does, it needs its own ADR, a compute budget per tenant, and a tenancy review — the record is tenant data.
3. Define where a T2 measurement is stored and what evidence closes the experiment. DecisionProvenance (ADR-007) records decisions with fixed scopes and outcomes; it is **not** a measurement store, so citing it for experiment results would be a category error. Until this is decided, "we tested it" is narrative, not a recorded answer.
4. Decide whether T4 probes are ordinary Workflows with TriggerSpecs. Today "standing probe" is a description of intent, not a defined object.

**Risk if ignored.** The taxonomy is easy to render and hard to honour. A four-box diagram on a page costs nothing and proves nothing; the value only appears when intake actually behaves differently per type, which is items 1–4.

## References

- ADR-007 DecisionProvenance schema — decision audit; explicitly not the T2 measurement store (open item 3).
- ADR-010 Organic emergence propose→approve — the propose→approve shape T3 inherits, within its detector's scope only.
- ADR-017 Cron daemon cadence tick — the substrate a T4 probe would run on, if defined as an object (open item 4).
- ADR-026 Workflow-type guidance-first resolution — orthogonal axis (process shape).
- ADR-027 Value axis single primitive — orthogonal axis (worth); also the reason this ADR mints no enum.
- Provenance of the framing: the Johari window (Luft + Ingham, 1955) supplies the 2×2; Rumsfeld's February 2002 briefing named three of the four cells; the fourth — unknown knowns — is Žižek's 2004 addition, read here as "held but never operationalised" rather than in his stronger sense of disavowed knowledge. Sketchplanations' rendering supplies the awareness × understanding axis labels. *(Dates high-confidence but not re-verified at authoring time: the session's web-search budget was exhausted.)*
