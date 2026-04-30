/**
 * host-llm-activity contract tests — M8 Group BB (T-117..T-119, T-122).
 *
 * Asserts:
 *  - invokeHostLLM (raw, internal) happy path for both hosts via stub
 *  - hostLLMActivity (Activity-wrapped public) preserves F-12 boundary
 *  - HostUnavailableError when availability override marks host missing
 *  - Subprocess failure → wrapped Error with exit_code in message
 *  - Claude path uses --bare --print with prompt as final positional arg
 *  - Codex path passes prompt via stdin (input field)
 *  - HostLLMResult shape includes host_kind + host_version + invocation_id
 *
 * Test seams (NOT in public barrel):
 *  - __setHostAvailabilityForTest / __resetHostAvailabilityForTest
 *  - __setExecFileSyncStubForTest / __resetExecFileSyncStubForTest
 *  - __deriveInvocationIdForTest
 *
 * Spec source:
 *  - holding/plans/native-v1.0/M8-hooks-otel-mcp.md Group BB
 *  - .enforcement/codex-reviews/2026-04-30-architecture-pivot-{review,rereview}.md
 */

import { describe, it, expect, afterEach } from 'vitest'
import {
  hostLLMActivity,
  invokeHostLLM,
  HostUnavailableError,
  __setHostAvailabilityForTest,
  __resetHostAvailabilityForTest,
  __setExecFileSyncStubForTest,
  __resetExecFileSyncStubForTest,
  __setInvokeHostLLMF12ProbeForTest,
  __resetInvokeHostLLMF12ProbeForTest,
  __deriveInvocationIdForTest,
  type ExecFileSyncStub,
} from '../../../src/engine/host-llm-activity.js'

// Stable availability map: both hosts present with deterministic versions
// so invocation_id stays stable across cases.
function setBothAvailable(): void {
  const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
  map.set('claude', { available: true, version: '2.1.123 (Claude Code)' })
  map.set('codex', { available: true, version: 'codex-cli 0.118.0' })
  __setHostAvailabilityForTest(map)
}

afterEach(() => {
  __resetHostAvailabilityForTest()
  __resetExecFileSyncStubForTest()
  __resetInvokeHostLLMF12ProbeForTest()
})

describe('invokeHostLLM — Claude path (T-117)', () => {
  it('happy path: dispatches `claude --bare --print <prompt>` and returns response', () => {
    setBothAvailable()
    let capturedFile: string | null = null
    let capturedArgs: string[] | null = null
    const stub: ExecFileSyncStub = (file, args, _opts) => {
      capturedFile = file
      capturedArgs = [...args]
      return 'claude-response-text'
    }
    __setExecFileSyncStubForTest(stub)

    const result = invokeHostLLM({
      prompt: 'hello-world',
      host: 'claude',
      workflow_run_seq: 1,
    })
    expect(capturedFile).toBe('claude')
    expect(capturedArgs).toEqual(['--bare', '--print', 'hello-world'])
    expect(result.response).toBe('claude-response-text')
    expect(result.host_kind).toBe('claude')
    expect(result.host_version).toBe('2.1.123 (Claude Code)')
    expect(result.exit_code).toBe(0)
    expect(result.invocation_id).toMatch(/^[a-f0-9]{32}$/)
  })

  it('--bare flag is REQUIRED (codex pivot review fold #3 — recursion safety)', () => {
    setBothAvailable()
    let observedArgs: string[] = []
    const stub: ExecFileSyncStub = (_file, args, _opts) => {
      observedArgs = [...args]
      return ''
    }
    __setExecFileSyncStubForTest(stub)
    invokeHostLLM({ prompt: 'p', host: 'claude', workflow_run_seq: 1 })
    // --bare MUST be the first arg per the recursion-safety contract.
    expect(observedArgs[0]).toBe('--bare')
    expect(observedArgs).toContain('--print')
  })
})

describe('invokeHostLLM — codex path (T-117)', () => {
  it('happy path: dispatches `codex exec --skip-git-repo-check` with prompt via stdin', () => {
    setBothAvailable()
    let capturedFile: string | null = null
    let capturedArgs: string[] | null = null
    let capturedStdin: string | undefined
    const stub: ExecFileSyncStub = (file, args, opts) => {
      capturedFile = file
      capturedArgs = [...args]
      capturedStdin = opts.input
      return 'codex-response-text'
    }
    __setExecFileSyncStubForTest(stub)

    const result = invokeHostLLM({
      prompt: 'codex-prompt',
      host: 'codex',
      workflow_run_seq: 7,
    })
    expect(capturedFile).toBe('codex')
    expect(capturedArgs).toEqual(['exec', '--skip-git-repo-check'])
    expect(capturedStdin).toBe('codex-prompt')
    expect(result.response).toBe('codex-response-text')
    expect(result.host_kind).toBe('codex')
    expect(result.host_version).toBe('codex-cli 0.118.0')
  })
})

