/**
 * Sutra Connectors — Gmail direct backend
 *
 * Implements the FROZEN ComposioClient interface (lib/types.ts) directly
 * against Google's Gmail v1 + OAuth 2.0 token endpoints. NO Composio
 * dependency: this lets T1/T2 ship Gmail without conceding the control
 * plane to a third-party planner.
 *
 * Surface (matches ComposioClient EXACTLY):
 *   - authenticate(toolkit, oauthToken)
 *   - executeTool(toolkit, tool, args)
 *   - isAuthenticated(toolkit)
 *
 * Tools routed inside executeTool:
 *   list-messages, get-message, get-thread, list-by-label,
 *   send-message, modify-labels
 *
 * OAuth refresh policy (load-bearing):
 *   1. Pre-emptive: before each Gmail API call, if expiresAt is within
 *      60s of now, refresh first.
 *   2. Reactive: on a 401 from Gmail, refresh and retry once. Second 401
 *      throws (do NOT loop — refresh-token is likely revoked).
 *
 * Persistence: caller supplies (loader, saver) — backend never touches
 * disk directly. Matches Sutra "no ~/.sutra writes inside backends" rule;
 * audit + storage live in the L1 connectors core.
 */

import type { ComposioClient } from '../types.js';

/** OAuth credential persisted by the connect.sh CLI after the browser dance. */
export interface GmailCredential {
  readonly type: 'gmail-oauth';
  readonly clientId: string;
  readonly clientSecret: string;
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly expiresAt: number; // unix ms
}

const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const GMAIL_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me';
const REFRESH_SKEW_MS = 60_000; // refresh if within 1 minute of expiry

interface RawAuthPayload {
  client_id?: unknown;
  client_secret?: unknown;
  access_token?: unknown;
  refresh_token?: unknown;
  expires_at?: unknown;
}

function parseAuthPayload(raw: string): GmailCredential {
  let parsed: RawAuthPayload;
  try {
    parsed = JSON.parse(raw) as RawAuthPayload;
  } catch (err) {
    throw new Error(
      `gmail-direct.authenticate: oauthToken is not valid JSON (${(err as Error).message})`,
    );
  }
  if (parsed === null || typeof parsed !== 'object') {
    throw new Error('gmail-direct.authenticate: oauthToken JSON must be an object');
  }
  const {
    client_id,
    client_secret,
    access_token,
    refresh_token,
    expires_at,
  } = parsed;
  if (typeof client_id !== 'string' || client_id.length === 0) {
    throw new Error('gmail-direct.authenticate: client_id missing or not a string');
  }
  if (typeof client_secret !== 'string' || client_secret.length === 0) {
    throw new Error('gmail-direct.authenticate: client_secret missing or not a string');
  }
  if (typeof access_token !== 'string' || access_token.length === 0) {
    throw new Error('gmail-direct.authenticate: access_token missing or not a string');
  }
  if (typeof refresh_token !== 'string' || refresh_token.length === 0) {
    throw new Error('gmail-direct.authenticate: refresh_token missing or not a string');
  }
  if (typeof expires_at !== 'number' || !Number.isFinite(expires_at)) {
    throw new Error('gmail-direct.authenticate: expires_at missing or not a finite number');
  }
  return {
    type: 'gmail-oauth',
    clientId: client_id,
    clientSecret: client_secret,
    accessToken: access_token,
    refreshToken: refresh_token,
    expiresAt: expires_at,
  };
}

/**
 * Build a base64url-encoded RFC-822 MIME envelope. Gmail's
 * users.messages.send takes `raw` as URL-safe base64 of the full MIME.
 */
export function buildMime(to: string, subject: string, body: string): string {
  const lines = [`To: ${to}`, `Subject: ${subject}`, '', body];
  const utf8 = new TextEncoder().encode(lines.join('\r\n'));
  return Buffer.from(utf8)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function asString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`gmail-direct: arg '${field}' must be a non-empty string`);
  }
  return value;
}

function asOptionalString(value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== 'string') {
    throw new Error(`gmail-direct: arg '${field}' must be a string`);
  }
  return value;
}

function asOptionalStringArray(value: unknown, field: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || !value.every((v): v is string => typeof v === 'string')) {
    throw new Error(`gmail-direct: arg '${field}' must be a string[]`);
  }
  return value;
}

