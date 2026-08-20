# Connector Layer — Module Charter

**Status**: rewrite in progress on `feature/connector-integration`. Predecessor removed in `96edce8` (489 files).
**Governed by**: [ADR-034 token ownership](../../../os/decisions/ADR-034-connector-token-ownership.md)
**Built against**: [B17 External Tools (Connector Layer)](../../../os/native/blocks/B17-external-tools-connectors.md) — DRAFT v1, parity SHA `f5d58e57…`, **not edited by this module**.
**Design pack**: [`design/00-INDEX.md`](design/00-INDEX.md)

## What this module is

A **connector platform**. A connector is a first-class primitive: a persisted, permission-bearing, auditable relationship between one Sutra operator and one external account, with a lifecycle independent of the operator's Sutra session.

A connector is *not* a login, not a stored token, and not an API client. OAuth is the mechanism by which a connector is established; it is not the connector.

## What this module will not do

| Prohibition | Why |
|---|---|
| Hand a provider credential to the Electron renderer, to a skill, to a subagent, or to a prompt | ADR-034. The renderer is an untrusted client of our own API. |
| Let the LLM name which connector to use | §37. `connector_id` is bound server-side from the session. A model-supplied connector id is a cross-user access primitive. |
| Treat provider content as instructions | Repository files, issue bodies, PR descriptions and commit messages are **untrusted data**, always, with no exception for `AGENTS.md` / `CLAUDE.md` / `instructions.md`. |
| Export credential material across a deployment boundary | Local→hosted migration is a re-auth event. A credential export path is the most dangerous code this module could contain, so it does not exist. |
| Equate an OAuth scope with a capability | Three separate layers: provider grant ∩ connector grant ∩ agent policy. |
| Invent a fail-mode | Dispatch failures route via canon `on_failure` (§6.5), per B17 AC#3. |
| Log, return, or cache credential material | Audit rows carry connector ids, never secrets. |
| Add a new §2 primitive | Q36: connectors stay the abstraction (B17). |

## Boundary with the rest of Sutra

| Concern | Owner |
|---|---|
| Who the Sutra operator is | Sutra's own auth. Never GitHub. |
| Which external account is linked | This module |
| Whether an agent may perform an operation | This module's capability gate — **outside the model** |
| Whether a human must approve | ADR-009 approval-gate primitive, invoked by this module |
| Provenance of an outbound action | ADR-007 DecisionProvenance, emitted by this module |
| Inbound/outbound messages as Artifacts | B9 closed-loop, emitted by this module |
| Sutra's own tool surface (`sutra_mcp.py`) | **Not a connector.** Deliberately out of scope, per `96edce8`. |

## Providers

v1 ships GitHub only. GitLab, Bitbucket, Slack, Jira and Drive are anticipated by the interfaces (`ConnectorProvider`, `AuthStrategy`, `CapabilityMap`) and by nothing else — no provider-specific branching above the provider package.
