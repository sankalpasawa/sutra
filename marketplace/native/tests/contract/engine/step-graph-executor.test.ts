/**
 * step-graph-executor contract tests — M5 Group K (T-049, T-051).
 *
 * Asserts:
 *  - Happy path: ordered dispatch, success state, no partial flag
 *  - Failure routing: each of the 5 on_failure policies (abort, rollback,
 *    pause, escalate, continue)
 *  - `continue` end-to-end: workflow proceeds past the failed step
 *  - terminalCheck integration (T-051): violations → 'forbidden_coupling:F-N,F-M'
 *    sorted ASCII, comma-joined, no spaces
 *  - Child workflow invocation (V2.3 §A11)
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-049 + T-051
 */

import { describe, it, expect } from 'vitest'
import { createWorkflow, type Workflow } from '../../../src/primitives/workflow.js'
import {
  executeStepGraph,
  formatTerminalCheckFailureReason,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../../src/engine/step-graph-executor.js'
import type { ForbiddenCouplingId } from '../../../src/laws/l4-terminal-check.js'

function wf(stepFailureActions: ('rollback' | 'escalate' | 'pause' | 'abort' | 'continue')[]): Workflow {
  return createWorkflow({
    id: 'W-exec-test',
    preconditions: '',
    step_graph: stepFailureActions.map((on_failure, i) => ({
      step_id: i + 1,
      skill_ref: `skill.${i}`,
      inputs: [],
      outputs: [],
      on_failure,
    })),
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

describe('executeStepGraph — happy path', () => {
  it('dispatches every step in order and returns success', async () => {
    const w = wf(['abort', 'abort', 'abort'])
    const visits: number[] = []
    const dispatch: ActivityDispatcher = (descriptor) => {
      visits.push(descriptor.step_id)
      return { kind: 'ok', outputs: [`step-${descriptor.step_id}-result`] }
    }
    const result = await executeStepGraph(w, dispatch)
    expect(visits).toEqual([1, 2, 3])
    expect(result.workflow_id).toBe(w.id)
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    // Codex P1.1 — completed_step_ids is the success-only subset; on the
    // happy path it equals visited_step_ids.
    expect(result.completed_step_ids).toEqual([1, 2, 3])
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.partial).toBe(false)
    expect(result.step_outputs).toHaveLength(3)
    expect(result.step_outputs.map((s) => s.outputs[0])).toEqual([
      'step-1-result',
      'step-2-result',
      'step-3-result',
    ])
    expect(result.step_outputs.every((s) => s.output_validation_skipped === false)).toBe(true)
  })
})

describe('executeStepGraph — per-step failure policies', () => {
  it('abort: terminates immediately on failed step', async () => {
    const w = wf(['abort', 'abort'])
    const dispatch: ActivityDispatcher = (descriptor) =>
      descriptor.step_id === 1
        ? { kind: 'failure', error: new Error('s1-bad') }
        : { kind: 'ok', outputs: [] }
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('step:1:abort:s1-bad')
    expect(result.visited_step_ids).toEqual([1]) // step 2 never dispatched
    expect(result.partial).toBe(false)
  })

  it('rollback: emits compensation_order in reverse', async () => {
    const w = wf(['abort', 'rollback'])
    const dispatch: ActivityDispatcher = (descriptor) =>
      descriptor.step_id === 1
        ? { kind: 'ok', outputs: [] }
        : { kind: 'failure', error: new Error('s2-bad') }
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('failed')
    expect(result.rollback_compensations).toEqual([1])
    expect(result.failure_reason).toContain('step:2:rollback:s2-bad')
    // Codex P1.1 — failed step 2 is in visited but NOT completed.
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.completed_step_ids).toEqual([1])
  })

  it('pause: emits paused state + resume_token', async () => {
    const w = wf(['pause'])
    const dispatch: ActivityDispatcher = () => ({ kind: 'failure', error: new Error('halt') })
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('paused')
    expect(result.resume_token).toMatch(/^resume:1:[0-9a-f]+$/)
    expect(result.failure_reason).toContain('pause')
  })

  it('escalate: emits escalated state + target', async () => {
    const w = wf(['escalate'])
    const dispatch: ActivityDispatcher = () => ({ kind: 'failure', error: new Error('hot') })
    const result = await executeStepGraph(w, dispatch, { escalation_target: 'meta-charter' })
    expect(result.state).toBe('escalated')
    expect(result.escalation_target).toBe('meta-charter')
    expect(result.failure_reason).toContain('escalate')
  })

  it('continue then rollback: rollback compensates only successfully-completed steps (codex P1.1 master fix)', async () => {
    // M5 ship-blocker fix from codex master review 2026-04-29:
    //   step1 — succeeds → completed
    //   step2 — fails with on_failure='continue' → visited but NOT completed
    //   step3 — fails with on_failure='rollback' → triggers rollback
    // Expected: rollback compensation_order reverses ONLY [step1] (NOT [step1,step2]).
    //          step2 appears in visited_step_ids but NOT in completed_step_ids
    //          and NOT in rollback_compensations.
    const w = wf(['abort', 'continue', 'rollback'])
    const dispatch: ActivityDispatcher = (descriptor) => {
      if (descriptor.step_id === 1) return { kind: 'ok', outputs: ['s1'] }
      if (descriptor.step_id === 2) return { kind: 'failure', error: new Error('s2-soft-fail') }
      return { kind: 'failure', error: new Error('s3-rollback') }
    }
    const result = await executeStepGraph(w, dispatch)

    // Workflow ended in rollback failure
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('step:3:rollback:s3-rollback')

    // Trace records all 3 steps as visited (incl. failed-continue step 2)
    expect(result.visited_step_ids).toEqual([1, 2, 3])

    // ONLY step 1 produced successful effects → only step 1 is completed
    expect(result.completed_step_ids).toEqual([1])

    // Compensation_order reverses completed (success-only), NOT visited.
    // Pre-fix this would be [2, 1] — wrong, would compensate a step that
    // never produced effects. Post-fix: [1] only.
    expect(result.rollback_compensations).toEqual([1])

    // partial flag stays true (continue fired in step 2)
    expect(result.partial).toBe(true)
  })

  it('continue (codex P1.3 5 assertions): partial=true, advances past failure, skips outputs', async () => {
    const w = wf(['continue', 'abort', 'abort'])
    const visits: number[] = []
    const dispatch: ActivityDispatcher = (descriptor) => {
      visits.push(descriptor.step_id)
      return descriptor.step_id === 1
        ? { kind: 'failure', error: new Error('s1-soft') }
        : { kind: 'ok', outputs: [`step-${descriptor.step_id}`] }
    }
    const result = await executeStepGraph(w, dispatch)

    // (a) failed step logged with reason — step 1's outputs entry has skipped flag
    const failedEntry = result.step_outputs.find((s) => s.step_id === 1)
    expect(failedEntry?.output_validation_skipped).toBe(true)
    expect(failedEntry?.outputs).toEqual([])

    // (b) step[i+1] dispatched — visits records step 2 + step 3 after failure
    expect(visits).toEqual([1, 2, 3])

    // (c) partial=true on the result
    expect(result.partial).toBe(true)

    // (d) outputs validation skipped (asserted via output_validation_skipped above)

    // (e) Workflow does NOT abort — final state is success
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()

    // visited_step_ids includes the failed step + subsequent
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    // Codex P1.1 — failed-continue step 1 is in visited but NOT completed.
    // step 2 + step 3 succeed → both completed.
    expect(result.completed_step_ids).toEqual([2, 3])
  })
})

describe('executeStepGraph — terminalCheck integration (T-051)', () => {
  it('violations → failure_reason = "forbidden_coupling:F-N,F-M" sorted ASCII, no spaces', async () => {
    const w = wf(['abort', 'abort'])
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })
    const result = await executeStepGraph(w, dispatch, {
      // F-7 + F-3 violations → sorted ASCII = ['F-3', 'F-7']
      terminalCheckProbe: () => ['F-7', 'F-3'] as ForbiddenCouplingId[],
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe('forbidden_coupling:F-3,F-7')
  })

  it('no terminalCheck violations → success, failure_reason=null', async () => {
    const w = wf(['abort'])
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })
    const result = await executeStepGraph(w, dispatch, { terminalCheckProbe: () => [] })
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
  })

  it('formatTerminalCheckFailureReason: empty list → null', () => {
    expect(formatTerminalCheckFailureReason([])).toBeNull()
  })

  it('formatTerminalCheckFailureReason: 1 violation → "forbidden_coupling:F-2"', () => {
    expect(formatTerminalCheckFailureReason(['F-2'])).toBe('forbidden_coupling:F-2')
  })

  it('formatTerminalCheckFailureReason: ASCII sort puts F-10 between F-1 and F-2 (string sort)', () => {
    // ASCII: '1' < '2', and 'F-10' < 'F-2' as strings (1 < 2 at index 2),
    // so ASCII-sorted order is F-1, F-10, F-2.
    const out = formatTerminalCheckFailureReason(['F-2', 'F-1', 'F-10'])
    expect(out).toBe('forbidden_coupling:F-1,F-10,F-2')
  })

  it('terminalCheckProbe NOT called when a step fails with abort policy', async () => {
    const w = wf(['abort'])
    let probeCalls = 0
    const dispatch: ActivityDispatcher = () => ({ kind: 'failure', error: new Error('abort-now') })
    const result = await executeStepGraph(w, dispatch, {
      terminalCheckProbe: () => {
        probeCalls++
        return ['F-3'] as ForbiddenCouplingId[]
      },
    })
    expect(result.state).toBe('failed')
    expect(probeCalls).toBe(0) // step failed first → terminate stage never reached
    // Failure reason comes from failure-policy, not terminalCheck.
    expect(result.failure_reason).toContain('step:1:abort')
  })
})

