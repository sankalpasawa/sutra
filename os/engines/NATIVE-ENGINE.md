# Sutra — Native Engine

ENFORCEMENT: HARD (runtime — primitive contracts, terminal_check, tenant isolation, telemetry); SOFT (operator UX — CLI, renderer registry).
STATUS: v1.0 GA shipped 2026-04-30; v1.1.x productization shipped 2026-05-03; v1.2 organic-emergence merged behind `SUTRA_NATIVE_PROPOSER` 2026-05-04. Ongoing v1.x waves per `holding/plans/native-v1.x/RESUME-V1.X.md`.
DRI: CEO of Asawa (engine-of-record). Founder-direction route for all Native protocol/architecture amendments.

Peer engines: see `sutra/os/engines/BLUEPRINT-ENGINE.md`, `sutra/os/engines/HUMAN-SUTRA-ENGINE.md`, `sutra/os/engines/ESTIMATION-ENGINE.md`.
ADRs reserved by this charter: ADR-004 .. ADR-017 (registry at `sutra/os/decisions/`). Decision provenance: see `holding/plans/native-formalization-v1.0/EXTRACTION.md`.

---

## 1. Purpose

Native is the Sutra runtime that turns Workflow JSON into executed work via host-LLM dispatch with a complete typed audit trail. One founder + one host-LLM install Native with a single command and get an operating layer that classifies founder utterances, fires registered Workflows, persists Executions, emits typed EngineEvents, gates approvals, enforces tenant boundaries, and produces DecisionProvenance for every consequential decision. Native ships as the `native@sutra` plugin (`sutra/marketplace/native/`); the host-LLM session is the effector that performs file/git/network mutations the Workflow declares.

---

## 2. Primitives

| Slot | Name | Reserved at | ADR |
|---|---|---|---|
| Runtime entity | Domain, Charter, Workflow, WorkflowStep, TriggerSpec, ExecutionResult, EngineEvent, Tenant | §2 below | ADR-007, ADR-009 |
| Decision provenance | DecisionProvenance | §2.9 + §3 | ADR-007 |
| Effector boundary | host-LLM session | §5 Integrations.host-llm | ADR-004, ADR-005 |
| Tenant ownership | `Domain.tenant_id` field | §6 Operations.multi-tenant | ADR-006 |

### 2.1 Domain

| Field | Type | Invariant |
|---|---|---|
| `id` | string (D-pattern: `D0` or `D<int>(.D<int>)*`) | matches I-1 |
| `name` | string | non-empty |
| `parent_id` | string \| null | null IFF `id == 'D0'`; else parent must exist |
| `principles` | string[] | append-only |
| `accountable` | string | role identifier |
| `authority` | object | scope of decisions Domain may make |
| `tenant_id` | string (T-hash) | required; references `Tenant.id`; see ADR-006 |

### 2.2 Charter

| Field | Type | Invariant |
|---|---|---|
| `id` | string (C-hash) | content-addressed |
| `purpose`, `scope_in`, `scope_out` | string / string[] | non-empty `purpose` |
| `obligations` | object[] | ≥1 OR explicitly empty + reasoned (I-2) |
| `invariants`, `success_metrics`, `constraints` | object[] | typed; machine-checkable per F-10 |
| `acl` | object[] | per-tenant access list |
| `cutover_contract` | object \| null | rollback gate, behavior_invariants, canary_window |
| `authority`, `termination` | object | declarative |

### 2.3 Workflow

| Field | Type | Invariant |
|---|---|---|
| `id` | string (W-hash) | content-addressed |
| `preconditions`, `postconditions` | typed predicate (PNC) | parsed per ADR-012; not free prose |
| `step_graph` | WorkflowStep[] | terminal_check T1-T6 (I-5) |
| `failure_policy` | enum | one of `rollback`, `escalate`, `pause`, `abort`, `continue` (ADR-011) |
| `stringency` | enum | `process` \| `directive` \| `principle` |
| `interfaces_with`, `expects_response_from` | string[] | typed boundary refs |
| `on_override_action` | enum | `pause` \| `block` \| `audit-only` |
| `reuse_tag` | bool | `true` ⇒ Workflow is a Skill; requires `return_contract` |
| `return_contract` | JSON Schema \| null | required IFF `reuse_tag=true` |
| `custody_owner` | Tenant id \| null | declares state ownership |
| `extension_ref` | string \| null | v1.0: must be null |
| `modifies_sutra` | bool | `true` ⇒ requires reflexive_check Constraint cleared (L6) |
| `requires_approval` | bool | per-workflow approval gate (ADR-009) |

