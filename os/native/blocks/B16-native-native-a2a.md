---
part-id: B16
bucket: blocks
template: L8-feature-spec
parity-source: §12.17 row B16 + §12.16 founder voice round 5 + Q35
parity-source-sha256: 2da345277a5c474d8f475931106c49507e345b46910ee04e65209e89a1492e6e
status: DRAFT v1
authored: 2026-05-09
---

# B16: Native-Native (Agent-to-Agent) Communication

## 1-line summary

Native instances exchange typed messages with each other via a minimum-viable A2A envelope `{src_native_id, dst_native_id, msg_type, payload, ack_id, agent_identity_chain}`; ack required; v1 stub logs intent.

## Scope (in / out)

**In scope (v1 stub)**:
- NEW A2A protocol per §12.17 row B16.
- Minimum viable envelope per Q35 default (2026-05-09) — `{src, dst, msg_type, payload, ack_id, agent_identity_chain}`.
- Ack required.
- v1 ships stub that LOGS intent (per §12.17 "stub v1 logs intent"); full handshake deferred.

**Out of scope (v1)**:
- Capability negotiation between Natives — Q35 v3.
- Cross-org A2A — v3+ per P13.
- Self-healing routing / retry — canon-silent (gap per F2).

## User outcome

Two Natives (e.g., founder's Native + co-worker's Native) can exchange typed messages — agents interact within the org structure. Founder voice round 5: "agents interact within them, the founder/founder interacts within them, and that's how it really would work out."

## UX flow (narrative; terminal + audit log)

1. Native A wishes to send a typed message to Native B.
2. Native A constructs envelope per Q35: `{src_native_id, dst_native_id, msg_type, payload, ack_id, agent_identity_chain}`.
3. v1 stub: envelope written to log (intent recorded per §12.17); actual delivery deferred.
4. Future (post-stub): Native B receives → emits ack → both update audit log.
5. Audit + DecisionProvenance row per message per ADR-007.

## Acceptance criteria (Given/When/Then)

| # | Given | When | Then |
|---|---|---|---|
| 1 | Native A submits A2A message | envelope validation | envelope must include all 6 fields per Q35; missing field → rejected |
| 2 | Envelope valid | v1 stub | logged as intent per §12.17; actual delivery deferred (no fail-mode invention per F3) |
| 3 | Native B receives + ack | future v1.x | ack flows back to A; both Natives' audit logs reconcile |
| 4 | `agent_identity_chain` truncated or missing | validation | rejected; identity chain is required per Q35 |

## Data model

NEW A2A protocol per §12.17 row B16. Per F5, canon authorizes new protocol. Not a new §2 primitive — protocol lives at integration layer.

```
A2AEnvelope = {
  src_native_id
  dst_native_id
  msg_type
  payload
  ack_id
  agent_identity_chain[]   // identity chain per ADR-005 effector boundary
}
```

Cross-refs:
- `../primitives/tenant.md` (Native instances are per-Tenant per ADR-016 replica)
- `../primitives/engine-event.md` (substrate)
- `../primitives/decision-provenance.md` (per-message audit row)

## Edge cases

- **Native B offline** → delivery semantics NOT specified in canon (gap per F2; future ADR may codify queue / retry).
- **Replay attack on ack_id** → ack_id idempotency NOT specified in canon (gap per F2; future ADR may codify dedup).
- **Identity chain spoofing** — STRIDE relevance (Spoofing); canon §7 threat model covers identity-chain integrity; specific defense for A2A NOT specified (gap per F2).
- **Cross-org message** → not v1; v3+ per P13.

## Telemetry

Events (canon-existing only):
- `policy_decision` (§3.2) — message routing decision.
- `artifact_registered` (#9) — A2A envelope persisted as audit artifact per P1 closed-loop.

Metrics affected (cross-ref `../metrics/north-star-ohs-per-week.md`):
- Founder weekly active sessions (future, multi-human use case) — Native-Native comm reduces inter-human latency.

## Dependencies

- **Primitives**: `tenant`, `engine-event`, `decision-provenance`.
- **Events**: `policy_decision`, `artifact_registered`.
- **Surfaces**: `audit`, `tenant`.
- **Hardstops**: HS-3 (tenant-boundary — A2A respects Tenant isolation), HS-4 (audit-unwritable).
- **Blocks**: B13 (Multi-runtime concurrency — A2A overlaps), B14 (Multi-human-org host structure), B15 (Local vs Org artifacts — A2A may carry artifact references), B17 (External tools — A2A is internal Native-Native; external = Connectors).
- **Pillars**: P13 (Multi-human-org-Native architecture).
- **ADRs**: ADR-005 (effector boundary + agent_identity), ADR-016 (replica isolation).

## References

- NATIVE-ENGINE.md §12.17 row B16 (founder voice round 5).
- Q35 (§12.19) — minimum viable envelope v1; capability negotiation v3.
- §8 OS-22 (A2A cross-process workflow comm — deferred v2).
- §7 Threat Model (STRIDE relevance).
