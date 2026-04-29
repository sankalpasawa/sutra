/**
 * Forbidden couplings (F-1..F-8, F-10, F-11) — property tests.
 *
 * M4.9 per holding/plans/native-v1.0/TASK-QUEUE.md.
 * Group D shipped: F-1..F-4 (≥1000 fast-check cases each).
 * Group E shipped: F-5..F-8 (≥1000 fast-check cases each).
 * Group F: F-10 + terminalCheck aggregator.
 * Group G' (2026-04-29): F-11 (extension_ref null in v1.0) per codex master.
 *
 * F-9 (D38 plugin shipment) is hook-level — DEFERRED to M8 per codex P1.3.
 *
 * Spec source:
 *  - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §3 §7.3
 *  - holding/plans/native-v1.0/M4-schemas-edges.md M4.9
 */

import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import {
  f1Predicate,
  f2Predicate,
  f3Predicate,
  f4Predicate,
  f5Predicate,
  f6Predicate,
  f7Predicate,
  f8Predicate,
  f10Predicate,
  f11Predicate,
  terminalCheck,
  type ReflexiveAuth,
} from '../../src/laws/l4-terminal-check.js'
import {
  ROUTING_GATING_POSITIONS,
  ROUTING_GATING_REPRESENTATIONS,
  isMachineCheckable,
} from '../../src/laws/routing-gating-positions.js'
import type { Workflow } from '../../src/primitives/workflow.js'
import type { Execution } from '../../src/primitives/execution.js'
import type { Charter } from '../../src/primitives/charter.js'
import type { DecisionProvenance } from '../../src/schemas/decision-provenance.js'
import type { Tenant } from '../../src/schemas/tenant.js'
import type { DelegatesToEdge } from '../../src/types/edges.js'

const PROP_RUNS = 1000

// ---- shared arbitraries ----------------------------------------------------

const tenantIdArb = fc
  .string({ minLength: 1, maxLength: 16 })
  .filter((s) => /^[a-z0-9-]+$/.test(s))
  .map((s) => `T-${s}`)

const domainIdArb = fc
  .array(fc.integer({ min: 0, max: 99 }), { minLength: 1, maxLength: 3 })
  .map((nums) => nums.map((n) => `D${n}`).join('.'))

const workflowIdArb = fc.string({ minLength: 1, maxLength: 12 }).map((s) => `W-${s}`)
const charterIdArb = fc.string({ minLength: 1, maxLength: 12 }).map((s) => `C-${s}`)

// =============================================================================
// Group D — F-1..F-4 (T-021..T-024)
// =============================================================================

