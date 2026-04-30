/**
 * Host-LLM step contract tests — M8 Group BB (T-115, T-116, T-120).
 *
 * Asserts:
 *  - createWorkflow accepts step with action='invoke_host_llm' + host
 *  - createWorkflow rejects action='invoke_host_llm' WITHOUT host
 *  - createWorkflow rejects host on action='wait' (forbidden case)
 *  - isValidWorkflow agrees with constructor on the same XOR rules
 *  - executor wires action='invoke_host_llm' → hostLLMActivity dispatch
 *  - executor wraps response in DataRef envelope (kind='host-llm-output')
 *  - executor synthesizes failure on host_llm_unavailable
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group BB T-115/T-116/T-120
 *  - .enforcement/codex-reviews/2026-04-30-architecture-pivot-rereview.md
 */

import { describe, it, expect, afterEach } from 'vitest'
import { createWorkflow, isValidWorkflow, type Workflow } from '../../src/primitives/workflow.js'
import type { DataRef, WorkflowStep } from '../../src/types/index.js'
import {
  executeStepGraph,
  __resetWorkflowRunSeqForTest,
  type ActivityDispatcher,
} from '../../src/engine/step-graph-executor.js'
import {
  __setHostAvailabilityForTest,
  __resetHostAvailabilityForTest,
  __setExecFileSyncStubForTest,
  __resetExecFileSyncStubForTest,
  type ExecFileSyncStub,
} from '../../src/engine/host-llm-activity.js'

const dr = (locator: string): DataRef => ({
  kind: 'host-llm-prompt',
  schema_ref: 'schema://prompt',
  locator,
  version: 'v1',
  mutability: 'immutable',
  retention: 'session',
})

afterEach(() => {
  __resetHostAvailabilityForTest()
  __resetExecFileSyncStubForTest()
  __resetWorkflowRunSeqForTest()
})

describe('createWorkflow — host-XOR step contract (T-115/T-116)', () => {
  it('accepts step with action=invoke_host_llm + host=claude', () => {
    const w = createWorkflow({
      id: 'W-host-claude',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [dr('hello')],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(isValidWorkflow(w)).toBe(true)
    expect(w.step_graph[0]!.host).toBe('claude')
  })

  it('accepts step with action=invoke_host_llm + host=codex', () => {
    const w = createWorkflow({
      id: 'W-host-codex',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'codex',
          inputs: [dr('hi')],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(w.step_graph[0]!.host).toBe('codex')
  })

  it('rejects action=invoke_host_llm WITHOUT host', () => {
    expect(() =>
      createWorkflow({
        id: 'W-host-missing',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            action: 'invoke_host_llm',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/host is required when action='invoke_host_llm'/)
  })

  it('rejects host="claude" on action=wait (forbidden case)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-host-wrong',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            action: 'wait',
            host: 'claude',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/host is forbidden unless action='invoke_host_llm'/)
  })

  it('rejects host on a skill_ref step (no action set)', () => {
    expect(() =>
      createWorkflow({
        id: 'W-host-on-skill',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            skill_ref: 's',
            host: 'claude',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/host is forbidden/)
  })

  it('rejects invalid host value', () => {
    expect(() =>
      createWorkflow({
        id: 'W-host-bad',
        preconditions: 'true',
        step_graph: [
          {
            step_id: 1,
            action: 'invoke_host_llm',
            host: 'gemini' as 'claude',
            inputs: [dr('p')],
            outputs: [],
            on_failure: 'abort',
          } as WorkflowStep,
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'true',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/host must be 'claude' or 'codex'/)
  })

  it('isValidWorkflow rejects deserialized record with host on action=wait', () => {
    const fake: Workflow = {
      id: 'W-deser-bad',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          action: 'wait',
          host: 'claude',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
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
      autonomy_level: 'manual',
    }
    expect(isValidWorkflow(fake)).toBe(false)
  })

  it('isValidWorkflow rejects deserialized record with action=invoke_host_llm and no host', () => {
    const fake: Workflow = {
      id: 'W-deser-missing',
      preconditions: '',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
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
      autonomy_level: 'manual',
    }
    expect(isValidWorkflow(fake)).toBe(false)
  })
})

describe('executeStepGraph — host-LLM dispatch wiring (T-120)', () => {
  function setBothAvailable(): void {
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: true, version: '2.1.123' })
    map.set('codex', { available: true, version: '0.118.0' })
    __setHostAvailabilityForTest(map)
  }

  it('dispatches action=invoke_host_llm via hostLLMActivity and wraps response in DataRef envelope', async () => {
    setBothAvailable()
    let called = false
    const stub: ExecFileSyncStub = (file, args) => {
      called = true
      expect(file).toBe('claude')
      expect(args[0]).toBe('--bare')
      return 'host-output'
    }
    __setExecFileSyncStubForTest(stub)

    const w = createWorkflow({
      id: 'W-exec-host-llm',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [dr('the-prompt')],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    // Pure-orchestration dispatcher — for action=invoke_host_llm the executor
    // does NOT call this. Provide a noop so the call site stays type-safe.
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })

    const result = await executeStepGraph(w, dispatch)
    expect(called).toBe(true)
    expect(result.state).toBe('success')
    expect(result.completed_step_ids).toEqual([1])
    expect(result.step_outputs).toHaveLength(1)
    const envelope = result.step_outputs[0]!.outputs[0] as DataRef
    expect(envelope.kind).toBe('host-llm-output')
    expect(envelope.locator).toBe('inline:' + JSON.stringify('host-output'))
    expect(envelope.mutability).toBe('immutable')
    expect(envelope.retention).toBe('session')
  })

  it('synthesizes step failure with host_llm_unavailable:<host> when host missing', async () => {
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: false, version: null })
    map.set('codex', { available: false, version: null })
    __setHostAvailabilityForTest(map)

    const w = createWorkflow({
      id: 'W-exec-host-missing',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [dr('p')],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('host_llm_unavailable:claude')
  })

  it('synthesizes failure with host_llm_invocation_failed when subprocess errors', async () => {
    setBothAvailable()
    __setExecFileSyncStubForTest(() => {
      throw new Error('boom')
    })

    const w = createWorkflow({
      id: 'W-exec-host-fail',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [dr('p')],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('host_llm_invocation_failed:')
  })

  it('synthesizes host_llm_invocation_failed:no_prompt when step has empty inputs', async () => {
    setBothAvailable()

    const w = createWorkflow({
      id: 'W-exec-no-prompt',
      preconditions: 'true',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [],
          outputs: [],
          on_failure: 'abort',
        } as WorkflowStep,
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'true',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const dispatch: ActivityDispatcher = () => ({ kind: 'ok', outputs: [] })
    const result = await executeStepGraph(w, dispatch)
    expect(result.state).toBe('failed')
    expect(result.failure_reason).toContain('host_llm_invocation_failed:no_prompt')
  })
})
