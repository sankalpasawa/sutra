/**
 * v1.3.0 Wave 5 — PNC (Pre/Post/Commitment) admission gate + commitment_broken
 * integration tests.
 *
 * Codex W5 BLOCKER folds covered:
 *   1. precondition_check fail ⇒ workflow_failed reason='precondition_failed:<expr>'
 *      WITHOUT workflow_started, WITHOUT step events.
 *   2. PNC engine reuses combinator shape from predicate.ts (and/or/not + atom);
 *      atoms registry-evaluated.
 *   3. commitment_broken explicit workflow→obligation mapping (no heuristics);
 *      requires charter_id + obligation_refs + charter loaded with matching
 *      obligation name.
 *
 * Codex W5 advisory folds covered:
 *   A. Predicate language minimal: AND/OR/NOT/atom only.
 *   B. Registry-based atoms via PredicateRegistry.
 *   C. Failed precondition_check distinct from runtime workflow_failed.
 *   D. commitment_broken only with explicit charter_id + obligation_refs.
 *   E. Predicate determinism: frozen ctx, no Date.now/random/I/O.
 *   F. Test surface: parse precedence, registry lookup failures, deterministic
 *      eval, e2e admitted/rejected/postcondition/commitment.
 *
 * Coverage matrix:
 *   1. Empty preconditions → workflow_started fires (legacy back-compat).
 *   2. Preconditions JSON {atom always_true} + registry → admitted.
 *   3. Preconditions JSON evaluating false → precondition_check{fail} +
 *      workflow_failed reason='precondition_failed:...' + NO workflow_started
 *      + NO step events.
 *   4. Postconditions evaluating false → workflow_failed reason=
 *      'postcondition_failed:...' instead of workflow_completed.
 *   5. Predicate registry lookup miss → workflow_failed reason=
 *      'precondition_failed:...:atom_not_registered:<name>'.
 *   6. Predicate AND/OR/NOT precedence (unit test on parse + eval).
 *   7. Workflow with obligation_refs + charter_id + matching obligation name →
 *      commitment_broken on workflow_failed.
 *   8. Same workflow but charter_id absent → no commitment_broken emitted.
 *   9. obligation_refs validator: empty string in array rejected.
 *  10. Determinism: same predicate + same ctx → same verdict.
 */

import { describe, expect, it } from 'vitest'

import {
  parsePNC,
  evaluatePNC,
  isPNCPredicate,
  BASELINE_PREDICATE_REGISTRY,
  type PNCPredicate,
  type PredicateAtomFn,
  type PredicateRegistry,
} from '../../src/runtime/pnc-predicate.js'
import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import { createCharter } from '../../src/primitives/charter.js'
import { NativeEngine } from '../../src/runtime/native-engine.js'
import type { Workflow } from '../../src/primitives/workflow.js'
import type { Charter } from '../../src/primitives/charter.js'
import type { TriggerSpec } from '../../src/types/trigger-spec.js'
import type { EngineEvent } from '../../src/types/engine-event.js'
import type { HSutraEvent } from '../../src/types/h-sutra-event.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildWorkflow(opts: {
  id?: string
  preconditions?: string
  postconditions?: string
  obligation_refs?: ReadonlyArray<string>
}): Workflow {
  return createWorkflow({
    id: opts.id ?? 'W-w5-test',
    preconditions: opts.preconditions ?? '',
    postconditions: opts.postconditions ?? '',
    step_graph: [
      {
        step_id: 1,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      },
    ],
    inputs: [],
    outputs: [],
    state: [],
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    obligation_refs: opts.obligation_refs,
  })
}

function emitsCollector() {
  const events: EngineEvent[] = []
  return {
    events,
    emit: (e: EngineEvent) => events.push(e),
  }
}

const FROZEN_CTX = Object.freeze({}) as Readonly<Record<string, unknown>>

