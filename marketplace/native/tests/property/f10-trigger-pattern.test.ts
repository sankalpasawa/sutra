/**
 * F-10 TriggerSpec.pattern parser — property tests (M7 Group W T-096).
 *
 * Per codex M7 P1.3: TriggerSpec.pattern parser-bound at M7. The parser
 * accepts the V2 §A11 5-enum (preprocessor / observer / gate / fan_out /
 * negotiation) and rejects everything else.
 *
 * Properties asserted (≥1000 cases each):
 *   1. Round-trip identity for the 5 valid enum values
 *   2. Random non-enum strings rejected with TriggerPatternParseError
 *   3. Non-string inputs (numbers, objects, null, undefined) rejected
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group W T-096
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3 F-10
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  parseTriggerSpecPattern,
  TriggerPatternParseError,
  type TriggerPatternKind,
} from '../../src/laws/f10-parsers.js'

const PROP_RUNS = 1000

const ENUM_VALUES: readonly TriggerPatternKind[] = [
  'preprocessor',
  'observer',
  'gate',
  'fan_out',
  'negotiation',
]

// Membership predicate (mirrors the parser's internal Set without exposing it).
const ENUM_SET: ReadonlySet<TriggerPatternKind> = new Set(ENUM_VALUES)

// =============================================================================
// 1. Hand-rolled positive / negative samples
// =============================================================================

describe('TriggerSpec.pattern parser — accepts the 5 V2 enum values', () => {
  it.each(ENUM_VALUES)('accepts %s', (val) => {
    expect(parseTriggerSpecPattern(val)).toBe(val)
  })

  it('returns identical reference (no canonicalization)', () => {
    // The parser MUST return the input unchanged when valid; downstream
    // consumers rely on `parsed === input` for the 5 known strings.
    for (const v of ENUM_VALUES) {
      const out = parseTriggerSpecPattern(v)
      expect(out).toBe(v)
    }
  })
})

describe('TriggerSpec.pattern parser — rejects', () => {
  it('rejects empty string', () => {
    expect(() => parseTriggerSpecPattern('')).toThrow(TriggerPatternParseError)
  })

  it('rejects near-miss casings', () => {
    const nearMiss = ['Preprocessor', 'OBSERVER', 'Gate', 'Fan_Out', 'Negotiation']
    for (const s of nearMiss) {
      expect(() => parseTriggerSpecPattern(s), `should reject "${s}"`).toThrow(
        TriggerPatternParseError,
      )
    }
  })

  it('rejects near-miss spellings', () => {
    const nearMiss = ['fan-out', 'fanout', 'pre-processor', 'observe', 'negotiate']
    for (const s of nearMiss) {
      expect(() => parseTriggerSpecPattern(s), `should reject "${s}"`).toThrow(
        TriggerPatternParseError,
      )
    }
  })

  it('rejects English prose', () => {
    const prose = [
      'when the trigger fires',
      'observer pattern please',
      'this is a gate',
      'fan_out to all consumers',
    ]
    for (const s of prose) {
      expect(() => parseTriggerSpecPattern(s), `should reject "${s}"`).toThrow(
        TriggerPatternParseError,
      )
    }
  })

  it('rejects strings with surrounding whitespace', () => {
    // Tokens, not labels — leading/trailing whitespace is a violation.
    for (const v of ENUM_VALUES) {
      expect(() => parseTriggerSpecPattern(` ${v}`)).toThrow(TriggerPatternParseError)
      expect(() => parseTriggerSpecPattern(`${v} `)).toThrow(TriggerPatternParseError)
    }
  })

  it('rejects non-string scalars', () => {
    expect(() => parseTriggerSpecPattern(0)).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(1)).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(true)).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(false)).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(null)).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(undefined)).toThrow(TriggerPatternParseError)
  })

  it('rejects non-string composites', () => {
    expect(() => parseTriggerSpecPattern({})).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern({ pattern: 'observer' })).toThrow(
      TriggerPatternParseError,
    )
    expect(() => parseTriggerSpecPattern([])).toThrow(TriggerPatternParseError)
    expect(() => parseTriggerSpecPattern(['observer'])).toThrow(TriggerPatternParseError)
  })
})

// =============================================================================
// 2. Property: round-trip identity for the 5 enum values
// =============================================================================

describe('TriggerSpec.pattern parser — property: round-trip identity (≥1000 cases)', () => {
  it('every draw of the 5 enum values round-trips identically', () => {
    const enumArb = fc.constantFrom(...ENUM_VALUES) as fc.Arbitrary<TriggerPatternKind>
    fc.assert(
      fc.property(enumArb, (v) => {
        const parsed = parseTriggerSpecPattern(v)
        // Strict-equal — parser does not canonicalize. Property holds for all
        // 5 values regardless of which one fast-check picks.
        expect(parsed).toBe(v)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// 3. Property: random non-enum strings rejected
// =============================================================================

describe('TriggerSpec.pattern parser — property: random strings are stable (≥1000 cases)', () => {
  it('arbitrary fc.string() inputs: parser is stable (returns enum or throws TriggerPatternParseError)', () => {
    // fc.string() returns arbitrary unicode strings; the overwhelming majority
    // are NOT in the 5-enum and MUST throw. The rare hit on an enum value (if
    // fast-check happens to draw 'gate' or 'observer') MUST round-trip.
    fc.assert(
      fc.property(fc.string({ minLength: 0, maxLength: 32 }), (s) => {
        if (ENUM_SET.has(s as TriggerPatternKind)) {
          // Lucky draw — must round-trip cleanly.
          expect(parseTriggerSpecPattern(s)).toBe(s)
        } else {
          // Otherwise — must throw the typed error (never some other class).
          try {
            parseTriggerSpecPattern(s)
            // If we reach here, the parser accepted a non-enum string — fail.
            throw new Error(`parser unexpectedly accepted: "${s}"`)
          } catch (e) {
            expect(e).toBeInstanceOf(TriggerPatternParseError)
          }
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('random alphabetic strings outside the enum are rejected', () => {
    // Tighter-shape arb: lowercase a-z only. Almost no chance of hitting an
    // enum value (fast-check is uniform over the alphabet, the 5 enum strings
    // occupy a vanishingly small subset). Pin the property anyway via the
    // membership check.
    const alphaArb = fc.stringMatching(/^[a-z]{1,16}$/)
    fc.assert(
      fc.property(alphaArb, (s) => {
        if (ENUM_SET.has(s as TriggerPatternKind)) {
          expect(parseTriggerSpecPattern(s)).toBe(s)
        } else {
          expect(() => parseTriggerSpecPattern(s)).toThrow(TriggerPatternParseError)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// 4. Property: non-string inputs rejected
// =============================================================================

describe('TriggerSpec.pattern parser — property: non-string inputs rejected (≥1000 cases)', () => {
  it('arbitrary numbers always throw TriggerPatternParseError', () => {
    fc.assert(
      fc.property(fc.integer(), (n) => {
        expect(() => parseTriggerSpecPattern(n)).toThrow(TriggerPatternParseError)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('arbitrary booleans always throw TriggerPatternParseError', () => {
    fc.assert(
      fc.property(fc.boolean(), (b) => {
        expect(() => parseTriggerSpecPattern(b)).toThrow(TriggerPatternParseError)
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('arbitrary objects + arrays always throw TriggerPatternParseError', () => {
    // Use anything() but filter to non-strings; covers null/undefined/objects/arrays
    // in one arbitrary so we exercise the broadest non-string surface in 1k runs.
    fc.assert(
      fc.property(
        fc
          .anything()
          .filter((x) => typeof x !== 'string'),
        (x) => {
          expect(() => parseTriggerSpecPattern(x)).toThrow(TriggerPatternParseError)
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

