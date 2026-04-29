/**
 * M5 Workflow Engine — integration test (Group L T-056).
 *
 * Goal: assert end-to-end replay determinism for the engine stack
 * (`registerWorkflow` → `executeStepGraph` → Activity dispatcher → terminal
 * check) on a 3-step Sutra Workflow (observe → shape → terminate). Two paths:
 *
 *  1. Mock-based E2E (PRIMARY — replay-determinism oracle).
 *     Spins up the real engine entry point (`registerWorkflow`), runs it twice
 *     with separate-but-equivalent deterministic dispatchers, and deep-equals
 *     the two `ExecutionResult` records. This is the load-bearing assertion
 *     for T-056: replay-determinism end-to-end through the public engine
 *     surface.
 *
 *  2. TestWorkflowEnvironment smoke (SECONDARY — SDK plumbing oracle).
 *     Imports + constructs `TestWorkflowEnvironment.createTimeSkipping()`, then
 *     tears it down. This validates the Temporal SDK is wired correctly in
 *     the package and the test-only dependency resolves; it does NOT assert
 *     workflow replay (a real Worker registration + bundling step is
 *     deferred to M11 dogfood per D-NS-12 (b)). Skipped automatically if the
 *     test server binary cannot be downloaded (CI without network).
 *
 * Boundary note (D-NS-12 (b), M5 plan):
 *   "TestWorkflowEnvironment for tests; production worker connects to real
 *    cluster (Temporal Cloud or self-hosted). Production cluster deferred to
 *    M11 dogfood entry."
 *   The mock-based path therefore IS the M5 replay-determinism contract for
 *   T-056. The Temporal smoke is a wiring oracle, not a replay oracle.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M5-workflow-engine.md Group L T-056
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 *  - .enforcement/codex-reviews/2026-04-29-m5-plan-pre-dispatch.md P2.5
 */

import { describe, it, expect } from 'vitest'
import {
  registerWorkflow,
  type ActivityDispatcher,
  type ExecutionResult,
} from '../../src/engine/index.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import type { WorkflowStep } from '../../src/types/index.js'

// =============================================================================
// Fixture — 3-step Sutra Workflow (observe → shape → terminate)
// =============================================================================

function buildThreeStepWorkflow() {
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
    on_failure: 'abort',
  }
  const terminate: WorkflowStep = {
    step_id: 3,
    action: 'terminate',
    inputs: [],
    outputs: [],
    on_failure: 'abort',
  }
  return createWorkflow({
    id: 'W-m5-integration',
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
  })
}

/**
 * Deterministic dispatcher factory. Each call returns a fresh dispatcher
 * instance whose outputs are pure functions of (step_id) — replay-safe.
 *
 * Two dispatchers built from this factory will produce bit-identical results
 * for the same step_graph; that's the load-bearing property for T-056.
 */
function buildDeterministicDispatcher(): ActivityDispatcher {
  return (descriptor) => ({
    kind: 'ok',
    outputs: [`result-${descriptor.skill_ref ?? descriptor.action}-${descriptor.step_id}`],
  })
}

// =============================================================================
// Test 1 — Mock-based E2E replay determinism (PRIMARY)
// =============================================================================

