/**
 * L4 COMMITMENT — contract tests (deterministic edges + T1-T6 edges)
 */
import { describe, it, expect } from 'vitest'
import { l4Commitment, type CoverageMatrix } from '../../../src/laws/l4-commitment.js'
import {
  l4TerminalCheck,
  type TerminalCheckContext,
  type SchemaValidator,
} from '../../../src/laws/l4-terminal-check.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import { createCharter } from '../../../src/primitives/charter.js'
import type { Workflow } from '../../../src/primitives/workflow.js'
import type { Charter } from '../../../src/primitives/charter.js'

const ALWAYS_VALID: SchemaValidator = () => true

const W: Workflow = createWorkflow({
  id: 'W-test',
  preconditions: '',
  step_graph: [
    { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
  ],
  inputs: [],
  outputs: [],
  state: [],
  postconditions: '',
  failure_policy: '',
  stringency: 'task',
  interfaces_with: [],
})

const C: Charter = createCharter({
  id: 'C-test',
  purpose: 'p',
  scope_in: '',
  scope_out: '',
  obligations: [
    {
      name: 'oblig-1',
      predicate: 'p1',
      durability: 'durable',
      owner_scope: 'charter',
      type: 'obligation',
    },
  ],
  invariants: [],
  success_metrics: [],
  authority: '',
  termination: '',
  constraints: [],
  acl: [],
})

describe('L4 COMMITMENT — contract', () => {
  it('happy: every step traces to oblig-1 → tracesAllSteps=true', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 0 }],
    }
    expect(l4Commitment.tracesAllSteps(W, C, cov)).toBe(true)
    expect(l4Commitment.coversAllObligations(C, cov)).toBe(true)
    expect(l4Commitment.operationalizes(W, C, cov)).toBe(true)
  })

  it('untraced step (no entry) → tracesAllSteps=false', () => {
    const cov: CoverageMatrix = {
      step_coverage: [{ step_id: 0, traces_to: ['oblig-1'] }], // step 1 missing
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 0 }],
    }
    expect(l4Commitment.tracesAllSteps(W, C, cov)).toBe(false)
    expect(l4Commitment.operationalizes(W, C, cov)).toBe(false)
  })

  it('orphan step with gap_status=accepted → tracesAllSteps=true', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: [], gap_status: 'accepted' },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 0 }],
    }
    expect(l4Commitment.tracesAllSteps(W, C, cov)).toBe(true)
  })

  it('uncovered obligation → coversAllObligations=false', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [],
    }
    expect(l4Commitment.coversAllObligations(C, cov)).toBe(false)
  })

  it('declared gap on obligation → coversAllObligations=true', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [
        { obligation_name: 'oblig-1', covered_by_step: null, gap_status: 'accepted' },
      ],
    }
    expect(l4Commitment.coversAllObligations(C, cov)).toBe(true)
  })

  it('terminal-check happy path → pass=true', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 0 }],
    }
    const ctx: TerminalCheckContext = {
      workflow: W,
      charter: C,
      postcondition_predicates: [],
      output_validators: [],
      coverage: cov,
      interface_violations: [],
      children: [],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      self_execution_id: 'E-self',
    }
    const r = l4TerminalCheck.runAll(ctx)
    expect(r.pass).toBe(true)
    expect(r.failed_at).toBeNull()
  })

  it('terminal-check T2 fail → failed_at=T2', () => {
    const wWithOutputs = createWorkflow({
      ...W,
      outputs: [
        {
          kind: 'k',
          schema_ref: 's',
          locator: 'l',
          version: '',
          mutability: 'immutable',
          retention: '',
        },
      ],
    })
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 0 }],
    }
    const ctx: TerminalCheckContext = {
      workflow: wWithOutputs,
      charter: C,
      postcondition_predicates: [],
      output_validators: [() => false],
      coverage: cov,
      interface_violations: [],
      children: [],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      self_execution_id: 'E-self',
    }
    const r = l4TerminalCheck.runAll(ctx)
    expect(r.pass).toBe(false)
    expect(r.failed_at).toBe('T2')
    expect(r.failure_reason).toBe('terminal_check_failed:T2')
    // Use ALWAYS_VALID to keep import alive (and keep helper available).
    expect(typeof ALWAYS_VALID).toBe('function')
  })
})
