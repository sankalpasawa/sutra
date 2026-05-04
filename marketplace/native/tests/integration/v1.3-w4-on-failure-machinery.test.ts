/**
 * v1.3.0 Wave 4 — on_failure machinery integration tests.
 *
 * Codex W4 advisory folds covered:
 *   #1 — compensate_action lives on WorkflowStep (step-local), reverse-walked
 *        for rollback.
 *   #2 — best-effort rollback semantics with distinct events
 *        (rollback_started / step_compensated / step_compensation_failed /
 *        rollback_complete / rollback_partial).
 *   #3 — pause/escalate/rollback mutually exclusive; resumeFromPause rejects
 *        runs already escalated or with a non-terminal approval.
 *
 * Coverage matrix:
 *   1. on_failure='pause' fails → status='paused', step_paused emitted, pause
 *      record persisted with status='pending'.
 *   2. resumeFromPause continues from step_index+1 (failed step is NOT
 *      re-run; pause semantics).
 *   3. on_failure='rollback' fails → reverse-walk emits step_compensated for
 *      steps with compensate_action; emits workflow_rollback_complete when
 *      all succeed.
 *   4. Mixed compensate failure → workflow_rollback_partial with counts.
 *   5. on_failure='escalate' fails → workflow_escalated event + escalation
 *      record + return failed reason='escalated:...'.
 *   6. Boot-time reload surfaces pending pauses + escalations as
 *      informational logs (DO NOT auto-resume).
 *   7. Mutual exclusion: resumeFromPause throws if execution already escalated.
 *   8. compensate_action validator: invoke_host_llm requires host (mirrors
 *      step.host XOR rule).
 *   9. on_failure='rollback' with no completed compensate_actions → emits
 *      workflow_rollback_complete with steps_compensated=0 (best-effort).
 */

import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { NativeEngine } from '../../src/runtime/native-engine.js'
import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import {
  listPauses,
  loadPause,
  persistPause,
  type ExecutionPauseRecord,
} from '../../src/persistence/execution-pause-ledger.js'
import {
  listEscalations,
  loadEscalation,
  persistEscalation,
  type ExecutionEscalationRecord,
} from '../../src/persistence/execution-escalation-ledger.js'
import type { Workflow } from '../../src/primitives/workflow.js'
import type { EngineEvent } from '../../src/types/engine-event.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a workflow with a step that fails (via invoke_host_llm with a stub
 * dispatcher that throws). on_failure on the failing step is parameterized.
 *
 * - step 1: wait (succeeds)
 * - step 2: invoke_host_llm (FAILS via stub)
 * - step 3: wait (only reached on 'continue')
 *
 * step 1 has compensate_action when withCompensate=true.
 */
