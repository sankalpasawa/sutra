/**
 * Unit tests for connectors/lib/composio-adapter.ts
 *
 * Frozen contract: LLD §2.7 + §4 (forbidden-API row) + §5 (justification:
 *   "Composio surface intentionally narrow — guard tests assert no plan/
 *    discover surface ever leaks; D38 control-plane-capture critique
 *    materially mitigated").
 *
 * Test plan: §3.6 + §4 row 4 ("Adapter guard: assert no plan/discover/
 *   workbench/session-memory APIs touched") of
 *   holding/research/2026-04-30-connectors-test-plan.md.
 *
 * iter 3 — TDD RED: every test fails until iter 5d implements
 *   composio-adapter.ts (current stub throws 'not implemented (TDD red
 *   phase)' on construction + call). The GUARD INVARIANT cases are
 *   load-bearing: they BLOCK SHIP if violated. Per codex review
 *   2026-04-30 row 4, no override permitted.
 *
 * Mock strategy: Proxy-based ComposioClient that records every property
 *   access. Lets us assert post-call() that no forbidden surface was
 *   touched, regardless of how the adapter is implemented internally.
 */

import { describe, it, expect, vi } from 'vitest';

import {
  ComposioAdapter,
  FORBIDDEN_COMPOSIO_APIS,
} from '../../lib/composio-adapter.js';
import { ForbiddenComposioApiError } from '../../lib/errors.js';
import type { ComposioClient } from '../../lib/types.js';

// ---------------------------------------------------------------------------
// Proxy-based recording mock
//
// recordingClient() returns:
//   - client:   a ComposioClient that delegates to the supplied impl, but
//               records every property access (read OR call) on `accesses`.
//   - accesses: Set<string> of property names touched during the test.
//
// Forbidden-API methods (plan/discover/workbench/etc) are NOT defined on
// impl by default; if the adapter touches them, the proxy still records
// the access — failing the guard invariants.
// ---------------------------------------------------------------------------

interface RecordingMock {
  readonly client: ComposioClient;
  readonly accesses: Set<string>;
  readonly executeToolMock: ReturnType<typeof vi.fn>;
  readonly authenticateMock: ReturnType<typeof vi.fn>;
  readonly isAuthenticatedMock: ReturnType<typeof vi.fn>;
}

function recordingClient(opts: {
  isAuthenticated?: boolean;
  executeToolImpl?: (
    toolkit: string,
    tool: string,
    args: Record<string, unknown>,
  ) => Promise<unknown>;
  extraMethods?: Readonly<Record<string, (...args: unknown[]) => unknown>>;
} = {}): RecordingMock {
  const accesses = new Set<string>();

  const executeToolMock = vi.fn(
    opts.executeToolImpl ??
      (async (
        _toolkit: string,
        _tool: string,
        _args: Record<string, unknown>,
      ) => ({ ok: true })),
  );
  const authenticateMock = vi.fn(async (_toolkit: string, _token: string) => {
    /* no-op */
  });
  const isAuthenticatedMock = vi.fn(
    async (_toolkit: string) => opts.isAuthenticated ?? true,
  );

  const base: Record<string, unknown> = {
    authenticate: authenticateMock,
    executeTool: executeToolMock,
    isAuthenticated: isAuthenticatedMock,
    ...(opts.extraMethods ?? {}),
  };

  const proxied = new Proxy(base, {
    get(target, prop, receiver) {
      if (typeof prop === 'string') accesses.add(prop);
      return Reflect.get(target, prop, receiver);
    },
    has(target, prop) {
      if (typeof prop === 'string') accesses.add(prop);
      return Reflect.has(target, prop);
    },
  }) as unknown as ComposioClient;

  return {
    client: proxied,
    accesses,
    executeToolMock,
    authenticateMock,
    isAuthenticatedMock,
  };
}

// ---------------------------------------------------------------------------
// HAPPY PATH
// ---------------------------------------------------------------------------

describe('ComposioAdapter — happy path', () => {
  it('constructor accepts a ComposioClient mock implementing the narrow surface', () => {
    const { client } = recordingClient();
    // Should not throw once implemented. Currently throws (red phase).
    expect(() => new ComposioAdapter(client)).not.toThrow();
  });

  it('call(toolkit, tool, args) delegates to client.executeTool with same arguments verbatim', async () => {
    const { client, executeToolMock } = recordingClient();
    const adapter = new ComposioAdapter(client);
    const args = { channel: '#dayflow-eng', text: 'hello' };

    await adapter.call('slack', 'sendMessage', args);

    expect(executeToolMock).toHaveBeenCalledTimes(1);
    expect(executeToolMock).toHaveBeenCalledWith('slack', 'sendMessage', args);
  });

  it('call() returns the unmodified value resolved by client.executeTool', async () => {
    const sentinel = { messageId: 'M_123', ts: 1730000000 };
    const { client } = recordingClient({
      executeToolImpl: async () => sentinel,
    });
    const adapter = new ComposioAdapter(client);

    const result = await adapter.call('slack', 'sendMessage', {
      channel: '#x',
      text: 'y',
    });

    expect(result).toBe(sentinel);
  });

  it('call() awaits client.authenticate when isAuthenticated returns false (lazy auth)', async () => {
    const { client, authenticateMock, isAuthenticatedMock, executeToolMock } =
      recordingClient({ isAuthenticated: false });
    const adapter = new ComposioAdapter(client);

    await adapter.call('slack', 'sendMessage', { channel: '#x', text: 'y' });

    expect(isAuthenticatedMock).toHaveBeenCalledWith('slack');
    expect(authenticateMock).toHaveBeenCalledTimes(1);
    // Auth must complete before executeTool fires.
    expect(authenticateMock.mock.invocationCallOrder[0]).toBeLessThan(
      executeToolMock.mock.invocationCallOrder[0]!,
    );
  });
});

