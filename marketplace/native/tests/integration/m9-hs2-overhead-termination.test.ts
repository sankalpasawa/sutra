/**
 * M9 Group HH — HS-2 overhead-termination integration test (T-163).
 *
 * Drives governance overhead >25% via a real GovernanceOverhead tracker;
 * runs through executeStepGraph; asserts:
 *   1. Execution.state ends as 'failed'
 *   2. failure_reason='hs2_overhead_exceeded'
 *   3. decision_kind='TERMINATE' provenance emitted with overhead_pct +
 *      threshold + reason fields on attributes
 *   4. Subsequent steps do NOT execute (the dispatcher records each call;
 *      we assert the call count stops at the step where HS-2 fired).
 *
 * Codex M9 pre-dispatch P1.1 fold: HS-2 reuses existing TERMINATE enum +
 * state='failed' + canonical failure_reason. No new enums, no new error
 * class — the test asserts THAT pattern explicitly.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M9-e2e-vinit.md Group HH T-163 (A-4)
 *   - holding/research/2026-04-29-native-d5-invariant-register.md §3 HS-2
 *   - .enforcement/codex-reviews/2026-04-30-m9-pre-dispatch.md P1.1
 */

import { describe, it, expect } from 'vitest'

import { createWorkflow } from '../../src/primitives/workflow.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import { GovernanceOverhead } from '../../src/engine/governance-overhead.js'
import {
  InMemoryOTelExporter,
  OTelEmitter,
} from '../../src/engine/otel-emitter.js'

