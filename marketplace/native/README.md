# Native — Sutra Engine Plugin (v1.0)

The deployable Claude Code plugin clients install — built fresh on the V2.4 Sutra Engine architecture (4 primitives + 6 laws + Skill Engine R4 + 6 terminal-check predicates).

Status: under construction (M1 scaffold). See `holding/plans/native-v1.0-execution-plan.md` for the 12-milestone roadmap.

## What's here (after v1.0 ships)

- `src/primitives/` — Domain, Charter, Workflow, Execution
- `src/laws/` — L1 DATA, L2 BOUNDARY, L3 ACTIVATION, L4 COMMITMENT, L5 META, L6 REFLEXIVITY
- `src/engine/` — Workflow Engine + Skill Engine + 4 starter engines (BLUEPRINT, COVERAGE, ADAPTIVE-PROTOCOL, ESTIMATION)
- `src/schemas/` — DataRef, Asset, TriggerSpec, BoundaryEndpoint, Interface, Constraint, Cohort
- `src/hooks/` — PreToolUse, PostToolUse, Stop
- `bin/` — bash thin shims that exec into TS hooks
- `skills/` — SKILL.md + schema.json sidecars per skill
- `tests/` — contract / property / integration

## Stack

- TypeScript 5.x (strict mode, ESM, ES2022)
- Bun runtime preferred; Node 20+ fallback OK
- Vitest 1.x + fast-check 3.x (property-based testing)
- JSONL append-only state with typed reducers + snapshots

## Coexistence with Core

Native is self-contained. Does NOT depend on Core plugin internals. Core (existing fleet) keeps running unchanged. Both ship to clients via Sutra Marketplace.

## Install (post-v1.0 release)

```
/plugin install native@sutra-marketplace
```

## Operationalization

1. Measurement: install count via Sutra Marketplace telemetry; Native session count vs Core
2. Adoption: T2 onboarding CM9 pattern — DayFlow first; Billu/Paisa/PPR/Maze follow
3. Monitoring: 7d canary observation post each T2 onboard; T+0→T+60s install verification
4. Iteration: client-reported issue OR codex audit finding triggers v1.x patch
5. DRI: Asawa CEO + Sutra-OS team rotation
6. Decommission: V3.0 ships breaking changes superseding V2.x, OR Native plugin discontinued

> **M2 primitive contracts** inherit ops surface from §Operationalization above
> (measurement = test-coverage; iteration trigger = contract-violation in CI).

> **M2 patch (2026-04-28)** — primitive validators tightened; constructors now
> reject spec-illegal shapes at boundary. Workflow.createWorkflow HARD-rejects
> reuse_tag=true with null/empty return_contract (V2.3 §A11). Workflow
> step_graph[i].on_failure validated against StepFailureAction enum;
> expects_response_from shape (null|non-empty string) and modifies_sutra type
> defensively checked. isValidWorkflow extends to all routing/gating fields
> for deserialized records. Charter ACL deeply validated
> (domain_or_charter_id non-empty string, reason non-empty) in both
> createCharter and isValidCharter. Domain enforces V2 §1 P1 invariants:
> id='D0' iff parent_id=null; non-root parent_id matches D-pattern;
> principles[*].durability='durable'. 26 new contract tests (43→69). Tag:
> native-v1.0-m2-codex-p1-fixed.

## Laws (M3) — V2 §3 + V2.1 §A6 + V2.4 §A12

Six pure-predicate transformation laws plus the 6 terminal-check predicates
(T1-T6) live at `src/laws/`. All laws operate on M2 primitive shapes; no I/O,
no runtime state. Property tests (fast-check, 1000 runs each) live at
`tests/property/`; deterministic edge tests at `tests/contract/laws/`. Shared
arbitraries at `tests/property/arbitraries.ts`.

### L1 DATA law

- **Rule** (V2 §3): "DataRef → Asset iff `stable_identity AND len(lifecycle_states) > 1`"
- **API**: `l1Data.shouldPromoteToAsset(ref) → boolean`
- **Measurement**: contract test coverage (deterministic) + property test counterexample density
- **Iteration trigger**: fast-check counterexample on regression run
- **Adoption**: read-only utility; no in-repo callers yet (Workflow Engine M5 + schemas M4 will consume)
- **Monitoring**: telemetry hook deferred to M5; intended event shape `{kind:l1_promotion, ts, ref_id}` in `~/.sutra/native/events.jsonl`
- **DRI**: Asawa CEO + Sutra-OS team rotation
- **Decommission**: V3.0 ships breaking changes superseding V2.x

