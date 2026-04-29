/**
 * skill-invocation contract tests — M6 Group P (T-069..T-073).
 *
 * Surface under test:
 *   invokeSkill(parentStep, context) — discriminated SkillInvocationResult.
 *   Happy path: resolve → run isolated child executor → extract terminal step
 *     output → validate against cached return_contract → success payload.
 *   Failure paths (errMsg formats per M5 canonical):
 *     - skill_unresolved:<skill_ref>      (registry miss)
 *     - skill_output_validation:<details> (return_contract violation)
 *     - skill_recursion_cap:<depth>       (depth ≥ SKILL_RECURSION_CAP)
 *   Determinism: same parentStep + same skill_ref → same child_execution_id.
 *
 * Plan: holding/plans/native-v1.0/M6-skill-engine.md Group P.
 * Codex pre-dispatch: .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P1.3).
 *
 * Note: executor wiring scenarios (steps with skill_ref dispatched via
 * executeStepGraph + child_edges shape) live in Group Q's integration
 * scenarios. This file holds the unit-level contract for invokeSkill itself.
 */

import { describe, it, expect } from 'vitest'
import { SkillEngine } from '../../../src/engine/skill-engine.js'
import {
  invokeSkill,
  SKILL_RECURSION_CAP,
  type SkillInvocationContext,
} from '../../../src/engine/skill-invocation.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
} from '../../../src/engine/step-graph-executor.js'
import { createWorkflow, type Workflow } from '../../../src/primitives/workflow.js'
import type { WorkflowStep } from '../../../src/types/index.js'

// -----------------------------------------------------------------------------
// Test helpers
// -----------------------------------------------------------------------------

/**
 * JSON Schema accepting `{value: <integer>}`. The Skill's terminal step output
 * is the validated_payload; we use this schema to drive both happy + invalid
 * output-validation paths.
 */
const SCHEMA_INT_VALUE = JSON.stringify({
  type: 'object',
  properties: { value: { type: 'integer' } },
  required: ['value'],
  additionalProperties: false,
})

/**
 * Build a Skill (Workflow with reuse_tag=true) whose single step is an
 * `action='wait'` step. We use `wait` (NOT `skill_ref`) so the child
 * executor goes through the dispatcher path — NOT a recursive
 * invokeSkill — keeping the test focused on the parent→child seam without
 * dragging Skill resolution of the leaf into the test.
 */
function makeSkill(opts: {
  id: string
  return_contract?: string
}): Workflow {
  return createWorkflow({
    id: opts.id,
    preconditions: '',
    step_graph: [
      // action='wait' → executor calls dispatcher; dispatcher returns the
      // synthetic Skill output we want to validate as the validated_payload.
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: true,
    return_contract: opts.return_contract ?? SCHEMA_INT_VALUE,
  })
}

/**
 * A parent step that invokes a Skill by ref. step_id=42 is arbitrary — the
 * deterministic child_execution_id is `child-<step_id>-<skill_ref>` so we can
 * assert on it without clock dependencies.
 */
function parentStep(skill_ref: string, step_id = 42): WorkflowStep {
  return { step_id, skill_ref, inputs: [], outputs: [], on_failure: 'abort' }
}

/**
 * Dispatcher that returns a fixed payload as the leaf step's first output.
 * Convention: validated_payload = outputs[0] of the Skill's terminal step.
 */
function dispatcherWithPayload(payload: unknown): ActivityDispatcher {
  return () => ({ kind: 'ok', outputs: [payload] })
}

// -----------------------------------------------------------------------------
// SKILL_RECURSION_CAP constant (T-072)
// -----------------------------------------------------------------------------

describe('SKILL_RECURSION_CAP', () => {
  it('exports SKILL_RECURSION_CAP = 8 (T-072)', () => {
    expect(SKILL_RECURSION_CAP).toBe(8)
  })
})

// -----------------------------------------------------------------------------
// invokeSkill — happy path (T-070)
// -----------------------------------------------------------------------------

describe('invokeSkill — happy path (T-070)', () => {
  it('resolves + runs child + validates payload + returns success', async () => {
    const engine = new SkillEngine()
    const skill = makeSkill({ id: 'W-skill-ok' })
    engine.register(skill)

    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 42 }),
      recursion_depth: 0,
    }
    const result = await invokeSkill(parentStep('W-skill-ok'), ctx)

    expect(result.kind).toBe('success')
    if (result.kind !== 'success') return // narrow
    expect(result.skill_ref).toBe('W-skill-ok')
    expect(result.validated_payload).toEqual({ value: 42 })
    // Deterministic, clock-free id (replay-determinism: codex P1.3)
    expect(result.child_execution_id).toBe('child-42-W-skill-ok')
    // Child result available for diagnostics (NOT merged into parent state by
    // invokeSkill itself — the executor at T-073 decides what to record).
    expect(result.child_result.workflow_id).toBe('W-skill-ok')
    expect(result.child_result.state).toBe('success')
  })

  it('child_execution_id is deterministic across calls (replay determinism)', async () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-det' }))
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 1 }),
      recursion_depth: 0,
    }
    const r1 = await invokeSkill(parentStep('W-det', 7), ctx)
    const r2 = await invokeSkill(parentStep('W-det', 7), ctx)
    expect(r1.kind).toBe('success')
    expect(r2.kind).toBe('success')
    if (r1.kind === 'success' && r2.kind === 'success') {
      expect(r1.child_execution_id).toBe(r2.child_execution_id)
    }
  })
})