function buildFailingWorkflow(opts: {
  on_failure: 'pause' | 'rollback' | 'escalate' | 'continue' | 'abort'
  withCompensate?: boolean
  step1CompensateFails?: boolean
  id?: string
}): Workflow {
  const wfId = opts.id ?? 'W-w4-test'
  const step1: Parameters<typeof createWorkflow>[0]['step_graph'][number] = {
    step_id: 1,
    action: 'wait',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  if (opts.withCompensate) {
    if (opts.step1CompensateFails) {
      // Mark step 1 with an invoke_host_llm compensate that will fail (stub
      // dispatch returns rejection). Use action='invoke_host_llm' with a
      // distinct prompt so the test stub can recognize + reject it.
      step1.compensate_action = {
        action: 'invoke_host_llm',
        host: 'claude',
        inputs: [
          {
            kind: 'prompt',
            schema_ref: '',
            locator: '__compensate_should_fail__',
            version: '1',
            mutability: 'immutable',
            retention: 'ephemeral',
          },
        ],
      }
    } else {
      step1.compensate_action = {
        action: 'wait',
        inputs: [],
      }
    }
  }
  return createWorkflow({
    id: wfId,
    preconditions: '',
    step_graph: [
      step1,
      {
        step_id: 2,
        action: 'invoke_host_llm',
        host: 'claude',
        inputs: [
          {
            kind: 'prompt',
            schema_ref: '',
            locator: '__step2_should_fail__',
            version: '1',
            mutability: 'immutable',
            retention: 'ephemeral',
          },
        ],
        outputs: [],
        on_failure: opts.on_failure,
      },
      {
        step_id: 3,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: '',
    stringency: 'task',
    interfaces_with: [],
  })
}

/** Stub host-LLM dispatcher: rejects step 2 + compensate-fail prompts; succeeds otherwise. */
function makeStubDispatch() {
  return async (args: { prompt: string; host: 'claude' | 'codex'; workflow_run_seq: number; timeout_ms?: number }) => {
    if (args.prompt === '__step2_should_fail__' || args.prompt === '__compensate_should_fail__') {
      throw new Error(`stub_failure:${args.prompt}`)
    }
    return {
      stdout: 'ok',
      stderr: '',
      exit_code: 0,
      host: args.host,
      duration_ms: 1,
      invocation_id: `inv-${args.workflow_run_seq}`,
    }
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('v1.3.0 W4 — on_failure machinery', () => {
  let HOME: string

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-w4-on-failure-'))
  })
  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  // -------------------------------------------------------------------------
  // SCENARIO 1 — on_failure='pause' fails → status='paused', step_paused emitted
  // -------------------------------------------------------------------------
  it('on_failure=pause: failing step → status=paused, step_paused emitted, pause record persisted', async () => {
    const wf = buildFailingWorkflow({ on_failure: 'pause' })
    const events: EngineEvent[] = []
    const pauseRecs: ExecutionPauseRecord[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-pause-1',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
      pause_persist: (rec) => {
        pauseRecs.push(rec)
        persistPause(rec, { home: HOME })
      },
    })

    expect(result.status).toBe('paused')
    expect(result.steps_completed).toBe(1)
    expect(result.steps_failed).toBe(1)
    expect(result.paused_step_index).toBe(2)

    const types = events.map((e) => e.type)
    expect(types).toContain('step_paused')
    expect(types).not.toContain('workflow_completed')
    expect(types).not.toContain('workflow_failed')

    expect(pauseRecs).toHaveLength(1)
    expect(pauseRecs[0].status).toBe('pending')
    expect(pauseRecs[0].step_index).toBe(2)

    const onDisk = loadPause('E-w4-pause-1', { home: HOME })
    expect(onDisk).not.toBeNull()
    expect(onDisk?.status).toBe('pending')
  })

  // -------------------------------------------------------------------------
  // SCENARIO 2 — resumeFromPause continues from step_index+1
  // -------------------------------------------------------------------------
  it('resumeFromPause continues from step_index+1 (failed step is NOT re-run)', async () => {
    const wf = buildFailingWorkflow({ on_failure: 'pause' })
    const events: EngineEvent[] = []
    const engine = new NativeEngine({
      triggers: [
        {
          id: 'T-w4-pause',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do pausable thing' },
          target_workflow: wf.id,
        },
      ],
      workflows: [wf],
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
    })
    for (const t of engine.renderer.getRegisteredTypes()) {
      engine.renderer.register(t as never, ((e: EngineEvent) => {
        events.push(e)
        return ''
      }) as never)
    }
    // Inject failing host-llm dispatcher into the engine path.
    // NativeEngine doesn't expose dispatch override, so we invoke ingest +
    // override the global lite-executor dispatch via the test's perspective:
    // since NativeEngine uses default hostLLMActivity, we call executeWorkflow
    // directly to exercise the resume path without spinning real host CLI.
    //
    // Phase A: execute workflow with stub dispatch (pause), persist pause via engine wiring
    await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-resume-1',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
      pause_persist: (rec) => persistPause(rec, { home: HOME }),
    })
    expect(listPauses({ home: HOME }, 'pending')).toHaveLength(1)

    // Phase B: resumeFromPause via NativeEngine — uses real dispatch (won't be
    // called since step 2 is skipped; only step 3 = 'wait' runs).
    events.length = 0
    const emitted = await engine.resumeFromPause('E-w4-resume-1')
    expect(emitted).toBeGreaterThan(0)

    const types = events.map((e) => e.type)
    // step 2 is skipped; step 3 should run + complete.
    expect(types).toContain('step_started')
    expect(types).toContain('step_completed')
    expect(types).toContain('workflow_completed')
    // step_paused / step_started for step 2 must NOT appear in resumed run.
    const stepStarted = events.filter((e) => e.type === 'step_started') as Array<{ step_index: number }>
    expect(stepStarted.every((e) => e.step_index === 3)).toBe(true)

    // Ledger transitioned pending → resumed.
    expect(listPauses({ home: HOME }, 'pending')).toHaveLength(0)
    expect(listPauses({ home: HOME }, 'resumed')).toHaveLength(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 3 — on_failure='rollback' all compensations succeed → rollback_complete
  // -------------------------------------------------------------------------
  it('on_failure=rollback: reverse-walks completed steps with compensate_action; emits rollback_complete', async () => {
    const wf = buildFailingWorkflow({ on_failure: 'rollback', withCompensate: true })
    const events: EngineEvent[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-rollback-1',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
    })

    expect(result.status).toBe('failed')
    expect(result.reason).toMatch(/^rollback_complete:/)

    const types = events.map((e) => e.type)
    expect(types).toContain('workflow_rollback_started')
    expect(types).toContain('step_compensated')
    expect(types).toContain('workflow_rollback_complete')
    expect(types).not.toContain('workflow_rollback_partial')

    const compensated = events.find((e) => e.type === 'step_compensated')
    expect(compensated).toBeDefined()
    if (compensated?.type !== 'step_compensated') throw new Error('narrow')
    expect(compensated.step_index).toBe(1) // step 1 had compensate_action

    const completeEvt = events.find((e) => e.type === 'workflow_rollback_complete')
    if (completeEvt?.type !== 'workflow_rollback_complete') throw new Error('narrow')
    expect(completeEvt.steps_compensated).toBe(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 4 — Mixed compensate failure → workflow_rollback_partial
  // -------------------------------------------------------------------------
  it('on_failure=rollback: compensate_action throws → workflow_rollback_partial with counts', async () => {
    const wf = buildFailingWorkflow({
      on_failure: 'rollback',
      withCompensate: true,
      step1CompensateFails: true,
    })
    const events: EngineEvent[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-partial-1',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
    })

    expect(result.status).toBe('failed')
    expect(result.reason).toMatch(/^rollback_partial:/)

    const types = events.map((e) => e.type)
    expect(types).toContain('workflow_rollback_started')
    expect(types).toContain('step_compensation_failed')
    expect(types).toContain('workflow_rollback_partial')
    expect(types).not.toContain('workflow_rollback_complete')

    const partial = events.find((e) => e.type === 'workflow_rollback_partial')
    if (partial?.type !== 'workflow_rollback_partial') throw new Error('narrow')
    expect(partial.steps_compensated).toBe(0)
    expect(partial.steps_failed).toBe(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 5 — on_failure='escalate' fails → workflow_escalated + record
  // -------------------------------------------------------------------------
  it('on_failure=escalate: failing step → workflow_escalated, escalation record persisted, status=failed', async () => {
    const wf = buildFailingWorkflow({ on_failure: 'escalate' })
    const events: EngineEvent[] = []
    const escRecs: ExecutionEscalationRecord[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-esc-1',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
      escalation_persist: (rec) => {
        escRecs.push(rec)
        persistEscalation(rec, { home: HOME })
      },
    })

    expect(result.status).toBe('failed')
    expect(result.reason).toMatch(/^escalated:/)

    const types = events.map((e) => e.type)
    expect(types).toContain('workflow_escalated')
    expect(types).toContain('workflow_failed')

    expect(escRecs).toHaveLength(1)
    expect(escRecs[0].step_index).toBe(2)

    const onDisk = loadEscalation('E-w4-esc-1', { home: HOME })
    expect(onDisk).not.toBeNull()
    expect(onDisk?.step_index).toBe(2)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 6 — Boot-time reload surfaces pending pauses + escalations
  // -------------------------------------------------------------------------
  it('boot-time reload: NativeEngine constructor surfaces pending pauses + escalations as informational logs', () => {
    // Pre-populate the runtime ledger directories.
    persistPause(
      {
        execution_id: 'E-w4-boot-1',
        workflow_id: 'W-w4-test',
        step_index: 2,
        status: 'pending',
        reason: 'preserved across restart',
        created_at_ms: 1_700_000_000_000,
      },
      { home: HOME },
    )
    persistEscalation(
      {
        execution_id: 'E-w4-boot-2',
        workflow_id: 'W-w4-test',
        step_index: 3,
        reason: 'pre-existing escalation',
        created_at_ms: 1_700_000_000_000,
      },
      { home: HOME },
    )

    // Boot a NativeEngine with home=HOME; collect onError messages.
    const errors: string[] = []
    new NativeEngine({
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
      on_error: (err) => errors.push(err.message),
    })

    const pauseLog = errors.find((m) => m.includes('pending pause'))
    const escLog = errors.find((m) => m.includes('escalation'))
    expect(pauseLog).toBeDefined()
    expect(pauseLog).toContain('E-w4-boot-1')
    expect(escLog).toBeDefined()
    expect(escLog).toContain('E-w4-boot-2')
  })

  // -------------------------------------------------------------------------
  // SCENARIO 7 — Mutual exclusion: resumeFromPause throws if escalated
  // -------------------------------------------------------------------------
  it('mutual exclusion: resumeFromPause rejects execution that has an escalation record', async () => {
    persistPause(
      {
        execution_id: 'E-w4-mutex-1',
        workflow_id: 'W-w4-test',
        step_index: 2,
        status: 'pending',
        reason: 'paused',
        created_at_ms: 1_700_000_000_000,
      },
      { home: HOME },
    )
    persistEscalation(
      {
        execution_id: 'E-w4-mutex-1',
        workflow_id: 'W-w4-test',
        step_index: 2,
        reason: 'also escalated',
        created_at_ms: 1_700_000_000_000,
      },
      { home: HOME },
    )

    const engine = new NativeEngine({
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
      on_error: () => {},
    })

    await expect(engine.resumeFromPause('E-w4-mutex-1')).rejects.toThrow(/already escalated/)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 8 — compensate_action validator: invoke_host_llm requires host
  // -------------------------------------------------------------------------
  it('validator: compensate_action.action=invoke_host_llm requires host', () => {
    expect(() => {
      createWorkflow({
        id: 'W-w4-bad',
        preconditions: '',
        step_graph: [
          {
            step_id: 1,
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
            compensate_action: {
              // host is missing — should throw
              action: 'invoke_host_llm',
              inputs: [],
            },
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: '',
        failure_policy: '',
        stringency: 'task',
        interfaces_with: [],
      })
    }).toThrow(/compensate_action\.host is required/)
  })

  it('validator: compensate_action.host forbidden unless action=invoke_host_llm', () => {
    expect(() => {
      createWorkflow({
        id: 'W-w4-bad-2',
        preconditions: '',
        step_graph: [
          {
            step_id: 1,
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
            compensate_action: {
              action: 'wait',
              host: 'claude', // forbidden when action=wait
              inputs: [],
            },
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: '',
        failure_policy: '',
        stringency: 'task',
        interfaces_with: [],
      })
    }).toThrow(/compensate_action\.host is forbidden/)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 9 — rollback path with no compensate_actions → complete with 0
  // -------------------------------------------------------------------------
  it('on_failure=rollback: no completed steps with compensate_action → workflow_rollback_complete with steps_compensated=0', async () => {
    const wf = buildFailingWorkflow({ on_failure: 'rollback', withCompensate: false })
    const events: EngineEvent[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w4-empty-rollback',
      host_llm_dispatch: makeStubDispatch(),
      emit: (e) => events.push(e),
    })

    expect(result.status).toBe('failed')
    expect(result.reason).toMatch(/^rollback_complete:/)

    const types = events.map((e) => e.type)
    expect(types).toContain('workflow_rollback_started')
    expect(types).toContain('workflow_rollback_complete')
    // No step_compensated since no compensate_action defined.
    expect(types).not.toContain('step_compensated')
    expect(types).not.toContain('step_compensation_failed')
    expect(types).not.toContain('workflow_rollback_partial')

    const completeEvt = events.find((e) => e.type === 'workflow_rollback_complete')
    if (completeEvt?.type !== 'workflow_rollback_complete') throw new Error('narrow')
    expect(completeEvt.steps_compensated).toBe(0)
  })
})
