/**
 * v1.3.0 Wave 1 — combined coverage for the three Wave-1 items:
 *
 *   #9 (W1.9 — codex W1.9 advisory fold): per-step `timeout_ms` is
 *       1) preserved through createWorkflow → persistWorkflow → loadWorkflow
 *          roundtrip (no field-strip in the construction whitelist), and
 *       2) forwarded to host_llm_dispatch at run time.
 *
 *   #7 (W1.7 — codex W1.7 fold): the `create-workflow` CLI accepts
 *       `invoke_host_llm` step actions, with PER-STEP `--host-N`,
 *       `--prompt-N`, `--timeout-N` flags (1-indexed). Multi-step
 *       workflows can carry different hosts per step.
 *
 *   #8 (W1.8 — codex W1.8 + W3 fold): the new `create-trigger` CLI
 *       subcommand validates `--workflow-id` exists, enforces
 *       `--match-all` XOR `--match-any` for founder_input event-types,
 *       accepts a `--cadence-spec` JSON for cron event-types, and persists
 *       a TriggerSpec with the correct predicate shape.
 */

import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { main } from '../../src/cli/sutra-native.js'
import { createWorkflow } from '../../src/primitives/workflow.js'
import { executeWorkflow } from '../../src/runtime/lite-executor.js'
import {
  loadTrigger,
  loadWorkflow,
  persistWorkflow,
} from '../../src/persistence/user-kit.js'
import type { HostLLMResult } from '../../src/engine/host-llm-activity.js'

interface CliResult {
  code: number
  stdout: string
  stderr: string
}

async function runCli(argv: string[], home: string): Promise<CliResult> {
  let stdout = ''
  let stderr = ''
  const code = await main({
    argv,
    env: { ...process.env, SUTRA_NATIVE_HOME: home, HOME: home },
    stdout: (s) => {
      stdout += s
    },
    stderr: (s) => {
      stderr += s
    },
  })
  return { code, stdout, stderr }
}

// ============================================================================
// #9 — per-step timeout_ms wirework
// ============================================================================

describe('v1.3.0 W1 #9 — WorkflowStep.timeout_ms (codex W1.9 advisory fold)', () => {
  it('createWorkflow preserves timeout_ms on invoke_host_llm step', () => {
    const wf = createWorkflow({
      id: 'W-timeout-roundtrip',
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
              locator: 'hello',
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
              authoritative_status: 'authoritative',
            },
          ],
          outputs: [],
          on_failure: 'abort',
          timeout_ms: 30000,
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'ok',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })
    expect(wf.step_graph[0]!.timeout_ms).toBe(30000)
  })

  it('createWorkflow rejects timeout_ms on a non-invoke_host_llm step', () => {
    expect(() =>
      createWorkflow({
        id: 'W-timeout-bad-action',
        preconditions: 'always',
        step_graph: [
          {
            step_id: 1,
            action: 'wait',
            inputs: [],
            outputs: [],
            on_failure: 'abort',
            timeout_ms: 30000,
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'ok',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      }),
    ).toThrow(/timeout_ms is only permitted when action='invoke_host_llm'/)
  })

  it('createWorkflow rejects non-positive / non-integer timeout_ms', () => {
    const mk = (val: unknown) =>
      createWorkflow({
        id: 'W-timeout-bad-val',
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
                locator: 'x',
                version: '1.0.0',
                mutability: 'immutable',
                retention: 'permanent',
              },
            ],
            outputs: [],
            on_failure: 'abort',
            timeout_ms: val as number,
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'ok',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      })
    expect(() => mk(0)).toThrow(/timeout_ms must be a positive integer/)
    expect(() => mk(-100)).toThrow(/timeout_ms must be a positive integer/)
    expect(() => mk(1.5)).toThrow(/timeout_ms must be a positive integer/)
  })

  it('persistWorkflow → loadWorkflow roundtrip preserves timeout_ms (no field-strip)', () => {
    const HOME = mkdtempSync(join(tmpdir(), 'sutra-w19-roundtrip-'))
    try {
      const wf = createWorkflow({
        id: 'W-timeout-disk',
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
                locator: 'persist me',
                version: '1.0.0',
                mutability: 'immutable',
                retention: 'permanent',
                authoritative_status: 'authoritative',
              },
            ],
            outputs: [],
            on_failure: 'abort',
            timeout_ms: 45000,
          },
        ],
        inputs: [],
        outputs: [],
        state: [],
        postconditions: 'ok',
        failure_policy: 'abort',
        stringency: 'task',
        interfaces_with: [],
      })
      const path = persistWorkflow(wf, { env: { SUTRA_NATIVE_HOME: HOME, HOME } })
      expect(existsSync(path)).toBe(true)
      const reloaded = loadWorkflow('W-timeout-disk', { env: { SUTRA_NATIVE_HOME: HOME, HOME } })
      expect(reloaded).not.toBeNull()
      expect(reloaded!.step_graph[0]!.timeout_ms).toBe(45000)
    } finally {
      rmSync(HOME, { recursive: true, force: true })
    }
  })

  it('lite-executor forwards timeout_ms to host_llm_dispatch', async () => {
    let observedTimeout: number | undefined
    const stubResult: HostLLMResult = {
      response: 'ok',
      host_kind: 'claude',
      host_version: 'Claude Code 2.1.123',
      exit_code: 0,
      invocation_id: 'fixed-w19',
    }
    const dispatch = async (args: {
      prompt: string
      host: 'claude' | 'codex'
      workflow_run_seq: number
      timeout_ms?: number
    }): Promise<HostLLMResult> => {
      observedTimeout = args.timeout_ms
      return stubResult
    }

    const wf = createWorkflow({
      id: 'W-timeout-forward',
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
              locator: 'do thing',
              version: '1.0.0',
              mutability: 'immutable',
              retention: 'permanent',
              authoritative_status: 'authoritative',
            },
          ],
          outputs: [],
          on_failure: 'abort',
          timeout_ms: 120000,
        },
      ],
      inputs: [],
      outputs: [],
      state: [],
      postconditions: 'ok',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w19-forward',
      host_llm_dispatch: dispatch as never,
      emit: () => {},
    })
    expect(result.status).toBe('success')
    expect(observedTimeout).toBe(120000)
  })

  it('lite-executor omits timeout_ms when not set (host-llm default applies)', async () => {
    let argHasTimeoutKey = true
    const stubResult: HostLLMResult = {
      response: 'ok',
      host_kind: 'claude',
      host_version: 'Claude Code 2.1.123',
      exit_code: 0,
      invocation_id: 'fixed-w19-omit',
    }
    const dispatch = async (args: {
      prompt: string
      host: 'claude' | 'codex'
      workflow_run_seq: number
      timeout_ms?: number
    }): Promise<HostLLMResult> => {
      argHasTimeoutKey = Object.prototype.hasOwnProperty.call(args, 'timeout_ms')
      return stubResult
    }

    const wf = createWorkflow({
      id: 'W-timeout-omitted',
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
              locator: 'no timeout',
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
      postconditions: 'ok',
      failure_policy: 'abort',
      stringency: 'task',
      interfaces_with: [],
    })

    const result = await executeWorkflow({
      workflow: wf,
      execution_id: 'E-w19-omit',
      host_llm_dispatch: dispatch as never,
      emit: () => {},
    })
    expect(result.status).toBe('success')
    expect(argHasTimeoutKey).toBe(false)
  })
})

