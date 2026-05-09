---
part-id: B6
bucket: blocks
template: L8-feature-spec
parity-source: §12.9 row B6 + §12.8 founder voice round 3 + Q24
parity-source-sha256: 7871f470be578c3e5284f83e25e4b2f1c801bdbf2b7034747a0c0795efbb89e2
status: DRAFT v1
authored: 2026-05-09
---

# B6: Research-on-the-fly

## 1-line summary

Native orchestrates ecosystem tools (Context7, web search, Slack and other Connectors) into a `ResearchWorkflow` class that produces a Research Artifact in response to operator's research ask.

## Scope (in / out)

**In scope (v1)**:
- NEW Workflow class `ResearchWorkflow` per §12.9 row B6.
- Orchestrates Context7 (MCP) / WebSearch / connectors per memory `project_connectors_slack_live` (Slack live).
- Produces Research Artifact (typed per B9 closed-loop).
- Two trigger paths per Q24 default (2026-05-09) — slash command (`/research X`) for explicit; conversational ("research X for me") via classifier matching ResearchWorkflow intent.

**Out of scope (v1)**:
- Auto-trigger of research without operator ask — operator-initiated only v1.
- Cross-Connector ranking of research results — canon-silent (gap per F2).
- Research result freshness / cache policy — overlaps F1 indexing; deferred v2.

## User outcome

Operator asks Native to research something; Native uses ecosystem tools (Context7 / Web / Connectors) and returns a typed Research Artifact ready to be consumed by next Workflow. Founder voice round 3: "I can do research on the fly by using Native".

## UX flow (narrative; terminal + audit log)

1. Operator issues research request via slash (`/research X`) OR conversational ("research X for me") — both paths per Q24 default.
2. Classifier matches → `ResearchWorkflow` fires.
3. ResearchWorkflow enumerates tools (Context7, WebSearch, configured Connectors per B17).
4. Per-tool retrieval runs (canon-silent on cross-tool sequencing — gap per F2).
5. Results aggregated into one typed Research Artifact (per B9 + P1).
6. Artifact registered; available to next Workflow's context-load per W-load-native-context (§5.5).

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Operator types `/research X` | classifier routes per ADR-015 | `ResearchWorkflow` fires; `routing_decision` (§3.2 #1) emitted |
| 2 | Operator says "research X for me" | classifier matches research intent | same `ResearchWorkflow` fires; conversational path per Q24 |
| 3 | ResearchWorkflow completes | aggregation finishes | typed Research Artifact registered per B9; `artifact_registered` (§3.2 #9) emitted |
| 4 | Tool error (Context7 unavailable, Slack token expired) | mid-ResearchWorkflow | routes via canon `on_failure` per §6.5 (no new fail-mode per F3) |

## Data model

Per §12.9 row B6: NEW Workflow class `ResearchWorkflow`. Per F5, canon authorizes new class within existing Workflow primitive. Not a new §2 primitive.

```
ResearchWorkflow extends Workflow (canon §2.3):
  + tool_targets[]    // Context7, WebSearch, Connector ids
  + research_artifact_id  // produced artifact reference
```

Cross-refs:
- `../primitives/workflow.md` (host primitive)
- `../primitives/engine-event.md` (substrate)

## Edge cases

- **Empty tool_targets list** → degenerate ResearchWorkflow; fallback semantic NOT specified in canon (gap per F2).
- **Operator interrupts mid-research** → routes via canon §6.8 recovery; partial results may be persisted (specific partial-persistence rule NOT specified in canon — gap per F2).
- **Multiple ResearchWorkflows concurrent** → handled per B13 ConcurrencyCoordinator.
- **Connector returns malformed data** → schema-validation failure routes via §6.5 on_failure.

## Telemetry

Events (canon-existing only):
- `routing_decision` (§3.2 #1) — research intent matched.
- `workflow_started` (#2) / `workflow_completed` (#3) / `workflow_failed` (#4).
- `artifact_registered` (#9) — Research Artifact persisted.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved — research-on-fly directly displaces manual research time.

## Dependencies

- **Primitives**: `workflow`, `engine-event`, `tenant`.
- **Events**: `routing_decision`, `workflow_started`, `workflow_completed`, `workflow_failed`, `artifact_registered`.
- **Surfaces**: `route`, `run`, `audit`.
- **Hardstops**: HS-3 (tenant-boundary), HS-4 (audit-unwritable).
- **Blocks**: B17 (External tools / Connectors substrate), B9 (Research Artifact emission), 7a (Research Artifact joins context catalog).
- **Pillars**: P11 (Constrained problem construction).
- **ADRs**: ADR-015 (H-Sutra classification — conversational match).

## References

- NATIVE-ENGINE.md §12.9 row B6 (founder voice round 3).
- Q24 (§12.11) — slash + conversational both v1.
- Memory `project_connectors_slack_live` — Slack Connector live.
- Memory `feedback_context7_default` — Context7 default for library/framework/SDK docs.