describe('executeStepGraph — child Workflow invocation (V2.3 §A11)', () => {
  it('action="spawn_sub_unit" with child_result outputs propagates child id', async () => {
    const w = createWorkflow({
      id: 'W-parent',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 's.a', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'spawn_sub_unit', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = (descriptor): StepDispatchResult => {
      if (descriptor.action === 'spawn_sub_unit') {
        return { kind: 'child_result', child_workflow_id: 'W-child', outputs: ['child-out'] }
      }
      return { kind: 'ok', outputs: [] }
    }
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('success')
    expect(result.child_workflows).toEqual([{ step_id: 2, child_workflow_id: 'W-child' }])
    expect(result.step_outputs[1]?.outputs).toEqual(['child-out'])
  })
})

describe('executeStepGraph — terminate action (T-051 anchor)', () => {
  it('action="terminate" stops dispatch + runs terminalCheck probe', async () => {
    const w = createWorkflow({
      id: 'W-term',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 's.a', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 3, skill_ref: 's.never', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const visits: number[] = []
    const dispatch: ActivityDispatcher = (d) => {
      visits.push(d.step_id)
      return { kind: 'ok', outputs: [] }
    }
    const result = await executeStepGraph(w, dispatch, {
      terminalCheckProbe: () => [],
    })
    expect(visits).toEqual([1]) // step 2 (terminate) NOT dispatched, step 3 not reached
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.state).toBe('success')
  })
})

describe('executeStepGraph — input validation', () => {
  it('rejects non-Workflow input', async () => {
    // @ts-expect-error — defensive runtime guard
    await expect(executeStepGraph(null, () => ({ kind: 'ok', outputs: [] }))).rejects.toThrow(TypeError)
  })

  it('rejects non-function dispatch', async () => {
    const w = wf(['abort'])
    // @ts-expect-error — defensive runtime guard
    await expect(executeStepGraph(w, 'not-a-fn')).rejects.toThrow(TypeError)
  })

  it('rejects empty step_graph', async () => {
    const w = wf(['abort'])
    const broken = { ...w, step_graph: [] } as Workflow
    await expect(executeStepGraph(broken, () => ({ kind: 'ok', outputs: [] }))).rejects.toThrow(/step_graph/)
  })
})