// ============================================================================
// #7 — CLI invoke_host_llm step scaffolding (per-step --host-N)
// ============================================================================

describe('v1.3.0 W1 #7 — create-workflow CLI invoke_host_llm support (codex W1.7 fold)', () => {
  let HOME: string

  beforeAll(() => {
    HOME = mkdtempSync(join(tmpdir(), 'sutra-w17-cli-'))
  })
  afterAll(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('persists timeout_ms when --timeout-1 supplied alongside --host-1 / --prompt-1', async () => {
    const r = await runCli(
      [
        'create-workflow',
        '--id',
        'W-cli-host',
        '--steps',
        'invoke_host_llm,wait',
        '--host-1',
        'claude',
        '--prompt-1',
        'hello',
        '--timeout-1',
        '30000',
      ],
      HOME,
    )
    expect(r.code).toBe(0)
    const path = join(HOME, 'user-kit', 'workflows', 'W-cli-host.json')
    expect(existsSync(path)).toBe(true)
    const persisted = JSON.parse(readFileSync(path, 'utf8'))
    expect(persisted.step_graph[0].action).toBe('invoke_host_llm')
    expect(persisted.step_graph[0].host).toBe('claude')
    expect(persisted.step_graph[0].timeout_ms).toBe(30000)
    expect(persisted.step_graph[0].inputs[0].locator).toBe('hello')
    expect(persisted.step_graph[1].action).toBe('wait')
  })

  it('multi-step workflow accepts different hosts per step', async () => {
    const r = await runCli(
      [
        'create-workflow',
        '--id',
        'W-cli-multi-host',
        '--steps',
        'invoke_host_llm,invoke_host_llm',
        '--host-1',
        'claude',
        '--prompt-1',
        'first',
        '--host-2',
        'codex',
        '--prompt-2',
        'second',
      ],
      HOME,
    )
    expect(r.code).toBe(0)
    const path = join(HOME, 'user-kit', 'workflows', 'W-cli-multi-host.json')
    const persisted = JSON.parse(readFileSync(path, 'utf8'))
    expect(persisted.step_graph[0].host).toBe('claude')
    expect(persisted.step_graph[1].host).toBe('codex')
    expect(persisted.step_graph[0].inputs[0].locator).toBe('first')
    expect(persisted.step_graph[1].inputs[0].locator).toBe('second')
  })

  it('rejects invoke_host_llm without --host-N', async () => {
    const r = await runCli(
      [
        'create-workflow',
        '--id',
        'W-cli-missing-host',
        '--steps',
        'invoke_host_llm',
        '--prompt-1',
        'hi',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/--host-1 is required/)
  })

  it('rejects invoke_host_llm without --prompt-N', async () => {
    const r = await runCli(
      [
        'create-workflow',
        '--id',
        'W-cli-missing-prompt',
        '--steps',
        'invoke_host_llm',
        '--host-1',
        'claude',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/--prompt-1 is required/)
  })

  it('rejects invalid --host-N value', async () => {
    const r = await runCli(
      [
        'create-workflow',
        '--id',
        'W-cli-bad-host',
        '--steps',
        'invoke_host_llm',
        '--host-1',
        'gpt',
        '--prompt-1',
        'x',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/host/)
  })
})

// ============================================================================
// #8 — create-trigger CLI subcommand
// ============================================================================

describe('v1.3.0 W1 #8 — create-trigger CLI (codex W1.8 + W3 fold)', () => {
  let HOME: string

  beforeAll(async () => {
    HOME = mkdtempSync(join(tmpdir(), 'sutra-w18-trigger-'))
    // Pre-create a workflow that triggers can target.
    await runCli(
      ['create-workflow', '--id', 'W-target', '--steps', 'wait,terminate'],
      HOME,
    )
  })
  afterAll(() => {
    if (HOME && existsSync(HOME)) rmSync(HOME, { recursive: true, force: true })
  })

  it('errors exit 2 when --workflow-id does not exist', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-bogus',
        '--workflow-id',
        'W-nonexistent',
        '--event-type',
        'founder_input',
        '--match-any',
        'foo',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/not found/)
  })

  it('errors exit 2 when both --match-all and --match-any are set', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-both',
        '--workflow-id',
        'W-target',
        '--event-type',
        'founder_input',
        '--match-all',
        'a,b',
        '--match-any',
        'c,d',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/mutually exclusive/)
  })

  it('errors exit 2 when neither match flag set for founder_input', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-none',
        '--workflow-id',
        'W-target',
        '--event-type',
        'founder_input',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/--match-all or --match-any/)
  })

  it('happy path: --match-all → AND-of-contains predicate', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-all',
        '--workflow-id',
        'W-target',
        '--event-type',
        'founder_input',
        '--match-all',
        'add,department',
      ],
      HOME,
    )
    expect(r.code).toBe(0)
    const t = loadTrigger('T-all', { env: { SUTRA_NATIVE_HOME: HOME, HOME } })
    expect(t).not.toBeNull()
    expect(t!.event_type).toBe('founder_input')
    expect(t!.target_workflow).toBe('W-target')
    expect(t!.route_predicate.type).toBe('and')
    if (t!.route_predicate.type === 'and') {
      expect(t!.route_predicate.clauses).toHaveLength(2)
      const c0 = t!.route_predicate.clauses[0]
      const c1 = t!.route_predicate.clauses[1]
      expect(c0.type).toBe('contains')
      expect(c1.type).toBe('contains')
      if (c0.type === 'contains') expect(c0.value).toBe('add')
      if (c1.type === 'contains') expect(c1.value).toBe('department')
    }
  })

  it('happy path: --match-any → OR-of-contains predicate', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-any',
        '--workflow-id',
        'W-target',
        '--event-type',
        'founder_input',
        '--match-any',
        'foo,bar',
      ],
      HOME,
    )
    expect(r.code).toBe(0)
    const t = loadTrigger('T-any', { env: { SUTRA_NATIVE_HOME: HOME, HOME } })
    expect(t).not.toBeNull()
    expect(t!.route_predicate.type).toBe('or')
  })

  it('cron event-type: stores cadence_spec + always_true predicate', async () => {
    const cadenceJson = JSON.stringify({ kind: 'every_n_hours', n: 6 })
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-cron',
        '--workflow-id',
        'W-target',
        '--event-type',
        'cron',
        '--cadence-spec',
        cadenceJson,
      ],
      HOME,
    )
    expect(r.code).toBe(0)
    const t = loadTrigger('T-cron', { env: { SUTRA_NATIVE_HOME: HOME, HOME } })
    expect(t).not.toBeNull()
    expect(t!.event_type).toBe('cron')
    expect(t!.route_predicate.type).toBe('always_true')
    expect(t!.cadence_spec).toEqual({ kind: 'every_n_hours', n: 6 })
  })

  it('errors exit 2 on invalid --event-type', async () => {
    const r = await runCli(
      [
        'create-trigger',
        '--id',
        'T-bad-evt',
        '--workflow-id',
        'W-target',
        '--event-type',
        'banana',
        '--match-any',
        'x',
      ],
      HOME,
    )
    expect(r.code).toBe(2)
    expect(r.stderr).toMatch(/event-type/)
  })
})
