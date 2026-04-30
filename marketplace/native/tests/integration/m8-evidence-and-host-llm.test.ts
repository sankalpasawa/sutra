/**
 * M8 evidence emission + host-LLM — integration scenarios (Group CC T-125).
 *
 * 11 codex-mandated scenarios per A-11.a..k. Each composes the M8 surfaces
 * (OTelEmitter + GovernanceOverhead + host-LLM Activity) with the M5/M6/M7
 * surfaces (executor + skill engine + policy dispatcher) and asserts the
 * end-to-end contract.
 *
 *   A-11.a  POLICY_ALLOW emits with policy_id + policy_version + authority
 *   A-11.b  POLICY_DENY emits with sanitized reason + policy_version
 *   A-11.c  Skill resolution: SKILL_RESOLVED + SKILL_UNRESOLVED + SKILL_RECURSION_CAP
 *   A-11.d  Overhead under 15% threshold → no GOVERNANCE_OVERHEAD_ALERT emitted
 *   A-11.e  Overhead over 15% threshold → alert emitted with per_category
 *   A-11.f  Claude CLI invocation: --bare --print + DataRef envelope
 *   A-11.g  Codex CLI invocation: prompt via stdin + DataRef envelope
 *   A-11.h  Host unavailable → HostUnavailableError synthesized step failure
 *   A-11.i  HOST_LLM_INVOCATION provenance carries host_kind/version/ids/hashes
 *   A-11.j  Trace ID correlation across one workflow run
 *   A-11.k  Recursion safety: --bare flag pinned in args (real subprocess deferred)
 *
 * Test seam contract (codex pivot review fold #3):
 *   - All host-LLM tests use `__setExecFileSyncStubForTest` +
 *     `__setHostAvailabilityForTest`. NO real `claude` or `codex` subprocesses
 *     spawn during the integration suite — keeps CI deterministic + offline-safe.
 *
 * Determinism contract:
 *   - `__resetWorkflowRunSeqForTest()` runs in `beforeEach` so back-to-back
 *     scenarios over identical Workflows produce identical trace_ids.
 *   - Host availability + execFileSync stubs reset in `afterEach`.
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group CC T-125
 *  - .enforcement/codex-reviews/2026-04-30-m8-plan-pre-dispatch.md (P2.3)
 *  - holding/research/2026-04-29-native-v1.0-final-architecture.md §5
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'

import { createCharter, type Charter } from '../../src/primitives/charter.js'
import { createWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import { compileCharter } from '../../src/engine/charter-rego-compiler.js'
import { OPABundleService } from '../../src/engine/opa-bundle-service.js'
import { makePolicyDispatcher } from '../../src/engine/policy-dispatcher.js'
import { SkillEngine } from '../../src/engine/skill-engine.js'
import { SKILL_RECURSION_CAP } from '../../src/engine/skill-invocation.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
  type StepDispatchResult,
} from '../../src/engine/step-graph-executor.js'
import {
  GovernanceOverhead,
} from '../../src/engine/governance-overhead.js'
import {
  InMemoryOTelExporter,
  OTelEmitter,
} from '../../src/engine/otel-emitter.js'
import {
  __setHostAvailabilityForTest,
  __resetHostAvailabilityForTest,
  __setExecFileSyncStubForTest,
  __resetExecFileSyncStubForTest,
  type ExecFileSyncStub,
} from '../../src/engine/host-llm-activity.js'
import type { DataRef, WorkflowStep } from '../../src/types/index.js'

// =============================================================================
// Fixtures
// =============================================================================

/** Minimal Charter with a single allow predicate (Rego literal). */
function charterAllowing(predicate: string, id = 'C-m8'): Charter {
  return createCharter({
    id,
    purpose: 'M8 Group CC integration test charter',
    scope_in: '',
    scope_out: '',
    obligations: [],
    invariants: [],
    success_metrics: [],
    authority: 'M8-test',
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

/** Wire compiled charter into a bundle + dispatcher with optional emitter. */
function wirePolicy(
  charter: Charter,
  emitter?: OTelEmitter,
): {
  policy: ReturnType<typeof compileCharter>
  dispatcher: ReturnType<typeof makePolicyDispatcher>
} {
  const policy = compileCharter(charter)
  const bundle = new OPABundleService()
  bundle.register(policy)
  const dispatcher = makePolicyDispatcher(bundle, emitter)
  return { policy, dispatcher }
}

/** Always-OK dispatcher emitting a deterministic per-step output. */
const okDispatcher: ActivityDispatcher = (descriptor): StepDispatchResult => ({
  kind: 'ok',
  outputs: [`m8-step-${descriptor.step_id}`],
})

/** Set both host CLIs available with stable versions for deterministic invocation_id. */
function setBothHostsAvailable(): void {
  const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
  map.set('claude', { available: true, version: '2.1.123' })
  map.set('codex', { available: true, version: 'codex-cli 0.118.0' })
  __setHostAvailabilityForTest(map)
}

/** Build a host-LLM step (action='invoke_host_llm', prompt in inputs[0].locator). */
function hostLLMStep(opts: {
  step_id: number
  host: 'claude' | 'codex'
  prompt: string
  on_failure?: 'abort' | 'rollback' | 'continue' | 'escalate' | 'pause'
  return_contract?: string
}): WorkflowStep {
  const promptRef: DataRef = {
    kind: 'host-llm-prompt',
    schema_ref: '',
    locator: opts.prompt,
    version: '1',
    mutability: 'immutable',
    retention: 'session',
    authoritative_status: 'authoritative',
  }
  const step: WorkflowStep = {
    step_id: opts.step_id,
    action: 'invoke_host_llm',
    host: opts.host,
    inputs: [promptRef],
    outputs: [],
    on_failure: opts.on_failure ?? 'abort',
  }
  if (opts.return_contract !== undefined) {
    step.return_contract = opts.return_contract
  }
  return step
}

// Reset shared module-level state between scenarios.
beforeEach(() => {
  __resetWorkflowRunSeqForTest()
})

afterEach(() => {
  __resetHostAvailabilityForTest()
  __resetExecFileSyncStubForTest()
})

// =============================================================================
// A-11.a — POLICY_ALLOW emits with policy_id + policy_version + authority
// =============================================================================

describe('M8 A-11.a — POLICY_ALLOW emits DecisionProvenance-bearing OTel record', () => {
  it('charter allows step → POLICY_ALLOW event present with policy_id + policy_version', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    // Predicate `1 == 1` always holds — allow path.
    const charter = charterAllowing('1 == 1', 'C-m8a')
    const { policy, dispatcher } = wirePolicy(charter, emitter)
    const w = createWorkflow({
      id: 'W-m8a',
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

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
      otel_emitter: emitter,
      actor: 'asawa@nurix.ai',
    })

    expect(result.state).toBe('success')
    // Find the POLICY_ALLOW event — at least one must be present.
    const allowEvents = exporter.records.filter((r) => r.decision_kind === 'POLICY_ALLOW')
    expect(allowEvents).toHaveLength(1)
    const evt = allowEvents[0]!
    expect(evt.attributes.policy_id).toBe(policy.policy_id)
    expect(evt.attributes.policy_version).toBe(policy.policy_version)
    // policy_version is 64-hex sha256.
    expect(evt.attributes.policy_version as string).toMatch(/^[a-f0-9]{64}$/)
    // authority surface — actor propagates to the event so downstream
    // observability can attribute the decision.
    expect(evt.actor).toBe('asawa@nurix.ai')
    expect(evt.workflow_id).toBe('W-m8a')
    expect(evt.step_id).toBe(1)
    // trace_id is 32-hex (D-NS-26).
    expect(evt.trace_id).toMatch(/^[a-f0-9]{32}$/)
  })
})

// =============================================================================
// A-11.b — POLICY_DENY emits with sanitized reason + policy_version
// =============================================================================

describe('M8 A-11.b — POLICY_DENY emits sanitized reason (M7 P1.2)', () => {
  it('charter denies → POLICY_DENY event present with rule_name + reason + policy_version', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    // `false` predicate → default-deny on every input.
    const charter = charterAllowing('false', 'C-m8b')
    const { policy, dispatcher } = wirePolicy(charter, emitter)
    const w = createWorkflow({
      id: 'W-m8b',
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

    const result = await executeStepGraph(w, okDispatcher, {
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
      otel_emitter: emitter,
    })

    expect(result.state).toBe('failed')
    // M7 P1.2 sanitized failure_reason envelope — `step:N:abort:policy_deny:...`.
    expect(result.failure_reason).toMatch(/^step:1:abort:policy_deny:[^:]+:[^:]+:[a-f0-9]{64}$/)

    const denyEvents = exporter.records.filter((r) => r.decision_kind === 'POLICY_DENY')
    expect(denyEvents).toHaveLength(1)
    const evt = denyEvents[0]!
    expect(evt.attributes.policy_id).toBe(policy.policy_id)
    expect(evt.attributes.policy_version).toBe(policy.policy_version)
    expect(evt.attributes.policy_version as string).toMatch(/^[a-f0-9]{64}$/)
    // rule_name + reason are non-colon tokens (sanitization invariant).
    expect(typeof evt.attributes.rule_name).toBe('string')
    expect(evt.attributes.rule_name as string).not.toContain(':')
    expect(typeof evt.attributes.reason).toBe('string')
    expect(evt.attributes.reason as string).not.toContain(':')
  })
})

// =============================================================================
// A-11.c — Skill resolution outcomes: SKILL_RESOLVED + SKILL_UNRESOLVED + SKILL_RECURSION_CAP
// =============================================================================

describe('M8 A-11.c — Skill resolution emits all 3 outcomes', () => {
  it('SKILL_RESOLVED — registered skill resolves; OTel event emitted', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const engine = new SkillEngine()
    engine.register(
      createWorkflow({
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
        return_contract: JSON.stringify(true),
      }),
    )
    const parent = createWorkflow({
      id: 'W-m8c-resolved',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-echo', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(parent, okDispatcher, {
      skill_engine: engine,
      otel_emitter: emitter,
    })

    expect(result.state).toBe('success')
    const resolved = exporter.records.filter((r) => r.decision_kind === 'SKILL_RESOLVED')
    expect(resolved.length).toBeGreaterThanOrEqual(1)
    expect(resolved[0]!.workflow_id).toBe('W-m8c-resolved')
    expect((resolved[0]!.attributes as { skill_ref: string }).skill_ref).toBe('W-echo')
  })

  it('SKILL_UNRESOLVED — unregistered skill_ref emits unresolved event', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const engine = new SkillEngine()
    const parent = createWorkflow({
      id: 'W-m8c-unresolved',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-missing', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(parent, okDispatcher, {
      skill_engine: engine,
      otel_emitter: emitter,
    })

    expect(result.state).toBe('failed')
    const unresolved = exporter.records.filter((r) => r.decision_kind === 'SKILL_UNRESOLVED')
    expect(unresolved).toHaveLength(1)
    expect((unresolved[0]!.attributes as { skill_ref: string }).skill_ref).toBe('W-missing')
  })

  it('SKILL_RECURSION_CAP — at-cap recursion_depth fires cap event', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const engine = new SkillEngine()
    engine.register(
      createWorkflow({
        id: 'W-cap-leaf',
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
        return_contract: JSON.stringify(true),
      }),
    )
    const parent = createWorkflow({
      id: 'W-m8c-cap',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-cap-leaf', inputs: [], outputs: [], on_failure: 'abort' },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(parent, okDispatcher, {
      skill_engine: engine,
      otel_emitter: emitter,
      recursion_depth: SKILL_RECURSION_CAP,
    })

    expect(result.state).toBe('failed')
    expect(result.failure_reason).toBe(`step:1:abort:skill_recursion_cap:${SKILL_RECURSION_CAP}`)
    const cap = exporter.records.filter((r) => r.decision_kind === 'SKILL_RECURSION_CAP')
    expect(cap).toHaveLength(1)
    expect((cap[0]!.attributes as { recursion_depth: number }).recursion_depth).toBe(
      SKILL_RECURSION_CAP,
    )
  })
})

