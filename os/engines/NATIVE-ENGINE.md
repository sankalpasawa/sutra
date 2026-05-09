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

---

## 14. PRD (Product Requirements Document) — L6 per holding/PRODUCT-DOC-STANDARD.md

### 14.0 Concise PRD — one-page summary

**For:** founder + manager-IC operating multi-stranded judgment-driven work.
**What:** Operating system that turns the operator's daily work into named, gated, audited workflows; learns the operator over time; carries picked work through the full lifecycle from analysis to auto-run.
**Why:** Multi-strand operators lose decisions, learnings, and action items to noise; vanilla LLMs execute but don't OPERATE.

| Section | Answer |
|---|---|
| **Problem** | Manager-ICs lose judgment-based work to noise; quality drifts at portfolio scale. |
| **User** | v1 wedge: solo founder operating 1-N companies (terminal-fluent). v2+ TAM: any manager-IC in any org. |
| **Solution** | Native runtime → 6 surfaces (ROUTE · RUN · GATE · EMERGE · AUDIT · TENANT) on host-LLM substrate; closed-loop artifact catalog; person formation; Sutra OS 8-phase lifecycle. |
| **Top-5 v1 outcomes** | (1) closed-loop artifact (B9) · (2) pre/post LLM validation (B7) · (3) lifecycle orchestrator (7d) · (4) explanation control (B5) · (5) person formation (B18). |
| **Top-3 risks** | codex/OpenAI dep · T4 fleet adoption signal · audit-log unwritability. |
| **N\* metric** | Operator-Hours-Saved per week ≥3 within 14d of install (see §11). |
| **Status** | RATIFIED v1.1 (2026-05-09 — codex consult round-3 CHANGES-REQUIRED resolved; 5 blockers/advisories addressed; Q11-Q14 answered §12.4; P13 falsification tightened §10.3; §14.10 Q1/Q4/Q5/Q6/Q8 founder signoff complete). 18 capability blocks identified; v1 ships every block as stub minimum (P3); top-5 get full impl per §14.15.2. |

**Goals (v1):** every utterance routes through typed classifier · every consequential decision emits DecisionProvenance · pattern repeats ≥4 → propose → approve → registered · cross-tenant ops gated · 1-command install (D49).

**Non-goals (v1):** UI/visual designer · autonomous execution (founder gates) · multi-LLM (claude/codex only) · auto-register patterns · browser automation · memory product · consumer app · capability-additive over vanilla Claude Code.

**Read-on:** §14.1-§14.12 detailed PRD · §14.13-§14.16 appendices (foundation index · process · kickoff · TODO sweep) · §10 Philosophy · §11 Vision · §12 Mission · §13 Strategy.

---

## 14. PRD (full) — L6 per holding/PRODUCT-DOC-STANDARD.md

**Status:** RATIFIED v1.1 (2026-05-09 — claude-drafted from canon + directions + memory + agent research; founder reviewed in-session; all goals/risks/metrics/JTBD/non-goals/solution-overview accepted; Q1/Q4/Q5/Q6/Q8 founder signoff complete per codex consult round-3 gate)
**Pipeline layer:** L6 (Asawa PRD template, influenced by Google-style PM/design docs)
**Pre-§10-§13 note:** Per codex Applied-To-Native rec (2026-05-09), Native is implementation-heavy + D54-canon-forced; PRD lands here BEFORE L1 Philosophy (§10) / L2 Vision (§11) / L3 Mission (§12) / L4 Strategy Map (§13), which derive from the validated problem space defined here. Subsequent turns backfill §10-§13.

### 14.1 Problem Statement

Founders running multiple companies + cross-cutting responsibilities lose decisions, action items, and learnings to noise. Existing tools (note apps · todo apps · Slack · email) capture data but don't OPERATE the founder's day. Vanilla LLMs (Claude Code · ChatGPT · Cursor) execute well but lack: persistent identity-of-system · audit trail per consequential decision · pattern emergence · multi-tenant isolation · governance discipline visible to founder.

Result: founder works HARDER than they should; cognitive load grows with portfolio size; quality drifts when multiple companies share context; learnings stay trapped in single-session memory.

### 14.2 Target User / Persona

**v1 wedge target (founder Q10 confirmed 2026-05-09):** solo founder operating a portfolio of 1-N companies + cross-cutting knowledge-work concerns. Technical (terminal-fluent) · design-particular · speed-prioritized. Identifies as CEO of holding-co (T1) running owned portfolio (T2) + projects (T3) + observing fleet (T4). v1 ships for this wedge; PMF signal here gates v2 expansion.

