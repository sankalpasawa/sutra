/**
 * M6 Skill resolution — integration scenarios (M6 Group Q, T-077).
 *
 * Five codex-mandated scenarios per .enforcement/codex-reviews/2026-04-30-
 * m6-plan-pre-dispatch.md (P2.3 — scenario coverage emphasis):
 *
 *   1. child miss + continue                       (codex P1.4 invariant)
 *   2. parent rollback after prior child success   (M5 P1.1 visited/completed split)
 *   3. invalid return_contract at registration     (codex P1.2)
 *   4. child trace isolation                       (codex P1.3)
 *   5. recursion depth cap                         (recursion_depth >= 8)
 *
 * Each scenario is a single integration `it(...)` block that wires the public
 * surface (SkillEngine + executeStepGraph) end-to-end. These are the M6
 * acceptance gate per the plan; do NOT remove or relax assertions without
 * updating the codex review record + plan A-criteria.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group Q T-077
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P1.x + P2.3)
 *   - holding/research/2026-04-28-v2-architecture-spec.md §A11
 */

import { describe, it, expect } from 'vitest'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import { SKILL_RECURSION_CAP } from '../../src/engine/skill-invocation.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import type { WorkflowStep } from '../../src/types/index.js'

// =============================================================================
// Helpers — keep scenarios readable; one fixture per role.
// =============================================================================

const SCHEMA_INT = JSON.stringify({ type: 'integer' })
const SCHEMA_OBJ_VALUE = JSON.stringify({
  type: 'object',
  properties: { value: { type: 'integer' } },
  required: ['value'],
  additionalProperties: false,
})

/** Single-step `wait` Skill returning an integer. */
function leafSkill(id: string, contract: string = SCHEMA_INT): Workflow {
  return createWorkflow({
    id,
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
    reuse_tag: true,
    return_contract: contract,
  })
}

// =============================================================================
// Scenario 1 — child miss + continue (codex P1.4)
// =============================================================================

