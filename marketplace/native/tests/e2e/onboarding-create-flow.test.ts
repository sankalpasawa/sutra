/**
 * E2E — On-the-fly creation flow.
 *
 * Founder ask 2026-05-03: prove that at runtime a founder can
 *   1. Create a NEW Domain (D6 outside the starter-kit's D1-D5)
 *   2. Create a NEW Charter under that Domain
 *   3. Create a NEW Workflow operationalizing that Charter
 *   4. Hand the Workflow to LiteExecutor and observe events fire
 *
 * If this passes, "create on the fly" is real for v1.1.1 primitives.
 * If it fails, the manifest's "5 Domains, 6 Charters, 10 Workflows" is
 * read-only data, not a runtime kit.
 */

import { describe, it, expect } from 'vitest'
import { createDomain } from '../../src/primitives/domain.js'
import { createCharter } from '../../src/primitives/charter.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import type { EngineEvent } from '../../src/types/engine-event.js'

describe('E2E: on-the-fly creation (Domain → Charter → Workflow → Execution)', () => {
  it('creates a new Domain D6 outside the starter-kit', () => {
    const d6 = createDomain({
      id: 'D6',
      name: 'Health',
      parent_id: null,
      principles: [
        {
          name: 'sleep_floor',
          predicate: 'nightly_sleep_minutes >= 360',
          durability: 'durable',
          owner_scope: 'domain',
          type: 'invariant',
        },
      ],
      intelligence: 'Sleep tracker, workout log, energy journal.',
      accountable: ['founder'],
      authority: 'Decide health investments, recovery cadence, training load.',
      tenant_id: 'T-default',
    })
    expect(d6.id).toBe('D6')
    expect(d6.name).toBe('Health')
    expect(d6.parent_id).toBeNull()
    expect(Object.isFrozen(d6)).toBe(true)
  })

  it('creates a new Charter under D6 referencing it via acl', () => {
    const c = createCharter({
      id: 'C-sleep-discipline',
      purpose: 'Hold a 6h floor on nightly sleep, surface drift early.',
      scope_in: 'sleep_logged_today',
      scope_out: 'workout_log, nutrition_log',
      obligations: [
        {
          name: 'sleep_logged_daily',
          predicate: 'sleep_log_present_for_today',
          durability: 'durable',
          owner_scope: 'charter',
          type: 'obligation',
        },
      ],
      invariants: [
        {
          name: 'sleep_floor_holds',
          predicate: 'sleep_minutes_7d_avg >= 360',
          durability: 'durable',
          owner_scope: 'charter',
          type: 'invariant',
        },
      ],
      success_metrics: ['7-day adherence ≥ 6/7', 'avg ≥ 7h'],
      authority: 'Decide own sleep schedule under D6 Health.',
      termination: 'Founder opts out for ≥30 days.',
      constraints: [],
      acl: [
        {
          domain_or_charter_id: 'D6',
          access: 'append',
          reason: 'D6 Health is the parent domain',
        },
      ],
    })
    expect(c.id).toBe('C-sleep-discipline')
    expect(c.acl[0]?.domain_or_charter_id).toBe('D6')
    expect(c.obligations[0]?.type).toBe('obligation')
    expect(c.invariants[0]?.type).toBe('invariant')
  })

  it('creates a new Workflow operationalizing the Charter', () => {
    const w = createWorkflow({
      id: 'W-evening-sleep-checkin',
      preconditions: 'evening_event_emitted',
      step_graph: [
        {
          step_id: 1,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'continue',
        },
        {
          step_id: 2,
          action: 'terminate',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'sleep_intent_recorded',
      failure_policy: 'continue',
      stringency: 'process',
      interfaces_with: [],
    })
    expect(w.id).toBe('W-evening-sleep-checkin')
    expect(w.step_graph.length).toBe(2)
    expect(w.step_graph[0]?.action).toBe('wait')
    expect(w.step_graph[1]?.action).toBe('terminate')
  })

  it('LiteExecutor runs the dynamically-created Workflow and emits events', () => {
    const w = createWorkflow({
      id: 'W-evening-sleep-checkin-exec',
      preconditions: 'evening_event_emitted',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'continue' },
        { step_id: 2, action: 'terminate', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'sleep_intent_recorded',
      failure_policy: 'continue',
      stringency: 'process',
      interfaces_with: [],
    })

    const events: EngineEvent[] = []
    const result = executeWorkflow({
      workflow: w,
      execution_id: 'E-e2e-create-flow-001',
      emit: (e) => events.push(e),
    })

    expect(result.status).toBe('success')
    expect(result.steps_completed).toBeGreaterThanOrEqual(1)
    expect(events.find((e) => e.type === 'workflow_started')).toBeDefined()
    expect(events.find((e) => e.type === 'workflow_completed')).toBeDefined()
    expect(events.find((e) => e.type === 'step_started')).toBeDefined()
  })

  it('full chain: D6 → C-sleep → W → execute → event chain intact', () => {
    const d6 = createDomain({
      id: 'D6',
      name: 'Health',
      parent_id: null,
      principles: [],
      intelligence: 'Sleep, workouts, energy.',
      accountable: ['founder'],
      authority: 'Health decisions.',
      tenant_id: 'T-default',
    })

    const charter = createCharter({
      id: 'C-sleep-discipline-chain',
      purpose: 'Hold 6h sleep floor.',
      scope_in: 'sleep_log',
      scope_out: 'workouts',
      obligations: [],
      invariants: [],
      success_metrics: ['adherence ≥ 6/7'],
      authority: 'Sleep schedule.',
      termination: 'Opt out 30d.',
      constraints: [],
      acl: [
        {
          domain_or_charter_id: d6.id,
          access: 'append',
          reason: 'parent domain',
        },
      ],
    })

    const wf = createWorkflow({
      id: 'W-evening-checkin-chain',
      preconditions: 'evening',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'continue' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'recorded',
      failure_policy: 'continue',
      stringency: 'process',
      interfaces_with: [],
    })

    const events: EngineEvent[] = []
    const result = executeWorkflow({
      workflow: wf,
      execution_id: 'E-chain-001',
      emit: (e) => events.push(e),
    })

    expect(charter.acl[0]?.domain_or_charter_id).toBe(d6.id)
    expect(result.status).toBe('success')
    expect(events.length).toBeGreaterThan(0)
    expect(events[0]?.type).toBe('workflow_started')
    expect(events[events.length - 1]?.type).toBe('workflow_completed')
  })
})
