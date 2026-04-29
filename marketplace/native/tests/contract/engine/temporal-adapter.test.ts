/**
 * TemporalAdapter contract test — M5 Group I (T-041, T-042).
 *
 * Asserts:
 *  - registerWorkflow(sutraWorkflow) returns a TemporalWorkflowDefinition shell
 *  - The mapper produces ONE Temporal workflow that orchestrates the ordered
 *    Sutra step_graph (codex P2.5: NOT 1:1 step→step Temporal workflow).
 *  - Per-step I/O is mapped to Activity references (not workflow code).
 *
 * This test pins the adapter SHAPE; no Temporal worker is started here.
 * Replay-determinism is enforced separately by the F-12 runtime trap.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group I
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

import { describe, it, expect } from 'vitest'
import { registerWorkflow } from '../../../src/engine/temporal-adapter.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import type { Workflow } from '../../../src/primitives/workflow.js'

function makeSutraWorkflow(): Workflow {
  return createWorkflow({
    id: 'W-test-engine-1',
    preconditions: 'pre',
    step_graph: [
      {
        step_id: 1,
        skill_ref: 'skill.alpha',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
      {
        step_id: 2,
        skill_ref: 'skill.beta',
        inputs: [],
        outputs: [],
        on_failure: 'continue',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'post',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

describe('TemporalAdapter — registerWorkflow', () => {
  it('returns a TemporalWorkflowDefinition with a workflow_id derived from Sutra id', () => {
    const sutra = makeSutraWorkflow()
    const def = registerWorkflow(sutra)

    expect(def).toBeDefined()
    expect(def.workflow_id).toBe(sutra.id)
    expect(def.task_queue).toBeTypeOf('string')
    expect(def.task_queue.length).toBeGreaterThan(0)
  })

  it('maps the ordered Sutra step_graph to ONE Temporal workflow (codex P2.5)', () => {
    const sutra = makeSutraWorkflow()
    const def = registerWorkflow(sutra)

    // ONE Temporal workflow function — not one-per-step.
    expect(typeof def.run).toBe('function')

    // Activity descriptors carry the per-step I/O (one entry per Sutra step).
    expect(Array.isArray(def.activities)).toBe(true)
    expect(def.activities.length).toBe(sutra.step_graph.length)
    expect(def.activities.map((a) => a.step_id)).toEqual([1, 2])
    expect(def.activities[0].skill_ref).toBe('skill.alpha')
    expect(def.activities[1].skill_ref).toBe('skill.beta')
  })

  it('preserves step_graph order in the activity descriptors (orchestration shape)', () => {
    const sutra: Workflow = createWorkflow({
      id: 'W-order-test',
      preconditions: 'pre',
      step_graph: [
        { step_id: 10, skill_ref: 's.x', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 20, skill_ref: 's.y', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 30, skill_ref: 's.z', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'post',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const def = registerWorkflow(sutra)
    expect(def.activities.map((a) => a.step_id)).toEqual([10, 20, 30])
  })

  it('rejects a Sutra workflow with an empty step_graph (degenerate orchestration)', () => {
    const sutra: Workflow = {
      ...makeSutraWorkflow(),
      step_graph: [],
    }
    expect(() => registerWorkflow(sutra)).toThrow(/step_graph/)
  })

  it('rejects a non-Workflow input (defensive type guard)', () => {
    // @ts-expect-error — intentional bad input for runtime guard
    expect(() => registerWorkflow(null)).toThrow()
    // @ts-expect-error — intentional bad input for runtime guard
    expect(() => registerWorkflow({ id: 'W-bad' })).toThrow()
  })

  it('run() returns the explicit __shell:true tag (Group J/K must remove)', async () => {
    // Fail-fast shell marker: until the real Temporal-SDK orchestration body
    // is wired up in Group J/K, run() must self-identify as a shell. When the
    // tag is removed, this test fails loudly and forces a contract update —
    // preventing downstream tests from passing against fake "success."
    const sutra = makeSutraWorkflow()
    const def = registerWorkflow(sutra)
    const result = await def.run()
    expect(result.__shell).toBe(true)
    expect(result.workflow_id).toBe(sutra.id)
    expect(result.visited_step_ids).toEqual([1, 2])
  })
})
