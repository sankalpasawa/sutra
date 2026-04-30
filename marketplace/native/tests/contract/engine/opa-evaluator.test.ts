/**
 * OPA evaluator contract test — M7 Group V (T-090, T-091).
 *
 * Asserts:
 *  - allow path: input that satisfies the charter constraint → kind:'allow'
 *  - deny path (default-deny): input that does NOT match any allow rule →
 *    kind:'deny', rule_name:'default_allow_false', reason:'default_deny'
 *  - obligation deny path: missing obligation → kind:'deny', rule_name:'deny',
 *    reason:<stringified obligation reason>
 *  - policy_version is preserved on every decision
 *  - policyEvalActivity throws F-12 when invoked from a Workflow context
 *  - same (policy, input) ⇒ same decision (replay determinism)
 *
 * Notes on test isolation:
 *  - Tests invoke the real OPA binary (1.15.2; verified by Group V plan).
 *  - The evaluator caches a one-shot binary probe. That cache is harmless
 *    across allow/deny tests; reset only needed by tests that simulate
 *    OPA-missing scenarios (none here — that path is covered by the
 *    OPAUnavailableError unit test in tests/unit).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-090, T-091
 */

import { describe, it, expect, afterAll } from 'vitest'

import {
  evaluate,
  policyEvalActivity,
  __setEvaluateF12ProbeForTest,
  __resetEvaluateF12ProbeForTest,
  type PolicyDecision,
} from '../../../src/engine/opa-evaluator.js'
import { compileCharter } from '../../../src/engine/charter-rego-compiler.js'
import type { Charter } from '../../../src/primitives/charter.js'
import {
  __setWorkflowContextProbeForTest,
  __resetWorkflowContextProbeForTest,
} from '../../../src/engine/_test_seams.js'

function charterWithAllow(predicate: string): Charter {
  return {
    id: 'C-eval-allow',
    purpose: 'p',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [{ name: 'allow_when', predicate, durability: 'episodic', owner_scope: 'charter' }],
    acl: [],
  }
}

function charterWithObligation(predicate: string): Charter {
  return {
    id: 'C-eval-oblig',
    purpose: 'p',
    scope_in: '',
    scope_out: '',
    obligations: [{ name: 'must_hold', type: 'obligation', predicate, durability: 'durable', owner_scope: 'charter' }],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [],
    acl: [],
  }
}

describe('opa-evaluator — allow path', () => {
  it('returns kind:"allow" when an allow rule matches', () => {
    const charter = charterWithAllow('input.step.step_id == 1')
    const policy = compileCharter(charter)
    const decision = evaluate(policy, {
      step: { step_id: 1 },
      workflow: { id: 'W-test' },
      execution_context: {},
    })
    expect(decision.kind).toBe('allow')
    if (decision.kind === 'allow') {
      expect(decision.policy_version).toBe(policy.policy_version)
    }
  })
})

describe('opa-evaluator — default-deny path', () => {
  it('returns kind:"deny" with rule_name:"default_allow_false" when no allow rule matches', () => {
    const charter = charterWithAllow('input.step.step_id == 1')
    const policy = compileCharter(charter)
    const decision = evaluate(policy, {
      step: { step_id: 99 },
      workflow: { id: 'W-test' },
      execution_context: {},
    })
    expect(decision.kind).toBe('deny')
    if (decision.kind === 'deny') {
      expect(decision.rule_name).toBe('default_allow_false')
      expect(decision.reason).toBe('default_deny')
      expect(decision.policy_version).toBe(policy.policy_version)
    }
  })
})

