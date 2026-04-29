/**
 * SkillEngine registry — round-trip property test (M6 Group Q, T-076).
 *
 * Property (≥1000 cases): for an arbitrary list of N (1..10) Skills with
 * distinct ids and valid `return_contract` JSON Schemas:
 *
 *   register(S_i) for all i  →  resolve(S_i.id) === S_i
 *   unregister(S_i.id)       →  resolve(S_i.id) === null
 *
 * Locks two invariants:
 *   1. register/resolve round-trip identity (same Workflow object back).
 *   2. unregister fully purges the registry entry — subsequent resolve
 *      returns null (the canonical "miss" sentinel per codex P1.4).
 *
 * Why a property test (not just unit): the contract-test surface in
 * skill-engine.test.ts pins single-Skill cases. The property generator
 * pushes the registry through arbitrary populations (size + ordering +
 * id distribution), surfacing any hidden cross-talk between entries
 * that a fixed-fixture test wouldn't see.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M6-skill-engine.md Group Q T-076
 *   - .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md (P2.3)
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'

const PROP_RUNS = 1000

/**
 * A handful of structurally-valid JSON Schema documents. The property test
 * picks one per Skill so the cache holds heterogeneous validators —
 * forcing the registry to keep `id → validator` pairing intact under
 * arbitrary insertion orders.
 */
const SCHEMA_POOL: ReadonlyArray<string> = [
  JSON.stringify(true), // any value
  JSON.stringify({ type: 'object' }),
  JSON.stringify({ type: 'object', properties: { value: { type: 'integer' } } }),
  JSON.stringify({ type: 'string' }),
  JSON.stringify({ type: 'number' }),
  JSON.stringify({
    type: 'object',
    properties: { result: { type: 'string' } },
    required: ['result'],
    additionalProperties: false,
  }),
]

/**
 * Build a minimal Skill (Workflow with reuse_tag=true). The step_graph is a
 * single `wait` action — Group O's register doesn't dispatch the step graph,
 * so any V2.3-valid graph satisfies the validator.
 */
function buildSkill(id: string, schema: string): Workflow {
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
    return_contract: schema,
  })
}

/**
 * Arbitrary: list of 1..10 Skills with DISTINCT ids. We map indices to ids to
 * guarantee uniqueness — fast-check's set-of-strings can be slow to converge
 * with Workflow.id pattern (W-<...>).
 */
const skillsArb: fc.Arbitrary<Workflow[]> = fc
  .integer({ min: 1, max: 10 })
  .chain((n) =>
    fc
      .array(fc.integer({ min: 0, max: SCHEMA_POOL.length - 1 }), {
        minLength: n,
        maxLength: n,
      })
      .map((schemaIdxs) =>
        schemaIdxs.map((idx, i) => buildSkill(`W-prop-${i}`, SCHEMA_POOL[idx]!)),
      ),
  )

describe('SkillEngine registry — round-trip property (≥1000 cases)', () => {
  it('register all → resolve each returns the registered Skill (identity)', () => {
    fc.assert(
      fc.property(skillsArb, (skills: Workflow[]) => {
        const engine = new SkillEngine()
        for (const s of skills) engine.register(s)
        for (const s of skills) {
          expect(engine.resolve(s.id)).toBe(s)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('unregister all → resolve each returns null', () => {
    fc.assert(
      fc.property(skillsArb, (skills: Workflow[]) => {
        const engine = new SkillEngine()
        for (const s of skills) engine.register(s)
        for (const s of skills) engine.unregister(s.id)
        for (const s of skills) {
          expect(engine.resolve(s.id)).toBeNull()
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('register → unregister → register replaces the prior validator (overwrite is idempotent)', () => {
    fc.assert(
      fc.property(skillsArb, (skills: Workflow[]) => {
        const engine = new SkillEngine()
        for (const s of skills) engine.register(s)
        // Cycle every skill through unregister + re-register; final resolve
        // must still match the registered instance (locks Map.set semantics
        // pinned in T-074).
        for (const s of skills) {
          engine.unregister(s.id)
          engine.register(s)
        }
        for (const s of skills) {
          expect(engine.resolve(s.id)).toBe(s)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
