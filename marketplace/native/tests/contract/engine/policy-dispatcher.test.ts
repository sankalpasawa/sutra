/**
 * Policy dispatcher contract test — M7 Group V (T-092).
 *
 * Asserts:
 *  - makePolicyDispatcher() returns an object with dispatch_policy_eval
 *  - dispatch_policy_eval routes through policyEvalActivity → real OPA path
 *  - The interface accepts hand-rolled mocks (test-time injection contract)
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-092
 */

import { describe, it, expect } from 'vitest'

import {
  makePolicyDispatcher,
  type PolicyDispatcher,
  type PolicyEvalCommand,
} from '../../../src/engine/policy-dispatcher.js'
import { compileCharter } from '../../../src/engine/charter-rego-compiler.js'
import { OPABundleService } from '../../../src/engine/opa-bundle-service.js'
import type { PolicyDecision } from '../../../src/engine/opa-evaluator.js'
import type { Charter } from '../../../src/primitives/charter.js'

function charter(): Charter {
  return {
    id: 'C-disp',
    purpose: 'p',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [
      { name: 'always_allow', predicate: '1 == 1', durability: 'episodic', owner_scope: 'charter' },
    ],
    acl: [],
  }
}

describe('makePolicyDispatcher — default factory', () => {
  it('returns an object with dispatch_policy_eval', () => {
    const bundle = new OPABundleService()
    const d = makePolicyDispatcher(bundle)
    expect(typeof d.dispatch_policy_eval).toBe('function')
  })

  it('routes through bundle.get → policyEvalActivity → allow for a passing charter', async () => {
    // Codex master review 2026-04-30 P2.1 fold (CHANGE): the dispatcher
    // command now references the policy by id (+ optional version); the
    // bundle service is consulted at dispatch time. Register the policy
    // first, then dispatch with `policy_id` only.
    const policy = compileCharter(charter())
    const bundle = new OPABundleService()
    bundle.register(policy)
    const d = makePolicyDispatcher(bundle)
    const cmd: PolicyEvalCommand = {
      kind: 'policy_eval',
      policy_id: policy.policy_id,
      policy_version: policy.policy_version,
      input: { step: {}, workflow: {}, execution_context: {} },
    }
    const decision: PolicyDecision = await d.dispatch_policy_eval(cmd)
    expect(decision.kind).toBe('allow')
  })

  it('synthesizes deny when bundle.get returns null (sovereignty discipline)', async () => {
    // P2.1 fold: missing policy ⇒ synthetic deny. The runtime never fabricates
    // an "approval" when policy resolution fails. rule_name carries the
    // diagnostic tag, reason carries the missing id+version for operator
    // diagnosis.
    const bundle = new OPABundleService()
    const d = makePolicyDispatcher(bundle)
    const decision = await d.dispatch_policy_eval({
      kind: 'policy_eval',
      policy_id: 'C-not-registered',
      input: { step: {}, workflow: {}, execution_context: {} },
    })
    expect(decision.kind).toBe('deny')
    if (decision.kind === 'deny') {
      expect(decision.rule_name).toBe('bundle_lookup_failure')
      expect(decision.reason).toContain('C-not-registered')
      expect(decision.policy_version).toBe('unknown')
    }
  })
})

describe('PolicyDispatcher — hand-rolled mock', () => {
  it('accepts test-time injected dispatchers via the interface', async () => {
    const mock: PolicyDispatcher = {
      dispatch_policy_eval: async (_cmd) => ({
        kind: 'deny',
        policy_version: 'mock-v1',
        rule_name: 'deny',
        reason: 'mock-reason',
      }),
    }
    const decision = await mock.dispatch_policy_eval({
      kind: 'policy_eval',
      policy_id: 'C-mock',
      input: { step: {}, workflow: {}, execution_context: {} },
    })
    expect(decision.kind).toBe('deny')
    if (decision.kind === 'deny') {
      expect(decision.reason).toBe('mock-reason')
    }
  })
})
