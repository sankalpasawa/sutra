import { describe, it, expect } from 'vitest'
import { createDomain, isValidDomain, type Domain } from '../../src/primitives/domain.js'
import type { Constraint } from '../../src/types/index.js'

describe('Domain primitive (V2 spec §1 Primitive 1)', () => {
  it('creates a D0 root domain with parent_id=null', () => {
    const d0 = createDomain({
      id: 'D0',
      name: 'Asawa Inc.',
      parent_id: null,
      principles: [],
      intelligence: '',
      accountable: ['founder'],
      authority: 'org-root',
    })
    expect(isValidDomain(d0)).toBe(true)
    expect(d0.parent_id).toBeNull()
    expect(d0.id).toBe('D0')
  })

  it('creates a sub-domain with parent_id reference', () => {
    const principle: Constraint = {
      name: 'plugin-first',
      predicate: 'always',
      durability: 'durable',
      owner_scope: 'domain',
    }
    const d1 = createDomain({
      id: 'D1',
      name: 'Sutra-OS',
      parent_id: 'D0',
      principles: [principle],
      intelligence: 'accumulated context',
      accountable: ['sutra-os-team'],
      authority: 'plugin-runtime',
    })
    expect(isValidDomain(d1)).toBe(true)
    expect(d1.parent_id).toBe('D0')
    expect(d1.principles).toHaveLength(1)
    expect(d1.principles[0]?.name).toBe('plugin-first')
  })

  it('accepts deep D-numbered hierarchy (D1.D2.D3)', () => {
    const deep = createDomain({
      id: 'D1.D2.D3',
      name: 'deep sub-domain',
      parent_id: 'D1.D2',
      principles: [],
      intelligence: '',
      accountable: [],
      authority: '',
    })
    expect(isValidDomain(deep)).toBe(true)
    expect(deep.id).toBe('D1.D2.D3')
  })

  it('rejects domain with non-D-shaped id', () => {
    expect(() =>
      createDomain({
        id: 'not-d-shaped',
        name: 'invalid',
        parent_id: null,
        principles: [],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/D-numbered hierarchy/)
  })

  it('rejects domain with lowercase d prefix', () => {
    expect(() =>
      createDomain({
        id: 'd0',
        name: 'invalid',
        parent_id: null,
        principles: [],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/D-numbered hierarchy/)
  })

  it('rejects domain with empty id', () => {
    expect(() =>
      createDomain({
        id: '',
        name: 'invalid',
        parent_id: null,
        principles: [],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/D-numbered hierarchy/)
  })

  it('isValidDomain returns false for malformed records', () => {
    const bad: Domain = {
      id: 'X1',
      name: 'malformed',
      parent_id: null,
      principles: [],
      intelligence: '',
      accountable: [],
      authority: '',
      tenant_id: 'T-asawa-holding',
    }
    expect(isValidDomain(bad)).toBe(false)
  })

  it('returned Domain is frozen (immutable)', () => {
    const d = createDomain({
      id: 'D0',
      name: 'root',
      parent_id: null,
      principles: [],
      intelligence: '',
      accountable: [],
      authority: '',
    })
    expect(Object.isFrozen(d)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // P2.1 — V2 §1 P1 spec invariants
  // ---------------------------------------------------------------------------

  it('P2.1: rejects D0 root with non-null parent_id', () => {
    expect(() =>
      createDomain({
        id: 'D0',
        name: 'root',
        parent_id: 'D1',
        principles: [],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/D0|root domain has no parent|parent_id/)
  })

  it('P2.1: isValidDomain returns false for D0 with non-null parent_id', () => {
    const bad: Domain = {
      id: 'D0',
      name: 'root',
      parent_id: 'D1',
      principles: [],
      intelligence: '',
      accountable: [],
      authority: '',
      tenant_id: 'T-asawa-holding',
    }
    expect(isValidDomain(bad)).toBe(false)
  })

  it('P2.1: rejects non-D0 with malformed parent_id (not D-pattern)', () => {
    expect(() =>
      createDomain({
        id: 'D1',
        name: 'sub',
        parent_id: 'not-d-shaped',
        principles: [],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/parent_id.*D-numbered/)
  })

  it('P2.1: isValidDomain returns false for malformed parent_id on deserialized record', () => {
    const bad: Domain = {
      id: 'D1',
      name: 'sub',
      parent_id: 'not-d-shaped',
      principles: [],
      intelligence: '',
      accountable: [],
      authority: '',
      tenant_id: 'T-asawa-holding',
    }
    expect(isValidDomain(bad)).toBe(false)
  })

  it('P2.1: rejects principle with durability=episodic (V2 §1 P1 — Domain.principles MUST be durable)', () => {
    const episodic: Constraint = {
      name: 'temp',
      predicate: 'p',
      durability: 'episodic',
      owner_scope: 'domain',
    }
    expect(() =>
      createDomain({
        id: 'D1',
        name: 'sub',
        parent_id: 'D0',
        principles: [episodic],
        intelligence: '',
        accountable: [],
        authority: '',
      }),
    ).toThrow(/durable|durability/)
  })

  it('P2.1: isValidDomain returns false for principle with durability=episodic on deserialized record', () => {
    const episodic: Constraint = {
      name: 'temp',
      predicate: 'p',
      durability: 'episodic',
      owner_scope: 'domain',
    }
    const bad: Domain = {
      id: 'D1',
      name: 'sub',
      parent_id: 'D0',
      principles: [episodic],
      intelligence: '',
      accountable: [],
      authority: '',
      tenant_id: 'T-asawa-holding',
    }
    expect(isValidDomain(bad)).toBe(false)
  })
})
