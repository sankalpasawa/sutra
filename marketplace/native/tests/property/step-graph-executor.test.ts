/**
 * step-graph-executor — replay-determinism property test (M5 Group K T-049).
 *
 * Property: same Workflow + same deterministic dispatcher ⇒ deep-equal
 * ExecutionResult on every call. ≥1000 cases.
 *
 * The dispatcher is constructed from the input arbitraries — its outcomes are
 * pure functions of (step_id, input_seed) so two back-to-back runs with the
 * same arbitrary instance yield bit-identical state.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-049
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  executeStepGraph,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../src/engine/step-graph-executor.js'
import { workflowArb } from './arbitraries.js'
import type { Workflow } from '../../src/primitives/workflow.js'

const PROP_RUNS = 1000

/**
 * Build a deterministic dispatcher from a per-step outcome plan.
 *
 * `plan[i]` is consumed for step_graph[i]. Falls back to `{kind:'ok',outputs:[]}`
 * when the plan is shorter than the step_graph.
 */
function buildDispatcher(
  plan: ReadonlyArray<'ok' | 'fail'>,
): ActivityDispatcher {
  let i = 0
  return (descriptor): StepDispatchResult => {
    const directive = plan[i++] ?? 'ok'
    if (directive === 'fail') {
      // Error message is a pure function of step_id — replay safe.
      return { kind: 'failure', error: new Error(`step-${descriptor.step_id}-fail`) }
    }
    return { kind: 'ok', outputs: [`out-${descriptor.step_id}`] }
  }
}

describe('step-graph-executor — replay determinism (≥1000 cases)', () => {
  it('two back-to-back runs yield deep-equal ExecutionResult', async () => {
    await fc.assert(
      fc.asyncProperty(
        workflowArb(),
        fc.array(fc.constantFrom<'ok' | 'fail'>('ok', 'fail'), { minLength: 0, maxLength: 5 }),
        async (workflow: Workflow, plan) => {
          // Two independent dispatcher instances — same plan, separate state.
          const d1 = buildDispatcher(plan)
          const d2 = buildDispatcher(plan)

          // Skip workflows with terminate-action steps to keep the replay
          // assertion focused on the dispatch loop; terminate is a control
          // flow concern covered by the contract test.
          if (workflow.step_graph.some((s) => s.action === 'terminate')) {
            return
          }

          const r1 = await executeStepGraph(workflow, d1)
          const r2 = await executeStepGraph(workflow, d2)

          // Deep-equal: every field bit-identical across two runs.
          expect(r2).toEqual(r1)
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })

  it('same workflow + ok-only plan always reaches success', async () => {
    await fc.assert(
      fc.asyncProperty(workflowArb(), async (workflow: Workflow) => {
        if (workflow.step_graph.some((s) => s.action === 'terminate')) return
        const dispatch: ActivityDispatcher = (d) => ({
          kind: 'ok',
          outputs: [`x-${d.step_id}`],
        })
        const r = await executeStepGraph(workflow, dispatch)
        expect(r.state).toBe('success')
        expect(r.failure_reason).toBeNull()
        expect(r.partial).toBe(false)
        // Visited every non-terminate step in order.
        expect(r.visited_step_ids).toEqual(workflow.step_graph.map((s) => s.step_id))
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('terminalCheckProbe with empty violations leaves state=success', async () => {
    await fc.assert(
      fc.asyncProperty(workflowArb(), async (workflow: Workflow) => {
        if (workflow.step_graph.some((s) => s.action === 'terminate')) return
        const r = await executeStepGraph(workflow, () => ({ kind: 'ok', outputs: [] }), {
          terminalCheckProbe: () => [],
        })
        expect(r.state).toBe('success')
        expect(r.failure_reason).toBeNull()
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
