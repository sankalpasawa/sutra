---
part-id: 7c
bucket: blocks
template: L8-feature-spec
parity-source: §12.6 row 7c + §12.5 round 2 founder voice + Q15
parity-source-sha256: 8c922312fc6df31dfb2ada65994d1cf1c3ab92ef7e2fe122742133faf1459371
status: DRAFT v1
authored: 2026-05-09
---

# 7c: Block-by-Block Mode

## 1-line summary

A step-through operating mode where Native surfaces "context used" per step, pauses for the founder to verify, then continues — gives the operator explicit per-step verification with tunable verbosity.

## Scope (in / out)

**In scope (v1)**:
- Per-step "context-used" surface per §12.6 row 7c.
- Founder approves block before next step; pause / resume cadence reuses canon Approval primitive (per §12.6 row 7c "Approval primitive (P-A6) + step-level pause + EngineEvent.step_paused").
- Opt-in v1 per Q15 default — default = continuous; step-through enabled when founder asks.
- Tunable verbosity (canon-silent on exact verbosity levels — gap per F2).

**Out of scope (v1)**:
- Default-on step-through (Q15 default = opt-in v1).
- Auto-skipping previously-approved blocks across executions — not specified in canon (gap per F2).
- Multi-operator concurrent approval on the same block — single approver v1 per §14.10 Q5.

## User outcome

Operator runs block-by-block when they want verification, sees context Native used at each step, approves before next step. Founder voice round 2: "it can give me a mode wherein I can run block by block in terms of what are the relevant contexts used. I can verify it, and then I can go to the next step."

## UX flow (narrative; terminal + audit log)

1. Operator enables block-by-block mode for a Workflow (opt-in per Q15).
2. Workflow fires step 1.
3. Before LLM dispatch, Native emits `step_paused` (§3.2) with "context used" payload (artifacts retrieved per 7a + scope per 7b + prompt assembly per B11).
4. Operator inspects context, types approval utterance per §3.4 (canon Approval primitive).
5. Native emits `approval_granted` (§3.2 #16) — step un-pauses; LLM call fires.
6. Step completes → `step_completed` (§3.2 #6) → loop to next step.
7. Operator may type rejection per §3.4 → `approval_denied` (§3.2 #17) → Workflow routes via canon `on_failure` per §6.5.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Block-by-block enabled on Workflow | step fires | `step_paused` emitted per §3.2 with context payload before LLM dispatch |
| 2 | Operator types approval utterance per §3.4 | utterance arrives | `approval_granted` (§3.2 #16) emitted; step un-pauses; LLM dispatch fires |
| 3 | Operator types rejection per §3.4 | utterance arrives | `approval_denied` (§3.2 #17) emitted; canon `on_failure` per §6.5 fires (no new fail-mode per F3) |
| 4 | Block-by-block NOT enabled | step fires | no pause; default = continuous per Q15; step_paused NOT emitted |
| 5 | Operator approves but timeout exceeds per-step timeout per §6.7 | timeout elapses | canon §6.7 per-step-timeout semantics apply (no new timeout-handling invented per F3) |

## Data model

Per §12.6 row 7c: 7c EXTENDS existing Approval primitive (canon-derived per primitives/approval.md ADR-009 + §3.2 #15-#18) + step-level pause + `step_paused` event. No new §2 primitive (per F5).

A `block_by_block_mode` flag on Workflow OR on per-execution config (exact location NOT specified in canon — gap per F2; runtime implementation choice).

Cross-refs:
- `../primitives/workflow.md` (host)
- `../primitives/approval.md` (substrate)
- `../primitives/engine-event.md` (step_paused / approval events)

## Edge cases

- **Approval timeout** → §6.7 per-step-timeout applies; canon-default.
- **Operator pauses indefinitely** → ExecutionResult stays in awaiting_approval terminal state per canon §4 I-5 (no new state invented per F4).
- **Multiple steps pending approval** → batched via canon Approval primitive; canon-silent on UI shape (gap per F2).
- **Operator changes mind after approval** → revocation NOT specified in canon (gap per F2; future ADR may codify).
- **Block-by-block on a fully autonomous Workflow** → conflict with operationalized auto-run per 7d / Q13; resolution NOT specified in canon (gap per F2; founder gates per Q13 supersede).

## Telemetry

Events emitted (canon-existing only):
- `step_paused` (§3.2) — per-step pause for verification.
- `approval_requested` (§3.2 #15) — paired with step_paused.
- `approval_granted` (#16) / `approval_denied` (#17).
- `approval_already_handled` (#18) — race protection per ADR-009.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Approval-gate latency (canon §14.9 ≤2 min median) — block-by-block raises approval volume; latency target sensitivity.
- Operator trust (qualitative; canon-silent as metric — gap per F2).

## Dependencies

- **Primitives**: `workflow`, `step`, `approval`, `engine-event`.
- **Events**: `step_paused`, `approval_requested`, `approval_granted`, `approval_denied`, `approval_already_handled`, `step_completed`.
- **Surfaces**: `gate` (canon approval surface), `run` (step execution), `audit`.
- **Hardstops**: HS-1 (reflexive-check — if Workflow mutates Sutra, block-by-block must still gate).
- **Blocks**: 7a (context retrieval surfaced at pause), 7b (scope surfaced at pause), B11 (PromptBuilder output surfaced at pause).
- **Pillars**: P6 (Operator controls explanation), P14 (Outcomes drive design).
- **ADRs**: ADR-009 (Approval gate).

## References

- NATIVE-ENGINE.md §12.6 row 7c (founder voice round 2 — block-by-block).
- NATIVE-ENGINE.md §3.4 (Approval utterances).
- NATIVE-ENGINE.md §6.6 (Approval ledger).
- NATIVE-ENGINE.md §6.7 (Per-step timeout).
- Q15 (§12.7) — opt-in v1.
- §14.10 Q5 — single-founder approval v1.