### 2.4 WorkflowStep

| Field | Type | Invariant |
|---|---|---|
| `skill_ref` | string \| null | XOR with `action` (I-3) |
| `action` | enum \| null | one of registered action kinds (e.g. `invoke_host_llm`, `emit_event`) |
| `host` | enum \| null | required IFF `action='invoke_host_llm'`; one of `claude`, `codex` (ADR-005) |
| `inputs` | DataRef[] | each carries `schema_ref` + `authoritative_status` (ADR-008) |
| `outputs` | DataRef[] / Asset | typed; sink rules in §6 Operations |
| `on_failure` | enum | one of the 5-set; defaults to Workflow.failure_policy |
| `requires_approval` | bool | step-level gate (ADR-009) |
| `timeout_ms` | int \| null | per-step override; flows into host activity args |
| `prompt_template` | string \| null | required IFF `action='invoke_host_llm'` |

### 2.5 TriggerSpec

| Field | Type | Invariant |
|---|---|---|
| `id` | string | unique |
| `pattern` | enum | one of `preprocessor`, `observer`, `gate`, `fan_out`, `negotiation` |
| `predicate` | typed predicate (match-all / match-any / cron) | not free prose |
| `target_workflow_id` | string | must resolve in registry |
| `cadence` | object \| null | tick/cron spec (see ADR-017) |

### 2.6 ExecutionResult

| Field | Type | Invariant |
|---|---|---|
| `id` | string (E-hash) | content-addressed |
| `workflow_id` | string | references Workflow |
| `trigger_event` | object | the EngineEvent that initiated execution |
| `state` | enum | one of `running`, `success`, `failed`, `awaiting_approval`, `paused`, `declared_gap` |
| `logs` | EngineEvent[] | append-only |
| `results` | object | per-step outputs |
| `parent_exec_id`, `sibling_group` | string \| null | child Execution lineage |
| `failure_reason` | string \| null | null IFF `state ∈ {success, declared_gap}` (I-4) |
| `agent_identity` | object | inferred per ADR-015; chain-shaped per OQ-D4-2 |
| `tenant_context` | object | `{tenant_id}`; required for cross-tenant ops (ADR-006) |
| `partial` | bool | true when `failure_policy='continue'` advanced past failure |

### 2.7 EngineEvent

Append-only typed audit row. One JSONL line per event. See §3 for full type catalog. Persisted per ADR-013.

| Field | Type | Invariant |
|---|---|---|
| `event_type` | enum (26 values) | exhaustive — see §3 |
| `ts_ms` | int | monotonic; assigned at emit |
| `execution_id` | string \| null | null for events outside an Execution (e.g. routing_decision) |
| `payload` | object | type-specific; validated against per-event schema |
| `agent_identity` | object | per ADR-015 |

### 2.8 Tenant

| Field | Type | Invariant |
|---|---|---|
| `id` | string (T-hash) | content-addressed |
| `name` | string | non-empty |
| `isolation_contract` | object | filesystem + capability isolation declaration |
| `parent_tenant_id` | string \| null | null for root |
| `audit_log_path` | string | absolute path to Tenant's DecisionProvenance JSONL |

### 2.9 DecisionProvenance

Emitted by every Workflow / Execution / Hook for every consequential decision (I-7). Schema per ADR-007.

| Field | Type | Invariant |
|---|---|---|
| `id` | string (uuid v4) | unique |
| `ts_ms` | int | monotonic |
| `agent_identity` | object | chain (parent → child) |
| `policy_id`, `policy_version` | string | non-empty (I-9; F-8) |
| `scope` | enum | `WORKFLOW` \| `STEP` \| `HOOK` \| `TENANT` \| `CUTOVER` |
| `outcome` | enum | `allow` \| `deny` \| `pause` \| `escalate` |
| `reason` | string | sanitized (no colons / newlines) |
| `data_refs` | DataRef[] | each with `authoritative_status` per ADR-008 |

