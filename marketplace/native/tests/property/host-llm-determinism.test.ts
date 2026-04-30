/**
 * host-llm-determinism property test — M8 Group BB (T-117).
 *
 * Asserts (≥1000 cases):
 *  - For all (prompt, host_kind, host_version, run_seq):
 *    deriveInvocationId is deterministic — same inputs ⇒ same id.
 *  - Distinct inputs (within seed space) ⇒ distinct ids ("collision-resistant"
 *    given sha256 truncated to 32 hex chars; the property is empirical
 *    within the fast-check sample space).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group BB T-117
 *  - .enforcement/codex-reviews/2026-04-30-architecture-pivot-rereview.md
 *    (DIRECTIVE-ID 1777521736)
 */

import { describe, it } from 'vitest'
import fc from 'fast-check'
import { __deriveInvocationIdForTest } from '../../src/engine/host-llm-activity.js'

const hostKindArb = fc.constantFrom('claude' as const, 'codex' as const)

describe('host-llm-determinism — invocation_id', () => {
  it('forall (prompt, host, version, seq): same inputs ⇒ same id', () => {
    fc.assert(
      fc.property(
        fc.string({ maxLength: 200 }),
        hostKindArb,
        fc.string({ minLength: 1, maxLength: 32 }),
        fc.integer({ min: 0, max: 1_000_000 }),
        (prompt, host, version, seq) => {
          const a = __deriveInvocationIdForTest(prompt, host, version, seq)
          const b = __deriveInvocationIdForTest(prompt, host, version, seq)
          if (a !== b) return false
          // sha256 truncated to 32 hex chars
          if (!/^[a-f0-9]{32}$/.test(a)) return false
          return true
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (p1≠p2): distinct prompts ⇒ distinct ids (within 1000 samples)', () => {
    fc.assert(
      fc.property(
        fc.string({ maxLength: 200 }),
        fc.string({ maxLength: 200 }),
        hostKindArb,
        fc.string({ minLength: 1, maxLength: 32 }),
        fc.integer({ min: 0, max: 1_000_000 }),
        (p1, p2, host, version, seq) => {
          fc.pre(p1 !== p2)
          return (
            __deriveInvocationIdForTest(p1, host, version, seq) !==
            __deriveInvocationIdForTest(p2, host, version, seq)
          )
        },
      ),
      { numRuns: 1000 },
    )
  })
})