**v2+ TAM expansion (founder reframe Q1 2026-05-09):** any **manager-IC** in any organization — someone whose work has THREE strands simultaneously:
1. Named scope (the role they're hired for)
2. Judgment-based additional work (initiatives they take on by judgment, not assignment)
3. IC work (hands-on contribution, not just delegation)

Universal trait: workload is **judgment-driven + multi-stranded**. They cannot just "do their job" because the job IS variable + cross-cutting. This is the unifying need Native serves.

**Examples of who fits the primary persona:**

| Role | Manager work | Judgment work | IC work |
|---|---|---|---|
| Founder (1-N companies) | leads orgs / hires | cross-co initiatives | codes / writes / sells |
| VP / Director | leads team | cross-org strategy | reviews / writes / decides |
| Engineering Manager | leads engineers | architecture pushes | ships features |
| Product Manager | leads product line | research / strategy bets | designs / writes specs |
| Tech Lead / Senior IC | mentors team | architecture reviews | core code / tooling |
| Department Head | leads dept | coordinates with peer depts | hands-on execution |

**Secondary:** TBD — clarification needed (see Q9 below). Likely a subset of the primary at later seniority OR an extension to non-managerial multi-stranded ICs.

**Anti-persona:** end-users wanting consumer-app polish · teams >5 sharing one OS instance (multi-tenant is per-individual, not per-team). NG7 (non-technical users without terminal fluency) is **under reconsideration** per persona reframe — see §14.10 Q9.

### 14.3 JTBD — Christensen / Ulwick outcome statements

Outcome-driven needs as metric statements (direction + unit + object). NOT the "When [X], I want [Y]" sentence — that's L6 §14.4.

| # | Outcome |
|---|---|
| 1 | Minimize time to surface what was decided last week |
| 2 | Minimize variance in execution quality across N companies one operator runs |
| 3 | Minimize friction of converting a repeated utterance into a named, gated workflow |
| 4 | Minimize time to replay any past decision with full provenance |
| 5 | Minimize leakage of decisions / learnings / action items into noise across sessions |
| 6 | Maximize audit-trail completeness per consequential decision |
| 7 | Maximize cross-tenant boundary integrity (zero accidental leakage) |
| 8 | Maximize founder's confidence that work-in-progress will not be lost on session close |

### 14.4 Job Story (Intercom format)

When **I'm running multiple companies + my LLM agent does substantial work for me**, I want to **have every consequential decision recorded with full provenance + every repeated pattern offered as a named workflow + every cross-tenant operation gated**, so I can **trust the system's output without auditing every line + scale to N companies without losing coherence**.

### 14.5 Goals

| # | Goal |
|---|---|
| G1 | Every founder utterance routes through typed classifier (H-Sutra) + lands as a row in append-only JSONL |
| G2 | Every consequential decision (allow/deny/escalate/pause) emits a typed DecisionProvenance entry |
| G3 | Founder repeating a pattern ≥4 times within window → Native proposes named Workflow (founder approves → registered) |
| G4 | Cross-tenant ops gated by PolicyDispatcher; default deny; explicit delegation only |
| G5 | Risky steps pause for founder approval before host-LLM execution |
| G6 | Audit trail replayable (any past Execution re-walkable from EngineEvent log) |
| G7 | Native installs in 1 command on a fresh client (D49 standalone H-Sutra) |
| G8 | Sutra plugin client (T4 fleet) inherits Asawa governance discipline by default (D40) |

### 14.6 Non-goals (anti-scope, explicit)

| # | NOT |
|---|---|
| NG1 | NOT a UI/visual designer. Terminal + audit log + slash commands ONLY |
| NG2 | NOT autonomous execution. Daemon proposes; founder approves; host-LLM executes |
| NG3 | NOT multi-LLM (v1.x locked to claude/codex per ADR-005) |
| NG4 | NOT auto-registering patterns (founder approval gated per ADR-010) |
| NG5 | NOT browser automation (commodity per A3 research; consume not build) |
| NG6 | NOT a memory product (commoditized per Vellum 2026; Native claims governance + multi-tenant + emergence + audit) |
| NG7 | NOT a feature-rich consumer app (anti-persona) |
| NG8 | NOT capability-additive over vanilla Claude Code (per memory `no-Sutra-sycophancy`); Native adds content + integration + curation + distribution |

### 14.7 Solution Overview

Native = Sutra runtime. Turns Workflow JSON into executed work via host-LLM dispatch with complete typed audit trail. 6 core surfaces:

| Surface | What it does |
|---|---|
| ROUTE | Classify utterance → matched Workflow OR pattern proposal |
| RUN | Fire matched Workflow → host-LLM executes step |
| GATE | Pause on `requires_approval` → surface to founder |
| EMERGE | Propose new Workflow when pattern repeats ≥4 |
| AUDIT | Every transition emits typed EngineEvent + DecisionProvenance |
| TENANT | Isolated audit log + ACL per company |

Runtime contracts: §1-§9 (already canonical). Strategic context: §10-§13 (next turns).

### 14.8 Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Codex / OpenAI dependency for review primitives | LiteExecutor falls back to claude-only path; multi-LLM v2 deferred per ADR-005 |
| R2 | T4 fleet adoption slow (no compensating signal) | D41 cohort pivot to T4-first; A→T0→T4 gate sequencing |
| R3 | Pattern emergence false-positive overload | k=4 threshold + memory rule [≥3 erroneous proposals/week → pause emergence] |
| R4 | Audit log unwritable (HS-4 fail-closed) | 3-channel durability; stderr beacon last-resort |
| R5 | Multi-tenant cross-leakage | TenantIsolation engine; F-6 fail-closed; STRIDE mitigation |
| R6 | Founder ratification bottleneck | Approval primitive batches; multi-party approval per OS-15 |
| R7 | Native canon drift (D54 violation) | `verify-archive-completeness.sh` + native-canon-check hook (Phase 1.5 Task 17) |

### 14.9 Success Metrics — anchored on L2 North Star (§11)

**Input (leading):**

| Metric | Target |
|---|---|
| Time-to-first-Execution on fresh install | ≤30 min (per I-11 §4) |
| Pattern-detection precision (founder approval rate of proposed Workflows) | ≥75% |
| DecisionProvenance log completeness | 100% of consequential decisions logged |

**Output (lagging):**

| Metric | Target |
|---|---|
| Founder weekly active sessions | trend up over 12-week window |
| T2/T3/T4 cohort net retention | ≥80% at 14d post-onboard |
| Cross-company decision-replay success rate | ≥99% (any past Execution replayable) |
| Approval-gate latency (founder-side response) | ≤2 min median |

### 14.10 Open Questions (for founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q1 | ✅ ANSWERED 2026-05-09 — primary = founder-portfolio (solo founder operating 1-N companies, terminal-fluent); secondary = operator-class (single-company manager-IC). v1 wedge validates the tighter-feedback primary; v2 expansion to secondary once PMF lands. | n/a |
| Q2 | ✅ ANSWERED 2026-05-09 — NG7 (non-technical users without terminal fluency) is HARD RULE for v1. Revisit at v3 once terminal-CoS PMF is established and web/app surfaces (Q9 v2+ deferred) come online. | n/a |
| Q3 | ✅ ANSWERED 2026-05-09 — disclaim NG6 ("Native is NOT a memory product"); integrate Mem0/Composio via Native Connector primitive. Memory is commoditized substrate; Native's claim is governance + multi-tenant + emergence + audit + closed-loop artifact (§14.6 NG6, §13.2). | n/a |
| Q4 | ✅ ANSWERED 2026-05-09 — k=4 default for pattern emergence proposal threshold; per-tenant configurable in v2 once usage data lands per D45 organic emergence. | n/a |
| Q5 | ✅ ANSWERED 2026-05-09 — single-founder approval v1 (matches founder-portfolio wedge); multi-party quorum deferred per OS-15 to v2+ when portfolio scale demands cross-approver workflows. | n/a |
| Q6 | ✅ ANSWERED 2026-05-09 — per-Tenant subscription v1 (simplest revenue model; flat-rate per-company); outcome-based experiment v2+ once N* (OHS/wk) measurement proves and Sierra-style pricing maturity allows. | n/a |
| Q7 | ✅ ANSWERED 2026-05-09 — signal-based v1→v2 trigger per D41 revert: ≥3 T4 clients green for 14d post-onboard OR ≥1 T2 portfolio co blocked on Native upgrade. Time-based deferred (premature without signal). | n/a |
| Q8 | ✅ ANSWERED 2026-05-09 — every founder-owned layer (L1/L2/L3/L4/L6/L7/L11/L14) gets a founder checkpoint. 8 explicit gates per product-doc cycle. Highest quality; founder time investment accepted; matches Phase A kickoff framework §14.15.1. | n/a |
| Q9 | ✅ ANSWERED 2026-05-09 — stay terminal-only v1; web/app surfaces deferred v2+ | Smaller v1 TAM accepted; broader TAM via web/app comes after PMF |
| Q10 | ✅ ANSWERED 2026-05-09 — founder-portfolio v1 wedge; "any manager-IC" v2+ TAM expansion | v1 ships for the narrower segment; v2+ expands once v1 PMF signal lands |

### 14.11 Evidence Log (REQUIRED appendix per L6 standard)

Sources informing this PRD — every claim traces to founder utterance, canon, direction, agent research, or memory. NO fabrication.

| Source | What it informed |
|---|---|
| Founder seed (2026-05-08, this session) | "chief of staff for the respective founder ... helps the human achieve his potential" → §14.7 ROUTE/RUN/EMERGE framing |
| NATIVE-ENGINE.md §1 Purpose (canon) | Solution overview substrate (runtime + audit + emergence + tenant) |
| D44 (2026-05-01) | T4 workflow personalization → §14.5 G3 + Q3 |
| D45 (2026-05-03) | T0/T2 organic emergence k=4 → §14.5 G3 + R3 + Q4 |
| D49 (2026-05-06) | Native standalone H-Sutra → §14.5 G7 |
| D54 (2026-05-07) | canon-only writes → R7 |
| D34 (2026-04-24) | 4-tier client taxonomy → §14.2 persona structure |
| D38 (2026-04-28) | plugin-first implementation → §14.5 G8 |
| D40 (2026-04-30) | governance parity for T4 → §14.5 G8 |
| D41 (2026-04-30) | T4-first cohort pivot → R2 + Q7 |
| Founding Doctrine | Customer Focus First + Dynamic/Flexible/Scalable/Simple/Nuanced → §14.6 NGs (anti-complexity) + §14.5 G2 (audit transparency) |
| A1 agent canon coverage (2026-05-08) | "73% runtime / 27% product POV" → this PRD fills product POV |
| A3 external landscape (2026-05-08) | Bond/Donna competitor + Paperclip 63k stars + Sierra outcome-pricing → §14.2 anti-persona + §14.10 Q6 |
| A4 methodology research (2026-05-08) | Christensen JTBD + Amazon PR/FAQ + Wardley = 3-framework stack → §14.3 + §14.4 |
| Memory `project_three_product_tiers` | Project / CoS / System-of-CoS → §14.2 persona |
| Memory `project_sutra_vision_apr2026` | CoS agents + Context Engine + DAGs + 2 business models → §14.7 + Q6 |
| Memory `project_sutra_core_ip` | weight distribution engine; depth = weighting → §14.5 G2 audit completeness |
| Memory `feedback_no_Sutra_sycophancy` | "Native does NOT add capability over vanilla Claude Code" → §14.6 NG8 |

### 14.12 §10-§13 (forthcoming — derive from this PRD per codex Applied-To-Native rec)

§12 L3 Mission landed below per codex order. Next turns: §11 L2 Vision + N* metric → §13 L4 Strategy Map → §10 L1 Philosophy (WHY backfill).

---

### 14.13 Foundation Index — full Native foundation absorbed into PRD (per founder direction 2026-05-09)

Per founder: *"Ensure that all the things we have had in the foundation of Native, on the unit theory, and the entire principles of Native, which we have as of right now, and all the things we thought about, we pick those up and add this to the PRD."*

This sub-section cross-references every Native foundation source. Live PRD = §14.1-§14.12 above + this §14.13 index + §12 Mission + §12.5-§12.15 capability rounds. Future §10/§11/§13 feed back when authored.

#### 14.13.1 Engine charter (the runtime / tech-spec foundation)

This file (`NATIVE-ENGINE.md`) §1-§9 is the engine charter. Maps to L9 Tech Spec per PRODUCT-DOC-STANDARD §5.

| § | Topic | What it canonicalizes |
|---|---|---|
| §1 | Purpose | Native runtime turns Workflow JSON into executed work via host-LLM dispatch with typed audit trail |
| §2 | Primitives | Domain · Charter · Workflow · WorkflowStep · TriggerSpec · ExecutionResult · EngineEvent · Tenant · DecisionProvenance — 9 unit-theory primitives |
| §3 | Contract | TS API signatures + 26 EngineEvent types |
| §4 | Invariants | I-1..I-15 hard constraints + governance overhead measurement |
| §5 | Integrations | host-LLM (claude/codex) + cadence + replicas |
| §6 | Operations | Multi-tenant + 6 cadences + on_failure 5-set + Approval ledger + Recovery + HARD-STOP HS-1..HS-8 |
| §7 | Threat Model | STRIDE × Native primitives × mitigations |
| §8 | Open Seams | OS-1..OS-25 future-work backlog |

#### 14.13.2 Unit theory — Native primitives (§2 detail)

The 9 unit primitives in §2 ARE the unit theory. Each is content-addressed where applicable; each has typed schema + invariants.

| Primitive | Hash prefix | Role |
|---|---|---|
| Domain | D-pattern | top-level scope; tenant-owned |
| Charter | C-hash | governance contract within Domain |
| Workflow | W-hash | executable plan |
| WorkflowStep | (in Workflow) | atomic step; XOR skill_ref / action |
| TriggerSpec | string | predicate that fires Workflow |
| ExecutionResult | E-hash | per-run state |
| EngineEvent | (typed enum) | append-only audit row |
| Tenant | T-hash | isolation + ACL boundary |
| DecisionProvenance | uuid v4 | per-decision audit row |

#### 14.13.3 Decision rationale — 14 ADRs (sutra/os/decisions/)

Native carries 14 ADRs (ADR-004..017) reserving why-each-major-design-choice was made.

| ADR | Title | One-line decision |
|---|---|---|
| ADR-004 | Registry-and-Effector Split | Native owns registry+audit; founder session is the effector |
| ADR-005 | Host-LLM Host Selection | host=claude (recursion-safe) or codex (sandboxed); per-step choice |
| ADR-006 | Tenant Isolation via Domain.tenant_id | every Domain has a Tenant; cross-tenant fails closed without delegation |
| ADR-007 | Decision Provenance as Typed Primitive | every consequential decision emits DecisionProvenance |
| ADR-008 | Authoritative-vs-Advisory on DataRef | every DataRef carries explicit authoritative_status |
| ADR-009 | Approval Gate as Workflow-Level Primitive | requires_approval steps pause; approve E-<id> resumes |
| ADR-010 | Organic Emergence: Propose-Approve at k≥4 | pattern detector proposes Workflows when k≥4 utterance matches |
| ADR-011 | on_failure Policy: Closed 5-Set | {rollback, escalate, pause, abort, continue} only |
| ADR-012 | PNC Predicates: Typed Parser, Not Prose | preconditions / postconditions / failure_policy must be typed predicates |
| ADR-013 | Telemetry Sink: fsync'd JSONL Append | EngineEvent + DecisionProvenance persist as fsync'd JSONL |
| ADR-014 | Depth Router via Native's Own Workflow | W-load-native-context fires codex sandboxed; dogfood pattern |
| ADR-015 | Native Ships Its Own H-Sutra Producer | no runtime core@sutra dependency; vendored classify.sh |
| ADR-016 | Asawa Replica as Isolated SUTRA_NATIVE_HOME | replica at $HOME/.sutra-native-asawa-replica/; clean-reset path |
| ADR-017 | Cadence Scheduling: Daemon-Side setInterval | CadenceScheduler in daemon; ±5 min window; portable |

#### 14.13.4 Founder Directions — Native-relevant (17 D-entries)

Cross-reference to `holding/FOUNDER-DIRECTIONS.md` (full verbatim in `holding/state/native-product-design/CAPTURE.md`).

Directly Native: D44 (workflow personalization T4 PARKED) · D45 (organic emergence T0/T2) · D49 (standalone H-Sutra) · D54 (canon-only writes).

Native-context: D34 (4-tier taxonomy) · D35 (priority order) · D38 (plugin-first) · D40 (governance parity) · D41 (T4-first cohort).

Native-runtime: D29 (Sutra plugin naming) · D33 (client firewall) · D42 (H↔Sutra Layer v1) · D43 (capability surface) · D46 (OUT-DIRECT 3-check) · D47 (PERMISSIONS extension) · D48 (BLUEPRINT verification) · D50 (identity-on-wire).

Session: D51 (caveman) · D52 (autonomous push) · D53 (Context7).

#### 14.13.5 Founding Doctrine — 6 root principles (~/Claude/root-os/FOUNDING-DOCTRINE.md)

L0 Principles inherits from Doctrine. Every Native primitive must pass these 6 tests:

| # | Principle | Native test |
|---|---|---|
| 0 | Customer Focus First | every Native output must be immediately clear to the operator without explanation |
| 1 | Dynamic | adapts to inputs (Depth + Estimation + classifier per turn) |
| 2 | Flexible | accommodates variety (override protocol, kill-switches, Tier 3 enable_all) |
| 3 | Scalable | works for 1 tenant or 100 tenants without rewrite |
| 4 | Simple | every primitive understandable in 10 minutes at the layer where used |
| 5 | Nuanced | handles gray zones (HS-1..8 escalation; PNC-typed predicates) |

#### 14.13.6 Native Philosophy pillars — P1-P12 (consolidated from §12.10 + §12.14 + §12 mission rounds)

| # | Pillar |
|---|---|
| P1 | Artifact-first: every Native output is typed, addressable, logged, reusable, system-readable |
| P2 | Pre/post intent-specifics validation per LLM node (testing-framework analog) |
| P3 | All blocks in v1 even as stubs (completeness > depth-of-one-block) |
| P4 | Product-POV before Tech-POV (interface-first; reverse-engineer voice into core needs) |
| P5 | MECE domains (mutually exclusive, collectively exhaustive per user) |
| P6 | Operator controls explanation; system controls production |
| P7 | Native grows with the operator (taste model evolves) |
| P8 | Lifecycle is the unit of value (Sutra D30a 8-phase, gated→autonomous) |
| P9 | Closed-loop artifact (artifact catalog IS memory) |
| P10 | Typed config at every primitive layer (Domain principles+guidelines+decisions; Charter instructions+guidelines+constraints) |
| P11 | Constrained problem construction (every LLM call receives explicit composed prompt) |
| P12 | Deterministic surface around stochastic core (only LLM reasoning + action are stochastic) |

#### 14.13.7 Capability map — 17 blocks (B1-B12 + 7a-7e) + F1 future feature

Synthesized from founder voice rounds 1-4 (§12.3 + §12.6 + §12.13). Each block has: founder source · existing primitive · v1 ship-status. v1 ships every block as a stub minimum (per P3).

Block roster: B1 Intent Layer · B2 Decomposition · B3 Domain Hierarchy MECE · B4 Charter↔Context · B5 Explanation Surface · B6 Research-on-fly · B7 Pre/Post Validation · B8 Task Framework + Factors · 7a Context Structuring · 7b Localized Intelligence · 7c Block-by-Block Mode · 7d Lifecycle Orchestrator · 7e Mid-Exec Mutation · B9 Closed-Loop Artifact · B10 Typed Config · B11 PromptBuilder · B12 E2E Testing.

Future feature: F1 Indexing + Retrieval (deferred v2+).

#### 14.13.8 Agent research foundation (this session, 2026-05-08)

| Agent | Source | Key contribution to PRD |
|---|---|---|
| A1 | Native canon coverage read | NATIVE-ENGINE.md is 73% runtime / 27% product POV; this PRD fills the gap |
| A2 | Founder directions extract | 17 D-directions tagged for Native; doctrine 6 principles; STRONG vs WEAK direction coverage map |
| A3 | External CoS landscape (18 products) | Bond/Donna direct competitor; Paperclip 63k stars validates "Company OS" demand; Sierra outcome-pricing defensible; market gaps Native owns |
| A4 | Product-design methodology (13 frameworks) | JTBD + Amazon PR/FAQ + Wardley = recommended 3-framework stack; Applied-To-Native order = L6 PRD first then derive L1-L4 |

#### 14.13.9 Memory — Native-relevant entries (~/Claude/projects/.../memory/MEMORY.md)

| Entry | What it adds |
|---|---|
| `feedback_native_canon_only` | D54 canon discipline rules |
| `project_resume_native_v1x` | "resume native" trigger; pinned plan |
| `project_asawa_native_replica` | Native-primitive replica at $HOME/.sutra-native-asawa-replica/ |
| `project_d45_ratification` | D45 ratifies Native organic emergence |
| `project_three_product_tiers` | Project / CoS / System-of-CoS |
| `project_sutra_vision_apr2026` | CoS agents + Context Engine + DAGs + 2 business models |
| `project_sutra_core_ip` | weight-distribution engine; depth = weighting |
| `project_context_sphere_research` | graph + 3D scoring + budget constraint; ACT-R analog |
| `project_sutra_v1_5blocks` | P0 TRIAGE + 9 skills + 5 blocks (workflow / context / artifact / os / gov) |
| `feedback_no_Sutra_sycophancy` | Native does NOT add capability over vanilla Claude Code; adds content + integration + curation + distribution |
| `feedback_case_by_case_implementation` | v2 mechanisms ship only when feedback demands |
| `project_sutra_v2_design` | domain-first; Cynefin gate; 5 patterns; terminal check |
| `project_managed_agents_direction` | Sutra on Claude Managed Agents; Anthropic=infra, Sutra=intelligence |
| `feedback_no_fabrication` | only founder words + memory + referenced infra; surface gaps as questions |
| `project_paperclip_eval` | closest Sutra adjacency; MIT 63k stars; market validation signal |

#### 14.13.10 Cross-refs to live working docs

- `holding/state/native-product-design/CAPTURE.md` — Phase 1 capture: founder seed + 17 D-directions verbatim + doctrine + memory + agent index
- `holding/PRODUCT-DOC-STANDARD.md` — 15-layer pipeline standard (this PRD = L6 instance)
- `holding/research/_archive/native-v1.x/INDEX.md` — 54 archived pre-canon docs (frozen per D54)
- `holding/plans/native-v1.x/RESUME-V1.X.md` — pinned plan (FROZEN forward per D54)

---

**§14.13 = Foundation Index complete.** PRD now absorbs full Native foundation per founder direction 2026-05-09.

---

### 14.14 Process for Continuous Native Evolution (founder meta-question answered 2026-05-09)

**Founder ask (verbatim 2026-05-09):**
> "What is the best way to plan and build this out? Because we already have version one of native, and that is still not yet working appropriately as we thought. So I want to ensure that you know we have airtight documentation of native, and we keep on adding in the same documentation, but we ensure that in those, the documentation is very airtight, where if you want to change something, we just change on a case-to-case basis, but the core documentation of native is still very intact."

**Answer = 5 disciplines below.**

#### 14.14.1 Document architecture — 4 tiers by stability

| Tier | Sections | Change type | Cadence |
|---|---|---|---|
| **IMMUTABLE** | L0 Founding Doctrine (`~/Claude/root-os/FOUNDING-DOCTRINE.md`) + NATIVE-ENGINE.md §1-§9 (Engine Charter) + §10 Philosophy (P1-P13 once authored) | RARE — founder direction only | yearly review or major pivot |
| **AUTHORITATIVE** | §11 Vision · §12 Mission · §13 Strategy Map · §14 PRD | CASE-BY-CASE via new ADR-NNN | per major requirement shift |
| **ADDITIVE** | §12.X founder voice rounds (12.1, 12.5, 12.8, 12.12, 12.16, ...) · §16 Feature Specs (1 per feature) · §17 OKRs (1 per quarter) · §19 Release Notes | APPEND-ONLY | continuous |
| **DERIVED** | §14.13 Foundation Index · capability maps (§12.X.Y) · cross-reference tables · CAPABILITY-MAP.md | REGENERATED periodically | per consolidation pass |

#### 14.14.2 Idea absorption flow

```
                FOUNDER IDEA (free-form, voice-text, any shape)
                         |
                         v
            §12.X capture (VERBATIM, no synthesis)
                         |
                         v
            Reverse-engineer (Claude does this)
            ├── Blocks (B-list)         -> §16 Feature Specs queue
            ├── Beliefs (P-list)        -> §10 Philosophy seeds
            └── Questions (Q-list)      -> founder review checkpoints
                         |
                         v
            Periodic consolidation pass
            (when capacity for blocks > 5 OR founder triggers)
                         |
                         v
            §10 Philosophy update / §16 Feature Spec authoring
            / new ADR-NNN per material decision
                         |
                         v
            Codex consult (per [Codex consult on everything])
                         |
                         v
            Founder review (boxed checkpoint)
                         |
                         v
            RATIFIED -> live canon
```

Critical property: **founder voice is captured verbatim BEFORE synthesis**. Synthesis happens after capture; never replaces capture. Verbatim is permanent; synthesis is revisable.

#### 14.14.3 Change discipline — 3 change classes

| Change kind | Examples | Process | ADR required? |
|---|---|---|---|
| **TRIVIAL** | typo · threshold tune (k=4 → k=5) · cosmetic | direct edit; cascade-d13 TODO | no |
| **MATERIAL** | new field on a primitive · new EngineEvent type · new on_failure semantics · new Capability bucket | new ADR-NNN + charter section update referencing ADR | YES |
| **STRUCTURAL** | new primitive class · new architecture layer · scope-pivot (T2 → T4 cohort) | new founder-direction (D-NNN) + cascade to all affected charters + ADR-NNN | YES + D-NNN |

#### 14.14.4 v1-not-yet-working honesty (per P3 + founder ask)

Per P3 (all blocks in v1 even as stubs): v1 ships with **every block PRESENT but not necessarily FUNCTIONAL**. v1 status today = `DRAFT` throughout §14.

Iteration cadence:
1. Founder identifies a block that's not working / missing logic
2. Block status in capability map flagged "needs fill"
3. Per-block ADR-NNN (material) OR Feature Spec §16 (atomic) authored
4. Implementation lands
5. Codex review (consult before / review on diff)
6. Founder confirms; block status → "ratified"

Repeat per block. v1 evolves to v1.1, v1.2, ..., v2.0 (when STRUCTURAL change accumulates enough to warrant a major).

**No false ratification:** the standard's `Status` field (DRAFT / RATIFIED / DEPRECATED / SUPERSEDED) gates downstream work. Honest "DRAFT" beats premature "RATIFIED".

#### 14.14.5 Core-intact discipline — what makes the doc airtight

| Discipline | Mechanism |
|---|---|
| Canon-only writes (D54) | `holding/research/*native*` + `holding/plans/native-*` BLOCKED via PreToolUse hook (Phase 1.5 Task 17 shipped); forward writes route via `holding/skills/updating-native-canon.md` decision tree |
| Decision rationale separation | charter (NATIVE-ENGINE.md §1-§9) holds CONTRACTS only; rationale lives in ADR-NNN; charter sections reference ADRs |
| Verbatim capture | founder voice → §12.X verbatim block FIRST; synthesis AFTER (revisable); verbatim permanent |
| Codex review at every material change | per `core:codex-sutra` skill; PROTO-019 directive gate; verdict file mandatory |
| Build-Layer marker | every Edit/Write to canon path requires marker (per D38 + LEGACY-HARD); no silent edits |
| Status-field gating | only RATIFIED docs are authoritative; DRAFT clearly flagged |
| Append-only audit | every change emits cascade-d13 TODO + DecisionProvenance row; replayable |

#### 14.14.6 What this means for founder (operational, not theoretical)

Founder action = keep dumping ideas. Native absorbs without disturbing core:

- **Free-form voice:** dump in any shape (voice-to-text, prose, fragments). I capture verbatim.
- **No "is this the right idea" pre-filter:** let me reverse-engineer. Ideas that don't fit get flagged as Qs.
- **Periodic consolidation:** when capability rounds accumulate >5 blocks of new material, I propose consolidation (e.g., "ready to author §10 Philosophy from accumulated P1-P13?").
- **Founder review checkpoints:** at each consolidation, you ratify or redirect.
- **Material changes always get codex review before ratify.**
- **Core stays intact:** §1-§9 + §10 (once authored) change RARELY; §11/§12/§13/§14 change CASE-BY-CASE via ADR; §12.X grows freely.

#### 14.14.7 v1 → v2 evolution path

v1 ships when: every block in capability map (§12.3 + §12.6 + §12.13 + §12.17) has a stub primitive declared in canon + a no-op implementation that emits `TODO` EngineEvent + passes through. v1 ship gate per Q26 default.

v1.x evolution: per-block fill (e.g., v1.1 fills B7 pre/post validation; v1.2 fills B11 PromptBuilder).

v2 trigger: STRUCTURAL change accumulates (e.g., B14 multi-human-org introduces new primitive class) OR signal lands (≥3 T4 clients green for 14d per D41 revert trigger).

v2 ship: same pipeline but with v1 lessons folded.

Repeat indefinitely. Native evolves WITH the operator (per P7).

---

**§14.14 = Process for Continuous Native Evolution complete.** Answers founder meta-Q: doc architecture (4 tiers) + idea-absorption flow + change discipline (3 classes) + v1-honesty (P3 + DRAFT status) + core-intact disciplines (7 mechanisms) + operational guidance + v1→v2 path.

---

### 14.15 Implementation Kickoff Framework (founder meta-question answered 2026-05-09)

**Founder ask (verbatim 2026-05-09):**
> "So we have to first solve that: how do we get implemented and get it implemented? I want to ensure this proper governance, security, and all the agentic frameworks which we have used are there. But these are kind of the outcomes which I need from a product point of view."

**Answer = phased plan + outcome-first ordering + repair-vs-new track.**

#### 14.15.1 Phased plan — 5 phases from voice → ship

```
+--- PHASE A : COMPLETE THE PRD DOCS -------------------------+
| Where   : NATIVE-ENGINE.md §10 / §11 / §13 / §15 / §16 / §17 |
|           / §18 / §19 (currently DRAFT or empty)             |
| Cadence : 1-3 sections / turn; multi-turn                    |
| Owner   : claude drafts STRAW; founder ratifies              |
| Gate    : every founder-owned layer (L1/L2/L3/L4/L11/L14)    |
|           must reach DRAFT v1 with founder review             |
| Status  : in-flight (Stage B — §14 PRD + §12 Mission landed) |
+--------------------------------------------------------------+
                          |
                          v
+--- PHASE B : §16 FEATURE SPECS PER BLOCK -------------------+
| Where   : §16 in NATIVE-ENGINE.md, one sub-section per       |
|           block (B1-B18 + 7a-7e + F1)                        |
| Cadence : 1-2 features / turn                                |
| Format  : per L8 standard — name + 1-line summary + scope-in |
|           / out + UX flow + acceptance + data model + edges  |
|           + telemetry                                        |
| Owner   : claude drafts; founder reviews                     |
| Gate    : top-5 outcome blocks (per Q39) authored before     |
|           Phase C starts                                     |
+--------------------------------------------------------------+
                          |
                          v
+--- PHASE C : PER-BLOCK IMPLEMENTATION -----------------------+
| Where   : sutra/marketplace/native/ (plugin runtime); for    |
|           extensions to existing primitives, sutra/marketplace|
|           /native/src/                                       |
| Cadence : per-block; can parallelize via subagent dispatch   |
| Format  : test-driven (TDD) per `superpowers:test-driven-    |
|           development`; codex consult before edit per D40 G2 |
| Owner   : claude codes; codex reviews                        |
| Gate    : block functional + tests pass + codex PASS         |
+--------------------------------------------------------------+
                          |
                          v
+--- PHASE D : CODEX REVIEW ON DIFF ---------------------------+
| Where   : per-PR diff via `core:codex-sutra` skill review    |
|           mode                                                |
| Cadence : per-PR; PROTO-019 directive gate                   |
| Format  : verdict file at .enforcement/codex-reviews/        |
|           <date>-<slug>.md w/ DIRECTIVE-ID + CODEX-VERDICT   |
| Owner   : claude dispatches; codex returns                   |
| Gate    : CODEX-VERDICT >= ADVISORY (PASS preferred)         |
+--------------------------------------------------------------+
                          |
                          v
+--- PHASE E : SHIP + ITERATE ---------------------------------+
| Where   : asawa-holding/ + sutra/ submodule push (per D52    |
|           autonomous push)                                   |
| Cadence : per-PR or per-block; minor versions for B-block    |
|           land; major bump on STRUCTURAL change              |
| Owner   : claude commits + pushes; founder dogfoods          |
| Gate    : observability per CLAUDE.md (.enforcement/sutra-   |
|           deploys.log) + post-ship operationalization        |
|           (D30a; OPERATIONALIZE phase)                       |
+--------------------------------------------------------------+
```

#### 14.15.2 Outcome-first ordering (per P14)

Per P14 (outcomes drive design), order blocks by founder-outcome value, not by infra dependency. v1.x cycle ships TOP-5 outcome blocks (Q39 default; founder confirms).

| Rank | Block | Outcome delivered | Why this rank |
|---|---|---|---|
| 1 | B9 Closed-Loop Artifact | "anything I produce is logged + reused" | foundation — every other block depends on artifact catalog being right |
| 2 | B7 Pre/Post Validation | "every LLM call is checked; nothing left to chance" | trust — testing-framework analog; gates Phase D shipping |
| 3 | 7d Lifecycle Orchestrator | "I pick work + it runs analysis → decide → build → operationalize → auto-run" | the "magic" outcome from r1 — the autonomous lifecycle |
| 4 | B5 Explanation Surface | "I control how Native explains things to me" | operator UX — gates founder dogfood quality |
| 5 | B18 Person Formation | "Native learns me + adapts; I grow + it grows" | personalization — long-term value driver |

**Other 13 blocks (B1-B4 · B6 · B8 · 7a-7c · 7e · B10-B13 · B14-B17) ship as STUBS in v1** (per P3 all-blocks-as-stubs); fill incrementally based on founder feedback signal.

#### 14.15.3 Repair-existing vs build-new track

Founder context: "v1 of native is still not yet working appropriately as we thought."

Implementation interleaves repair + new:

| Track | Items | Approach |
|---|---|---|
| **REPAIR** | Top-3 most-broken existing v1 blocks (TBD via Native v1 audit; pending Q41 below) | per-block ADR documenting what's broken + fix; codex consult before edit |
| **BUILD** | Top-5 NEW outcome blocks per §14.15.2 | per-block §16 Feature Spec → impl → codex review → ship |
| Cycle | 6 items (3 repair + 3 build) per v1.x mini-cycle; founder confirms order; rest queued v2+ | weekly cadence; codex review at each ship |

(New Q41 added §12.23 to identify the TOP-3 existing-v1 broken blocks.)

#### 14.15.4 Governance / security / agentic-framework infra (already present)

Per founder: "I want to ensure this proper governance, security, and all the agentic frameworks which we have used are there. But these are kind of the outcomes which I need from a product point of view."

These INFRA disciplines are already canonical (no new work):

| Layer | Mechanism | Reference |
|---|---|---|
| Governance | per-turn blocks (Input Routing · Depth · BLUEPRINT · Build-Layer · Output Trace) | CLAUDE.md + D27/D28/D40 |
| Security | Tenant isolation · DecisionProvenance · STRIDE threat model · HARD-STOP HS-1..HS-8 | NATIVE-ENGINE.md §6 + §7 + ADR-006/007/008 |
| Agentic frameworks | host-LLM dispatch (claude/codex) · Workflow JSON · Approval gates · Skill registry | NATIVE-ENGINE.md §1-§5 + ADR-005/009/010 |
| Audit | EngineEvent + DecisionProvenance JSONL · 3-channel durability · `.enforcement/codex-reviews/` | NATIVE-ENGINE.md §3.2 + ADR-013 |
| Build-Layer | D38 plugin-first + LEGACY-HARD marker + cascade-d13 | CLAUDE.md + PROTO-021/025 |
| Codex review | core:codex-sutra skill + PROTO-019 directive gate + 15-min hard cap | CLAUDE.md + D40 G2 |

Per P14: these surfaces are infra — they ENABLE the outcome-bearing blocks. They are NOT the customer-facing product; outcomes are.

#### 14.15.5 Recommendation — what happens next

After this turn, the natural sequence:

1. **Continue Phase A** — author §11 L2 Vision + N* metric → §13 L4 Strategy Map → §10 L1 Philosophy (15-section PRD plus §10/§11/§13/§14 strategic layers)
2. **Then Phase B for top-5 outcome blocks** — §16 Feature Specs for B9 / B7 / 7d / B5 / B18 (per §14.15.2 ordering)
3. **Native v1 audit** to identify TOP-3 most-broken existing blocks (Q41) — happens in parallel with Phase A/B
4. **Phase C implementation** starts after first 5 outcome blocks have feature specs + repair targets identified
5. **Codex review + ship** per-PR

Founder confirms order or redirects.

---

**§14.15 = Implementation Kickoff Framework complete.** 5 phases (A complete docs → B feature specs → C impl → D codex → E ship) + outcome-first ordering (top-5 blocks per P14) + repair-vs-build interleave (3+3 per v1.x cycle) + infra inventory.

---

### 14.16 TODO Sweep — Aggregated Native Features (subagent A5 result, 2026-05-09)

**Founder ask (verbatim 2026-05-09):**
> "Also check all the to-do's of Asawa and Sutra and add all the relevant features which we have thought about into this PRD documentation."

**Subagent A5 verdict:** scanned `holding/TODO.md` (~32K tokens) + archive INDEX.md + `sutra/marketplace/native/README.md` + `SUTRA-CURRENT-VERSION.md` + native-formalization PLAN/SPEC. **26 Native-relevant items extracted.**

#### 14.16.1 Most items are canon duplicates (skip)

A5 finding: **No rework needed.** Phase 1.5 / v1.0 / v1.1 / v1.2 items in TODOs are already canonical in NATIVE-ENGINE.md §1-§9 + ADR-004..017 + archive INDEX.md. Per D54, charter + ADRs are source-of-truth; do NOT re-mint in PRD §14.

| Class | Examples | Already at | Action |
|---|---|---|---|
| 4 primitives (Domain · Charter · Workflow · Execution) | shipped v1.0 | NATIVE-ENGINE.md §2.1-§2.9 | reference, don't duplicate |
| 26 EngineEvent types | shipped v1.0 | §3.2 | reference |
| Approval utterances (approve / reject) | shipped v1.0 | §3.4 + ADR-009 | reference |
| Tenant isolation + cutover_contract | schema shipped v1.0; runtime deferred | §6.2 + ADR-006 + §8 OS-4 | reference |
| Replica + `SUTRA_NATIVE_HOME` | shipped v1.0 (`~/.sutra-native-asawa-replica/`) | §6.3 + ADR-016 | reference |
| 14 ADRs (ADR-004..017) | shipped 2026-05-07 | sutra/os/decisions/ | reference |
| Phase 1.5 D54 canon-only writes | shipped 2026-05-07 | FOUNDER-DIRECTIONS D54 + this charter | reference |
| Phase 1 NATIVE-ENGINE.md canonical charter | shipped 2026-05-07 | this file §1-§9 | reference |
| Archive INDEX.md (54 rows mapped) | shipped 2026-05-07 | holding/research/_archive/native-v1.x/INDEX.md | reference |
| Phase 0 6 writing-standard skills | shipped 2026-05-07 | holding/skills/ | reference |
| Sutra v2.30.0 D43 capability surface (8 disciplines) | shipped 2026-05-04 | CSM + SUTRA-CURRENT-VERSION.md | reference |

#### 14.16.2 Six GAPs to fold into PRD (real new content)

A5 flagged 6 items NOT yet in §14. These should be folded. Per D54, fold via reference (not duplication). Each gap → one PRD sub-section with cross-ref to canonical source.

| # | Gap | Source | Fold target |
|---|---|---|---|
| G1 | **Asawa native replica operating manual** (21 Domains + 8 Charters + 6 Workflows + 6 Triggers inventory; rebuild via `holding/scripts/build-asawa-native-replica.sh`) | archive row 43 + ADR-016 + memory `project_asawa_native_replica` | §14.16.4 below — operationalization sub-section |
| G2 | **Time-to-value metric** (I-11 ≤30min; Asawa dogfood evidence median-of-3 measured 2026-04-30) | archive rows 7+41 + sutra/marketplace/native/README.md | §14.9 success metrics — append measured-evidence note + I-11 anchor |
| G3 | **Phase 1.5 canon-only governance** (D54; forbidden paths; native-canon-check hook PreToolUse) | TODO.md lines 7+13 + D54 + Phase 1.5 Task 17 | §14.16.5 below — governance sub-section (already in §14.14.5 — confirmed; cross-ref) |
| G4 | **Wave 1-6 v1.x roadmap** (host-LLM wire · approval gate · cadence scheduler · failure-policy · PNC predicate · commitment-broken event) | archive row 24 RESUME-V1.X.md (FROZEN per D54) | §14.16.6 below — v1.x roadmap inventory |
| G5 | **Build-discipline milestones M4-M12** (strict M1-M6 deps; M5.5 rolling integration) | archive rows 4+23 + native-formalization PLAN.md | §14.16.7 below — build-discipline reference |
| G6 | **Test coverage drift** (1273 shipped vs `marketplace.json` advertises 1207; OS-19 manifest drift; contract + property-based test split) | archive rows 9+21 + §8 OS-19 | §14.16.8 below — quality gates note |

#### 14.16.3 A5 TOP-15 inventory (existing canonical features by infra-importance)

Different lens than §14.15.2 outcome-ordering. A5's list ranks WHAT EXISTS by infra criticality (what loads-bear). §14.15.2 ranks BY-OUTCOME for v1.x build sequence (per P14). Both are useful: §14.15.2 = build order; §14.16.3 = inventory of what's already canonical.

| # | Feature | Canonical home |
|---|---|---|
| 1 | Approval gate primitive + approval-granted/denied events | ADR-009 + §3.3 events 15-17 |
| 2 | DecisionProvenance schema + policy_id/version invariant | ADR-007 + §2.9 + I-17 |
| 3 | Tenant isolation (Domain.tenant_id + TenantIsolation engine) | ADR-006 + §2.1 + §6.2 + HS-3 |
| 4 | Workflow execution + terminal_check (T1-T6) | §4 I-5 + §3.1-§3.2 |
| 5 | Failure policy 5-set | ADR-011 + §6.5 |
| 6 | Host-LLM integration + registry/effector split | ADR-004 + ADR-005 + §5.1 |
| 7 | Cadence scheduling daemon (CadenceScheduler ±5min) | ADR-017 + §6.4 |
| 8 | SkillEngine resolve-only + reuse_tag/return_contract | §3.1 + OS-12 |
| 9 | Organic emergence (propose k≥4 / approve flow) | ADR-010 + §3.3 events 12-13 |
| 10 | PNC typed predicates (precondition/postcondition parser) | ADR-012 + §4 F-10 |
| 11 | on_failure machinery + step compensation | §6.5-§6.6 |
| 12 | H-Sutra event classification + routing | ADR-015 + §5.3 + §5.5 |
| 13 | Replica isolation (SUTRA_NATIVE_HOME) | ADR-016 + §6.3 |
| 14 | Threat model (STRIDE + HS-1..HS-8) | §7 + §6.9 |
| 15 | Open Seams (OS-1..OS-25 backlog) | §8 |

#### 14.16.4 [G1] Asawa replica operating manual

Asawa Inc. dogfoods Native via primitive replica at `$HOME/.sutra-native-asawa-replica/`. Inventory:

- 21 Domains
- 8 Charters
- 6 Workflows
- 6 Triggers

Rebuild script: `holding/scripts/build-asawa-native-replica.sh` (idempotent). Memory: `project_asawa_native_replica`. ADR: ADR-016 (replica isolation rationale).

This replica is the canonical T0 dogfood instance; it gates "v1.0 acceptance" before T2/T3/T4 cohort onboarding (per D41).

#### 14.16.5 [G3] D54 canon-only governance — confirmed cross-ref

Already covered at §14.14.5 (Core-intact discipline) via D54 + native-canon-check hook + verify-archive-completeness.sh + holding/skills/updating-native-canon.md decision tree. No new content needed.

#### 14.16.6 [G4] v1.x Wave roadmap (from FROZEN RESUME-V1.X archive)

Per D54, `holding/plans/native-v1.x/RESUME-V1.X.md` is FROZEN forward. The wave roadmap below is captured as inventory; future evolution lands as new sections in this charter (e.g., §18 Roadmap once authored) or new ADR-018+.

| Wave | Focus | Status (as of 2026-05-09) |
|---|---|---|
| **Wave 1** | host-LLM wire + Workflow execution path + replica setup | shipped v1.0 (2026-04-30) |
| **Wave 2** | Approval gate primitive + ledger persistence + utterance routing | shipped v1.0 |
| **Wave 3** | Cadence scheduler daemon + tick window + cron-style escape | shipped (ADR-017) |
| **Wave 4** | Failure-policy 5-set + step compensation + rollback | shipped v1.0 (ADR-011) |
| **Wave 5** | PNC typed predicate parser + precondition/postcondition gating | shipped v1.0 (ADR-012) |
| **Wave 6** | `commitment_broken` event semantics + continue-policy interaction | OPEN — see §8 OS-5 |

Future waves (v1.x+ implied by §8 Open Seams):
| Wave | OS-* | Status |
|---|---|---|
| Wave 7 | OS-1 daemon-routed autonomous + OS-2 per-workflow sandbox config | DEFERRED v1.3 |
| Wave 8 | OS-6 Temporal Workflow Executor + OS-8 Router.routeAsync + LLMFallback | DEFERRED |
| Wave 9 | OS-12 Skill Engine compose / create / bias / auto_retire | DEFERRED |
| Wave 10 | OS-3 cross-process replay + OS-22 A2A cross-process workflow comm | DEFERRED v2 |

#### 14.16.7 [G5] Build-discipline milestones (M-series)

Reference for v1.x build cadence. From native-formalization PLAN.md (Phase 0/1/1.5 sequence) + RESUME-V1.X archive (M-series):

- M1-M6 strict serial deps (canon foundation)
- M5.5 rolling integration (continuous validation)
- M7+ parallel where independent (block-level work)

Implementation discipline: per [Codex consult on everything] + D40 G2 (consult-before-edit at Depth ≥3) + per-block ADR for material changes.

#### 14.16.8 [G6] Quality gates note

Test coverage discipline:
- Contract tests + property-based tests (split per §6 Operations)
- Coverage gate ≥80% per build
- Manifest drift OS-19: `marketplace.json` + `plugin.json` advertise 1207 tests; source ships 1273 — needs reconciliation in next plugin release

Per P12 (deterministic surface around stochastic core): all non-LLM-non-action code is testable; gate enforced at Phase D codex review.

---

**§14.16 = TODO Sweep complete.** A5 verdict: 26 Native-relevant items inventoried; 11 categories of canon duplicates flagged for skip-don't-duplicate; 6 GAPs folded as cross-references (G1 replica · G2 t2v metric · G3 D54 governance · G4 Wave roadmap · G5 M-milestones · G6 quality gates); A5's TOP-15 infra-inventory captured complementing §14.15.2's outcome-ordering. Founder ask satisfied: "all relevant features we have thought about" now folded into PRD documentation per [No fabrication] + D54 cross-ref discipline.

---

## 10. Philosophy / POV (L1 per holding/PRODUCT-DOC-STANDARD.md)

**Status:** RATIFIED v1 (2026-05-09 — claude-drafted from founder voice rounds r1-r6 + Founding Doctrine + capability rounds §12.X; founder reviewed in-session; 7 new falsifications P5/P6/P7/P8/P10/P11/P13 + P13 tightening applied per codex consult round-3; §14.10 Q1/Q4/Q5/Q6/Q8 signoff complete 2026-05-09)
**Pipeline layer:** L1 (WHY belief system per Sinek Golden Circle)
**Writing method:** 1-page POV (Sinek) + falsification tests (Founding Doctrine convention)

### 10.1 POV — one paragraph

> Native exists because operating a portfolio of judgment-driven, multi-stranded work — running companies, managing teams, doing IC work, taking on initiatives by judgment — drowns the operator in decisions, learnings, and action items that fall on the floor. Vanilla LLMs execute well but they don't OPERATE: they don't structure context, they don't gate decisions, they don't learn the operator, they don't reuse their own outputs. Every operator's outputs should become typed, addressable, system-readable artifacts that feed the next iteration. The system should grow with the operator: learn taste, decision-style, voice; personalize how it thinks; carry picked work through the full lifecycle from analysis to auto-run. Governance, security, and agentic frameworks are infrastructure — the customer-facing surface is OUTCOMES.

### 10.2 14 Pillars (P1-P14, consolidated from §12.X capability rounds)

| # | Pillar | One-line |
|---|---|---|
| **P1** | Artifact-first | every Native output is typed, addressable, logged, reusable, system-readable |
| **P2** | Pre/post LLM validation | every LLM call has pre-declared expected output + post-call check (testing-framework analog) |
| **P3** | All blocks in v1 | completeness > depth-of-one-block; v1 ships every block as a stub minimum |
| **P4** | Product-POV before tech-POV | reverse-engineer voice → core needs; structure problem before solution |
| **P5** | MECE domains | mutually exclusive, collectively exhaustive per user |
| **P6** | Operator controls explanation | system controls production silently |
| **P7** | Native grows with operator | personalization is dynamic, not static |
| **P8** | Lifecycle is unit of value | analysis → decide → build → operationalize → auto-run |
| **P9** | Closed-loop artifact | input + output both stored; system consumes own outputs next iteration |
| **P10** | Typed config at every layer | Domain principles+guidelines+decisions; Charter instructions+guidelines+constraints |
| **P11** | Constrained problem construction | every LLM call gets explicit composed prompt; no implicit context |
| **P12** | Deterministic surface, stochastic core | only LLM reasoning + action are stochastic; everything else is tested code |
| **P13** | Multi-human-org-Native architecture | each human has own Native; Natives interact; org-shared artifacts |
| **P14** | Outcomes drive design | governance/security/frameworks are infra; outcomes are customer surface |

### 10.3 Falsification tests — when philosophy is wrong

| Pillar | Falsification (when broken) |
|---|---|
| P1 | If artifacts are NOT consumed by next iteration → P1 broken; system not closed-loop |
| P2 | If an LLM call is silent (no pre/post check) → P2 broken; trust erodes |
| P3 | If v1 ships missing any of B1-B18 + 7a-7e → P3 broken; not feature-complete |
| P4 | If a new Native primitive starts with "how does it work technically?" before "what does the operator see?" → P4 broken |
| P5 | If a domain overlaps another domain OR an operator concern fits no domain → P5 broken; not MECE |
| P6 | If operator cannot tune explanation verbosity OR system surfaces raw production noise to operator → P6 broken; control surfaces inverted |
| P7 | If Native behaves identically at day-1 vs day-180 (no observable adaptation in voice / decision-bias / cadence) → P7 broken; personalization static not dynamic |
| P8 | If picked work cannot traverse analysis → decide → build → operationalize → auto-run as ONE addressable lifecycle, OR phase transitions require manual re-pickup → P8 broken |
| P9 | If memory is treated as a separate primitive (not the artifact catalog) → P9 broken |
| P10 | If a Native primitive's config is implicit / inferred-from-code / scattered-across-files (not Domain or Charter typed-config schema) → P10 broken; not typed-at-every-layer |
| P11 | If any LLM call fires without explicit pre-composed prompt + declared expected output → P11 broken; implicit context creeped in |
| P12 | If non-LLM-non-action code lacks tests → P12 broken |
| P13 | v1 = single-human-Native (org mode = v2+ scope per codex consult round-3 2026-05-09). Post-v2: if two operators in same org share one Native instance OR Natives cannot address each other for org-shared artifacts → P13 broken |
| P14 | If Native ships without measurable operator-outcome → P14 broken |

(Per Founding Doctrine: every principle has a falsification test that fails on violation.)

### 10.4 Inheritance from Founding Doctrine (L0)

Native's 14 pillars MUST also pass the 6 Doctrine tests (Customer Focus First / Dynamic / Flexible / Scalable / Simple / Nuanced). When any Native pillar conflicts with Doctrine, **Doctrine wins**. Particular tensions:

| Native pillar | Doctrine tension | Resolution |
|---|---|---|
| P3 (all blocks v1) | Simple (10-min understandable) | v1 stubs are simple by design; logic added incrementally |
| P11 (constrained problem) | Customer Focus (operator clarity) | constraints are explicit + visible to operator (per P6) |
| P13 (multi-human-org) | Scalable (1 → 100 companies) | org-tenant primitive built into v1 schema (deferred logic) |

---

## 11. Vision + North Star Metric (L2 per holding/PRODUCT-DOC-STANDARD.md)

**Status:** RATIFIED v1 (2026-05-09 — claude-drafted from §14 PRD problem space + founder voice + agent A3 landscape; founder reviewed in-session; Vision paragraph + OHS/wk N* + leading inputs + 5-yr winning targets + v2 trigger all accepted; §14.10 Q1/Q4/Q5/Q6/Q8 signoff complete)
**Pipeline layer:** L2 (5-year future state + N* metric per Sinek/Collins + Sean Ellis Amplitude N* playbook)
**Writing method:** 1-paragraph future-state narrative + N* metric block + leading inputs

### 11.1 5-year vision (paragraph)

> By 2031, Native is the operating system every founder, manager-IC, and operator runs alongside their work. A user typing into their terminal — or speaking on a call, or messaging on Slack — has a Chief of Staff that captures every decision as a typed artifact, surfaces what needs operator judgment, runs picked work through the full lifecycle (analysis → decide → build → operationalize → auto-run), and grows with the operator's taste over time. Multiple humans in an organization each have their own Native; Natives interact at org level; humans + Natives + external tools form a coherent fabric where no decision, learning, or action item falls on the floor.

### 11.2 North Star Metric — Operator-Hours-Saved per Week (OHS/wk)

| Field | Value |
|---|---|
| **Name** | Operator-Hours-Saved per Week (OHS/wk) |
| **Definition** | Hours per week the operator NO LONGER thinks about, because Native handled them — audit-derived from auto-run lifecycle phases + operator weekly confirmation |
| **Why this metric** | Captures unit-of-value (time); measurable; leading indicator of retention; aligns with §14.3 JTBD outcomes #1+#2 (minimize time + variance); works at any scale |
| **v1 baseline** | 0 (pre-Native) |
| **v1 target (14d post-install)** | ≥3 OHS/wk per operator |
| **v3 target (mature product)** | ≥20 OHS/wk per operator |
| **Measurement** | (a) auto-run lifecycle Executions × completion-time × non-trivial gate; (b) operator weekly survey "did Native save you time this week?" |

### 11.3 Leading inputs to N*

- Workflows successfully auto-run after operationalization (count/wk per operator)
- Pattern proposals approved by operator (count/wk; precision ≥75%)
- Cross-company decisions replayable from audit log (% complete; ≥99%)
- Operator weekly active sessions (trend up over 12-week window)
- Time-to-first-Execution on fresh install (≤30 min, per I-11 in §4)

### 11.4 What "winning" looks like (5-year picture)

| Metric | 5-yr target |
|---|---|
| T4 fleet operators running Native daily | ≥1000 |
| Operator retention at 90d post-install | ≥80% |
| Portfolio companies (T2 owned) operating ENTIRELY through Native | ≥5 |
| Paying T3 / enterprise clients on outcome-based pricing | ≥1 |
| Native shipping as canonical Sutra plugin extension; T4 self-onboards | YES |

(Targets illustrative for direction; founder reviews + tunes at quarterly OKR cycle per §17.)

### 11.5 What v1 must validate before v2 expansion

Per D41 cohort pivot trigger:
- ≥3 T4 clients green for 14d post-onboard, OR
- ≥1 T2 portfolio company blocked on Native upgrade

When trigger fires, scope expands from "founder-portfolio v1 wedge" → "any manager-IC v2 TAM" per §14.2.

---

## 13. Strategy Map (L4 per holding/PRODUCT-DOC-STANDARD.md)

**Status:** RATIFIED v1 (2026-05-09 — claude-drafted from agent A3 external landscape + A4 framework picks + founder voice; founder reviewed in-session; Wardley map + Build/Buy/Host + competitive positioning + 5-yr defensible position + strategic bets + anti-bets all accepted; §14.10 Q1/Q4/Q5/Q6/Q8 signoff complete)
**Pipeline layer:** L4 (Wardley value-chain map + competitive positioning per Wardley + Geoffrey Moore)
**Writing method:** Wardley value chain (anchor=user need; Y=stack; X=evolution stage genesis→commodity) + build/buy/host boundary table + competitive comp + strategic bets

### 13.1 Wardley map (ASCII sketch — full visual artifact deferred to §14 Comms / website)

```
USER NEED: manager-IC operating multi-stranded judgment work
   |
   v
+--- GENESIS ----+--- CUSTOM -----+--- PRODUCT -----+--- COMMODITY ---+
                                                                       
| Person Form   |                                  | host-LLM         |
| (B18)         |                                  | (claude/codex)   |
| Outcome-driv. |                                  |                  |
| design (P14)  |                                  | terminal/CLI     |
| Native-Native |                                  |                  |
| A2A (B16)     |                                  | audit JSONL      |
                                                                       
| Lifecycle     | Workflow JSON                    | plugin           |
| orchestrator  | Approval primitive               | marketplace      |
| (7d)          | DecisionProvenance               |                  |
| Org-Tenant    | Tenant isolation                 | git/GitHub       |
| (B14)         | Closed-loop artifact (B9)        |                  |
                | PromptBuilder (B11)              | MCP/Connectors   |
                |                                  | (Slack/Email)    |
                | Charter / Domain / Workflow      |                  |
                | (existing primitives)            | mem0 / Composio  |
                                                                       
+----------------+----------------+-----------------+------------------+
```

### 13.2 Build / Buy / Host boundaries

| Capability | Decision | Rationale |
|---|---|---|
| Host-LLM (claude/codex) | **HOST** | Anthropic / OpenAI = infra; commodity by 2026; never build |
| Browser automation | **HOST** | CUA / Nova Act / ChatGPT Agent commoditized; consume not build |
| Memory layer | **HOST via Connector** | Mem0 / Composio commoditized; integrate via Native Connector |
| Audit log infra (JSONL+fsync) | **BUY (open-source)** | standard pattern; no need to build |
| Workflow execution runtime | **BUILD** | Native first-party value; control surface |
| Closed-loop artifact catalog (B9) | **BUILD** | core IP; not commoditized (memory ≠ artifact catalog) |
| Person formation primitive (B18) | **BUILD** | core IP; commoditizing memory ≠ commoditizing taste/voice/style |
| Multi-tenant isolation | **BUILD** | regulated industries need; Sutra-tier discipline; not commoditized |
| Plugin distribution | **HOST (Claude Code marketplace)** | Anthropic owns substrate |
| External communication | **HOST via Connectors** | every channel (Slack/Email/etc.) is a Connector |
| Indexing + semantic retrieval (F1) | **HOST (v2+)** | will commoditize via Vectorize/Pinecone/Anthropic; consume |

### 13.3 Competitive positioning

| Competitor | Their wedge | Native's differentiation |
|---|---|---|
| **Bond / Donna** (YC S25) | AI CoS for CEOs; web app | multi-business · terminal-native · governance-first · audit-replayable |
| **Paperclip** (OSS, 63k stars) | "Company OS"; self-hosted | per-operator Person Formation · Sutra discipline · live runtime (Paperclip is org-graph) |
| **Cognition Devin** | autonomous SWE; session replay | operator-as-CoS not engineer-as-agent; broader scope |
| **Sierra** | enterprise CX; outcome-pricing | Native borrows outcome-pricing v2; CX-only vs cross-cutting |
| **ChatGPT / Claude Code** | substrate | Native sits ON these; never competes |
| **Notion Custom Agents** | docs + agents | Native is terminal + governance; complementary |

### 13.4 Defensible position (5-year)

1. **Multi-tenant + multi-business is structural** — single-CEO competitors can't replicate
2. **Organic emergence (Workflow propose at k≥4)** — no surveyed competitor has this
3. **Governance discipline visible to operator** — anti-pattern by mainstream UX, founder-correct for high-trust
4. **Closed-loop artifact catalog as memory** — system's outputs become inputs; commoditized memory players don't have this loop
5. **Terminal-native CoS for high-leverage operators** — niche but defensible

### 13.5 Strategic bets (where we're betting custom stays custom for 3+ years)

- **B18 Person Formation** — persona model (taste + voice + decision-style + factor-weights) won't commoditize in 3 years
- **B11 Constrained problem construction** — explicit prompt composition is undervalued; will become standard but Native is early
- **7d Lifecycle orchestrator** — operationalize-then-auto-run as first-class lifecycle is a 5-yr bet
- **B16 Multi-human-org A2A protocol** — first-mover advantage if executed well; complex infra moat

### 13.6 Anti-bets (where we explicitly do NOT differentiate)

- Memory storage tech (commoditizing fast)
- Browser-action models (commodity layer)
- LLM substrate (Anthropic owns)
- IDE / editor (Cursor / VS Code own)
- Visual workflow designer (Linear / Notion / Lindy own UX patterns; Native is JSON-first)

---

## 12. Mission (L3 per holding/PRODUCT-DOC-STANDARD.md)

**Status:** RATIFIED v1 (2026-05-09 — claude-drafted from founder high-level capability list 2026-05-09 + §14 PRD problem statement; founder reviewed in-session; Q11/Q12/Q13/Q14 answered + Q12 P7-tightening applied per codex consult round-3; §14.10 Q1/Q4/Q5/Q6/Q8 signoff complete)
**Pipeline layer:** L3 (present-tense operating promise — what the product does for whom TODAY)

### 12.1 Founder voice — high-level capability list (verbatim, 2026-05-09)

> "The way high-level thing I'm thinking about is:
> - It can help me execute projects over time.
> - It can help me do one-off tasks.
> - It can surface relevant decisions it needs to take.
> - It can understand my taste and the way I take decisions, the way I communicate.
> - It can personalize communication for me and personalize the way I think about things and help me grow, and as I'm growing it can change things accordingly.
> - It can help me have interactions between me and the Native.
> - It can help me create and pick some work so it can run through the entire lifecycle of doing analysis, taking decisions, maybe building out and then operationalizing it, and once it is operationalized it can just automatically run so..."

(Last bullet truncated at "...so" in verbatim capture. Founder extended 2026-05-09 per §12.4 Q11: "...so founder graduates to next problem" — operator freed for next judgment work once operationalized lifecycle is auto-running.)

### 12.2 Mission statement (claude-drafted from §12.1 + §14 PRD; founder review)

> **Native is the operating system that runs alongside a manager-IC day-to-day — executing projects over time, picking up one-off tasks, surfacing decisions the operator needs to take, learning taste + decision-style + communication voice, personalizing how it thinks with the operator as the operator grows, and carrying picked work through its full lifecycle from analysis → decision → build → operationalize → auto-run.**

(One sentence per L3 spec. Compresses founder's 7 capabilities. Founder voice may want to tune verbs / cadence.)

### 12.3 Capability map — 7 founder capabilities → Native primitives + §16 feature gaps

Each row: founder capability (verbatim phrase) → existing Native primitive that partly covers it → feature gap to fill in §16 Feature Specs (next turns).

| # | Founder capability | Existing Native primitive | §16 feature gap (queued) |
|---|---|---|---|
| 1 | execute projects over time | Workflow + ExecutionResult + parent_exec_id chain | **Project** as first-class container above Workflow (groups workflows; persistent state across Executions; long-horizon) |
| 2 | do one-off tasks | Workflow.reuse_tag=false (single-use) | **Lightweight task surface**: one-shot Execution without registry persistence; ergonomic for not-worth-naming work |
| 3 | surface relevant decisions it needs to take | Approval primitive (P-A6) + DecisionProvenance | **Proactive surface**: Pulse-style daily/weekly cards (not just reactive approval-queue); founder sees what needs attention without asking |
| 4 | understand my taste / decisions / communication | H-Sutra log + ESTIMATION-LOG + EXECUTION trace | **Founder profile primitive**: aggregates patterns across logs into a queryable taste model (decision-style + voice + risk tolerance + cadence) |
| 5 | personalize communication / how it thinks / help me grow / change as I grow | Skill registry (compose/bias deferred per OS-12) + DecisionProvenance | **Personalization primitive**: per-operator voice + decision-style baseline that evolves over time; bias / compose / re-tune skills as taste shifts |
| 6 | interactions between me and the Native | UserPromptSubmit + classify + EngineEvent emit | **Conversational surface beyond turn-based**: longer dialogues, follow-ups, clarifications, multi-turn proposals (vs. current single-turn classify) |
| 7 | pick work + lifecycle: analysis → decisions → build → operationalize → auto-run | LiteExecutor (sync stub) + on_failure 5-set + Approval + cadence scheduler (ADR-017) | **Lifecycle orchestrator**: ANALYZE → DECIDE → BUILD → OPERATIONALIZE → AUTO-RUN as first-class lifecycle phases (above current Execution-states); operationalized work transitions to autonomous-on-trigger |

### 12.4 Open questions (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q11 | ✅ ANSWERED 2026-05-09 — bullet extended to "...so founder graduates to next problem" (operator freed for next judgment work once operationalized lifecycle is auto-running) | n/a |
| Q12 | ✅ ANSWERED 2026-05-09 — Logs remain DEFAULT substrate (H-Sutra + execution trace + estimation log = passive learning per D45 organic emergence). Explicit founder ratings are OPTIONAL high-signal corrections (sparse, non-required, additive) for ambiguous cases. Active ratings DO NOT replace passive substrate — they amplify it. Codex consult round-3 (2026-05-09) confirms P7-compatible only under this constraint. | n/a |
| Q13 | ✅ ANSWERED 2026-05-09 — Gated v1 (founder approval each cycle for auto-run). Fully autonomous deferred until trust signal lands (≥30d clean cadence per cycle). **Orthogonal to §14.5 G3** (codex consult round-3 distinguishing sentence): G3 = REGISTRATION approval (once, when pattern proposes → Workflow registered in registry); Q13 = per-cycle EXECUTION approval (each auto-run firing of a registered Workflow until trust signal lands). Two distinct gates, not redundant. | n/a |
| Q14 | ✅ ANSWERED 2026-05-09 — extend current turn-based emission with multi-turn context v1. New chat-shape primitive deferred v2 once turn-based shows friction. | n/a |

### 12.5 Founder voice round 2 — autonomous-mode unpack + artifact discipline (verbatim, 2026-05-09)

> "Within Autonomous, it can help create context and have structuring of context, which can help in effective retrieval. Then, for localized intelligence, it can use that particular context, and then it can give me a mode wherein I can run block by block in terms of what are the relevant contexts used. I can verify it, and then I can go to the next step. It can run through the entire process which we have in Sutra, from observe to orient and various steps we have in any kind of workflow. I can help dynamically change it, but that would require some system approvals or something like that.
>
> I want to ensure that anything which is produced is an artifact and it gets logged, and the same things are used next time by the system natively. They are written in such a format that they are system-readable."

**Two layers in this round:**
1. **Layer A — Autonomous mode unpacks capability #7** (lifecycle: analysis → decisions → build → operationalize → auto-run): adds 5 sub-capabilities (7a-7e) about context, retrieval, step-mode, Sutra-lifecycle integration, dynamic mutation.
2. **Layer B — Artifact-first discipline** is a new architectural principle (capability 8) that crosses every capability — every Native output is a typed, logged, reusable, system-readable Artifact. This is L1 Philosophy material and seeds §10 (forthcoming).

### 12.6 Capability map extension — rows 7a-7e + 8

| # | Founder capability | Existing Native primitive | §16 feature gap (queued) |
|---|---|---|---|
| 7a | create + structure context → effective retrieval | Context Engine (per memory `project_context_sphere_research`; partial via H-Sutra log + execution trace + ESTIMATION-LOG) | **Context structuring primitive**: graph + 3D scoring (depth/weight/recency) + budget-constrained retrieval; queryable interface |
| 7b | localized intelligence using particular context | Workflow.scope_in / scope_out (partial) + Tenant.tenant_id isolation | **Per-task context scope primitive**: explicit context-window declaration; localized model attention; Tenant + Project + Workflow scoping |
| 7c | block-by-block mode; founder verifies context-used; then next step | Approval primitive (P-A6) + step-level pause + EngineEvent.step_paused | **Step-through mode**: per-step "context-used" surface; founder approves block before next; pause/resume cadence; tunable verbosity |
| 7d | run through Sutra's process (observe → orient → various steps) | Sutra TASK-LIFECYCLE 8-phase per D30a (OBJECTIVE → OBSERVE → SHAPE → PLAN → EXECUTE → MEASURE → OPERATIONALIZE → LEARN) | **Lifecycle orchestrator**: Sutra's 8 phases become Native's first-class Execution-state phases (above current `running/success/failed/awaiting_approval/paused/declared_gap`) |
| 7e | dynamically change workflow w/ system approvals | Workflow.modifies_sutra + reflexive_check Constraint (HS-1) + Approval primitive (ADR-009) | **Mid-execution mutation**: founder edits Workflow during run; system gates by change-class (trivial vs material); reflexive_check + audit log |
| 8 | every produced thing = artifact, logged, reused next time, system-readable | Asset + DataRef primitives (§2) + EngineEvent.artifact_registered (event #9) + ArtifactCatalog (built but unwired per OS-9) | **Artifact-first discipline (architectural principle)**: every Workflow output → typed Artifact w/ system-readable schema → catalog row → indexed for reuse → next Execution resolves by reference. Cross-cuts every capability above; seeds §10 Philosophy. |

### 12.7 Open questions (founder review, round 2)

| # | Question | Default if unanswered |
|---|---|---|
| Q15 | Block-by-block mode (7c) — opt-in (founder enables when wanting verification) OR default-on (always step-through unless founder says "go")? | opt-in v1 (default = continuous; step-through when founder enables); founder-tunable verbosity |
| Q16 | Capability 7d — Sutra's 8-phase lifecycle (OBJECTIVE → ... → LEARN) becomes Native's first-class Execution phases? Or does Native have a simpler lifecycle of its own? | Sutra's 8-phase becomes Native canon; lifecycle phases land as new ExecutionResult.lifecycle_phase enum |
| Q17 | Capability 7e — "system approvals" for workflow mutation: what's the boundary between "trivial change auto-approved" vs "material change founder-approved"? | trivial = typo / threshold-tune / cosmetic; material = logic / scope / new step / new dep — founder gate. Per-class config in v2. |
| Q18 | Capability 8 artifact-first — does this REPLACE current Asset / DataRef / Artifact primitives, or EXTEND them with stricter "system-readable" requirements? "System-readable" = typed JSON only? Or also structured markdown? | extend existing primitives; "system-readable" = typed JSON for state + structured markdown for docs (with frontmatter); reject prose-only artifacts |
| Q19 | Capability 7a "create context" — does Native author NEW context (synthesizes from logs) or only RETRIEVE existing context (already-logged)? | retrieve v1 (passive); synthesize v2 (active — composes new context bundles from existing artifacts) |
| Q20 | Artifact "reused next time by the system natively" — implies Artifact addressability. Should every Artifact get a deterministic id (content hash like Workflow W-hash / Charter C-hash)? | yes — Artifact.id = content-addressed hash A-<hash>; canonical retrieval key |

### 12.8 Founder voice round 3 — system-design dump (verbatim, 2026-05-09)

Founder framing intent (verbatim):
> "We are creating a system design. We are creating a design of the architecture, not from a tech point of view but from a product point of view, like how the interface and the various features will be there. You want to ensure that we have the entire list of it so you can do reverse engineering on what I was all saying, so that we can figure out exactly the core need and we can structure this problem so that the solutions, because sometimes I'm just giving you the solutions which can work."

Capability dump (verbatim):

> "I want to control how Native explains things to me. Artifacts will be produced in the background, but I want to control how it explains things to me, and I can do research on the fly by using Native.
>
> If I see something as a user, I want to ensure that Native understands the user intent and understands what the user wants to do. First, we can do an entire decomposition. If some clarity is needed, then probably Native will get that clarity and then go about doing something, so that layer also has to be there. Understanding of what the user has said, and sometimes we don't need clarity, so that has to be contextualized as per the Native ecosystem.
>
> That is how we want to build this out. I want to build out a version 1, but having all the blocks. The blocks can just be a true gate and nothing there much. We can add the logic later on, but I want to ensure that all blocks are there.
>
> Then I want to really work on anything I give instructions that has to be like what we have in the testing framework, which is intents, which are specifics and some specific sense, and there are some intents. I want that human and native interactions to be captured very effectively, that intents are captured and then specifics are captured and then those are measured. Those are checked once the output is there.
>
> I want everything, every node, when it is processed by the LLM. When an element is called before the LLM is called, we exactly know what is the output desired, and when the LLM is called, we check the output. That has to have an at that day every LLM node, and then, when the output is created, we probably save it in some artifact, right, so that there has to be ensured that we properly have the artifacts. When we are going about some particular task, we have a basic framework of how that task should be created, which is the task framework which we have, and then we figure out factors and everything around them in the reasoning part of it, like which are the various factors we need to consider and everything.
>
> As things grow, we need to have different contexts of different things. Those are all domains, probably, so they are different and they are MISI kind of domains, which have different parts of the MySystem set up for a particular user. Within, there are charters, which we already have, which are basically kind of functioning things over time, which kind of do things over time. Charters are made of various workflows and everything. We can not just run through them. There have to be right boundaries in terms of which context is for what charters. We pick up the relevant things as well."

(Voice-to-text drift: "MISI kind of domains" interpreted as **MECE** — mutually exclusive, collectively exhaustive. Verification ask in Q21.)

### 12.9 Reverse-engineered architecture — 8 product blocks (v1 ships ALL as stubs minimum)

Per founder direction "v1 has all blocks even as stubs / true-gate / no logic", v1 must ENUMERATE every block; logic fills incrementally. Each row maps founder voice → product block → existing primitive → v1 stub status.

| # | Block | Founder voice source (round) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| B1 | **Intent Layer** — capture user intent (high-level "what user wants") + specifics (detailed sub-tasks); pre-LLM declare expected output; post-LLM check actual; measure | r3: "intents are captured then specifics are captured then those are measured" | None yet (testing-framework analog new) | NEW primitive: `Intent { high_level, specifics, expected_output_schema, post_check }`; stub validates schema, logic later |
| B2 | **Decomposition Layer** — full decomposition of user request; clarification sub-routine (when needed); context-resolve (when no clarity needed) via Native ecosystem | r3: "first we can do an entire decomposition. If some clarity is needed, Native will get that clarity ... sometimes we don't need clarity, so that has to be contextualized" | Workflow.preconditions (typed PNC predicates ADR-012) — partial | NEW: Decomposition Engine — splits intent into sub-intents; clarification-needed predicate; default = no clarity ⇒ ecosystem-contextualize |
| B3 | **Domain Hierarchy (MECE)** — domains are different contexts; MECE per user; "different parts of MySystem set up for a particular user" | r3: "different contexts of different things ... MISI [MECE] kind of domains ... different parts of MySystem set up for a particular user" | Domain primitive (§2.1) — present | EXTEND existing Domain — add MECE-validation invariant: every Workflow lives in exactly one Domain; no overlap; together cover the user's full surface |
| B4 | **Charter ↔ Context Boundary** — charters function over time; made of workflows; right boundaries on which context is for which charter | r3: "Charters are made of various workflows ... right boundaries in terms of which context is for what charters. We pick up the relevant things as well" | Charter primitive (§2.2) + scope_in/scope_out — present | EXTEND existing Charter — add explicit `context_scope: {included_artifacts[], excluded_artifacts[]}` so charter-level retrieval is bounded |
| B5 | **Explanation Surface (founder-controlled)** — artifacts produced silently; explanation = founder's control surface | r3: "I want to control how Native explains things to me. Artifacts will be produced in the background, but I want to control how it explains things to me" | Renderer registry (§3 + ADR-015 partial) | NEW config primitive: `ExplainProfile { verbosity, what_to_surface, what_to_hide, channel }` — per-founder, per-domain |
| B6 | **Research-on-the-fly** — founder asks Native to research X; Native uses ecosystem (web / Context7 / connectors) | r3: "I can do research on the fly by using Native" | Connectors (Slack live; web/Context7 via MCP) | NEW Workflow class: `ResearchWorkflow` — orchestrates Context7/WebSearch/connectors → produces Research Artifact |
| B7 | **Pre/Post LLM-Node Validation (testing-framework analog)** — every LLM call: pre-declare expected; post-call check actual; save output as artifact | r3: "every LLM node ... before the LLM is called we exactly know what is the output desired, when the LLM is called we check the output ... when output is created we save it in some artifact" | step.outputs validation (§2.4) — partial; ajv-compiled schema | EXTEND existing step contract — add MANDATORY `expected_output_schema` (pre) + `output_check_predicate` (post) per LLM-bearing step (`action='invoke_host_llm'`) |
| B8 | **Task Framework + Factors-Reasoning** — basic task creation framework + reasoning step that enumerates factors to consider | r3: "we have a basic framework of how that task should be created, which is the task framework which we have, and then we figure out factors and everything around them in the reasoning part of it" | Task lifecycle (D30a 8-phase) — exists at Sutra layer | EXTEND TaskLifecycle — add `factors[]` array as required reasoning artifact between SHAPE and PLAN phases; each factor weighted (per Sutra core IP weight-distribution) |

**Observed pattern:** Every block either (a) extends an existing Native primitive with new fields/invariants OR (b) introduces a NEW primitive. v1 ships skeletal definitions for all 8; logic fills per-block incrementally.

### 12.10 Philosophy seeds (Pillar 1-6 for §10 L1 forthcoming)

Reverse-engineered from founder voice rounds 1-3. These become Philosophy beliefs in §10 (next-next turn after §11/§13).

| # | Belief pillar | Source quote (verbatim) |
|---|---|---|
| **P1** | **Artifact-first**: every Native output is a typed, addressable, logged, reusable, system-readable Artifact. Prose-only outputs are anti-pattern. The system's own outputs become its inputs over time. | r2: "anything which is produced is an artifact and it gets logged ... used next time by the system natively ... written in such a format that they are system-readable" |
| **P2** | **Pre/post intent-specifics validation per LLM node** (testing-framework analog): every LLM call has pre-declared expected output + post-call check. No silent LLM calls. | r3: "every node when it is processed by the LLM ... we exactly know what is the output desired, when the LLM is called we check the output" |
| **P3** | **All blocks in v1 even as stubs**: completeness of structure beats depth of any one block. v1 ships every block as a "true gate" with stub logic; depth fills incrementally. | r3: "I want to build out a version 1, but having all the blocks. The blocks can just be a true gate and nothing there much. We can add the logic later on" |
| **P4** | **Product-POV before tech-POV**: architecture is designed from interface + features outward, not from tech stack inward. Reverse-engineer user voice into core needs; structure the problem (don't accept solutions as the problem). | r3: "We are creating a system design ... not from a tech point of view but from a product point of view ... reverse engineering on what I was all saying, so that we can figure out exactly the core need" |
| **P5** | **MECE domains**: a user's surface is partitioned into mutually exclusive, collectively exhaustive Domains; every Workflow lives in exactly one; together they cover the user's full surface. | r3: "different contexts of different things ... MISI [MECE] kind of domains ... different parts of MySystem set up for a particular user" |
| **P6** | **Operator controls explanation; system controls production**: artifacts are produced silently in the background; the human-facing explanation surface is operator-controlled (verbosity, what to show, what to hide). | r3: "Artifacts will be produced in the background, but I want to control how it explains things to me" |
| **P7** | **Native grows with the operator**: as the operator grows, the system's understanding of taste / decisions / communication grows; personalization is dynamic, not static. | r1: "personalize communication for me and personalize the way I think about things and help me grow, and as I'm growing it can change things accordingly" |
| **P8** | **Lifecycle is the unit of value**: picked work runs through analysis → decision → build → operationalize → auto-run as first-class lifecycle phases (per Sutra D30a 8-phase). Once operationalized, it auto-runs (gated v1, autonomous v2). | r1+r2: "run through the entire lifecycle ... once it is operationalized it can just automatically run" |

(P7 and P8 derived from rounds 1+2; appear here for completeness.)

### 12.11 Open questions round 3 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q21 | "MISI kind of domains" — confirm voice-to-text reading as **MECE** (mutually exclusive, collectively exhaustive)? | yes, MECE |
| Q22 | B7 pre/post validation — apply to EVERY LLM-bearing step (heavy gate; possibly slow) OR only to risky/high-blast-radius steps (fast path for cheap calls)? | every LLM-bearing step v1 (consistent gate); fast-path opt-out per step in v2 |
| Q23 | B5 ExplainProfile — does verbosity / what-to-surface get configured per-founder globally, OR per-domain (e.g. minimal for routine ops, verbose for strategic decisions)? | per-domain v1 (each Domain has its own ExplainProfile); per-founder default cascades |
| Q24 | B6 Research-on-the-fly — what's the trigger? Slash command (`/research X`) OR conversational ("research X for me") OR both? | both — slash command for explicit; conversational intent classified into ResearchWorkflow when matched |
| Q25 | B8 Task Framework "factors" array — is this the same `factors` you've referenced in prior memory (Karpathy / Right-Effort Discipline) OR a new construct? | extends Right-Effort Discipline factors to first-class typed array; same conceptual root |
| Q26 | "All blocks in v1 even as stubs" — what's the v1 ship gate? When is "all blocks present as stubs" considered DONE? | gate = every block listed in §12.9 has a typed primitive declared in canon + a no-op stub implementation that emits "TODO" EngineEvent and passes through; founder confirms ship-readiness |
| Q27 | P4 (Product-POV before Tech-POV) — does this become a HARD invariant (Native core dev rejects tech-first proposals) OR a SOFT principle (preferred but not blocking)? | HARD — every new Native primitive starts with "what does the operator see/do?" before "how does it work technically?" |
| Q28 | Charter ↔ Context Boundary (B4) — when a Workflow needs context from MULTIPLE Charters, what wins? Cross-Charter delegation (per ADR-006-style Tenant pattern) OR explicit per-Workflow override? | cross-Charter delegation as default v1 (audit-logged); per-Workflow override deferred v2 |

### 12.12 Founder voice round 4 — closed-loop artifacts + typed config + constrained problem construction (verbatim, 2026-05-09)

> "So whenever something is typed or something a user says or something LLM gives an output. It is stored in a certain particular artifacts which is a native recognizes. And then again that is picked up by the LLM. Then for each domain and everything that might be some guidelines, principles or some decisions and for each charter also there would be certain instructions guideline constraints so I want to ensure that whenever LLM whenever that execution happens via the LLM block everything everything is passed as prompts so that is constrained so we construct a problem we construct a problem and then give it to the reasoning part of it which is the LLM part of it we ensure there's end to end testing of everything so that nothing is left to chance only the reasoning part is left the LM or the decision-making part or the really execution via the actions part but everything is tested we ensure that when we get the relevant information form of context from all internal and external tools we have the right kind of mechanisms to get the context like indexing and everything this can be a future future features for everything"

### 12.13 Capability map round 4 — blocks B9-B12 + future-feature F1

| # | Block | Founder voice (r4) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| **B9** | **Closed-loop artifact** — every typed input + every user utterance + every LLM output stored as Native-recognized artifact; re-consumed by LLM next iteration | "whenever something is typed or something a user says or something LLM gives an output. It is stored in a certain particular artifacts ... again that is picked up by the LLM" | Asset + DataRef + EngineEvent (§2) — partial | EXTEND existing Asset/DataRef — every input/output emits typed Artifact; closed-loop config: Artifact catalog auto-feeds next Workflow's context |
| **B10** | **Domain typed config + Charter typed config** — Domain carries principles + guidelines + decisions; Charter carries instructions + guidelines + constraints | "for each domain ... guidelines, principles or some decisions and for each charter also there would be certain instructions guideline constraints" | Domain.principles (§2.1) + Charter.invariants/constraints (§2.2) — partial | EXTEND existing Domain — add `guidelines[]` + `decisions[]` typed arrays. EXTEND Charter — add `instructions[]` + `guidelines[]` + `constraints[]` typed arrays. All consumed at prompt-build time per B11. |
| **B11** | **Constrained problem construction** — every LLM execution receives full context + Domain principles/guidelines/decisions + Charter instructions/guidelines/constraints + relevant artifacts as prompt | "whenever LLM execution happens via the LLM block everything everything is passed as prompts so that is constrained ... we construct a problem and give it to the reasoning part" | step.prompt_template (§2.4) — partial; manual today | NEW PromptBuilder primitive — composes prompt from {Domain config + Charter config + Relevant Artifacts + Step inputs + Intent specifics}; deterministic concatenation; testable |
| **B12** | **End-to-end testing — only reasoning + action left to chance** | "we ensure there's end to end testing of everything so that nothing is left to chance only the reasoning part is left ... the decision-making part or the really execution via the actions part" | Tests scattered (Vitest + bats); coverage 80% gate | NEW TestSurface contract — every Native primitive + every PromptBuilder + every artifact-resolve gets a deterministic test; only `invoke_host_llm` (LLM call) and `host_action` (action execution) are marked stochastic |
| **F1** | **(future)** Indexing + context-retrieval mechanisms | "we have the right kind of mechanisms to get the context like indexing and everything this can be a future future features" | None yet (Context Engine sketched per memory) | DEFERRED to v2+ — flagged as future feature; v1 uses naive concat or canonical-rank retrieval |

### 12.14 Philosophy seeds round 4 — pillars P9-P12

| # | Belief pillar | Source quote |
|---|---|---|
| **P9** | **Closed-loop artifact**: input + output both stored as artifacts; the system consumes its own outputs next iteration. Memory ≠ separate; the artifact catalog IS memory. | r4: "whenever something is typed ... or LLM gives an output ... stored in artifacts ... that is picked up by the LLM [next time]" |
| **P10** | **Typed config at every primitive layer**: Domain holds principles+guidelines+decisions; Charter holds instructions+guidelines+constraints. No tacit-knowledge LLM calls — every constraint is declared. | r4: "for each domain ... guidelines, principles or some decisions and for each charter ... instructions guideline constraints" |
| **P11** | **Constrained problem construction**: every LLM call receives explicit prompt = (Domain config + Charter config + relevant Artifacts + Step inputs + Intent specifics). No implicit context. The PROBLEM is constructed before given to the reasoning step. | r4: "everything everything is passed as prompts so that is constrained ... we construct a problem and give it to the reasoning part" |
| **P12** | **Deterministic surface around stochastic core**: only LLM reasoning + action execution are stochastic; everything else (prompt construction, artifact retrieval, gate evaluation, output validation, state transitions) is tested deterministic code. | r4: "everything is tested ... only the reasoning part is left to chance ... the decision-making part or the really execution via the actions part" |

### 12.15 Open questions round 4 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q29 | B11 PromptBuilder — full inline assembly per call (every prompt rebuilt fresh) OR caching layer (memoized per Domain × Charter × Intent)? | full inline v1 (deterministic + replayable); cache layer v2 once perf signal lands |
| Q30 | B10 typed config — schema for `Domain.guidelines[]` / `Charter.constraints[]`: structured (YAML-ish typed predicates) OR free-form prose? Tension with PNC (typed predicates per ADR-012). | structured typed predicates v1 (PNC-aligned); allow free-form `notes` field for human commentary |
| Q31 | B12 end-to-end testing — what's the test gate before v1 ships? "Every Native primitive has ≥1 contract test" OR "coverage ≥80%" (current) OR "deterministic-replay test for top-N journey paths"? | (a) every primitive ≥1 contract test + (c) deterministic-replay top-10 journeys; (b) coverage ≥80% remains gate |
| Q32 | F1 indexing + retrieval — confirm DEFERRED to v2+? OR is some minimum retrieval mechanism (e.g. exact-match Artifact lookup by id) required in v1? | exact-match by Artifact.id required v1 (B9 closed-loop needs it); semantic indexing v2+; embedding retrieval v3+ |

### 12.16 Founder voice round 5 — multi-runtime + multi-human-org + Native-Native + external tools (verbatim, 2026-05-09)

> "In autonomous things, like you know, we have one runtime process, and there's another runtime process. When two runtime processes are there, how do they interact with each other? The one runtime process probably puts a lock on all the artifacts and everything on the states, and that second time, who is trying to do the same thing, they also know those things. Solving two simultaneously runtime processes is also something I want to solve for, and eventually the vision would be that in an organization, there is one human, there are multiple humans, and each human has their own Chief of Staff of Native. So how do a human and Native interact, and then how do they create their artifacts locally? How do they create artifacts at the org level? Similarly, there is another human, and they have their own Chief of Staff of Native. They also interact with the org documents, the agents interact within them, the founder/founder interacts within them, and that's how it really would work out. There would be external tools as well, where in the people would communicate, so we need to ensure that whenever we are trying to do something, we take the external tools as well."

### 12.17 Capability map round 5 — blocks B13-B17

| # | Block | Founder voice (r5) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| **B13** | **Multi-runtime concurrency** — two simultaneous runtime processes; lock artifacts + states; both processes aware of each other | "we have one runtime process, and there's another runtime process. When two runtime processes are there, how do they interact ... one runtime process probably puts a lock on all the artifacts and everything on the states, and that second time, who is trying to do the same thing, they also know those things" | None (single-process v1.x runtime per OS-22) | NEW: ConcurrencyCoordinator — file-based locks on Artifact.id + ExecutionResult.id; lock-table visible across processes; deadlock detection v2 |
| **B14** | **Multi-human-org architecture** — org has multiple humans; each human has own CoS-Native; humans + their Natives interact at org level | "in an organization, there is one human, there are multiple humans, and each human has their own Chief of Staff of Native ... another human ... has their own Chief of Staff of Native" | Tenant.parent_tenant_id (§2.8) sketches hierarchy | EXTEND Tenant — `Org-Tenant` has children = `Human-Tenants`; each Human-Tenant has its own Native instance + isolated audit log + ACL; Org-Tenant carries org-shared artifacts |
| **B15** | **Local vs Org artifacts** — humans create artifacts locally + at org level; both addressable; org-level artifacts visible to all humans in org | "how do they create their artifacts locally? How do they create artifacts at the org level?" | Asset / DataRef (§2) — partial; no scope distinction | EXTEND Artifact — `Artifact.scope: 'local-tenant' \| 'org-tenant'`; cross-tenant read requires PolicyDispatcher allow per ADR-006 pattern |
| **B16** | **Native-Native communication** — Natives interact with each other; agents interact within them; founder + founder interact via Natives | "agents interact within them, the founder/founder interacts within them" | None (no A2A protocol; OS-22 noted) | NEW: A2A protocol — Native instances exchange typed messages; envelope = `{src_native_id, dst_native_id, msg_type, payload, agent_identity_chain}`; ack required; stub v1 logs intent |
| **B17** | **External tools as communication channels** — people communicate via external tools (Slack, Email, etc.); Native ingests + emits via these channels | "external tools as well, where in the people would communicate ... we need to ensure that whenever we are trying to do something, we take the external tools as well" | Connectors (Slack live per memory `project_connectors_slack_live`); MCP servers; via plugin | EXTEND Connectors — every external tool = a typed Connector; inbound msgs → Artifact log; outbound msgs → DecisionProvenance + Artifact emit; tool-aware Workflow steps |

### 12.18 Philosophy seed round 5 — Pillar 13

| # | Belief pillar | Source quote |
|---|---|---|
| **P13** | **Multi-human-org-Native architecture (vision-level)**: each human in an org has their own Native instance; Natives interact with each other + with humans + with org-shared artifacts + with external tools (Slack, Email, etc.). v1 = single-human single-Native; v2+ = multi-human-multi-Native within Org-Tenant; v3+ = cross-org A2A. | r5: "in an organization, there is one human, there are multiple humans, and each human has their own Chief of Staff of Native ... agents interact within them ... external tools as well, where in the people would communicate" |

### 12.19 Open questions round 5 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q33 | B13 multi-runtime locking — file-based locks (git-index style) OR DB-style serializable transactions OR optimistic-concurrency-control with retry? | file-based locks v1 (matches existing JSONL fsync pattern + portable + observable); upgrade to OCC v2 if perf signal lands |
| Q34 | B14 Org-Tenant — introduce in v1 schema (deferred logic; future-proof) OR add only when first multi-human use case lands? | introduce in v1 schema (deferred logic stub); built into Tenant.parent_tenant_id day-1 prevents v2 schema migration |
| Q35 | B16 Native-Native A2A — minimum viable handshake protocol? Auth + envelope + ack? Or richer (capability negotiation)? | minimum viable v1 = `{src, dst, msg_type, payload, ack_id, agent_identity_chain}`; capability negotiation v3 |
| Q36 | B17 External Tools — confirm Connectors stay the abstraction (every external tool = a Connector class)? OR new primitive class for "external comm channels"? | Connectors stay the abstraction (single primitive class for all external integrations); aligns with current memory `project_connectors_slack_live` |

### 12.20 Founder voice round 6 — dynamic improvement + person formation + outcomes-drive-design (verbatim, 2026-05-09)

> "I want to ensure that you know things improve dynamically as things evolve. My decisions are recorded, my events are recorded, and those act as a context, and then they get executed, they get refreshed. My person also gets formed; the system learns from me how I do things and then appropriately changes the way you do problem-solving.
>
> So we have to first solve that: how do we get implemented and get it implemented? I want to ensure this proper governance, security, and all the agentic frameworks which we have used are there. But these are kind of the outcomes which I need from a product point of view."

### 12.21 Capability map round 6 — block B18

| # | Block | Founder voice (r6) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| **B18** | **Person Formation** — system models operator's persona over time from decisions + events + utterances + estimates; persona acts as context for problem-solving; problem-solving adapts as persona evolves | "My decisions are recorded, my events are recorded, and those act as a context ... My person also gets formed; the system learns from me how I do things and then appropriately changes the way you do problem-solving" | Partial — DecisionProvenance log + EngineEvent log + H-Sutra log + ESTIMATION-LOG exist but no persona aggregator | NEW: `Person` primitive — aggregates decisions + events + utterances + estimates into queryable persona model: {taste · decision-style · voice · risk-tolerance · cadence · factor-weights}; v1 = read-only view over existing logs; v2 = active learning + bias-injection into PromptBuilder (B11) |

### 12.22 Philosophy seed round 6 — Pillar 14

| # | Belief pillar | Source quote |
|---|---|---|
| **P14** | **Outcomes drive design (product POV first)**: governance · security · agentic frameworks are INFRA — necessary but not the customer surface. The customer (operator) sees OUTCOMES. Architecture must be ordered around outcomes, not infrastructure. Infra serves outcome; outcome doesn't serve infra. | r6: "I want to ensure this proper governance, security, and all the agentic frameworks which we have used are there. But these are kind of the outcomes which I need from a product point of view." |

(P14 is meta — it constrains how every other pillar gets prioritized. P14 says: when in tension, the outcome-side wins.)

### 12.23 Open questions round 6 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q37 | B18 Person primitive scope — what fields? Suggest: `{id, taste_signals[], decision_style{}, voice_profile{}, risk_tolerance, cadence_preferences{}, factor_weights{}}`. Confirm or amend. | confirmed; v1 ships read-only view + canonical schema; v2 active learning |
| Q38 | "How do we get implemented" — answer in §14.15 below. Founder picks: do we (a) finish §10-§19 docs first, (b) start §16 Feature Specs in parallel with doc-fill, (c) start implementation now on the most-broken existing v1 blocks? | (a) finish docs first per current Stage B sequence; (b) parallel feature specs once §13 lands |
| Q39 | Outcome-first ordering: which 3-5 founder outcomes are TOP for v1 ship? Pick from capability rounds 1-6: project execution · one-off tasks · surface decisions · taste-learning · personalization · interactions · full lifecycle · artifact-discipline · context structuring · localized intelligence · step-by-step mode · Sutra-process · dynamic mutation · explanation control · research-on-fly · intent-decomposition · pre/post validation · task framework · closed-loop artifact · typed config · constrained problem construction · e2e testing · multi-runtime · multi-human-org · Native-Native · external tools · person formation · dynamic improvement. | top-5 candidates: (1) closed-loop artifact (B9) [foundation for everything] · (2) intent-specifics validation (B7) [trust] · (3) lifecycle orchestrator (7d) [picked-work auto-runs] · (4) explanation control (B5) [operator UX] · (5) person formation (B18) [grows with operator]. Founder confirms or re-orders. |
| Q40 | Repair existing v1 vs build new blocks — which track first? Existing v1 has unfilled gaps (per "v1 of native still not yet working appropriately"); 18 NEW blocks identified across rounds 1-6. | repair-and-build interleaved: identify TOP-3 most-broken existing v1 blocks + TOP-3 NEW outcome-blocks (per Q39); 6 work items in v1.x cycle; rest queued v2+ |

### 12.24 Founder voice round 7 — learning loop + Native = vibe-coding AI assistant (verbatim, 2026-05-09)

> "I want to ensure that you know when any problem comes or any feedback with the founder is showing, so we have a learning loop. We just don't fix that problem. We also understand why that happens, systemically fix it everywhere, and also try to check it next time.
>
> I also want this product to operate on the third step: check it next time, so that is what our product is: to help people, to help people. This is an AI assistant to do vibe coding, actually, so that vibe coding is the powerfulness of this. Whenever you're going about certain things by doing vibe coding, it can help you prepare for it in the right places, operationalize things, and then it will help you. Vibe coding is just one fire call, and you just do it, which is the building, the operational part of it, the govern part of it, understanding systemically where it is evolving and finding the right things that are also important part of it."

### 12.25 Capability map round 7 — blocks B19-B20

| # | Block | Founder voice (r7) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| **B19** | **Learning Loop** — problem/feedback arrives → understand root cause → systemic fix everywhere → check next time | "when any problem comes or any feedback with the founder is showing ... We just don't fix that problem. We also understand why that happens, systemically fix it everywhere, and also try to check it next time" | D11 (Fix the Process, Not Just the Instance) at Asawa-doctrine layer; partial: post-mortem disciplines exist in CSM + cascade-d13 | NEW: LearningLoop primitive with 4 phases — `Problem → RootCause → SystemicFix → CheckNextTime`; each phase = typed Workflow; emits DecisionProvenance + Artifact at every phase |
| **B20** | **Vibe Coding Mode** — Native = AI assistant for vibe coding; surrounds the vibe-code "fire call" with preparation + building + governance + operationalization + evolutionary understanding + relevance-finding | "this is an AI assistant to do vibe coding ... Vibe coding is just one fire call, and you just do it, which is the building, the operational part of it, the govern part of it, understanding systemically where it is evolving and finding the right things that are also important part of it" | None as named primitive; capabilities scattered (PRD §14.7 ROUTE/RUN/GATE/EMERGE/AUDIT/TENANT) | NEW: VibeCodingMode = first-class operating mode that wraps vibe-code Workflow with: PREPARE (context structuring per 7a) → BUILD (vibe code "fire call") → GOVERN (B7 pre/post + Approval) → OPERATIONALIZE (D30a phase) → CHECK-NEXT-TIME (B19 learning loop) |

### 12.26 Philosophy seed round 7 — Pillar 15 + repositioning flag

| # | Belief pillar | Source quote |
|---|---|---|
| **P15** | **Systemic learning, not patches**: every problem and every founder-feedback signal triggers root-cause understanding + systemic fix across all instances + verification that it does not recur. The third step (check-next-time) is where Native uniquely operates. Patches alone are anti-pattern. | r7: "We just don't fix that problem. We also understand why that happens, systemically fix it everywhere, and also try to check it next time. I also want this product to operate on the third step: check it next time" |

**Repositioning signal (NOT yet folded into §14.2 — flagged for founder review):**

Founder said: *"This is an AI assistant to do vibe coding, actually, so that vibe coding is the powerfulness of this."*

This reframes Native's positioning. §14.2 currently says target persona = "any manager-IC operating multi-stranded judgment work" (v1 wedge = solo founder running portfolio). Round 7 introduces "AI assistant for vibe coding" as a primary positioning.

Two possible reads:
1. **Compatible:** vibe coding is one ACTIVITY a manager-IC does (founders code, eng managers ship features, etc.). Native = AI assistant for the manager-IC's full work, with vibe coding as one prominent activity that gets first-class wrap (PREPARE/BUILD/GOVERN/OPERATIONALIZE/CHECK-NEXT-TIME).
2. **Reposition:** persona narrows to "vibe coders" (a specific segment — founders + indie hackers + non-eng-trained code-shippers). Different competitive set (Cursor / Replit / Lovable / v0).

This is material — affects §14.2 Persona, §11 Vision, §13 Strategy Map (competitive set), §14.7 Solution Overview, §16 Features ordering. **Do NOT auto-rewrite per [No fabrication]; founder reconciles via Q41-Q42 below.**

### 12.27 Open questions round 7 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q41 | **REPOSITIONING:** "AI assistant for vibe coding" — is this (a) compatible with manager-IC framing (vibe coding = one prominent activity)? OR (b) a NARROWING of v1 wedge to vibe-coder segment specifically (founders + indie hackers + non-eng-trained shippers)? Cascades to §14.2 + §11 + §13. | (a) compatible — v1 wedge stays manager-IC + founder-portfolio; vibe coding wraps as B20 first-class mode within the broader product; v2+ TAM remains "any manager-IC" |
| Q42 | If (a) compatible: B20 VibeCodingMode is one of multiple operating modes. What other modes exist? (e.g. ResearchMode · DecisionMode · ProjectMode · ReviewMode) | yes, multiple modes; B20 first to ship in v1 because it's the most-trafficked operator activity; other modes added per founder signal |
| Q43 | B19 LearningLoop — does the loop fire on EVERY problem/feedback (heavy gate; possibly slow) OR only on classified ones (e.g. severity threshold + recurrence threshold)? | fires on classified: (i) any problem with `severity ≥ medium` OR (ii) any founder feedback explicitly tagged "feedback"; light-weight on trivial; codex consult gate for systemic-fix step |
| Q44 | P15 (systemic learning) — does Native author the systemic fix proactively (autonomous propose) OR only flag the systemic-fix CANDIDATES for founder approval? Tension with NG2 (NOT autonomous execution). | flag candidates v1 (founder-gated); autonomous fix v2+ once Person primitive (B18) reaches confidence threshold |

### 12.28 Founder voice round 8 — abilities (abstract layer above features) (verbatim, 2026-05-09)

> "It should give abilities. Let's suppose certain areas do not have too many features, so it should give abilities that there is one that does routine checks of certain things. Now I don't know whether it should be a standalone feature. The assistant should be able to assess and determine that this is required, so this, at an abstract level, is what it will do."

### 12.29 Round 8 follow-up — Q41 answered + abstraction-level + 2036 horizon (verbatim, 2026-05-09)

> "No, it is the first one. Wipe coding [vibe coding — voice-to-text drift, founder corrected to "vibe coding"] is one of the activities of manager IC, but yeah, largely it is an AI assistant. What I meant by that was saying that people can just use Wipe coding [vibe coding] as a way, but we have to anticipate and operate at that abstraction level so that it can become the truly effective assistant in 2036."

**Three locks from this clarification:**
1. **Q41 ✅ ANSWERED — option (a) COMPATIBLE.** Manager-IC persona stands (§14.2 unchanged). Vibe coding = ONE activity within manager-IC's work, not the whole product.
2. **Vibe coding is an entry pattern / "way" people use Native** — B20 VibeCodingMode stays as one mode among many; not the whole positioning.
3. **2036 horizon** — "truly effective assistant in 2036" extends §11 Vision's 5-yr (2031) target to a 10-yr horizon (2036). Native v3+ aspirational state.

### 12.30 Capability map round 8 — block B21 + abilities-over-features

| # | Block | Founder voice (r8) | Existing Native primitive | v1 ships as |
|---|---|---|---|---|
| **B21** | **Ability Assessment + Determination** — Native operates at ABSTRACT level: assesses situation → determines what ability is needed → assembles or invokes implementation (could be one feature, multiple, ad-hoc Workflow, or new orchestration). Operator may not have a fixed feature catalog; Native judges. | "It should give abilities ... so it should give abilities that there is one that does routine checks of certain things ... The assistant should be able to assess and determine that this is required, so this, at an abstract level, is what it will do" | SkillEngine.resolve (§3.1) — closest existing primitive but more concrete than abilities | NEW: AbilityAssessor primitive — abstract-capability registry; situation→ability mapper; ability→implementation router (Skill / Workflow / ad-hoc orchestration). v1 ships routine-checks ability + skeleton catalog |

**Abilities layer (NEW abstraction tier above Features §16):**

```
   ABSTRACTION LAYERS
   ====================
   ABILITIES   (NEW; abstract capability registry; situation-aware)
        |
        v
   FEATURES    (§16; atomic specs per block B1-B21)
        |
        v
   PRIMITIVES  (§2; Domain/Charter/Workflow/Step/etc.)
        |
        v
   RUNTIME     (§5; host-LLM dispatch + scheduler)
```

**Routine-checks example (founder-mentioned ability):**
- Ability name: `routine-checks`
- Definition: periodic verification that key state/health invariants hold
- Implementation route v1: cadence-scheduled Workflow that fires checks per Domain config; emits Artifacts on drift; surfaces decisions if invariant violation
- Founder Q: "should it be standalone feature?" — Native's AbilityAssessor judges: ability registered abstractly; specific implementation chosen based on Domain context (could be ad-hoc Workflow OR named feature)

### 12.31 Philosophy seeds round 8 — Pillars P16 + P17

| # | Belief pillar | Source quote |
|---|---|---|
| **P16** | **Abstract abilities over fixed features**: Native gives ABILITIES at the abstract level; specific feature implementations are how — but the WHAT is the ability. The system assesses situation and determines required ability dynamically; doesn't require operator to know the feature catalog. Areas with few features still get abilities. | r8: "It should give abilities ... certain areas do not have too many features, so it should give abilities ... at an abstract level, is what it will do" |
| **P17** | **Operate at the abstraction level for the long-arc product**: Native's design must anticipate use cases (vibe coding · research · decision-making · review · etc.) at the abstraction layer so it can become the "truly effective assistant" by 2036 — a 10-yr horizon beyond v1's 2026 ship. Short-term feature lists serve long-term abstraction. | r8 follow-up: "we have to anticipate and operate at that abstraction level so that it can become the truly effective assistant in 2036" |

### 12.32 Open questions round 8 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q41 | ✅ ANSWERED 2026-05-09 — vibe coding compatible (option a); manager-IC persona stands; B20 stays as one mode among many | n/a |
| Q45 | B21 Ability Assessment — what's the ability registry SCHEMA? Suggest: `Ability {id, name, definition, situation_predicate, implementation_options[], default_route}`. Confirm or amend. | confirmed; v1 ships skeleton schema + 3-5 seed abilities (routine-checks · research · decision-surfacing · operationalize · check-next-time) |
| Q46 | What other abilities should v1 ship beyond routine-checks? Candidates from prior rounds: research-on-fly (B6) · intent-decomposition (B2) · learning-loop (B19) · context-structuring (7a) · explanation-control (B5). | top-5 abilities for v1: (1) routine-checks · (2) research-on-fly · (3) decision-surfacing · (4) learning-loop (check-next-time) · (5) context-structuring |
| Q47 | §11 Vision year — keep 2031 (5-yr) OR extend to 2036 (10-yr per founder)? OR both (incremental 2031 + mature 2036)? | both: 2031 = "Native v3 mature" (incremental milestone); 2036 = "truly effective assistant" (long-arc target per P17); §11.4 winning-looks-like targets refer to 2031; "true effectiveness" extends to 2036 |

### 12.33 Founder voice round 9 — consequences anticipation + judgment simulation + dynamic adaptation (verbatim, 2026-05-09)

> "It should basically be able to anticipate long-term consequences, horizontal consequences, second-order, third-order, fourth-order effects. There should be abilities to figure that out in complex systems. The ability to figure out the consequences and use those as inputs to go about decisions. Ability to take judgment calls where there is no right answer, but it is able to simulate the judgment of the user as an ability to simulate the taste of the user and ability to be dynamic as per changing times. That would be helpful."

### 12.34 Abilities map round 9 — 3 new abilities for v1 seed catalog

Per round 8 abilities-over-features framing (P16); these land in B21 AbilityAssessor's seed registry. Total v1 seed abilities now = 8 (5 prior + 3 new).

| # | Ability | Founder voice (r9) | Definition | Implementation route v1 |
|---|---|---|---|---|
| **A6** | **consequences-anticipation** | "anticipate long-term consequences, horizontal consequences, second-order, third-order, fourth-order effects ... figure that out in complex systems ... use those as inputs to go about decisions" | Given a proposed decision/action, model multi-order effects (1st-direct, 2nd-cascade, 3rd-systemic, 4th-emergent) across horizontal dimensions (orgs/people/timelines/dependencies); surface as decision-input | Workflow class `consequence-tree`: input = proposed action + Domain context; output = typed multi-order effect tree as Artifact; consumed by B11 PromptBuilder before any consequential decision; v1 = LLM-synthesis with explicit Person-primitive bias |
| **A7** | **judgment-simulation** | "take judgment calls where there is no right answer ... simulate the judgment of the user as an ability to simulate the taste of the user" | When no objective right answer exists, simulate operator's judgment using Person primitive (taste + decision-style + factor-weights); produce reasoned candidate decision + confidence + alternatives | Workflow class `judgment-call`: input = situation w/ no objective answer; reads Person primitive (B18); LLM step constrained to operator's persona; output = candidate decision + reasoning chain + confidence interval + 2-3 alternatives; gated by Approval primitive (operator can override) |
| **A8** | **dynamic-adaptation** | "ability to be dynamic as per changing times" | Adapts the system's behavior + outputs as context shifts (operator's situation evolves, market changes, internal state changes); re-tunes thresholds + factor-weights + ability-routing | Continuous: every Execution feeds Person primitive (B18); periodic recalibration Workflow re-weights factors; Cadence-fired re-tune at quarterly + on-trigger (e.g., founder feedback); produces Re-Tuning Artifact w/ before/after diff |

### 12.35 Philosophy seed round 9 — Pillar P18

| # | Belief pillar | Source quote |
|---|---|---|
| **P18** | **Judgment under uncertainty is a first-class capability**: Native must operate when there is no objective right answer. It does this by (a) anticipating multi-order consequences as decision input, (b) simulating the operator's taste/judgment via the Person primitive, and (c) staying dynamic as context evolves. Failure mode: a CoS that only handles deterministic problems is not a CoS — it's a calculator. | r9: "judgment calls where there is no right answer ... simulate the judgment of the user ... ability to be dynamic as per changing times" |

### 12.36 Open questions round 9 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q48 | A6 consequences-anticipation depth — fixed at 4-orders (per founder voice) OR adaptive (depth scales with decision blast-radius)? | adaptive: 1-2 orders for routine; 3-4 for material; 4+ for STRUCTURAL change; per BLUEPRINT D48 verification class |
| Q49 | A7 judgment-simulation — when does Native simulate vs ask the operator? Threshold for "no right answer" classification? | simulate when (a) Person primitive confidence ≥ 0.7 AND (b) decision is reversible OR (c) operator unavailable + time-bound; otherwise surface to operator with simulated candidate as suggestion |
| Q50 | A8 dynamic-adaptation cadence — continuous (every Execution updates Person) OR scheduled (quarterly recalibration)? | continuous-write to Person (every Execution); scheduled re-tune (quarterly + on-trigger from founder feedback / persona drift signal); two-track |

### 12.37 Founder voice round 10 — daily-companion abilities (verbatim, 2026-05-09)

> "I should be able to read all the messages, communications, and everything. Help me process what's happening around. Help me structure my day. It should be able to help me have a great experience, and it should be able to flag all the problems and information which is coming. Help me consume in a manner I'd like to consume, and then, after that, it will help me prioritize which other things I need to focus on, the most important ones or something like that, some kind of thing. Those are some small features which are just coming by default, and definitely someone can customize it the way they want it."

### 12.38 Abilities map round 10 — A9-A12 (default + customizable)

Founder framing: these ship "by default" in v1; operator can customize per their preference. Total v1 seed abilities now = 12 (A1-A12).

| # | Ability | Founder voice (r10) | Existing primitive | Implementation route v1 |
|---|---|---|---|---|
| **A9** | **inbox-aggregation** | "read all the messages, communications, and everything" | B17 Connectors (Slack live; partial); MCP servers | Connector-fed inbox aggregator; pulls from Slack/Email/Calendar/Notion/etc.; lands as typed Artifacts in unified queue; per-Tenant scope |
| **A10** | **sense-making** | "process what's happening around" | A4 learning-loop + DecisionProvenance audit log (partial) | Sense-Making Workflow class: ingests inbox + audit log + EngineEvents; produces "what's happening" digest Artifact (configurable cadence: daily/weekly); LLM-synthesized; constrained by Person primitive (B18) |
| **A11** | **day-structuring** | "Help me structure my day" + "flag all problems and information" + "prioritize ... most important ones" | None (NEW); leverages A3 decision-surfacing | Daily-Plan Workflow: aggregates inbox (A9) + sense-digest (A10) + open Workflows + cadence-fired triggers + flagged problems; produces ranked DayPlan Artifact; ranking inputs = Person primitive factor-weights + impact + reversibility + dependency |
| **A12** | **consumption-personalization** | "consume in a manner I'd like to consume" | B5 Explanation Surface + B6 Conversational Surface (partial) | ConsumptionProfile primitive (sub-field of Person): {voice/tone/format/cadence/density/channel}; A10 sense-digest + A11 day-plan + every operator-facing Artifact rendered through this profile; defaults to founder baseline + per-operator override |

### 12.39 Customization principle (P19)

| # | Belief pillar | Source quote |
|---|---|---|
| **P19** | **Defaults that work + customization that respects operator**: every Native ability ships with sensible defaults derived from operator's Person primitive (B18); operator can customize verbosity, cadence, channels, ranking, format. The default is for someone who hasn't customized yet; customization extends, not replaces, the default. | r10: "those are some small features which are just coming by default, and definitely someone can customize it the way they want it" |

### 12.40 Open questions round 10 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q51 | A9 inbox-aggregation scope — which channels in v1? Slack (already live) + Email + Calendar minimum? OR broader (Notion / GitHub / Linear / Jira)? | v1 minimum: Slack + Email + Calendar; v1.x additions per founder request; v2+ Notion / GitHub / Linear via Connectors as demand surfaces |
| Q52 | A10 sense-making cadence — daily digest default? Or operator-tunable (real-time / hourly / daily / weekly)? | daily digest default at start-of-day (operator timezone); operator-tunable cadence in customization profile; real-time push reserved for HIGH-severity flags only |
| Q53 | A11 day-structuring — morning push (start-of-day surface) OR on-demand (operator opens "what should I do today")? | both: morning push as default at operator's start-of-day; on-demand via slash command / ability-call any time; configurable in customization profile |

### 12.41 Founder voice round 11 — capture-closed signal + ship-v1-fast (verbatim, 2026-05-09)

> "We had written a unit theory of various things: how things evolve over time, speed and energy, and how complex systems are built over time. I'm going to keep on adding to it in the future, but I think those are some future ideas. Right now, we are good to go with these. I want to create a version one very quickly, and then we can iterate on that."

### 12.42 Phase pivot — CAPTURE-CLOSED → SHIP-V1

**Capture phase status: CLOSED (this pass; reopens when founder dumps more).**

State at capture-close (2026-05-09):

| Dimension | Count |
|---|---|
| Founder voice rounds | 11 (r1-r11) |
| Capability blocks | 27 (B1-B21 + 7a-7e + F1) |
| Abilities (B21 registry seed) | 12 (A1-A12) |
| Philosophy pillars | 19 (P1-P19) |
| Open Qs | 53 (4 ✅: Q1/Q9/Q10/Q41) |
| Authored canon sections | §10 + §11 + §12 (with 11 rounds) + §13 + §14.0 + §14.1-§14.16 |

**Founder unit-theory flag (FUTURE FOLDING):**

Founder referenced existing "unit theory of various things: how things evolve over time, speed and energy, and how complex systems are built over time." This is parked as a future-folding candidate. Likely sources to consult when folding:

- Memory `project_sutra_core_ip` — weight-distribution engine; depth = weighting
- D26 (Gear = decomposition granularity; speed-vs-precision trade-off)
- D21 (speed of building is a factor)
- D9 (recursive estimation engine)
- D2 (thoroughness scales with the change)
- Memory `project_context_sphere_research` — graph + 3D scoring + budget constraint
- Memory `project_sutra_v2_design` — domain-first; Cynefin gate; 5 patterns

Per [No fabrication] — exact location of "unit theory" doc is unverified; founder confirms when ready to fold. Marked as deferred to v2+ per founder "future ideas."

### 12.43 Ship-v1 plan (proposal — founder confirms or redirects)

Per founder direction "create version 1 very quickly + iterate" + P3 (all blocks v1 even as stubs) + P14 (outcomes drive) + §14.15 Implementation Kickoff Framework, recommended v1 path:

**Track A — top-5 outcome blocks get FULL implementation:**

| Rank | Block | Outcome |
|---|---|---|
| 1 | B9 Closed-Loop Artifact | "anything I produce is logged + reused" |
| 2 | B7 Pre/Post LLM Validation | "every LLM call is checked" |
| 3 | 7d Lifecycle Orchestrator | "I pick work + it runs full lifecycle" |
| 4 | B5 Explanation Surface | "I control how Native explains things" |
| 5 | B18 Person Formation | "Native learns me + adapts" |

**Track B — remaining 22 blocks (B1-B4 · B6 · B8 · B10-B17 · B19-B21 · 7a-7c · 7e · F1) ship as STUBS** per P3 (typed primitive declared + no-op stub that emits TODO EngineEvent + passes through).

**Track C — 12 abilities ship as registry entries:** routine-checks · research-on-fly · decision-surfacing · learning-loop · context-structuring · consequences-anticipation · judgment-simulation · dynamic-adaptation · inbox-aggregation · sense-making · day-structuring · consumption-personalization. v1 = registry skeleton + simple route map; deep implementation per founder feedback signal.

**Phase sequence (compressed for "very quickly"):**

```
TURN N    : §16 Feature Specs for top-5 outcome blocks (B9/B7/7d/B5/B18)
            (parallel-dispatched via subagents; ~5-7 turns or 1 wave)
TURN N+1  : §15 PRFAQ (concise, Amazon-style; quick draft)
            §17 OKRs · §18 Roadmap (concise; quick draft)
            §19 Release Notes scaffold (Keep-a-Changelog stub)
TURN N+2  : Codex review of full §10-§19 PRD package (Stage C)
TURN N+3  : Implementation kickoff per §14.15 Phase C — top-5 blocks first
TURN N+4+ : per-block impl + codex review + ship cycle
```

Subsequent doc-rounds (founder's future "unit theory" additions + new voice) are absorbed via §12.X capture (continues append-only) + periodic consolidation per §14.14.

**Decision needed (founder):**

(a) `proceed` → execute v1-quickly plan as above (Track A + B + C; Phase sequence as listed)
(b) re-order top-5 (pick different priority)
(c) ship-faster: top-3 only + everything else stub; revisit at v1.5
(d) different direction (specify)

Default if unanswered = (a).

### 12.44 Founder voice round 12 — multi-device + tool detection + modes (verbatim, 2026-05-09)

> "It should be able to support me on my laptop, phone, or on the go, and it should be able to detect all the tools. Sometimes it has to work with the tools, so it should be able to work with the tools and get it done as well. Sometimes it can work autonomously, so there will be different modes on which it runs."

(Capture-closed marker §12.42 was advisory; founder continues — natural per P3 + capture protocol. State below absorbs round 12.)

### 12.45 Capability map round 12 — blocks B22-B24

| # | Block | Founder voice (r12) | Existing primitive | v1 ships as |
|---|---|---|---|---|
| **B22** | **Multi-Device Surface** — Native runs on laptop, phone, on-the-go; same Native instance, different I/O channels | "support me on my laptop, phone, or on the go" | None (current = terminal-only via Claude Code substrate) | NEW: DeviceSurface primitive — same Native instance, different I/O adapters: terminal (laptop, primary v1) · mobile-app shim (phone, v2) · voice (on-the-go, v3); **v1 ships TERMINAL-ONLY per Q9 founder answer (codex P1 fold 2026-05-09); mobile-thin-client deferred to v2** |
| **B23** | **Tool Discovery** — Native auto-detects available external tools in operator's environment | "it should be able to detect all the tools" | B17 Connectors (manually configured); MCP server registry partial | EXTEND B17 — Tool-Discovery probe: scans `~/.claude/plugins/installed_plugins.json` + `~/.claude-plugins/` + env-vars + filesystem markers; populates Connector registry automatically; operator confirms or excludes |
| **B24** | **Mode Framework** — first-class operating modes (vibe-coding · tool-collaborative · autonomous · etc.); operator picks or Native auto-routes | "Sometimes it has to work with the tools ... Sometimes it can work autonomously, so there will be different modes on which it runs" | B20 VibeCodingMode (single mode declared) | NEW: Mode primitive — typed enum + per-mode config: `{vibe-coding (B20) · tool-collaborative · autonomous · research · decision · review}`; operator selects or Native auto-routes from Intent Layer (B1) classification; per-mode `gate_policy` + `surface_policy` + `tool_set` |

**Mode taxonomy v1 (initial; extensible):**

| Mode | When to use | Behavior |
|---|---|---|
| **vibe-coding** | operator wants fire-call build (per r7) | wraps with PREPARE/BUILD/GOVERN/OPERATIONALIZE/CHECK-NEXT-TIME (B20) |
| **tool-collaborative** | task needs external tool (browser, IDE, API) | Native delegates to tool via Connector; supervises + audits |
| **autonomous** | operator unavailable + low-risk + Person-confidence high | **v1 STUB (per NG2 + Q13 + codex P1 fold 2026-05-09): mode declared in registry but defaults to founder-gated; no autonomous-without-gate path in v1.** v2+ ships true autonomous once trust signal lands (≥30d clean cadence + Person-confidence ≥0.85). Always emits DecisionProvenance + reviewable at next session. |
| **research** | operator asks "find out X" | A2 research-on-fly; ecosystem retrieval; produces Research Artifact |
| **decision** | operator faces choice with no objective answer | A7 judgment-simulation; produces decision candidate + alternatives |
| **review** | operator asks "audit / check / review X" | Pulls audit log + DecisionProvenance + Artifact catalog; produces Review Artifact |

### 12.46 Philosophy seed round 12 — Pillar P20

| # | Belief pillar | Source quote |
|---|---|---|
| **P20** | **Native fits the operator, not vice-versa**: Native runs on the operator's chosen device (laptop/phone/voice); detects + integrates with the operator's existing tools (no rewrite required); selects mode based on operator's task shape (vibe-coding / tool-collaborative / autonomous / etc.). Operators don't migrate to Native — Native meets them where they are. | r12: "support me on my laptop, phone, or on the go ... detect all the tools ... different modes on which it runs" |

### 12.47 Open questions round 12 (founder review)

| # | Question | Default if unanswered |
|---|---|---|
| Q54 | B22 Multi-Device — v1 ships terminal-only; phone/voice deferred. Is mobile-thin-client (read-only Artifacts via Slack/SMS) acceptable for v1, or push to v1.x? | mobile-thin-client v1 (read-only via existing Slack Connector + SMS via future Connector); full mobile app v2 |
| Q55 | B23 Tool Discovery — opt-in (operator runs `sutra discover-tools`) OR opt-out (auto-runs at install + per session start)? | opt-in v1 (operator-controlled per P6 explanation surface); auto-discovery v2 once trust signal lands |
| Q56 | B24 Mode Framework — operator-explicit selection OR Native auto-routes from Intent classifier? | both; default = Native auto-routes; operator override via `sutra mode <name>` slash command |
| Q57 | Mode taxonomy — 6 modes listed above sufficient for v1 OR add others? Candidates: `meeting-prep` · `daily-summary` · `creative` · `learning`. | 6 modes v1; additional modes added per founder signal (capture-rounds reopens) |
