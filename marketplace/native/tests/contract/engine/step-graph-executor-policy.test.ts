/**
 * step-graph-executor + policy gate contract test — M7 Group V (T-094).
 *
 * Asserts:
 *  - allow path: step.policy_check=true + dispatcher returns allow ⇒ step
 *    runs through normal dispatch
 *  - deny path: step.policy_check=true + dispatcher returns deny ⇒ step
 *    fails with synthetic errMsg `policy_deny:<rule_name>:<reason>:<policy_version>`,
 *    routed via M5 failure-policy per step.on_failure
 *  - workflow.modifies_sutra=true triggers policy_check on EVERY step (V2.4 §A12),
 *    even when step.policy_check is unset
 *  - policy gate is no-op when policy_dispatcher is absent (back-compat with
 *    M5/M6 tests that don't supply one)
 *  - dispatcher errors (e.g. OPAUnavailableError) translate to deny — the
 *    runtime never fabricates approval when authorization can't be verified
 *  - rollback / abort / continue routes all fire correctly on policy deny
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-094
 */

import { describe, it, expect } from 'vitest'

import { createWorkflow, type Workflow } from '../../../src/primitives/workflow.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../../src/engine/step-graph-executor.js'
import type {
  PolicyDispatcher,
  PolicyEvalCommand,
} from '../../../src/engine/policy-dispatcher.js'
import type {
  PolicyDecision,
  PolicyAllow,
  PolicyDeny,
} from '../../../src/engine/opa-evaluator.js'
import type { CompiledPolicy } from '../../../src/engine/charter-rego-compiler.js'

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

const stubPolicy: CompiledPolicy = Object.freeze({
  policy_id: 'C_test',
  policy_version: 'sha256-stub-v1',
  rego_source: 'package sutra.charter.C_test\nimport rego.v1\ndefault allow := false\n',
})

function alwaysAllow(): PolicyDispatcher {
  return {
    dispatch_policy_eval: async (_cmd: PolicyEvalCommand): Promise<PolicyDecision> => {
      const allow: PolicyAllow = { kind: 'allow', policy_version: stubPolicy.policy_version }
      return allow
    },
  }
}

function alwaysDeny(rule_name = 'deny', reason = 'unmet_obligation'): PolicyDispatcher {
  return {
    dispatch_policy_eval: async (_cmd: PolicyEvalCommand): Promise<PolicyDecision> => {
      const deny: PolicyDeny = {
        kind: 'deny',
        policy_version: stubPolicy.policy_version,
        rule_name,
        reason,
      }
      return deny
    },
  }
}

function dispatcherErrors(message: string): PolicyDispatcher {
  return {
    dispatch_policy_eval: async (_cmd: PolicyEvalCommand): Promise<PolicyDecision> => {
      throw new Error(message)
    },
  }
}

interface BuildOpts {
  on_failure?: 'rollback' | 'escalate' | 'pause' | 'abort' | 'continue'
  policy_check?: boolean
  modifies_sutra?: boolean
  steps?: number
}

function workflowFor(opts: BuildOpts = {}): Workflow {
  const stepCount = opts.steps ?? 2
  return createWorkflow({
    id: 'W-policy-test',
    preconditions: '',
    step_graph: Array.from({ length: stepCount }, (_, i) => ({
      step_id: i + 1,
      skill_ref: `skill.${i + 1}`,
      inputs: [],
      outputs: [],
      on_failure: opts.on_failure ?? 'abort',
      ...(opts.policy_check !== undefined ? { policy_check: opts.policy_check } : {}),
    })),
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    ...(opts.modifies_sutra !== undefined ? { modifies_sutra: opts.modifies_sutra } : {}),
  })
}

const okDispatcher: ActivityDispatcher = (descriptor): StepDispatchResult => {
  return { kind: 'ok', outputs: [`step-${descriptor.step_id}-result`] }
}

// -----------------------------------------------------------------------------
// Tests
// -----------------------------------------------------------------------------

describe('executeStepGraph — policy gate allow path', () => {
  it('allows step.policy_check=true to proceed when dispatcher returns allow', async () => {
    const w = workflowFor({ policy_check: true })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: alwaysAllow(),
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1, 2])
    expect(result.failure_reason).toBeNull()
  })

  it('passes the policy gate transparently when neither policy_check nor modifies_sutra is set', async () => {
    const w = workflowFor({ policy_check: false, modifies_sutra: false })
    let dispatchCount = 0
    const dispatcher: PolicyDispatcher = {
      dispatch_policy_eval: async () => {
        dispatchCount++
        return { kind: 'allow', policy_version: stubPolicy.policy_version }
      },
    }
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('success')
    // Policy dispatcher MUST NOT have been invoked — neither activation
    // condition was true.
    expect(dispatchCount).toBe(0)
  })
})

