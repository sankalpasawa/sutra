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

// M7 Group V — OPA evaluator. `evaluate(policy, input)` shells out to the
// OPA binary; `policyEvalActivity` is the asActivity-wrapped form that
// preserves the M5 I/O boundary (codex r8 P1.1). `OPAUnavailableError`
// surfaces when the binary is missing — the runtime treats this as deny.
export {
  evaluate,
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

// Note: `__set/resetWorkflowContextProbeForTest` are intentionally NOT
// re-exported here — they live in `./_test_seams.ts` and are reachable only
// by test code that imports from that path directly. This keeps the public
// engine barrel free of test-only seams.
