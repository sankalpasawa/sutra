/**
 * DecisionProvenance contract tests — M4.3 (D2 §2.1).
 *
 * Per M4.3.6: 13 per-field tests (one per field; round-trip + invalid-input
 * rejection).
 */

import { describe, expect, it } from 'vitest'
import {
  DecisionProvenanceSchema,
  createDecisionProvenance,
  isValidDecisionProvenance,
  type DecisionProvenance,
} from '../../../src/schemas/decision-provenance.js'
import * as DPFx from '../../fixtures/decision-provenance.fixture.js'

function base(): DecisionProvenance {
  return DPFx.validMinimal()
}

describe('DecisionProvenance — D2 §2.1 schema', () => {
  it('fixtures: validMinimal + validFull round-trip', () => {
    const a = createDecisionProvenance(DPFx.validMinimal())
    expect(isValidDecisionProvenance(a)).toBe(true)
    const b = createDecisionProvenance(DPFx.validFull())
    expect(isValidDecisionProvenance(b)).toBe(true)
  })

  it('fixtures: invalidMissingRequired throws', () => {
    expect(() =>
      // @ts-expect-error — fixture intentionally missing required field
      createDecisionProvenance(DPFx.invalidMissingRequired()),
    ).toThrow()
  })

  // ---- 13 per-field contract tests ----

  it('field 1/13: id round-trips and rejects malformed (no dp- prefix)', () => {
    const v = createDecisionProvenance({ ...base(), id: 'dp-abc123' })
    expect(v.id).toBe('dp-abc123')
    expect(() => createDecisionProvenance({ ...base(), id: 'bad-prefix' })).toThrow()
    expect(() => createDecisionProvenance({ ...base(), id: 'dp-XYZ' })).toThrow()
  })

  it('field 2/13: actor round-trips and rejects empty', () => {
    const v = createDecisionProvenance({ ...base(), actor: 'sutra-ceo' })
    expect(v.actor).toBe('sutra-ceo')
    expect(() => createDecisionProvenance({ ...base(), actor: '' })).toThrow()
  })

  it('field 3/13: agent_identity round-trips and rejects wrong-prefix id', () => {
    const v = createDecisionProvenance({
      ...base(),
      agent_identity: { kind: 'codex', id: 'codex:s1' },
    })
    expect(v.agent_identity.kind).toBe('codex')
    expect(() =>
      createDecisionProvenance({
        ...base(),
        // claim claude-opus but use codex prefix
        agent_identity: { kind: 'claude-opus', id: 'codex:s1' } as never,
      }),
    ).toThrow()
  })

  it('field 4/13: timestamp round-trips and rejects non-ISO', () => {
    const v = createDecisionProvenance({
      ...base(),
      timestamp: '2026-04-29T12:00:00.000Z',
    })
    expect(v.timestamp).toBe('2026-04-29T12:00:00.000Z')
    expect(() =>
      createDecisionProvenance({ ...base(), timestamp: 'not-a-date' }),
    ).toThrow()
  })

  it('field 5/13: evidence round-trips (empty + populated)', () => {
    const empty = createDecisionProvenance({ ...base(), evidence: [] })
    expect(empty.evidence).toEqual([])
    const populated = createDecisionProvenance({
      ...base(),
      evidence: [
        {
          kind: 'json',
          schema_ref: 'native://x',
          locator: '/x',
          version: '1',
          mutability: 'immutable',
          retention: '30d',
        },
      ],
    })
    expect(populated.evidence).toHaveLength(1)
    // invalid evidence shape rejected
    expect(() =>
      createDecisionProvenance({
        ...base(),
        evidence: [{ kind: '', schema_ref: '', locator: '', version: '', mutability: 'immutable', retention: '' }],
      }),
    ).toThrow()
  })

  it('field 6/13: authority_id round-trips and rejects empty', () => {
    const v = createDecisionProvenance({ ...base(), authority_id: 'A-1' })
    expect(v.authority_id).toBe('A-1')
    expect(() => createDecisionProvenance({ ...base(), authority_id: '' })).toThrow()
  })

  it('field 7/13: policy_id round-trips and rejects empty', () => {
    const v = createDecisionProvenance({ ...base(), policy_id: 'PROTO-021' })
    expect(v.policy_id).toBe('PROTO-021')
    expect(() => createDecisionProvenance({ ...base(), policy_id: '' })).toThrow()
  })

  it('field 8/13: policy_version round-trips and rejects empty (F-8 partial)', () => {
    const v = createDecisionProvenance({ ...base(), policy_version: 'v1.2' })
    expect(v.policy_version).toBe('v1.2')
    expect(() => createDecisionProvenance({ ...base(), policy_version: '' })).toThrow()
  })

  it('field 9/13: confidence accepts 0/0.5/1; rejects -0.1 / 1.01', () => {
    expect(createDecisionProvenance({ ...base(), confidence: 0 }).confidence).toBe(0)
    expect(createDecisionProvenance({ ...base(), confidence: 0.5 }).confidence).toBe(0.5)
    expect(createDecisionProvenance({ ...base(), confidence: 1 }).confidence).toBe(1)
    expect(() => createDecisionProvenance({ ...base(), confidence: -0.1 })).toThrow()
    expect(() => createDecisionProvenance({ ...base(), confidence: 1.01 })).toThrow()
  })

  it('field 10/13: decision_kind accepts every D1 enum; rejects unknown', () => {
    const kinds = [
      'DECIDE',
      'EXECUTE',
      'OVERRIDE',
      'APPROVE',
      'REJECT',
      'DELEGATE',
      'TERMINATE',
    ] as const
    for (const k of kinds) {
      const v = createDecisionProvenance({ ...base(), decision_kind: k })
      expect(v.decision_kind).toBe(k)
    }
    expect(() =>
      // @ts-expect-error — invalid enum
      createDecisionProvenance({ ...base(), decision_kind: 'GUESS' }),
    ).toThrow()
  })

  it('field 11/13: scope accepts every D1 enum; rejects unknown', () => {
    const scopes = [
      'CONSTITUTIONAL',
      'DOMAIN',
      'CHARTER',
      'TENANT',
      'WORKFLOW',
      'EXECUTION',
      'HOOK',
    ] as const
    for (const s of scopes) {
      const v = createDecisionProvenance({ ...base(), scope: s })
      expect(v.scope).toBe(s)
    }
    expect(() =>
      // @ts-expect-error — invalid enum
      createDecisionProvenance({ ...base(), scope: 'PLANET' }),
    ).toThrow()
  })

  it('field 12/13: outcome round-trips and rejects empty', () => {
    const v = createDecisionProvenance({ ...base(), outcome: 'approved' })
    expect(v.outcome).toBe('approved')
    expect(() => createDecisionProvenance({ ...base(), outcome: '' })).toThrow()
  })

  it('field 13/13: next_action_ref accepts dp-/W-/null; rejects others', () => {
    const a = createDecisionProvenance({ ...base(), next_action_ref: null })
    expect(a.next_action_ref).toBeNull()
    const b = createDecisionProvenance({ ...base(), next_action_ref: 'dp-abc' })
    expect(b.next_action_ref).toBe('dp-abc')
    const c = createDecisionProvenance({ ...base(), next_action_ref: 'W-abc' })
    expect(c.next_action_ref).toBe('W-abc')
    expect(() =>
      // @ts-expect-error — invalid string for the union
      createDecisionProvenance({ ...base(), next_action_ref: 'X-abc' }),
    ).toThrow()
  })

  // ---- Aggregate edge cases (M4.3.6) ----

  it('round-trip via JSON.stringify → schema.parse preserves all fields', () => {
    const v = createDecisionProvenance(DPFx.validFull())
    const parsed = DecisionProvenanceSchema.parse(JSON.parse(JSON.stringify(v)))
    expect(parsed).toEqual(v)
  })

  it('isValidDecisionProvenance rejects non-objects', () => {
    expect(isValidDecisionProvenance(null)).toBe(false)
    expect(isValidDecisionProvenance('dp-abc')).toBe(false)
    expect(isValidDecisionProvenance(42)).toBe(false)
  })
})