---

## 3. Contract

### 3.1 Engine API (TypeScript signatures)

```
NativeEngine.handleHSutraEvent(evt: HSutraEvent): Promise<RoutingDecision>
NativeEngine.run(workflowId: string, ctx: RunContext): Promise<ExecutionResult>
NativeEngine.resumeApproved(execId: string): Promise<ExecutionResult>
NativeEngine.on_host_llm_result(execId: string, stepIdx: int, r: HostLLMResult): Promise<void>   // §8 OS-1

LiteExecutor.executeWorkflow(wf: Workflow, ctx: ExecCtx): Promise<ExecutionResult>
Router.route(evt: HSutraEvent): RoutingDecision                                                  // sync (live path)
Router.routeAsync(evt: HSutraEvent): Promise<RoutingDecision>                                    // latent — §8 OS-8

CadenceScheduler.tick(now_ms: int): TriggerEvent[]
CadenceScheduler.start(intervalMs: int): void                                                    // ADR-017

SkillEngine.resolve(skill_ref: string): Workflow | null                                          // v1.0; §8 OS-12

PolicyDispatcher.evaluate(scope, evidence): DecisionProvenance
TenantIsolation.assertCrossTenantAllowed(srcTenant, dstTenant, op): void                         // throws on deny

UserKit.loadWorkflows(home: string): Workflow[]
UserKit.appendDecisionProvenance(dp: DecisionProvenance): void                                   // fsync per ADR-013
```

### 3.2 EngineEvent type catalog (26 types)

Every event carries `event_type`, `ts_ms`, `execution_id?`, `agent_identity`, `payload`. Listed by lifecycle group.

| # | event_type | When emitted | Key payload fields |
|---|---|---|---|
| 1 | `routing_decision` | Router selects (or rejects) a Workflow for an HSutraEvent | matched_workflow_id, predicate_id, score |
| 2 | `workflow_started` | Execution enters `running` | workflow_id, trigger_event_id |
| 3 | `workflow_completed` | Execution enters terminal `success` | execution_id, results_ref |
| 4 | `workflow_failed` | Execution enters terminal `failed` | execution_id, failure_reason |
| 5 | `step_started` | LiteExecutor dispatches step[i] | step_index, host?, timeout_ms |
| 6 | `step_completed` | Step returns successfully | step_index, output_ref, duration_ms |
| 7 | `step_paused` | `failure_policy='pause'` triggered at step | step_index, pause_reason |
| 8 | `policy_decision` | PolicyDispatcher emits a deny/allow/escalate | policy_id, policy_version, outcome |
| 9 | `artifact_registered` | New Asset/DataRef registered in catalog | artifact_id, lineage_parent_id |
| 10 | `precondition_check` | Workflow.preconditions evaluated (ADR-012) | wf_id, predicate_id, result |
| 11 | `postcondition_check` | Workflow.postconditions evaluated (ADR-012) | wf_id, predicate_id, result |
| 12 | `pattern_proposed` | Pattern detector reaches k≥4 (ADR-010) | pattern_hash, k, sample_utterances |
| 13 | `proposal_approved` | Founder approves a proposed Workflow | proposal_id, workflow_id |
| 14 | `proposal_rejected` | Founder rejects a proposed Workflow | proposal_id, reason |
| 15 | `approval_requested` | Step with `requires_approval=true` reached (ADR-009) | execution_id, step_index, prompt_summary |
| 16 | `approval_granted` | Founder utterance `approve E-<id>` parsed | execution_id, approver_id |
| 17 | `approval_denied` | Founder utterance `reject E-<id> <reason>` parsed | execution_id, reason |
| 18 | `approval_already_handled` | Idempotent re-fire on resolved approval | execution_id, prior_outcome |
| 19 | `workflow_rollback_started` | `failure_policy='rollback'` initiated | execution_id, snapshot_ref |
| 20 | `step_compensated` | Single step's compensation completed | step_index |
| 21 | `step_compensation_failed` | Compensation itself failed | step_index, reason |
| 22 | `workflow_rollback_complete` | All steps compensated; Execution restored | execution_id |
| 23 | `workflow_rollback_partial` | Some steps not compensable; partial state | execution_id, uncompensated_steps[] |
| 24 | `workflow_escalated` | `failure_policy='escalate'` triggered | execution_id, channel |
| 25 | `commitment_broken` | Workflow failed and L4-COMMITMENT obligation missed (ADR-012) | charter_id, obligation_id |
| 26 | `tenant_boundary_violation` | Cross-tenant op attempted without delegation (HS-3; ADR-006) | src_tenant, dst_tenant, op |

