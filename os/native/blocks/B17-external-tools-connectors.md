---
part-id: B17
bucket: blocks
template: L8-feature-spec
parity-source: §12.17 row B17 + §12.16 founder voice round 5 + Q36
parity-source-sha256: f5d58e57d3ac0f0012280fc4544c988a25a3e775de7c2ca0c18c7dda2fbb535b
status: DRAFT v1
authored: 2026-05-09
---

# B17: External Tools (Connector Layer)

## 1-line summary

Every external tool (Slack, Email, web, etc.) is a typed Connector — inbound messages become Artifacts in the catalog; outbound messages emit DecisionProvenance + Artifact rows; Workflow steps are tool-aware.

## Scope (in / out)

**In scope (v1)**:
- EXTEND existing Connectors (Slack live per memory `project_connectors_slack_live`; MCP servers; via plugin) per §12.17 row B17.
- Every external tool = typed Connector class per Q36 default (2026-05-09) — Connectors stay the abstraction.
- Inbound msgs → Artifact log (per B9 closed-loop).
- Outbound msgs → DecisionProvenance per ADR-007 + Artifact emit per B9.
- Tool-aware Workflow steps (step declares `connector_id` to route via).

**Out of scope (v1)**:
- New primitive class for "external comm channels" — Q36 rejects; Connectors stay the abstraction.
- Auto-discovery of new external tools — not specified in canon (gap per F2).
- Cross-Connector orchestration ranking — overlaps F1 indexing; deferred v2+.

## User outcome

Operator's external tools (Slack, Email, etc.) feed and receive from Native naturally — inbound becomes context, outbound is audit-tracked. Founder voice round 5: "external tools as well, where in the people would communicate, so we need to ensure that whenever we are trying to do something, we take the external tools as well".

## UX flow (narrative; terminal + audit log)

1. External tool sends message inbound (Slack mention, email arrives, etc.).
2. Connector receives → emits `artifact_registered` (§3.2 #9) for inbound message per B9.
3. Inbound Artifact joins context catalog; routable per 7a / B11.
4. Workflow step with `connector_id='slack'` (or similar) fires outbound.
5. Connector dispatches outbound → emits DecisionProvenance row per ADR-007 + outbound Artifact per B9.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Inbound message arrives via Connector | Connector handler runs | `artifact_registered` (§3.2 #9) emitted; inbound Artifact persisted with `Artifact-type=<connector>-inbound` (specific type-naming NOT specified in canon — gap per F2) |
| 2 | Workflow step declares `connector_id` matching configured Connector | step fires | outbound message dispatched; DecisionProvenance per ADR-007 emitted + Artifact per B9 |
| 3 | Connector authentication expired / token revoked | dispatch attempted | failure routes via canon `on_failure` per §6.5 (no fail-mode invention per F3) |
| 4 | New external tool requested | author Connector class | per Q36, stays within Connector abstraction; no new primitive class |

## Data model

Per §12.17 row B17 + Q36: EXTEND existing Connectors. No new §2 primitive (per F5).

```
Connector = {
  connector_id
  tool_name             // 'slack', 'email', 'web', etc.
  auth_config           // token / oauth config
  inbound_handler       // routes incoming msgs to Artifact log
  outbound_dispatcher   // routes outbound to external tool
}
```

Cross-refs:
- `../primitives/workflow.md` (steps may declare `connector_id`)
- `../primitives/engine-event.md` (artifact_registered substrate)
- `../primitives/decision-provenance.md` (outbound audit row)

## Edge cases

- **Token revoked mid-dispatch** → `on_failure` per §6.5.
- **Inbound message malformed (Slack API change, etc.)** → schema-validation failure routes via §6.5.
- **Cross-Connector message duplication** (e.g., Slack message also forwarded via email) → dedup rule NOT specified in canon (gap per F2).
- **Connector-emitted Artifact crosses Tenant boundary** → HS-3 fires per §6.9.3.

## Telemetry

Events (canon-existing only):
- `artifact_registered` (§3.2 #9) — inbound + outbound messages persisted.
- `policy_decision` — dispatch routing decision.
- `tenant_boundary_violation` — on cross-Tenant attempt.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Operator-Hours-Saved — Connectors directly displace manual cross-tool ferrying.
- Cross-company decision-replay success rate — outbound DecisionProvenance preserves replay.

## Dependencies

- **Primitives**: `workflow`, `engine-event`, `decision-provenance`, `tenant`.
- **Events**: `artifact_registered`, `policy_decision`, `tenant_boundary_violation`.
- **Surfaces**: `route`, `run`, `audit`, `tenant`.
- **Hardstops**: HS-3 (tenant-boundary), HS-4 (audit-unwritable).
- **Blocks**: B6 (Research-on-the-fly composes Connectors), B9 (Artifact catalog substrate), B16 (Native-Native vs external — distinct: B16 = internal, B17 = external).
- **Pillars**: P13 (Multi-human-org-Native architecture — external tools as comm channels), P1 (Artifact-first — all I/O = Artifacts).

## References

- NATIVE-ENGINE.md §12.17 row B17 (founder voice round 5).
- Q36 (§12.19) — Connectors stay the abstraction.
- Memory `project_connectors_slack_live` — Slack live 2026-04-30.
- Memory `feedback_context7_default` — Context7 MCP default.
