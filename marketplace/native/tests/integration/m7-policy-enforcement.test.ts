/**
 * M7 policy enforcement — integration scenarios (M7 Group W T-098).
 *
 * 7 cross-component scenarios per A-7 acceptance criteria. Each builds a
 * Charter → compileCharter → OPABundleService.register → executor wired with
 * makePolicyDispatcher (real OPA path) → assert end-to-end behavior.
 *
 *   A-7.a — allow path
 *   A-7.b — deny + abort
 *   A-7.c — deny + continue (partial advances)
 *   A-7.d — deny + rollback compensates only prior SUCCESS (not denied step)
 *   A-7.e — tenant isolation via execution_context.tenant_id
 *   A-7.f — builtin denylist enforced at COMPILE time (not eval time)
 *   A-7.g — failure_reason carries policy_version (sha256 hash) for audit
 *
 * Determinism contract: every scenario uses fixed Charter + fixed Workflow +
 * fixed PolicyInput shape — same run, same result. No clocks, no randomness.
 *
 * Test-fixture invariants:
 *  - OPA 1.15.2 binary on $PATH (verified at Group V; CI installs via brew).
 *  - WorkflowStep.policy_check on the gated step (per V2 §A11 + M7 P1.1 fold).
 *  - on_failure routes deny via the SAME path as a step failure
 *    (canonical errMsg = `policy_deny:<rule>:<reason>:<policy_version>`).
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M7-opa-compiler.md Group W T-098 (A-7)
 */

import { describe, it, expect } from 'vitest'

import { createCharter, type Charter } from '../../src/primitives/charter.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import {
  compileCharter,
  BuiltinNotAllowedError,
  type CompiledPolicy,
} from '../../src/engine/charter-rego-compiler.js'
import { OPABundleService } from '../../src/engine/opa-bundle-service.js'
import { makePolicyDispatcher } from '../../src/engine/policy-dispatcher.js'
import {
  executeStepGraph,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../src/engine/step-graph-executor.js'

// =============================================================================
// Fixtures — reusable across scenarios
// =============================================================================

/**
 * Build a Charter from a single allow predicate. The predicate is taken AS-IS
 * — Group U embeds it in `allow if { <predicate> }`. Predicates that succeed
 * for the test input ⇒ allow; predicates that fail ⇒ default-deny.
 */
function charterAllowing(predicate: string, id = 'C-m7-allow'): Charter {
  return createCharter({
    id,
    purpose: 'M7 Group W integration test charter',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: 'M7-test',
    termination: 'test-end',
    constraints: [
      {
        name: 'allow_when',
        predicate,
        durability: 'episodic',
        owner_scope: 'charter',
      },
    ],
    acl: [],
  })
}

/**
 * Build a Workflow with N steps; step at `policyStepIndex` (0-based) carries
 * `policy_check=true`. All steps use action='wait' (a real, non-skill_ref
 * step that the dispatcher fulfills directly).
 */
function workflowWithPolicyCheck(opts: {
  id?: string
  steps: number
  policyStepIndex: number
  on_failure: 'abort' | 'rollback' | 'continue' | 'escalate' | 'pause'
}): Workflow {
  const id = opts.id ?? 'W-m7-policy'
  return createWorkflow({
    id,
    preconditions: '',
    step_graph: Array.from({ length: opts.steps }, (_, i) => ({
      step_id: i + 1,
      action: 'wait',
      inputs: [],
      outputs: [],
      on_failure: i === opts.policyStepIndex ? opts.on_failure : 'abort',
      ...(i === opts.policyStepIndex ? { policy_check: true } : {}),
    })),
    inputs: [],
    outputs: [],
    state: [],
    postconditions: '',
    failure_policy: 'abort',
    stringency: 'task',
    interfaces_with: [],
  })
}

/** Always-OK dispatcher — emits a deterministic per-step outputs payload. */
const okDispatcher: ActivityDispatcher = (descriptor): StepDispatchResult => ({
  kind: 'ok',
  outputs: [`m7-step-${descriptor.step_id}`],
})

/**
 * Wire a compiled Charter into the bundle service and produce a dispatcher
 * pointed at the real OPA binary. Returns the dispatcher + compiled policy
 * for direct attachment to executeStepGraph options.
 *
 * Codex master review 2026-04-30 P2.1 fold (CHANGE): the dispatcher now
 * fetches CompiledPolicy via OPABundleService.get(policy_id, policy_version)
 * at runtime — bundle is the live source of truth. `makePolicyDispatcher`
 * takes the bundle as its only argument; tests register the policy with
 * the bundle BEFORE invoking executeStepGraph (the executor still receives
 * compiled_policy in options to surface policy_id/version on the dispatch
 * command, but the dispatcher does the actual lookup).
 */
function wirePolicy(
  charter: Charter,
): { policy: CompiledPolicy; dispatcher: ReturnType<typeof makePolicyDispatcher> } {
  const policy = compileCharter(charter)
  const bundle = new OPABundleService()
  bundle.register(policy)
  const dispatcher = makePolicyDispatcher(bundle)
  return { policy, dispatcher }
}

// =============================================================================
// A-7.a — allow path
// =============================================================================

describe('M7 A-7.a — allow path', () => {
  it('charter allows step → executor proceeds → state="success", failure_reason=null', async () => {
    // Predicate that ALWAYS holds — Rego literal `1 == 1`. The Workflow's step
    // 1 has policy_check=true; the executor evaluates the policy first, gets
    // 'allow', then dispatches the step normally.
    const charter = charterAllowing('1 == 1', 'C-m7a')
    const { policy, dispatcher } = wirePolicy(charter)
    const w = workflowWithPolicyCheck({
      id: 'W-m7a',
      steps: 2,
      policyStepIndex: 0,
      on_failure: 'abort',
    })

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.completed_step_ids).toEqual([1, 2])
    expect(result.partial).toBe(false)
  })
})