### L2 BOUNDARY law

- **Rule** (V2 §3): "Every Interface MUST have `contract_schema` (JSON schema). 'Environment' is not a type."
- **API**: `l2Boundary.isValid(iface) → boolean`
- **Measurement**: contract test for malformed JSON + empty schema; property tests for valid JSON-object + valid JSON-string-root rejection
- **Iteration trigger**: M5 Workflow Engine integration may surface need for full Ajv compile (deferred per M3.2.3)
- **Adoption**: ready for M5 dispatch-stage interface check
- **Monitoring**: violations logged at the engine layer (M5)
- **DRI**: Sutra-OS team
- **Decommission**: V3 supersession or full Ajv replacement

### L3 ACTIVATION law

- **Rule** (V2 §3): "TriggerEvent creates Execution iff `schema_match(payload) AND route_predicate(payload)`."
- **API**: `l3Activation.shouldActivate(event, spec) → boolean`
- **Measurement**: 4 contract edges + 4 property tests covering the truth-table for (schemaMatch × routeMatch × spec_id_match × predicate_throws)
- **Iteration trigger**: spec-string compilation lands in M5 (replaces accept-precompiled-fn shim)
- **Adoption**: ready for M5 trigger dispatcher
- **Monitoring**: per-trigger activation counter at engine layer
- **DRI**: Sutra-OS team
- **Decommission**: V3 supersession

### L4 COMMITMENT law (load-bearing)

- **Rule** (V2 §3): "operationalizes(W,C) iff every workflow step traces to obligation/invariant AND all charter obligations have explicit coverage or `gap_status='accepted'`."
- **API**: `l4Commitment.{tracesAllSteps, coversAllObligations, operationalizes}(W, C, coverage) → boolean`
- **Measurement**: 7 contract edges + 5 property tests; happy + missing-coverage + accepted-gap branches
- **Iteration trigger**: Workflow Engine integration (M5) reads coverage matrix at terminate stage; deviations logged
- **Adoption**: M5 Workflow Engine `terminate` stage will invoke `tracesAllSteps` + `coversAllObligations`
- **Monitoring**: telemetry: per-execution coverage matrix snapshot
- **DRI**: Sutra-OS team
- **Decommission**: V3 supersession

### L4 TERMINAL-CHECK (T1-T6)

- **Rule** (V2.4 §A12): A Workflow Execution reaches `state=success` iff ALL six predicates hold at terminal_check time. Any `T_i==false` → `state=failed`, `failure_reason=terminal_check_failed:T<i>`.
- **API**: `l4TerminalCheck.runAll(ctx) → TerminalCheckResult`; individual `t1Postconditions / t2OutputSchemas / t3StepTraces / t4InterfaceContracts / t5NoAbandonedChildren / t6ReflexiveAuth` exported for granular telemetry
- **Measurement**: 18 property tests (positive + negative per T_i, plus aggregate happy + T2-fail edge); 1 contract edge for T2 fail in commitment suite
- **Iteration trigger**: T6 specifically fires escalation TriggerSpec (V2.2 §A9) on failure — Engine wiring lands in M5
- **Adoption**: M5 Workflow Engine `terminate` stage runs the 6 predicates in order
- **Monitoring**: per-execution `failure_reason` recorded in JSONL event log; per-T failure counter at engine layer
- **DRI**: Sutra-OS team + founder gate (T6 escalation path)
- **Decommission**: V3 supersession

### L5 META law

- **Rule** (V2 §3 + V2.1 §A1): "Single containment edge: `Domain.contains(Charter)`. All others typed."
- **API**: `l5Meta.{isValidContainment, isValidEdge, typedEdges}() → boolean | Set<TypedEdgeKind>`
- **Measurement**: 5 contract edges + 3 property tests covering the (kind × parent × child) cube; explicit V2.1 §A1 `propagates_to` inclusion verified
- **Iteration trigger**: new typed-edge addition in V2.5+ requires update to TYPED_EDGES set
- **Adoption**: M4 schemas + M5 graph traversal will consume
- **Monitoring**: graph-edge audit at engine layer
- **DRI**: Sutra-OS team
- **Decommission**: V3 supersession

### L6 REFLEXIVITY law

