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
| ROUTE-I5 | Routing precedes every operator-originated action: every HSutraEvent receives a `routing_decision` before RUN/EMERGE. Machine-originated entries are not unclassified — CLI direct-run (run.md) and cadence firing (trigger.md) carry their declared trigger-spec as the classification record. When in doubt, classify input → depth + plan gate → act. NO silent-skip path for blocked process steps. | PROTO-006 lesson-port (see amendment note below) |

Canon gap: §14.7 says "OR pattern proposal" but does NOT specify the internal handshake between ROUTE → pattern detector → EMERGE. ROUTE emits the `routing_decision` (matched=false); the EMERGE surface's pattern detector consumes that signal. Exact data shape (does the detector tail `routing_decision` events, or does ROUTE call a detector method?) is NOT specified in canon — runtime implementation choice; future ADR may codify.

**Amendment (2026-06-12 — PROTO-006 "Process Discipline" lesson-port, ROUTE-I5)**: ports the constitutional PROTO-006 contract into the ROUTE surface as a canon gap (adjacent doctrine — D3 never-bypass, per-turn classification — existed; the PROTO-006 contract itself did not). Operative ladder, verbatim from the protocol: *"Process exists? → follow it. Cannot follow? → resolve without skipping. Still blocked? → STOP, ask human. Never write 'TBD.'"* Doubt about whether to act routes through dispatcher classification (TYPE/ROUTE) + depth + plan gate (Depth + BLUEPRINT in production terms) BEFORE acting; only the named founder override phrases ("skip the process" / "just do it" / "skip depth assessment") suspend it. Production label inconsistency resolved at port time: the protocol body says HARD while the registry row says SOFT (memory/convention per CLAUDE.md §Process Discipline) — Native wires the invariant into the pre-action decision points of this surface instead of leaving it memory-only: every HSutraEvent passes through ROUTE before RUN or EMERGE, and no bypass handler exists (ROUTE-I1 guarantees exactly one `routing_decision` per input; ROUTE-I5 guarantees no action without one).

Living evidence (production): `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-006 (constitutional; merged from PROTO-006 Process Is Default + PROTO-007 Escalate Before Violating); `sutra/marketplace/plugin/sutra-defaults.json` `.process_discipline_proto006` (fleet schema v2.26.0 — "When in doubt about whether to ship: route via dispatcher — read SUTRA-CONFIG/CLAUDE.md, classify input (TYPE/ROUTE), emit Depth + BLUEPRINT, then act. No silent skips."); CLAUDE.md §Process Discipline (canonical memory anchor). Enforcement today is convention-only / policy-visible terminal (CSM cap-116).

**Falsification test (ROUTE-I5)**: any EngineEvent trace showing a Workflow fired or an action taken without a preceding `routing_decision` for the triggering utterance, OR a blocked process step resolved by silently skipping it (e.g., a "TBD" placeholder shipped) instead of STOP-and-ask — either observation proves ROUTE-I5 violated.

Amendment parity-source (deviation from the NATIVE-ENGINE.md-anchor norm — this content is a canon gap; source is the protocol corpus): `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-006 L170-178, sha256 `92c658024d7bc35e2fb88897df32ec223e0abd48047e45fc76852f773c154a43`.

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
- `sutra/layer2-operating-system/PROTOCOLS.md` §PROTO-006 — ROUTE-I5 source (lesson-port).
- `sutra/marketplace/plugin/sutra-defaults.json` `.process_discipline_proto006` — fleet schema mirror of ROUTE-I5.