describe('invokeHostLLM — HostUnavailableError (T-118)', () => {
  it('throws HostUnavailableError when availability says claude not present', () => {
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: false, version: null })
    map.set('codex', { available: true, version: 'codex-cli 0.118.0' })
    __setHostAvailabilityForTest(map)
    expect(() =>
      invokeHostLLM({ prompt: 'x', host: 'claude', workflow_run_seq: 1 }),
    ).toThrow(HostUnavailableError)
  })

  it('throws HostUnavailableError when codex unavailable', () => {
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: true, version: '2.1.123' })
    map.set('codex', { available: false, version: null })
    __setHostAvailabilityForTest(map)
    expect(() =>
      invokeHostLLM({ prompt: 'x', host: 'codex', workflow_run_seq: 1 }),
    ).toThrow(HostUnavailableError)
  })

  it('error message includes install hint per host', () => {
    const map = new Map<'claude' | 'codex', { available: boolean; version: string | null }>()
    map.set('claude', { available: false, version: null })
    map.set('codex', { available: false, version: null })
    __setHostAvailabilityForTest(map)
    try {
      invokeHostLLM({ prompt: 'x', host: 'claude', workflow_run_seq: 1 })
    } catch (e) {
      expect((e as Error).message).toContain('claude.com/code')
    }
    try {
      invokeHostLLM({ prompt: 'x', host: 'codex', workflow_run_seq: 1 })
    } catch (e) {
      expect((e as Error).message).toContain('@openai/codex')
    }
  })
})

describe('invokeHostLLM — subprocess failure handling', () => {
  it('wraps subprocess error with exit_code in message', () => {
    setBothAvailable()
    const stub: ExecFileSyncStub = () => {
      const err: Error & { status?: number } = new Error('command-failed')
      err.status = 7
      throw err
    }
    __setExecFileSyncStubForTest(stub)
    expect(() =>
      invokeHostLLM({ prompt: 'x', host: 'claude', workflow_run_seq: 1 }),
    ).toThrow(/Host LLM 'claude' invocation failed \(exit 7\)/)
  })

  it('defaults exit_code to 1 when subprocess error has no status', () => {
    setBothAvailable()
    const stub: ExecFileSyncStub = () => {
      throw new Error('mystery-error')
    }
    __setExecFileSyncStubForTest(stub)
    expect(() =>
      invokeHostLLM({ prompt: 'x', host: 'claude', workflow_run_seq: 1 }),
    ).toThrow(/exit 1/)
  })
})

describe('invokeHostLLM — invocation_id determinism', () => {
  it('same inputs → same invocation_id', () => {
    const a = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 1)
    const b = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 1)
    expect(a).toBe(b)
    expect(a).toMatch(/^[a-f0-9]{32}$/)
  })

  it('different prompt → different invocation_id', () => {
    const a = __deriveInvocationIdForTest('p1', 'claude', '2.1.123', 1)
    const b = __deriveInvocationIdForTest('p2', 'claude', '2.1.123', 1)
    expect(a).not.toBe(b)
  })

  it('different host_kind → different invocation_id', () => {
    const a = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 1)
    const b = __deriveInvocationIdForTest('p', 'codex', '2.1.123', 1)
    expect(a).not.toBe(b)
  })

  it('different host_version → different invocation_id', () => {
    const a = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 1)
    const b = __deriveInvocationIdForTest('p', 'claude', '2.1.124', 1)
    expect(a).not.toBe(b)
  })

  it('different workflow_run_seq → different invocation_id', () => {
    const a = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 1)
    const b = __deriveInvocationIdForTest('p', 'claude', '2.1.123', 2)
    expect(a).not.toBe(b)
  })
})

// =============================================================================
// F-12 defense-in-depth — codex master review 2026-04-30 P1.1 fold
// =============================================================================

describe('invokeHostLLM — F-12 defense-in-depth (codex M8 P1.1 fold)', () => {
  it('throws F-12 error when called from simulated Workflow context (codex M8 P1.1 fold)', () => {
    // Pin a passing config: hosts available + a stub that WOULD succeed if
    // the F-12 guard were absent. The F-12 trap MUST fire BEFORE the stub
    // runs — that is the load-bearing assertion.
    setBothAvailable()
    let stubInvoked = false
    const stub: ExecFileSyncStub = (_file, _args, _opts) => {
      stubInvoked = true
      return 'should-never-reach-here'
    }
    __setExecFileSyncStubForTest(stub)

    // Simulate Workflow context — the same shape opa-evaluator.evaluate uses.
    __setInvokeHostLLMF12ProbeForTest(() => true)

    expect(() =>
      invokeHostLLM({ prompt: 'p', host: 'claude', workflow_run_seq: 1 }),
    ).toThrow(/F-12/)

    // Defense-in-depth: the subprocess stub MUST NOT have been reached.
    expect(stubInvoked).toBe(false)
  })

  it('does NOT throw F-12 when probe returns false (default non-Workflow context)', () => {
    setBothAvailable()
    __setExecFileSyncStubForTest(() => 'normal-response')
    __setInvokeHostLLMF12ProbeForTest(() => false)

    const result = invokeHostLLM({
      prompt: 'p',
      host: 'claude',
      workflow_run_seq: 1,
    })
    expect(result.response).toBe('normal-response')
  })
})

describe('hostLLMActivity — asActivity-wrapped public API (T-119)', () => {
  it('exists as a function', () => {
    expect(typeof hostLLMActivity).toBe('function')
  })

  it('returns a HostLLMResult when invoked outside Workflow context', async () => {
    setBothAvailable()
    __setExecFileSyncStubForTest(() => 'wrapped-response')
    const r = await hostLLMActivity({
      prompt: 'wrap-test',
      host: 'claude',
      workflow_run_seq: 1,
    })
    expect(r.response).toBe('wrapped-response')
    expect(r.host_kind).toBe('claude')
    expect(r.invocation_id).toMatch(/^[a-f0-9]{32}$/)
  })
})
