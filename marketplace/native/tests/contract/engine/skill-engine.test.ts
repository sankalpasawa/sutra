/**
 * SkillEngine — contract tests (M6 Group O, T-064..T-067).
 *
 * Surface under test:
 *   - SkillEngine class: register / unregister / resolve / validateOutputs
 *   - Registration-time validation per codex P1.2:
 *       (a) reuse_tag !== true     → reject
 *       (b) return_contract empty  → reject
 *       (c) return_contract not valid JSON Schema → reject
 *   - Successful register caches the compiled ajv validator (probed via
 *     validateOutputs hit/miss).
 *   - resolve(): hit returns the registered Workflow; miss returns null.
 *   - unregister(): removes registry entry AND cached validator.
 *
 * Plan: holding/plans/native-v1.0/M6-skill-engine.md Group O
 * Codex pre-dispatch: .enforcement/codex-reviews/2026-04-30-m6-plan-pre-dispatch.md
 */

import { describe, it, expect } from 'vitest'
import { SkillEngine } from '../../../src/engine/skill-engine.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import type { Workflow } from '../../../src/primitives/workflow.js'

// -----------------------------------------------------------------------------
// Test helpers
// -----------------------------------------------------------------------------

const VALID_JSON_SCHEMA = JSON.stringify({
  type: 'object',
  properties: {
    result: { type: 'string' },
    score: { type: 'number' },
  },
  required: ['result'],
  additionalProperties: false,
})

const STRICT_JSON_SCHEMA = JSON.stringify({
  type: 'object',
  properties: { value: { type: 'integer' } },
  required: ['value'],
  additionalProperties: false,
})