- **Rule** (V2.1 §A6): "Workflows that modify Sutra primitives require an explicit `reflexive_check` Constraint with founder OR meta-charter authorization."
- **API**: `l6Reflexivity.{requiresApproval, reflexiveChecks}(workflow, constraints, satisfaction?) → boolean | Constraint[]`
- **Measurement**: 5 contract edges + 5 property tests (modifies_sutra=false no-op; modifies_sutra=true with/without reflexive_check; founder-auth vs meta-charter-approval branches)
- **Iteration trigger**: T6 in terminal-check is the post-commit verification; L6 fires PRE-execution. Engine wires both at M5.
- **Adoption**: M5 Workflow Engine dispatch stage runs L6; terminate stage runs T6
- **Monitoring**: founder gate state + meta-charter approval ledger feed `satisfaction` map
- **DRI**: founder (gate) + Sutra-OS team (engine)
- **Decommission**: V3 supersession

> **M3 ship (2026-04-28)** — 6 laws + T1-T6 + arbitraries + 187 tests
> (43 new contract law tests + ~31 property law tests covering 25,000+
> fast-check cases). Coverage: stmts 96.89% / branches 82.87% / funcs 100%
> / lines 96.89% (all above 80% threshold). TS strict clean. Tag:
> `native-v1.0-m3-shipped`. Codex Layer 1 xhigh review pending
> (controller-dispatched).

### DecisionProvenance schema (M4.3)

- **Measurement**: contract test count + property test counterexample density (5,000+ cases)
- **Iteration trigger**: any consequential decision in M5+ that the schema can't represent
- **DRI**: Sutra OS team
- **Decommission**: V3 supersession of D2 §2.1 spec
- v1.0 contract: DecisionProvenance schema is shipped at M4 as a typed contract. The emission gateway (Activity wrapper that pushes DP via OTel SDK to OTel Collector) lands at M8. M4 does NOT ship the emitter — only the shape.
- F-8 partial enforcement: `policy_id` + `policy_version` both `min(1)`; full F-8 cross-coupling at terminal_check lands at M4.9 chunk 2.

### Execution.agent_identity (M4.2)

- **Measurement**: count of Executions with non-null agent_identity / total
- **Iteration trigger**: founder request to attribute decisions to specific LLMs/agents in audit
- **DRI**: Sutra OS team
- **Decommission**: Inherited from M2.4+ Authority Map evolution
- D-NS-10 founder default (c) applied: id values use namespace prefix per kind (`claude-opus:abc`, `codex:session-xyz`); cross-kind prefixes rejected at constructor + validator.

### Tenant primitive (M4.1)

- **Measurement**: contract test count + property test counterexample density
- **Iteration trigger**: any cross-tenant operation surfaces in audit log
- **DRI**: Sutra OS team
- **Decommission**: when Tenant moves from sovereignty primitive to inherited from SPIFFE
- D-NS-9 default applied (codex P1.2): only `extension_ref` extension seam ships in M4.5; the other 4 candidate seams defer to v1.x.

### Test data fixtures (M4.10)

- **Measurement**: count of fixtures vs primitives ≥ 1:1; fixtures self-test count
- **Iteration trigger**: any new primitive in M4-M12 ships with a matching fixture in the same commit
- **DRI**: Sutra-OS team
- **Decommission**: V3 schema generators auto-emit fixtures
- See `tests/fixtures/README.md` for the factory convention (`validMinimal()` / `validFull()` / `invalidMissingRequired()`).

> **M3 patch (2026-04-28)** — L2 schema-root validation tightened (array
> roots, raw-boolean trivial schemas, and JSON-null roots all rejected per
> V2 §3 HARD spirit, conservative); L4/T3 step coverage soundness via
> Workflow primitive-level enforcement of unique step_ids in step_graph
> (createWorkflow throws; isValidWorkflow rejects deserialized duplicates);
> L4 obligation coverage relation-check (covered_by_step MUST exist in
> workflow.step_graph AND step.traces_to MUST include the obligation it's
> claimed to cover — closes the unsoundness where operationalizes(W,C) could
> return true with fabricated coverage decisions); runAll property test
> density bumped 200 → 1000 cases. 19 new contract + property tests
> (187 → 206). Coverage: stmts 96.99% / branches 83.08% / funcs 100% /
> lines 96.99%. TS strict clean. Sub-tag:
> `native-v1.0-m3-codex-p1-fixed`. Awaits codex re-review
> (controller-dispatched).