describe('M9 Group HH — HS-2 overhead-termination at >25%', () => {
  it('overhead ≥25% → state=failed, failure_reason=hs2_overhead_exceeded, TERMINATE provenance emitted', async () => {
    __resetWorkflowRunSeqForTest()

    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-hs2-turn', 1000)
    // Drive overhead to ≥25% via a single track call.
    overhead.track('m9-hs2-turn', 'codex_review', 300) // 300/1000 = 30% → red

    expect(overhead.getThresholdState('m9-hs2-turn')).toBe('red')

    const wf = createWorkflow({
      id: 'W-hs2-overhead',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 3, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    let dispatchCalls = 0
    const dispatch: ActivityDispatcher = (descriptor) => {
      dispatchCalls += 1
      return { kind: 'ok', outputs: [`out-${descriptor.step_id}`] }
    }

    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)

    const result = await executeStepGraph(wf, dispatch, {
      governance_overhead: overhead,
      turn_id: 'm9-hs2-turn',
      otel_emitter: emitter,
    })

    // Canonical I-4 contract: state='failed' ⇒ failure_reason non-null.
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe('hs2_overhead_exceeded')

    // HS-2 fires at the TOP of step 1's iteration (red zone detected
    // before any dispatch); zero dispatcher calls. (If the test wanted
    // HS-2 to fire mid-run, it would track() between steps via a custom
    // dispatcher.)
    expect(dispatchCalls).toBe(0)

    // TERMINATE provenance emitted, carrying overhead_pct + threshold + reason.
    const terminates = exporter.records.filter((r) => r.decision_kind === 'TERMINATE')
    expect(terminates).toHaveLength(1)
    expect(terminates[0]!.workflow_id).toBe('W-hs2-overhead')
    expect(terminates[0]!.attributes.reason).toBe('hs2_overhead_exceeded')
    expect(terminates[0]!.attributes.overhead_pct).toBeCloseTo(0.3, 5)
    expect(terminates[0]!.attributes.threshold).toBe(0.25)

    overhead.endTurn('m9-hs2-turn') // cleanup
  })

  it('mid-run breach: HS-2 fires AFTER step 1 completes, halts before step 2', async () => {
    __resetWorkflowRunSeqForTest()

    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-hs2-mid', 1000)
    // Start in green zone — overhead 0/1000 = 0%.
    expect(overhead.getThresholdState('m9-hs2-mid')).toBe('green')

    const wf = createWorkflow({
      id: 'W-hs2-mid-run',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 3, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    let dispatchCalls = 0
    // Dispatcher pushes overhead into red zone on step 1's call so HS-2
    // fires at the top of step 2's iteration.
    const dispatch: ActivityDispatcher = (descriptor) => {
      dispatchCalls += 1
      if (descriptor.step_id === 1) {
        overhead.track('m9-hs2-mid', 'blueprint', 400) // → 40% red
      }
      return { kind: 'ok', outputs: [`out-${descriptor.step_id}`] }
    }

    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)

    const result = await executeStepGraph(wf, dispatch, {
      governance_overhead: overhead,
      turn_id: 'm9-hs2-mid',
      otel_emitter: emitter,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe('hs2_overhead_exceeded')
    expect(dispatchCalls).toBe(1) // step 1 ran; step 2/3 never started
    expect(result.completed_step_ids).toEqual([1])

    const terminates = exporter.records.filter((r) => r.decision_kind === 'TERMINATE')
    expect(terminates).toHaveLength(1)

    overhead.endTurn('m9-hs2-mid') // cleanup
  })

  it('overhead in green/yellow zone → no HS-2 trigger; workflow completes', async () => {
    __resetWorkflowRunSeqForTest()

    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-hs2-yellow', 1000)
    overhead.track('m9-hs2-yellow', 'input_routing', 200) // 20% yellow

    expect(overhead.getThresholdState('m9-hs2-yellow')).toBe('yellow')

    const wf = createWorkflow({
      id: 'W-hs2-yellow',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [1] })
    const result = await executeStepGraph(wf, dispatch, {
      governance_overhead: overhead,
      turn_id: 'm9-hs2-yellow',
    })

    // Yellow zone → no HS-2; workflow proceeds normally.
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    overhead.endTurn('m9-hs2-yellow') // cleanup
  })
})

describe('M9 codex master P1.2 fold — HS-2 fires on terminal-return paths too', () => {
  it('overhead crosses red on the LAST step → natural-end exit reports hs2_overhead_exceeded (not success)', async () => {
    __resetWorkflowRunSeqForTest()
    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-hs2-end', 1000)
    expect(overhead.getThresholdState('m9-hs2-end')).toBe('green')

    const wf = createWorkflow({
      id: 'W-hs2-end-of-graph',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    // Dispatcher pushes overhead into red zone DURING step 1 (the only
    // step). After step 1 completes, the loop exits — without the codex
    // master P1.2 fold, the executor would return state='success' here.
    // With the fold, the natural-end HS-2 check fires and reports
    // failure_reason='hs2_overhead_exceeded'.
    const dispatch: ActivityDispatcher = () => {
      overhead.track('m9-hs2-end', 'codex_review', 400) // → 40% red
      return { kind: 'ok', outputs: [1] }
    }

    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)

    const result = await executeStepGraph(wf, dispatch, {
      governance_overhead: overhead,
      turn_id: 'm9-hs2-end',
      otel_emitter: emitter,
    })
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe('hs2_overhead_exceeded')
    const terminates = exporter.records.filter((r) => r.decision_kind === 'TERMINATE')
    expect(terminates).toHaveLength(1)
    overhead.endTurn('m9-hs2-end')
  })

  it('overhead crosses red during a failure-policy abort path → HS-2 takes priority over abort reason', async () => {
    __resetWorkflowRunSeqForTest()
    const overhead = new GovernanceOverhead()
    overhead.startTurn('m9-hs2-abort', 1000)
    const wf = createWorkflow({
      id: 'W-hs2-abort-path',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => {
      overhead.track('m9-hs2-abort', 'codex_review', 400)
      return { kind: 'failure', error: new Error('step-fail') }
    }
    const result = await executeStepGraph(wf, dispatch, {
      governance_overhead: overhead,
      turn_id: 'm9-hs2-abort',
    })
    // P1.2 fold: HS-2 priority over the abort reason — the run is failed,
    // and the failure_reason is the HS-2 envelope, NOT the step-fail.
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe('hs2_overhead_exceeded')
    overhead.endTurn('m9-hs2-abort')
  })
})

describe('M9 Group HH — getThresholdState contract', () => {
  it('returns green / yellow / red per band boundaries', () => {
    const o = new GovernanceOverhead()
    o.startTurn('t', 1000)
    expect(o.getThresholdState('t')).toBe('green')
    o.track('t', 'input_routing', 100) // 10%
    expect(o.getThresholdState('t')).toBe('green')
    o.track('t', 'input_routing', 50) // 15% (closed lower bound)
    expect(o.getThresholdState('t')).toBe('yellow')
    o.track('t', 'input_routing', 100) // 25% (closed lower bound)
    expect(o.getThresholdState('t')).toBe('red')
    o.track('t', 'input_routing', 250) // 50%
    expect(o.getThresholdState('t')).toBe('red')
    o.endTurn('t')
  })
})
