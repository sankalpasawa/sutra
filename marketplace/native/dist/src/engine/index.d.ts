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
export { registerWorkflow, type TemporalWorkflowDefinition, type ActivityDescriptor, } from './temporal-adapter.js';
export { asActivity, F12_ERROR_TAG, type ActivityFn, } from './activity-wrapper.js';
export { executeStepGraph, formatTerminalCheckFailureReason, type ActivityDispatcher, type ChildEdge, type DispatchContext, type ExecuteOptions, type ExecutionResult, type StepDispatchResult, type TerminalCheckProbe, } from './step-graph-executor.js';
export { applyFailurePolicy, type ExecutionContext, type FailurePolicyOutcome, } from './failure-policy.js';
export { SkillEngine, type ValidateOutputsResult, } from './skill-engine.js';
export { invokeSkill, SKILL_RECURSION_CAP, type SkillInvocationContext, type SkillInvocationFailure, type SkillInvocationResult, type SkillInvocationSuccess, } from './skill-invocation.js';
export { compileCharter, checkBuiltinAllowlist, ALLOWED_BUILTINS, BuiltinNotAllowedError, COMPILER_VERSION_CONST, type CompiledPolicy, } from './charter-rego-compiler.js';
export { OPABundleService } from './opa-bundle-service.js';
export { policyEvalActivity, OPAUnavailableError, type PolicyAllow, type PolicyDecision, type PolicyDeny, type PolicyInput, } from './opa-evaluator.js';
export { makePolicyDispatcher, type DispatchableCommand, type PolicyDispatcher, type PolicyEvalCommand, } from './policy-dispatcher.js';
export { InMemoryOTelExporter, NoopOTelExporter, OTelEmitter, OTLPHttpExporter, type OTelEventKind, type OTelEventRecord, type OTelExporter, } from './otel-emitter.js';
export { GovernanceOverhead, TurnNotStartedError, type GovernanceCategory, type GovernanceOverheadOptions, type OverheadReport, } from './governance-overhead.js';
export { hostLLMActivity, HostUnavailableError, type HostKind, type HostLLMInvokeArgs, type HostLLMResult, } from './host-llm-activity.js';
export { TenantIsolation, CrossTenantBoundaryError, type AssertCrossTenantAllowedInput, } from './tenant-isolation.js';
export { CadenceScheduler, CADENCE_JITTER_MS, type CadenceSpec, type CadenceCallback, type CadenceHandle, type CadenceSchedulerOptions, type TickReport, type TickFireEntry, type TickErrorEntry, } from './cadence-scheduler.js';
//# sourceMappingURL=index.d.ts.map