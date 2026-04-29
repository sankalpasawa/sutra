/**
 * failure-policy contract tests — M5 Group K (T-050).
 *
 * Asserts each of the 5 routing branches and the explicit `continue` semantics
 * defined by codex P1.3:
 *   (a) failed step logged with reason
 *   (b) step[i+1] dispatched (executor advances — verified end-to-end in
 *       step-graph-executor.test.ts; failure-policy itself returns the
 *       continue outcome with the right shape)
 *   (c) `partial=true` flips on the Workflow execution
 *   (d) outputs validator SKIPPED for the failed step
 *   (e) Workflow does NOT abort
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-050
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P1.3
 */

import { describe, it, expect } from 'vitest'
import {
  applyFailurePolicy,
  type ExecutionContext,
  type FailurePolicyOutcome,
} from '../../../src/engine/failure-policy.js'
import type { WorkflowStep, StepFailureAction } from '../../../src/types/index.js'

function makeStep(on_failure: StepFailureAction, step_id = 7): WorkflowStep {
  return {
    step_id,
    skill_ref: 'skill.x',
    inputs: [],
    outputs: [],
    on_failure,
  }
}

function makeCtx(overrides: Partial<ExecutionContext> = {}): ExecutionContext {
  return {
    completed_step_ids: overrides.completed_step_ids ?? [1, 2, 3],
    autonomy_level: overrides.autonomy_level ?? 'manual',
    escalation_target: overrides.escalation_target,
  }
}

describe('failure-policy — 5-set router (V2 §17 A10)', () => {
  it('rollback: reverses completed step ids (compensation walk)', () => {
    const step = makeStep('rollback')
    const err = new Error('boom')
    const out: FailurePolicyOutcome = applyFailurePolicy(step, err, makeCtx({ completed_step_ids: [10, 20, 30] }))
    expect(out.action).toBe('rollback')
    if (out.action !== 'rollback') throw new Error('type narrowing')
    expect(out.compensation_order).toEqual([30, 20, 10])
    expect(out.reason).toContain('rollback')
    expect(out.reason).toContain('boom')
    expect(out.reason).toContain(`step:${step.step_id}`)
  })

  it('rollback with empty completed list → empty compensation_order', () => {
    const step = makeStep('rollback')
    const out = applyFailurePolicy(step, new Error('e'), makeCtx({ completed_step_ids: [] }))
    expect(out.action).toBe('rollback')
    if (out.action !== 'rollback') throw new Error('type narrowing')
    expect(out.compensation_order).toEqual([])
  })

  it('escalate: returns escalated:true + escalation_target (default founder)', () => {
    const step = makeStep('escalate')
    const out = applyFailurePolicy(step, new Error('whoops'), makeCtx())
    expect(out.action).toBe('escalate')
    if (out.action !== 'escalate') throw new Error('type narrowing')
    expect(out.escalated).toBe(true)
    expect(out.escalation_target).toBe('founder')
    expect(out.reason).toContain('escalate')
  })

  it('escalate: honors caller-supplied escalation_target', () => {
    const step = makeStep('escalate')
    const out = applyFailurePolicy(step, new Error('whoops'), makeCtx({ escalation_target: 'meta-charter' }))
    if (out.action !== 'escalate') throw new Error('type narrowing')
    expect(out.escalation_target).toBe('meta-charter')
  })

  it('pause: returns paused:true + deterministic resume_token', () => {
    const step = makeStep('pause', 42)
    const err = new Error('halt')
    const a = applyFailurePolicy(step, err, makeCtx())
    const b = applyFailurePolicy(step, err, makeCtx())
    expect(a.action).toBe('pause')
    if (a.action !== 'pause' || b.action !== 'pause') throw new Error('type narrowing')
    expect(a.paused).toBe(true)
    expect(a.resume_token).toMatch(/^resume:42:[0-9a-f]+$/)
    // Determinism — same step + same error msg ⇒ same token.
    expect(a.resume_token).toBe(b.resume_token)
  })

  it('abort: terminates immediately + returns failure reason', () => {
    const step = makeStep('abort', 99)
    const out = applyFailurePolicy(step, new Error('bad'), makeCtx())
    expect(out.action).toBe('abort')
    if (out.action !== 'abort') throw new Error('type narrowing')
    expect(out.reason).toContain('step:99:abort:bad')
  })

  // -------- continue: 5 specific assertions per codex P1.3 --------

  describe('continue (codex P1.3 — NON-NEGOTIABLE semantics)', () => {
    it('(a) failed step is logged with reason', () => {
      const step = makeStep('continue', 5)
      const out = applyFailurePolicy(step, new Error('oops'), makeCtx())
      expect(out.action).toBe('continue')
      if (out.action !== 'continue') throw new Error('type narrowing')
      // Reason carries step id + action + raw error message — that's the log line.
      expect(out.reason).toContain('step:5:continue:oops')
    })

    it('(b) advances to step[i+1] — outcome is "continue" (executor must dispatch next)', () => {
      const step = makeStep('continue', 5)
      const out = applyFailurePolicy(step, new Error('oops'), makeCtx())
      // The policy's contract is "continue" — the step-graph-executor test
      // separately verifies that the executor actually advances; here we
      // verify the routing primitive itself signals advance, not abort.
      expect(out.action).toBe('continue')
      expect(out.action).not.toBe('abort')
    })

    it('(c) sets partial=true on the outcome', () => {
      const step = makeStep('continue', 5)
      const out = applyFailurePolicy(step, new Error('oops'), makeCtx())
      if (out.action !== 'continue') throw new Error('type narrowing')
      expect(out.partial).toBe(true)
    })

    it('(d) failed_step_id surfaces so executor can SKIP outputs validation', () => {
      const step = makeStep('continue', 5)
      const out = applyFailurePolicy(step, new Error('oops'), makeCtx())
      if (out.action !== 'continue') throw new Error('type narrowing')
      // The executor uses failed_step_id to skip outputs validation; the
      // routing primitive surfaces it explicitly.
      expect(out.failed_step_id).toBe(5)
    })

    it('(e) Workflow does NOT abort — outcome is never abort/rollback/escalate/pause for continue policy', () => {
      const step = makeStep('continue', 5)
      const out = applyFailurePolicy(step, new Error('oops'), makeCtx())
      expect(out.action).not.toBe('abort')
      expect(out.action).not.toBe('rollback')
      expect(out.action).not.toBe('escalate')
      expect(out.action).not.toBe('pause')
    })
  })

  // -------- input validation --------

  it('rejects non-step input', () => {
    // @ts-expect-error — defensive runtime guard
    expect(() => applyFailurePolicy(null, new Error('e'), makeCtx())).toThrow(TypeError)
  })

  it('rejects non-Error', () => {
    const step = makeStep('abort')
    // @ts-expect-error — defensive runtime guard
    expect(() => applyFailurePolicy(step, 'oops', makeCtx())).toThrow(TypeError)
  })

  it('rejects unknown on_failure value (defensive)', () => {
    const step = { ...makeStep('abort'), on_failure: 'frobnicate' as unknown as StepFailureAction }
    expect(() => applyFailurePolicy(step, new Error('e'), makeCtx())).toThrow(/unknown on_failure/)
  })
})