// =============================================================================
// A-7.b — deny + abort
// =============================================================================

describe('M7 A-7.b — deny + abort', () => {
  it('charter denies step → on_failure=abort → state="failed", failure_reason=/policy_deny:/', async () => {
    // Predicate that NEVER holds — `false` literally. Charter compiles to a
    // single `allow if { false }` rule + the `default allow := false` →
    // every input default-denies. Default-deny evaluates as
    // rule_name=default_allow_false, reason=default_deny.
    const charter = charterAllowing('false', 'C-m7b')
    const { policy, dispatcher } = wirePolicy(charter)
    const w = workflowWithPolicyCheck({
      id: 'W-m7b',
      steps: 2,
      policyStepIndex: 0,
      on_failure: 'abort',
    })

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toMatch(/^step:\d+:abort:policy_deny:/)
    // The denied step is visited but never completed (codex P1.1 contract).
    expect(result.visited_step_ids).toEqual([1])
    expect(result.completed_step_ids).toEqual([])
  })
})

// =============================================================================
// A-7.c — deny + continue
// =============================================================================

describe('M7 A-7.c — deny + continue (partial=true, advances)', () => {
  it('charter denies step1 (continue) → step1 fails → step2 runs → state="success", partial=true', async () => {
    // 2-step Workflow. Step 1 has policy_check=true + on_failure=continue;
    // policy denies → step 1 logged, executor advances to step 2 (no
    // policy_check) → step 2 runs to completion. Final state stays 'success'
    // but partial=true; step 1's output entry has output_validation_skipped=true.
    const charter = charterAllowing('false', 'C-m7c')
    const { policy, dispatcher } = wirePolicy(charter)
    const w = workflowWithPolicyCheck({
      id: 'W-m7c',
      steps: 2,
      policyStepIndex: 0,
      on_failure: 'continue',
    })

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    expect(result.state).toBe('success')
    expect(result.partial).toBe(true)
    // Step 1 visited (failed-continue), step 2 visited+completed.
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.completed_step_ids).toEqual([2])
    // Step 1's output entry exists with output_validation_skipped=true.
    const s1 = result.step_outputs.find((s) => s.step_id === 1)
    expect(s1).toBeDefined()
    expect(s1!.output_validation_skipped).toBe(true)
    expect(s1!.outputs).toEqual([])
  })
})

// =============================================================================
// A-7.d — deny + rollback after prior success (codex P1.1 carry-forward)
// =============================================================================