export class GmailDirectClient implements ComposioClient {
  readonly #loader: () => Promise<GmailCredential | null>;
  readonly #saver: (c: GmailCredential) => Promise<void>;

  constructor(
    loader: () => Promise<GmailCredential | null>,
    saver: (c: GmailCredential) => Promise<void>,
  ) {
    if (typeof loader !== 'function') {
      throw new Error('GmailDirectClient: loader must be a function');
    }
    if (typeof saver !== 'function') {
      throw new Error('GmailDirectClient: saver must be a function');
    }
    this.#loader = loader;
    this.#saver = saver;
  }

  // ────────────────────────────────────────────────────────────
  // ComposioClient surface
  // ────────────────────────────────────────────────────────────

  async authenticate(toolkit: string, oauthToken: string): Promise<void> {
    if (toolkit !== 'gmail') {
      throw new Error(
        `gmail-direct.authenticate: expected toolkit='gmail', got '${toolkit}'`,
      );
    }
    const cred = parseAuthPayload(oauthToken);
    await this.#saver(cred);
  }

  async executeTool(
    toolkit: string,
    tool: string,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    if (toolkit !== 'gmail') {
      throw new Error(
        `gmail-direct.executeTool: expected toolkit='gmail', got '${toolkit}'`,
      );
    }
    const cred = await this.#loadFresh();

    switch (tool) {
      case 'list-messages':
        return this.#listMessages(cred, args);
      case 'list-by-label':
        return this.#listByLabel(cred, args);
      case 'get-message':
        return this.#getMessage(cred, args);
      case 'get-thread':
        return this.#getThread(cred, args);
      case 'send-message':
        return this.#sendMessage(cred, args);
      case 'modify-labels':
        return this.#modifyLabels(cred, args);
      default:
        throw new Error(`unsupported gmail tool: ${tool}`);
    }
  }

