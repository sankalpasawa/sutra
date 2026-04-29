/**
 * skill-invocation isolation — property test (M6 Group Q, T-076).
 *
 * Codex P1.3 — child trace isolation. The parent Workflow's
 * `visited_step_ids` MUST NOT contain any step_id from the child Skill's
 * step_graph. Only the parent step that carried `skill_ref` appears in the
 * parent's visited / completed lists.
 *
 * Property (≥1000 cases): for an arbitrary parent Workflow with 1..5 steps
 * where exactly ONE carries a skill_ref pointing to a registered Skill
 * (also arbitrary, with 1..3 internal steps):
 *
 *   forall valid invocations:
 *     parent.visited_step_ids   ∩ child.step_ids = ∅   (except via different namespaces)
 *     parent.completed_step_ids ∩ child.step_ids = ∅
 *
 * Why it matters: this is the cross-cutting V2.3 §A11 guarantee that Skill
 * composition does NOT leak child-execution state into parent-execution
 * observability. A regression here would silently merge child trace into
 * parent — readers couldn't tell which step ran where, and rollback walks
 * (codex P1.1) would compensate child steps the parent never owned.
 *
 * Implementation note: parent step_ids and child step_ids share the integer
 * namespace, so set-disjoint is the meaningful invariant only when they
 * actually differ. The arbitrary picks DISJOINT id ranges for parent vs
 * child to keep the test focused on the isolation contract (not on a
 * trivially-true case where ranges coincidentally overlap with no
 * isolation).
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group Q T-076
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P1.3 + P2.3)
 *   - holding/research/2026-04-28-v2-architecture-spec.md §A11
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import type { WorkflowStep } from '../../src/types/index.js'

const PROP_RUNS = 1000

/** JSON Schema accepting an integer payload — used for child return_contract. */
const SCHEMA_INT = JSON.stringify({ type: 'integer' })

/**
 * Build a child Skill with N (1..3) `wait` steps. Child step_ids are 1..N
 * (low range). Parent step_ids in the test use a high range (100..) so the
 * isolation assertion is meaningful (no namespace coincidence).
 */
function buildChildSkill(id: string, n_steps: number): Workflow {
  const steps: WorkflowStep[] = []
  for (let i = 1; i <= n_steps; i++) {
    steps.push({
      step_id: i,
      action: 'wait',
      inputs: [],
      outputs: [],
      on_failure: 'abort',
    })
  }
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: steps,
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: true,
    return_contract: SCHEMA_INT,
  })
}

/**
 * Build a parent Workflow with M (1..5) steps. The step at `skill_ref_idx`
 * carries skill_ref → child_skill_id; every other step is an action='wait'.
 * Parent step_ids are 100..(100+M-1) to keep them disjoint from child ids.
 */
function buildParent(
  child_skill_id: string,
  m_steps: number,
  skill_ref_idx: number,
): Workflow {
  const steps: WorkflowStep[] = []
  for (let i = 0; i < m_steps; i++) {
    const step_id = 100 + i
    if (i === skill_ref_idx) {
      steps.push({
        step_id,
        skill_ref: child_skill_id,
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      })
    } else {
      steps.push({
        step_id,
        action: 'wait',
        inputs: [],
        outputs: [],
        on_failure: 'abort',
      })
    }
  }
  return createWorkflow({
    id: 'W-iso-parent',
    preconditions: '',
    step_graph: steps,
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

/**
 * Arbitrary: a (parent, child) configuration. Returns:
 *   - n_child_steps  ∈ [1..3]
 *   - m_parent_steps ∈ [1..5]
 *   - skill_ref_idx  ∈ [0..m_parent_steps-1]  (which parent step carries the ref)
 */
const configArb = fc
  .record({
    n_child_steps: fc.integer({ min: 1, max: 3 }),
    m_parent_steps: fc.integer({ min: 1, max: 5 }),
  })
  .chain((r) =>
    fc.record({
      n_child_steps: fc.constant(r.n_child_steps),
      m_parent_steps: fc.constant(r.m_parent_steps),
      skill_ref_idx: fc.integer({ min: 0, max: r.m_parent_steps - 1 }),
    }),
  )

/**
 * Dispatcher: returns an integer payload for every step. The value embeds
 * the step_id so we can detect any cross-namespace bleed in child_edges
 * vs parent step_outputs.
 */
const dispatch: ActivityDispatcher = (descriptor) => ({
  kind: 'ok',
  outputs: [descriptor.step_id], // integer → conforms to SCHEMA_INT
})

describe('skill-invocation isolation — property (≥1000 cases)', () => {
  it('parent visited/completed step_ids never contain child step_ids', async () => {
    await fc.assert(
      fc.asyncProperty(configArb, async (cfg) => {
        const child_id = 'W-iso-child'
        const child = buildChildSkill(child_id, cfg.n_child_steps)
        const parent = buildParent(child_id, cfg.m_parent_steps, cfg.skill_ref_idx)

        const engine = new SkillEngine()
        engine.register(child)

        const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

        // The set of child step_ids (1..N) is disjoint from parent step_ids
        // (100..100+M-1) by construction. Assert visited/completed contain
        // ONLY parent ids — no leakage.
        const parent_step_id_set = new Set<number>(parent.step_graph.map((s) => s.step_id))
        for (const id of result.visited_step_ids) {
          expect(parent_step_id_set.has(id)).toBe(true)
        }
        for (const id of result.completed_step_ids) {
          expect(parent_step_id_set.has(id)).toBe(true)
        }
        // Stronger: NONE of the child step_ids (1..N) appear anywhere on
        // parent's lists.
        for (let cid = 1; cid <= cfg.n_child_steps; cid++) {
          expect(result.visited_step_ids).not.toContain(cid)
          expect(result.completed_step_ids).not.toContain(cid)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('child_edges surfaces exactly the one parent step carrying skill_ref', async () => {
    await fc.assert(
      fc.asyncProperty(configArb, async (cfg) => {
        const child_id = 'W-iso-child-edge'
        const child = buildChildSkill(child_id, cfg.n_child_steps)
        const parent = buildParent(child_id, cfg.m_parent_steps, cfg.skill_ref_idx)
        const engine = new SkillEngine()
        engine.register(child)

        const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

        // Parent has exactly ONE step with skill_ref → exactly one child_edge.
        expect(result.child_edges).toBeDefined()
        expect(result.child_edges).toHaveLength(1)
        const edge = result.child_edges![0]!
        expect(edge.skill_ref).toBe(child_id)
        // The edge points at the parent step that carried skill_ref.
        const expected_parent_step_id = 100 + cfg.skill_ref_idx
        expect(edge.step_id).toBe(expected_parent_step_id)
        // Deterministic child_execution_id: child-<parent_step_id>-<skill_ref>.
        expect(edge.child_execution_id).toBe(`child-${expected_parent_step_id}-${child_id}`)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