// ---------------------------------------------------------------------------
// GUARD INVARIANTS — LOAD-BEARING
//
// These cases are why this file exists. They satisfy codex
// 2026-04-30-connectors-build-plan.md §"Required test categories" row 4
// ("Adapter guard"). Failure here BLOCKS SHIP. No CODEX_DIRECTIVE_ACK
// override; surface blocks.
// ---------------------------------------------------------------------------

describe('ComposioAdapter — GUARD INVARIANTS (load-bearing, gates ship)', () => {
  it('FORBIDDEN_COMPOSIO_APIS contains the codex-required surface (plan, discover, workbench, session-memory, autoExecute, multiExecute)', () => {
    const required = [
      'plan',
      'discover',
      'workbench',
      'session-memory',
      'autoExecute',
      'multiExecute',
    ];
    for (const api of required) {
      expect(FORBIDDEN_COMPOSIO_APIS).toContain(api);
    }
  });

  it('during normal call() flow, adapter does NOT access ANY property in FORBIDDEN_COMPOSIO_APIS on the client', async () => {
    const { client, accesses } = recordingClient();
    const adapter = new ComposioAdapter(client);

    await adapter.call('slack', 'sendMessage', { channel: '#x', text: 'y' });

    for (const api of FORBIDDEN_COMPOSIO_APIS) {
      expect(
        accesses.has(api),
        `adapter touched forbidden api '${api}' — surface leakage; codex §4 row 4 violation`,
      ).toBe(false);
    }
  });

  it('if client exposes a future Composio.plan-like method, adapter does NOT invoke it during normal call() flow', async () => {
    const planSpy = vi.fn(() => {
      throw new Error('plan() must NEVER be invoked by the adapter');
    });
    const { client, accesses } = recordingClient({
      extraMethods: {
        plan: planSpy as unknown as (...args: unknown[]) => unknown,
      },
    });
    const adapter = new ComposioAdapter(client);

    await adapter.call('slack', 'sendMessage', { channel: '#x', text: 'y' });

    expect(planSpy).not.toHaveBeenCalled();
    expect(accesses.has('plan')).toBe(false);
  });

  it('ForbiddenComposioApiError carries .api field naming the offending api', () => {
    const err = new ForbiddenComposioApiError('plan');
    expect(err).toBeInstanceOf(ForbiddenComposioApiError);
    expect(err.api).toBe('plan');
    expect(err.code).toBe('forbidden-composio-api');
  });

  it('constructor rejects a client missing required method: authenticate (narrow surface contract)', () => {
    const broken = {
      executeTool: vi.fn(),
      isAuthenticated: vi.fn(),
    } as unknown as ComposioClient;
    expect(() => new ComposioAdapter(broken)).toThrow();
  });

  it('constructor rejects a client missing required method: executeTool (narrow surface contract)', () => {
    const broken = {
      authenticate: vi.fn(),
      isAuthenticated: vi.fn(),
    } as unknown as ComposioClient;
    expect(() => new ComposioAdapter(broken)).toThrow();
  });

  it('constructor rejects a client missing required method: isAuthenticated (narrow surface contract)', () => {
    const broken = {
      authenticate: vi.fn(),
      executeTool: vi.fn(),
    } as unknown as ComposioClient;
    expect(() => new ComposioAdapter(broken)).toThrow();
  });
});

// ---------------------------------------------------------------------------
// ERROR PATHS
// ---------------------------------------------------------------------------

describe('ComposioAdapter — error paths', () => {
  it('call() propagates client.executeTool rejection unchanged (network errors bubble)', async () => {
    const networkErr = new Error('ECONNRESET');
    const { client } = recordingClient({
      executeToolImpl: async () => {
        throw networkErr;
      },
    });
    const adapter = new ComposioAdapter(client);

    await expect(
      adapter.call('slack', 'sendMessage', { channel: '#x', text: 'y' }),
    ).rejects.toBe(networkErr);
  });

  it('call() never logs args (audit owns logging; adapter is dumb)', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});

    try {
      const { client } = recordingClient();
      const adapter = new ComposioAdapter(client);
      const sensitiveArgs = {
        channel: '#priv',
        text: 'TEST_TOKEN_xoxb_should_never_be_logged',
        oauthToken: 'TEST_TOKEN_should_never_be_logged',
      };

      await adapter.call('slack', 'sendMessage', sensitiveArgs);

      const allCalls = [
        ...logSpy.mock.calls,
        ...errSpy.mock.calls,
        ...warnSpy.mock.calls,
        ...infoSpy.mock.calls,
        ...debugSpy.mock.calls,
      ];
      const haystack = JSON.stringify(allCalls);
      expect(haystack).not.toContain('TEST_TOKEN_xoxb_should_never_be_logged');
      expect(haystack).not.toContain('TEST_TOKEN_should_never_be_logged');
    } finally {
      logSpy.mockRestore();
      errSpy.mockRestore();
      warnSpy.mockRestore();
      infoSpy.mockRestore();
      debugSpy.mockRestore();
    }
  });
});