function makeSkill(overrides: {
  id?: string
  return_contract?: string | null
  reuse_tag?: boolean
} = {}): Workflow {
  return createWorkflow({
    id: overrides.id ?? 'W-skill-test',
    preconditions: 'true',
    step_graph: [
      { step_id: 1, action: 'terminate', inputs: [], outputs: [], on_failure: 'escalate' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'true',
    failure_policy: 'escalate',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: overrides.reuse_tag ?? true,
    return_contract:
      overrides.return_contract === undefined ? VALID_JSON_SCHEMA : overrides.return_contract,
  })
}

function makeNonSkill(): Workflow {
  return createWorkflow({
    id: 'W-not-a-skill',
    preconditions: 'true',
    step_graph: [
      { step_id: 1, skill_ref: 'noop', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'true',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    reuse_tag: false,
  })
}

/**
 * Build a Workflow whose `return_contract` is a non-empty string but NOT valid
 * JSON Schema. The createWorkflow constructor only requires non-empty string;
 * runtime JSON-Schema compilation is the SkillEngine's job.
 */
function makeSkillWithBadContract(badContract: string): Workflow {
  return makeSkill({ id: 'W-bad-contract', return_contract: badContract })
}

// -----------------------------------------------------------------------------
// Class shape
// -----------------------------------------------------------------------------

describe('SkillEngine — class shape (T-065)', () => {
  it('is a constructable class with register/unregister/resolve/validateOutputs methods', () => {
    const engine = new SkillEngine()
    expect(typeof engine.register).toBe('function')
    expect(typeof engine.unregister).toBe('function')
    expect(typeof engine.resolve).toBe('function')
    expect(typeof engine.validateOutputs).toBe('function')
  })
})

// -----------------------------------------------------------------------------
// register() — happy path + 3 rejection paths (codex P1.2, T-066)
// -----------------------------------------------------------------------------

describe('SkillEngine.register() — codex P1.2 (T-066)', () => {
  it('registers a valid Skill (reuse_tag=true + valid JSON Schema return_contract)', () => {
    const engine = new SkillEngine()
    const skill = makeSkill({ id: 'W-ok' })
    expect(() => engine.register(skill)).not.toThrow()
    expect(engine.resolve('W-ok')).toBe(skill)
  })

  it('rejects a non-Skill (reuse_tag=false)', () => {
    const engine = new SkillEngine()
    const w = makeNonSkill()
    expect(() => engine.register(w)).toThrow(/only Skills.*reuse_tag=true.*can be registered/)
  })

  it('rejects a Skill with null return_contract', () => {
    // We cannot build a Skill via createWorkflow with null return_contract
    // (the constructor enforces V2.3 §A11). But the SkillEngine MUST defend
    // against deserialized records bypassing the constructor — fabricate one.
    const engine = new SkillEngine()
    const fake: Workflow = {
      ...makeSkill({ id: 'W-no-contract' }),
      return_contract: null,
    } as Workflow
    expect(() => engine.register(fake)).toThrow(/missing return_contract/)
  })

  it('rejects a Skill whose return_contract is not parseable JSON', () => {
    const engine = new SkillEngine()
    const skill = makeSkillWithBadContract('not-json-{{')
    expect(() => engine.register(skill)).toThrow(/not valid JSON Schema/)
  })

  it('rejects a Skill whose return_contract is parseable JSON but not a valid JSON Schema', () => {
    const engine = new SkillEngine()
    // ajv.compile throws on a schema with an unknown keyword in strict mode,
    // OR on structurally invalid keyword shapes (e.g. type as a number).
    const skill = makeSkillWithBadContract(JSON.stringify({ type: 42 }))
    expect(() => engine.register(skill)).toThrow(/not valid JSON Schema/)
  })
})

// -----------------------------------------------------------------------------
// resolve() / unregister() (T-067)
// -----------------------------------------------------------------------------

describe('SkillEngine.resolve() / unregister() (T-067)', () => {
  it('resolve() returns the registered Workflow on hit', () => {
    const engine = new SkillEngine()
    const skill = makeSkill({ id: 'W-hit' })
    engine.register(skill)
    expect(engine.resolve('W-hit')).toBe(skill)
  })

  it('resolve() returns null on miss', () => {
    const engine = new SkillEngine()
    expect(engine.resolve('W-missing')).toBeNull()
  })

  it('unregister() removes the registry entry — resolve subsequently returns null', () => {
    const engine = new SkillEngine()
    const skill = makeSkill({ id: 'W-unreg' })
    engine.register(skill)
    expect(engine.resolve('W-unreg')).toBe(skill)
    engine.unregister('W-unreg')
    expect(engine.resolve('W-unreg')).toBeNull()
  })

  it('unregister() also clears the cached validator (validateOutputs no longer succeeds)', () => {
    const engine = new SkillEngine()
    const skill = makeSkill({ id: 'W-cache', return_contract: STRICT_JSON_SCHEMA })
    engine.register(skill)
    // valid output — cache hit, validator passes
    const ok = engine.validateOutputs('W-cache', { value: 42 })
    expect(ok.valid).toBe(true)
    engine.unregister('W-cache')
    const after = engine.validateOutputs('W-cache', { value: 42 })
    expect(after.valid).toBe(false)
    if (!after.valid) {
      expect(after.errors).toMatch(/no validator cached/)
    }
  })

  it('unregister() of an unknown id is a silent no-op', () => {
    const engine = new SkillEngine()
    expect(() => engine.unregister('W-never')).not.toThrow()
  })
})

// -----------------------------------------------------------------------------
// validateOutputs() — used by Group P at child completion
// -----------------------------------------------------------------------------

describe('SkillEngine.validateOutputs() — Group P seam', () => {
  it('returns {valid:true} on schema-conforming output', () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-v', return_contract: STRICT_JSON_SCHEMA }))
    const r = engine.validateOutputs('W-v', { value: 7 })
    expect(r.valid).toBe(true)
  })

  it('returns {valid:false, errors} on schema-violating output', () => {
    const engine = new SkillEngine()
    engine.register(makeSkill({ id: 'W-v', return_contract: STRICT_JSON_SCHEMA }))
    const r = engine.validateOutputs('W-v', { value: 'not-an-int' })
    expect(r.valid).toBe(false)
    if (!r.valid) {
      expect(typeof r.errors).toBe('string')
      expect(r.errors.length).toBeGreaterThan(0)
    }
  })

  it('returns {valid:false, errors:"no validator cached"} for unknown skill_ref', () => {
    const engine = new SkillEngine()
    const r = engine.validateOutputs('W-ghost', { anything: true })
    expect(r.valid).toBe(false)
    if (!r.valid) {
      expect(r.errors).toMatch(/no validator cached/)
    }
  })
})