### 3.3 CLI subcommands (`bin/sutra-native`)

| Subcommand | Purpose |
|---|---|
| `start` | Spawn detached daemon; acquire PID lock |
| `stop` | Stop daemon; release PID lock |
| `daemon` | Direct daemon entrypoint (spawned by `start`) |
| `status` | Print daemon state, registry counts, tenant list |
| `version` (`-v`, `--version`) | Print Native version |
| `help` (`-h`, `--help`) | Print usage |
| `create-domain` | Mint Domain JSON in user-kit |
| `create-charter` | Mint Charter JSON |
| `create-workflow` | Mint Workflow JSON; accepts `--steps` including `invoke_host_llm`, `--host <claude\|codex>`, `--prompt-N <text>` |
| `create-trigger` | Mint TriggerSpec; predicate from `--match-all` / `--match-any` |
| `list` | List primitives in user-kit |
| `run` | Execute a Workflow by id |
| `workflow status` | Show Execution states |
| `workflow cancel` | Cancel a running Execution |
| `tenant list` | Enumerate tenants |
| `cutover validate` | Run cutover_contract checks |

### 3.4 Approval utterances

| Utterance | Effect |
|---|---|
| `approve P-<id>` | Approve a proposed Workflow (ADR-010) |
| `approve E-<id>` | Resume an Execution in `awaiting_approval` (ADR-009) |
| `reject E-<id> <reason>` | Deny a pending Execution; emit `approval_denied` |

### 3.5 Authoritative state

Every DataRef carries `authoritative_status ∈ {authoritative, advisory}` per ADR-008. The field resolves markdown-vs-code conflicts at lookup time; readers honor authoritative entries over advisory ones.

---

## 4. Invariants

Each invariant is testable; tests live with the corresponding primitive or engine.

| # | Invariant |
|---|---|
| I-1 | `Domain.id` matches D-pattern (`D0` or `D<int>(.D<int>)*`). |
| I-2 | `Charter.obligations` has ≥1 entry OR is explicitly empty + reasoned. |
| I-3 | Every `WorkflowStep` has `skill_ref` XOR `action` (mutually exclusive; F-4 + F-5). |
| I-4 | `ExecutionResult.failure_reason` is null IFF `state ∈ {success, declared_gap}`. |
| I-5 | Every Workflow passes terminal_check predicates T1-T6 before any step dispatches. |
| I-6 | Per-turn governance overhead ≤15% of token budget. HARD-STOP at >25% (HS-2). |
| I-7 | Every Workflow Execution emits ≥1 DecisionProvenance per consequential decision. |
| I-8 | Tenant boundary not crossed without an explicit `delegates_to` edge (HS-3). |
| I-9 | Every governance hook emits DecisionProvenance carrying `policy_id` AND `policy_version`. |
| I-10 | Cutover canary observes `behavior_invariants` throughout `canary_window`. |
| I-11 | First-time T4 user reaches first useful Execution in ≤30 min on fresh install. |
| I-12 | CadenceScheduler fires within ±5 min of scheduled time (ADR-017). |
| I-13 | Every `Domain` is owned by exactly one `Tenant` via `tenant_id`; the field is required (ADR-006). |
| I-14 | Every Workflow Execution emits exactly one terminal EngineEvent: one of `workflow_completed`, `workflow_failed`, `approval_requested` (transitioning to `awaiting_approval`). |
| I-15 | Every Execution in `awaiting_approval` has a persisted ledger row at `user-kit/pending-approvals/E-<id>.json` (ADR-009). |
| I-16 | Every `commitment_broken` event references a Charter obligation id that resolves in the registry. |
| I-17 | Every DecisionProvenance carries `policy_id` AND `policy_version` (F-8). |

