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

  // ---------------------------------------------------------------------------
  // Codex M3 P1 #3 (2026-04-28) — coversAllObligations relation-check:
  //   (a) covered_by_step MUST exist in workflow.step_graph[*].step_id
  //   (b) the referenced step's traces_to MUST include the obligation
  // Shape-only acceptance of a numeric covered_by_step is unsound — it lets
  // operationalizes(W,C) return true with fabricated coverage decisions.
  // ---------------------------------------------------------------------------

  it('P1.3: coversAllObligations(C, cov, W) rejects covered_by_step pointing to non-existent step', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      // 999 is NOT a step_id in W (which has step_ids 0 and 1).
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 999 }],
    }
    expect(l4Commitment.coversAllObligations(C, cov, W)).toBe(false)
    expect(l4Commitment.operationalizes(W, C, cov)).toBe(false)
  })

  it('P1.3: coversAllObligations(C, cov, W) rejects step that does not trace to the obligation it claims to cover', () => {
    // step_id=1 exists, but its traces_to does NOT include 'oblig-1'.
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['some-other-name'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 1 }],
    }
    expect(l4Commitment.coversAllObligations(C, cov, W)).toBe(false)
    expect(l4Commitment.operationalizes(W, C, cov)).toBe(false)
  })

  it('P1.3: coversAllObligations(C, cov, W) accepts when covered_by_step exists AND traces_to includes obligation', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: ['oblig-1'] },
        { step_id: 1, traces_to: ['oblig-1'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 1 }],
    }
    expect(l4Commitment.coversAllObligations(C, cov, W)).toBe(true)
    expect(l4Commitment.operationalizes(W, C, cov)).toBe(true)
  })

  it('P1.3: coversAllObligations without workflow skips step-existence check but still validates step_coverage relation', () => {
    // No workflow passed → step-existence check (a) is skipped, but the
    // step_coverage relation-check (b) still runs when step_coverage is
    // provided. This keeps the predicate sound when used standalone (e.g.
    // legacy callers that exercise charter+coverage in isolation).
    const covWithRelation: CoverageMatrix = {
      step_coverage: [
        { step_id: 5, traces_to: ['oblig-1'] },
      ],
      // 5 exists in step_coverage AND traces_to includes 'oblig-1' → ok.
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 5 }],
    }
    expect(l4Commitment.coversAllObligations(C, covWithRelation)).toBe(true)

    // Disagreement in step_coverage relation → still false even without W.
    const covMismatch: CoverageMatrix = {
      step_coverage: [
        { step_id: 5, traces_to: ['some-other'] },
      ],
      obligation_coverage: [{ obligation_name: 'oblig-1', covered_by_step: 5 }],
    }
    expect(l4Commitment.coversAllObligations(C, covMismatch)).toBe(false)
  })

  it('P1.3: declared accepted gap clears relation-check (no covered_by_step required)', () => {
    const cov: CoverageMatrix = {
      step_coverage: [
        { step_id: 0, traces_to: [] },
        { step_id: 1, traces_to: [] },
      ],
      // gap_status='accepted' clears even with non-existent step pointer.
      obligation_coverage: [
        { obligation_name: 'oblig-1', covered_by_step: 999, gap_status: 'accepted' },
      ],
    }
    expect(l4Commitment.coversAllObligations(C, cov, W)).toBe(true)
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
