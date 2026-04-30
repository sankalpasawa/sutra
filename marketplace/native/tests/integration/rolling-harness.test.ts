/**
 * M5.5 — Rolling integration harness (T-061).
 *
 * Composes ALL shipped milestone surfaces (M2 primitives + M3 laws +
 * M4 schemas + M5 engine) into ONE cross-cutting integration test suite.
 * The harness asserts the cross-milestone interface contract — i.e.
 * "M2 records flow into M3 predicates flow into M4 evidence flow into
 * M5 execution" — in a single place. As M6, M7, M8 land, the harness
 * extends to compose those too. CI already runs every file under
 * `tests/integration/**` on every push (.github/workflows/native-tests.yml).
 *
 * Goals (per M5.5 plan acceptance criteria A-1..A-7):
 *   - Build a Domain → Charter → Workflow → Execution chain end-to-end (M2).
 *   - Apply L4 terminalCheck (T6) on the Workflow (M3).
 *   - Reference extension_ref (null gate per v1.0 / F-11), decision_provenance,
 *     cutover_contract, agent_identity (M4).
 *   - Drive the engine: registerWorkflow + executeStepGraph + asActivity +
 *     a failure_policy='continue' variant (M5).
 *   - Replay determinism: deep-equal across two independent runs.
 *
 * Boundary note: the harness pins the PUBLIC engine barrel surface
 * (`src/engine/index.ts`) — interface drift in any milestone surfaces here
 * before it can leak into M6+. Wall <3s per A-4.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5.5-rolling-integration.md
 *  - holding/plans/native-v1.0/M5-workflow-engine.md (engine baseline)
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md (P1.1 partial)
 */

import { describe, it, expect } from 'vitest'

// ---- M2 primitives ----------------------------------------------------------
import { createDomain, type Domain } from '../../src/primitives/domain.js'
import { createCharter, type Charter } from '../../src/primitives/charter.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import { createExecution, type Execution } from '../../src/primitives/execution.js'

// ---- M3 laws ----------------------------------------------------------------
import { l4TerminalCheck } from '../../src/laws/l4-terminal-check.js'

// ---- M4 schemas + types -----------------------------------------------------
import {
  createDecisionProvenance,
  type DecisionProvenance,
} from '../../src/schemas/decision-provenance.js'
import {
  createCutoverContract,
  type CutoverContract,
} from '../../src/schemas/cutover-contract.js'
import {
  createAgentIdentity,
  type AgentIdentity,
} from '../../src/types/agent-identity.js'
import { isValidExtensionRef } from '../../src/types/extension.js'

// ---- M5 engine --------------------------------------------------------------
import {
  registerWorkflow,
  executeStepGraph,
  asActivity,
  SkillEngine,
  type ActivityDispatcher,
  type ExecutionResult,
  type StepDispatchResult,
} from '../../src/engine/index.js'

// ---- M7 engine (Charter→Rego compile + bundle + dispatcher) ----------------
import {
  compileCharter,
  OPABundleService,
  makePolicyDispatcher,
} from '../../src/engine/index.js'

import type { Constraint, WorkflowStep } from '../../src/types/index.js'

// =============================================================================
// Fixtures — reusable across sub-tests so the cross-milestone wiring is
// asserted on a single shape (not 5 ad-hoc shapes).
// =============================================================================

/**
 * Build a Domain → Charter → Workflow chain. Pure function: same call ⇒
 * deep-equal output. Used by the replay-determinism sub-test.
 */
