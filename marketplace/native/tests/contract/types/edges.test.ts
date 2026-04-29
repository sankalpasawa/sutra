/**
 * Edge types contract tests — M4.8 (Group C; T-018).
 *
 * Six tests exercising the three new edge schemas (owns / delegates_to /
 * emits), the discriminated union round-trip, and rejection of malformed
 * cross-kind shapes.
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §2.2
 * - holding/plans/native-v1.0/TASK-QUEUE.md §1 Group C
 */

import { describe, expect, it } from 'vitest'
import {
  DelegatesToEdgeSchema,
  EdgeSchema,
  EmitsEdgeSchema,
  OwnsEdgeSchema,
  isValidEdge,
} from '../../../src/types/edges.js'

describe('OwnsEdge (Tenant → Domain) — M4.8 T-018.1', () => {
  it('round-trips a valid OwnsEdge (T-asawa → D1)', () => {
    const e = { kind: 'owns', source: 'T-asawa', target: 'D1' } as const
    const parsed = OwnsEdgeSchema.parse(e)
    expect(parsed).toEqual(e)
    expect(isValidEdge(parsed)).toBe(true)
    // also via the discriminated-union entry point
    expect(EdgeSchema.parse(e)).toEqual(e)
  })

  it('accepts hierarchical Domain ids (D1.D2.D3)', () => {
    const e = { kind: 'owns', source: 'T-asawa-holding', target: 'D1.D2.D3' } as const
    expect(OwnsEdgeSchema.safeParse(e).success).toBe(true)
  })
})

describe('DelegatesToEdge (Tenant → Tenant) — M4.8 T-018.2', () => {
  it('round-trips a valid DelegatesToEdge (T-asawa → T-paisa)', () => {
    const e = {
      kind: 'delegates_to',
      source: 'T-asawa',
      target: 'T-paisa',
    } as const
    const parsed = DelegatesToEdgeSchema.parse(e)
    expect(parsed).toEqual(e)
    expect(isValidEdge(parsed)).toBe(true)
    expect(EdgeSchema.parse(e)).toEqual(e)
  })
})

describe('EmitsEdge (Workflow/Execution/Hook → DecisionProvenance) — M4.8 T-018.3', () => {
  it('round-trips a Workflow → DP edge', () => {
    const e = {
      kind: 'emits',
      source: 'W-abc123',
      target: 'dp-deadbeef',
    } as const
    const parsed = EmitsEdgeSchema.parse(e)
    expect(parsed).toEqual(e)
    expect(EdgeSchema.parse(e)).toEqual(e)
  })

  it('round-trips an Execution → DP edge', () => {
    const e = {
      kind: 'emits',
      source: 'E-xyz789',
      target: 'dp-cafe1234',
    } as const
    expect(EmitsEdgeSchema.parse(e)).toEqual(e)
  })

  it('round-trips a Hook (free-form id) → DP edge', () => {
    const e = {
      kind: 'emits',
      source: 'hook:cascade-check',
      target: 'dp-0123456789abcdef',
    } as const
    expect(EmitsEdgeSchema.parse(e)).toEqual(e)
  })

  it('rejects empty source', () => {
    expect(
      EmitsEdgeSchema.safeParse({ kind: 'emits', source: '', target: 'dp-deadbeef' })
        .success,
    ).toBe(false)
  })
})

describe('EdgeSchema discriminated-union — M4.8 T-018.4', () => {
  it('rejects an unknown kind', () => {
    const bad = { kind: 'unknown', source: 'T-x', target: 'D1' }
    expect(EdgeSchema.safeParse(bad).success).toBe(false)
    expect(isValidEdge(bad)).toBe(false)
  })

  it('rejects missing kind', () => {
    expect(EdgeSchema.safeParse({ source: 'T-x', target: 'D1' }).success).toBe(false)
  })
})

describe('Cross-kind type errors — M4.8 T-018.5', () => {
  it('rejects owns with a Workflow id in target slot', () => {
    // owns target must be Domain.id (D-pattern), not Workflow.id (W-pattern)
    const bad = { kind: 'owns', source: 'T-asawa', target: 'W-abc123' }
    expect(OwnsEdgeSchema.safeParse(bad).success).toBe(false)
    expect(EdgeSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects delegates_to with a Domain id in target slot', () => {
    const bad = { kind: 'delegates_to', source: 'T-asawa', target: 'D1' }
    expect(DelegatesToEdgeSchema.safeParse(bad).success).toBe(false)
    expect(EdgeSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects emits with a Workflow id in target slot (must be DP)', () => {
    const bad = { kind: 'emits', source: 'W-abc', target: 'W-def' }
    expect(EmitsEdgeSchema.safeParse(bad).success).toBe(false)
    expect(EdgeSchema.safeParse(bad).success).toBe(false)
  })
})

describe('Bad source/target combinations — M4.8 T-018.6', () => {
  it('rejects owns with a Workflow id in source slot (source must be Tenant)', () => {
    const bad = { kind: 'owns', source: 'W-abc123', target: 'D1' }
    expect(OwnsEdgeSchema.safeParse(bad).success).toBe(false)
    expect(EdgeSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects owns with lowercase tenant id (must match T-<lowercase>)', () => {
    // Source slot expects T-<lowercase>; uppercase fails the regex.
    const bad = { kind: 'owns', source: 'T-ASAWA', target: 'D1' }
    expect(OwnsEdgeSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects emits with malformed DP id (uppercase hex)', () => {
    const bad = { kind: 'emits', source: 'W-abc', target: 'dp-DEADBEEF' }
    expect(EmitsEdgeSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects delegates_to with non-tenant source', () => {
    const bad = { kind: 'delegates_to', source: 'D1', target: 'T-paisa' }
    expect(DelegatesToEdgeSchema.safeParse(bad).success).toBe(false)
  })
})
