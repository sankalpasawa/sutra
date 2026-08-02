---
part-id: B11
bucket: blocks
template: L8-feature-spec
parity-source: §12.13 row B11 + §12.12 founder voice round 4 + §10.2 P11 + Q29
parity-source-sha256: f815ea3f3da0b671d654d19003c901add41eb57207f5a4f3e074d413e217dc98
status: DRAFT v1
authored: 2026-05-09
---

# B11: PromptBuilder (Constrained Problem Construction)

## 1-line summary

Every LLM execution receives a deterministically-composed prompt = {Domain config + Charter config + relevant Artifacts + Step inputs + Intent specifics} — the problem is constructed before being given to the reasoning step.

## Scope (in / out)

**In scope (v1)**:
- NEW PromptBuilder primitive per §12.13 row B11.
- Deterministic concatenation of {Domain config (per B10) + Charter config (per B10) + Relevant Artifacts (per 7a / B9) + Step inputs (per §2.4) + Intent specifics (per B1)}.
- Deterministic + testable per P12 (deterministic surface around stochastic core).
- Full inline assembly per Q29 default (2026-05-09) — every prompt rebuilt fresh; cache layer v2 once perf signal lands.

**Out of scope (v1)**:
- Caching layer (memoized per Domain × Charter × Intent) — Q29 defers to v2.
- LLM-side prompt-rewriting (Native NEVER rewrites prompt post-build; the LLM gets the deterministic prompt) — per P12 stochastic core does not mutate deterministic surface.
- Token-budget enforcement at prompt-build — overlaps F1 (canon-silent; gap per F2).

## User outcome

Every LLM call is fully constrained — the operator (and the audit log) can replay the exact prompt that produced any decision. Founder voice round 4: "everything everything is passed as prompts so that is constrained ... we construct a problem and give it to the reasoning part".

## UX flow (narrative; terminal + audit log)

1. Workflow step S where `action='invoke_host_llm'` is about to fire.
2. B11 PromptBuilder reads: Domain config (B10) + Charter config (B10) + relevant Artifacts (via 7a / B9) + Step inputs + Intent specifics (B1).
3. B11 deterministically concatenates into a single prompt (specific concatenation order NOT specified in canon — gap per F2; runtime implementation choice).
4. Prompt content-addressed (canon-silent on hash scheme — gap per F2).
5. host-LLM dispatch fires with composed prompt per §5.1.
6. Prompt + response persisted as Artifacts per B9.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Step has `action='invoke_host_llm'` | step fires | B11 composes prompt from all 5 sources (Domain, Charter, Artifacts, Inputs, Intent specifics) |
| 2 | Same {Domain, Charter, Artifacts, Inputs, Intent} | B11 invoked twice | identical prompt produced (deterministic per P12) |
| 3 | Domain config missing | composition | empty Domain config slot; prompt still composes; no exception (specific empty-slot behavior NOT specified in canon — gap per F2) |
| 4 | Cache layer requested | v1 | rejected v1 per Q29 default; fresh assembly each call |
| 5 | Prompt content hash captured | persisted | hash recorded; prompt deterministically replayable (per §14.9 cross-company decision-replay ≥99% target) |

## Data model

NEW PromptBuilder primitive per §12.13 row B11. Per F5, canon authorizes new primitive. Not added to §2 enumeration in v1 (deferred).

```
PromptBuilder = {
  domain_config        // from B10
  charter_config       // from B10
  relevant_artifacts   // from 7a / B9
  step_inputs          // from §2.4 WorkflowStep
  intent_specifics     // from B1
  → composed_prompt    // deterministic concat
}
```

Cross-refs:
- `../primitives/step.md` (host — step.prompt_template per §2.4 is the partial substrate B11 extends)
- `../primitives/domain.md` (config source)
- `../primitives/charter.md` (config source)
- `../primitives/workflow.md` (Workflow root)

## Edge cases

- **Prompt exceeds LLM context window** → not specified in canon (gap per F2; future ADR may codify trimming policy).
- **Artifact pointer resolves to deleted artifact** → resolution-failure semantics NOT specified in canon (gap per F2).
- **Concurrent B11 calls on same Workflow** → handled per B13 ConcurrencyCoordinator.
- **B11 receives null in any of the 5 slots** → empty-slot composition (canon-silent — gap per F2).

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — B11 composition is a policy decision.
- `artifact_registered` (#9) — composed prompt + response persisted per B9.
- `step_started` (#5) — at prompt-dispatch.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Cross-company decision-replay success rate (canon §14.9 ≥99% target) — deterministic prompts are the substrate of replay.
- Pattern-detection precision — well-constrained prompts raise proposal precision.

## Dependencies

- **Primitives**: `step` (host), `domain`, `charter`, `workflow`, `engine-event`.
- **Events**: `policy_decision`, `artifact_registered`, `step_started`.
- **Surfaces**: `run`, `audit`.
- **Hardstops**: HS-4 (audit-unwritable).
- **Blocks**: B1 (Intent specifics input), B10 (Domain + Charter configs input), 7a (Artifact retrieval input), B9 (prompt+response persisted as Artifact), B7 (pre-check fires against composed prompt), B18 (Person bias-injection v2+).
- **Pillars**: P11 (Constrained problem construction), P12 (Deterministic surface around stochastic core).

## References

- NATIVE-ENGINE.md §12.13 row B11 (founder voice round 4).
- NATIVE-ENGINE.md §10.2 P11 + P12.
- NATIVE-ENGINE.md §2.4 WorkflowStep.prompt_template (partial substrate).
- Q29 (§12.15) — full inline v1; cache layer v2.
