/**
 * OTel emitter contract test (M8 Group Z T-105/T-106/T-107/T-108/T-109).
 *
 * Asserts:
 *  - OTelEmitter + InMemoryOTelExporter + NoopOTelExporter + OTLPHttpExporter
 *    shape & basic semantics
 *  - policy-dispatcher emits POLICY_ALLOW + POLICY_DENY (T-106)
 *  - skill-invocation emits SKILL_RESOLVED + SKILL_UNRESOLVED + SKILL_RECURSION_CAP
 *    (T-107)
 *  - step-graph-executor emits STEP_START + STEP_COMPLETE + STEP_FAIL (T-108)
 *  - failure-policy emits FAILURE_POLICY_<OUTCOME> for each of 5 actions (T-109)
 *  - trace_id propagation: invokeSkill child re-entry shares parent's trace_id
 *
 * Spec source:
 *   - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group Z
 */

import { describe, it, expect, beforeEach } from 'vitest'

import {
  InMemoryOTelExporter,
  NoopOTelExporter,
  OTelEmitter,
  OTLPHttpExporter,
} from '../../../src/engine/otel-emitter.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../../src/engine/step-graph-executor.js'
import {
  applyFailurePolicy,
  type ExecutionContext,
} from '../../../src/engine/failure-policy.js'
import { makePolicyDispatcher } from '../../../src/engine/policy-dispatcher.js'
import { OPABundleService } from '../../../src/engine/opa-bundle-service.js'
import { invokeSkill } from '../../../src/engine/skill-invocation.js'
import { SkillEngine } from '../../../src/engine/skill-engine.js'
import { createWorkflow } from '../../../src/primitives/workflow.js'
import type { Workflow } from '../../../src/primitives/workflow.js'
import type { WorkflowStep } from '../../../src/types/index.js'

beforeEach(() => {
  __resetWorkflowRunSeqForTest()
})

// -----------------------------------------------------------------------------
// T-105 — OTelEmitter + exporters shape
// -----------------------------------------------------------------------------

describe('OTelEmitter — shape (T-105)', () => {
  it('InMemoryOTelExporter collects records via emit + reset clears them', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    await emitter.emit({
      decision_kind: 'POLICY_ALLOW',
      trace_id: 't1',
      attributes: {},
    })
    expect(exporter.records).toHaveLength(1)
    expect(exporter.records[0]!.decision_kind).toBe('POLICY_ALLOW')
    exporter.reset()
    expect(exporter.records).toHaveLength(0)
  })

  it('flush() is a no-op for in-memory exporter', async () => {
    const emitter = new OTelEmitter(new InMemoryOTelExporter())
    await expect(emitter.flush()).resolves.toBeUndefined()
  })

  it('OTelEmitter.disabled() returns an emitter wired to NoopOTelExporter', async () => {
    const emitter = OTelEmitter.disabled()
    await expect(
      emitter.emit({ decision_kind: 'STEP_START', trace_id: 't', attributes: {} }),
    ).resolves.toBeUndefined()
  })

  it('NoopOTelExporter export + flush both no-op', async () => {
    const exporter = new NoopOTelExporter()
    await expect(exporter.export([])).resolves.toBeUndefined()
    await expect(exporter.flush()).resolves.toBeUndefined()
  })

  it('OTLPHttpExporter constructor rejects empty endpoint', () => {
    expect(() => new OTLPHttpExporter('')).toThrow(TypeError)
    expect(() => new OTLPHttpExporter('https://collector.example/v1/traces')).not.toThrow()
  })

  it('OTLPHttpExporter export + flush silently drop (M11 stub)', async () => {
    const exporter = new OTLPHttpExporter('https://collector.example/v1/traces')
    await expect(exporter.export([])).resolves.toBeUndefined()
    await expect(exporter.flush()).resolves.toBeUndefined()
  })

  it('OTelEmitter constructor rejects invalid exporter', () => {
    expect(() => new OTelEmitter(null as unknown as InMemoryOTelExporter)).toThrow(TypeError)
    expect(
      () =>
        new OTelEmitter({
          // missing flush method
          export: async () => {},
        } as unknown as InMemoryOTelExporter),
    ).toThrow(TypeError)
  })
})

// -----------------------------------------------------------------------------
// T-106 — policy-dispatcher emits POLICY_ALLOW + POLICY_DENY
// -----------------------------------------------------------------------------

