/**
 * v1.2.1 — LiteExecutor host-LLM dispatch test.
 *
 * Proves the load-bearing wire from M8 Group BB into the lite path:
 *   - Workflow with one invoke_host_llm step (host='claude') flows into
 *     `executeWorkflow` and reaches the injected host_llm_dispatch stub.
 *   - on_host_llm_result fires once with the canned HostLLMResult + step.
 *   - workflow_completed event is emitted.
 *   - prompt is read from step.inputs[0].locator (canonical v1.0 source).
 *
 * Closes P1.2 of DIRECTIVE 1777839055 — post-approval workflows are no
 * longer hollow when their step_graph contains invoke_host_llm.
 *
 * F-12 boundary: LiteExecutor runs on Worker context (not Workflow
 * context); the asActivity wrapper inside hostLLMActivity remains the
 * authority on F-12 enforcement. This test stubs dispatch directly so no
 * subprocess fires.
 */

import { describe, expect, it } from 'vitest'

import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import type { EngineEvent } from '../../src/types/engine-event.js'
import type { HostLLMResult } from '../../src/engine/host-llm-activity.js'

describe('LiteExecutor — invoke_host_llm dispatch (v1.2.1)', () => {
  it('dispatches to host_llm_dispatch stub, fires on_host_llm_result, emits workflow_completed', async () => {
    const stubResult: HostLLMResult = {
      response: 'website tagline updated to: "Sutra — operating system for context."',
      host_kind: 'claude',
      host_version: 'Claude Code 2.1.123',
      exit_code: 0,
      invocation_id: 'fixed-invocation-for-test-determinism',
    }

    let dispatchCallCount = 0
    let observedPrompt = ''
    let observedHost: string | undefined
    let observedSeq: number | undefined

    const dispatch = async (args: {
      prompt: string
      host: 'claude' | 'codex'
      workflow_run_seq: number
    }): Promise<HostLLMResult> => {
      dispatchCallCount++
      observedPrompt = args.prompt
      observedHost = args.host
      observedSeq = args.workflow_run_seq
      return stubResult
    }

    let resultCallbackCount = 0
    let observedResult: HostLLMResult | null = null

    const wf = createWorkflow({
      id: 'W-host-llm-dispatch-test',
      preconditions: 'always',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [
            {
              kind: 'host-llm-prompt',
              schema_ref: 'prompt/v1',
              locator: 'Update the website tagline to a punchier one.',
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
              authoritative_status: 'authoritative',
            },
          ],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'response_recorded',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const events: EngineEvent[] = []
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-host-llm-dispatch-001',
      workflow_run_seq: 42,
      host_llm_dispatch: dispatch as never, // typeof hostLLMActivity expects asActivity branding
      on_host_llm_result: (r) => {
        resultCallbackCount++
        observedResult = r
      },
      emit: (e) => events.push(e),
    })

    // Dispatch fired exactly once with canonical args
    expect(dispatchCallCount).toBe(1)
    expect(observedPrompt).toBe('Update the website tagline to a punchier one.')
    expect(observedHost).toBe('claude')
    expect(observedSeq).toBe(42)

    // on_host_llm_result fired exactly once with the canned result
    expect(resultCallbackCount).toBe(1)
    expect(observedResult).toBe(stubResult)

    // ExecutionResult is success
    expect(result.status).toBe('success')
    expect(result.steps_completed).toBe(1)
    expect(result.steps_failed).toBe(0)

    // workflow_completed event emitted
    const completed = events.find((e) => e.type === 'workflow_completed')
    expect(completed).toBeDefined()
    if (completed?.type !== 'workflow_completed') throw new Error('type narrow')
    expect(completed.workflow_id).toBe('W-host-llm-dispatch-test')
    expect(completed.execution_id).toBe('E-host-llm-dispatch-001')
  })

  it('default on_host_llm_result is a no-op (does not throw, does not log)', async () => {
    const stubResult: HostLLMResult = {
      response: 'noop',
      host_kind: 'claude',
      host_version: 'Claude Code 2.1.123',
      exit_code: 0,
      invocation_id: 'noop-invocation',
    }
    const dispatch = async () => stubResult

    const wf = createWorkflow({
      id: 'W-host-llm-noop-default',
      preconditions: 'always',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [
            {
              kind: 'host-llm-prompt',
              schema_ref: 'prompt/v1',
              locator: 'whatever',
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
              authoritative_status: 'authoritative',
            },
          ],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'response_recorded',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    // Omit on_host_llm_result → default no-op — must not throw + workflow completes.
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-host-llm-noop-001',
      host_llm_dispatch: dispatch as never,
      emit: () => {},
    })
    expect(result.status).toBe('success')
  })

  it('HostUnavailableError → host_llm_unavailable:<host> failure_reason', async () => {
    const dispatch = async (args: { host: 'claude' | 'codex' }) => {
      // Mirror the production seam: hostLLMActivity throws HostUnavailableError
      // when the host CLI isn't on PATH at dispatch time.
      const { HostUnavailableError } = await import('../../src/engine/host-llm-activity.js')
      throw new HostUnavailableError(args.host)
    }
    const wf = createWorkflow({
      id: 'W-host-llm-unavailable',
      preconditions: 'always',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'codex',
          inputs: [
            {
              kind: 'host-llm-prompt',
              schema_ref: 'prompt/v1',
              locator: 'anything',
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
              authoritative_status: 'authoritative',
            },
          ],
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'n/a',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-host-unavailable-001',
      host_llm_dispatch: dispatch as never,
      emit: () => {},
    })
    expect(result.status).toBe('failed')
    expect(result.reason ?? '').toContain('host_llm_unavailable:codex')
  })

  it('missing prompt → host_llm_invocation_failed:no_prompt', async () => {
    const dispatch = async () => {
      throw new Error('should not be called')
    }
    // Build via raw workflow object — primitive validator forbids empty inputs[]
    // for invoke_host_llm in the strict createWorkflow path; we bypass to test
    // the executor's defensive guard. Cast via unknown to satisfy TS.
    const wf = {
      id: 'W-host-llm-missing-prompt',
      preconditions: 'always',
      step_graph: [
        {
          step_id: 1,
          action: 'invoke_host_llm',
          host: 'claude',
          inputs: [], // empty — no DataRef → no locator
          outputs: [],
          on_failure: 'abort',
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'n/a',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
      on_override_action: 'escalate',
      reuse_tag: null,
      return_contract: null,
      modifies_sutra: false,
      custody_owner: null,
      extension_ref: null,
      autonomy_level: 'manual',
      expects_response_from: null,
    } as unknown as Parameters<typeof executeWorkflow>[0]['workflow']

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-no-prompt',
      host_llm_dispatch: dispatch as never,
      emit: () => {},
    })
    expect(result.status).toBe('failed')
    expect(result.reason ?? '').toContain('host_llm_invocation_failed:no_prompt')
  })
})
