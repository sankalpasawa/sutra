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
export {
  executeStepGraph,
  formatTerminalCheckFailureReason,
  type ActivityDispatcher,
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

// Note: `__set/resetWorkflowContextProbeForTest` are intentionally NOT
// re-exported here — they live in `./_test_seams.ts` and are reachable only
// by test code that imports from that path directly. This keeps the public
// engine barrel free of test-only seams.
