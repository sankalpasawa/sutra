/**
 * OPA bundle service contract test — M7 Group V (T-089).
 *
 * Asserts:
 *  - register/get round-trip
 *  - latest version resolution when version is omitted
 *  - explicit version pin via get(id, version)
 *  - idempotence on duplicate (id, version) registration
 *  - version accumulation across multiple registers for same id
 *  - unregister clears all versions for an id
 *  - list_versions returns insertion order
 *  - get / list_versions return safe defaults for unknown ids
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group V T-089
 */

import { describe, it, expect } from 'vitest'

import { OPABundleService } from '../../../src/engine/opa-bundle-service.js'
import type { CompiledPolicy } from '../../../src/engine/charter-rego-compiler.js'

function policy(id: string, version: string, source = `package ${id}\n`): CompiledPolicy {
  return Object.freeze({ policy_id: id, policy_version: version, rego_source: source })
}

describe('OPABundleService — register / get round-trip', () => {
  it('round-trips a single policy via get(id) → returns latest', () => {
    const svc = new OPABundleService()
    const p = policy('C_foo', 'v1')
    svc.register(p)
    expect(svc.get('C_foo')).toBe(p)
  })

  it('returns the same record via get(id, version)', () => {
    const svc = new OPABundleService()
    const p = policy('C_foo', 'v1')
    svc.register(p)
    expect(svc.get('C_foo', 'v1')).toBe(p)
  })

  it('returns null for unknown policy_id', () => {
    const svc = new OPABundleService()
    expect(svc.get('C_unknown')).toBeNull()
  })

  it('returns null for known id but unknown version', () => {
    const svc = new OPABundleService()
    svc.register(policy('C_foo', 'v1'))
    expect(svc.get('C_foo', 'v2')).toBeNull()
  })
})

describe('OPABundleService — version accumulation', () => {
  it('keeps every registered version addressable', () => {
    const svc = new OPABundleService()
    const v1 = policy('C_foo', 'v1', 'rev1')
    const v2 = policy('C_foo', 'v2', 'rev2')
    svc.register(v1)
    svc.register(v2)
    expect(svc.get('C_foo', 'v1')).toBe(v1)
    expect(svc.get('C_foo', 'v2')).toBe(v2)
  })

  it('latest-version pointer follows the most recent register', () => {
    const svc = new OPABundleService()
    svc.register(policy('C_foo', 'v1', 'rev1'))
    svc.register(policy('C_foo', 'v2', 'rev2'))
    expect(svc.get('C_foo')?.policy_version).toBe('v2')
  })

  it('list_versions returns insertion order', () => {
    const svc = new OPABundleService()
    svc.register(policy('C_foo', 'v1'))
    svc.register(policy('C_foo', 'v2'))
    svc.register(policy('C_foo', 'v3'))
    expect(svc.list_versions('C_foo')).toEqual(['v1', 'v2', 'v3'])
  })

  it('list_versions returns empty array for unknown id', () => {
    const svc = new OPABundleService()
    expect(svc.list_versions('C_unknown')).toEqual([])
  })
})

describe('OPABundleService — idempotence', () => {
  it('overwriting same (id, version) keeps latest content', () => {
    const svc = new OPABundleService()
    const a = policy('C_foo', 'v1', 'first')
    const b = policy('C_foo', 'v1', 'second')
    svc.register(a)
    svc.register(b)
    expect(svc.get('C_foo', 'v1')).toBe(b)
    expect(svc.list_versions('C_foo')).toEqual(['v1'])
  })
})

describe('OPABundleService — unregister', () => {
  it('clears all versions for an id', () => {
    const svc = new OPABundleService()
    svc.register(policy('C_foo', 'v1'))
    svc.register(policy('C_foo', 'v2'))
    svc.unregister('C_foo')
    expect(svc.get('C_foo')).toBeNull()
    expect(svc.get('C_foo', 'v1')).toBeNull()
    expect(svc.list_versions('C_foo')).toEqual([])
  })

  it('does not affect other ids', () => {
    const svc = new OPABundleService()
    svc.register(policy('C_foo', 'v1'))
    svc.register(policy('C_bar', 'v1'))
    svc.unregister('C_foo')
    expect(svc.get('C_foo')).toBeNull()
    expect(svc.get('C_bar')?.policy_id).toBe('C_bar')
  })

  it('unregistering an unknown id is a no-op', () => {
    const svc = new OPABundleService()
    expect(() => svc.unregister('C_never_registered')).not.toThrow()
  })
})