// -----------------------------------------------------------------------------
// invokeSkill — failure: registry miss (T-071)
// -----------------------------------------------------------------------------

describe('invokeSkill — registry miss (T-071)', () => {
  it('returns kind:failure with errMsg=skill_unresolved:<ref>', async () => {
    const engine = new SkillEngine()
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 0 }),
      recursion_depth: 0,
    }
    const result = await invokeSkill(parentStep('W-ghost'), ctx)
    expect(result.kind).toBe('failure')
    if (result.kind === 'failure') {
      expect(result.skill_ref).toBe('W-ghost')
      expect(result.errMsg).toBe('skill_unresolved:W-ghost')
    }
  })
})

// -----------------------------------------------------------------------------
// invokeSkill — failure: output validation (T-071)
// -----------------------------------------------------------------------------

describe('invokeSkill — output_validation failure (T-071)', () => {
  it('returns kind:failure with errMsg=skill_output_validation:<details>', async () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-skill-bad' }))
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      // Dispatcher emits a payload that violates SCHEMA_INT_VALUE
      // (value is a string, not an integer).
      dispatch: dispatcherWithPayload({ value: 'not-an-int' }),
      recursion_depth: 0,
    }
    const result = await invokeSkill(parentStep('W-skill-bad'), ctx)
    expect(result.kind).toBe('failure')
    if (result.kind === 'failure') {
      expect(result.skill_ref).toBe('W-skill-bad')
      expect(result.errMsg.startsWith('skill_output_validation:')).toBe(true)
      // ajv error string mentions the violated field + expected type.
      expect(result.errMsg.length).toBeGreaterThan('skill_output_validation:'.length)
    }
  })
})

// -----------------------------------------------------------------------------
// invokeSkill — recursion cap (T-072)
// -----------------------------------------------------------------------------

describe('invokeSkill — recursion cap (T-072)', () => {
  it('cap fires when recursion_depth >= SKILL_RECURSION_CAP', async () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-deep' }))
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 1 }),
      // Already at the cap → must fail before resolution.
      recursion_depth: SKILL_RECURSION_CAP,
    }
    const result = await invokeSkill(parentStep('W-deep'), ctx)
    expect(result.kind).toBe('failure')
    if (result.kind === 'failure') {
      expect(result.errMsg).toBe(`skill_recursion_cap:${SKILL_RECURSION_CAP}`)
    }
  })

  it('cap does NOT fire at depth = cap-1 (boundary on the safe side)', async () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-edge' }))
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 1 }),
      recursion_depth: SKILL_RECURSION_CAP - 1,
    }
    const result = await invokeSkill(parentStep('W-edge'), ctx)
    expect(result.kind).toBe('success')
  })
})

// -----------------------------------------------------------------------------
// Defensive guard — invokeSkill called with a parentStep missing skill_ref
// -----------------------------------------------------------------------------