describe('F-1: Tenant directly contains Workflow (skips Domain + Charter)', () => {
  it('VIOLATION (true) for chains [Tenant, Workflow] (length 2 — no Domain + Charter)', () => {
    fc.assert(
      fc.property(tenantIdArb, workflowIdArb, (tid, wid) => {
        const result = f1Predicate({
          tenant: { id: tid },
          workflow: { id: wid },
          containment_chain: [tid, wid],
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) for well-formed chains [Tenant, Domain, Charter, Workflow]', () => {
    fc.assert(
      fc.property(
        tenantIdArb,
        domainIdArb,
        charterIdArb,
        workflowIdArb,
        (tid, did, cid, wid) => {
          const result = f1Predicate({
            tenant: { id: tid },
            workflow: { id: wid },
            containment_chain: [tid, did, cid, wid],
          })
          return result === false
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-2: Workflow without operationalizes link to Charter', () => {
  it('VIOLATION (true) for empty operationalizes_charters list', () => {
    fc.assert(
      fc.property(workflowIdArb, (wid) => {
        const result = f2Predicate({
          workflow: { id: wid },
          operationalizes_charters: [],
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) for non-empty operationalizes_charters list', () => {
    fc.assert(
      fc.property(
        workflowIdArb,
        fc.array(charterIdArb, { minLength: 1, maxLength: 4 }),
        (wid, charters) => {
          const result = f2Predicate({
            workflow: { id: wid },
            operationalizes_charters: charters,
          })
          return result === false
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-3: Execution spawned without TriggerEvent', () => {
  it('VIOLATION (true) for empty trigger_event', () => {
    fc.assert(
      fc.property(fc.constant(''), (te) => {
        const result = f3Predicate({ execution: { trigger_event: te } })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) for non-empty trigger_event', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 30 }), (te) => {
        const result = f3Predicate({ execution: { trigger_event: te } })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-4: step_graph[i] with both skill_ref AND action set', () => {
  it('VIOLATION (true) when any step has both skill_ref AND action', () => {
    const stepBothArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      skill_ref: fc.string({ minLength: 1, maxLength: 16 }),
      action: fc.constantFrom('spawn_sub_unit', 'wait', 'terminate'),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    fc.assert(
      fc.property(fc.array(stepBothArb, { minLength: 1, maxLength: 4 }), (steps) => {
        const result = f4Predicate({
          workflow: { step_graph: steps as unknown as Workflow['step_graph'] },
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when every step has exactly one of skill_ref XOR action', () => {
    const stepSkillArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      skill_ref: fc.string({ minLength: 1, maxLength: 16 }),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    const stepActionArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      action: fc.constantFrom('spawn_sub_unit', 'wait', 'terminate'),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    const xorStep = fc.oneof(stepSkillArb, stepActionArb)
    fc.assert(
      fc.property(fc.array(xorStep, { minLength: 1, maxLength: 4 }), (steps) => {
        const result = f4Predicate({
          workflow: { step_graph: steps as unknown as Workflow['step_graph'] },
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// Group E — F-5..F-8 (T-025..T-028)
// =============================================================================

describe('F-5: step_graph[i] with neither skill_ref NOR action', () => {
  it('VIOLATION (true) when any step has neither skill_ref nor action', () => {
    const emptyStepArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    fc.assert(
      fc.property(fc.array(emptyStepArb, { minLength: 1, maxLength: 4 }), (steps) => {
        const result = f5Predicate({
          workflow: { step_graph: steps as unknown as Workflow['step_graph'] },
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when every step has at least one of skill_ref or action', () => {
    const stepSkillArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      skill_ref: fc.string({ minLength: 1, maxLength: 16 }),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    const stepActionArb = fc.record({
      step_id: fc.integer({ min: 0, max: 50 }),
      action: fc.constantFrom('spawn_sub_unit', 'wait', 'terminate'),
      inputs: fc.constant([]),
      outputs: fc.constant([]),
      on_failure: fc.constantFrom('rollback', 'escalate', 'pause', 'abort', 'continue'),
    })
    fc.assert(
      fc.property(
        fc.array(fc.oneof(stepSkillArb, stepActionArb), { minLength: 1, maxLength: 4 }),
        (steps) => {
          const result = f5Predicate({
            workflow: { step_graph: steps as unknown as Workflow['step_graph'] },
          })
          return result === false
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-6: Cross-tenant operation without TenantDelegation (uses delegates_to from M4.8)', () => {
  it('VIOLATION (true) when custody_owner != operating tenant AND no delegates_to edge', () => {
    fc.assert(
      fc.property(tenantIdArb, tenantIdArb, (opTenant, otherTenant) => {
        fc.pre(opTenant !== otherTenant)
        const result = f6Predicate({
          workflow: { custody_owner: otherTenant },
          operating_tenant_id: opTenant,
          delegates_to_edges: [],
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when delegates_to edge bridges operating → custody_owner', () => {
    fc.assert(
      fc.property(tenantIdArb, tenantIdArb, (opTenant, otherTenant) => {
        fc.pre(opTenant !== otherTenant)
        const edge: DelegatesToEdge = {
          kind: 'delegates_to',
          source: opTenant,
          target: otherTenant,
        }
        const result = f6Predicate({
          workflow: { custody_owner: otherTenant },
          operating_tenant_id: opTenant,
          delegates_to_edges: [edge],
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when custody_owner is null (single-tenant)', () => {
    fc.assert(
      fc.property(tenantIdArb, (opTenant) => {
        const result = f6Predicate({
          workflow: { custody_owner: null },
          operating_tenant_id: opTenant,
          delegates_to_edges: [],
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-7: Workflow.modifies_sutra=true without reflexive_check Constraint cleared', () => {
  it('VIOLATION (true) when modifies_sutra=true AND no auth granted', () => {
    fc.assert(
      fc.property(fc.constant(true), (modifies) => {
        const auth: ReflexiveAuth = {
          founder_authorization: false,
          meta_charter_approval: false,
        }
        const result = f7Predicate({
          workflow: { modifies_sutra: modifies },
          reflexive_auth: auth,
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when modifies_sutra=true AND ≥1 auth granted', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), (founder, meta) => {
        fc.pre(founder || meta)
        const auth: ReflexiveAuth = {
          founder_authorization: founder,
          meta_charter_approval: meta,
        }
        const result = f7Predicate({
          workflow: { modifies_sutra: true },
          reflexive_auth: auth,
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when modifies_sutra=false (no L6 gate fires)', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), (founder, meta) => {
        const auth: ReflexiveAuth = {
          founder_authorization: founder,
          meta_charter_approval: meta,
        }
        const result = f7Predicate({
          workflow: { modifies_sutra: false },
          reflexive_auth: auth,
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

describe('F-8: DecisionProvenance without policy_id + policy_version', () => {
  type DpFields = Pick<DecisionProvenance, 'policy_id' | 'policy_version'>

  it('VIOLATION (true) when policy_id is empty', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 16 }), (ver) => {
        const dp: DpFields = { policy_id: '', policy_version: ver }
        const result = f8Predicate({ dp })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('VIOLATION (true) when policy_version is empty', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 16 }), (id) => {
        const dp: DpFields = { policy_id: id, policy_version: '' }
        const result = f8Predicate({ dp })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when both policy_id and policy_version are non-empty', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 16 }),
        fc.string({ minLength: 1, maxLength: 16 }),
        (id, ver) => {
          const dp: DpFields = { policy_id: id, policy_version: ver }
          const result = f8Predicate({ dp })
          return result === false
        },
      ),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// Group F — F-10 + aggregator (T-029..T-031)
// =============================================================================

describe('F-10: English-only fields in routing/gating positions', () => {
  it('SAFE (false) — all 10 inventoried positions register a representation kind', () => {
    // F-10 is a static inventory check; we run it under fc.property to keep
    // the cadence consistent (≥1000 cases) per task spec, even though the
    // function is a no-arg pure check.
    fc.assert(
      fc.property(fc.integer(), () => {
        return f10Predicate() === false
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('inventory has exactly 10 positions and each is machine-checkable', () => {
    // Sanity assertion on the inventory itself.
    fc.assert(
      fc.property(fc.integer({ min: 0, max: ROUTING_GATING_POSITIONS.length - 1 }), (i) => {
        const pos = ROUTING_GATING_POSITIONS[i]!
        return (
          ROUTING_GATING_POSITIONS.length === 10 &&
          isMachineCheckable(pos) &&
          pos in ROUTING_GATING_REPRESENTATIONS
        )
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// Group G' — F-11 (extension_ref null in v1.0)
// =============================================================================

describe('F-11: Workflow.extension_ref non-null in v1.0 (D4 §7.3)', () => {
  const validExtensionRefArb = fc
    .string({ minLength: 1, maxLength: 24 })
    .filter((s) => /^[a-z0-9-]+$/.test(s) && s.length > 0)
    .map((s) => `ext-${s}`)

  it('VIOLATION (true) for any non-null extension_ref', () => {
    fc.assert(
      fc.property(validExtensionRefArb, (ref) => {
        const result = f11Predicate({
          workflow: { extension_ref: ref },
        })
        return result === true
      }),
      { numRuns: PROP_RUNS },
    )
  })

  it('SAFE (false) when extension_ref is null (v1.0 default)', () => {
    fc.assert(
      fc.property(fc.constant(null), (ref) => {
        const result = f11Predicate({
          workflow: { extension_ref: ref },
        })
        return result === false
      }),
      { numRuns: PROP_RUNS },
    )
  })
})

// =============================================================================
// Aggregator — terminalCheck(...)
// =============================================================================

describe('terminalCheck aggregator (F-1..F-8 + F-10)', () => {
  function makeMinimalSafeInput(): Parameters<typeof terminalCheck>[0] {
    const tenantId = 'T-default'
    const workflow: Workflow = {
      id: 'W-safe',
      preconditions: '',
      autonomy_level: 'manual',
      step_graph: [
        {
          step_id: 0,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate',
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
    }
    const execution: Execution = {
      id: 'E-safe',
      workflow_id: 'W-safe',
      trigger_event: 'turn_start',
      state: 'success',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp-1',
      failure_reason: null,
      agent_identity: null,
    }
    const charter: Charter = {
      id: 'C-safe',
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
    }
    const tenant: Tenant = {
      id: tenantId,
      name: 'default',
      isolation_contract: 'single-tenant',
      parent_tenant_id: null,
      managed_agents_session: null,
      audit_log_path: null,
    }
    return {
      workflow,
      execution,
      charter,
      tenant,
      operationalizes_charters: ['C-safe'],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
    }
  }

  it('returns pass=true with empty violations list for minimal SAFE input', () => {
    fc.assert(
      fc.property(fc.integer(), () => {
        const result = terminalCheck(makeMinimalSafeInput())
        return result.pass === true && result.violations.length === 0
      }),
      { numRuns: 200 },
    )
  })

  it('aggregates F-2 + F-3 violations when both fire', () => {
    fc.assert(
      fc.property(fc.integer(), () => {
        const input = makeMinimalSafeInput()
        // Trigger F-2 (no operationalizes link).
        input.operationalizes_charters = []
        // Trigger F-3 (empty trigger_event).
        input.execution = { ...input.execution, trigger_event: '' }
        const result = terminalCheck(input)
        return (
          result.pass === false &&
          result.violations.includes('F-2') &&
          result.violations.includes('F-3')
        )
      }),
      { numRuns: 200 },
    )
  })

  it('skips F-1 when containment_chain omitted; skips F-8 when dp omitted', () => {
    fc.assert(
      fc.property(fc.integer(), () => {
        const input = makeMinimalSafeInput()
        // No containment_chain; no dp. SAFE input otherwise.
        const result = terminalCheck(input)
        return (
          result.pass === true &&
          !result.violations.includes('F-1') &&
          !result.violations.includes('F-8')
        )
      }),
      { numRuns: 200 },
    )
  })

  it('catches F-6 cross-tenant op without delegates_to edge', () => {
    fc.assert(
      fc.property(fc.integer(), () => {
        const input = makeMinimalSafeInput()
        input.workflow = { ...input.workflow, custody_owner: 'T-other' }
        input.delegates_to_edges = []
        const result = terminalCheck(input)
        return result.pass === false && result.violations.includes('F-6')
      }),
      { numRuns: 200 },
    )
  })

  it('catches F-11 when extension_ref is non-null (v1.0 violation)', () => {
    fc.assert(
      fc.property(fc.integer(), () => {
        const input = makeMinimalSafeInput()
        input.workflow = { ...input.workflow, extension_ref: 'ext-test' }
        const result = terminalCheck(input)
        return result.pass === false && result.violations.includes('F-11')
      }),
      { numRuns: 200 },
    )
  })

  it('catches F-8 violation when dp lacks policy_id', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 12 }), (ver) => {
        const input = makeMinimalSafeInput()
        input.dp = {
          id: 'dp-deadbeef',
          actor: 'a',
          agent_identity: { kind: 'claude-opus', id: 'claude-opus:test' },
          timestamp: '2026-04-29T00:00:00.000Z',
          evidence: [],
          authority_id: 'auth',
          policy_id: '', // empty -> F-8 fires
          policy_version: ver,
          confidence: 0.5,
          decision_kind: 'DECIDE',
          scope: 'EXECUTION',
          outcome: 'ok',
          next_action_ref: null,
        } as DecisionProvenance
        const result = terminalCheck(input)
        return result.pass === false && result.violations.includes('F-8')
      }),
      { numRuns: 200 },
    )
  })
})