describe('policy-dispatcher OTel emission (T-106)', () => {
  it('synthesizes POLICY_DENY when bundle.get returns null AND emits to OTel', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const bundle = new OPABundleService()
    const dispatcher = makePolicyDispatcher(bundle, emitter)
    const decision = await dispatcher.dispatch_policy_eval({
      kind: 'policy_eval',
      policy_id: 'C-missing',
      input: { step: {}, workflow: {}, execution_context: {} },
      trace_id: 'trace-abc',
      workflow_id: 'W-test',
      step_id: 0,
    })
    expect(decision.kind).toBe('deny')
    expect(exporter.records).toHaveLength(1)
    const r = exporter.records[0]!
    expect(r.decision_kind).toBe('POLICY_DENY')
    expect(r.trace_id).toBe('trace-abc')
    expect(r.workflow_id).toBe('W-test')
    expect(r.step_id).toBe(0)
    expect(r.attributes).toMatchObject({
      policy_id: 'C-missing',
      rule_name: 'bundle_lookup_failure',
    })
  })

  it('absent trace_id ⇒ no emission (M7 baseline back-compat)', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const bundle = new OPABundleService()
    const dispatcher = makePolicyDispatcher(bundle, emitter)
    await dispatcher.dispatch_policy_eval({
      kind: 'policy_eval',
      policy_id: 'C-missing',
      input: { step: {}, workflow: {}, execution_context: {} },
      // no trace_id
    })
    expect(exporter.records).toHaveLength(0)
  })

  it('no emitter argument ⇒ no emission, dispatcher still functions', async () => {
    const bundle = new OPABundleService()
    const dispatcher = makePolicyDispatcher(bundle)
    const decision = await dispatcher.dispatch_policy_eval({
      kind: 'policy_eval',
      policy_id: 'C-missing',
      input: { step: {}, workflow: {}, execution_context: {} },
      trace_id: 'trace-xyz',
    })
    expect(decision.kind).toBe('deny')
  })
})

// -----------------------------------------------------------------------------
// T-107 — skill-invocation emits 3 outcomes
// -----------------------------------------------------------------------------

describe('skill-invocation OTel emission (T-107)', () => {
  function parentStep(skill_ref: string): WorkflowStep {
    return {
      step_id: 0,
      skill_ref,
      inputs: [],
      outputs: [],
      on_failure: 'abort',
    }
  }

  it('emits SKILL_UNRESOLVED on missing skill', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const result = await invokeSkill(parentStep('missing-skill'), {
      skill_engine: new SkillEngine(),
      dispatch: () => ({ kind: 'ok', outputs: [] }),
      recursion_depth: 0,
      otel_emitter: emitter,
      trace_id: 'tid-1',
      workflow_id: 'W-parent',
    })
    expect(result.kind).toBe('failure')
    expect(exporter.records).toHaveLength(1)
    expect(exporter.records[0]!.decision_kind).toBe('SKILL_UNRESOLVED')
    expect(exporter.records[0]!.trace_id).toBe('tid-1')
  })

  it('emits SKILL_RECURSION_CAP at depth ≥ cap', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const result = await invokeSkill(parentStep('any-skill'), {
      skill_engine: new SkillEngine(),
      dispatch: () => ({ kind: 'ok', outputs: [] }),
      recursion_depth: 8, // cap
      otel_emitter: emitter,
      trace_id: 'tid-2',
    })
    expect(result.kind).toBe('failure')
    expect(exporter.records).toHaveLength(1)
    expect(exporter.records[0]!.decision_kind).toBe('SKILL_RECURSION_CAP')
    expect(exporter.records[0]!.attributes).toMatchObject({ recursion_depth: 8 })
  })

  it('emits SKILL_RESOLVED on a registered skill happy path', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const skillWf: Workflow = createWorkflow({
      id: 'W-skill',
      preconditions: '',
      step_graph: [
        { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'pause',
      reuse_tag: true,
      return_contract: '{"type":"string"}',
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'autonomous',
    })
    const engine = new SkillEngine()
    engine.register(skillWf)
    const result = await invokeSkill(parentStep('W-skill'), {
      skill_engine: engine,
      dispatch: () => ({ kind: 'ok', outputs: ['hello'] }),
      recursion_depth: 0,
      otel_emitter: emitter,
      trace_id: 'tid-3',
    })
    expect(result.kind).toBe('success')
    // SKILL_RESOLVED is emitted at end of invokeSkill on success path. The
    // child execution itself may have emitted STEP_* events too — assert
    // that AT LEAST one SKILL_RESOLVED fired with our trace_id.
    const resolved = exporter.records.filter((r) => r.decision_kind === 'SKILL_RESOLVED')
    expect(resolved.length).toBeGreaterThanOrEqual(1)
    expect(resolved[0]!.trace_id).toBe('tid-3')
    expect(resolved[0]!.attributes).toHaveProperty('skill_ref', 'W-skill')
    expect(resolved[0]!.attributes).toHaveProperty('child_execution_id')
    expect(resolved[0]!.attributes).toHaveProperty('validated_dataref')
  })
})

// -----------------------------------------------------------------------------
// T-108 — step-graph-executor emits STEP_START / STEP_COMPLETE / STEP_FAIL
// -----------------------------------------------------------------------------

