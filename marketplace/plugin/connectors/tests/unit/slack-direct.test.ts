/**
 * Unit tests for connectors/lib/backends/slack-direct.ts
 *
 * Validates that SlackDirectClient:
 *   - implements the frozen ComposioClient narrow surface
 *     (authenticate / executeTool / isAuthenticated)
 *   - routes the three documented tools to the correct Slack Web API
 *     endpoints with the correct body shape and Authorization header
 *   - throws on Slack `ok=false` responses with the slack error code
 *   - never opens a network connection to anywhere outside slack.com/api/<method>
 *
 * All network is mocked via `vi.stubGlobal('fetch', vi.fn())`. No real
 * HTTP, no filesystem (~/.sutra / ~/.claude), no override flags.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  SlackDirectClient,
  type SlackCredential,
} from '../../lib/backends/slack-direct.js';

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

type AnyMock = ReturnType<typeof vi.fn>;

interface FetchMock {
  readonly fetchFn: AnyMock;
}

/**
 * Install a fetch mock that returns `responseJson` for every call.
 * Tests that need per-call shaping can call .mockResolvedValueOnce on the
 * returned mock fn directly.
 */
function installFetchMock(responseJson: unknown): FetchMock {
  const fetchFn: AnyMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => responseJson,
  })) as AnyMock;
  vi.stubGlobal('fetch', fetchFn);
  return { fetchFn };
}

function makeClient(opts: {
  initialCred?: SlackCredential | null;
} = {}): {
  client: SlackDirectClient;
  loader: AnyMock;
  saver: AnyMock;
} {
  const initial = opts.initialCred === undefined
    ? ({ type: 'slack-bot', token: 'xoxb-test' } satisfies SlackCredential)
    : opts.initialCred;
  const loader: AnyMock = vi.fn(async () => initial) as AnyMock;
  const saver: AnyMock = vi.fn(async (_cred: SlackCredential) => {
    /* no-op */
  }) as AnyMock;
  const client = new SlackDirectClient(
    loader as unknown as () => Promise<SlackCredential | null>,
    saver as unknown as (cred: SlackCredential) => Promise<void>,
  );
  return { client, loader, saver };
}

// Helper: extract the (url, init) pair from a captured fetch call.
function callArgs(fetchFn: AnyMock, idx = 0): {
  url: string;
  init: RequestInit;
} {
  const call = fetchFn.mock.calls[idx];
  if (!call) throw new Error(`no fetch call at index ${idx}`);
  return { url: String(call[0]), init: call[1] as RequestInit };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// authenticate()
// ---------------------------------------------------------------------------

describe('SlackDirectClient — authenticate()', () => {
  it('on auth.test ok=true, calls saver with the validated credential', async () => {
    const { fetchFn } = installFetchMock({ ok: true, user_id: 'U123' });
    const { client, saver } = makeClient({ initialCred: null });

    await client.authenticate('slack', 'xoxb-test');

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const { url, init } = callArgs(fetchFn);
    expect(url).toBe('https://slack.com/api/auth.test');
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer xoxb-test');

    expect(saver).toHaveBeenCalledTimes(1);
    expect(saver).toHaveBeenCalledWith({ type: 'slack-bot', token: 'xoxb-test' });
  });

  it('on auth.test ok=false, throws with the slack error code AND does NOT save', async () => {
    installFetchMock({ ok: false, error: 'invalid_auth' });
    const { client, saver } = makeClient({ initialCred: null });

    await expect(client.authenticate('slack', 'xoxb-bad')).rejects.toThrow(
      /invalid_auth/,
    );
    expect(saver).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// executeTool() — happy paths
// ---------------------------------------------------------------------------

describe('SlackDirectClient — executeTool() routing', () => {
  it("'read-channel' POSTs to conversations.history with channel + default limit", async () => {
    const { fetchFn } = installFetchMock({ ok: true, messages: [] });
    const { client } = makeClient();

    await client.executeTool('slack', 'read-channel', { channel: '#test' });

    expect(fetchFn).toHaveBeenCalledTimes(1);
    const { url, init } = callArgs(fetchFn);
    expect(url).toBe('https://slack.com/api/conversations.history');
    expect(init.method).toBe('POST');
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ channel: '#test', limit: 50 });
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer xoxb-test');
    expect(headers['Content-Type']).toBe('application/json');
  });

  it("'read-channel' respects an explicit limit override", async () => {
    const { fetchFn } = installFetchMock({ ok: true, messages: [] });
    const { client } = makeClient();

    await client.executeTool('slack', 'read-channel', {
      channel: '#test',
      limit: 5,
    });

    const { init } = callArgs(fetchFn);
    const body = JSON.parse(String(init.body));
    expect(body.limit).toBe(5);
  });

  it("'post-message' POSTs to chat.postMessage with channel + text and forwards thread_ts when present", async () => {
    const { fetchFn } = installFetchMock({ ok: true, ts: '1730000000.000100' });
    const { client } = makeClient();

    await client.executeTool('slack', 'post-message', {
      channel: '#dayflow-eng',
      text: 'hello world',
      thread_ts: '1700000000.000100',
    });

    const { url, init } = callArgs(fetchFn);
    expect(url).toBe('https://slack.com/api/chat.postMessage');
    expect(init.method).toBe('POST');
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      channel: '#dayflow-eng',
      text: 'hello world',
      thread_ts: '1700000000.000100',
    });
  });

  it("'post-message' omits thread_ts when not provided", async () => {
    const { fetchFn } = installFetchMock({ ok: true, ts: 't1' });
    const { client } = makeClient();

    await client.executeTool('slack', 'post-message', {
      channel: '#x',
      text: 'y',
    });

    const { init } = callArgs(fetchFn);
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ channel: '#x', text: 'y' });
    expect('thread_ts' in body).toBe(false);
  });

  it("'get-user' POSTs to users.info with user id", async () => {
    const { fetchFn } = installFetchMock({ ok: true, user: { id: 'U1' } });
    const { client } = makeClient();

    await client.executeTool('slack', 'get-user', { user: 'U1' });

    const { url, init } = callArgs(fetchFn);
    expect(url).toBe('https://slack.com/api/users.info');
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ user: 'U1' });
  });

  it('unknown tool throws "unsupported slack tool: <tool>" without firing fetch', async () => {
    const { fetchFn } = installFetchMock({ ok: true });
    const { client } = makeClient();

    await expect(
      client.executeTool('slack', 'plan' as string, {}),
    ).rejects.toThrow(/unsupported slack tool: plan/);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it('Slack ok=false response surfaces as Error(<error code>)', async () => {
    installFetchMock({ ok: false, error: 'channel_not_found' });
    const { client } = makeClient();

    await expect(
      client.executeTool('slack', 'read-channel', { channel: '#missing' }),
    ).rejects.toThrow(/channel_not_found/);
  });
});

