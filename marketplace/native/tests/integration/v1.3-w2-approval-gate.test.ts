/**
 * v1.3.0 Wave 2 — step-level approval gate primitive integration tests.
 *
 * Founder centerpiece: "workflow is shown, then approval from founder, like
 * how evolved that workflow should be from the steps point of view."
 *
 * Coverage matrix (codex W2 advisory F fold):
 *   1. Workflow with step.requires_approval=true → executeWorkflow returns
 *      status='paused', emits approval_requested, persists pending record.
 *   2. Approve E-<id> → status approved → resumeFromStep continues remaining
 *      steps → workflow_completed.
 *   3. Reject E-<id> "reason text" → status rejected → workflow_failed
 *      approval_denied.
 *   4. Duplicate approve → second approve emits approval_already_handled with
 *      original decided_at_ms.
 *   5. Stale approve after fresh engine boot: kill engine after pause, fresh
 *      `new NativeEngine()` reloads pending approval, founder approves,
 *      resume works.
 *   6. Both lite path (direct executeWorkflow) and routed path
 *      (NativeEngine.handleHSutraEvent with utterance) — same scenarios.
 *   7. WorkflowStep validator: requires_approval='not-boolean' rejected at
 *      createWorkflow.
 *   8. parseApprovalUtterance unit tests: P vs E namespace, approve vs
 *      reject, with/without reason.
 */