// ---------------------------------------------------------------------------
// Unit tests — parsePNC + evaluatePNC + isPNCPredicate (codex advisory F)
// ---------------------------------------------------------------------------

describe('PNC parser', () => {
  it('rejects empty / whitespace string (caller treats as legacy)', () => {
    expect(parsePNC('').ok).toBe(false)
    expect(parsePNC('   ').ok).toBe(false)
  })

  it('rejects legacy free-form string (does not start with {)', () => {
    const r = parsePNC('is_morning_window AND no_pulse_today')
    expect(r.ok).toBe(false)
    expect(r.error).toBe('expression_not_json')
  })

  it('parses atom JSON', () => {
    const r = parsePNC('{"type":"atom","name":"always_true"}')
    expect(r.ok).toBe(true)
    expect(r.predicate).toEqual({ type: 'atom', name: 'always_true' })
  })

  it('parses nested AND/OR/NOT correctly', () => {
    const r = parsePNC(
      '{"type":"and","clauses":[{"type":"atom","name":"a"},{"type":"or","clauses":[{"type":"atom","name":"b"},{"type":"not","clause":{"type":"atom","name":"c"}}]}]}',
    )
    expect(r.ok).toBe(true)
    expect(r.predicate).toBeDefined()
  })

  it('rejects malformed JSON', () => {
    const r = parsePNC('{"type":"atom"')
    expect(r.ok).toBe(false)
    expect(r.error?.startsWith('json_parse_error')).toBe(true)
  })

  it('rejects shape with unknown discriminator', () => {
    const r = parsePNC('{"type":"foo"}')
    expect(r.ok).toBe(false)
    expect(r.error).toBe('shape_invalid')
  })

  it('rejects atom with empty name', () => {
    expect(isPNCPredicate({ type: 'atom', name: '' })).toBe(false)
  })

  it('rejects and/or with non-array clauses', () => {
    expect(isPNCPredicate({ type: 'and', clauses: 'not-array' })).toBe(false)
    expect(isPNCPredicate({ type: 'or', clauses: { not: 'array' } })).toBe(false)
  })

  it('recursively validates and/or/not clauses', () => {
    expect(
      isPNCPredicate({ type: 'and', clauses: [{ type: 'atom', name: 'x' }, { type: 'foo' }] }),
    ).toBe(false)
    expect(isPNCPredicate({ type: 'not', clause: { type: 'foo' } })).toBe(false)
  })
})

