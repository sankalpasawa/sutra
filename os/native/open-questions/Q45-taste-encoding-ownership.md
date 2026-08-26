---
part-id: Q45
bucket: open-questions
template: research-log
parity-source: none — net-new question, not a §14.10 row migration
parity-source-sha256: n/a (no upstream anchor; net-new 2026-08-26)
status: OPEN
authored: 2026-08-26
---

# Q45: Who owns taste — define, encode, apply, check, maintain?

## Question

Native's mission includes "learning taste / decision-style / voice"
(`../doc-layers/L3-mission.md`) and the Person primitive carries a `taste_signals[]`
field (`../blocks/B18-person-formation.md`). But no canon row assigns the lifecycle
roles for taste. Concretely:

1. **Define** — where does an operator's taste become a stated artifact, rather than
   an inference over logs?
2. **Encode** — does Native hold taste only *descriptively* (what the operator did),
   or also *prescriptively* (a rule an artifact can be checked against)?
3. **Apply at runtime** — what injects taste into generation, and is prompt influence
   sufficient, or is a binding required?
4. **Check** — what portion of taste reduces to deterministic predicates that B7 can
   validate, and what portion stays model-graded under P12?
5. **Maintain + monitor** — who owns taste drift, recalibration cadence, and decay?

## Why it matters

The operator's recurring failure mode is: "I want it beautiful, I cannot articulate
what beautiful is, but I know it when I see it." If taste stays descriptive-only, every
artifact costs a manual review round. If a prescriptive floor can be declared and bound,
that round is spent only on the part that genuinely needs judgment.

It also bounds an honesty problem: Native must not claim taste is validated when only
its craft floor is.

## Current state in canon (audited 2026-08-26)

| Role | Where it lives today | Status |
|---|---|---|
| Define | nowhere — inferred from DecisionProvenance / EngineEvent / H-Sutra / ESTIMATION-LOG | no artifact exists |
| Encode | `../blocks/B18-person-formation.md` — `taste_signals[]` on Person | EXISTS, v1 READ-ONLY, descriptive only |
| Apply at runtime | `../blocks/B11-promptbuilder.md` — bias-injection from Person | DEFERRED to B18 v2 |
| Check | `../blocks/B7-pre-post-validation.md` | stochastic content quality EXPLICITLY out of scope (v1) |
| Assist | `../blocks/B5-explanation-surface.md`, `../blocks/B6-research-on-fly.md` | partial, never stated as a taste role |
| Maintain + monitor | `../blocks/B18-person-formation.md` edge case "Persona drift" | named as a gap; decay / eviction rule NOT specified (gap per F2) |

Verified by grep across `sutra/os/` on 2026-08-26: the strings `taste`, `aesthetic`,
`beaut` appear in exactly two files (`../blocks/B18-person-formation.md`,
`../doc-layers/L3-mission.md`).

## What is NOT the blocker

Two candidate readings were tested against canon and rejected:

- **"B7 forbids checking taste."** It does not. B7 excludes *stochastic content
  quality*, and `../pillars/P12-deterministic-surface-stochastic-core.md` states only
  LLM reasoning and action are stochastic — "everything else is tested code."
  A deterministic predicate (contrast ratio, count of distinct type sizes, conformance
  to a spacing scale) is therefore in scope, not excluded. What B7 does forbid is
  claiming taste *in general* is validated once a craft-floor check passes.
- **"B18 v2 bias-injection closes the prescriptive gap."** It does not. Bias-injection
  shapes generation via prompt context. Prompt influence is not enforcement: nothing
  fails, nothing gates. A prescriptive standard needs a declared check and a binding.

## Default if unanswered

Taste stays descriptive-only. Every visual or written artifact continues to require a
manual operator review round, and Native carries a mission claim ("learning taste")
that no runtime surface enforces.

## Candidate resolution (NOT a decision — for founder ruling)

Route a prescriptive taste standard through the existing verifier layer
(`../../decisions/ADR-032-verifier-layer.md`) rather than minting a new engine:

| Verifier stage | Taste instantiation |
|---|---|
| DECLARATION | a named standard registered as a check in `holding/state/verifier/registry.jsonl` |
| BINDING | `{attach: workflow.close or deploy.pre, mode: gate or observe, life}` |
| EXECUTION | `verify-runner.sh` runs the deterministic predicates |
| JUDGMENT | pass/fail on craft floor; model-graded lanes stay `mode=observe` |

Layer split governing what may be declared as a gate:

| Layer | Example predicate | Gate-able |
|---|---|---|
| craft floor | contrast ratio, spacing-scale conformance | yes |
| coherence | count of distinct greys / weights | yes |
| restraint | budgets — at most N type sizes, N accents | yes |
| fit | "does this read as this brand" | observe only |
| the move | the one memorable choice | not checkable; operator-owned |

Extraction of the standard does not require the operator to articulate anything:
forced-choice ranking over existing artifacts yields the rules. Protocol in
`../../../../holding/research/2026-08-26-solvability-and-taste-framework.md` section 5.4.

## Sub-questions the founder must rule on

| id | question |
|---|---|
| Q45.1 | Does a prescriptive taste standard become a Native concern, or stay an Asawa-local discipline? |
| Q45.2 | Which stage does a taste check bind at — `workflow.close`, `deploy.pre`, or observe-only in v1? |
| Q45.3 | Who owns drift: recalibration cadence, decay semantics, standard versioning? |
| Q45.4 | Does B18 v2 bias-injection ship paired with a declared check, or independently? |
| Q45.5 | What is the honesty rule for reporting a craft-floor pass, so it is never read as "taste validated"? |

## Sources informing the question

- `../blocks/B18-person-formation.md` — `taste_signals[]`, v1 read-only, drift gap
- `../blocks/B7-pre-post-validation.md` — stochastic content quality out of scope
- `../pillars/P12-deterministic-surface-stochastic-core.md` — stochastic core boundary
- `../blocks/B11-promptbuilder.md` — persona consumption at prompt-build time
- `../../decisions/ADR-032-verifier-layer.md` — four-way verification split
- `../../../layer2-operating-system/READABILITY-STANDARD.md` — the working precedent: an
  enforced taste standard written as 13 prohibitions / budgets against 1 positive
  aesthetic word (measured 2026-08-26)

## References

- `../MIGRATION-PLAN.md` (bucket template contract)
- `../../engines/NATIVE-ENGINE.md` sections 12.21 (B18 row), 12.9 (B7 row), 12.14 (P12 row)

---

provenance: authored 2026-08-26 by Claude (Fable 5), session e5caa2b8, atom a-e5caa2b8-01, from founder question "who defines taste, who encodes it, who uses it, who maintains it — is it already in our architecture?". Canon audited live (verify-archive-completeness.sh PASS before write). Dual-lane peer review: codex CHANGES-REQUIRED (2 P1, 2 P2) + deepseek CHANGES-REQUIRED (5 P1, 5 P2); convergent findings folded, one deepseek P1 refuted against P12 text. Status OPEN — the candidate resolution is not a decision; Q45.1-Q45.5 await founder ruling. An ADR follows only if Q45.1 resolves yes.
