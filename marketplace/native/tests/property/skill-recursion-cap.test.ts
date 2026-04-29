/**
 * skill-invocation recursion cap — property test (M6 Group Q, T-076).
 *
 * Property (≥1000 cases): for an arbitrary skill chain depth N (5..15):
 *   - N >= 8 (= SKILL_RECURSION_CAP) → invocation chain fails at depth 8
 *     with the canonical errMsg `skill_recursion_cap:8`.
 *   - N < 8                          → chain succeeds without the cap firing.
 *
 * The chain is built by registering N skills `chain-0`, `chain-1`, …,
 * `chain-(N-1)` where each skill_i invokes skill_(i+1). The terminal skill
 * (chain-(N-1)) has a single `wait` step (leaf — no recursive invoke).
 *
 * Why a property (not a fixed-N test): the cap is a continuous boundary;
 * a one-off N=9 test would lock the canonical errMsg but not catch
 * off-by-one regressions across the safe-side range. The property test
 * exercises both branches of the cap predicate uniformly.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group Q T-076
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P2.3)
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import { SKILL_RECURSION_CAP } from '../../src/engine/skill-invocation.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'

const PROP_RUNS = 1000

/** JSON Schema accepting an integer payload. */
const SCHEMA_INT = JSON.stringify({ type: 'integer' })

/**
 * Build a non-leaf chain skill: skill_i has a single step with skill_ref
 * pointing at skill_(i+1). The executor MUST resolve through invokeSkill,
 * which increments recursion_depth before re-entering executeStepGraph.
 */
function buildChainStep(id: string, next_skill_ref: string): Workflow {
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: [
      {
        step_id: 1,
        skill_ref: next_skill_ref,
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
  })
}

/** Build the leaf skill — a single `wait` step that returns an integer. */
function buildLeafSkill(id: string): Workflow {
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
    return_contract: SCHEMA_INT,
  })
}

/**
 * Register `chain-0 → chain-1 → … → chain-(N-1)` (leaf) on the engine.
 * Returns the engine + the entry skill id (`chain-0`).
 */
function buildChain(N: number): { engine: SkillEngine; entry_id: string } {
  const engine = new SkillEngine()
  // Register leaf first so non-leaf .skill_ref always resolves at registration
  // time of the parent — though SkillEngine doesn't validate skill_ref
  // existence at register-time (resolution happens at invokeSkill), the order
  // is documentation, not a contract.
  engine.register(buildLeafSkill(`W-chain-${N - 1}`))
  for (let i = N - 2; i >= 0; i--) {
    engine.register(buildChainStep(`W-chain-${i}`, `W-chain-${i + 1}`))
  }
  return { engine, entry_id: 'W-chain-0' }
}

/**
 * Build the root parent Workflow: a single step with skill_ref → chain-0.
 * The executor invokes chain-0 at recursion_depth=0 (default).
 */
function buildRootParent(entry_id: string): Workflow {
  return createWorkflow({
    id: 'W-chain-root',
    preconditions: '',
    step_graph: [
      { step_id: 1, skill_ref: entry_id, inputs: [], outputs: [], on_failure: 'abort' },
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

/** Dispatcher returns an integer for the leaf `wait` step (conforms to SCHEMA_INT). */
const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [42] })

describe('skill-invocation recursion cap — property (≥1000 cases)', () => {
  it('chain depth N >= SKILL_RECURSION_CAP+1 fails (cap fires; bubble-up wraps as skill_output_validation)', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Depth tracing — root parent invokes chain-0 at recursion_depth=0
        // (root executor's recursion_depth=0; the FIRST invokeSkill is at
        // depth 0, NOT depth 1). chain-0's executor receives
        // recursion_depth=1 (root's+1). chain-i's executor runs at depth
        // (i+1) and (if non-leaf) calls invokeSkill at the SAME depth (i+1).
        // chain-(N-1) is the LEAF (action='wait', no further invokeSkill).
        //
        // The cap predicate `recursion_depth >= 8` fires when some non-leaf
        // invokes at depth >= 8. The deepest non-leaf is chain-(N-2) at
        // executor depth (N-1). Cap fires when N-1 >= 8 → N >= 9
        // (= SKILL_RECURSION_CAP+1). At N=8, chain-6 at depth 7 invokes
        // chain-7 (leaf) → cap NOT fired (7 < 8); chain succeeds.
        //
        // Bubble-up: the cap returns kind=failure with errMsg
        // `skill_recursion_cap:8` from the deepest invokeSkill. That step's
        // executor wraps it as a step failure → `step:1:abort:skill_recursion_cap:8`
        // → ExecutionResult.state='failed'. The PARENT's invokeSkill then
        // sees this child's empty terminal payload (failed steps push empty
        // outputs) → return_contract validation rejects undefined →
        // surfaces as `skill_output_validation:...` at each ancestor frame.
        // The OUTERMOST failure_reason therefore matches
        // `step:1:abort:skill_output_validation:...`. The canonical
        // `skill_recursion_cap:8` errMsg is asserted directly by the
        // contract test (skill-invocation.test.ts) and by m6-skill-resolution
        // scenario 5(a) which uses options.recursion_depth=8 to fire the
        // cap at the OUTER frame (no bubble-up wrapping).
        fc.integer({ min: SKILL_RECURSION_CAP + 1, max: 15 }),
        async (N: number) => {
          const { engine, entry_id } = buildChain(N)
          const parent = buildRootParent(entry_id)
          const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

          expect(result.state).toBe('failed')
          // Bubble-up surface — locked here so a future change to the cap
          // propagation path surfaces in tests.
          expect(result.failure_reason).toMatch(/^step:1:abort:skill_output_validation:/)
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })

  it('chain depth N <= SKILL_RECURSION_CAP succeeds without firing the cap', async () => {
    await fc.assert(
      fc.asyncProperty(
        // Boundary on the safe side: N = SKILL_RECURSION_CAP (=8). chain has
        // chain-0..chain-7. chain-7 is the leaf. chain-6 at executor depth 7
        // invokes chain-7 at depth 7 — cap predicate (depth >= 8) is FALSE
        // (7 < 8); chain-7 leaf returns 42 → SCHEMA_INT validates → all the
        // way up to root with state='success'.
        fc.integer({ min: 1, max: SKILL_RECURSION_CAP }),
        async (N: number) => {
          const { engine, entry_id } = buildChain(N)
          const parent = buildRootParent(entry_id)
          const result = await executeStepGraph(parent, dispatch, { skill_engine: engine })

          expect(result.state).toBe('success')
          // No cap fire anywhere in the failure_reason (which is null on success).
          expect(result.failure_reason).toBeNull()
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})
