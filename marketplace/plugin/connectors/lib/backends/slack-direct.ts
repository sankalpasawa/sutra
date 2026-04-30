/**
 * Sutra Connectors — Slack direct backend
 *
 * Implements the frozen `ComposioClient` interface (see ../types.ts §2.1)
 * by talking to the Slack Web API directly — no Composio dependency.
 *
 * Surface discipline:
 *   - Implements ONLY the three ComposioClient methods
 *     (authenticate / executeTool / isAuthenticated).
 *   - DOES NOT expose plan / discover / workbench / session-memory /
 *     autoExecute / multiExecute (the FORBIDDEN_COMPOSIO_APIS set in
 *     ../composio-adapter.ts). Adding any of those would defeat the
 *     control-plane-narrow invariant the adapter guards.
 *
 * Network contract:
 *   - All calls are POST application/json to https://slack.com/api/<method>.
 *   - Authorization: Bearer <token> on every request.
 *   - Slack returns `{ ok: boolean, error?: string, ... }`. On `ok=false`
 *     this client throws `new Error(<error code>)`. Callers (typically
 *     ConnectorRouter) decide how to wrap / audit the failure.
 *
 * Auth lifecycle:
 *   - Constructor takes a paired loader/saver. The loader returns the
 *     current credential (or null if unauthenticated); the saver persists
 *     a credential after `authenticate()` validates the token via
 *     `auth.test`. Persistence storage is the caller's choice — this
 *     class does not touch the filesystem.
 *
 * Test contract (tests/unit/slack-direct.test.ts):
 *   - All network is mocked via `vi.stubGlobal('fetch', vi.fn())`.
 *   - No real network calls, no `~/.sutra` or `~/.claude` writes.
 */

import type { ComposioClient } from '../types.js';

export interface SlackCredential {
  readonly type: 'slack-bot';
  readonly token: string; // xoxb-...
}

export type SlackCredentialLoader = () => Promise<SlackCredential | null>;
export type SlackCredentialSaver = (cred: SlackCredential) => Promise<void>;

const SLACK_API_BASE = 'https://slack.com/api';

interface SlackResponse {
  readonly ok: boolean;
  readonly error?: string;
  readonly [k: string]: unknown;
}

export class SlackDirectClient implements ComposioClient {
  readonly #loadCredential: SlackCredentialLoader;
  readonly #saveCredential: SlackCredentialSaver;

  constructor(
    loadCredential: SlackCredentialLoader,
    saveCredential: SlackCredentialSaver,
  ) {
    this.#loadCredential = loadCredential;
    this.#saveCredential = saveCredential;
  }

  /**
   * Validate `oauthToken` via Slack's `auth.test`, then persist on success.
   *
   * `toolkit` is part of the frozen ComposioClient signature; we accept
   * any value here because the class is Slack-specific by construction.
   * Callers that want strict toolkit gating should layer that check above
   * this client.
   */
  async authenticate(_toolkit: string, oauthToken: string): Promise<void> {
    const res = await this.#post('auth.test', oauthToken, {});
    if (!res.ok) {
      throw new Error(
        `slack auth.test failed: ${res.error ?? 'unknown_error'}`,
      );
    }
    await this.#saveCredential({ type: 'slack-bot', token: oauthToken });
  }

  /**
   * Route `tool` to the corresponding Slack Web API method.
   *
   * Supported tools (matches manifests/slack.yaml capabilities):
   *   - 'read-channel' → conversations.history
   *   - 'post-message' → chat.postMessage
   *   - 'get-user'     → users.info
   *
   * Anything else throws `unsupported slack tool: <tool>` — the narrow
   * surface stays narrow.
   */
  async executeTool(
    _toolkit: string,
    tool: string,
    args: Record<string, unknown>,
    opts?: { signal?: AbortSignal },
  ): Promise<unknown> {
    const cred = await this.#loadCredential();
    if (!cred) {
      throw new Error('slack: not authenticated (no credential loaded)');
    }

    let method: string;
    let body: Record<string, unknown>;

    switch (tool) {
      case 'read-channel': {
        method = 'conversations.history';
        body = {
          channel: args['channel'],
          limit: args['limit'] ?? 50,
        };
        break;
      }
      case 'post-message': {
        method = 'chat.postMessage';
        body = {
          channel: args['channel'],
          text: args['text'],
        };
        if (args['thread_ts'] !== undefined) {
          body['thread_ts'] = args['thread_ts'];
        }
        break;
      }
      case 'get-user': {
        method = 'users.info';
        body = { user: args['user'] };
        break;
      }
      default:
        throw new Error(`unsupported slack tool: ${tool}`);
    }

    const res = await this.#post(method, cred.token, body, opts?.signal);
    if (!res.ok) {
      throw new Error(`slack ${method} failed: ${res.error ?? 'unknown_error'}`);
    }
    return res;
  }

  /**
   * Probe current credential via `auth.test`. Returns false (never throws)
   * if no credential is loaded, the network call rejects, or Slack returns
   * `ok=false`.
   */
  async isAuthenticated(_toolkit: string): Promise<boolean> {
    const cred = await this.#loadCredential();
    if (!cred) return false;
    try {
      const res = await this.#post('auth.test', cred.token, {});
      return res.ok === true;
    } catch {
      return false;
    }
  }

  // --------------------------------------------------------------------
  // Internal: single fetch primitive. Every Slack call goes through here
  // so the test guard ("no request goes anywhere except slack.com/api/")
  // has one place to assert against.
  // --------------------------------------------------------------------
  async #post(
    method: string,
    token: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<SlackResponse> {
    const url = `${SLACK_API_BASE}/${method}`;
    const init: RequestInit = {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    };
    // M1.4 — undefined-safe: fetch ignores `signal: undefined`. Mode-B
    // Router supplies ctx.signal so an abort cancels the in-flight request.
    if (signal !== undefined) init.signal = signal;
    const response = await fetch(url, init);
    // Slack always returns JSON for Web API methods.
    const json = (await response.json()) as SlackResponse;
    return json;
  }
}