import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { NativeEngine, parseApprovalUtterance } from '../../src/runtime/native-engine.js'
import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import { listApprovals, loadApproval, persistApproval } from '../../src/persistence/execution-approval-ledger.js'
import type { Workflow } from '../../src/primitives/workflow.js'
import type { HSutraEvent } from '../../src/types/h-sutra-event.js'
import type { EngineEvent } from '../../src/types/engine-event.js'
import type { ExecutionApprovalRecord } from '../../src/persistence/execution-approval-ledger.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a 3-step Workflow where step 2 has requires_approval=true. */
function buildGatedWorkflow(id = 'W-w2-test'): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
      {
        step_id: 2,
        action: 'wait',
        inputs: [
          {
            kind: 'config',
            schema_ref: '',
            locator: 'review-this-step',
            version: '1',
            mutability: 'immutable',
            retention: 'ephemeral',
          },
        ],
        outputs: [],
        on_failure: 'abort',
        requires_approval: true,
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

function makeEvent(turn_id: string, input_text: string): HSutraEvent {
  return { turn_id, input_text, cell: 'DIRECT·INBOUND' }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('v1.3.0 W2 — step-level approval gate primitive', () => {
  let HOME: string

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-w2-approval-'))
  })
  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  // -------------------------------------------------------------------------
  // SCENARIO 1 — direct lite-path: pause + persist + emit
  // -------------------------------------------------------------------------
  it('lite path: requires_approval=true → status="paused", approval_requested emitted, pending record persisted', async () => {
    const wf = buildGatedWorkflow()
    const events: EngineEvent[] = []
    const persistedRecords: ExecutionApprovalRecord[] = []

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-test-1',
      emit: (e) => events.push(e),
      approval_persist: (rec) => {
        persistedRecords.push(rec)
        persistApproval(rec, { home: HOME })
      },
    })

    // Result shape
    expect(result.status).toBe('paused')
    expect(result.steps_completed).toBe(1) // step 1 ran; step 2 paused
    expect(result.paused_step_index).toBe(2)

    // Events: workflow_started, step_started(1), step_completed(1), approval_requested
    const types = events.map((e) => e.type)
    expect(types).toContain('workflow_started')
    expect(types).toContain('approval_requested')
    expect(types).not.toContain('workflow_completed') // paused, not completed
    expect(types).not.toContain('workflow_failed')

    const approvalEvt = events.find((e) => e.type === 'approval_requested')
    expect(approvalEvt).toBeDefined()
    if (approvalEvt?.type !== 'approval_requested') throw new Error('type narrow')
    expect(approvalEvt.execution_id).toBe('E-test-1')
    expect(approvalEvt.workflow_id).toBe('W-w2-test')
    expect(approvalEvt.step_index).toBe(2)
    expect(approvalEvt.prompt_summary).toContain('review-this-step')

    // Persisted record
    expect(persistedRecords).toHaveLength(1)
    expect(persistedRecords[0].status).toBe('pending')

    const onDisk = loadApproval('E-test-1', { home: HOME })
    expect(onDisk).not.toBeNull()
    expect(onDisk?.status).toBe('pending')
    expect(onDisk?.step_index).toBe(2)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 2 — routed path: approve E-<id> → resume → workflow_completed
  // -------------------------------------------------------------------------
  it('routed path: approve E-<id> → ledger approved → resume runs remaining steps → workflow_completed', async () => {
    const wf = buildGatedWorkflow()
    const events: EngineEvent[] = []

    // Build NativeEngine with an empty starter and ONLY our gated workflow.
    // We register a synthetic trigger that matches "do gated thing" so the
    // engine routes to this workflow on the test utterance.
    const engine = new NativeEngine({
      triggers: [
        {
          id: 'T-gated-test',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do gated thing' },
          target_workflow: wf.id,
        },
      ],
      workflows: [wf],
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
      now_ms: () => 1_700_000_000_000,
    })
    // Capture all events.
    for (const t of engine.renderer.getRegisteredTypes()) {
      engine.renderer.register(t as never, ((e: EngineEvent) => {
        events.push(e)
        return ''
      }) as never)
    }

    // First utterance — routes to W-w2-test, runs through step 1, pauses at step 2.
    const evt1 = makeEvent('t1', 'do gated thing')
    await engine.ingest(evt1)
    expect(events.find((e) => e.type === 'approval_requested')).toBeDefined()
    expect(events.find((e) => e.type === 'workflow_completed')).toBeUndefined()
    const pending = listApprovals({ home: HOME }, 'pending')
    expect(pending).toHaveLength(1)
    const execId = pending[0].execution_id

    // Founder approves via next utterance
    events.length = 0
    const evt2 = makeEvent('t2', `approve ${execId}`)
    await engine.ingest(evt2)

    // Should emit approval_granted + step_started(2) + step_completed(2) +
    // step_started(3) + step_completed(3) + workflow_completed.
    const types = events.map((e) => e.type)
    expect(types).toContain('approval_granted')
    expect(types).toContain('workflow_completed')

    // Ledger transitioned approved → resumed
    expect(listApprovals({ home: HOME }, 'pending')).toHaveLength(0)
    expect(listApprovals({ home: HOME }, 'resumed')).toHaveLength(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 3 — routed path: reject E-<id> → workflow_failed
  // -------------------------------------------------------------------------
  it('routed path: reject E-<id> "reason" → ledger rejected → approval_denied + workflow_failed', async () => {
    const wf = buildGatedWorkflow()
    const events: EngineEvent[] = []

    const engine = new NativeEngine({
      triggers: [
        {
          id: 'T-gated-test',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do gated thing' },
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

    await engine.ingest(makeEvent('t1', 'do gated thing'))
    const pending = listApprovals({ home: HOME }, 'pending')
    expect(pending).toHaveLength(1)
    const execId = pending[0].execution_id

    events.length = 0
    await engine.ingest(makeEvent('t2', `reject ${execId} not approved by ops`))

    const denied = events.find((e) => e.type === 'approval_denied')
    expect(denied).toBeDefined()
    if (denied?.type !== 'approval_denied') throw new Error('narrow')
    expect(denied.reason).toBe('not approved by ops')

    const failed = events.find((e) => e.type === 'workflow_failed')
    expect(failed).toBeDefined()
    if (failed?.type !== 'workflow_failed') throw new Error('narrow')
    expect(failed.reason).toContain('approval_denied:not approved by ops')

    expect(listApprovals({ home: HOME }, 'pending')).toHaveLength(0)
    expect(listApprovals({ home: HOME }, 'rejected')).toHaveLength(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 4 — duplicate approve → approval_already_handled
  // -------------------------------------------------------------------------
  it('duplicate approve E-<id> emits approval_already_handled with originally_decided_at_ms', async () => {
    const wf = buildGatedWorkflow()
    const events: EngineEvent[] = []

    const engine = new NativeEngine({
      triggers: [
        {
          id: 'T-gated-test',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do gated thing' },
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

    await engine.ingest(makeEvent('t1', 'do gated thing'))
    const pending = listApprovals({ home: HOME }, 'pending')
    const execId = pending[0].execution_id

    // First approve — succeeds
    await engine.ingest(makeEvent('t2', `approve ${execId}`))
    expect(listApprovals({ home: HOME }, 'resumed')).toHaveLength(1)
    const firstDecidedAt = loadApproval(execId, { home: HOME })?.decided_at_ms

    // Second approve — already-handled
    events.length = 0
    await engine.ingest(makeEvent('t3', `approve ${execId}`))
    const handled = events.find((e) => e.type === 'approval_already_handled')
    expect(handled).toBeDefined()
    if (handled?.type !== 'approval_already_handled') throw new Error('narrow')
    expect(handled.execution_id).toBe(execId)
    expect(handled.originally_decided_at_ms).toBe(firstDecidedAt)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 5 — fresh engine boot reloads pending; approve still works
  // -------------------------------------------------------------------------
  it('boot-time reload: fresh NativeEngine surfaces pending approval; founder can still approve', async () => {
    const wf = buildGatedWorkflow()
    const errors1: Error[] = []

    // Engine 1 — pause at step 2
    const engine1 = new NativeEngine({
      triggers: [
        {
          id: 'T-gated-test',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do gated thing' },
          target_workflow: wf.id,
        },
      ],
      workflows: [wf],
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
      on_error: (e) => errors1.push(e),
    })
    await engine1.ingest(makeEvent('t1', 'do gated thing'))
    const pending = listApprovals({ home: HOME }, 'pending')
    expect(pending).toHaveLength(1)
    const execId = pending[0].execution_id

    // Engine 2 — fresh boot. Constructor should surface the pending approval
    // via onError (informational).
    const errors2: Error[] = []
    const engine2 = new NativeEngine({
      triggers: [
        {
          id: 'T-gated-test',
          event_type: 'founder_input',
          route_predicate: { type: 'contains', value: 'do gated thing' },
          target_workflow: wf.id,
        },
      ],
      workflows: [wf],
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      skip_user_kit: true,
      write: () => {},
      on_error: (e) => errors2.push(e),
    })
    const bootMsg = errors2.find((e) => e.message.includes('pending step approval'))
    expect(bootMsg).toBeDefined()
    expect(bootMsg?.message).toContain(execId)

    // Founder approves on the fresh engine — workflow resumes.
    const events: EngineEvent[] = []
    for (const t of engine2.renderer.getRegisteredTypes()) {
      engine2.renderer.register(t as never, ((e: EngineEvent) => {
        events.push(e)
        return ''
      }) as never)
    }
    await engine2.ingest(makeEvent('t2', `approve ${execId}`))
    expect(events.find((e) => e.type === 'approval_granted')).toBeDefined()
    expect(events.find((e) => e.type === 'workflow_completed')).toBeDefined()
    expect(listApprovals({ home: HOME }, 'resumed')).toHaveLength(1)
  })

  // -------------------------------------------------------------------------
  // SCENARIO 7 — validator: requires_approval='not-boolean' rejected
  // -------------------------------------------------------------------------
  it('createWorkflow rejects step.requires_approval that is not a boolean', () => {
    expect(() =>
      createWorkflow({
        id: 'W-bad',
        preconditions: '',
        step_graph: [
          {
            step_id: 1,
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
            // @ts-expect-error — testing runtime defense
            requires_approval: 'true',
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: '',
        failure_policy: '',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/requires_approval must be a boolean/)
  })

  it('createWorkflow accepts step.requires_approval=true', () => {
    expect(() => buildGatedWorkflow()).not.toThrow()
  })
})

// -----------------------------------------------------------------------------
// SCENARIO 8 — parseApprovalUtterance unit tests
// -----------------------------------------------------------------------------
describe('parseApprovalUtterance — namespace dispatch (codex W2 advisory C)', () => {
  it('parses "approve P-deadbeef" — P namespace, no reason', () => {
    const r = parseApprovalUtterance('approve P-deadbeef')
    expect(r).toEqual({ namespace: 'P', id: 'P-deadbeef', action: 'approve' })
  })

  it('parses "reject P-deadbeef too generic" — P namespace, with reason', () => {
    const r = parseApprovalUtterance('reject P-deadbeef too generic')
    expect(r).toEqual({ namespace: 'P', id: 'P-deadbeef', action: 'reject', reason: 'too generic' })
  })

  it('parses "approve E-t1-1" — E namespace', () => {
    const r = parseApprovalUtterance('approve E-t1-1')
    expect(r).toEqual({ namespace: 'E', id: 'E-t1-1', action: 'approve' })
  })

  it('parses "reject E-foo-bar-7 needs ops review" — E namespace with reason', () => {
    const r = parseApprovalUtterance('reject E-foo-bar-7 needs ops review')
    expect(r).toEqual({
      namespace: 'E',
      id: 'E-foo-bar-7',
      action: 'reject',
      reason: 'needs ops review',
    })
  })

  it('case-insensitive verb', () => {
    expect(parseApprovalUtterance('APPROVE E-x-1')?.action).toBe('approve')
    expect(parseApprovalUtterance('Reject E-x-1')?.action).toBe('reject')
  })

  it('returns null for non-matching input', () => {
    expect(parseApprovalUtterance('hello world')).toBeNull()
    expect(parseApprovalUtterance('approve')).toBeNull()
    expect(parseApprovalUtterance('approve X-foo')).toBeNull() // wrong namespace
    expect(parseApprovalUtterance('')).toBeNull()
  })

  it('returns null for non-string input', () => {
    // @ts-expect-error testing defensive type guard
    expect(parseApprovalUtterance(42)).toBeNull()
    // @ts-expect-error testing defensive type guard
    expect(parseApprovalUtterance(null)).toBeNull()
  })

  it('handles leading/trailing whitespace', () => {
    expect(parseApprovalUtterance('  approve E-x-1  ')).toEqual({
      namespace: 'E',
      id: 'E-x-1',
      action: 'approve',
    })
  })
})
