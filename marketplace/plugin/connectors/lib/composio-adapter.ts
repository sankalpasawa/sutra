/**
 * Sutra Connectors — Composio L2 adapter
 * Frozen by LLD §2.7. Implementation lands iter 5 (sequential green, fourth).
 *
 * INVARIANT (load-bearing): adapter NEVER calls Composio.plan, .discover,
 * .workbench, session-memory, or similar planning APIs. Guard tests verify
 * — failures here block ship.
 *
 * Why this matters (LLD §5 justification): Composio's full surface includes
 * planning/discovery primitives (plan, discover, workbench, session-memory,
 * autoExecute, multiExecute). If Sutra's adapter ever calls those, Composio
 * captures the control plane and Sutra degrades to a thin proxy. The adapter
 * must therefore touch ONLY the narrow {authenticate, executeTool,
 * isAuthenticated} triple — every other property access is a guard violation.
 *
 * iter 7 implementation: replaces the TDD-red stub with a delegating impl
 * that flips ~13 unit tests green. The 7 GUARD cases are the load-bearing
 * ones — they block ship if violated. No CODEX_DIRECTIVE_ACK override.
 */

import type { ComposioClient } from './types.js';
import { ForbiddenComposioApiError } from './errors.js';

export { ForbiddenComposioApiError } from './errors.js';

// Sentinel for guard-test introspection (iter 7 verifies this list is the
// COMPLETE set of forbidden APIs; any addition requires charter amendment)
export const FORBIDDEN_COMPOSIO_APIS: ReadonlyArray<string> = [
  'plan',
  'discover',
  'workbench',
  'session-memory',
  'autoExecute',
  'multiExecute',
] as const;

/**
 * Placeholder OAuth token used during lazy auth. Real OAuth flow lands
 * iter 9 — until then the narrow ComposioClient mock accepts any string,
 * and tests do not assert on token contents. The literal value is a
 * sentinel so that telemetry / audit can recognize iter-7 unauth-edge
 * traffic if any leaks to staging.
 */
const ITER7_PLACEHOLDER_OAUTH_TOKEN = 'Sutra/L1/no-token-iter7';

export class ComposioAdapter {
  // Private storage. Touched ONLY via the narrow surface; no enumeration,
  // no Object.keys, no `in` checks (those would trip the recording-proxy
  // guard tests — Proxy `has` trap records on `prop in target`).
  readonly #client: ComposioClient;

  constructor(client: ComposioClient) {
    // typeof checks (not truthy / not `'x' in client`) per test guidance:
    // Proxy `has` traps record accesses, and a truthy-property check could
    // be satisfied by a non-function value. The contract is "function".
    if (typeof client.authenticate !== 'function') {
      throw new Error(
        "ComposioAdapter: client missing required method 'authenticate' " +
          '(narrow surface contract — LLD §2.7)',
      );
    }
    if (typeof client.executeTool !== 'function') {
      throw new Error(
        "ComposioAdapter: client missing required method 'executeTool' " +
          '(narrow surface contract — LLD §2.7)',
      );
    }
    if (typeof client.isAuthenticated !== 'function') {
      throw new Error(
        "ComposioAdapter: client missing required method 'isAuthenticated' " +
          '(narrow surface contract — LLD §2.7)',
      );
    }
    this.#client = client;
  }

  /**
   * Execute a Composio toolkit tool with lazy authentication.
   *
   * Surface discipline: this method touches the client ONLY via three
   * named property accesses — `.isAuthenticated`, `.authenticate`,
   * `.executeTool`. No other properties are read, enumerated, or
   * existence-checked. This is the LOAD-BEARING invariant verified by
   * the recording-Proxy guard tests in
   * tests/unit/composio-adapter.test.ts.
   *
   * No logging here — audit owns logging (see audit-sink.ts). Adapter
   * is dumb on purpose.
   */
  async call(
    toolkit: string,
    tool: string,
    args: Record<string, unknown>,
    opts?: { signal?: AbortSignal },
  ): Promise<unknown> {
    // Lazy auth: probe first, authenticate only if needed. Tests use a
    // mocked isAuthenticated (true by default; explicit false for the
    // lazy-auth case).
    const authed = await this.#client.isAuthenticated(toolkit);
    if (!authed) {
      await this.#client.authenticate(toolkit, ITER7_PLACEHOLDER_OAUTH_TOKEN);
    }

    // Delegate verbatim. Return value passes through unchanged.
    // Rejections propagate unchanged (no try/catch — would swallow them).
    //
    // M1.4 (AbortSignal threading): if the caller supplied opts (Mode B
    // path), thread it to executeTool. Backends that accept signal use it
    // to cancel in-flight fetches; backends that do not accept opts simply
    // ignore the extra parameter.
    //
    // PRESERVATION (Mode A): when no opts were supplied, call executeTool
    // with the EXACT 3-argument signature. Tests assert
    // `toHaveBeenCalledWith(toolkit, tool, args)` and adding a 4th
    // `undefined` would regress those assertions for legacy callers.
    if (opts !== undefined) {
      return this.#client.executeTool(toolkit, tool, args, opts);
    }
    return this.#client.executeTool(toolkit, tool, args);
  }
}

// Re-export retained so consumers importing from this module get the
// error class without a second import path. Also keeps the symbol live
// for the guard test that constructs `new ForbiddenComposioApiError('plan')`
// via the errors.ts re-export above.
void ForbiddenComposioApiError;