describe('executeStepGraph — policy gate deny path', () => {
  it('translates deny into synthetic step failure with the canonical errMsg format', async () => {
    const w = workflowFor({ policy_check: true, on_failure: 'abort' })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: alwaysDeny('deny', 'reflexive_check_failed'),
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('failed')
    // failure_reason format from failure-policy: step:<id>:<action>:<errMsg>
    // errMsg from the policy gate: policy_deny:<rule_name>:<reason>:<version>
    expect(result.failure_reason).toContain('step:1:abort:policy_deny:deny:reflexive_check_failed:sha256-stub-v1')
    // Step 1 visited (failed step) but never completed.
    expect(result.visited_step_ids).toEqual([1])
    expect(result.completed_step_ids).toEqual([])
  })

  it('routes deny through on_failure=rollback policy', async () => {
    // Two steps; step 1 succeeds (no policy_check), step 2 has policy_check=true
    // + on_failure=rollback. Step 1 should appear in rollback_compensations.
    const w = createWorkflow({
      id: 'W-policy-rollback',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 's1', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, skill_ref: 's2', inputs: [], outputs: [], on_failure: 'rollback', policy_check: true },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: alwaysDeny('deny', 'oblig_x'),
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('failed')
    expect(result.rollback_compensations).toEqual([1])
    expect(result.failure_reason).toContain('policy_deny:deny:oblig_x:sha256-stub-v1')
  })

  it('routes deny through on_failure=continue policy (partial=true, advances)', async () => {
    const w = workflowFor({ policy_check: true, on_failure: 'continue', steps: 2 })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: alwaysDeny('deny', 'oblig_y'),
      compiled_policy: stubPolicy,
    })
    // Both steps' policy_check=true → both fail → both 'continue' → state stays
    // 'success' but partial=true; visited has both, completed has neither.
    expect(result.state).toBe('success')
    expect(result.partial).toBe(true)
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.completed_step_ids).toEqual([])
  })
})

describe('executeStepGraph — modifies_sutra triggers policy gate on every step', () => {
  it('every step gets policy-checked when workflow.modifies_sutra=true', async () => {
    const w = workflowFor({ modifies_sutra: true, steps: 3 })
    const calls: number[] = []
    const dispatcher: PolicyDispatcher = {
      dispatch_policy_eval: async (cmd) => {
        // The PolicyInput contains the step under evaluation — we read its
        // step_id from the input shape to assert per-step invocation.
        const stepId = (cmd.input.step as { step_id: number }).step_id
        calls.push(stepId)
        return { kind: 'allow', policy_version: stubPolicy.policy_version }
      },
    }
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('success')
    expect(calls).toEqual([1, 2, 3])
  })
})

describe('executeStepGraph — policy gate misconfiguration safety', () => {
  it('is a no-op when policy_dispatcher is absent (back-compat)', async () => {
    // policy_check=true on the step but NO policy_dispatcher in options.
    // Per the gate-active rule, the gate is inactive → step proceeds.
    const w = workflowFor({ policy_check: true })
    const result = await executeStepGraph(w, okDispatcher, {})
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1, 2])
  })

  it('is a no-op when compiled_policy is absent', async () => {
    // policy_dispatcher supplied but compiled_policy is not — gate stays
    // inactive (defensive default — never block-as-side-effect-of-misconfiguration).
    const w = workflowFor({ policy_check: true })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: alwaysDeny(),
      // compiled_policy intentionally omitted
    })
    expect(result.state).toBe('success')
  })
})

describe('executeStepGraph — dispatcher errors → deny', () => {
  it('treats dispatcher exceptions as deny (sovereignty discipline)', async () => {
    const w = workflowFor({ policy_check: true })
    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcherErrors('OPA binary missing'),
      compiled_policy: stubPolicy,
    })
    expect(result.state).toBe('failed')
    // Synthetic errMsg uses rule_name='dispatch_error' so operators can
    // distinguish "policy returned deny" from "policy could not be evaluated".
    expect(result.failure_reason).toContain('policy_deny:dispatch_error:OPA binary missing')
  })
})
