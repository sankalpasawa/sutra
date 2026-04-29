/**
 * L4 TERMINAL-CHECK — property tests (V2.4 §A12 T1-T6)
 *
 * Every T_i gets at least one positive (true → pass) and one negative
 * (false → fail) property. T6 also covers the modifies_sutra=false (no-op)
 * branch.
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  t1Postconditions,
  t2OutputSchemas,
  t3StepTraces,
  t4InterfaceContracts,
  t5NoAbandonedChildren,
  t6ReflexiveAuth,
  l4TerminalCheck,
  type SchemaValidator,
  type InterfaceViolationsView,
  type ReflexiveAuth,
  type TerminalCheckContext,
} from '../../src/laws/l4-terminal-check.js'
import {
  workflowArb,
  charterArb,
  dataRefArb,
  interfaceArb,
  constraintArb,
} from './arbitraries.js'
import type { Execution } from '../../src/primitives/execution.js'
import type { CoverageMatrix } from '../../src/laws/l4-commitment.js'

const TRUE_PRED = (() => true) as (outputs: ReadonlyArray<unknown>) => boolean
const FALSE_PRED = (() => false) as (outputs: ReadonlyArray<unknown>) => boolean
const ALWAYS_VALID: SchemaValidator = () => true
const ALWAYS_INVALID: SchemaValidator = () => false

describe('T1 — postconditions', () => {
  it('forall outputs + all-true predicates: T1 passes', () => {
    fc.assert(
      fc.property(fc.array(dataRefArb, { maxLength: 5 }), fc.integer({ min: 0, max: 5 }), (outputs, n) => {
        const preds = Array.from({ length: n }, () => TRUE_PRED)
        return t1Postconditions(preds, outputs) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall outputs + ≥1 false predicate: T1 fails', () => {
    fc.assert(
      fc.property(fc.array(dataRefArb, { maxLength: 5 }), fc.integer({ min: 0, max: 4 }), (outputs, before) => {
        const preds = [
          ...Array.from({ length: before }, () => TRUE_PRED),
          FALSE_PRED,
        ]
        return t1Postconditions(preds, outputs) === false
      }),
      { numRuns: 1000 },
    )
  })
})

describe('T2 — output schemas', () => {
  it('forall outputs + matching all-valid validators: T2 passes', () => {
    fc.assert(
      fc.property(fc.array(dataRefArb, { maxLength: 5 }), (outputs) => {
        const validators = outputs.map(() => ALWAYS_VALID)
        return t2OutputSchemas(outputs, validators) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall outputs + ≥1 invalid validator: T2 fails', () => {
    fc.assert(
      fc.property(
        fc.array(dataRefArb, { minLength: 1, maxLength: 5 }),
        fc.integer({ min: 0 }),
        (outputs, badIdxRaw) => {
          const validators = outputs.map(() => ALWAYS_VALID)
          const badIdx = badIdxRaw % outputs.length
          validators[badIdx] = ALWAYS_INVALID
          return t2OutputSchemas(outputs, validators) === false
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall outputs + length-mismatched validators: T2 fails', () => {
    fc.assert(
      fc.property(fc.array(dataRefArb, { minLength: 1, maxLength: 5 }), (outputs) => {
        const validators = outputs.slice(1).map(() => ALWAYS_VALID)
        return t2OutputSchemas(outputs, validators) === false
      }),
      { numRuns: 1000 },
    )
  })
})

describe('T3 — step traces', () => {
  it('forall (W, C) with happy coverage: T3 passes', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 3,
          }),
        }),
        (w, c) => {
          const allowed = [...c.obligations.map((o) => o.name), ...c.invariants.map((i) => i.name)]
          // T3 only checks tracesAllSteps; allowed[0] is sufficient (every
          // step traces to ≥1 allowed name). Relation-check (codex M3 P1)
          // applies only to coversAllObligations / operationalizes.
          const cov: CoverageMatrix = {
            step_coverage: w.step_graph.map((s) =>
              allowed.length > 0
                ? { step_id: s.step_id, traces_to: [allowed[0]!] }
                : { step_id: s.step_id, traces_to: [], gap_status: 'accepted' as const },
            ),
            obligation_coverage: c.obligations.map((o) => ({
              obligation_name: o.name,
              covered_by_step: w.step_graph[0]!.step_id,
            })),
          }
          return t3StepTraces(w, c, cov) === true
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall (W, C) with bogus traces_to (random name): T3 fails', () => {
    fc.assert(
      fc.property(
        workflowArb(),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 1,
            maxLength: 2,
          }),
        }),
        fc.string({ minLength: 1, maxLength: 8 }),
        (w, c, randomName) => {
          // Ensure randomName isn't an actual obligation/invariant name.
          const reserved = new Set([
            ...c.obligations.map((o) => o.name),
            ...c.invariants.map((i) => i.name),
          ])
          if (reserved.has(randomName)) return true // skip
          const cov: CoverageMatrix = {
            step_coverage: w.step_graph.map((s) => ({
              step_id: s.step_id,
              traces_to: [randomName],
            })),
            obligation_coverage: [],
          }
          return t3StepTraces(w, c, cov) === false
        },
      ),
      { numRuns: 1000 },
    )
  })
})

describe('T4 — interface contracts', () => {
  it('forall workflow with all-zero contract_violations: T4 passes', () => {
    fc.assert(
      fc.property(workflowArb(), (w) => {
        const views: InterfaceViolationsView[] = w.interfaces_with.map(() => ({ contract_violations: 0 }))
        return t4InterfaceContracts(w, views) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall workflow with ≥1 non-zero contract_violations: T4 fails', () => {
    fc.assert(
      fc.property(
        fc
          .record({
            ...{
              id: fc.string({ minLength: 1, maxLength: 8 }).map((s) => `W-${s}`),
              preconditions: fc.string({ maxLength: 8 }),
              step_graph: fc.array(
                fc.record({
                  step_id: fc.integer({ min: 0, max: 5 }),
                  action: fc.constant<'wait'>('wait'),
                  inputs: fc.constant([]),
                  outputs: fc.constant([]),
                  on_failure: fc.constant<'abort'>('abort'),
                }),
                { minLength: 1, maxLength: 1 },
              ),
              inputs: fc.constant([]),
              outputs: fc.constant([]),
              state: fc.constant([]),
              postconditions: fc.constant(''),
              failure_policy: fc.constant(''),
              stringency: fc.constant<'task'>('task'),
              interfaces_with: fc.array(interfaceArb(), { minLength: 1, maxLength: 3 }),
              expects_response_from: fc.constant<null>(null),
              on_override_action: fc.constant<'escalate'>('escalate'),
              reuse_tag: fc.constant(false),
              return_contract: fc.constant<null>(null),
              modifies_sutra: fc.constant(false),
              custody_owner: fc.constant<null>(null),
              extension_ref: fc.constant<null>(null),
              autonomy_level: fc.constant<'manual'>('manual'),
            },
          }),
        fc.integer({ min: 1, max: 99 }),
        (w, badCount) => {
          const views: InterfaceViolationsView[] = w.interfaces_with.map((_, i) => ({
            contract_violations: i === 0 ? badCount : 0,
          }))
          return t4InterfaceContracts(w, views) === false
        },
      ),
      { numRuns: 1000 },
    )
  })
})

describe('T5 — no abandoned children', () => {
  const childArb = (parentId: string, state: Execution['state']): fc.Arbitrary<Execution> =>
    fc.record({
      id: fc.string({ minLength: 1, maxLength: 8 }).map((s) => `E-${s}`),
      workflow_id: fc.string({ minLength: 1, maxLength: 8 }).map((s) => `W-${s}`),
      trigger_event: fc.constant('t'),
      state: fc.constant(state),
      logs: fc.constant([]),
      results: fc.constant([]),
      parent_exec_id: fc.constant<string | null>(parentId),
      sibling_group: fc.constant<string | null>(null),
      fingerprint: fc.constant('fp'),
      failure_reason: fc.constant<string | null>(state === 'failed' ? 'r' : null),
      agent_identity: fc.constant(null),
    }) as fc.Arbitrary<Execution>

  it('forall children all in {success, declared_gap, escalated}: T5 passes', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 8 }).map((s) => `E-${s}`),
        fc.array(
          fc.constantFrom<Execution['state']>('success', 'declared_gap', 'escalated'),
          { maxLength: 5 },
        ),
        (selfId, states) => {
          const children = states.map(
            (st, i) =>
              ({
                id: `E-c${i}`,
                workflow_id: 'W-x',
                trigger_event: 't',
                state: st,
                logs: [],
                results: [],
                parent_exec_id: selfId,
                sibling_group: null,
                fingerprint: 'fp',
                failure_reason: null,
                agent_identity: null,
              }) as Execution,
          )
          return t5NoAbandonedChildren(selfId, children) === true
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall ≥1 child in {failed, running, pending}: T5 fails', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 8 }).map((s) => `E-${s}`),
        fc.constantFrom<Execution['state']>('failed', 'running', 'pending'),
        (selfId, badState) => {
          const child = {
            id: 'E-bad',
            workflow_id: 'W-x',
            trigger_event: 't',
            state: badState,
            logs: [],
            results: [],
            parent_exec_id: selfId,
            sibling_group: null,
            fingerprint: 'fp',
            failure_reason: badState === 'failed' ? 'r' : null,
            agent_identity: null,
          } as Execution
          return t5NoAbandonedChildren(selfId, [child]) === false
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forall children belonging to a DIFFERENT parent: T5 ignores them (passes)', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 8 }).map((s) => `E-${s}`),
        fc.string({ minLength: 1, maxLength: 8 }).map((s) => `E-${s}`),
        fc.constantFrom<Execution['state']>('failed', 'running', 'pending'),
        (selfId, otherParent, badState) => {
          if (otherParent === selfId) return true
          const child = {
            id: 'E-x',
            workflow_id: 'W-x',
            trigger_event: 't',
            state: badState,
            logs: [],
            results: [],
            parent_exec_id: otherParent,
            sibling_group: null,
            fingerprint: 'fp',
            failure_reason: badState === 'failed' ? 'r' : null,
            agent_identity: null,
          } as Execution
          return t5NoAbandonedChildren(selfId, [child]) === true
        },
      ),
      { numRuns: 1000 },
    )
  })

  // Use childArb to keep the local helper exercised (and exported pattern usable).
  it('childArb helper produces consistent shape', () => {
    fc.assert(
      fc.property(childArb('E-parent', 'success'), (c) => c.parent_exec_id === 'E-parent'),
      { numRuns: 50 },
    )
  })
})

describe('T6 — reflexive auth', () => {
  it('forall workflow with modifies_sutra=false: T6 passes regardless of auth', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: false }), fc.boolean(), fc.boolean(), (w, fa, mca) => {
        const auth: ReflexiveAuth = { founder_authorization: fa, meta_charter_approval: mca }
        return t6ReflexiveAuth(w, auth) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall workflow with modifies_sutra=true + at least one auth=true: T6 passes', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: true }), fc.boolean(), (w, useFounder) => {
        const auth: ReflexiveAuth = useFounder
          ? { founder_authorization: true, meta_charter_approval: false }
          : { founder_authorization: false, meta_charter_approval: true }
        return t6ReflexiveAuth(w, auth) === true
      }),
      { numRuns: 1000 },
    )
  })

  it('forall workflow with modifies_sutra=true + both auth=false: T6 fails', () => {
    fc.assert(
      fc.property(workflowArb({ modifies_sutra: true }), (w) => {
        const auth: ReflexiveAuth = { founder_authorization: false, meta_charter_approval: false }
        return t6ReflexiveAuth(w, auth) === false
      }),
      { numRuns: 1000 },
    )
  })
})

describe('runAll — aggregate semantics', () => {
  it('happy-path aggregate returns pass=true', () => {
    fc.assert(
      fc.property(
        workflowArb({ modifies_sutra: false }),
        charterArb({
          obligations: fc.array(constraintArb({ forceType: 'obligation' }), {
            minLength: 0,
            maxLength: 1,
          }),
        }),
        (rawW, c) => {
          // Force interfaces_with to empty so T4 trivially passes.
          const w = { ...rawW, interfaces_with: [] }
          const allowed = [...c.obligations.map((o) => o.name), ...c.invariants.map((i) => i.name)]
          const ctx: TerminalCheckContext = {
            workflow: w,
            charter: c,
            postcondition_predicates: [],
            output_validators: w.outputs.map(() => ALWAYS_VALID),
            coverage: {
              // Codex M3 P1 fix: traces_to MUST include the obligation each
              // decision points at. Cover all allowed names per step so the
              // L4 relation-check passes regardless of which step covers
              // which obligation.
              step_coverage: w.step_graph.map((s) =>
                allowed.length > 0
                  ? { step_id: s.step_id, traces_to: [...allowed] }
                  : { step_id: s.step_id, traces_to: [], gap_status: 'accepted' as const },
              ),
              obligation_coverage: c.obligations.map((o) => ({
                obligation_name: o.name,
                covered_by_step: w.step_graph[0]!.step_id,
              })),
            },
            interface_violations: [],
            children: [],
            reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
            self_execution_id: 'E-self',
          }
          const r = l4TerminalCheck.runAll(ctx)
          return r.pass === true && r.failed_at === null && r.failure_reason === null
        },
      ),
      { numRuns: 1000 },
    )
  })

  it('forces T2 failure → result reports failed_at=T2', () => {
    const w = {
      id: 'W-x',
      preconditions: '',
      step_graph: [{ step_id: 0, action: 'wait' as const, inputs: [], outputs: [], on_failure: 'abort' as const }],
      inputs: [],
      outputs: [
        {
          kind: 'k',
          schema_ref: 's',
          locator: 'l',
          version: '',
          mutability: 'immutable' as const,
          retention: '',
        },
      ],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task' as const,
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'escalate' as const,
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual' as const,
    }
    const c = {
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
    }
    const ctx: TerminalCheckContext = {
      workflow: w,
      charter: c,
      postcondition_predicates: [],
      output_validators: [ALWAYS_INVALID],
      coverage: {
        step_coverage: [{ step_id: 0, traces_to: [], gap_status: 'accepted' }],
        obligation_coverage: [],
      },
      interface_violations: [],
      children: [],
      reflexive_auth: { founder_authorization: false, meta_charter_approval: false },
      self_execution_id: 'E-self',
    }
    const r = l4TerminalCheck.runAll(ctx)
    expect(r.pass).toBe(false)
    expect(r.failed_at).toBe('T2')
    expect(r.failure_reason).toBe('terminal_check_failed:T2')
  })
})