Forbidden couplings (F-1 .. F-10): see `holding/research/2026-04-29-native-d4-primitives-composition-spec.md` §3. Each is a HARD reject at terminal_check.

---

## 5. Integrations

### 5.1 host-llm (effector boundary)

| Aspect | Contract |
|---|---|
| Hosts | `claude --bare` (recursion-safe; no plugin sync, no CLAUDE.md auto-load, no hooks) and `codex exec` (read-only sandbox). See ADR-005. |
| Dispatch | `WorkflowStep.action='invoke_host_llm'` with `host` + `prompt_template` + `timeout_ms`. |
| Effector split | Native is registry+audit; the founder's interactive host-LLM session performs file/git/network mutations declared by the Workflow. See ADR-004. |
| Identity | `agent_identity` chain inferred from session metadata; emitted on every DecisionProvenance per ADR-015. |
| Failure | Subprocess timeout → `step_failed` event → routes per `Workflow.failure_policy`. |

### 5.2 Sutra plugin (`@sutra` core)

| Aspect | Contract |
|---|---|
| Registry | Workflows + Triggers loaded from `user-kit/` at boot. |
| Audit | DecisionProvenance + EngineEvent rows append to `user-kit/decision-provenance.jsonl`. |
| Skills | Resolved via `SkillEngine.resolve(skill_ref)` from the same registry (Workflow with `reuse_tag=true`). |

### 5.3 H-Sutra event bus

| Aspect | Contract |
|---|---|
| Producer | Native ships its own `per-turn-h-sutra.sh` + `classify.sh` (vendored; no `core@sutra` runtime dep). See ADR-015. |
| Consumer | `HSutraConnector` tails the JSONL log; forwards each row to `NativeEngine.handleHSutraEvent`. |
| Schema | One JSONL row per founder turn carrying 9-cell + 3 tags (per `sutra/os/charters/HUMAN-SUTRA-LAYER.md`). |
| Failure mode | Append fail-CLOSED at row level; missing rows never block downstream Edit/Write/Bash. |

### 5.4 Build-Layer governance

| Aspect | Contract |
|---|---|
| Marker check | `holding/hooks/build-layer-check.sh` reads `.claude/build-layer-registered` on every Edit/Write touching D38 paths. |
| L0 default | `sutra/marketplace/native/**` ships at L0; Native primitives consult build-layer markers when emitting Workflow scaffolds. |
| Override | `BUILD_LAYER_ACK=1 BUILD_LAYER_ACK_REASON='<why>'` honor-system; logged with actor, path, cmd, declared_layer. |

### 5.5 Context-load (W-load-native-context)

| Aspect | Contract |
|---|---|
| Pattern | Native dogfoods its own registry+audit pattern: `W-load-native-context` is a Workflow that fires `codex exec` and emits a load-plan JSON. See ADR-014. |
| Purpose | Depth-router: pulls only the Native context needed for a turn, scored by depth + task class. |
| Audit | Each load fires an Execution; load-plan JSON is the structured `return_contract`. |

### 5.6 Telemetry sink

| Aspect | Contract |
|---|---|
| Format | JSONL append-only; one EngineEvent or DecisionProvenance per line. |
| Durability | `fsync` per append; stderr beacon fallback when primary path unwritable (ADR-013). |
| OTel | OTel emitter shape live with NoopExporter at v1.1.x; OTLPHttpExporter is a stub (production transport in v1.x backlog). |

### 5.7 Replica

| Aspect | Contract |
|---|---|
| Path | `$HOME/.sutra-native-asawa-replica/` (separate `SUTRA_NATIVE_HOME`). See ADR-016. |
| Purpose | Asawa-specific dogfood; 21 Domains + 8 Charters + 6 Workflows + 6 Triggers replicating the holding company in Native primitives. |
| Reset | `bash holding/scripts/build-asawa-native-replica.sh` (idempotent). |

---

## 6. Operations

