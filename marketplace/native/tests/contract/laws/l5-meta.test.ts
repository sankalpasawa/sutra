/**
 * L5 META — contract tests
 */
import { describe, it, expect } from 'vitest'
import { l5Meta } from '../../../src/laws/l5-meta.js'

describe('L5 META — contract', () => {
  it('Domain → Charter containment is valid', () => {
    expect(l5Meta.isValidContainment('domain', 'charter')).toBe(true)
    expect(l5Meta.isValidEdge('contains', 'domain', 'charter')).toBe(true)
  })

  it('Charter → Workflow containment is REJECTED', () => {
    expect(l5Meta.isValidContainment('charter', 'workflow')).toBe(false)
    expect(l5Meta.isValidEdge('contains', 'charter', 'workflow')).toBe(false)
  })

  it('Workflow → Workflow containment is REJECTED', () => {
    expect(l5Meta.isValidContainment('workflow', 'workflow')).toBe(false)
    expect(l5Meta.isValidEdge('contains', 'workflow', 'workflow')).toBe(false)
  })

  it('typed edges are accepted regardless of (parent, child) shapes', () => {
    expect(l5Meta.isValidEdge('operationalizes', 'charter', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('decomposes_into', 'workflow', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('depends_on', 'workflow', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('produces', 'execution', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('consumes', 'workflow', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('activates', 'workflow', 'execution')).toBe(true)
    expect(l5Meta.isValidEdge('interfaces_with', 'workflow', 'workflow')).toBe(true)
    expect(l5Meta.isValidEdge('propagates_to', 'workflow', 'workflow')).toBe(true)
  })

  it('typedEdges() exposes the V2.x inventory', () => {
    const edges = l5Meta.typedEdges()
    expect(edges.has('operationalizes')).toBe(true)
    expect(edges.has('propagates_to')).toBe(true)
    expect(edges.size).toBe(8)
  })
})