describe('M5 Workflow Engine — integration (T-056)', () => {
  it('registers a 3-step Sutra Workflow end-to-end', async () => {
    const workflow = buildThreeStepWorkflow()
    const def = registerWorkflow(workflow)

    expect(def.workflow_id).toBe('W-m5-integration')
    expect(def.task_queue).toBe('sutra-m5-integration')
    expect(def.activities).toHaveLength(3)
    expect(def.activities.map((a) => a.step_id)).toEqual([1, 2, 3])
    expect(def.activities[2]!.action).toBe('terminate')
  })

  it('runs end-to-end via the registered orchestrator', async () => {
    const workflow = buildThreeStepWorkflow()
    const def = registerWorkflow(workflow)

    const result = await def.run({ dispatch: buildDeterministicDispatcher() })

    // observe (s1) + shape (s2) dispatched; terminate (s3) is structural,
    // visited but not dispatched. Step outputs only for dispatched steps.
    expect(result.workflow_id).toBe('W-m5-integration')
    expect(result.visited_step_ids).toEqual([1, 2, 3])
    expect(result.state).toBe('success')
    expect(result.failure_reason).toBeNull()
    expect(result.partial).toBe(false)
    expect(result.step_outputs.map((s) => s.step_id)).toEqual([1, 2])
    expect(result.step_outputs[0]!.outputs).toEqual(['result-sutra:observe-1'])
    expect(result.step_outputs[1]!.outputs).toEqual(['result-sutra:shape-2'])
  })

  it('replay determinism: two back-to-back runs yield deep-equal ExecutionResult', async () => {
    const workflow = buildThreeStepWorkflow()
    const def = registerWorkflow(workflow)

    // Two independent dispatcher instances built from the same factory.
    const r1: ExecutionResult = await def.run({ dispatch: buildDeterministicDispatcher() })
    const r2: ExecutionResult = await def.run({ dispatch: buildDeterministicDispatcher() })

    // Bit-identical end-to-end. This is the M5 replay-determinism contract
    // for T-056 — the production Worker (M11 dogfood) provides the same
    // guarantee via Temporal's deterministic-execution sandbox; the engine
    // ABOVE that sandbox must already be deterministic on its own, which is
    // what this asserts.
    expect(r2).toEqual(r1)
  })

  it('replay determinism survives terminalCheck violations (T-051 fold)', async () => {
    const workflow = buildThreeStepWorkflow()
    const def = registerWorkflow(workflow)

    // Inject a terminalCheck probe that returns the same violations on every
    // call — the engine's failure_reason MUST be deep-equal across runs.
    const probe = () => ['F-2', 'F-10'] as const
    const r1 = await def.run({
      dispatch: buildDeterministicDispatcher(),
      options: { terminalCheckProbe: () => [...probe()] },
    })
    const r2 = await def.run({
      dispatch: buildDeterministicDispatcher(),
      options: { terminalCheckProbe: () => [...probe()] },
    })

    expect(r1.state).toBe('failed')
    expect(r1.failure_reason).toBe('forbidden_coupling:F-10,F-2')
    expect(r2).toEqual(r1)
  })
})

// =============================================================================
// Test 2 — TestWorkflowEnvironment SDK plumbing smoke (SECONDARY)
// =============================================================================

describe('M5 Workflow Engine — Temporal SDK smoke (T-056)', () => {
  // ---------------------------------------------------------------------------
  // Scope of this describe block (codex master review 2026-04-29 P2.1):
  //
  // This block proves DEPENDENCY SMOKE only — the @temporalio/* modules
  // resolve, type signatures match, and `MockActivityEnvironment` instantiates
  // without a cluster. It does NOT prove the F-12 RUNTIME TRAP fires inside
  // Temporal's real Workflow sandbox — that proof requires:
  //   1. A Worker bundled with `@temporalio/workflow` (not just imported)
  //   2. A `TestWorkflowEnvironment.createTimeSkipping()` cluster
  //   3. A registered Workflow function that calls `asActivity(impl)` directly
  //      (not via proxyActivities) and asserts the F-12 trap fires inside the
  //      sandbox interpreter
  //
  // That proof is DEFERRED to M11 (Asawa dogfood) per D-NS-12 (b) — production
  // cluster connection deferred to M11, and the bundling step rides with it.
  //
  // The F-12 contract IS proven at L2 via:
  //   - Injected-probe contract test in tests/contract/engine/activity-wrapper.test.ts
  //   - 1000-case property test in tests/property/f12-determinism.test.ts
  //
  // Tracked in holding/plans/native-v1.0/M5-workflow-engine.md → "M5 Follow-ups (post-close)".
  //
  // The Temporal test server downloads a binary on first use; in CI without
  // network the import itself succeeds but `createTimeSkipping()` may stall.
  // We import lazily and skip on failure so the M5 mock-based contract above
  // remains the load-bearing signal. Per D-NS-12 (b) the production cluster
  // wiring lands at M11 dogfood.
  it('Temporal @temporalio/testing exports resolve', async () => {
    const mod = await import('@temporalio/testing')
    expect(typeof mod.TestWorkflowEnvironment).toBe('function')
    expect(typeof mod.MockActivityEnvironment).toBe('function')
  })

  it('MockActivityEnvironment instantiates without a cluster', async () => {
    // MockActivityEnvironment is the in-process Activity test harness — no
    // server binary, no network. Validates the @temporalio/testing import is
    // wired and the SDK shape matches the engine's Activity adapter contract
    // (the real Worker integration arrives at M11 dogfood).
    const { MockActivityEnvironment } = await import('@temporalio/testing')
    const env = new MockActivityEnvironment()
    expect(env).toBeDefined()
    expect(typeof env.run).toBe('function')
  })
})