// =============================================================================
// A-11.d — Overhead under 15% threshold → no alert
// =============================================================================

describe('M8 A-11.d — overhead under threshold → no GOVERNANCE_OVERHEAD_ALERT', () => {
  it('10% overhead does not trip; exporter contains no alert event', () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const overhead = new GovernanceOverhead({ otelEmitter: emitter })

    overhead.startTurn('turn-d', 1000)
    overhead.track('turn-d', 'codex_review', 100) // 10% — below 15%
    const report = overhead.endTurn('turn-d')

    expect(report.threshold_tripped).toBe(false)
    expect(report.overhead_pct).toBeCloseTo(0.1, 5)
    const alerts = exporter.records.filter(
      (r) => r.decision_kind === 'GOVERNANCE_OVERHEAD_ALERT',
    )
    expect(alerts).toHaveLength(0)
  })
})

// =============================================================================
// A-11.e — Overhead over 15% threshold → alert with per_category
// =============================================================================

describe('M8 A-11.e — overhead over threshold → GOVERNANCE_OVERHEAD_ALERT emitted', () => {
  it('25% overhead trips; alert carries per_category breakdown', async () => {
    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const overhead = new GovernanceOverhead({ otelEmitter: emitter })

    overhead.startTurn('turn-e', 1000)
    overhead.track('turn-e', 'codex_review', 200) // 20%
    overhead.track('turn-e', 'hook_fire', 50) // +5% = 25% total
    const report = overhead.endTurn('turn-e')

    expect(report.threshold_tripped).toBe(true)
    expect(report.overhead_pct).toBeCloseTo(0.25, 5)

    // The emit is fire-and-forget — let the microtask drain.
    await Promise.resolve()
    await Promise.resolve()

    const alerts = exporter.records.filter(
      (r) => r.decision_kind === 'GOVERNANCE_OVERHEAD_ALERT',
    )
    expect(alerts).toHaveLength(1)
    const evt = alerts[0]!
    expect(evt.trace_id).toBe('turn-e')
    expect(evt.attributes.threshold).toBe(0.15)
    expect(evt.attributes.overhead_pct).toBeCloseTo(0.25, 5)
    expect(evt.attributes.tokens_total).toBe(1000)
    expect(evt.attributes.tokens_governance).toBe(250)
    const per = evt.attributes.per_category as Record<string, number>
    expect(per.codex_review).toBe(200)
    expect(per.hook_fire).toBe(50)
    // Untouched categories present and zero — full breakdown surface.
    expect(per.input_routing).toBe(0)
    expect(per.depth_estimation).toBe(0)
    expect(per.blueprint).toBe(0)
    expect(per.build_layer).toBe(0)
  })
})

