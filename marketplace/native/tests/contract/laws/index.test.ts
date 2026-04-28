/**
 * Barrel-export tests + defensive-branch coverage for the laws module.
 *
 * Targets:
 *   - laws/index.ts re-exports (lifts to 100%)
 *   - defensive null/non-object branches across all 6 laws + T1-T6
 *   - error/throw paths in predicate evaluators
 */
import { describe, it, expect } from 'vitest'
import * as laws from '../../../src/laws/index.js'
import {
  l1Data,
  l2Boundary,
  l3Activation,
  l4Commitment,
  l5Meta,
  l6Reflexivity,
  l4TerminalCheck,
  t1Postconditions,
  t2OutputSchemas,
  t4InterfaceContracts,
  t5NoAbandonedChildren,
  t6ReflexiveAuth,
} from '../../../src/laws/index.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import { createCharter } from '../../../src/primitives/charter.js'
import type { Constraint } from '../../../src/types/index.js'

describe('laws/index.ts barrel — re-export integrity', () => {
  it('exports all 6 laws + 1 terminal-check helper + named T1-T6 functions', () => {
    expect(typeof laws.l1Data.shouldPromoteToAsset).toBe('function')
    expect(typeof laws.l2Boundary.isValid).toBe('function')
    expect(typeof laws.l3Activation.shouldActivate).toBe('function')
    expect(typeof laws.l4Commitment.operationalizes).toBe('function')
    expect(typeof laws.l4TerminalCheck.runAll).toBe('function')
    expect(typeof laws.l5Meta.isValidContainment).toBe('function')
    expect(typeof laws.l6Reflexivity.requiresApproval).toBe('function')
    expect(typeof laws.t1Postconditions).toBe('function')
    expect(typeof laws.t2OutputSchemas).toBe('function')
    expect(typeof laws.t3StepTraces).toBe('function')
    expect(typeof laws.t4InterfaceContracts).toBe('function')
    expect(typeof laws.t5NoAbandonedChildren).toBe('function')
    expect(typeof laws.t6ReflexiveAuth).toBe('function')
  })
})