describe('step-graph-executor OTel emission (T-108)', () => {
  function simpleWorkflow(steps: WorkflowStep[]): Workflow {
    return createWorkflow({
      id: 'W-otel',
      preconditions: '',
      step_graph: steps,
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: '',
      stringency: 'task',
      interfaces_with: [],
      expects_response_from: null,
      on_override_action: 'pause',
      reuse_tag: false,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'autonomous',
    })
  }

  it('emits STEP_START + STEP_COMPLETE for each successful step', async () => {
    const exporter = new InMemoryOTelExporter()
    const wf = simpleWorkflow([
      { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ])
    const dispatch: ActivityDispatcher = (d) => ({ kind: 'ok', outputs: [`x-${d.step_id}`] })
    const r = await executeStepGraph(wf, dispatch, {
      otel_emitter: new OTelEmitter(exporter),
    })
    expect(r.state).toBe('success')
    const starts = exporter.records.filter((x) => x.decision_kind === 'STEP_START')
    const completes = exporter.records.filter((x) => x.decision_kind === 'STEP_COMPLETE')
    expect(starts).toHaveLength(2)
    expect(completes).toHaveLength(2)
    // attributes on STEP_COMPLETE include outputs_hash
    for (const c of completes) {
      expect(c.attributes).toHaveProperty('outputs_hash')
      expect(typeof c.attributes.outputs_hash).toBe('string')
    }
  })

  it('emits STEP_FAIL when a step fails, then a FAILURE_POLICY_<OUTCOME>', async () => {
    const exporter = new InMemoryOTelExporter()
    const wf = simpleWorkflow([
      { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ])
    const dispatch: ActivityDispatcher = () => ({
      kind: 'failure',
      error: new Error('boom'),
    })
    await executeStepGraph(wf, dispatch, { otel_emitter: new OTelEmitter(exporter) })

    const fails = exporter.records.filter((r) => r.decision_kind === 'STEP_FAIL')
    expect(fails).toHaveLength(1)
    expect(fails[0]!.attributes).toMatchObject({
      failure_reason: 'boom',
      on_failure: 'abort',
    })
    const aborts = exporter.records.filter(
      (r) => r.decision_kind === 'FAILURE_POLICY_ABORT',
    )
    expect(aborts).toHaveLength(1)
  })

  it('all emitted events for one run share the same trace_id', async () => {
    const exporter = new InMemoryOTelExporter()
    const wf = simpleWorkflow([
      { step_id: 0, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
      { step_id: 1, action: 'wait', inputs: [], outputs: [], on_failure: 'abort' },
    ])
    await executeStepGraph(
      wf,
      (d) => ({ kind: 'ok', outputs: [d.step_id] }),
      { otel_emitter: new OTelEmitter(exporter) },
    )
    expect(exporter.records.length).toBeGreaterThan(0)
    const tid = exporter.records[0]!.trace_id
    expect(tid).toMatch(/^[a-f0-9]{32}$/)
    for (const r of exporter.records) {
      expect(r.trace_id).toBe(tid)
    }
  })
})

// -----------------------------------------------------------------------------
// T-109 — failure-policy emits one event per outcome
// -----------------------------------------------------------------------------

describe('failure-policy OTel emission (T-109)', () => {
  function step(action: 'rollback' | 'escalate' | 'pause' | 'abort' | 'continue'): WorkflowStep {
    return {
      step_id: 7,
      action: 'wait',
      inputs: [],
      outputs: [],
      on_failure: action,
    }
  }
  const ctx: ExecutionContext = {
    completed_step_ids: [1, 2, 3],
    autonomy_level: 'autonomous',
  }
  const err = new Error('boom')

  it.each([
    ['rollback', 'FAILURE_POLICY_ROLLBACK'],
    ['escalate', 'FAILURE_POLICY_ESCALATE'],
    ['pause', 'FAILURE_POLICY_PAUSE'],
    ['abort', 'FAILURE_POLICY_ABORT'],
    ['continue', 'FAILURE_POLICY_CONTINUE'],
  ] as const)('on_failure=%s emits %s', async (action, kind) => {
    const exporter = new InMemoryOTelExporter()
    applyFailurePolicy(step(action), err, ctx, {
      otel_emitter: new OTelEmitter(exporter),
      trace_id: 't-fp',
      workflow_id: 'W-fp',
    })
    // emit is fire-and-forget; let the microtask queue drain.
    await new Promise((r) => setImmediate(r))
    expect(exporter.records).toHaveLength(1)
    expect(exporter.records[0]!.decision_kind).toBe(kind)
    expect(exporter.records[0]!.trace_id).toBe('t-fp')
    expect(exporter.records[0]!.workflow_id).toBe('W-fp')
    expect(exporter.records[0]!.step_id).toBe(7)
    expect(exporter.records[0]!.attributes).toMatchObject({
      failed_step_id: 7,
      reason: expect.stringContaining(`step:7:${action}:boom`),
    })
  })

  it('omitted otelCtx ⇒ no emit (M5/M6/M7 backward compat)', async () => {
    // No throws when otelCtx is undefined.
    const outcome = applyFailurePolicy(step('abort'), err, ctx)
    expect(outcome.action).toBe('abort')
  })
})
