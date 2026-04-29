/**
 * DecisionProvenance property tests — M4.3 (D2 §2.1).
 *
 * 1000+ cases per property per M4.3.6: random DP records validate;
 * `policy_id` + `policy_version` always co-present (cross-coupling F-8 partial);
 * `next_action_ref` union exhaustively exercised.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  DecisionProvenanceSchema,
  createDecisionProvenance,
  isValidDecisionProvenance,
  type DecisionProvenance,
} from '../../src/schemas/decision-provenance.js'
import { AGENT_KINDS, type AgentKind } from '../../src/types/agent-identity.js'

const PROP_RUNS = 1000

const hexHashArb = fc
  .string({ minLength: 1, maxLength: 16 })
  .filter((s) => /^[a-f0-9]+$/.test(s))

const dpIdArb = hexHashArb.map((h) => `dp-${h}`)

const wIdArb = fc.string({ minLength: 1, maxLength: 16 }).map((s) => `W-${s}`)

const nextActionRefArb: fc.Arbitrary<string | null> = fc.oneof(
  dpIdArb,
  wIdArb,
  fc.constant(null),
)

const agentIdentityArb = fc
  .record({
    kind: fc.constantFrom(...AGENT_KINDS) as fc.Arbitrary<AgentKind>,
    suffix: fc
      .string({ minLength: 1, maxLength: 16 })
      .filter((s) => /^\S+$/.test(s)),
    version: fc.option(fc.string({ minLength: 1, maxLength: 8 }), { nil: undefined }),
  })
  .map(({ kind, suffix, version }) =>
    version === undefined
      ? ({ kind, id: `${kind}:${suffix}` } as never)
      : ({ kind, id: `${kind}:${suffix}`, version } as never),
  )

const decisionKindArb = fc.constantFrom(
  'DECIDE',
  'EXECUTE',
  'OVERRIDE',
  'APPROVE',
  'REJECT',
  'DELEGATE',
  'TERMINATE',
) as fc.Arbitrary<DecisionProvenance['decision_kind']>

const scopeArb = fc.constantFrom(
  'CONSTITUTIONAL',
  'DOMAIN',
  'CHARTER',
  'TENANT',
  'WORKFLOW',
  'EXECUTION',
  'HOOK',
) as fc.Arbitrary<DecisionProvenance['scope']>

const dataRefArb = fc.record({
  kind: fc.string({ minLength: 1, maxLength: 8 }),
  schema_ref: fc.string({ minLength: 1, maxLength: 16 }),
  locator: fc.string({ minLength: 1, maxLength: 16 }),
  version: fc.string({ maxLength: 4 }),
  mutability: fc.constantFrom('mutable', 'immutable') as fc.Arbitrary<
    'mutable' | 'immutable'
  >,
  retention: fc.string({ maxLength: 6 }),
})

const dpArb: fc.Arbitrary<DecisionProvenance> = fc.record({
  id: dpIdArb,
  actor: fc.string({ minLength: 1, maxLength: 16 }),
  agent_identity: agentIdentityArb,
  timestamp: fc
    .integer({ min: 1700000000, max: 1900000000 })
    .map((unix) => new Date(unix * 1000).toISOString()),
  evidence: fc.array(dataRefArb, { maxLength: 3 }),
  authority_id: fc.string({ minLength: 1, maxLength: 16 }),
  policy_id: fc.string({ minLength: 1, maxLength: 16 }),
  policy_version: fc.string({ minLength: 1, maxLength: 8 }),
  confidence: fc.double({ min: 0, max: 1, noNaN: true }),
  decision_kind: decisionKindArb,
  scope: scopeArb,
  outcome: fc.string({ minLength: 1, maxLength: 30 }),
  next_action_ref: nextActionRefArb,
})

describe('DecisionProvenance property tests (M4.3)', () => {
  it('round-trip: createDecisionProvenance → JSON → parse equals original', () => {
    fc.assert(
      fc.property(dpArb, (dp) => {
        const v = createDecisionProvenance(dp)
        const parsed = DecisionProvenanceSchema.parse(
          JSON.parse(JSON.stringify(v)),
        )
        expect(parsed).toEqual(v)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('isValidDecisionProvenance true for every accepted record', () => {
    fc.assert(
      fc.property(dpArb, (dp) => {
        const v = createDecisionProvenance(dp)
        expect(isValidDecisionProvenance(v)).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('F-8 partial: policy_id + policy_version always co-present (both non-empty)', () => {
    fc.assert(
      fc.property(dpArb, (dp) => {
        const v = createDecisionProvenance(dp)
        expect(v.policy_id.length).toBeGreaterThan(0)
        expect(v.policy_version.length).toBeGreaterThan(0)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('next_action_ref union exhaustive: dp-/W-/null all accepted, others rejected', () => {
    // Positive: union members
    fc.assert(
      fc.property(dpArb, nextActionRefArb, (dp, ref) => {
        const v = createDecisionProvenance({ ...dp, next_action_ref: ref })
        expect(v.next_action_ref).toEqual(ref)
      }),
      { numRuns: PROP_RUNS },
    )
    // Negative: arbitrary non-W / non-dp non-null strings
    const invalidRefArb = fc
      .string({ minLength: 1, maxLength: 16 })
      .filter((s) => !/^dp-[a-f0-9]+$/.test(s) && !/^W-.+$/.test(s))
    fc.assert(
      fc.property(dpArb, invalidRefArb, (dp, badRef) => {
        expect(
          isValidDecisionProvenance({ ...dp, next_action_ref: badRef }),
        ).toBe(false)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('confidence boundary: 0 and 1 accepted; >1 and <0 rejected', () => {
    fc.assert(
      fc.property(dpArb, (dp) => {
        expect(createDecisionProvenance({ ...dp, confidence: 0 }).confidence).toBe(0)
        expect(createDecisionProvenance({ ...dp, confidence: 1 }).confidence).toBe(1)
      }),
      { numRuns: PROP_RUNS },
    )
    const outOfRangeArb = fc.oneof(
      fc.double({ min: -10, max: -0.0001, noNaN: true }),
      fc.double({ min: 1.0001, max: 10, noNaN: true }),
    )
    fc.assert(
      fc.property(dpArb, outOfRangeArb, (dp, c) => {
        expect(() => createDecisionProvenance({ ...dp, confidence: c })).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
