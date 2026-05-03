/**
 * Contract tests — predicate evaluator (D2 step 2 of vertical slice).
 *
 * Coverage:
 *   leaves      — always_true, contains (case sensitive/insensitive),
 *                 matches (valid/invalid regex, flags), event_type_eq,
 *                 cell_eq, verb_eq, direction_eq, risk_eq
 *   combinators — and (incl. empty algebraic identity), or (incl. empty),
 *                 not, nested
 *   edge cases  — missing context fields return false (never throw),
 *                 reasons populated for audit trail
 */

import { describe, it, expect } from 'vitest'
import { evaluate, type PredicateContext } from '../../../src/runtime/predicate.js'
import type { Predicate } from '../../../src/types/trigger-spec.js'
import type { HSutraEvent } from '../../../src/types/h-sutra-event.js'

const baseCtx: PredicateContext = { event_type: 'founder_input' }

const ctxWith = (input_text: string, hsutra?: HSutraEvent): PredicateContext => ({
  event_type: 'founder_input',
  input_text,
  hsutra,
})

describe('predicate.evaluate — D2 step 2 contract', () => {
  describe('always_true', () => {
    it('matches unconditionally', () => {
      expect(evaluate({ type: 'always_true' }, baseCtx)).toEqual({ matched: true })
    })
  })

  describe('contains', () => {
    it('matches case-insensitive by default', () => {
      const r = evaluate({ type: 'contains', value: 'BUILD' }, ctxWith('please build a product'))
      expect(r.matched).toBe(true)
    })

    it('returns false with reason when needle absent', () => {
      const r = evaluate({ type: 'contains', value: 'deploy' }, ctxWith('write the docs'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('does not contain')
      expect(r.reason).toContain('deploy')
    })

    it('respects case_sensitive=true (mismatch on case)', () => {
      const r = evaluate(
        { type: 'contains', value: 'Build', case_sensitive: true },
        ctxWith('please build a product'),
      )
      expect(r.matched).toBe(false)
    })

    it('matches case_sensitive=true when case matches exactly', () => {
      const r = evaluate(
        { type: 'contains', value: 'Build', case_sensitive: true },
        ctxWith('please Build a product'),
      )
      expect(r.matched).toBe(true)
    })

    it('returns false (no throw) when input_text missing', () => {
      const r = evaluate({ type: 'contains', value: 'anything' }, baseCtx)
      expect(r.matched).toBe(false)
    })
  })

  describe('matches', () => {
    it('matches a valid regex', () => {
      const r = evaluate({ type: 'matches', pattern: '^build\\s+\\w+' }, ctxWith('build product'))
      expect(r.matched).toBe(true)
    })

    it('returns false with reason when regex does not match', () => {
      const r = evaluate({ type: 'matches', pattern: '^deploy' }, ctxWith('build product'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('does not match')
    })

    it('honors regex flags (i = case-insensitive)', () => {
      const r = evaluate(
        { type: 'matches', pattern: 'BUILD', flags: 'i' },
        ctxWith('please build it'),
      )
      expect(r.matched).toBe(true)
    })

    it('returns false (no throw) on invalid regex', () => {
      const r = evaluate({ type: 'matches', pattern: '[invalid(' }, ctxWith('whatever'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('invalid regex')
    })
  })

  describe('event_type_eq', () => {
    it('matches when event_type equals', () => {
      const r = evaluate({ type: 'event_type_eq', value: 'founder_input' }, baseCtx)
      expect(r.matched).toBe(true)
    })

    it('returns false with reason when event_type differs', () => {
      const r = evaluate({ type: 'event_type_eq', value: 'cron' }, baseCtx)
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('founder_input')
      expect(r.reason).toContain('cron')
    })
  })

  describe('hsutra-derived leaves', () => {
    const hsutra: HSutraEvent = {
      turn_id: 't-1',
      verb: 'DIRECT',
      direction: 'INBOUND',
      cell: 'DIRECT·INBOUND',
      risk: 'MEDIUM',
    }

    it('cell_eq matches when present + equal', () => {
      const r = evaluate(
        { type: 'cell_eq', value: 'DIRECT·INBOUND' },
        ctxWith('hi', hsutra),
      )
      expect(r.matched).toBe(true)
    })

    it('cell_eq returns <missing> in reason when hsutra absent', () => {
      const r = evaluate({ type: 'cell_eq', value: 'DIRECT·INBOUND' }, baseCtx)
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('<missing>')
    })

    it('verb_eq matches', () => {
      const r = evaluate({ type: 'verb_eq', value: 'DIRECT' }, ctxWith('hi', hsutra))
      expect(r.matched).toBe(true)
    })

    it('direction_eq matches', () => {
      const r = evaluate({ type: 'direction_eq', value: 'INBOUND' }, ctxWith('hi', hsutra))
      expect(r.matched).toBe(true)
    })

    it('risk_eq matches', () => {
      const r = evaluate({ type: 'risk_eq', value: 'MEDIUM' }, ctxWith('hi', hsutra))
      expect(r.matched).toBe(true)
    })

    it('verb_eq returns false when verb missing on hsutra', () => {
      const minimal: HSutraEvent = { turn_id: 't-2' }
      const r = evaluate({ type: 'verb_eq', value: 'DIRECT' }, ctxWith('hi', minimal))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('<missing>')
    })
  })

  describe('and combinator', () => {
    it('returns true when ALL clauses match', () => {
      const p: Predicate = {
        type: 'and',
        clauses: [
          { type: 'contains', value: 'build' },
          { type: 'event_type_eq', value: 'founder_input' },
        ],
      }
      expect(evaluate(p, ctxWith('build product')).matched).toBe(true)
    })

    it('empty AND is true (algebraic identity)', () => {
      expect(evaluate({ type: 'and', clauses: [] }, baseCtx)).toEqual({ matched: true })
    })

    it('short-circuits on first false with reason', () => {
      const p: Predicate = {
        type: 'and',
        clauses: [
          { type: 'always_true' },
          { type: 'contains', value: 'deploy' },
          { type: 'always_true' },
        ],
      }
      const r = evaluate(p, ctxWith('build product'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('and:')
      expect(r.reason).toContain('deploy')
    })
  })

  describe('or combinator', () => {
    it('returns true when ANY clause matches', () => {
      const p: Predicate = {
        type: 'or',
        clauses: [
          { type: 'contains', value: 'deploy' },
          { type: 'contains', value: 'build' },
        ],
      }
      expect(evaluate(p, ctxWith('build product')).matched).toBe(true)
    })

    it('empty OR is false (algebraic identity)', () => {
      const r = evaluate({ type: 'or', clauses: [] }, baseCtx)
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('empty')
    })

    it('aggregates reasons when no clause matches', () => {
      const p: Predicate = {
        type: 'or',
        clauses: [
          { type: 'contains', value: 'deploy' },
          { type: 'contains', value: 'ship' },
        ],
      }
      const r = evaluate(p, ctxWith('build product'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('or:')
      expect(r.reason).toContain('deploy')
      expect(r.reason).toContain('ship')
    })
  })

  describe('not combinator', () => {
    it('inverts a matching clause to false', () => {
      const r = evaluate({ type: 'not', clause: { type: 'always_true' } }, baseCtx)
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('inner clause matched')
    })

    it('inverts a failing clause to true', () => {
      const r = evaluate(
        { type: 'not', clause: { type: 'contains', value: 'deploy' } },
        ctxWith('build product'),
      )
      expect(r.matched).toBe(true)
    })
  })

  describe('nested combinators', () => {
    it('handles (A AND B) OR (NOT C)', () => {
      const p: Predicate = {
        type: 'or',
        clauses: [
          {
            type: 'and',
            clauses: [
              { type: 'contains', value: 'build' },
              { type: 'event_type_eq', value: 'cron' }, // false → AND fails
            ],
          },
          { type: 'not', clause: { type: 'contains', value: 'deploy' } }, // true
        ],
      }
      expect(evaluate(p, ctxWith('build product')).matched).toBe(true)
    })

    it('deep failure surfaces nested reasons', () => {
      const p: Predicate = {
        type: 'and',
        clauses: [
          { type: 'always_true' },
          {
            type: 'or',
            clauses: [
              { type: 'contains', value: 'x' },
              { type: 'contains', value: 'y' },
            ],
          },
        ],
      }
      const r = evaluate(p, ctxWith('hello'))
      expect(r.matched).toBe(false)
      expect(r.reason).toContain('and:')
      expect(r.reason).toContain('or:')
    })
  })
})