describe('M6 scenarios — 1. child miss + continue (codex P1.4)', () => {
  it('parent step with skill_ref to unregistered Skill + on_failure=continue advances; partial=true', async () => {
    // Parent: 3 steps. step1=action wait (success), step2=skill_ref to an
    // UNREGISTERED Skill with on_failure='continue', step3=action wait (success).
    const parent = createWorkflow({
      id: 'W-miss-continue',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        {
          step_id: 2,
          skill_ref: 'unregistered_skill',
          inputs: [],
          outputs: [],
          on_failure: 'continue',
        },
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

    const engine = new SkillEngine() // empty
    const dispatch: ActivityDispatcher = (descriptor) => ({
      kind: 'ok',
      outputs: [`out-${descriptor.step_id}`],
    })

    const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

    // continue: state stays success; partial=true; failure_reason is null on
    // success path even though step 2 failed (continue is non-fatal in M5
    // contract; the failed step's reason is captured in step_outputs only).
    expect(result.state).toBe('success')
    expect(result.partial).toBe(true)
    // Visited covers all three; completed excludes step 2 (codex P1.1 split).
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    expect(result.completed_step_ids).toEqual([1, 3])
    // Step 2's output entry: empty outputs + output_validation_skipped=true.
    const step2 = result.step_outputs.find((s) => s.step_id === 2)
    expect(step2).toBeDefined()
    expect(step2!.output_validation_skipped).toBe(true)
    expect(step2!.outputs).toEqual([])
    // No child_edges populated (the miss never produced a successful invocation).
    expect(result.child_edges).toBeUndefined()
  })
})

// =============================================================================
// Scenario 2 — parent rollback after prior child success (M5 P1.1 carried forward)
// =============================================================================

describe('M6 scenarios — 2. parent rollback after prior child success', () => {
  it('child success → child_edge recorded; subsequent failed step routes rollback over completed (excluding failed step)', async () => {
    // Register a Skill 'W-compute' that returns a valid integer payload.
    // (Workflow.id MUST match W-<...> pattern per V2 §1 P3.)
    const engine = new SkillEngine()
    engine.register(leafSkill('W-compute'))

    // Parent: 3 steps.
    //   step 1: skill_ref='W-compute'           → success; child_edge appended.
    //   step 2: action='wait', on_failure='rollback' → fails; routes rollback.
    //   step 3: action='wait'                   → never reached.
    const parent = createWorkflow({
      id: 'W-rollback-after-skill',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-compute', inputs: [], outputs: [], on_failure: 'abort' },
        { step_id: 2, action: 'wait', inputs: [], outputs: [], on_failure: 'rollback' },
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

    // Dispatcher: child Skill leaf returns 7 (integer; passes SCHEMA_INT).
    // Parent step 2 (action='wait') is dispatched too — fail it.
    const dispatch: ActivityDispatcher = (descriptor) => {
      if (descriptor.action === 'wait' && descriptor.step_id === 2) {
        return { kind: 'failure', error: new Error('parent-step-2-fail') }
      }
      // Both the leaf Skill's wait step (step_id=1 inside child) AND parent
      // step 3 if reached: succeed with an integer.
      return { kind: 'ok', outputs: [7] }
    }

    const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

    // rollback → state=failed; failure_reason carries M5 canonical wrapping.
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('step:2:rollback:parent-step-2-fail')
    // Compensation walks ONLY successful effects (codex P1.1) — step 1
    // (the skill invocation) succeeded and is in the completed list; step 2
    // (the failed step) is NOT. compensation_order is the reversed completed.
    expect(result.rollback_compensations).toEqual([1])
    // child_edge for the successful Skill invocation surfaces even though
    // the parent ultimately failed downstream — observability MUST capture
    // the work that did happen.
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toHaveLength(1)
    expect(result.child_edges![0]!.skill_ref).toBe('W-compute')
    expect(result.child_edges![0]!.step_id).toBe(1)
    // Visited covers steps 1 (skill) + 2 (failed); completed = [1] only.
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.completed_step_ids).toEqual([1])
  })
})

// =============================================================================
// Scenario 3 — invalid return_contract at registration (codex P1.2)
// =============================================================================

describe('M6 scenarios — 3. invalid return_contract at registration', () => {
  it('register() throws with "not valid JSON Schema" for malformed JSON', () => {
    const engine = new SkillEngine()
    // Workflow primitive accepts the string; SkillEngine compiles it via ajv
    // and throws when JSON.parse fails. Per Group O T-066 implementation.
    const skill = createWorkflow({
      id: 'W-bad-json',
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
      reuse_tag: true,
      return_contract: '{not valid json',
    })
    expect(() => engine.register(skill)).toThrow(/not valid JSON Schema/)
  })

  it('register() throws for parseable JSON but invalid JSON Schema document (e.g. type as a number)', () => {
    const engine = new SkillEngine()
    const skill = createWorkflow({
      id: 'W-bad-schema',
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
      reuse_tag: true,
      // Parseable JSON, but `type: 42` is not a valid JSON Schema type
      // — ajv.compile rejects.
      return_contract: JSON.stringify({ type: 42 }),
    })
    expect(() => engine.register(skill)).toThrow(/not valid JSON Schema/)
  })
})

// =============================================================================
// Scenario 4 — child trace isolation (codex P1.3)
// =============================================================================

describe('M6 scenarios — 4. child trace isolation (codex P1.3)', () => {
  it('parent visited/completed/step_outputs do NOT contain any child internal step_ids', async () => {
    // Child Skill with FIVE internal steps (step_ids 1..5). Parent's only
    // step has step_id=10. After invocation, parent.visited/completed must
    // contain ONLY 10 — the child's 1..5 are isolated to the child execution.
    const childSteps: WorkflowStep[] = []
    for (let i = 1; i <= 5; i++) {
      childSteps.push({
        step_id: i,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      })
    }
    const child = createWorkflow({
      id: 'W-iso-5step',
      preconditions: '',
      step_graph: childSteps,
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      return_contract: SCHEMA_OBJ_VALUE,
    })

    const parent = createWorkflow({
      id: 'W-iso-parent',
      preconditions: '',
      step_graph: [
        { step_id: 10, skill_ref: 'W-iso-5step', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const engine = new SkillEngine()
    engine.register(child)

    // Dispatcher: the LAST child step (step_id=5) emits the validated payload.
    // Earlier child steps emit arbitrary internal outputs that are NOT
    // validated against the schema (per Group P extractTerminalPayload).
    const dispatch: ActivityDispatcher = (descriptor) => {
      if (descriptor.step_id === 5) return { kind: 'ok', outputs: [{ value: 99 }] }
      return { kind: 'ok', outputs: ['internal'] }
    }

    const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

    expect(result.state).toBe('success')
    // Parent's lists contain ONLY its own step (10).
    expect(result.visited_step_ids).toEqual([10])
    expect(result.completed_step_ids).toEqual([10])
    // None of child's 1..5 leaked into parent's visited/completed.
    for (let cid = 1; cid <= 5; cid++) {
      expect(result.visited_step_ids).not.toContain(cid)
      expect(result.completed_step_ids).not.toContain(cid)
    }
    // step_outputs has exactly ONE entry (the parent step) — child internal
    // step outputs are NOT in the parent's step_outputs list.
    expect(result.step_outputs).toHaveLength(1)
    expect(result.step_outputs[0]!.step_id).toBe(10)
    expect(result.step_outputs[0]!.outputs).toEqual([{ value: 99 }])
    // child_edge surfaces with the validated payload + deterministic id.
    expect(result.child_edges).toEqual([
      {
        step_id: 10,
        skill_ref: 'W-iso-5step',
        child_execution_id: 'child-10-W-iso-5step',
        validated_payload: { value: 99 },
      },
    ])
  })
})

// =============================================================================
// Scenario 5 — recursion depth cap fires at 8
// =============================================================================

describe('M6 scenarios — 5. recursion depth cap', () => {
  // Two complementary integration tests pin the cap surface:
  //   (a) Direct: parent executor receives recursion_depth = SKILL_RECURSION_CAP
  //       via options; the FIRST invokeSkill call is at-cap → canonical
  //       errMsg `skill_recursion_cap:8` is preserved in failure_reason.
  //   (b) Chain: a 10-skill chain (a..j) is built so the cap fires DEEP in
  //       the recursion. The cap message is wrapped by the chain's
  //       failure-policy bubble-up (each ancestor's invokeSkill sees the
  //       child's empty terminal payload → skill_output_validation), but the
  //       canonical contract is "the chain fails" — that is the load-bearing
  //       observable invariant. The exact wrapped errMsg shape is asserted
  //       here so a future change to the bubble-up format surfaces in tests.

  it('(a) direct: at-cap recursion_depth fires immediately with canonical errMsg', async () => {
    // Depth math: parent executor with options.recursion_depth = 8 calls
    // invokeSkill at depth 8 on the FIRST skill_ref step → cap predicate
    // (`recursion_depth >= 8`) fires immediately → `skill_recursion_cap:8`
    // is the InvokeSkill failure errMsg → routed via on_failure='abort' →
    // failure_reason = `step:1:abort:skill_recursion_cap:8`. No wrapping.
    const engine = new SkillEngine()
    engine.register(leafSkill('W-skill-cap-leaf'))
    const parent = createWorkflow({
      id: 'W-cap-direct',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-skill-cap-leaf', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [42] })
    const result = await executeStepGraph(parent, dispatch, {
      skill_engine: engine,
      recursion_depth: SKILL_RECURSION_CAP,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe(`step:1:abort:skill_recursion_cap:${SKILL_RECURSION_CAP}`)
  })

  it('(b) chain: 10-skill chain (a..j) propagates a cap fire as a failed execution', async () => {
    // Codex P2.3 mandate: cap fires at depth 8. Depth math (1-step-per-skill
    // chain at root recursion_depth=0): chain[i]'s executor runs at depth
    // (i+1) and (if non-leaf) invokes chain[i+1] at depth (i+1). For the cap
    // (`recursion_depth >= 8`) to fire, some non-leaf must invoke at depth
    // 8 → that non-leaf is at index 7 (the 8th skill). With 10 skills total
    // (8 non-leaves + 1 invoking-leaf-position + 1 leaf), the cap fires when
    // chain[8]'s executor (depth 8) attempts to invoke chain[9].
    //
    // Bubble-up: the cap message is wrapped by each ancestor's invokeSkill
    // (which sees the child's empty terminal payload + fails return_contract
    // validation → `skill_output_validation:...`). The OUTER failure_reason
    // carries the wrapped form. We assert state='failed' (the load-bearing
    // invariant) and that the failure surfaced through return_contract
    // validation (the documented bubble-up shape). A direct cap test (above)
    // pins the canonical errMsg surface separately.
    const engine = new SkillEngine()
    const ids = [
      'W-skill-a', 'W-skill-b', 'W-skill-c', 'W-skill-d', 'W-skill-e',
      'W-skill-f', 'W-skill-g', 'W-skill-h', 'W-skill-i', 'W-skill-j',
    ]
    engine.register(leafSkill(ids[ids.length - 1]!))
    for (let i = ids.length - 2; i >= 0; i--) {
      engine.register(
        createWorkflow({
          id: ids[i]!,
          preconditions: '',
          step_graph: [
            {
              step_id: 1,
              skill_ref: ids[i + 1]!,
              inputs: [],
              outputs: [],
              on_failure: 'abort',
            },
          ],
          inputs: [],
          outputs: [],
          state: [],
          postconditions: '',
          failure_policy: 'abort',
          stringency: 'task',
          interfaces_with: [],
          reuse_tag: true,
          return_contract: SCHEMA_INT,
        }),
      )
    }

    const parent = createWorkflow({
      id: 'W-cap-parent',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-skill-a', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [42] })
    const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

    expect(result.state).toBe('failed')
    // Bubble-up: each ancestor's invokeSkill saw the failed child's empty
    // terminal payload → return_contract validation rejected `undefined` as
    // not-an-integer → wraps as `skill_output_validation:`. The outermost
    // failure_reason is therefore step:1:abort:skill_output_validation:...
    expect(result.failure_reason).toMatch(/^step:1:abort:skill_output_validation:/)
  })
})
