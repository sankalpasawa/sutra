/**
 * CutoverContract contract tests — M4.7 (D1 §11.1 + D3 §3.3).
 *
 * 4 contract tests per TASK-QUEUE.md §1 T-009:
 *   1) null default applied via Charter constructor (no cutover_contract supplied)
 *   2) full record round-trips through createCutoverContract + Charter
 *   3) empty behavior_invariants array rejected when contract is set
 *   4) invalid types rejected (e.g. number for source_engine)
 *
 * Plus aggregate guards (isValid for null + full; CutoverContractSchema parse
 * round-trip via JSON.stringify) so the schema is exhausively covered at the
 * boundary it ships.
 */

import { describe, expect, it } from 'vitest'
import {
  CutoverContractSchema,
  createCutoverContract,
  isValidCutoverContract,
  type CutoverContract,
} from '../../../src/schemas/cutover-contract.js'
import {
  createCharter,
  isValidCharter,
} from '../../../src/primitives/charter.js'

/**
 * Returns the non-null variant explicitly so spreads stay well-typed at the
 * field-mutation sites below (CutoverContract = T | null which makes spread
 * unsound otherwise).
 */
function fullCutover(): NonNullable<CutoverContract> {
  return {
    source_engine: 'sutra-core-v2.8',
    target_engine: 'sutra-native-v1.0',
    behavior_invariants: ['no_data_loss', 'latency_within_5_percent'],
    rollback_gate: 'error_rate > 0.01',
    canary_window: '7d',
  }
}

function baseCharterFields() {
  return {
    id: 'C-cutover-test',
    purpose: 'cutover contract test charter',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [],
    acl: [],
  }
}

describe('CutoverContract — D1 §11.1 schema (M4.7)', () => {
  // ---- 4 atomic contract tests per T-009 ----

  it('1/4: null default applied when Charter has no cutover_contract', () => {
    const c = createCharter(baseCharterFields())
    expect(c.cutover_contract).toBeNull()
  })

  it('2/4: full record round-trips through createCutoverContract + Charter', () => {
    const cc = createCutoverContract(fullCutover())
    expect(cc).not.toBeNull()
    expect(cc?.source_engine).toBe('sutra-core-v2.8')
    expect(cc?.target_engine).toBe('sutra-native-v1.0')
    expect(cc?.behavior_invariants).toHaveLength(2)
    expect(cc?.rollback_gate).toBe('error_rate > 0.01')
    expect(cc?.canary_window).toBe('7d')

    const charter = createCharter({
      ...baseCharterFields(),
      cutover_contract: fullCutover(),
    })
    expect(charter.cutover_contract).toEqual(fullCutover())
  })

  it('3/4: empty behavior_invariants array rejected when contract is set', () => {
    expect(() =>
      createCutoverContract({ ...fullCutover(), behavior_invariants: [] }),
    ).toThrow()
    expect(() =>
      createCharter({
        ...baseCharterFields(),
        cutover_contract: { ...fullCutover(), behavior_invariants: [] },
      }),
    ).toThrow()
  })

  it('4/4: invalid types rejected (number for source_engine)', () => {
    expect(() =>
      createCutoverContract({
        ...fullCutover(),
        // @ts-expect-error — intentionally wrong type at the schema boundary
        source_engine: 42,
      }),
    ).toThrow()
    expect(() =>
      createCutoverContract({ ...fullCutover(), target_engine: '' }),
    ).toThrow()
    expect(() =>
      createCutoverContract({ ...fullCutover(), rollback_gate: '' }),
    ).toThrow()
    expect(() =>
      createCutoverContract({ ...fullCutover(), canary_window: '' }),
    ).toThrow()
    expect(() =>
      createCutoverContract({ ...fullCutover(), behavior_invariants: [''] }),
    ).toThrow()
  })

  // ---- aggregate guards ----

  it('isValidCutoverContract: null is valid (no cutover required)', () => {
    expect(isValidCutoverContract(null)).toBe(true)
    const cc = createCutoverContract(null)
    expect(cc).toBeNull()
  })

  it('isValidCutoverContract: full record is valid; non-objects are not', () => {
    expect(isValidCutoverContract(fullCutover())).toBe(true)
    expect(isValidCutoverContract('not-an-object')).toBe(false)
    expect(isValidCutoverContract(42)).toBe(false)
    expect(isValidCutoverContract({ source_engine: 'x' })).toBe(false)
  })

  it('JSON round-trip: stringify + parse preserves all fields', () => {
    const cc = createCutoverContract(fullCutover())
    const parsed = CutoverContractSchema.parse(JSON.parse(JSON.stringify(cc)))
    expect(parsed).toEqual(cc)
  })

  it('Charter.isValidCharter rejects deserialized record with malformed cutover_contract', () => {
    // explicit malformed cutover (not null, missing required field) on a
    // freshly-deserialized Charter shape — guards the audit-time predicate.
    const bad = {
      ...baseCharterFields(),
      cutover_contract: {
        source_engine: 'sutra-core',
        // missing target_engine + behavior_invariants + rollback_gate + canary_window
      },
    }
    expect(isValidCharter(bad as never)).toBe(false)
  })
})
