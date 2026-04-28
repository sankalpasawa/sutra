import { describe, it, expect } from 'vitest'
import { createCharter, isValidCharter } from '../../src/primitives/charter.js'
import type { AclEntry, Constraint } from '../../src/types/index.js'

describe('Charter primitive (V2 spec §1 Primitive 2 + V2.2 §A8 acl)', () => {
  it('creates a charter with required fields', () => {
    const obligation: Constraint = {
      name: 'ship-native-to-clients',
      predicate: 'install_count >= 1',
      durability: 'durable',
      owner_scope: 'charter',
      type: 'obligation',
    }
    const invariant: Constraint = {
      name: 'no-breaking-changes-in-V2',
      predicate: 'spec.compat == backward',
      durability: 'durable',
      owner_scope: 'charter',
      type: 'invariant',
    }
    const c = createCharter({
      id: 'C-abc123',
      purpose: 'Ship Native plugin to clients',
      scope_in: 'native_build && client_install',
      scope_out: 'core_internals',
      obligations: [obligation],
      invariants: [invariant],
      success_metrics: ['client_install_count >= 1 within 90d'],
      authority: 'inherited:D1',
      termination: 'V3.0 supersedes',
      constraints: [],
      acl: [],
    })
    expect(isValidCharter(c)).toBe(true)
    expect(c.id).toBe('C-abc123')
    expect(c.obligations).toHaveLength(1)
    expect(c.invariants).toHaveLength(1)
  })

  it('rejects charter with non-C-prefixed id', () => {
    expect(() =>
      createCharter({
        id: 'not-c-shaped',
        purpose: 'invalid',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [],
      }),
    ).toThrow(/Charter\.id/)
  })

  it('rejects charter with empty purpose', () => {
    expect(() =>
      createCharter({
        id: 'C-x',
        purpose: '',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [],
      }),
    ).toThrow(/Charter\.purpose/)
  })

  it('rejects obligation/invariant Constraint with wrong type sub-type', () => {
    const wrongType: Constraint = {
      name: 'mis-typed',
      predicate: 'p',
      durability: 'durable',
      owner_scope: 'charter',
      type: 'predicate', // obligations[] must use type='obligation' or undefined
    }
    expect(() =>
      createCharter({
        id: 'C-x',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [wrongType],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [],
      }),
    ).toThrow(/obligation/)
  })

  it('accepts acl entries with all access values', () => {
    const acl: AclEntry[] = [
      { domain_or_charter_id: 'D1', access: 'read', reason: 'parent' },
      { domain_or_charter_id: 'C-other', access: 'write', reason: 'co-owner' },
      { domain_or_charter_id: 'C-third', access: 'append', reason: 'observer' },
      { domain_or_charter_id: 'C-fourth', access: 'none', reason: 'sibling default' },
    ]
    const c = createCharter({
      id: 'C-acl',
      purpose: 'test acl',
      scope_in: 'a',
      scope_out: 'b',
      obligations: [],
      invariants: [],
      success_metrics: ['m'],
      authority: 'inherited',
      termination: 'V3',
      constraints: [],
      acl,
    })
    expect(c.acl).toHaveLength(4)
    expect(c.acl.map((e) => e.access)).toEqual(['read', 'write', 'append', 'none'])
  })

  it('rejects acl entry with invalid access value', () => {
    expect(() =>
      createCharter({
        id: 'C-x',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [
          // @ts-expect-error — runtime guard for invalid access value
          { domain_or_charter_id: 'D1', access: 'admin', reason: 'bad' },
        ],
      }),
    ).toThrow(/access/)
  })

  it('returned Charter is frozen', () => {
    const c = createCharter({
      id: 'C-x',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [],
    })
    expect(Object.isFrozen(c)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // P1.3 — V2.2 §A8 deep ACL validation
  // ---------------------------------------------------------------------------

  it('P1.3: createCharter rejects acl entry with empty domain_or_charter_id', () => {
    expect(() =>
      createCharter({
        id: 'C-acl-empty-id',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [{ domain_or_charter_id: '', access: 'read', reason: 'sibling' }],
      }),
    ).toThrow(/domain_or_charter_id/)
  })

  it('P1.3: createCharter rejects acl entry with non-string domain_or_charter_id (number)', () => {
    expect(() =>
      createCharter({
        id: 'C-acl-num-id',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [
          // @ts-expect-error — runtime guard for non-string
          { domain_or_charter_id: 42, access: 'read', reason: 'sibling' },
        ],
      }),
    ).toThrow(/domain_or_charter_id/)
  })

  it('P1.3: createCharter rejects acl entry with empty reason', () => {
    expect(() =>
      createCharter({
        id: 'C-acl-empty-reason',
        purpose: 'p',
        scope_in: '',
        scope_out: '',
        obligations: [],
        invariants: [],
        success_metrics: [],
        authority: '',
        termination: '',
        constraints: [],
        acl: [{ domain_or_charter_id: 'D1', access: 'read', reason: '' }],
      }),
    ).toThrow(/reason/)
  })

  it('P1.3: createCharter accepts acl entry with all fields valid', () => {
    const c = createCharter({
      id: 'C-acl-ok',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [{ domain_or_charter_id: 'D1', access: 'read', reason: 'parent domain' }],
    })
    expect(isValidCharter(c)).toBe(true)
    expect(c.acl).toHaveLength(1)
    expect(c.acl[0]?.reason).toBe('parent domain')
  })

  it('P1.3: isValidCharter returns false for deserialized acl with empty domain_or_charter_id', () => {
    const bad = {
      id: 'C-deser-empty-id',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [{ domain_or_charter_id: '', access: 'read' as const, reason: 'sibling' }],
    }
    expect(isValidCharter(bad)).toBe(false)
  })

  it('P1.3: isValidCharter returns false for deserialized acl with non-string domain_or_charter_id', () => {
    const bad = {
      id: 'C-deser-num-id',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [
        {
          domain_or_charter_id: 42 as unknown as string,
          access: 'read' as const,
          reason: 'sibling',
        },
      ],
    }
    expect(isValidCharter(bad)).toBe(false)
  })

  it('P1.3: isValidCharter returns false for deserialized acl with empty reason', () => {
    const bad = {
      id: 'C-deser-empty-reason',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [{ domain_or_charter_id: 'D1', access: 'read' as const, reason: '' }],
    }
    expect(isValidCharter(bad)).toBe(false)
  })
})
