/**
 * Policy dispatcher — M7 Group V (T-092).
 *
 * Bridges the M5 step-graph executor to the M7 OPA evaluator. The executor
 * already has an `ActivityDispatcher` for routing per-step Activity calls;
 * Group V adds an ORTHOGONAL dispatcher path for `policy_eval` commands.
 *
 * Why orthogonal (codex r8 P1.1):
 * - The existing ActivityDispatcher is a callable `(descriptor, ctx) =>
 *   StepDispatchResult` — its contract is "dispatch this step's Activity".
 *   Cramming a `policy_eval` discriminator into the descriptor would
 *   pollute every M5 dispatcher implementation with M7-specific knowledge.
 * - Instead, `PolicyDispatcher` is a separate object with a single method
 *   `dispatch_policy_eval(cmd) → Promise<PolicyDecision>`. The executor
 *   checks for its presence in `options.policy_dispatcher` and invokes it
 *   BEFORE the step's normal dispatch when policy_check applies.
 * - This keeps the M5 dispatcher contract unchanged AND makes the policy
 *   path independently testable (a unit test can pass a mock
 *   PolicyDispatcher without re-implementing the full ActivityDispatcher).
 *
 * Activity boundary preservation:
 * - The default factory `withPolicyDispatch()` returns a PolicyDispatcher
 *   whose `dispatch_policy_eval` calls `policyEvalActivity(policy, input)`.
 *   The Activity wrapper enforces F-12 at runtime: Workflow code that
 *   tried to bypass the dispatcher and call `policyEvalActivity` directly
 *   would still throw F-12 (the wrapper detects Workflow context).
 *
 * Source-of-truth:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-092
 *  - .enforcement/codex-reviews/2026-04-30-m7-plan-pre-dispatch.md P1.1
 */

import type { OPABundleService } from './opa-bundle-service.js'
import {
  policyEvalActivity,
  type PolicyDecision,
  type PolicyInput,
} from './opa-evaluator.js'
import type { AgentIdentity } from '../types/agent-identity.js'
import { OTelEmitter, type OTelEventRecord } from './otel-emitter.js'

/**
 * Discriminated command shape. v1.0 only carries `policy_eval`; future
 * dispatchable commands (e.g. `policy_compile_refresh`) extend the union
 * without breaking existing handlers.
 *
 * Codex master review 2026-04-30 P2.1 fold (CHANGE): commands now carry a
 * BUNDLE REFERENCE (`policy_id` + optional `policy_version`) rather than a
 * full `CompiledPolicy` payload. The dispatcher looks the policy up via
 * `OPABundleService.get(...)` at runtime — making the bundle service the
 * live policy source of truth (matching the M7 stated runtime model).
 */
export interface PolicyEvalCommand {
  readonly kind: 'policy_eval'
  readonly policy_id: string
  /** Optional version pin. When omitted, the bundle's latest is used. */
  readonly policy_version?: string
  readonly input: PolicyInput
  /**
   * M8 Group Z (T-106). Optional observability fields — when supplied, the
   * dispatcher emits POLICY_ALLOW / POLICY_DENY events to the configured
   * OTelEmitter carrying these identity + correlation fields. Absent values
   * keep the dispatcher emission-clean (e.g. M7 baseline tests that do not
   * supply an emitter or identity).
   */
  readonly trace_id?: string
  readonly workflow_id?: string
  readonly step_id?: number
  readonly agent_identity?: AgentIdentity
  readonly actor?: string
}

export type DispatchableCommand = PolicyEvalCommand

/**
 * Public PolicyDispatcher contract. Single method for v1.0; the interface
 * exists so future commands can be added without changing the executor's
 * call shape.
 */
export interface PolicyDispatcher {
  /**
   * Evaluate a compiled policy against a policy input. Returns the
   * deterministic `PolicyDecision` per `OPAEvaluator.evaluate` semantics
   * (deny-wins). Throws `OPAUnavailableError` if the OPA binary is missing.
   *
   * Bundle-lookup failure (no policy registered for `policy_id` / version):
   * synthesizes a deny per sovereignty discipline (the runtime never
   * fabricates an "approval" when policy resolution fails).
   */
  dispatch_policy_eval(cmd: PolicyEvalCommand): Promise<PolicyDecision>
}