### 6.1 Telemetry replay

DecisionProvenance JSONL is the replay surface. Every consequential decision is rebuildable from `agent_identity + policy_id + policy_version + data_refs + outcome`. Cross-process replay is deferred (see §8 OS-3).

### 6.2 Multi-tenant isolation

Tenant scan at boot via `Domain.tenant_id`. `TenantIsolation.assertCrossTenantAllowed` is called unconditionally when `Execution.tenant_context.tenant_id` differs from a step's effective tenant. Fail-closed when `workflow.custody_owner !== null` AND `tenant_context_id` is undefined. See ADR-006.

### 6.3 Replica / SUTRA_NATIVE_HOME

`SUTRA_NATIVE_HOME` env var redirects user-kit reads/writes. Asawa replica uses `$HOME/.sutra-native-asawa-replica`; primary user-kit at `$HOME/.sutra-native/user-kit`. See ADR-016.

### 6.4 Cadence scheduling

`CadenceScheduler.start(intervalMs)` runs as a daemon-side `setInterval` tick. On each tick, scheduled cadences within the ±5 min window fire `TriggerEvent` rows. No external cron / launchd dependency. See ADR-017.

| Cadence | Use |
|---|---|
| Per-hour | Sutra-OS monitoring tick |
| Per-6h | Sutra-OS team tick |
| Daily | Asawa daily pulse (default composition) |
| Weekly | Authoritative-vs-advisory drift report |
| Monthly | cso comprehensive threat audit |
| Quarterly | V2.x stress-test |

### 6.5 on_failure machinery

`step.on_failure ∈ {rollback, escalate, pause, abort, continue}` (5-set per ADR-011).

| Policy | Effect |
|---|---|
| `rollback` | Emit `workflow_rollback_started`; compensate steps in reverse; terminal `workflow_rollback_complete` or `_partial`. |
| `escalate` | Emit `workflow_escalated`; route to founder channel. |
| `pause` | Emit `step_paused`; persist queue entry; resume on signal. |
| `abort` | Emit `workflow_failed` immediately. |
| `continue` | Log failure; advance to step[i+1]; set `partial=true`; skip outputs validation for the failed step; do NOT abort. |

### 6.6 Approval ledger

Persisted per execution awaiting approval at `user-kit/pending-approvals/E-<id>.json` carrying `{workflow_id, step_index, ts_ms, prompt_summary}`. Resumed via `approve E-<id>` utterance → `NativeEngine.resumeApproved(execId)` → continue at `step_index+1`. See ADR-009 + I-15.

### 6.7 Per-step timeout

`step.timeout_ms` flows into host activity args. When unset, defaults to host-class default (60s for `claude --bare`; complex codex tasks need ≥300s per Wave 1 evidence on DayFlow run).

### 6.8 Recovery

CLI surface (P-C11):

| Command | Authority |
|---|---|
| `sutra recover --status` | any |
| `sutra recover --rollback <snapshot>` | Tenant owner OR founder |
| `sutra recover --disable <component>` | Tenant owner |
| `sutra recover --repair <issue-id>` | Tenant owner + founder approval |
| `sutra recover --reset` | Founder ONLY (DESTRUCTIVE) |

### 6.9 HARD-STOP conditions

| # | Condition | Escalation |
|---|---|---|
| HS-1 | reflexive_check Constraint violated (Sutra primitives modified without authorization) | Founder ASK gate |
| HS-2 | Governance overhead >25% | Abort turn; emit HARD-STOP DecisionProvenance |
| HS-3 | Tenant boundary cross attempted without TenantDelegation | Block + log + escalate |
| HS-4 | DecisionProvenance log unwritable across all 3 channels | Block all governance hooks; stderr beacon |
| HS-5 | Cutover rollback fails | Pause cutover; founder + Tenant owner HITL |
| HS-6 | 3+ governance hooks fail in same turn | Suspend session; founder HITL |
| HS-7 | Codex review queue >20 OR >7d stale | Block shipment; founder HITL |
| HS-8 | Production canary regression | Auto-rollback; founder notify |

---

## 7. Threat Model

