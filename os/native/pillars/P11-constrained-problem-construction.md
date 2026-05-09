---
part-id: P11
bucket: pillars
template: L1-pov
parity-source: §10.2 row P11 + §10.3 row P11 + §10.4 row P11
parity-source-sha256: efdce2ca44db5fcebf593a77cb0e173b6ca2c0466f505d6cb6ddf57990f50049
status: DRAFT v1
authored: 2026-05-09
---

# P11: Constrained problem construction

## Pillar statement

> Every LLM call in Native receives an explicit, composed prompt — there is no implicit context. Per §10.2 row P11: "every LLM call gets explicit composed prompt; no implicit context." The Native runtime constructs the problem for the LLM (assembling context, declaring constraints, stating expected output) rather than letting the LLM pick up ambient state. Implicit context is a defect.

## What this rules in

- Every LLM call is preceded by a deterministic prompt-composition step.
- Context, constraints, and expected-output declaration are all explicit in the composed prompt.
- Cross-ref to P2 (`./P2-pre-post-llm-validation.md`) — P11 is the pre-call construction discipline; P2 is the pre/post check discipline.
- Companion to P12 (`./P12-deterministic-surface-stochastic-core.md`) — prompt composition is deterministic, even though the LLM call that consumes the prompt is stochastic.

## What this rules out

- LLM calls that fire without an explicit pre-composed prompt (per §10.3 P11 falsification).
- "The LLM will figure out the context from the conversation" — implicit context creep is the explicit defect this pillar names.
- Skipping the declared-expected-output step.

## Falsification test

**If any LLM call fires without explicit pre-composed prompt + declared expected output → P11 broken; implicit context creeped in.** (Exact text from §10.3 row P11.)

## Doctrine inheritance (from L0)

§10.4 lists a direct tension: **P11 (constrained problem) vs Doctrine "Customer Focus" (operator clarity)**. Resolution per §10.4: "constraints are explicit + visible to operator (per P6)." The constraints that P11 imposes on LLM calls are not hidden — they surface to the operator under P6 (Operator controls explanation), so the operator can see what Native asked the LLM and what it expected. Customer clarity is preserved because the constraint envelope is visible, not hidden.

## References

- NATIVE-ENGINE.md §10.2 row P11 — pillar statement.
- NATIVE-ENGINE.md §10.3 row P11 — falsification test.
- NATIVE-ENGINE.md §10.4 row P11 — doctrine tension + resolution.
- `./P2-pre-post-llm-validation.md` — post-call analog.
- `./P6-operator-controls-explanation.md` — the surface where P11's constraints become visible.
- `./P12-deterministic-surface-stochastic-core.md` — prompt composition is deterministic.