function buildPrimitiveChain(): { domain: Domain; charter: Charter; workflow: Workflow } {
  const principle: Constraint = {
    name: 'p1',
    predicate: 'always-true',
    durability: 'durable',
    owner_scope: 'domain',
  }
  const domain = createDomain({
    id: 'D1',
    name: 'rolling-harness-domain',
    parent_id: null,
    principles: [principle],
    intelligence: '',
    accountable: ['CEO'],
    authority: 'rolling-harness',
  })

  const obligation: Constraint = {
    name: 'o1',
    predicate: 'ship-rolling-harness',
    durability: 'durable',
    owner_scope: 'charter',
    type: 'obligation',
  }
  const cutover_contract: CutoverContract = createCutoverContract({
    source_engine: 'core-v0',
    target_engine: 'native-v1.0',
    behavior_invariants: ['terminal_check_passes', 'replay_deterministic'],
    rollback_gate: 'partial_executions_observed',
    canary_window: 'PT1H',
  })
  const charter = createCharter({
    id: 'C-rolling-harness',
    purpose: 'Lock in cross-milestone interface contract.',
    scope_in: 'M2..M5 surfaces composed in one harness',
    scope_out: 'M6+ surfaces',
    obligations: [obligation],
    invariants: [],
    success_metrics: ['harness_passes_on_every_commit'],
    authority: 'derived-from-domain',
    termination: 'M6+ extends harness',
    constraints: [],
    acl: [],
    cutover_contract,
  })

  const observe: WorkflowStep = {
    step_id: 1,
    skill_ref: 'sutra:observe',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  const shape: WorkflowStep = {
    step_id: 2,
    skill_ref: 'sutra:shape',
    inputs: [],
    outputs: [],
    // 'continue' so a failing dispatcher in the failure-policy sub-test
    // advances rather than aborts.
    on_failure: 'continue',
  }
  const terminate: WorkflowStep = {
    step_id: 3,
    action: 'terminate',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  const workflow = createWorkflow({
    id: 'W-rolling-harness',
    preconditions: '',
    step_graph: [observe, shape, terminate],
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
    on_override_action: 'escalate',
    // M4.5: extension_ref MUST be null in v1.0 per D4 §7.3 / F-11.
    extension_ref: null,
    autonomy_level: 'manual',
  })

  return { domain, charter, workflow }
}

/**
 * Pure dispatcher — same (descriptor, ctx) ⇒ same StepDispatchResult.
 * Replay-deterministic per M5 step-graph executor contract.
 */
function buildDeterministicDispatcher(): ActivityDispatcher {
  return (descriptor): StepDispatchResult => ({
    kind: 'ok',
    outputs: [`m55-${descriptor.skill_ref ?? descriptor.action}-${descriptor.step_id}`],
  })
}

// =============================================================================
// Test 1 — M2 chain composes; M3 T6 clears; M4 schema records validate
// =============================================================================

describe('M5.5 rolling harness — primitives + laws + schemas (M2/M3/M4)', () => {
  it('composes Domain → Charter → Workflow → Execution and clears L4 T6', () => {
    const { domain, charter, workflow } = buildPrimitiveChain()

    // M2 — chain shape
    expect(domain.id).toBe('D1')
    expect(charter.id).toBe('C-rolling-harness')
    expect(workflow.id).toBe('W-rolling-harness')
    expect(workflow.step_graph).toHaveLength(3)
    expect(workflow.autonomy_level).toBe('manual')

    // M2 — Execution carries an agent_identity (M4.2)
    const agent_identity: AgentIdentity = createAgentIdentity({
      kind: 'claude-opus',
      id: 'claude-opus:m55-harness',
      version: '4.7',
    })
    const execution: Execution = createExecution({
      id: 'E-m55-1',
      workflow_id: workflow.id,
      trigger_event: 'rolling-harness:start',
      state: 'running',
      logs: [],
      results: [],
      parent_exec_id: null,
      sibling_group: null,
      fingerprint: 'fp-m55-1',
      agent_identity,
    })
    expect(execution.workflow_id).toBe('W-rolling-harness')
    expect(execution.agent_identity?.kind).toBe('claude-opus')

    // M3 — L4 T6 clears: modifies_sutra=false ⇒ vacuously true regardless of auth.
    const t6 = l4TerminalCheck.t6(workflow, {
      founder_authorization: false,
      meta_charter_approval: false,
    })
    expect(t6).toBe(true)

    // M4 — extension_ref null gate (F-11 lives in terminalCheck; the schema
    // accepts both null and ext-* shapes; the harness pins the v1.0 default).
    expect(workflow.extension_ref).toBeNull()
    expect(isValidExtensionRef(null)).toBe(true)
    expect(isValidExtensionRef('ext-m55-future')).toBe(true)

    // M4 — cutover_contract round-trips through Charter.
    expect(charter.cutover_contract).not.toBeNull()
    expect(charter.cutover_contract?.target_engine).toBe('native-v1.0')

    // M4 — DecisionProvenance schema validates a record referring to this
    // Workflow. The OTel emission gateway lands at M8; here we exercise SCHEMA
    // only (M4.3 ships schema; M8 wires emission).
    const dp: DecisionProvenance = createDecisionProvenance({
      id: 'dp-deadbeef',
      actor: 'asawa@nurix.ai',
      agent_identity,
      timestamp: '2026-04-29T00:00:00.000Z',
      evidence: [],
      authority_id: 'A-rolling-harness',
      policy_id: 'M5.5-rolling-integration',
      policy_version: '1.0.0',
      confidence: 0.95,
      decision_kind: 'EXECUTE',
      scope: 'WORKFLOW',
      outcome: 'M5.5 harness composed M2-M5 surfaces',
      next_action_ref: workflow.id,
    })
    expect(dp.next_action_ref).toBe(workflow.id)
    expect(dp.policy_version).toBe('1.0.0')
  })
})

// =============================================================================
// Test 2 — M5 engine: registerWorkflow + executeStepGraph + asActivity
// =============================================================================

describe('M5.5 rolling harness — engine surfaces (M5)', () => {
  it('registerWorkflow produces a TemporalWorkflowDefinition; executeStepGraph runs end-to-end', async () => {
    const { workflow } = buildPrimitiveChain()
    const def = registerWorkflow(workflow)

    expect(def.workflow_id).toBe('W-rolling-harness')
    expect(def.task_queue).toBe('sutra-rolling-harness')
    expect(def.activities.map((a) => a.step_id)).toEqual([1, 2, 3])
    expect(def.activities[2]!.action).toBe('terminate')

    // executeStepGraph drives the same workflow through a deterministic
    // dispatcher. step 3 is structural (terminate) — visited but not dispatched.
    const result: ExecutionResult = await executeStepGraph(
      workflow,
      buildDeterministicDispatcher(),
    )
    expect(result.workflow_id).toBe('W-rolling-harness')
    expect(result.state).toBe('success')
    expect(result.partial).toBe(false)
    expect(result.failure_reason).toBeNull()
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    expect(result.completed_step_ids).toEqual([1, 2])
    expect(result.step_outputs.map((s) => s.step_id)).toEqual([1, 2])
    expect(result.step_outputs[0]!.outputs).toEqual(['m55-sutra:observe-1'])
  })

  it('asActivity wraps a Promise-returning impl; dispatcher invokes it once per step', async () => {
    const { workflow } = buildPrimitiveChain()

    // Track invocations to prove the wrapped Activity actually runs (not just
    // a no-op echo dispatcher).
    const calls: Array<{ step_id: number; arg: string }> = []
    const impl = asActivity(async (step_id: number, arg: string): Promise<string> => {
      calls.push({ step_id, arg })
      return `wrapped:${step_id}:${arg}`
    })

    const dispatch: ActivityDispatcher = async (descriptor) => {
      const out = await impl(descriptor.step_id, descriptor.skill_ref ?? 'no-skill')
      return { kind: 'ok', outputs: [out] }
    }

    const result = await executeStepGraph(workflow, dispatch)

    // step 3 is `terminate` — structural, no dispatch. Steps 1 + 2 dispatch.
    expect(calls).toEqual([
      { step_id: 1, arg: 'sutra:observe' },
      { step_id: 2, arg: 'sutra:shape' },
    ])
    expect(result.state).toBe('success')
    expect(result.step_outputs[0]!.outputs).toEqual(['wrapped:1:sutra:observe'])
    expect(result.step_outputs[1]!.outputs).toEqual(['wrapped:2:sutra:shape'])
  })

  it('failure_policy=continue advances past a failing step; partial=true; completed excludes failed step', async () => {
    const { workflow } = buildPrimitiveChain()

    // step 2 has on_failure='continue'. Make it throw — executor must
    // (a) advance to step 3 (terminate, structural),
    // (b) set partial=true,
    // (c) keep state='success' (continue is non-fatal),
    // (d) include step 2 in visited but NOT in completed (codex P1.1).
    const dispatch: ActivityDispatcher = (descriptor) => {
      if (descriptor.step_id === 2) {
        return { kind: 'failure', error: new Error('m55-step-2-failed') }
      }
      return {
        kind: 'ok',
        outputs: [`m55-${descriptor.skill_ref ?? descriptor.action}-${descriptor.step_id}`],
      }
    }

    const result = await executeStepGraph(workflow, dispatch)

    expect(result.state).toBe('success')
    expect(result.partial).toBe(true)
    expect(result.failure_reason).toBeNull()
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    // codex P1.1: step 2 failed-continue → visited yes, completed NO.
    expect(result.completed_step_ids).toEqual([1])
    // The failed step's output entry exists with output_validation_skipped=true.
    const s2 = result.step_outputs.find((s) => s.step_id === 2)
    expect(s2).toBeDefined()
    expect(s2!.output_validation_skipped).toBe(true)
    expect(s2!.outputs).toEqual([])
  })
})

// =============================================================================
// Test 3 — M6 SkillEngine: register + invoke + isolated child trace
// =============================================================================

describe('M5.5 rolling harness — M6 SkillEngine surfaces', () => {
  it('register echo Skill + invoke from a parent step + child_edge surfaces with deterministic id', async () => {
    // M6 cross-milestone composition: SkillEngine registers a leaf Skill
    // ('echo'); a parent Workflow with a single step.skill_ref dispatches
    // through invokeSkill; the harness asserts state=success + child_edge
    // shape + parent isolation. This locks M2..M6 surfaces under the same
    // harness umbrella so M7+ can extend without re-deriving the contract.
    const echo = createWorkflow({
      id: 'W-echo',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      reuse_tag: true,
      // Permissive schema (literal-true) — accepts any payload from the
      // dispatcher. The contract test in skill-engine.test.ts T-074 covers
      // schema-conformance assertions; this harness pins the COMPOSE.
      return_contract: JSON.stringify(true),
    })

    const engine = new SkillEngine()
    engine.register(echo)

    // Parent: 1 step with skill_ref='W-echo'.
    const parent = createWorkflow({
      id: 'W-harness-m6-parent',
      preconditions: '',
      step_graph: [
        { step_id: 7, skill_ref: 'W-echo', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    // Dispatcher returns the leaf Skill's terminal payload. Validated against
    // the literal-true return_contract (always passes).
    const dispatch: ActivityDispatcher = (descriptor) => ({
      kind: 'ok',
      outputs: [`echo:${descriptor.step_id}`],
    })

    const result: ExecutionResult = await executeStepGraph(parent, dispatch, {
      skill_engine: engine,
    })

    expect(result.state).toBe('success')
    expect(result.partial).toBe(false)
    expect(result.failure_reason).toBeNull()
    // Parent's lists carry ONLY parent step_id (7) — child internals isolated.
    expect(result.completed_step_ids).toEqual([7])
    expect(result.visited_step_ids).toEqual([7])
    // child_edges has exactly ONE entry — the echo invocation. Codex master
    // 2026-04-30 P1.1 fold: validated_dataref carries the V2 §A11 DataRef
    // envelope; parent step 7's outputs[0] is the same envelope.
    expect(result.child_edges).toBeDefined()
    expect(result.child_edges).toHaveLength(1)
    expect(result.child_edges![0]!.step_id).toBe(7)
    expect(result.child_edges![0]!.skill_ref).toBe('W-echo')
    // Deterministic child_execution_id (replay-stable, no clock).
    expect(result.child_edges![0]!.child_execution_id).toBe('child-7-W-echo')
    // The DataRef envelope wraps the leaf step's dispatcher output ('echo:1').
    const expectedDataRef = {
      kind: 'skill-output',
      schema_ref: JSON.stringify(true),
      locator: `inline:${JSON.stringify('echo:1')}`,
      version: '1',
      mutability: 'immutable',
      retention: 'session',
      authoritative_status: 'authoritative',
    }
    expect(result.child_edges![0]!.validated_dataref).toEqual(expectedDataRef)
    // Parent step 7's outputs[0] is the validated DataRef envelope.
    expect(result.step_outputs[0]?.outputs).toEqual([expectedDataRef])
  })
})

// =============================================================================
// Test 4 — Replay determinism across the full compose
// =============================================================================

describe('M5.5 rolling harness — replay determinism', () => {
  it('two independent runs yield deep-equal ExecutionResult', async () => {
    // Both runs build the chain from scratch — proves the COMPOSE itself is
    // pure (no module-scope mutable state leaking across runs).
    const { workflow: w1 } = buildPrimitiveChain()
    const { workflow: w2 } = buildPrimitiveChain()

    const r1 = await executeStepGraph(w1, buildDeterministicDispatcher())
    const r2 = await executeStepGraph(w2, buildDeterministicDispatcher())

    // Bit-identical end-to-end. This is the cross-milestone replay contract:
    // any non-determinism introduced in M2/M3/M4/M5 surfaces here as an
    // inequality before it leaks into M6+.
    expect(r2).toEqual(r1)
  })
})

// =============================================================================
// Test 5 — M7 surface (T-099): Charter compile → bundle register → policy
// allow path runs end-to-end through the executor's policy gate
// =============================================================================

describe('M5.5 rolling harness — M7 policy surfaces (Charter compile + bundle + evaluate)', () => {
  it('compileCharter + OPABundleService.register + executor policy gate allow path', async () => {
    // Charter with a single permissive predicate (Rego literal `1 == 1` —
    // always holds). The compiler emits `allow if { 1 == 1 }` + default deny;
    // the OPA evaluator returns kind:'allow' on every input.
    const charter = createCharter({
      id: 'C-m55-m7',
      purpose: 'Rolling-harness M7 policy gate allow path.',
      scope_in: '',
      scope_out: '',
      obligations: [],
      invariants: [],
      success_metrics: ['policy_gate_allow_path_passes'],
      authority: 'M5.5-harness',
      termination: '',
      constraints: [
        {
          name: 'always_allow',
          predicate: '1 == 1',
          durability: 'episodic',
          owner_scope: 'charter',
        },
      ],
      acl: [],
    })

    // Compile + register. Bundle service round-trips the policy by id.
    const policy = compileCharter(charter)
    const bundle = new OPABundleService()
    bundle.register(policy)
    expect(bundle.get(policy.policy_id)).toBe(policy)
    // policy_version is a 64-hex sha256 — pin format so cross-milestone
    // changes that broke determinism would surface here.
    expect(policy.policy_version).toMatch(/^[a-f0-9]{64}$/)

    // Workflow: 1 step with policy_check=true + action='wait'. The executor
    // evaluates the policy via the dispatcher (real OPA), gets allow, then
    // dispatches the step normally.
    const w = createWorkflow({
      id: 'W-m55-m7',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
          policy_check: true,
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    // P2.1 fold: makePolicyDispatcher takes the bundle service.
    const dispatcher = makePolicyDispatcher(bundle)
    const dispatch: ActivityDispatcher = (descriptor): StepDispatchResult => ({
      kind: 'ok',
      outputs: [`m55-m7-step-${descriptor.step_id}`],
    })

    const result: ExecutionResult = await executeStepGraph(w, dispatch, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    // M7 surface composes cleanly with M5 executor: allow ⇒ step runs ⇒
    // success ⇒ failure_reason=null ⇒ partial=false. Step 1 visited+completed.
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.partial).toBe(false)
    expect(result.completed_step_ids).toEqual([1])
    expect(result.step_outputs[0]?.outputs).toEqual(['m55-m7-step-1'])
  })
})