describe('PNC evaluator', () => {
  it('atom hit returns verdict=true; miss returns verdict=false with stable reason', () => {
    const r1 = evaluatePNC({ type: 'atom', name: 'always_true' }, FROZEN_CTX, BASELINE_PREDICATE_REGISTRY)
    expect(r1.verdict).toBe(true)

    const r2 = evaluatePNC({ type: 'atom', name: 'never_registered' }, FROZEN_CTX, BASELINE_PREDICATE_REGISTRY)
    expect(r2.verdict).toBe(false)
    expect(r2.reason).toBe('atom_not_registered:never_registered')
  })

  it('atom that throws returns verdict=false with atom_threw reason (deterministic; fail closed)', () => {
    const reg: PredicateRegistry = new Map<string, PredicateAtomFn>([
      ['boom', () => { throw new Error('synthetic') }],
    ])
    const r = evaluatePNC({ type: 'atom', name: 'boom' }, FROZEN_CTX, reg)
    expect(r.verdict).toBe(false)
    expect(r.reason).toBe('atom_threw:boom:synthetic')
  })

  it('algebraic identities: empty AND ⇒ true; empty OR ⇒ false', () => {
    expect(evaluatePNC({ type: 'and', clauses: [] }, FROZEN_CTX, BASELINE_PREDICATE_REGISTRY).verdict).toBe(true)
    expect(evaluatePNC({ type: 'or', clauses: [] }, FROZEN_CTX, BASELINE_PREDICATE_REGISTRY).verdict).toBe(false)
  })

  it('AND/OR/NOT precedence — and short-circuits on first false; or short-circuits on first true; not flips', () => {
    // (always_true AND always_false) ⇒ false
    const andFalse = evaluatePNC(
      { type: 'and', clauses: [{ type: 'atom', name: 'always_true' }, { type: 'atom', name: 'always_false' }] },
      FROZEN_CTX,
      BASELINE_PREDICATE_REGISTRY,
    )
    expect(andFalse.verdict).toBe(false)
    // (always_false OR always_true) ⇒ true
    const orTrue = evaluatePNC(
      { type: 'or', clauses: [{ type: 'atom', name: 'always_false' }, { type: 'atom', name: 'always_true' }] },
      FROZEN_CTX,
      BASELINE_PREDICATE_REGISTRY,
    )
    expect(orTrue.verdict).toBe(true)
    // NOT (always_true) ⇒ false
    const notT = evaluatePNC(
      { type: 'not', clause: { type: 'atom', name: 'always_true' } },
      FROZEN_CTX,
      BASELINE_PREDICATE_REGISTRY,
    )
    expect(notT.verdict).toBe(false)
    // NOT (always_false) ⇒ true
    const notF = evaluatePNC(
      { type: 'not', clause: { type: 'atom', name: 'always_false' } },
      FROZEN_CTX,
      BASELINE_PREDICATE_REGISTRY,
    )
    expect(notF.verdict).toBe(true)
  })

  it('determinism: same predicate + same context ⇒ same verdict (codex advisory E)', () => {
    let calls = 0
    const reg: PredicateRegistry = new Map<string, PredicateAtomFn>([
      ['count', (ctx) => {
        calls++
        return ctx['marker'] === 'on'
      }],
    ])
    const ctx = Object.freeze({ marker: 'on' })
    const p: PNCPredicate = { type: 'atom', name: 'count' }
    const r1 = evaluatePNC(p, ctx, reg)
    const r2 = evaluatePNC(p, ctx, reg)
    expect(r1.verdict).toBe(true)
    expect(r2.verdict).toBe(true)
    expect(calls).toBe(2) // two calls, identical results
  })
})

// ---------------------------------------------------------------------------
// Workflow primitive — obligation_refs validator (codex W5 BLOCKER 3)
// ---------------------------------------------------------------------------

describe('Workflow.obligation_refs validator', () => {
  it('defaults to [] when omitted', () => {
    const wf = buildWorkflow({})
    expect(wf.obligation_refs).toEqual([])
  })

  it('accepts non-empty string entries', () => {
    const wf = buildWorkflow({ obligation_refs: ['weekly_pulse_published', 'gdpr_audit_completed'] })
    expect(wf.obligation_refs).toEqual(['weekly_pulse_published', 'gdpr_audit_completed'])
  })

  it('rejects empty string entries (codex W5 BLOCKER 3 explicit declarative mapping)', () => {
    expect(() =>
      buildWorkflow({ obligation_refs: ['ok', ''] }),
    ).toThrowError(/obligation_refs\[1\]/)
  })

  it('rejects non-array', () => {
    expect(() =>
      // @ts-expect-error — intentional misuse to verify runtime guard
      buildWorkflow({ obligation_refs: 'not-an-array' }),
    ).toThrowError(/obligation_refs/)
  })
})

// ---------------------------------------------------------------------------
// lite-executor — precondition + postcondition admission gate
// ---------------------------------------------------------------------------

