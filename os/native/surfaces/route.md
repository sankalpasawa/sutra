---
part-id: ROUTE
bucket: surfaces
template: L9-surface-spec
parity-source: §14.7 + §3.1 + §3.2 #1 + §5.3
parity-source-sha256: bef49e938e9ee75c77e142cca8a616cbfa9660e685397c9949a711d8a39b07bd
status: DRAFT v1
authored: 2026-05-09
---

# Surface: ROUTE

## Purpose

Classify a founder utterance (delivered as an HSutraEvent) into either a matched Workflow (registered in user-kit) or a candidate pattern proposal — without executing anything.

Canon: §14.7 row 1 — *"ROUTE | Classify utterance → matched Workflow OR pattern proposal"*.

## Interface (operator-facing)

The operator does not call ROUTE directly. The H-Sutra event bus (§5.3) tails the per-turn JSONL log; `HSutraConnector` forwards each row to `NativeEngine.handleHSutraEvent(evt)` (§3.1). ROUTE is the body of that handler.

| Input | Source | Shape |
|---|---|---|
| `HSutraEvent` | per-turn-h-sutra.sh JSONL row | 9-cell + 3 tags per §5.3 |
| Workflow registry | UserKit.loadWorkflows(home) | Workflow[] (§3.1) |

Return type: `RoutingDecision` (§3.1 `Router.route(evt)` synchronous; `Router.routeAsync(evt)` latent path per §8 OS-8).

## Invariants (must always hold)

| # | Invariant | Source |
|---|---|---|
| ROUTE-I1 | Every HSutraEvent input produces exactly one `routing_decision` EngineEvent (matched or unmatched). | §3.2 row 1 |
| ROUTE-I2 | `routing_decision.execution_id` is null — routing happens outside any Execution. | §2.7 `execution_id` invariant + §3.2 row 1 (no execution_id key) |
| ROUTE-I3 | When a Workflow matches, the matched `target_workflow_id` MUST resolve in the registry. | §2.5 TriggerSpec.target_workflow_id invariant |
| ROUTE-I4 | When no Workflow matches, the utterance becomes a candidate for the pattern detector (k counter increment); no Workflow fires. | §14.7 row 1 ("OR pattern proposal"); k threshold answered Q4 = 4 |

Canon gap: §14.7 says "OR pattern proposal" but does NOT specify the internal handshake between ROUTE → pattern detector → EMERGE. ROUTE emits the `routing_decision` (matched=false); the EMERGE surface's pattern detector consumes that signal. Exact data shape (does the detector tail `routing_decision` events, or does ROUTE call a detector method?) is NOT specified in canon — runtime implementation choice; future ADR may codify.

## Integration points

- **Primitives consumed**: [`Workflow`](../primitives/workflow.md), [`TriggerSpec`](../primitives/trigger.md), [`Tenant`](../primitives/tenant.md) (for tenant_context resolution).
- **Events emitted**: [`routing_decision`](../events/routing_decision.md) (#1).
- **Events consumed**: HSutraEvent (NOT one of the 26 typed EngineEvents — it is the H-Sutra bus row per §5.3; HSutraEvent crosses the boundary into Native).
- **Surfaces upstream**: H-Sutra event bus producer (§5.3 — Native's vendored `per-turn-h-sutra.sh`).
- **Surfaces downstream**: [RUN](run.md) (when a Workflow matches → `NativeEngine.run(workflowId, ctx)` per §3.1); [EMERGE](emerge.md) (when no Workflow matches and the pattern detector escalates).

## C4 context

```
[Founder utterance]
        |
        v
[H-Sutra event bus]  --(JSONL row)-->  [HSutraConnector] --(handleHSutraEvent)--> [ROUTE]
                                                                                     |
                                       matched? --yes--> emits routing_decision -> [RUN]
                                                |
                                                +--no---> emits routing_decision -> [EMERGE pattern detector]
                                                                                     |
                                                                                     v
                                                                              [AUDIT JSONL]
```

ROUTE is a synchronous handler inside the Native daemon (`Router.route` per §3.1). It is NOT a long-running surface — one HSutraEvent in, one RoutingDecision + one EngineEvent out. AUDIT persists the event row.

## References

- `NATIVE-ENGINE.md` §14.7 row "ROUTE"
- `NATIVE-ENGINE.md` §3.1 `Router.route` + `Router.routeAsync` + `NativeEngine.handleHSutraEvent`
- `NATIVE-ENGINE.md` §3.2 row 1 `routing_decision`
- `NATIVE-ENGINE.md` §5.3 H-Sutra event bus integration
- `NATIVE-ENGINE.md` §8 OS-8 (latent async route — future)
- `../events/routing_decision.md`
- `../primitives/workflow.md`
- `../primitives/trigger.md`
- `../primitives/tenant.md`
- `../surfaces/run.md`
- `../surfaces/emerge.md`
- `../surfaces/audit.md`
- Open question Q4 (k=4 ANSWERED 2026-05-09) — see `../open-questions/Q4-pattern-emergence-k.md`