describe('opa-evaluator — obligation deny path', () => {
  it('returns kind:"deny" with the obligation reason when obligation predicate fails', () => {
    // Obligations both produce an `allow if {pred}` AND a `deny[reason] if
    // {!pred}` rule. When pred is false ⇒ allow=false AND deny set non-empty.
    // The evaluator's deny-wins logic surfaces the obligation reason.
    const charter = charterWithObligation('input.workflow.id == "W-required"')
    const policy = compileCharter(charter)
    const decision = evaluate(policy, {
      step: { step_id: 1 },
      workflow: { id: 'W-other' },
      execution_context: {},
    })
    expect(decision.kind).toBe('deny')
    if (decision.kind === 'deny') {
      expect(decision.rule_name).toBe('deny')
      // Codex master review 2026-04-30 P1.2 fold (BLOCKER): the raw Rego SET
      // key is `{"obligation":"must_hold"}` — sanitizer escapes `:` to `\:`
      // so the reason can flow into the M5 canonical failure_reason envelope
      // without breaking the colon-delimited audit format. The keywords
      // (`must_hold`, `obligation`) still appear in the sanitized output.
      expect(decision.reason).toContain('must_hold')
      expect(decision.reason).toContain('obligation')
      // Sanitizer contract: NO unescaped `:` in the reason after sanitization.
      // Every `:` must be preceded by `\` (escape). We verify by stripping
      // escaped colons and asserting no raw `:` remains.
      const stripped = decision.reason.replace(/\\:/g, '')
      expect(stripped).not.toContain(':')
      expect(decision.policy_version).toBe(policy.policy_version)
    }
  })
})

describe('opa-evaluator — replay determinism', () => {
  it('same (policy, input) yields the same decision on re-evaluation', () => {
    const charter = charterWithAllow('input.step.step_id == 7')
    const policy = compileCharter(charter)
    const input = {
      step: { step_id: 7 },
      workflow: { id: 'W-test' },
      execution_context: {},
    }
    const a: PolicyDecision = evaluate(policy, input)
    const b: PolicyDecision = evaluate(policy, input)
    expect(a).toEqual(b)
  })
})

describe('policyEvalActivity — F-12 boundary', () => {
  afterAll(() => {
    __resetWorkflowContextProbeForTest()
  })

  it('throws F-12 when invoked from a Workflow context', async () => {
    // Simulate Workflow context — probe returns true.
    __setWorkflowContextProbeForTest(() => true)
    const charter = charterWithAllow('input.step.step_id == 1')
    const policy = compileCharter(charter)
    await expect(
      policyEvalActivity(policy, {
        step: { step_id: 1 },
        workflow: { id: 'W-test' },
        execution_context: {},
      }),
    ).rejects.toThrowError(/F-12/)
    __resetWorkflowContextProbeForTest()
  })

  it('returns the decision when invoked outside a Workflow context', async () => {
    __resetWorkflowContextProbeForTest()
    const charter = charterWithAllow('input.step.step_id == 1')
    const policy = compileCharter(charter)
    const decision = await policyEvalActivity(policy, {
      step: { step_id: 1 },
      workflow: { id: 'W-test' },
      execution_context: {},
    })
    expect(decision.kind).toBe('allow')
  })
})

// =============================================================================
// Codex master review 2026-04-30 P1.1 fold (BLOCKER) — raw evaluate() F-12
// =============================================================================
//
// Defense-in-depth: the public engine barrel no longer re-exports `evaluate`
// (consumers reach the OPA path only via policyEvalActivity / dispatcher).
// However, internal/test code still imports `evaluate` directly. This guard
// trips when evaluate() is called from inside a Workflow context — the
// Workflow code can't bypass the Activity boundary even if it imports the
// raw function.
describe('opa-evaluator — raw evaluate() F-12 guard (P1.1 fold)', () => {
  afterAll(() => {
    __resetEvaluateF12ProbeForTest()
  })

  it('throws F-12 error when evaluate() is called from a simulated Workflow context', () => {
    // Simulate Workflow context — probe returns true.
    __setEvaluateF12ProbeForTest(() => true)
    const charter = charterWithAllow('input.step.step_id == 1')
    const policy = compileCharter(charter)
    expect(() =>
      evaluate(policy, {
        step: { step_id: 1 },
        workflow: { id: 'W-test' },
        execution_context: {},
      }),
    ).toThrowError(/F-12/)
    __resetEvaluateF12ProbeForTest()
  })
})