// ---------------------------------------------------------------------------
// isAuthenticated()
// ---------------------------------------------------------------------------

describe('SlackDirectClient — isAuthenticated()', () => {
  it('returns true when auth.test ok=true', async () => {
    installFetchMock({ ok: true, user_id: 'U123' });
    const { client } = makeClient();

    await expect(client.isAuthenticated('slack')).resolves.toBe(true);
  });

  it('returns false when auth.test ok=false', async () => {
    installFetchMock({ ok: false, error: 'token_revoked' });
    const { client } = makeClient();

    await expect(client.isAuthenticated('slack')).resolves.toBe(false);
  });

  it('returns false when no credential is loaded (and never opens a connection)', async () => {
    const { fetchFn } = installFetchMock({ ok: true });
    const { client } = makeClient({ initialCred: null });

    await expect(client.isAuthenticated('slack')).resolves.toBe(false);
    expect(fetchFn).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Cross-cutting invariants — load-bearing
// ---------------------------------------------------------------------------

describe('SlackDirectClient — invariants', () => {
  it('every fetch URL is on https://slack.com/api/<method> (no third-party hosts)', async () => {
    const { fetchFn } = installFetchMock({ ok: true });
    const { client } = makeClient();

    await client.executeTool('slack', 'read-channel', { channel: '#a' });
    await client.executeTool('slack', 'post-message', {
      channel: '#a',
      text: 'b',
    });
    await client.executeTool('slack', 'get-user', { user: 'U1' });
    await client.isAuthenticated('slack');

    for (const call of fetchFn.mock.calls) {
      const url = String(call[0]);
      expect(url.startsWith('https://slack.com/api/')).toBe(true);
    }
  });

  it('every request carries Authorization: Bearer <token> from the loaded credential', async () => {
    const { fetchFn } = installFetchMock({ ok: true });
    const { client } = makeClient();

    await client.executeTool('slack', 'read-channel', { channel: '#a' });
    await client.executeTool('slack', 'post-message', {
      channel: '#a',
      text: 'b',
    });

    for (const call of fetchFn.mock.calls) {
      const init = call[1] as RequestInit;
      const headers = init.headers as Record<string, string>;
      expect(headers['Authorization']).toBe('Bearer xoxb-test');
    }
  });
});