Layered on D5 §3 HARD-STOP (HS-1..HS-8), D1 §11 cutover-as-defense, F-1..F-10 forbidden couplings.

| STRIDE | Attack class | Vector | Native primitive at risk | Mitigation | Invariant guard |
|---|---|---|---|---|---|
| **Spoofing** | host-LLM identity spoofing | Subprocess presents wrong agent_identity; chain not verifiable | `Execution.agent_identity`, `DecisionProvenance.agent_identity` | `claude --bare` recursion-safe (no recursive plugin/hook load); agent_identity chain inferred from session metadata on every emit | I-7, I-9 |
| **Tampering** | Workflow JSON injection | Malicious string in `WorkflowStep.inputs` or `prompt_template` subverts host-LLM step | `Workflow.step_graph[i].inputs`, `action='invoke_host_llm'`, `DecisionProvenance.reason` | L2 BOUNDARY rejects malformed steps at primitive-mint; ajv-compiled schema validates DataRef before executor; sanitized `failure_reason` | I-3, I-7 |
| **Tampering** | PNC predicate injection | Free-prose preconditions/postconditions evade gating | `Workflow.preconditions`, `Workflow.postconditions` | Typed parser per ADR-012; F-10 forbids English-only routing/gating positions | I-5, F-10 |
| **Tampering** | Hook tampering | Workflow attempts to modify `sutra/marketplace/plugin/hooks/*.sh` | `Workflow.modifies_sutra` | L6 REFLEXIVITY law + F-7: `modifies_sutra=true` without reflexive_check Constraint cleared = HARD reject; `build-layer-check.sh` PreToolUse hook | HS-1, I-7 |
| **Repudiation** | Audit-trail loss | DecisionProvenance log unwritable; consequential decision leaves no trace | DecisionProvenance JSONL | fsync per append (ADR-013); stderr beacon fallback; dual fallback to `/tmp` | HS-4, I-7, I-9 |
| **Information Disclosure** | Cross-tenant leakage | Workflow under Tenant A reads Tenant B resource without delegation | `Execution.tenant_context.tenant_id`, `Workflow.custody_owner`, `delegates_to` edge | TenantIsolation engine: runtime-derived enforcement; F-6 at terminal_check; fail-closed when `custody_owner !== null` AND `tenant_context_id` undefined | I-8, HS-3 |
| **Information Disclosure** | Exfiltration via DataRef.retention bypass | Session-scope DataRef written to permanent-retention Asset | `DataRef.retention`, Asset lifecycle_states | DOC-ONLY at v1.0: schema-level retention captures intent; post-hoc audit via DecisionProvenance. Sink-policy enforcement deferred — §8 OS-14 | I-7 (post-hoc) |
| **Information Disclosure** | Supply-chain (malicious Skill) | Tampered Skill registered; subsequent `resolve()` loads malicious version | `SkillEngine.register`, `SkillEngine.resolve` | PARTIAL at v1.0: JSON Schema validation on `return_contract`; F-13 (no `return_contract` = reject). Commit-pin / signature verify / SBOM consult deferred — §8 OS-13 | HS-1 (partial) |
| **Denial of Service** | Per-step / per-host hang | host-LLM subprocess wedges; Workflow stalls | `WorkflowStep.timeout_ms`, host activity args | Per-step timeout configurable; 15-min hard cap on codex per `core:codex-sutra`; daemon kills wedged child on timeout | HS-7 |
| **Denial of Service** | Governance overhead exhaustion | Per-turn blocks consume >25% token budget | Hook self-test, OTel emitter | I-6 governance overhead measurement; HS-2 HARD-STOP at >25% | I-6, HS-2 |
| **Elevation of Privilege** | Approval-gate bypass | Step proceeds past `requires_approval=true` without `approval_granted` event | `WorkflowStep.requires_approval`, ledger row | LiteExecutor pause behavior persists ledger row + emits `approval_requested` + returns `awaiting_approval`; resume requires utterance match `approve E-<id>` per ADR-009 | I-14, I-15 |
| **Elevation of Privilege** | Reflexive primitive modification | Workflow modifies Sutra core without authorization | `Workflow.modifies_sutra`, reflexive_check Constraint | L6 REFLEXIVITY + F-7 + HS-1 founder ASK gate | HS-1 |