/**
 * Default factory. Returns a `PolicyDispatcher` whose `dispatch_policy_eval`
 * resolves the policy via `bundleService.get(policy_id, policy_version)` and
 * routes through the Activity-wrapped evaluator. Tests inject their own
 * `PolicyDispatcher` directly when they want to assert allow/deny paths
 * without invoking the OPA binary.
 *
 * Codex master review 2026-04-30 P2.1 fold (CHANGE): the factory now takes
 * `bundleService` as its single required parameter — the bundle is the
 * policy source of truth at evaluation time.
 */
export function makePolicyDispatcher(
  bundleService: OPABundleService,
  otelEmitter?: OTelEmitter,
): PolicyDispatcher {
  if (typeof bundleService !== 'object' || bundleService === null) {
    throw new TypeError(
      'makePolicyDispatcher: bundleService must be an OPABundleService instance',
    )
  }
  // M8 Group Z (T-106). The emitter is OPTIONAL — M7 callers that don't yet
  // wire observability stay backward-compatible. When undefined we use a
  // shared "disabled" emitter so the dispatch hot-path can call .emit()
  // unconditionally without per-call branching.
  const emitter = otelEmitter ?? OTelEmitter.disabled()

  return {
    dispatch_policy_eval: async (cmd: PolicyEvalCommand): Promise<PolicyDecision> => {
      const policy = bundleService.get(cmd.policy_id, cmd.policy_version)
      if (policy === null) {
        // Sovereignty discipline: missing policy ⇒ synthetic deny. No
        // approval is fabricated when the runtime cannot prove authorization.
        // The reason carries the missing policy_id for operator diagnosis;
        // policy_version surfaces "unknown" since no compiled record exists.
        const missingId = cmd.policy_id
        const versionPart = cmd.policy_version ?? 'latest'
        const decision: PolicyDecision = {
          kind: 'deny',
          rule_name: 'bundle_lookup_failure',
          reason: `no_policy_for_id:${missingId}@${versionPart}`,
          policy_version: 'unknown',
        }
        await emitPolicyDecision(emitter, cmd, decision)
        return decision
      }
      const decision = await policyEvalActivity(policy, cmd.input)
      await emitPolicyDecision(emitter, cmd, decision)
      return decision
    },
  }
}

/**
 * M8 Group Z (T-106) helper. Emit POLICY_ALLOW or POLICY_DENY for the
 * dispatcher's decision. The emit is async but errors are NEVER propagated:
 * an exporter failure must not break Workflow execution. We swallow inside
 * a try/catch so the dispatch result returns to the executor regardless.
 *
 * Attribute schema:
 *   ALLOW: { policy_id, policy_version }
 *   DENY:  { policy_id, policy_version, rule_name, reason }
 *
 * Reason field carries the dispatcher's `reason` UNREDACTED. Codex review
 * note (Group AA + DD): if reasons start carrying user data in M11 dogfood,
 * this is the layer to add a sanitizer; for v1.0 the rule names + bundle
 * tags are operator-controlled strings.
 */
async function emitPolicyDecision(
  emitter: OTelEmitter,
  cmd: PolicyEvalCommand,
  decision: PolicyDecision,
): Promise<void> {
  // Emission requires a trace_id to be useful — without one the record
  // cannot correlate to a Workflow run. Skip silently if the executor
  // didn't supply one (M7 baseline path).
  if (typeof cmd.trace_id !== 'string' || cmd.trace_id.length === 0) {
    return
  }
  try {
    const base: Pick<
      OTelEventRecord,
      'trace_id' | 'workflow_id' | 'step_id' | 'agent_identity' | 'actor'
    > = {
      trace_id: cmd.trace_id,
      ...(cmd.workflow_id !== undefined ? { workflow_id: cmd.workflow_id } : {}),
      ...(cmd.step_id !== undefined ? { step_id: cmd.step_id } : {}),
      ...(cmd.agent_identity !== undefined ? { agent_identity: cmd.agent_identity } : {}),
      ...(cmd.actor !== undefined ? { actor: cmd.actor } : {}),
    }
    if (decision.kind === 'allow') {
      await emitter.emit({
        ...base,
        decision_kind: 'POLICY_ALLOW',
        attributes: {
          policy_id: cmd.policy_id,
          policy_version: decision.policy_version,
        },
      })
    } else {
      await emitter.emit({
        ...base,
        decision_kind: 'POLICY_DENY',
        attributes: {
          policy_id: cmd.policy_id,
          policy_version: decision.policy_version,
          rule_name: decision.rule_name,
          reason: decision.reason,
        },
      })
    }
  } catch {
    // Observability failure must NEVER break execution. Drop silently;
    // the production OTLP exporter handles its own retry/buffering.
  }
}
