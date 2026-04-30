/**
 * Engine barrel — M5 Group I.
 *
 * The Sutra Workflow Engine binds the V2 primitives (Domain / Charter /
 * Workflow / Execution) to Temporal SDK runtime. Codex P2.5: ONE Temporal
 * workflow orchestrates the Sutra step_graph; per-step I/O lives in
 * Activities — F-12 enforced at runtime by the Activity wrapper.
 *
 * Source-of-truth:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

export {
  registerWorkflow,
  type TemporalWorkflowDefinition,
  type ActivityDescriptor,
} from './temporal-adapter.js'

export {
  asActivity,
  F12_ERROR_TAG,
  type ActivityFn,
} from './activity-wrapper.js'

// M5 Group K — step_graph executor + failure_policy.
// M6 Group P (T-073) extends ExecutionResult + ExecuteOptions for child Skill
// invocations: ChildEdge surfaces parent→child invocation edges; skill_engine
// + recursion_depth on options carry the SkillEngine + depth through the
// nested invocation chain.
export {
  executeStepGraph,
  formatTerminalCheckFailureReason,
  type ActivityDispatcher,
  type ChildEdge,
  type DispatchContext,
  type ExecuteOptions,
  type ExecutionResult,
  type StepDispatchResult,
  type TerminalCheckProbe,
} from './step-graph-executor.js'

export {
  applyFailurePolicy,
  type ExecutionContext,
  type FailurePolicyOutcome,
} from './failure-policy.js'

// M6 Group O — SkillEngine: skill_ref registry + JSON Schema return_contract
// validation per V2 §A11. Caches ajv-compiled validators at register-time so
// Group P (child-invocation adapter) can validate outputs in O(1).
export {
  SkillEngine,
  type ValidateOutputsResult,
} from './skill-engine.js'

// M6 Group P — child invocation adapter. Wires step.skill_ref → resolved
// Skill execution with isolated child trace + canonical M5 failure-policy
// failure formats (skill_unresolved / skill_output_validation /
// skill_recursion_cap) + recursion cap. The executor calls into invokeSkill
// when a step has skill_ref + options.skill_engine is provided.
export {
  invokeSkill,
  SKILL_RECURSION_CAP,
  type SkillInvocationContext,
  type SkillInvocationFailure,
  type SkillInvocationResult,
  type SkillInvocationSuccess,
} from './skill-invocation.js'

// M7 Group U — Charter→Rego compiler. compileCharter(charter) → CompiledPolicy
// (policy_id, content-hash policy_version, rego_source). Throws
// BuiltinNotAllowedError when generated Rego references a forbidden builtin
// (codex P1.4 fold; sovereignty discipline foundation).
export {
  compileCharter,
  checkBuiltinAllowlist,
  ALLOWED_BUILTINS,
  BuiltinNotAllowedError,
  COMPILER_VERSION_CONST,
  type CompiledPolicy,
} from './charter-rego-compiler.js'

// M7 Group V — OPA bundle service: in-memory, version-keyed CompiledPolicy
// store. The runtime registers compiled policies via `register()`; the
// dispatcher fetches the active version via `get(policy_id)` (or pins a
// specific version via `get(policy_id, policy_version)` for audit / replay).
export { OPABundleService } from './opa-bundle-service.js'

// M7 Group V — OPA evaluator. `policyEvalActivity` is the asActivity-wrapped
// form that preserves the M5 I/O boundary (codex r8 P1.1). `OPAUnavailableError`
// surfaces when the binary is missing — the runtime treats this as deny.
//
// Codex master review 2026-04-30 P1.1 fold (BLOCKER): the raw `evaluate()`
// function is INTENTIONALLY OMITTED from this public barrel. Workflow code
// must reach the OPA shell-out ONLY through `policyEvalActivity` (or via
// `makePolicyDispatcher().dispatch_policy_eval(...)` which wraps the same).
// `evaluate()` is reachable only by importing directly from
// `./opa-evaluator.js` (test code, internal) and additionally enforces the
// F-12 guard at runtime (defense-in-depth — see opa-evaluator.ts).
export {
  policyEvalActivity,
  OPAUnavailableError,
  type PolicyAllow,
  type PolicyDecision,
  type PolicyDeny,
  type PolicyInput,
} from './opa-evaluator.js'

// M7 Group V — policy dispatcher. `makePolicyDispatcher()` returns the
// default dispatcher (Activity-wrapped); tests inject mock dispatchers
// through the same interface.
export {
  makePolicyDispatcher,
  type DispatchableCommand,
  type PolicyDispatcher,
  type PolicyEvalCommand,
} from './policy-dispatcher.js'

// M8 Group Z — OTel emitter + universal evidence-emit. The OTelEmitter is
// the gateway every consequential decision flows through; InMemoryOTelExporter
// is the test sink; NoopOTelExporter + OTLPHttpExporter ship for production
// (the OTLP HTTP exporter is a stub at v1.0 — M11 dogfood will wire the real
// implementation). `OTelEventKind` is the open-ended discriminator carrying
// both the strict D2 §2.1 set and Group Z/BB observability kinds.
export {
  InMemoryOTelExporter,
  NoopOTelExporter,
  OTelEmitter,
  OTLPHttpExporter,
  type OTelEventKind,
  type OTelEventRecord,
  type OTelExporter,
} from './otel-emitter.js'

// M8 Group AA — Governance overhead measurement + 15% threshold alert (PS-14
// closure). The runtime accumulates per-turn governance tokens across six
// disciplines (input_routing, depth_estimation, blueprint, build_layer,
// codex_review, hook_fire) and emits a non-blocking OTel
// 'GOVERNANCE_OVERHEAD_ALERT' event when overhead exceeds the configured
// threshold (default 0.15, env override SUTRA_GOVERNANCE_OVERHEAD_THRESHOLD).
// HARD-STOP at 25% (D5 §3 HS-2) is wired separately at M9 invariants.
export {
  GovernanceOverhead,
  TurnNotStartedError,
  type GovernanceCategory,
  type GovernanceOverheadOptions,
  type OverheadReport,
} from './governance-overhead.js'

// M8 Group BB — Host-LLM Activity (Claude --bare first-class + codex
// advisory). The architecture pivot's load-bearing public surface: every
// host-LLM dispatch flows through `hostLLMActivity` (asActivity-wrapped) so
// the M5 F-12 boundary is preserved. The raw `invokeHostLLM` is INTENTIONALLY
// NOT exported here (M7 P1.1 lesson — keep raw subprocess functions out of
// the production import surface; consumers reach the I/O via the wrapped form).
//
// HostUnavailableError surfaces when a host CLI is missing on PATH at
// dispatch time; the executor (T-120) translates this to a step failure with
// `host_llm_unavailable:<host>` for the failure-policy switch.
export {
  hostLLMActivity,
  HostUnavailableError,
  type HostKind,
  type HostLLMInvokeArgs,
  type HostLLMResult,
} from './host-llm-activity.js'

// M9 Group FF (T-151). TenantIsolation engine — runtime-derived cross-tenant
// boundary enforcement. Reads existing D4 §3 `delegates_to: Tenant→Tenant`
// edges (codex P1.2 fold; no new schema). Engine throws CrossTenantBoundaryError
// when a cross-tenant op is attempted without a delegates_to edge granting it;
// step-graph-executor catches the throw and synthesizes a step failure routed
// via the existing M5 failure-policy. No annotation-driven opt-out (codex
// re-review P1 fold — `WorkflowStep.crosses_tenant?` was removed as a bypass
// loophole).
export {
  TenantIsolation,
  CrossTenantBoundaryError,
  type AssertCrossTenantAllowedInput,
} from './tenant-isolation.js'

// M9 Group GG (T-156..T-160). CadenceScheduler — per-cadence callback
// dispatcher with deterministic clock injection. Supports every_n_minutes /
// every_n_hours / every_day_at / cron (escape hatch). I-12 invariant: per-hour
// cadence fires within ±5 minutes (`CADENCE_JITTER_MS`).
export {
  CadenceScheduler,
  CADENCE_JITTER_MS,
  type CadenceSpec,
  type CadenceCallback,
  type CadenceHandle,
  type CadenceSchedulerOptions,
  type TickReport,
  type TickFireEntry,
  type TickErrorEntry,
} from './cadence-scheduler.js'

// Note: `__set/resetWorkflowContextProbeForTest` are intentionally NOT
// re-exported here — they live in `./_test_seams.ts` and are reachable only
// by test code that imports from that path directly. This keeps the public
// engine barrel free of test-only seams.
//
// `__resetWorkflowRunSeqForTest` (M8 Group Z T-108) is the trace_id seam —
// also intentionally NOT on the public barrel; tests import directly from
// './step-graph-executor.js'.
//
// `__set/resetHostAvailabilityForTest`, `__set/resetExecFileSyncStubForTest`,
// `__deriveInvocationIdForTest` (M8 Group BB T-117..T-119) are also NOT on
// the public barrel — tests import directly from './host-llm-activity.js'.
//
// `__set/resetInvokeHostLLMF12ProbeForTest` (M8 codex master 2026-04-30 P1.1
// fold) — F-12 defense-in-depth probe seam mirroring the opa-evaluator
// pattern. Reachable only via direct module import in test code.