---

## 8. Open Seams

Numbered backlog for v1.x and beyond. Each row carries an open question + pointer.

| # | Seam | Open question | Pointer |
|---|---|---|---|
| OS-1 | Daemon-routed autonomous path | Can `NativeEngine.on_host_llm_result` write back without re-entering founder session? | RESUME-V1.X §0; per-workflow sandbox config required (ADR-004 deferred slice) |
| OS-2 | Per-workflow sandbox config | What schema declares "this Workflow may write filesystem from daemon"? | RESUME-V1.X §0; v1.3 scope per CLAUDE.md NL routing table |
| OS-3 | Cross-process replay | How does Tenant A's daemon replay an Execution that originated in Tenant B's process? | D5 OQ; v1.x deferred |
| OS-4 | Cutover engine production wiring | Runtime cutover engine still aspirational | D1 §11; final-architecture §6 |
| OS-5 | `commitment_broken` event semantics | When `failure_policy='continue'` advances past a step that violated a Charter obligation, does `commitment_broken` fire at terminal `workflow_failed` only, or per-step? | RESUME-V1.X Wave 5 #12 |
| OS-6 | Wire Full Temporal Workflow Executor onto live runtime path | LiteExecutor sync stub covers v1.0 | block-diagram §4 backlog |
| OS-7 | Own UserPromptSubmit intake | Native today depends on `core@sutra` writing H-Sutra log | block-diagram §4 backlog |
| OS-8 | Wire Router.routeAsync() + LLMFallback | Sync routing covers v1.0; first deterministic-predicate gap forces async + LLM fallback | block-diagram §4 backlog |
| OS-9 | Wire ArtifactCatalog into execution path | Catalog built but not called by engine | block-diagram §4 backlog |
| OS-10 | OTel production transport | OTLPHttpExporter is non-functional stub; no WAL | block-diagram §4 backlog |
| OS-11 | Multi-AI nested agent_identity | Claude calls codex calls Claude — chain shape needs schema adjustment | D4 OQ-D4-2; ADR-015 follow-up |
| OS-12 | Skill Engine compose / create / bias / auto_retire | v1.0 ships only `resolve` | D4 §6; OQ-D4-3 |
| OS-13 | Skill commit-pin + signature verify | Threat-model §4 deferred mitigation | threat-model §4; OQ-T-1 |
| OS-14 | DataRef sink-policy enforcement | Threat-model §5 deferred mitigation | threat-model §5; OQ-T-2 |
| OS-15 | Multi-party approval | `Approval.approver` becomes a list with quorum predicate when first use case lands | D5 OQ-D5-4 |
| OS-16 | Cadence scheduler advanced spec | Higher-level rate spec vs cron-style escape-hatch | D5 OQ-D5-5 |
| OS-17 | Cohort / cross-cohort routing | Cohort primitive is batch-targeting (per ADR-006 rejected alternative); first multi-cohort routing use case may require revisit | D1 §3 |
| OS-18 | Migration doc cohort order | `MIGRATION.md` still documents older T0→T2→T3→T4; charter ships A→B→C→D→E per D41 | block-diagram §4 doc TODOs |
| OS-19 | Manifest test-count drift | `marketplace.json` + `plugin.json` advertise 1207 tests; source ships 1273 | block-diagram §4 doc TODOs |
| OS-20 | Per-invocation MCP context passing | `claude --bare` skips MCP context; first MCP-context need forces wire-up | block-diagram §4 deferred |
| OS-21 | LLMSubstrate adapter | OpenAI / Gemini swap; first non-Claude use case | final-architecture §6 |
| OS-22 | A2A cross-process workflow comm | First cross-process workflow forces wire-up | final-architecture §6 |
| OS-23 | SPIFFE / SPIRE multi-tenant | First multi-tenant deployment forces wire-up | final-architecture §6 |
| OS-24 | Constitutional veto Safety predicate | First "authorized but unsafe" decision forces wire-up | final-architecture §6 |
| OS-25 | Coverage templates per business function | T4 demand unknown; first request forces template land | final-architecture §6 |
