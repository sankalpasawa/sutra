/**
 * Unit tests for connectors/lib/backends/gmail-direct.ts
 *
 * Strategy: stub `fetch` globally per test. Each test seeds the fetch
 * mock with one or more responses and asserts:
 *   - URL + method + headers (especially Authorization Bearer)
 *   - body shape (base64url MIME, refresh form-encoded, etc.)
 *   - refresh side-effects (saver called; expiresAt advanced)
 *   - error paths (unsupported tool, second 401, malformed JSON)
 *
 * All requests are mocked — no real network. No ~/.sutra writes:
 * loader/saver are in-memory closures.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  GmailDirectClient,
  type GmailCredential,
} from '../../lib/backends/gmail-direct.js';

// ────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeCred(over: Partial<GmailCredential> = {}): GmailCredential {
  return {
    type: 'gmail-oauth',
    clientId: 'client-id-xyz',
    clientSecret: 'client-secret-xyz',
    accessToken: 'access-aaa',
    refreshToken: 'refresh-rrr',
    expiresAt: Date.now() + 60 * 60 * 1000, // 1h ahead — far from expiry
    ...over,
  };
}

interface Store {
  cred: GmailCredential | null;
  saves: GmailCredential[];
}

function makeStore(initial: GmailCredential | null): {
  store: Store;
  loader: () => Promise<GmailCredential | null>;
  saver: (c: GmailCredential) => Promise<void>;
} {
  const store: Store = { cred: initial, saves: [] };
  return {
    store,
    loader: async () => store.cred,
    saver: async (c) => {
      store.cred = c;
      store.saves.push(c);
    },
  };
}

function lastRequestInit(mock: ReturnType<typeof vi.fn>, callIndex: number): RequestInit {
  const call = mock.mock.calls[callIndex];
  if (!call) throw new Error(`no fetch call at index ${callIndex}`);
  return (call[1] as RequestInit) ?? {};
}

function lastRequestUrl(mock: ReturnType<typeof vi.fn>, callIndex: number): string {
  const call = mock.mock.calls[callIndex];
  if (!call) throw new Error(`no fetch call at index ${callIndex}`);
  return call[0] as string;
}

function authHeader(init: RequestInit): string | undefined {
  const h = init.headers;
  if (!h) return undefined;
  if (h instanceof Headers) return h.get('Authorization') ?? undefined;
  const obj = h as Record<string, string>;
  return obj.Authorization ?? obj.authorization;
}

// ────────────────────────────────────────────────────────────

describe('GmailDirectClient', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // ── authenticate ────────────────────────────────────────────

  it('authenticate parses + saves valid OAuth credential JSON', async () => {
    const { store, loader, saver } = makeStore(null);
    const client = new GmailDirectClient(loader, saver);

    const payload = JSON.stringify({
      client_id: 'cid',
      client_secret: 'csec',
      access_token: 'atok',
      refresh_token: 'rtok',
      expires_at: 1_900_000_000_000,
    });

    await client.authenticate('gmail', payload);

    expect(store.saves).toHaveLength(1);
    expect(store.cred).toEqual({
      type: 'gmail-oauth',
      clientId: 'cid',
      clientSecret: 'csec',
      accessToken: 'atok',
      refreshToken: 'rtok',
      expiresAt: 1_900_000_000_000,
    });
    expect(fetchMock).not.toHaveBeenCalled(); // authenticate does no network
  });

  it('authenticate rejects malformed JSON', async () => {
    const { saver, loader } = makeStore(null);
    const client = new GmailDirectClient(loader, saver);

    await expect(client.authenticate('gmail', '{not-json')).rejects.toThrow(
      /not valid JSON/,
    );
    await expect(
      client.authenticate('gmail', JSON.stringify({ client_id: 'x' })),
    ).rejects.toThrow(/client_secret/);
  });

  // ── executeTool routing ─────────────────────────────────────

  it('executeTool list-messages calls correct URL with Authorization header', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(jsonResponse({ messages: [{ id: 'm1' }] }));

    const result = await client.executeTool('gmail', 'list-messages', {
      q: 'from:foo',
      labelIds: ['INBOX'],
      maxResults: 10,
    });

    expect(result).toEqual({ messages: [{ id: 'm1' }] });
    const url = lastRequestUrl(fetchMock, 0);
    expect(url).toContain('https://gmail.googleapis.com/gmail/v1/users/me/messages?');
    expect(url).toContain('q=from%3Afoo');
    expect(url).toContain('labelIds=INBOX');
    expect(url).toContain('maxResults=10');
    const init = lastRequestInit(fetchMock, 0);
    expect(init.method).toBe('GET');
    expect(authHeader(init)).toBe('Bearer access-aaa');
  });

  it('executeTool get-message calls correct URL with message id', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'm-77', snippet: 'hi' }));

    const out = await client.executeTool('gmail', 'get-message', { id: 'm-77' });

    expect(out).toEqual({ id: 'm-77', snippet: 'hi' });
    expect(lastRequestUrl(fetchMock, 0)).toBe(
      'https://gmail.googleapis.com/gmail/v1/users/me/messages/m-77',
    );
    expect(lastRequestInit(fetchMock, 0).method).toBe('GET');
  });

  it('executeTool send-message POSTs base64url-encoded MIME to send endpoint', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'sent-1' }));

    await client.executeTool('gmail', 'send-message', {
      to: 'a@b.com',
      subject: 'Hello+World',
      body: 'Body line 1\nLine 2',
    });

    const url = lastRequestUrl(fetchMock, 0);
    const init = lastRequestInit(fetchMock, 0);
    expect(url).toBe('https://gmail.googleapis.com/gmail/v1/users/me/messages/send');
    expect(init.method).toBe('POST');
    expect(authHeader(init)).toBe('Bearer access-aaa');

    const sent = JSON.parse(init.body as string) as { raw: string };
    expect(typeof sent.raw).toBe('string');
    // base64url alphabet only — no '+', '/', or '='
    expect(sent.raw).toMatch(/^[A-Za-z0-9\-_]+$/);
    // round-trip decode and verify MIME content
    const b64 = sent.raw.replace(/-/g, '+').replace(/_/g, '/');
    const pad = b64.length % 4 === 0 ? '' : '='.repeat(4 - (b64.length % 4));
    const decoded = Buffer.from(b64 + pad, 'base64').toString('utf8');
    expect(decoded).toContain('To: a@b.com');
    expect(decoded).toContain('Subject: Hello+World');
    expect(decoded).toContain('Body line 1\nLine 2');
    expect(decoded.includes('\r\n\r\n')).toBe(true); // header/body separator
  });

  it('executeTool list-by-label sends correct labelIds query param', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(jsonResponse({ messages: [] }));

    await client.executeTool('gmail', 'list-by-label', {
      label: 'asawa-finance',
      maxResults: 5,
    });

    const url = lastRequestUrl(fetchMock, 0);
    expect(url).toContain('labelIds=asawa-finance');
    expect(url).toContain('maxResults=5');
  });

  it('executeTool unknown-tool throws', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    await expect(
      client.executeTool('gmail', 'plan-something', {}),
    ).rejects.toThrow(/unsupported gmail tool: plan-something/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('executeTool modify-labels POSTs add/remove arrays to /modify', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'm-9', labelIds: ['STARRED'] }));

    await client.executeTool('gmail', 'modify-labels', {
      id: 'm-9',
      addLabelIds: ['STARRED'],
      removeLabelIds: ['UNREAD'],
    });

    const url = lastRequestUrl(fetchMock, 0);
    const init = lastRequestInit(fetchMock, 0);
    expect(url).toBe(
      'https://gmail.googleapis.com/gmail/v1/users/me/messages/m-9/modify',
    );
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      addLabelIds: ['STARRED'],
      removeLabelIds: ['UNREAD'],
    });
  });

  // ── refresh: reactive (401 → refresh → retry) ───────────────

  it('401 response triggers refresh: fetch is called for /token, then retried', async () => {
    const cred = makeCred();
    const { loader, saver, store } = makeStore(cred);
    const client = new GmailDirectClient(loader, saver);

    fetchMock
      // first call: 401 from Gmail
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      // refresh: 200 from token endpoint
      .mockResolvedValueOnce(
        jsonResponse({ access_token: 'access-NEW', expires_in: 3600 }),
      )
      // retry: 200 success
      .mockResolvedValueOnce(jsonResponse({ messages: [{ id: 'm1' }] }));

    const result = await client.executeTool('gmail', 'list-messages', {});

    expect(result).toEqual({ messages: [{ id: 'm1' }] });
    expect(fetchMock).toHaveBeenCalledTimes(3);

    // call 0 → Gmail /messages with old token
    expect(authHeader(lastRequestInit(fetchMock, 0))).toBe('Bearer access-aaa');

    // call 1 → token endpoint, x-www-form-urlencoded
    expect(lastRequestUrl(fetchMock, 1)).toBe('https://oauth2.googleapis.com/token');
    const refreshInit = lastRequestInit(fetchMock, 1);
    expect(refreshInit.method).toBe('POST');
    const headers = refreshInit.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/x-www-form-urlencoded');
    const form = new URLSearchParams(refreshInit.body as string);
    expect(form.get('grant_type')).toBe('refresh_token');
    expect(form.get('client_id')).toBe('client-id-xyz');
    expect(form.get('client_secret')).toBe('client-secret-xyz');
    expect(form.get('refresh_token')).toBe('refresh-rrr');

    // call 2 → Gmail retry with NEW token
    expect(authHeader(lastRequestInit(fetchMock, 2))).toBe('Bearer access-NEW');

    // saver was called — store has new cred
    expect(store.saves).toHaveLength(1);
    expect(store.cred?.accessToken).toBe('access-NEW');
  });

  it('after refresh, expiresAt is updated and saver is called', async () => {
    const cred = makeCred();
    const { loader, saver, store } = makeStore(cred);
    const client = new GmailDirectClient(loader, saver);

    fetchMock
      .mockResolvedValueOnce(new Response('', { status: 401 }))
      .mockResolvedValueOnce(
        jsonResponse({ access_token: 'access-NEW', expires_in: 1800 }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    const before = Date.now();
    await client.executeTool('gmail', 'get-message', { id: 'abc' });
    const after = Date.now();

    expect(store.saves).toHaveLength(1);
    const saved = store.saves[0]!;
    expect(saved.accessToken).toBe('access-NEW');
    // expiresAt should be roughly Date.now() + 1800*1000
    expect(saved.expiresAt).toBeGreaterThanOrEqual(before + 1800 * 1000 - 1000);
    expect(saved.expiresAt).toBeLessThanOrEqual(after + 1800 * 1000 + 1000);
    // refreshToken preserved
    expect(saved.refreshToken).toBe('refresh-rrr');
  });

  it('second 401 (refresh failed) throws without infinite loop', async () => {
    const cred = makeCred();
    const { loader, saver } = makeStore(cred);
    const client = new GmailDirectClient(loader, saver);

    fetchMock
      .mockResolvedValueOnce(new Response('', { status: 401 })) // first Gmail call
      .mockResolvedValueOnce(
        jsonResponse({ access_token: 'access-NEW', expires_in: 3600 }),
      ) // refresh ok
      .mockResolvedValueOnce(new Response('', { status: 401 })); // retry still 401

    await expect(
      client.executeTool('gmail', 'list-messages', {}),
    ).rejects.toThrow(/401 after refresh/);

    // Exactly 3 fetches — no further retries
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  // ── isAuthenticated ─────────────────────────────────────────

  it('isAuthenticated returns true on 200 from /profile', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(
      jsonResponse({ emailAddress: 'me@asawa.ai', historyId: '1' }),
    );

    await expect(client.isAuthenticated('gmail')).resolves.toBe(true);
    expect(lastRequestUrl(fetchMock, 0)).toBe(
      'https://gmail.googleapis.com/gmail/v1/users/me/profile',
    );
    expect(authHeader(lastRequestInit(fetchMock, 0))).toBe('Bearer access-aaa');
  });

  it('isAuthenticated returns false on 401 from /profile', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    fetchMock.mockResolvedValueOnce(new Response('', { status: 401 }));

    await expect(client.isAuthenticated('gmail')).resolves.toBe(false);
  });

  // ── refresh: pre-emptive (expiresAt < now) ──────────────────

  it('expiresAt < now triggers PRE-emptive refresh before the actual API call (no first-call 401)', async () => {
    // cred with expiry in the past — must refresh before any Gmail call
    const cred = makeCred({ expiresAt: Date.now() - 5_000 });
    const { loader, saver, store } = makeStore(cred);
    const client = new GmailDirectClient(loader, saver);

    fetchMock
      // refresh first
      .mockResolvedValueOnce(
        jsonResponse({ access_token: 'access-PRE', expires_in: 3600 }),
      )
      // then the actual list-messages call succeeds with new token
      .mockResolvedValueOnce(jsonResponse({ messages: [] }));

    await client.executeTool('gmail', 'list-messages', { maxResults: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    // First fetch is the token endpoint (NOT Gmail) — proves pre-emptive
    expect(lastRequestUrl(fetchMock, 0)).toBe('https://oauth2.googleapis.com/token');
    expect(lastRequestUrl(fetchMock, 1)).toContain(
      'gmail.googleapis.com/gmail/v1/users/me/messages',
    );
    // Gmail call carried the NEW bearer
    expect(authHeader(lastRequestInit(fetchMock, 1))).toBe('Bearer access-PRE');
    // saver was called once (pre-emptive only)
    expect(store.saves).toHaveLength(1);
    expect(store.cred?.accessToken).toBe('access-PRE');
  });

  // ── header sanity across all tools ──────────────────────────

  it('all requests carry correct Bearer header (every routed tool)', async () => {
    const { loader, saver } = makeStore(makeCred());
    const client = new GmailDirectClient(loader, saver);

    // 5 successful calls, one per tool variant
    for (let i = 0; i < 6; i++) {
      fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, i }));
    }

    await client.executeTool('gmail', 'list-messages', {});
    await client.executeTool('gmail', 'list-by-label', { label: 'INBOX' });
    await client.executeTool('gmail', 'get-message', { id: 'm1' });
    await client.executeTool('gmail', 'get-thread', { id: 't1' });
    await client.executeTool('gmail', 'send-message', {
      to: 'x@y.com',
      subject: 's',
      body: 'b',
    });
    await client.executeTool('gmail', 'modify-labels', {
      id: 'm1',
      addLabelIds: ['A'],
      removeLabelIds: [],
    });

    expect(fetchMock).toHaveBeenCalledTimes(6);
    for (let i = 0; i < 6; i++) {
      expect(authHeader(lastRequestInit(fetchMock, i))).toBe('Bearer access-aaa');
    }
  });
});
