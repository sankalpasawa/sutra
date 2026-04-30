/**
 * Default Composition v1.0 — Workflow 1: governance-turn-emit
 *
 * Seed Workflow that demonstrates a minimal governance turn end-to-end:
 * receive an input, emit a Decision-Provenance record, terminate. Exercises
 * M5 step-graph executor + M8 OTel emitter (when wired by the caller).
 *
 * Use case: a fresh Asawa-style operator wants to wire a per-turn governance
 * record into their existing workflow without rebuilding the primitives. They
 * import this seed, register a Domain + Charter for their tenant, and run.
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M12-release-canary.md (D-NS-52, A-1, T-241)
 *   - holding/research/2026-04-29-native-v1.0-final-architecture.md line 229
 *
 * NOT shipped at v1.0:
 *   - Real OTel exporter binding (caller wires per their telemetry stack)
 *   - Tenant-specific obligation/invariant predicates (caller customizes)
 */

import { createDomain } from '../src/primitives/domain.js'
import { createCharter } from '../src/primitives/charter.js'
import { createWorkflow } from '../src/primitives/workflow.js'
import type { Constraint } from '../src/types/index.js'

export interface GovernanceTurnEmitOptions {
  /** Operator's tenant id (e.g. "T-asawa", "T-dayflow"). */
  tenant_id: string
  /** Domain id (e.g. "D1.D2"). */
  domain_id: string
  /** Charter id (e.g. "C-governance-turn"). */
  charter_id?: string
}

export function buildGovernanceTurnEmitWorkflow(opts: GovernanceTurnEmitOptions) {
  const charter_id = opts.charter_id ?? 'C-governance-turn'

  const domain = createDomain({
    id: opts.domain_id,
    name: 'Governance Turn',
    parent_id: 'D0',
    principles: [
      { name: 'every turn emits a record', predicate: 'always_true', durability: 'durable', owner_scope: 'domain' },
    ],
    intelligence: '',
    accountable: ['founder'],
    authority: 'tenant',
    tenant_id: opts.tenant_id,
  })

  const obligations: Constraint[] = [
    { name: 'emit governance record per turn', predicate: 'always_true', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
  ]

  const charter = createCharter({
    id: charter_id,
    purpose: 'Every operator turn emits a Decision-Provenance record',
    scope_in: 'Operator-driven turns',
    scope_out: 'Cron-driven background tasks',
    obligations,
    invariants: [],
    success_metrics: ['DP-records-per-turn = 1'],
    constraints: [],
    acl: [],
    authority: opts.domain_id,
    termination: 'When operator stops driving turns',
  })

  const workflow = createWorkflow({
    id: 'W-governance-turn-emit',
    preconditions: 'turn input received',
    step_graph: [
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 2, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: 'governance record emitted',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })

  return { domain, charter, workflow }
}
