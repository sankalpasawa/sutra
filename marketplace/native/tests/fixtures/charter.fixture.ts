/**
 * Charter fixture factories — M4.10 baseline.
 *
 * Spec source: V2 §1 P2 + V2.2 §A8 + `src/primitives/charter.ts`.
 */

import type { Charter } from '../../src/primitives/charter.js'
import type { AclEntry, Constraint } from '../../src/types/index.js'

/**
 * Minimal valid Charter — required fields only, empty arrays.
 */
export function validMinimal(): Charter {
  return {
    id: 'C-min',
    purpose: 'minimum viable charter',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [],
    acl: [],
  }
}

/**
 * Fully populated valid Charter — obligations + invariants + ACL.
 */
export function validFull(): Charter {
  const obligation: Constraint = {
    name: 'ship-v1.0',
    predicate: 'M1..M12 milestones complete',
    durability: 'durable',
    owner_scope: 'charter',
    type: 'obligation',
  }
  const invariant: Constraint = {
    name: 'tests-green',
    predicate: 'every commit has all tests green',
    durability: 'durable',
    owner_scope: 'charter',
    type: 'invariant',
  }
  const episodic: Constraint = {
    name: 'codex-review-passed',
    predicate: 'codex P1 verdict CLEARED',
    durability: 'episodic',
    owner_scope: 'charter',
  }
  const acl: AclEntry[] = [
    { domain_or_charter_id: 'D1', access: 'read', reason: 'parent domain visibility' },
    { domain_or_charter_id: 'C-peer', access: 'append', reason: 'cross-charter event log' },
  ]
  return {
    id: 'C-native-v1',
    purpose: 'ship Sutra Native plugin v1.0',
    scope_in: 'M1-M12 milestones',
    scope_out: 'v2.0+ feature work',
    obligations: [obligation],
    invariants: [invariant],
    success_metrics: ['286+ tests green', 'codex CLEARED'],
    authority: 'inherited from D1.Sutra-OS',
    termination: 'when v3.0 supersedes v2.x',
    constraints: [episodic],
    acl,
  }
}

/**
 * Invalid: missing required `purpose`. Constructor must throw.
 */
export function invalidMissingRequired(): Partial<Charter> {
  return {
    id: 'C-no-purpose',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: '',
    termination: '',
    constraints: [],
    acl: [],
    scope_in: '',
    scope_out: '',
  }
}