  async isAuthenticated(toolkit: string): Promise<boolean> {
    if (toolkit !== 'gmail') return false;
    const cred = await this.#loader();
    if (!cred) return false;
    let active = cred;
    if (Date.now() > active.expiresAt - REFRESH_SKEW_MS) {
      active = await this.#refresh(active);
    }
    const res = await fetch(`${GMAIL_BASE}/profile`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${active.accessToken}` },
    });
    if (res.status === 200) return true;
    if (res.status === 401 || res.status === 403) return false;
    // Other statuses (5xx, network) — be conservative: not authenticated
    return false;
  }

  // ────────────────────────────────────────────────────────────
  // Tool routes
  // ────────────────────────────────────────────────────────────

  async #listMessages(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    return this.#listLike(cred, args, undefined);
  }

  async #listByLabel(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    const label = asString(args.label, 'label');
    return this.#listLike(cred, args, [label]);
  }

  async #listLike(
    cred: GmailCredential,
    args: Record<string, unknown>,
    enforcedLabels: string[] | undefined,
  ): Promise<unknown> {
    const q = asOptionalString(args.q, 'q');
    const argLabels = asOptionalStringArray(args.labelIds, 'labelIds');
    const maxResults = typeof args.maxResults === 'number' ? args.maxResults : 25;
    const labels = enforcedLabels ?? argLabels;
    const params = new URLSearchParams();
    if (q !== undefined) params.set('q', q);
    if (labels && labels.length > 0) params.set('labelIds', labels.join(','));
    params.set('maxResults', String(maxResults));
    const url = `${GMAIL_BASE}/messages?${params.toString()}`;
    return this.#requestJson(cred, url, { method: 'GET' });
  }

  async #getMessage(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    const id = asString(args.id, 'id');
    return this.#requestJson(cred, `${GMAIL_BASE}/messages/${encodeURIComponent(id)}`, {
      method: 'GET',
    });
  }

  async #getThread(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    const id = asString(args.id, 'id');
    return this.#requestJson(cred, `${GMAIL_BASE}/threads/${encodeURIComponent(id)}`, {
      method: 'GET',
    });
  }

  async #sendMessage(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    const to = asString(args.to, 'to');
    const subject = asString(args.subject, 'subject');
    const body = asString(args.body, 'body');
    const raw = buildMime(to, subject, body);
    return this.#requestJson(cred, `${GMAIL_BASE}/messages/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw }),
    });
  }

  async #modifyLabels(
    cred: GmailCredential,
    args: Record<string, unknown>,
  ): Promise<unknown> {
    const id = asString(args.id, 'id');
    const addLabelIds = asOptionalStringArray(args.addLabelIds, 'addLabelIds') ?? [];
    const removeLabelIds =
      asOptionalStringArray(args.removeLabelIds, 'removeLabelIds') ?? [];
    return this.#requestJson(
      cred,
      `${GMAIL_BASE}/messages/${encodeURIComponent(id)}/modify`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ addLabelIds, removeLabelIds }),
      },
    );
  }

  // ────────────────────────────────────────────────────────────
  // OAuth + HTTP plumbing
  // ────────────────────────────────────────────────────────────

  /** Load latest cred from saver-side storage; reject if missing. */
  async #loadFresh(): Promise<GmailCredential> {
    const cred = await this.#loader();
    if (!cred) {
      throw new Error(
        'gmail-direct: no credential available — call authenticate() first',
      );
    }
    return cred;
  }

  /**
   * Issue an authenticated request. Pre-emptive refresh if near expiry.
   * On 401, refresh once and retry. Second 401 throws.
   */
  async #requestJson(
    cred: GmailCredential,
    url: string,
    init: { method: string; headers?: Record<string, string>; body?: string },
  ): Promise<unknown> {
    let active = cred;
    if (Date.now() > active.expiresAt - REFRESH_SKEW_MS) {
      active = await this.#refresh(active);
    }
    const first = await this.#fetchWith(active, url, init);
    if (first.status === 401) {
      const refreshed = await this.#refresh(active);
      const second = await this.#fetchWith(refreshed, url, init);
      if (second.status === 401) {
        throw new Error(
          'gmail-direct: 401 after refresh — refresh-token revoked or invalid',
        );
      }
      return this.#readJsonOrThrow(second, url);
    }
    return this.#readJsonOrThrow(first, url);
  }

  async #fetchWith(
    cred: GmailCredential,
    url: string,
    init: { method: string; headers?: Record<string, string>; body?: string },
  ): Promise<Response> {
    const headers: Record<string, string> = {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${cred.accessToken}`,
    };
    const reqInit: RequestInit = { method: init.method, headers };
    if (init.body !== undefined) {
      reqInit.body = init.body;
    }
    return fetch(url, reqInit);
  }

  async #readJsonOrThrow(res: Response, url: string): Promise<unknown> {
    if (res.status >= 200 && res.status < 300) {
      return res.json();
    }
    let detail = '';
    try {
      detail = await res.text();
    } catch {
      // ignore
    }
    throw new Error(
      `gmail-direct: ${res.status} from ${url}${detail ? `: ${detail}` : ''}`,
    );
  }

  /**
   * Exchange refresh_token for a new access_token. Persists the result
   * via the saver and returns the fresh cred.
   */
  async #refresh(cred: GmailCredential): Promise<GmailCredential> {
    const form = new URLSearchParams();
    form.set('grant_type', 'refresh_token');
    form.set('client_id', cred.clientId);
    form.set('client_secret', cred.clientSecret);
    form.set('refresh_token', cred.refreshToken);

    const res = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form.toString(),
    });
    if (res.status !== 200) {
      let detail = '';
      try {
        detail = await res.text();
      } catch {
        // ignore
      }
      throw new Error(
        `gmail-direct: refresh failed (${res.status})${detail ? `: ${detail}` : ''}`,
      );
    }
    const payload = (await res.json()) as {
      access_token?: unknown;
      expires_in?: unknown;
    };
    if (typeof payload.access_token !== 'string' || payload.access_token.length === 0) {
      throw new Error('gmail-direct: refresh response missing access_token');
    }
    const expiresIn =
      typeof payload.expires_in === 'number' && Number.isFinite(payload.expires_in)
        ? payload.expires_in
        : 3600;
    const fresh: GmailCredential = {
      type: 'gmail-oauth',
      clientId: cred.clientId,
      clientSecret: cred.clientSecret,
      accessToken: payload.access_token,
      refreshToken: cred.refreshToken,
      expiresAt: Date.now() + expiresIn * 1000,
    };
    await this.#saver(fresh);
    return fresh;
  }
}