// =============================================================================
// A-11.f — Claude CLI invocation: --bare --print + DataRef envelope
// =============================================================================

describe('M8 A-11.f — Claude CLI invocation produces DataRef envelope', () => {
  it('stub captures `claude --bare --print <prompt>`; outputs[0] is DataRef', async () => {
    setBothHostsAvailable()
    let capturedFile = ''
    let capturedArgs: string[] = []
    const stub: ExecFileSyncStub = (file, args, _opts) => {
      capturedFile = file
      capturedArgs = [...args]
      return 'response text'
    }
    __setExecFileSyncStubForTest(stub)

    // Codex master review 2026-04-30 P2.1 fold: declare a step.return_contract
    // so the envelope advertises the response schema (not the prompt schema —
    // the previous shape was a contract drift).
    const responseSchema = JSON.stringify({ type: 'string' })
    const w = createWorkflow({
      id: 'W-m8f',
      preconditions: '',
      step_graph: [
        hostLLMStep({
          step_id: 1,
          host: 'claude',
          prompt: 'hello',
          return_contract: responseSchema,
        }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(w, okDispatcher)

    expect(result.state).toBe('success')
    expect(capturedFile).toBe('claude')
    // --bare MUST be the first arg (recursion-safety contract).
    expect(capturedArgs).toEqual(['--bare', '--print', 'hello'])

    expect(result.step_outputs).toHaveLength(1)
    const outs = result.step_outputs[0]!.outputs
    expect(outs).toHaveLength(1)
    const dr = outs[0] as DataRef
    expect(dr.kind).toBe('host-llm-output')
    // Codex P2.1 fold: schema_ref MUST be step.return_contract (the response
    // schema), NOT inputs[0].schema_ref (the prompt schema).
    expect(dr.schema_ref).toBe(responseSchema)
    expect(dr.locator).toBe('inline:' + JSON.stringify('response text'))
    expect(dr.version).toBe('1')
    expect(dr.mutability).toBe('immutable')
    expect(dr.retention).toBe('session')
    expect(dr.authoritative_status).toBe('authoritative')
  })

  it('omitted return_contract → schema_ref defaults to empty string (codex M8 P2.1 fold)', async () => {
    setBothHostsAvailable()
    __setExecFileSyncStubForTest(() => 'unconstrained-response')
    const w = createWorkflow({
      id: 'W-m8f-no-rc',
      preconditions: '',
      step_graph: [
        hostLLMStep({ step_id: 1, host: 'claude', prompt: 'p' }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeStepGraph(w, okDispatcher)
    expect(result.state).toBe('success')
    const dr = result.step_outputs[0]!.outputs[0] as DataRef
    expect(dr.schema_ref).toBe('')
  })
})

// =============================================================================
// A-11.g — Codex CLI invocation: prompt via stdin + DataRef envelope
// =============================================================================

describe('M8 A-11.g — Codex CLI invocation produces DataRef envelope', () => {
  it('stub receives `codex exec --skip-git-repo-check` with prompt via stdin', async () => {
    setBothHostsAvailable()
    let capturedFile = ''
    let capturedArgs: string[] = []
    let capturedStdin: string | undefined
    const stub: ExecFileSyncStub = (file, args, opts) => {
      capturedFile = file
      capturedArgs = [...args]
      capturedStdin = opts.input
      return 'codex response'
    }
    __setExecFileSyncStubForTest(stub)

    // Codex P2.1: declare step.return_contract so envelope schema_ref carries
    // the response schema (not the prompt schema).
    const responseSchema = JSON.stringify({ type: 'string' })
    const w = createWorkflow({
      id: 'W-m8g',
      preconditions: '',
      step_graph: [
        hostLLMStep({
          step_id: 1,
          host: 'codex',
          prompt: 'codex prompt',
          return_contract: responseSchema,
        }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(w, okDispatcher)

    expect(result.state).toBe('success')
    expect(capturedFile).toBe('codex')
    expect(capturedArgs).toEqual(['exec', '--skip-git-repo-check'])
    // Prompt MUST flow via stdin (input field), NOT via positional args.
    expect(capturedStdin).toBe('codex prompt')

    const dr = result.step_outputs[0]!.outputs[0] as DataRef
    expect(dr.kind).toBe('host-llm-output')
    // Codex P2.1 fold: schema_ref MUST be step.return_contract.
    expect(dr.schema_ref).toBe(responseSchema)
    expect(dr.locator).toBe('inline:' + JSON.stringify('codex response'))
  })
})

// =============================================================================
// A-11.l — codex master review 2026-04-30 P2.1 fold: host-LLM output validation
// =============================================================================

describe('M8 A-11.l — host-LLM output validates against return_contract (codex P2.1 fold)', () => {
  it('valid response → step succeeds; envelope carries return_contract as schema_ref', async () => {
    setBothHostsAvailable()
    // Response is JSON-encoded number; schema asserts type=number.
    __setExecFileSyncStubForTest(() => '42')
    const numberSchema = JSON.stringify({ type: 'number' })
    const w = createWorkflow({
      id: 'W-m8l-ok',
      preconditions: '',
      step_graph: [
        hostLLMStep({
          step_id: 1,
          host: 'claude',
          prompt: 'p',
          return_contract: numberSchema,
        }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeStepGraph(w, okDispatcher)
    expect(result.state).toBe('success')
    const dr = result.step_outputs[0]!.outputs[0] as DataRef
    expect(dr.schema_ref).toBe(numberSchema)
  })

  it('invalid response → synthesizes step failure with host_llm_output_validation:<details> errMsg', async () => {
    setBothHostsAvailable()
    // Response cannot parse as JSON → falls back to validating the raw
    // string. Schema asserts type=number, so a string fails validation.
    __setExecFileSyncStubForTest(() => 'not-a-number')
    const numberSchema = JSON.stringify({ type: 'number' })
    const w = createWorkflow({
      id: 'W-m8l-bad',
      preconditions: '',
      step_graph: [
        hostLLMStep({
          step_id: 1,
          host: 'claude',
          prompt: 'p',
          return_contract: numberSchema,
        }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeStepGraph(w, okDispatcher)
    expect(result.state).toBe('failed')
    // M5 P1.2 sanitized envelope: `step:<id>:<action>:<errMsg>`.
    expect(result.failure_reason).toMatch(
      /^step:1:abort:host_llm_output_validation:/,
    )
  })

  it('malformed return_contract (non-JSON) → schema_compile_failed under host_llm_output_validation', async () => {
    setBothHostsAvailable()
    __setExecFileSyncStubForTest(() => 'response')
    const w = createWorkflow({
      id: 'W-m8l-malformed',
      preconditions: '',
      step_graph: [
        hostLLMStep({
          step_id: 1,
          host: 'claude',
          prompt: 'p',
          return_contract: '{ not json',
        }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeStepGraph(w, okDispatcher)
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toMatch(
      /^step:1:abort:host_llm_output_validation:schema_compile_failed/,
    )
  })
})

// =============================================================================
// A-11.h — Host unavailable → HostUnavailableError → synthesized step failure
// =============================================================================

describe('M8 A-11.h — host unavailable → synthesized step failure', () => {
  it('codex unavailable → failure_reason carries host_llm_unavailable:codex (M5 envelope)', async () => {
    // Override availability: codex absent, claude present (irrelevant here).
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: true, version: '2.1.123' })
    map.set('codex', { available: false, version: null })
    __setHostAvailabilityForTest(map)

    const w = createWorkflow({
      id: 'W-m8h',
      preconditions: '',
      step_graph: [
        hostLLMStep({ step_id: 1, host: 'codex', prompt: 'unused' }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(w, okDispatcher)

    expect(result.state).toBe('failed')
    // M5 P1.2 sanitized envelope: `step:<id>:<action>:<errMsg>`.
    expect(result.failure_reason).toBe('step:1:abort:host_llm_unavailable:codex')
    expect(result.completed_step_ids).toEqual([])
    expect(result.visited_step_ids).toEqual([1])
  })
})

// =============================================================================
// A-11.i — HOST_LLM_INVOCATION provenance
// =============================================================================

describe('M8 A-11.i — HOST_LLM_INVOCATION provenance event', () => {
  it('successful host invocation emits provenance with host_kind/version/ids/hashes', async () => {
    setBothHostsAvailable()
    const stub: ExecFileSyncStub = (_file, _args, _opts) => 'response text'
    __setExecFileSyncStubForTest(stub)

    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)
    const w = createWorkflow({
      id: 'W-m8i',
      preconditions: '',
      step_graph: [
        hostLLMStep({ step_id: 1, host: 'claude', prompt: 'prompt-i' }),
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
      otel_emitter: emitter,
    })

    expect(result.state).toBe('success')
    const events = exporter.records.filter(
      (r) => r.decision_kind === 'HOST_LLM_INVOCATION',
    )
    expect(events).toHaveLength(1)
    const evt = events[0]!
    expect(evt.workflow_id).toBe('W-m8i')
    expect(evt.step_id).toBe(1)
    expt32Hex(evt.trace_id)

    const attrs = evt.attributes as {
      host_kind: string
      host_version: string
      invocation_id: string
      prompt_hash: string
      response_hash: string
      tokens_used: number | null
    }
    expect(attrs.host_kind).toBe('claude')
    expect(attrs.host_version).toBe('2.1.123')
    expt32Hex(attrs.invocation_id)
    expt32Hex(attrs.prompt_hash)
    expt32Hex(attrs.response_hash)
    // tokens_used not surfaced by stub; v1.0 contract = null.
    expect(attrs.tokens_used).toBeNull()
  })
})

// Helper: assert a 32-char hex string (sha256 truncated).
function expt32Hex(s: string | undefined): void {
  expect(typeof s).toBe('string')
  expect(s).toMatch(/^[a-f0-9]{32}$/)
}

// =============================================================================
// A-11.j — Trace ID correlation across one workflow run
// =============================================================================

describe('M8 A-11.j — trace_id correlation across one workflow run', () => {
  it('all events from a 3-step run (skill + policy + host_llm) share one trace_id', async () => {
    setBothHostsAvailable()
    __setExecFileSyncStubForTest(() => 'response text')

    const exporter = new InMemoryOTelExporter()
    const emitter = new OTelEmitter(exporter)

    const charter = charterAllowing('1 == 1', 'C-m8j')
    const { policy, dispatcher } = wirePolicy(charter, emitter)

    const engine = new SkillEngine()
    engine.register(
      createWorkflow({
        id: 'W-m8j-leaf',
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
        return_contract: JSON.stringify(true),
      }),
    )

    const parent = createWorkflow({
      id: 'W-m8j',
      preconditions: '',
      step_graph: [
        { step_id: 1, skill_ref: 'W-m8j-leaf', inputs: [], outputs: [], on_failure: 'abort' },
        {
          step_id: 2,
          action: 'wait',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
          policy_check: true,
        },
        hostLLMStep({ step_id: 3, host: 'claude', prompt: 'prompt-j' }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(parent, okDispatcher, {
      skill_engine: engine,
      policy_dispatcher: dispatcher,
      compiled_policy: policy,
      otel_emitter: emitter,
    })

    expect(result.state).toBe('success')
    expect(exporter.records.length).toBeGreaterThan(3)
    // ALL events share ONE trace_id. Take the first as canonical and assert.
    const traceIds = new Set(exporter.records.map((r) => r.trace_id))
    expect(traceIds.size).toBe(1)
    const sole = [...traceIds][0]!
    expect(sole).toMatch(/^[a-f0-9]{32}$/)

    // At least one event from each surface is present and correlated.
    const kinds = new Set(exporter.records.map((r) => r.decision_kind))
    expect(kinds.has('SKILL_RESOLVED')).toBe(true)
    expect(kinds.has('POLICY_ALLOW')).toBe(true)
    expect(kinds.has('HOST_LLM_INVOCATION')).toBe(true)
    expect(kinds.has('STEP_START')).toBe(true)
    expect(kinds.has('STEP_COMPLETE')).toBe(true)
  })
})

// =============================================================================
// A-11.k — Recursion safety: --bare flag pinned in args
// =============================================================================

describe('M8 A-11.k — recursion safety: --bare flag pinned in args', () => {
  // Test contract:
  //   The actual `claude --bare` subprocess SKIPS plugin sync per Claude Code
  //   2.1.123 verified semantics. This test pins that the wrapper passes the
  //   `--bare` flag (and that it is the FIRST argument so the recursion-safety
  //   guarantee cannot regress to a positional-argument shuffle). Real-
  //   subprocess verification of the no-plugin-load behavior is deferred to
  //   M11 dogfood per D-NS-12 (b).
  it('claude invocation pins --bare as first arg (recursion-safety contract)', async () => {
    setBothHostsAvailable()
    let observedArgs: string[] = []
    __setExecFileSyncStubForTest((_file, args, _opts) => {
      observedArgs = [...args]
      return ''
    })

    const w = createWorkflow({
      id: 'W-m8k',
      preconditions: '',
      step_graph: [
        hostLLMStep({ step_id: 1, host: 'claude', prompt: 'recursion-pin' }),
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: '',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeStepGraph(w, okDispatcher)
    expect(result.state).toBe('success')

    // Load-bearing assertion: --bare is the FIRST arg + --print is present.
    // A future change that shuffles arg order (e.g. `claude --print --bare`)
    // would still SKIP plugin sync per claude 2.1.123 today, but the
    // first-position contract is the documented promise — we pin it.
    expect(observedArgs[0]).toBe('--bare')
    expect(observedArgs).toContain('--print')
    expect(observedArgs).toContain('recursion-pin')
  })

  // Optional smoke that the binary exists. Deliberately does NOT spawn
  // `claude --bare --print` — that would be slow and non-deterministic in CI.
  // Gated behind RUN_REAL_CLAUDE so the default test suite stays offline-safe.
  it.skipIf(!process.env.RUN_REAL_CLAUDE)(
    'optional smoke: real `claude --version` returns a string (gated by RUN_REAL_CLAUDE)',
    () => {
      // Pull execFileSync directly — bypassing the runtime's stub seam.
      // Importing inside the test keeps the cost off the standard suite.
      const { execFileSync } = require('node:child_process')
      const out = execFileSync('claude', ['--version'], {
        encoding: 'utf-8',
        timeout: 5000,
      })
      expect(typeof out).toBe('string')
      expect(out.length).toBeGreaterThan(0)
    },
  )
})
