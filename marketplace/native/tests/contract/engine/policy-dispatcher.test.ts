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
    const d = makePolicyDispatcher()
    expect(typeof d.dispatch_policy_eval).toBe('function')
  })

  it('routes through policyEvalActivity → returns allow for a passing charter', async () => {
    const d = makePolicyDispatcher()
    const policy = compileCharter(charter())
    const cmd: PolicyEvalCommand = {
      kind: 'policy_eval',
      policy,
      input: { step: {}, workflow: {}, execution_context: {} },
    }
    const decision: PolicyDecision = await d.dispatch_policy_eval(cmd)
    expect(decision.kind).toBe('allow')
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
    const policy = compileCharter(charter())
    const decision = await mock.dispatch_policy_eval({
      kind: 'policy_eval',
      policy,
      input: { step: {}, workflow: {}, execution_context: {} },
    })
    expect(decision.kind).toBe('deny')
    if (decision.kind === 'deny') {
      expect(decision.reason).toBe('mock-reason')
    }
  })
})
