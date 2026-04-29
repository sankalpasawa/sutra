/**
 * AgentIdentity property tests — M4.2.
 *
 * 1000+ cases per property. Asserts the namespace-prefix invariant
 * (D-NS-10 default c) holds for every kind across random ids.
 */

import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  AGENT_KINDS,
  AgentIdentitySchema,
  createAgentIdentity,
  isValidAgentIdentity,
  namespaceOf,
  type AgentKind,
} from '../../src/types/agent-identity.js'

const PROP_RUNS = 1000

const kindArb = fc.constantFrom(...AGENT_KINDS) as fc.Arbitrary<AgentKind>

// Suffix must be all non-whitespace to satisfy the `\S+$` end of the
// per-kind regex in src/types/agent-identity.ts.
const idSuffixArb = fc
  .string({ minLength: 1, maxLength: 24 })
  .filter((s) => /^\S+$/.test(s))

const validInputArb = fc.record({
  kind: kindArb,
  suffix: idSuffixArb,
  version: fc.option(fc.string({ minLength: 1, maxLength: 12 }), { nil: undefined }),
})

describe('AgentIdentity property tests (M4.2)', () => {
  it('round-trips: createAgentIdentity → JSON → parse equals original', () => {
    fc.assert(
      fc.property(validInputArb, ({ kind, suffix, version }) => {
        const id = `${kind}:${suffix}`
        const v = createAgentIdentity(
          version === undefined
            ? ({ kind, id } as never)
            : ({ kind, id, version } as never),
        )
        const parsed = AgentIdentitySchema.parse(JSON.parse(JSON.stringify(v)))
        expect(parsed).toEqual(v)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('isValidAgentIdentity true for every namespace-prefix-correct input', () => {
    fc.assert(
      fc.property(validInputArb, ({ kind, suffix }) => {
        const id = `${kind}:${suffix}`
        expect(isValidAgentIdentity({ kind, id })).toBe(true)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('namespace-prefix invariant: every accepted id has namespaceOf(id) === kind', () => {
    fc.assert(
      fc.property(validInputArb, ({ kind, suffix }) => {
        const id = `${kind}:${suffix}`
        const v = createAgentIdentity({ kind, id } as never)
        expect(namespaceOf(v.id)).toBe(kind)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('rejects: id with wrong-kind prefix', () => {
    const wrongPrefixArb = fc
      .record({
        kind: kindArb,
        otherKind: kindArb,
        suffix: idSuffixArb,
      })
      .filter(({ kind, otherKind }) => kind !== otherKind)
    fc.assert(
      fc.property(wrongPrefixArb, ({ kind, otherKind, suffix }) => {
        const id = `${otherKind}:${suffix}`
        expect(isValidAgentIdentity({ kind, id })).toBe(false)
        expect(() => createAgentIdentity({ kind, id } as never)).toThrow()
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('rejects: id with no colon at all', () => {
    const noColonArb = fc
      .string({ minLength: 1, maxLength: 16 })
      .filter((s) => !s.includes(':'))
    fc.assert(
      fc.property(kindArb, noColonArb, (kind, id) => {
        expect(isValidAgentIdentity({ kind, id })).toBe(false)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})