describe('lite-executor PNC admission gate', () => {
  it('1. empty preconditions ⇒ workflow_started fires (legacy back-compat — no PNC gate)', async () => {
    const wf = buildWorkflow({ preconditions: '' })
    const { events, emit } = emitsCollector()
    await executeWorkflow({
      workflow: wf,
      execution_id: 'E-1',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    const started = events.find((e) => e.type === 'workflow_started')
    expect(started).toBeDefined()
    const preCheck = events.find((e) => e.type === 'precondition_check')
    expect(preCheck).toBeUndefined()
  })

  it('2. preconditions JSON {atom always_true} ⇒ admitted; precondition_check{pass} fires', async () => {
    const wf = buildWorkflow({ preconditions: '{"type":"atom","name":"always_true"}' })
    const { events, emit } = emitsCollector()
    await executeWorkflow({
      workflow: wf,
      execution_id: 'E-2',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    const preCheck = events.find((e) => e.type === 'precondition_check')
    expect(preCheck).toBeDefined()
    if (preCheck && preCheck.type === 'precondition_check') {
      expect(preCheck.verdict).toBe('pass')
    }
    const started = events.find((e) => e.type === 'workflow_started')
    expect(started).toBeDefined()
    const completed = events.find((e) => e.type === 'workflow_completed')
    expect(completed).toBeDefined()
  })

  it('3. preconditions evaluating false ⇒ precondition_check{fail} + workflow_failed reason=precondition_failed; NO workflow_started; NO step events', async () => {
    const wf = buildWorkflow({ preconditions: '{"type":"atom","name":"always_false"}' })
    const { events, emit } = emitsCollector()
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-3',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    expect(result.status).toBe('failed')
    expect(result.steps_completed).toBe(0)
    expect(result.reason?.startsWith('precondition_failed:')).toBe(true)

    // Audit-shape invariants:
    expect(events.find((e) => e.type === 'workflow_started')).toBeUndefined()
    expect(events.find((e) => e.type === 'step_started')).toBeUndefined()
    expect(events.find((e) => e.type === 'step_completed')).toBeUndefined()

    // precondition_check{fail} + workflow_failed both emitted
    const preCheck = events.find((e) => e.type === 'precondition_check')
    expect(preCheck).toBeDefined()
    if (preCheck && preCheck.type === 'precondition_check') {
      expect(preCheck.verdict).toBe('fail')
      expect(preCheck.expression).toBe('{"type":"atom","name":"always_false"}')
    }
    const failed = events.find((e) => e.type === 'workflow_failed')
    expect(failed).toBeDefined()
    if (failed && failed.type === 'workflow_failed') {
      expect(failed.reason.startsWith('precondition_failed:')).toBe(true)
    }
  })

  it('4. postconditions evaluating false ⇒ workflow_failed reason=postcondition_failed (instead of workflow_completed)', async () => {
    const wf = buildWorkflow({
      preconditions: '',
      postconditions: '{"type":"atom","name":"always_false"}',
    })
    const { events, emit } = emitsCollector()
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-4',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    expect(result.status).toBe('failed')
    expect(result.reason?.startsWith('postcondition_failed:')).toBe(true)

    // workflow_started fires (admission ok); steps run; then postcondition fails
    expect(events.find((e) => e.type === 'workflow_started')).toBeDefined()
    expect(events.find((e) => e.type === 'step_completed')).toBeDefined()
    expect(events.find((e) => e.type === 'workflow_completed')).toBeUndefined()
    const postCheck = events.find((e) => e.type === 'postcondition_check')
    expect(postCheck).toBeDefined()
    if (postCheck && postCheck.type === 'postcondition_check') {
      expect(postCheck.verdict).toBe('fail')
    }
    const failed = events.find((e) => e.type === 'workflow_failed')
    expect(failed).toBeDefined()
  })

  it('5. predicate registry lookup miss ⇒ precondition_failed:...:atom_not_registered:<name>', async () => {
    const wf = buildWorkflow({ preconditions: '{"type":"atom","name":"never_registered"}' })
    const { events, emit } = emitsCollector()
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-5',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    expect(result.status).toBe('failed')
    expect(result.reason).toContain('atom_not_registered:never_registered')
    // No workflow_started
    expect(events.find((e) => e.type === 'workflow_started')).toBeUndefined()
  })

  it('legacy free-form preconditions string ⇒ skip PNC gate silently (legacy back-compat)', async () => {
    const wf = buildWorkflow({ preconditions: 'is_morning_window AND no_pulse_today' })
    const { events, emit } = emitsCollector()
    await executeWorkflow({
      workflow: wf,
      execution_id: 'E-legacy',
      emit,
      pnc_registry: BASELINE_PREDICATE_REGISTRY,
    })
    // No PNC events; normal lifecycle
    expect(events.find((e) => e.type === 'precondition_check')).toBeUndefined()
    expect(events.find((e) => e.type === 'workflow_started')).toBeDefined()
    expect(events.find((e) => e.type === 'workflow_completed')).toBeDefined()
  })

  it('PNC gate skipped when pnc_registry is undefined (NativeEngine routed-only feature)', async () => {
    const wf = buildWorkflow({ preconditions: '{"type":"atom","name":"always_false"}' })
    const { events, emit } = emitsCollector()
    await executeWorkflow({
      workflow: wf,
      execution_id: 'E-no-reg',
      emit,
      // pnc_registry intentionally omitted
    })
    expect(events.find((e) => e.type === 'precondition_check')).toBeUndefined()
    expect(events.find((e) => e.type === 'workflow_started')).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// NativeEngine — commitment_broken emission (codex W5 BLOCKER 3)
// ---------------------------------------------------------------------------

describe('NativeEngine commitment_broken emission', () => {
  // Build a Workflow that ALWAYS fails (postcondition forces failure even
  // though the single step succeeds — easy way to trigger workflow_failed
  // through a routed run).
  function buildAlwaysFailingWorkflow(opts: {
    id: string
    obligation_refs?: ReadonlyArray<string>
  }): Workflow {
    return createWorkflow({
      id: opts.id,
      preconditions: '',
      postconditions: '{"type":"atom","name":"always_false"}',
      step_graph: [
        {
          step_id: 1,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      obligation_refs: opts.obligation_refs,
    })
  }

  function buildCharter(opts: { id: string; obligationName: string }): Charter {
    return createCharter({
      id: opts.id,
      purpose: 'test charter',
      scope_in: 'test',
      scope_out: '',
      obligations: [
        {
          name: opts.obligationName,
          predicate: 'always',
          durability: 'durable',
          owner_scope: 'charter',
          type: 'obligation',
        },
      ],
      invariants: [],
      success_metrics: [],
      authority: 'test',
      termination: 'test',
      constraints: [],
      acl: [],
    })
  }

  it('7. workflow with obligation_refs + charter_id (via STARTER_WORKFLOW_CHARTER_MAP) + matching obligation ⇒ commitment_broken emitted on workflow_failed', async () => {
    // Use the existing W-daily-pulse-morning ↔ C-daily-pulse mapping in
    // STARTER_WORKFLOW_CHARTER_MAP. We swap the workflow definition with a
    // matching id but obligation_refs declared, and the charter with the
    // same id but a matching obligation name.
    const obligationName = 'morning_pulse_published'
    const wf = buildAlwaysFailingWorkflow({
      // Must match a workflow id in STARTER_WORKFLOW_CHARTER_MAP. The starter
      // map binds W-morning-pulse → C-daily-pulse so we substitute our test
      // workflow under that id.
      id: 'W-morning-pulse',
      obligation_refs: [obligationName],
    })
    const charter = buildCharter({
      id: 'C-daily-pulse',
      obligationName,
    })

    // Wire a matching trigger so the engine routes founder_input → wf.
    const trigger: TriggerSpec = {
      id: 'T-w5-test',
      event_type: 'founder_input',
      route_predicate: { type: 'always_true' },
      target_workflow: wf.id,
    }

    const collected: EngineEvent[] = []
    const engine = new NativeEngine({
      workflows: [wf],
      charters: [charter],
      triggers: [trigger],
      skip_user_kit: true,
      now_ms: () => 0,
      write: () => undefined, // silent stdout for tests
      on_error: () => undefined, // swallow informational logs
    })
    // Hook the renderer so we capture events directly.
    engine.renderer.register('commitment_broken', (e) => {
      collected.push(e)
      return ''
    })
    engine.renderer.register('workflow_failed', (e) => {
      collected.push(e)
      return ''
    })

    const evt: HSutraEvent = {
      turn_id: 'turn-1',
      ts_ms: 0,
      direction: 'INTERNAL',
      verb: 'DIRECT',
      cell: 'INTERNAL.DIRECT',
      input_text: 'test',
      risk: 'LOW',
    }
    await engine.handleHSutraEvent(evt)

    const failed = collected.find((e) => e.type === 'workflow_failed')
    expect(failed).toBeDefined()

    const broken = collected.find((e) => e.type === 'commitment_broken')
    expect(broken).toBeDefined()
    if (broken && broken.type === 'commitment_broken') {
      expect(broken.charter_id).toBe('C-daily-pulse')
      expect(broken.obligation_name).toBe(obligationName)
      expect(broken.workflow_id).toBe('W-morning-pulse')
    }
  })

  it('8. workflow with obligation_refs but charter_id absent (workflow id not in STARTER_WORKFLOW_CHARTER_MAP) ⇒ NO commitment_broken', async () => {
    const wf = buildAlwaysFailingWorkflow({
      id: 'W-orphan-no-charter-map',
      obligation_refs: ['orphan_obligation'],
    })
    const trigger: TriggerSpec = {
      id: 'T-w5-orphan',
      event_type: 'founder_input',
      route_predicate: { type: 'always_true' },
      target_workflow: wf.id,
    }

    const collected: EngineEvent[] = []
    const engine = new NativeEngine({
      workflows: [wf],
      triggers: [trigger],
      skip_user_kit: true,
      now_ms: () => 0,
      write: () => undefined,
      on_error: () => undefined,
    })
    engine.renderer.register('commitment_broken', (e) => {
      collected.push(e)
      return ''
    })
    engine.renderer.register('workflow_failed', (e) => {
      collected.push(e)
      return ''
    })

    const evt: HSutraEvent = {
      turn_id: 'turn-2',
      ts_ms: 0,
      direction: 'INTERNAL',
      verb: 'DIRECT',
      cell: 'INTERNAL.DIRECT',
      input_text: 'test',
      risk: 'LOW',
    }
    await engine.handleHSutraEvent(evt)

    expect(collected.find((e) => e.type === 'workflow_failed')).toBeDefined()
    expect(collected.find((e) => e.type === 'commitment_broken')).toBeUndefined()
  })

  it('workflow.obligation_refs empty ⇒ no commitment_broken even with charter_id', async () => {
    const wf = buildAlwaysFailingWorkflow({
      id: 'W-evening-shutdown', // mapped to C-daily-pulse in starter map
      obligation_refs: [], // explicitly empty
    })
    const trigger: TriggerSpec = {
      id: 'T-w5-empty-refs',
      event_type: 'founder_input',
      route_predicate: { type: 'always_true' },
      target_workflow: wf.id,
    }

    const collected: EngineEvent[] = []
    const engine = new NativeEngine({
      workflows: [wf],
      triggers: [trigger],
      skip_user_kit: true,
      now_ms: () => 0,
      write: () => undefined,
      on_error: () => undefined,
    })
    engine.renderer.register('commitment_broken', (e) => {
      collected.push(e)
      return ''
    })

    const evt: HSutraEvent = {
      turn_id: 'turn-3',
      ts_ms: 0,
      direction: 'INTERNAL',
      verb: 'DIRECT',
      cell: 'INTERNAL.DIRECT',
      input_text: 'test',
      risk: 'LOW',
    }
    await engine.handleHSutraEvent(evt)

    expect(collected.find((e) => e.type === 'commitment_broken')).toBeUndefined()
  })
})
