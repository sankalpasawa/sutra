/**
 * F-10 typed parsers — property tests (M5 Group K T-052).
 *
 * Per codex P2.6 (D-NS-13 (b) flipped 2026-04-29) — 2 parsers at M5:
 *   1. parseWorkflowPreconditions  — boolean expression
 *   2. parseWorkflowFailurePolicy  — 5-enum / structured JSON
 *
 * Properties asserted (≥1000 cases each):
 *   - Reject English-only prose (random `fc.string()` mostly rejects;
 *     hand-written prose strings ALL reject)
 *   - Accept structured / enum forms (constructed positive samples + arbitrary
 *     structure-shaped inputs)
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group K T-052
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P2.6
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseWorkflowPreconditions,
  parseWorkflowFailurePolicy,
  F10ParseError,
} from '../../src/laws/f10-parsers.js'

const PROP_RUNS = 1000

// =============================================================================
// 1. parseWorkflowPreconditions
// =============================================================================

describe('F-10: parseWorkflowPreconditions — accepts structured boolean expressions', () => {
  it('accepts bare identifier', () => {
    const ast = parseWorkflowPreconditions('depth_marker_present')
    expect(ast.kind).toBe('identifier')
    if (ast.kind !== 'identifier') throw new Error('narrow')
    expect(ast.name).toBe('depth_marker_present')
  })

  it('accepts comparison: identifier op literal', () => {
    const ast = parseWorkflowPreconditions("domain.type == 'observation'")
    expect(ast.kind).toBe('comparison')
    if (ast.kind !== 'comparison') throw new Error('narrow')
    expect(ast.field).toBe('domain.type')
    expect(ast.op).toBe('==')
    expect(ast.value).toBe('observation')
  })

  it('accepts != null', () => {
    const ast = parseWorkflowPreconditions('charter.id != null')
    if (ast.kind !== 'comparison') throw new Error('narrow')
    expect(ast.op).toBe('!=')
    expect(ast.value).toBeNull()
  })

  it('accepts && composition', () => {
    const ast = parseWorkflowPreconditions("a == 'x' && b != null")
    expect(ast.kind).toBe('and')
  })

  it('accepts || composition', () => {
    const ast = parseWorkflowPreconditions('a || b')
    expect(ast.kind).toBe('or')
  })

  it('accepts ! negation', () => {
    const ast = parseWorkflowPreconditions('!a')
    expect(ast.kind).toBe('not')
  })

  it('accepts parenthesized groups + precedence', () => {
    const ast = parseWorkflowPreconditions('(a || b) && c')
    expect(ast.kind).toBe('and')
  })

  it('accepts numeric comparisons', () => {
    const ast = parseWorkflowPreconditions('x >= 5')
    if (ast.kind !== 'comparison') throw new Error('narrow')
    expect(ast.op).toBe('>=')
    expect(ast.value).toBe(5)
  })

  it('accepts boolean literals', () => {
    const ast = parseWorkflowPreconditions('flag == true')
    if (ast.kind !== 'comparison') throw new Error('narrow')
    expect(ast.value).toBe(true)
  })
})

describe('F-10: parseWorkflowPreconditions — rejects', () => {
  it('rejects empty string', () => {
    expect(() => parseWorkflowPreconditions('')).toThrow(F10ParseError)
  })

  it('rejects English prose (specific samples)', () => {
    const proseSamples = [
      'when the founder approves',
      'this should run after Monday',
      'if the depth marker is set then proceed',
      'only when ready, please',
      'wait for the agent to finish, then go',
    ]
    for (const s of proseSamples) {
      expect(() => parseWorkflowPreconditions(s), `should reject: "${s}"`).toThrow(F10ParseError)
    }
  })

  it('rejects unbalanced parens', () => {
    expect(() => parseWorkflowPreconditions('(a && b')).toThrow(F10ParseError)
  })

  it('rejects trailing tokens after expression', () => {
    expect(() => parseWorkflowPreconditions('a b')).toThrow(F10ParseError)
  })

  it('rejects comparison without literal', () => {
    expect(() => parseWorkflowPreconditions('a ==')).toThrow(F10ParseError)
  })

  it('rejects non-string input', () => {
    // @ts-expect-error — defensive runtime guard
    expect(() => parseWorkflowPreconditions(42)).toThrow(F10ParseError)
  })
})

describe('F-10: parseWorkflowPreconditions — property (≥1000 cases)', () => {
  it('arbitrary fc.string() inputs: parser is stable (returns AST or throws F10ParseError)', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 80 }), (s) => {
        try {
          const ast = parseWorkflowPreconditions(s)
          // If it parses, the AST has a known kind.
          expect(['identifier', 'comparison', 'and', 'or', 'not']).toContain(ast.kind)
        } catch (e) {
          // Otherwise it MUST throw F10ParseError — never some other error.
          expect(e).toBeInstanceOf(F10ParseError)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('constructed valid identifiers always parse to identifier or comparison', () => {
    // Identifiers from a tight alphabet — guaranteed to lex cleanly.
    const identArb = fc
      .stringMatching(/^[a-zA-Z_][a-zA-Z0-9_.]{0,15}$/)
      .filter((s) => !['true', 'false', 'null'].includes(s))
    fc.assert(
      fc.property(identArb, (ident) => {
        const ast = parseWorkflowPreconditions(ident)
        expect(['identifier']).toContain(ast.kind)
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// 2. parseWorkflowFailurePolicy
// =============================================================================

describe('F-10: parseWorkflowFailurePolicy — accepts', () => {
  it.each(['rollback', 'escalate', 'pause', 'abort', 'continue'] as const)(
    'accepts bare enum %s',
    (enumVal) => {
      const out = parseWorkflowFailurePolicy(enumVal)
      expect(out.policy).toBe(enumVal)
      expect(out.escalation_target).toBeUndefined()
    },
  )

  it('accepts JSON object {"policy": "abort"}', () => {
    const out = parseWorkflowFailurePolicy('{"policy":"abort"}')
    expect(out.policy).toBe('abort')
  })

  it('accepts JSON with escalation_target', () => {
    const out = parseWorkflowFailurePolicy('{"policy":"escalate","escalation_target":"founder"}')
    expect(out.policy).toBe('escalate')
    expect(out.escalation_target).toBe('founder')
  })

  it('tolerates surrounding whitespace', () => {
    expect(parseWorkflowFailurePolicy('  abort  ').policy).toBe('abort')
  })
})

describe('F-10: parseWorkflowFailurePolicy — rejects', () => {
  it('rejects empty string', () => {
    expect(() => parseWorkflowFailurePolicy('')).toThrow(F10ParseError)
  })

  it('rejects English prose (specific samples)', () => {
    const prose = [
      'please abort this workflow',
      'tell the founder',
      'just give up',
      'rollback then escalate',
      'maybe pause but maybe continue',
    ]
    for (const s of prose) {
      expect(() => parseWorkflowFailurePolicy(s), `should reject: "${s}"`).toThrow(F10ParseError)
    }
  })

  it('rejects unknown enum value', () => {
    expect(() => parseWorkflowFailurePolicy('frobnicate')).toThrow(F10ParseError)
  })

  it('rejects malformed JSON', () => {
    expect(() => parseWorkflowFailurePolicy('{not-json}')).toThrow(F10ParseError)
  })

  it('rejects JSON array', () => {
    expect(() => parseWorkflowFailurePolicy('["abort"]')).toThrow(F10ParseError)
  })

  it('rejects JSON with bad policy', () => {
    expect(() => parseWorkflowFailurePolicy('{"policy":"frobnicate"}')).toThrow(F10ParseError)
  })

  it('rejects JSON with extra fields', () => {
    expect(() =>
      parseWorkflowFailurePolicy('{"policy":"abort","extra":"x"}'),
    ).toThrow(F10ParseError)
  })

  it('rejects JSON with empty escalation_target', () => {
    expect(() =>
      parseWorkflowFailurePolicy('{"policy":"escalate","escalation_target":""}'),
    ).toThrow(F10ParseError)
  })
})

describe('F-10: parseWorkflowFailurePolicy — property (≥1000 cases)', () => {
  it('arbitrary fc.string() inputs: parser is stable (returns ParsedFailurePolicy or throws F10ParseError)', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 0, maxLength: 60 }), (s) => {
        try {
          const out = parseWorkflowFailurePolicy(s)
          expect(['rollback', 'escalate', 'pause', 'abort', 'continue']).toContain(out.policy)
        } catch (e) {
          expect(e).toBeInstanceOf(F10ParseError)
        }
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('constructed JSON inputs from arbitrary policies always parse', () => {
    const policyArb = fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue') as fc.Arbitrary<
      'rollback' | 'escalate' | 'pause' | 'abort' | 'continue'
    >
    fc.assert(
      fc.property(
        policyArb,
        fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
        (policy, escalation_target) => {
          const json: Record<string, string> = { policy }
          if (escalation_target) json.escalation_target = escalation_target
          const out = parseWorkflowFailurePolicy(JSON.stringify(json))
          expect(out.policy).toBe(policy)
          if (escalation_target) {
            expect(out.escalation_target).toBe(escalation_target)
          }
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})