describe('Defensive branches — null/undefined/non-object inputs', () => {
  it('L1 — non-string stable_identity rejected', () => {
    expect(
      l1Data.shouldPromoteToAsset({ stable_identity: 123, lifecycle_states: ['a', 'b'] }),
    ).toBe(false)
  })

  it('L1 — lifecycle_states not an array rejected', () => {
    expect(
      l1Data.shouldPromoteToAsset({ stable_identity: 'id', lifecycle_states: 'nope' }),
    ).toBe(false)
  })

  it('L2 — null root JSON rejected', () => {
    expect(l2Boundary.isValid({ contract_schema: 'null' })).toBe(false)
  })

  it('L2 — number root JSON rejected', () => {
    expect(l2Boundary.isValid({ contract_schema: '42' })).toBe(false)
  })

  it('L2 — non-string contract_schema rejected', () => {
    expect(l2Boundary.isValid({ contract_schema: 123 })).toBe(false)
  })

  it('L2 — missing contract_schema key rejected', () => {
    expect(l2Boundary.isValid({ direction: 'inbound' })).toBe(false)
  })

  it('L3 — null event/spec rejected', () => {
    expect(l3Activation.shouldActivate(null, { id: 's' })).toBe(false)
    expect(l3Activation.shouldActivate({ spec_id: 's', payload: {} }, null)).toBe(false)
  })

  it('L3 — non-string spec.id rejected', () => {
    expect(
      l3Activation.shouldActivate(
        { spec_id: 's', payload: {} },
        { id: 123, payload_validator: () => true, route_predicate: () => true },
      ),
    ).toBe(false)
  })

  it('L3 — non-function payload_validator rejected', () => {
    expect(
      l3Activation.shouldActivate(
        { spec_id: 's', payload: {} },
        { id: 's', payload_validator: 'no', route_predicate: () => true },
      ),
    ).toBe(false)
  })

  it('L3 — non-function route_predicate rejected', () => {
    expect(
      l3Activation.shouldActivate(
        { spec_id: 's', payload: {} },
        { id: 's', payload_validator: () => true, route_predicate: 'no' },
      ),
    ).toBe(false)
  })

  it('L3 — throwing route_predicate returns false', () => {
    expect(
      l3Activation.shouldActivate(
        { spec_id: 's', payload: {} },
        {
          id: 's',
          payload_validator: () => true,
          route_predicate: () => {
            throw new Error('boom')
          },
        },
      ),
    ).toBe(false)
  })

  it('L4 commitment — null charter rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(
      l4Commitment.tracesAllSteps(w, null as never, {
        step_coverage: [],
        obligation_coverage: [],
      }),
    ).toBe(false)
  })

  it('L4 commitment — non-array step_graph rejected', () => {
    const c = createCharter({
      id: 'C-1',
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
    const broken = { step_graph: 'nope' }
    expect(
      l4Commitment.tracesAllSteps(broken as never, c, {
        step_coverage: [],
        obligation_coverage: [],
      }),
    ).toBe(false)
  })

  it('L4 commitment — non-array step_coverage rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
    })
    const c = createCharter({
      id: 'C-1',
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
    expect(
      l4Commitment.tracesAllSteps(w, c, {
        step_coverage: 'nope' as never,
        obligation_coverage: [],
      }),
    ).toBe(false)
  })

  it('L4 commitment — coversAllObligations rejects null charter', () => {
    expect(
      l4Commitment.coversAllObligations(null as never, {
        step_coverage: [],
        obligation_coverage: [],
      }),
    ).toBe(false)
  })

  it('L4 commitment — non-array obligation_coverage rejected', () => {
    const c = createCharter({
      id: 'C-1',
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
    expect(
      l4Commitment.coversAllObligations(c, {
        step_coverage: [],
        obligation_coverage: 'nope' as never,
      }),
    ).toBe(false)
  })

  it('L4 commitment — non-string obligation_name rejected', () => {
    const c = createCharter({
      id: 'C-1',
      purpose: 'p',
      scope_in: '',
      scope_out: '',
      obligations: [
        { name: 'o1', predicate: 'p', durability: 'durable', owner_scope: 'charter', type: 'obligation' },
      ],
      invariants: [],
      success_metrics: [],
      authority: '',
      termination: '',
      constraints: [],
      acl: [],
    })
    expect(
      l4Commitment.coversAllObligations(c, {
        step_coverage: [],
        obligation_coverage: [{ obligation_name: 123 as never, covered_by_step: 0 }],
      }),
    ).toBe(false)
  })

  it('L4 terminal-check — null context rejected', () => {
    const r = l4TerminalCheck.runAll(null as never)
    expect(r.pass).toBe(false)
    expect(r.failed_at).toBe('T1')
  })

  it('T1 — non-array predicates rejected', () => {
    expect(t1Postconditions('nope' as never, [])).toBe(false)
  })

  it('T1 — non-array outputs rejected', () => {
    expect(t1Postconditions([], 'nope' as never)).toBe(false)
  })

  it('T1 — non-function predicate rejected', () => {
    expect(t1Postconditions(['nope' as never], [])).toBe(false)
  })

  it('T1 — throwing predicate returns false', () => {
    const throwingP = () => {
      throw new Error('p')
    }
    expect(t1Postconditions([throwingP], [])).toBe(false)
  })

  it('T2 — non-function validator rejected', () => {
    expect(
      t2OutputSchemas(
        [
          {
            kind: 'k',
            schema_ref: 's',
            locator: 'l',
            version: '',
            mutability: 'immutable',
            retention: '',
          },
        ],
        ['nope' as never],
      ),
    ).toBe(false)
  })

  it('T2 — throwing validator returns false', () => {
    expect(
      t2OutputSchemas(
        [
          {
            kind: 'k',
            schema_ref: 's',
            locator: 'l',
            version: '',
            mutability: 'immutable',
            retention: '',
          },
        ],
        [
          () => {
            throw new Error('v')
          },
        ],
      ),
    ).toBe(false)
  })

  it('T2 — non-array outputs rejected', () => {
    expect(t2OutputSchemas('nope' as never, [])).toBe(false)
  })

  it('T2 — non-array validators rejected', () => {
    expect(t2OutputSchemas([], 'nope' as never)).toBe(false)
  })

  it('T4 — non-array views rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(t4InterfaceContracts(w, 'nope' as never)).toBe(false)
  })

  it('T4 — null view rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [
        {
          endpoint_ref: 'ep',
          workflow_ref: 'W-1',
          direction: 'outbound',
          contract_schema: '{}',
          qos: '',
          failure_modes: [],
        },
      ],
    })
    expect(t4InterfaceContracts(w, [null as never])).toBe(false)
  })

  it('T4 — non-number contract_violations rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [
        {
          endpoint_ref: 'ep',
          workflow_ref: 'W-1',
          direction: 'outbound',
          contract_schema: '{}',
          qos: '',
          failure_modes: [],
        },
      ],
    })
    expect(t4InterfaceContracts(w, [{ contract_violations: 'nope' as never }])).toBe(false)
  })

  it('T5 — empty selfExecutionId rejected', () => {
    expect(t5NoAbandonedChildren('', [])).toBe(false)
  })

  it('T5 — non-array children rejected', () => {
    expect(t5NoAbandonedChildren('E-self', 'nope' as never)).toBe(false)
  })

  it('T5 — null child rejected', () => {
    expect(t5NoAbandonedChildren('E-self', [null as never])).toBe(false)
  })

  it('T6 — non-boolean modifies_sutra rejected', () => {
    expect(
      t6ReflexiveAuth({ modifies_sutra: 'nope' } as never, {
        founder_authorization: false,
        meta_charter_approval: false,
      }),
    ).toBe(false)
  })

  it('T6 — null auth rejected when modifies_sutra=true', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    expect(t6ReflexiveAuth(w, null as never)).toBe(false)
  })

  it('T6 — non-boolean auth fields rejected', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    expect(
      t6ReflexiveAuth(w, { founder_authorization: 'nope' as never, meta_charter_approval: false }),
    ).toBe(false)
  })

  it('L5 — invalid parent kind rejected', () => {
    expect(l5Meta.isValidContainment('alien' as never, 'charter')).toBe(false)
    expect(l5Meta.isValidEdge('contains', 'alien' as never, 'charter')).toBe(false)
  })

  it('L5 — invalid child kind rejected', () => {
    expect(l5Meta.isValidContainment('domain', 'alien' as never)).toBe(false)
    expect(l5Meta.isValidEdge('operationalizes', 'domain', 'alien' as never)).toBe(false)
  })

  it('L6 — null workflow returns true (defensive: requires approval)', () => {
    expect(l6Reflexivity.requiresApproval(null as never, [])).toBe(true)
  })

  it('L6 — non-boolean modifies_sutra returns true', () => {
    expect(l6Reflexivity.requiresApproval({ modifies_sutra: 'nope' } as never, [])).toBe(true)
  })

  it('L6 — non-array constraints returns true (modifies_sutra=true case)', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    expect(l6Reflexivity.requiresApproval(w, 'nope' as never)).toBe(true)
  })

  it('L6 — empty-named reflexive_check Constraint is skipped (still requires approval)', () => {
    const w = createWorkflow({
      id: 'W-1',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' }],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      modifies_sutra: true,
    })
    const c: Constraint = {
      name: '',
      predicate: 'p',
      durability: 'durable',
      owner_scope: 'workflow',
      type: 'reflexive_check',
    }
    expect(l6Reflexivity.requiresApproval(w, [c])).toBe(true)
  })

  it('L6 — reflexiveChecks(non-array) returns []', () => {
    expect(l6Reflexivity.reflexiveChecks('nope' as never)).toEqual([])
  })
})
