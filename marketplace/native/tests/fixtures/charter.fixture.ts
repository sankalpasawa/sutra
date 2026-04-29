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

// -----------------------------------------------------------------------------
// M4.7 — cutover_contract fixture variants (per TASK-QUEUE.md §1 T-011)
// -----------------------------------------------------------------------------

/**
 * Charter with a minimal valid cutover_contract — single behavior_invariant +
 * short engine ids. Useful for: smoke tests, contract round-trip checks,
 * cutover engine seed scenarios at M10.
 */
export function validMinimalWithCutover(): Charter {
  return {
    ...validMinimal(),
    id: 'C-cutover-min',
    purpose: 'minimum viable charter with cutover contract',
    cutover_contract: {
      source_engine: 'engine-a',
      target_engine: 'engine-b',
      behavior_invariants: ['no_data_loss'],
      rollback_gate: 'failure_count > 0',
      canary_window: '60s',
    },
  }
}

/**
 * Charter with a fully-populated cutover_contract — multiple behavior
 * invariants, realistic Core→Native engine ids, ISO-8601-style canary window.
 * Mirrors the canonical example from D1 §11.1.
 */
export function validFullWithCutover(): Charter {
  return {
    ...validFull(),
    id: 'C-cutover-full',
    cutover_contract: {
      source_engine: 'sutra-core-v2.8',
      target_engine: 'sutra-native-v1.0',
      behavior_invariants: [
        'no_data_loss',
        'latency_within_5_percent',
        'no_authority_drift',
      ],
      rollback_gate: 'error_rate > 0.01 OR latency_p99 > baseline * 1.5',
      canary_window: 'PT168H',
    },
  }
}

/**
 * Invalid Charter: cutover_contract is set but `behavior_invariants` is empty.
 * Constructor must throw — schema requires `min(1)` when contract is set.
 */
export function invalidEmptyInvariants(): Charter {
  return {
    ...validMinimal(),
    id: 'C-cutover-empty-invariants',
    purpose: 'cutover with empty invariants — must be rejected',
    cutover_contract: {
      source_engine: 'engine-a',
      target_engine: 'engine-b',
      behavior_invariants: [],
      rollback_gate: 'r',
      canary_window: '60s',
    },
  }
}