describe('M7 A-7.d — deny + rollback compensates only prior SUCCESS (not denied step)', () => {
  it('step1 success, step2 denied + on_failure=rollback → compensation_order=[1] (NOT [1,2])', async () => {
    // Two-step Workflow. Step 1 has NO policy_check — runs normally → success.
    // Step 2 has policy_check=true + on_failure=rollback. Policy denies →
    // executor synthesizes a step failure → failure-policy walks rollback.
    // Per codex P1.1 (M5 ship-blocker fix): rollback compensates only the
    // SUCCESS-only completed list, NOT the visited list. Step 2 (denied)
    // never produced effects → MUST NOT appear in compensation_order.
    const charter = charterAllowing('false', 'C-m7d')
    const { policy, dispatcher } = wirePolicy(charter)
    const w = createWorkflow({
      id: 'W-m7d',
      preconditions: '',
      step_graph: [
        { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
        {
          step_id: 2,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'rollback',
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

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    expect(result.state).toBe('failed')
    // PIN — compensation_order has step 1 only. NOT [1, 2]. NOT [2, 1].
    // This pins codex P1.1 across the policy-deny path.
    expect(result.rollback_compensations).toEqual([1])
    expect(result.failure_reason).toMatch(/policy_deny:/)
    // Step 2 visited (failed) but NOT completed.
    expect(result.visited_step_ids).toEqual([1, 2])
    expect(result.completed_step_ids).toEqual([1])
  })
})

// =============================================================================
// A-7.e — tenant isolation
// =============================================================================

describe('M7 A-7.e — tenant isolation via execution_context.tenant_id', () => {
  it('charter requires execution_context.tenant_id == workflow.custody_owner → denies cross-tenant', async () => {
    // Codex master review 2026-04-30 P2.3 fold (CHANGE): A-7.e now exercises
    // the REAL tenant-isolation surface — `input.execution_context.tenant_id`
    // — rather than the prior surrogate (`input.workflow.custody_owner`).
    // The executor's PolicyInput now carries tenant_id when supplied via
    // ExecuteOptions.tenant_id; the Charter encodes the cross-tenant
    // isolation rule.
    //
    // Charter rule (allow predicate): tenant binding holds when
    // execution_context.tenant_id matches the workflow's declared
    // custody_owner. The negative scenario sets a DIFFERENT tenant_id
    // (T-tenant-b) on the execution_context than the workflow's
    // custody_owner (T-tenant-a) → cross-tenant access attempt → deny.
    const charter = charterAllowing(
      'input.execution_context.tenant_id == input.workflow.custody_owner',
      'C-m7e',
    )
    const { policy, dispatcher } = wirePolicy(charter)

    // Workflow custody_owner='T-tenant-a'. Execution context tenant_id will
    // be 'T-tenant-b' (set via ExecuteOptions below) — does NOT match ⇒ deny.
    const w = createWorkflow({
      id: 'W-m7e',
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
      custody_owner: 'T-tenant-a',
    })

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
      tenant_id: 'T-tenant-b',
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toMatch(/policy_deny:/)
  })
})

// =============================================================================
// A-7.f — builtin denylist (compile-time)
// =============================================================================

describe('M7 A-7.f — builtin denylist enforced at COMPILE time', () => {
  it('charter with predicate using forbidden builtin (http.send) → compileCharter throws BuiltinNotAllowedError', () => {
    // The charter predicate references `http.send` — a forbidden builtin
    // (sovereignty discipline; non-deterministic + external). Group U's
    // checkBuiltinAllowlist scans the generated Rego and rejects at COMPILE
    // time, NOT eval time. This pin matters: a policy that's already deployed
    // can't suddenly become non-deterministic; rejection happens before
    // anything is registered with OPABundleService.
    const charter = charterAllowing(
      'http.send({"url": "https://example.com"})',
      'C-m7f',
    )

    expect(() => compileCharter(charter)).toThrow(BuiltinNotAllowedError)
  })

  it('error carries the offending builtin name + charter id for downstream logging', () => {
    const charter = charterAllowing(
      'time.now_ns() > 0',
      'C-m7f-time',
    )
    let captured: BuiltinNotAllowedError | null = null
    try {
      compileCharter(charter)
    } catch (e) {
      if (e instanceof BuiltinNotAllowedError) captured = e
    }
    expect(captured).not.toBeNull()
    expect(captured!.builtin_name).toBe('time')
    expect(captured!.charter_id).toBe('C-m7f-time')
  })
})

// =============================================================================
// A-7.g — failure_reason carries policy_version for audit
// =============================================================================

describe('M7 A-7.g — failure_reason carries policy_version (sha256) for audit', () => {
  it('deny path failure_reason matches /^step:\\d+:abort:policy_deny:[^:]+:[^:]+:[a-f0-9]{64}$/', async () => {
    // Same shape as A-7.b but the assertion locks the FULL canonical
    // failure_reason format including the trailing 64-hex policy_version.
    // This is the audit-trail pin: every deny carries the sha256 hash of
    // the Rego source + compiler version so downstream telemetry can
    // reconstruct exactly which policy revision rejected the call.
    const charter = charterAllowing('false', 'C-m7g')
    const { policy, dispatcher } = wirePolicy(charter)
    const w = workflowWithPolicyCheck({
      id: 'W-m7g',
      steps: 1,
      policyStepIndex: 0,
      on_failure: 'abort',
    })

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).not.toBeNull()
    // Anchored regex: the full prefix `step:N:abort:policy_deny:` followed by
    // <rule_name>:<reason>:<policy_version> where policy_version is 64-hex.
    // rule_name + reason are non-colon tokens (Group V's evaluator normalizes
    // both to ':'-free strings). Test pins the audit shape end-to-end.
    expect(result.failure_reason).toMatch(
      /^step:\d+:abort:policy_deny:[^:]+:[^:]+:[a-f0-9]{64}$/,
    )
    // Sanity: the 64-hex tail equals the compiled policy's policy_version.
    const tail = result.failure_reason!.split(':').pop()
    expect(tail).toBe(policy.policy_version)
  })
})
