/**
 * E2E vertical slice — organic emergence loop (SPEC v1.2 §4.7).
 *
 * Proves the load-bearing happy path:
 *   1. 4 founder utterances with the same normalized phrase → all no-match
 *      against the empty trigger set
 *   2. The 5th call with proposer_enabled=true emits pattern_proposed +
 *      persists a ProposalEntry in pending state
 *   3. Founder utterance "approve P-<id>" triggers applyApproval:
 *      Workflow + TriggerSpec persisted to user-kit, router registered,
 *      ledger entry → approved
 *   4. The next matching utterance routes mode='exact' through the new
 *      TriggerSpec → workflow execution events emitted
 *   5. A fresh NativeEngine constructed against the same user-kit reloads
 *      the emergent Workflow + TriggerSpec from disk
 */

import { existsSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { NativeEngine } from '../../src/runtime/native-engine.js'
import { listProposals } from '../../src/persistence/proposal-ledger.js'
import { listTriggers, listWorkflows } from '../../src/persistence/user-kit.js'
import {
  normalizeUtterance,
  patternIdFor,
} from '../../src/runtime/pattern-detector.js'
import type { HSutraEvent } from '../../src/types/h-sutra-event.js'
import type { EngineEvent } from '../../src/types/engine-event.js'

function writeLog(path: string, events: object[]): void {
  mkdirSync(join(path, '..'), { recursive: true })
  writeFileSync(path, events.map((e) => JSON.stringify(e)).join('\n') + '\n')
}

function makeHSutraRow(turn_id: string, input_text: string, ts_ms: number): object {
  return {
    turn_id,
    input_text,
    ts: new Date(ts_ms).toISOString(),
    cell: 'DIRECT·INBOUND',
  }
}

function makeEvent(turn_id: string, input_text: string): HSutraEvent {
  return {
    turn_id,
    input_text,
    cell: 'DIRECT·INBOUND',
  }
}

describe('E2E — organic emergence vertical slice', () => {
  let HOME: string
  let LOG: string
  const NOW = 1_700_000_000_000

  beforeEach(() => {
    HOME = mkdtempSync(join(tmpdir(), 'native-emergence-e2e-'))
    LOG = join(HOME, 'h-sutra.jsonl')
  })

  afterEach(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('full propose → approve → re-route flow + restart reload', async () => {
    // Seed H-Sutra log with 4 repeated utterances within the detector window.
    writeLog(LOG, [
      makeHSutraRow('t1', 'track design partners', NOW - 4000),
      makeHSutraRow('t2', 'track design partners', NOW - 3000),
      makeHSutraRow('t3', 'track design partners', NOW - 2000),
      makeHSutraRow('t4', 'track design partners', NOW - 1000),
    ])

    const events: EngineEvent[] = []
    const lines: string[] = []

    const engine = new NativeEngine({
      // empty starter triggers + workflows so no-match is guaranteed
      triggers: [],
      workflows: [],
      proposer_enabled: true,
      user_kit_options: { home: HOME },
      pattern_detector_options: { hsutra_log_path: LOG, now_ms: NOW },
      now_ms: () => NOW,
      connector_options: { log_path: LOG },
      write: (s) => lines.push(s),
    })

    // Capture every event the engine renders for assertion.
    engine.renderer.register('routing_decision', (e) => {
      events.push(e); return `[routing_decision] ${e.mode}`
    })
    engine.renderer.register('pattern_proposed', (e) => {
      events.push(e); return `[pattern_proposed] ${e.pattern_id}`
    })
    engine.renderer.register('proposal_approved', (e) => {
      events.push(e); return `[proposal_approved] ${e.pattern_id}`
    })
    engine.renderer.register('workflow_started', (e) => {
      events.push(e); return `[workflow_started] ${e.workflow_id}`
    })
    engine.renderer.register('workflow_completed', (e) => {
      events.push(e); return `[workflow_completed] ${e.workflow_id}`
    })
    engine.renderer.register('step_started', (e) => {
      events.push(e); return `[step_started] ${e.step_id}`
    })
    engine.renderer.register('step_completed', (e) => {
      events.push(e); return `[step_completed] ${e.step_id}`
    })

    // 5th utterance — same phrase. The pattern detector should surface it.
    const trigger_event = makeEvent('t5', 'track design partners')
    const emitted_first = await engine.ingest(trigger_event)
    expect(emitted_first).toBeGreaterThanOrEqual(2) // routing_decision + pattern_proposed

    // Verify the pattern_proposed event landed
    const proposed = events.find((e) => e.type === 'pattern_proposed')
    expect(proposed).toBeDefined()
    if (proposed?.type !== 'pattern_proposed') throw new Error('type narrow')
    const expected_pattern_id = patternIdFor(normalizeUtterance('track design partners'))
    expect(proposed.pattern_id).toBe(expected_pattern_id)
    expect(proposed.evidence_count).toBe(4)
    expect(proposed.proposed_workflow_id).toBe(`W-emergent-${expected_pattern_id.slice(2)}`)

    // Verify ledger persisted as 'pending'
    const pending = listProposals({ home: HOME }, 'pending')
    expect(pending).toHaveLength(1)
    expect(pending[0].pattern_id).toBe(expected_pattern_id)

    // Founder approves via next utterance
    const approve_event = makeEvent('t6', `approve ${expected_pattern_id}`)
    const emitted_approve = await engine.ingest(approve_event)
    expect(emitted_approve).toBe(1)

    // Verify proposal_approved event + ledger flipped to 'approved'
    const approved = events.find((e) => e.type === 'proposal_approved')
    expect(approved).toBeDefined()
    if (approved?.type !== 'proposal_approved') throw new Error('type narrow')
    expect(approved.registered_workflow_id).toBe(`W-emergent-${expected_pattern_id.slice(2)}`)
    expect(approved.registered_trigger_id).toBe(`T-emergent-${expected_pattern_id.slice(2)}`)

    expect(listProposals({ home: HOME }, 'pending')).toHaveLength(0)
    expect(listProposals({ home: HOME }, 'approved')).toHaveLength(1)

    // Verify Workflow + TriggerSpec persisted to user-kit
    expect(listWorkflows({ home: HOME }).map((w) => w.id)).toContain(
      `W-emergent-${expected_pattern_id.slice(2)}`,
    )
    expect(listTriggers({ home: HOME }).map((t) => t.id)).toContain(
      `T-emergent-${expected_pattern_id.slice(2)}`,
    )

    // Next matching utterance — should route mode='exact' now
    events.length = 0 // clear for clean assertion
    await engine.ingest(makeEvent('t7', 'I want to track design partners again'))
    const exact_routing = events.find((e) => e.type === 'routing_decision')
    expect(exact_routing).toBeDefined()
    if (exact_routing?.type !== 'routing_decision') throw new Error('type narrow')
    expect(exact_routing.mode).toBe('exact')
    expect(exact_routing.workflow_id).toBe(`W-emergent-${expected_pattern_id.slice(2)}`)

    // Fresh engine on same user-kit reloads emergent primitives — survives restart
    const engine2 = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: false, // no need to re-propose
      user_kit_options: { home: HOME },
      connector_options: { log_path: LOG },
      write: () => {},
    })
    const reloaded_events: EngineEvent[] = []
    engine2.renderer.register('routing_decision', (e) => {
      reloaded_events.push(e); return ''
    })
    await engine2.ingest(makeEvent('t8', 'track design partners reloaded'))
    const reloaded_routing = reloaded_events.find((e) => e.type === 'routing_decision')
    expect(reloaded_routing).toBeDefined()
    if (reloaded_routing?.type !== 'routing_decision') throw new Error('type narrow')
    expect(reloaded_routing.mode).toBe('exact')
    expect(reloaded_routing.workflow_id).toBe(`W-emergent-${expected_pattern_id.slice(2)}`)
  })

  it('reject path: ledger flips to rejected, no workflow persisted', async () => {
    writeLog(LOG, [
      makeHSutraRow('t1', 'shutdown daily review', NOW - 4000),
      makeHSutraRow('t2', 'shutdown daily review', NOW - 3000),
      makeHSutraRow('t3', 'shutdown daily review', NOW - 2000),
      makeHSutraRow('t4', 'shutdown daily review', NOW - 1000),
    ])
    const engine = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: true,
      user_kit_options: { home: HOME },
      pattern_detector_options: { hsutra_log_path: LOG, now_ms: NOW },
      now_ms: () => NOW,
      connector_options: { log_path: LOG },
      write: () => {},
    })
    await engine.ingest(makeEvent('t5', 'shutdown daily review'))

    const expected_id = patternIdFor(normalizeUtterance('shutdown daily review'))
    expect(listProposals({ home: HOME }, 'pending')).toHaveLength(1)

    await engine.ingest(makeEvent('t6', `reject ${expected_id} too generic`))

    expect(listProposals({ home: HOME }, 'pending')).toHaveLength(0)
    expect(listProposals({ home: HOME }, 'rejected')).toHaveLength(1)
    expect(listProposals({ home: HOME }, 'rejected')[0].decision_reason).toBe('too generic')

    // No workflow / trigger persisted
    expect(listWorkflows({ home: HOME })).toHaveLength(0)
    expect(listTriggers({ home: HOME })).toHaveLength(0)
  })

  it('proposer_enabled=false suppresses the no-match → propose path', async () => {
    writeLog(LOG, [
      makeHSutraRow('t1', 'review pipeline status', NOW - 4000),
      makeHSutraRow('t2', 'review pipeline status', NOW - 3000),
      makeHSutraRow('t3', 'review pipeline status', NOW - 2000),
      makeHSutraRow('t4', 'review pipeline status', NOW - 1000),
    ])
    const engine = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: false,
      user_kit_options: { home: HOME },
      pattern_detector_options: { hsutra_log_path: LOG, now_ms: NOW },
      connector_options: { log_path: LOG },
      write: () => {},
    })
    await engine.ingest(makeEvent('t5', 'review pipeline status'))
    expect(listProposals({ home: HOME })).toHaveLength(0)
  })

  it('approve unknown pattern_id is a no-op (logs error, returns 0)', async () => {
    const errors: Error[] = []
    const engine = new NativeEngine({
      triggers: [],
      workflows: [],
      proposer_enabled: true,
      user_kit_options: { home: HOME },
      pattern_detector_options: { hsutra_log_path: LOG, now_ms: NOW },
      connector_options: { log_path: LOG },
      write: () => {},
      on_error: (e) => errors.push(e),
    })
    const emitted = await engine.ingest(makeEvent('t1', 'approve P-deadbeef'))
    expect(emitted).toBe(0)
    expect(errors.length).toBeGreaterThan(0)
    expect(errors[0].message).toMatch(/no pending proposal/)
  })
})