describe('invokeSkill — defensive guard for missing skill_ref', () => {
  it('returns kind:failure with skill_unresolved when parentStep.skill_ref is absent', async () => {
    const engine = new SkillEngine()
    const ctx: SkillInvocationContext = {
      skill_engine: engine,
      dispatch: dispatcherWithPayload({ value: 1 }),
      recursion_depth: 0,
    }
    // Direct construct: parent step has neither skill_ref nor a non-empty
    // string for it. Caller (executor) is contracted to only call invokeSkill
    // when skill_ref is set; this guards against programmer error.
    const result = await invokeSkill(
      { step_id: 1, inputs: [], outputs: [], on_failure: 'abort' },
      ctx,
    )
    expect(result.kind).toBe('failure')
    if (result.kind === 'failure') {
      expect(result.errMsg.startsWith('skill_unresolved:')).toBe(true)
    }
  })
})

// -----------------------------------------------------------------------------
// Executor wiring (T-073) — minimum surface to lock codex P1.3 isolation +
// child_edge surfacing + canonical failure routing. Full integration
// scenarios live in Group Q's tests.
// -----------------------------------------------------------------------------

describe('step-graph-executor wiring (T-073)', () => {
  /** Build a tiny parent Workflow with one step that carries skill_ref. */
  function parentWf(skill_ref: string, on_failure: 'abort' | 'continue' = 'abort'): Workflow {
    return createWorkflow({
      id: 'W-parent',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref, inputs: [], outputs: [], on_failure },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
  }

  it('records child_edge on success + isolates child trace from parent visited (codex P1.3)', async () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-leaf' }))
    // Build a child Skill whose step_graph contains TWO steps so we can
    // assert the child's internal step_ids (1, 2) do NOT appear in the
    // parent's visited_step_ids — parent only sees its own step (id=10).
    const twoStepSkill = createWorkflow({
      id: 'W-leaf-2step',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      return_contract: SCHEMA_INT_VALUE,
    })
    engine.register(twoStepSkill)

    const parent = createWorkflow({
      id: 'W-isolation',
      preconditions: '',
      step_graph: [
        { step_id: 10, skill_ref: 'W-leaf-2step', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    // Dispatcher returns the validated payload only on the LAST child step
    // (terminal payload convention). Earlier child steps return arbitrary
    // outputs that are NOT validated against the schema — they're internal.
    const dispatch: ActivityDispatcher = (descriptor) => {
      if (descriptor.step_id === 2) return { kind: 'ok', outputs: [{ value: 99 }] }
      return { kind: 'ok', outputs: ['internal'] }
    }

    const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

    expect(result.state).toBe('success')
    // Parent visited contains ONLY its own step (10). Child steps (1, 2)
    // stay isolated — codex P1.3.
    expect(result.visited_step_ids).toEqual([10])
    expect(result.completed_step_ids).toEqual([10])
    // child_edges surfaces the parent→child cross-reference.
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toEqual([
      {
        step_id: 10,
        skill_ref: 'W-leaf-2step',
        child_execution_id: 'child-10-W-leaf-2step',
        validated_payload: { value: 99 },
      },
    ])
    // Parent's step_outputs records the validated payload as outputs[0].
    expect(result.step_outputs[0]?.outputs).toEqual([{ value: 99 }])
  })

  it('skill_unresolved synthesizes step failure → routed via on_failure=abort', async () => {
    const engine = new SkillEngine()
    // No registration → unresolved.
    const result = await executeStepGraph(
      parentWf('W-ghost', 'abort'),
      dispatcherWithPayload({ value: 1 }),
      { skill_engine: engine },
    )
    expect(result.state).toBe('failed')
    // failure_reason is from M5 failure-policy with the canonical errMsg
    // pinned by skill-invocation.
    expect(result.failure_reason).toContain('step:1:abort:skill_unresolved:W-ghost')
    expect(result.child_edges).toBeUndefined()
  })

  it('without options.skill_engine, step.skill_ref still flows through dispatcher (back-compat)', async () => {
    // M5 back-compat: when no SkillEngine is wired, skill_ref steps go to
    // the dispatcher exactly as before. Locks this behavior so M5 tests
    // (which don't use SkillEngine) continue to work after Group P lands.
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: ['legacy-out'] })
    const result = await executeStepGraph(parentWf('W-legacy'), dispatch /* no opts */)
    expect(result.state).toBe('success')
    expect(result.step_outputs[0]?.outputs).toEqual(['legacy-out'])
    expect(result.child_edges).toBeUndefined()
  })
})
