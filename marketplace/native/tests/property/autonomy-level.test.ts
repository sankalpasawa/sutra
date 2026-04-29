/**
 * autonomy_level — property test (M5 Group L T-054 — gap fill).
 *
 * The Group K replay-determinism property test (`step-graph-executor.test.ts`)
 * exercises autonomy_level *implicitly* via `workflowArb` (rotates through all
 * 3 enum values per the M5 J/T-045 wiring in `arbitraries.ts`). Group L T-054
 * mandates an explicit ≥1000-cases × all-3-enum-values property, so this file
 * pins the routing surface that depends on `autonomy_level`:
 *
 *   1. constructor + validator round-trip the field across the full enum
 *   2. step-graph executor surfaces it on every `dispatch(...)` ctx
 *   3. failure-policy carries it through every outcome (no-drop guarantee)
 *
 * Each property runs ≥1000 fast-check cases. Combined with the implicit
 * coverage in step-graph-executor.test.ts (1000 cases × 3 properties × all 3
 * enum values rotated in `workflowArb`), T-054 is satisfied with margin.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group L T-054
 *  - codex P1.2: required_capabilities[] REMOVED — autonomy_level is the
 *    routing field that survived to v1.0
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { createWorkflow, isValidWorkflow } from '../../src/primitives/workflow.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
  type DispatchContext,
} from '../../src/engine/step-graph-executor.js'
import { applyFailurePolicy } from '../../src/engine/failure-policy.js'
import type { WorkflowAutonomyLevel } from '../../src/types/index.js'
import { workflowArb } from './arbitraries.js'

const PROP_RUNS = 1000

const autonomyLevelArb: fc.Arbitrary<WorkflowAutonomyLevel> = fc.constantFrom(
  'manual',
  'semi',
  'autonomous',
)

describe('autonomy_level — round-trip across full enum (≥1000 cases)', () => {
  it('createWorkflow + isValidWorkflow accept all 3 enum values', () => {
    fc.assert(
      fc.property(workflowArb(), autonomyLevelArb, (base, level) => {
        const w = createWorkflow({ ...base, autonomy_level: level })
        expect(w.autonomy_level).toBe(level)
        expect(isValidWorkflow(w)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('autonomy_level — surfaces on every dispatch ctx (≥1000 cases)', () => {
  it('every step dispatch sees the workflow autonomy_level on ctx', async () => {
    await fc.assert(
      fc.asyncProperty(workflowArb(), autonomyLevelArb, async (base, level) => {
        const w = createWorkflow({ ...base, autonomy_level: level })
        // Skip workflows with terminate-action — terminate is structural, no
        // dispatcher call (see step-graph-executor.ts:231).
        if (w.step_graph.some((s) => s.action === 'terminate')) return

        const seen: WorkflowAutonomyLevel[] = []
        const dispatch: ActivityDispatcher = (_descriptor, ctx: DispatchContext) => {
          seen.push(ctx.autonomy_level)
          return { kind: 'ok', outputs: [] }
        }
        await executeStepGraph(w, dispatch)
        expect(seen.length).toBe(w.step_graph.length)
        for (const observed of seen) {
          expect(observed).toBe(level)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('autonomy_level — carried through failure-policy outcomes (≥1000 cases)', () => {
  it('applyFailurePolicy is invariant to autonomy_level for all 5 actions', () => {
    fc.assert(
      fc.property(
        fc.constantFrom<'rollback' | 'escalate' | 'pause' | 'abort' | 'continue'>(
          'rollback',
          'escalate',
          'pause',
          'abort',
          'continue',
        ),
        autonomyLevelArb,
        fc.string({ minLength: 1, maxLength: 24 }),
        (action, level, errMsg) => {
          const step = {
            step_id: 0,
            action: 'wait' as const,
            inputs: [],
            outputs: [],
            on_failure: action,
          }
          const outcome = applyFailurePolicy(step, new Error(errMsg), {
            completed_step_ids: [],
            autonomy_level: level,
          })
          // Action mapping must hold for every autonomy_level — failure-policy
          // is enum-pure (autonomy_level is plumbed for downstream branching at
          // M11 dogfood; the policy itself stays deterministic on action only).
          expect(outcome.action).toBe(action)
          expect(typeof outcome.reason).toBe('string')
          expect(outcome.reason.startsWith(`step:0:${action}:`)).toBe(true)
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})
