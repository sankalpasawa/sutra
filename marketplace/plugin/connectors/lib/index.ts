/**
 * Sutra Connectors — Public API barrel
 * Frozen by LLD §2.9. ConnectorRouter implementation iter 8 (per LLD §3 lifecycle).
 */

export type {
  Tier,
  Depth,
  Capability,
  ConnectorCallContext,
  ConnectorCallResult,
  FounderApprovalRequest,
  ConnectorManifest,
  CapabilityDecl,
  PolicyDecision,
  AuditEvent,
  AuditSinkConfig,
  FleetPolicy,
  FreezeRule,
  FleetPolicySource,
  CapabilityCheckResult,
  ComposioClient,
} from './types.js';

export { parseManifest, validateManifest } from './manifest.js';
export { tierGrants, matchesResourcePattern, isOverbroadCapability } from './capability.js';
export { evaluatePolicy, consumeApproval } from './policy.js';
export { AuditSink } from './audit.js';
export { FleetPolicyCache } from './fleet-policy.js';
export { ComposioAdapter, FORBIDDEN_COMPOSIO_APIS } from './composio-adapter.js';
export { SecretStoreAge } from './secret-store-age.js';
export type {
  SecretStoreAgeConfig,
  DecryptOptions,
  EncryptOptions,
} from './secret-store-age.js';

export { CredentialLoader } from './credential-loader.js';
export type {
  CredentialBundle,
  SlackBotBundle,
  GmailOAuthBundle,
  ComposioToolkitBundle,
  CredentialLoaderOpts,
} from './credential-loader.js';

// ConnectorRouterOpts is declared further down (alongside the class) since
// it carries CredentialLoader + ComposioAdapter symbols that must be in
// scope. The type is exported lower in this file via `export interface
// ConnectorRouterOpts {...}` — kept here as a doc anchor for the public API.

export {
  ConnectorError,
  ManifestError,
  PolicyDeniedError,
  StalePolicyError,
  ApprovalRequiredError,
  ApprovalTokenExpiredError,
  ForbiddenComposioApiError,
  IdempotencyKeyRequiredError,
  PayloadTooLargeError,
  CredentialNotFoundError,
  SecretStoreSafetyError,
  SecretStoreTimeoutError,
  SecretStoreDecryptError,
  AbortError,
} from './errors.js';

import type {
  ConnectorCallContext,
  ConnectorCallResult,
  ConnectorManifest,
  AuditEvent,
} from './types.js';
import { AuditSink } from './audit.js';
import { FleetPolicyCache } from './fleet-policy.js';
import { ComposioAdapter } from './composio-adapter.js';
import { CredentialLoader } from './credential-loader.js';
import { evaluatePolicy, consumeApproval, issueApproval } from './policy.js';
import {
  StalePolicyError,
  ForbiddenComposioApiError,
  IdempotencyKeyRequiredError,
  PayloadTooLargeError,
} from './errors.js';
import { retry, handleAll, ExponentialBackoff } from 'cockatiel';

/**
 * ConnectorRouter constructor opts.
 *
 * Mode A ('legacy') — preserves the v0 surface for existing call sites
 * (Slack-live integration fixtures, CLI tests). No idempotency-key,
 * AbortSignal, retry, or credential-loader requirements.
 *
 * Mode B ('native-compat') — Activity-shaped contract for native/Temporal
 * orchestration: REQUIRES `ctx.idempotency_key` and `ctx.signal` per call,
 * REQUIRES `credentialLoader` at construction, wraps backend calls in a
 * cockatiel retry policy, and threads AbortSignal end-to-end. Payload bound
 * (1 MB) applies in BOTH modes for safety (M1.5).
 *
 * Mode is REQUIRED — no default — so a caller who forgets to declare cannot
 * accidentally land in either mode.
 */
export interface ConnectorRouterOpts {
  readonly mode: 'legacy' | 'native-compat';
  readonly manifests: ReadonlyArray<ConnectorManifest>;
  readonly fleetPolicy: FleetPolicyCache;
  readonly audit: AuditSink;
  readonly adapter: ComposioAdapter;
  /** REQUIRED when mode === 'native-compat'; ignored otherwise. */
  readonly credentialLoader?: CredentialLoader;
}

/**
 * ConnectorRouter — top-level orchestrator for the 6-step LLD §3 call lifecycle.
 *
 *   1. Manifest lookup by capability connector segment.
 *   2. Fetch FleetPolicy via FleetPolicyCache.current() (may throw StalePolicyError).
 *   3. evaluatePolicy(ctx, manifest, fleetPolicy):
 *        - block            → audit blocked + return outcome='blocked'
 *        - require-approval → audit blocked(approval-required) + return approvalRequired
 *                             with a freshly-issued single-use approvalToken
 *        - allow            → continue
 *   4. ComposioAdapter.call(toolkit, tool, args). On error: audit + return error.
 *   5. (Audit sink redacts args by construction; router passes raw args + ctx
 *      and the sink computes redactedArgsHash from manifest.redactPaths.)
 *   6. AuditSink.append({outcome: 'allowed' | 'approved-after-gate', ...}, ctx.args)
 *      then return ConnectorCallResult { outcome, value }.
 *
 * The 'approved-after-gate' outcome fires when ctx.approvalToken is provided AND
 * consumeApproval(token) returns true AND the policy verdict resolves to 'allow'
 * for that ctx (because evaluatePolicy honors a registered approvalToken).
 *
 * No retries here — retry policy lives outside this module per LLD §4.
 * No logging beyond AuditSink — adapter is dumb on purpose.
 */
export class ConnectorRouter {
  readonly #manifests: ReadonlyArray<ConnectorManifest>;
  readonly #fleetPolicy: FleetPolicyCache;
  readonly #audit: AuditSink;
  readonly #adapter: ComposioAdapter;
  readonly #mode: 'legacy' | 'native-compat';
  readonly #credentialLoader: CredentialLoader | undefined;

  constructor(opts: ConnectorRouterOpts) {
    if (!opts || typeof opts !== 'object') {
      throw new Error('ConnectorRouter: opts must be an object');
    }
    if (opts.mode !== 'legacy' && opts.mode !== 'native-compat') {
      throw new Error(
        `ConnectorRouter: mode must be 'legacy' | 'native-compat' (got: ${String(opts.mode)})`,
      );
    }
    if (opts.mode === 'native-compat' && !opts.credentialLoader) {
      throw new Error(
        'ConnectorRouter: mode=native-compat requires credentialLoader',
      );
    }
    if (!Array.isArray(opts.manifests)) {
      throw new Error('ConnectorRouter: opts.manifests must be an array');
    }
    if (!(opts.fleetPolicy instanceof FleetPolicyCache)) {
      throw new Error('ConnectorRouter: opts.fleetPolicy must be a FleetPolicyCache');
    }
    if (!(opts.audit instanceof AuditSink)) {
      throw new Error('ConnectorRouter: opts.audit must be an AuditSink');
    }
    if (!(opts.adapter instanceof ComposioAdapter)) {
      throw new Error('ConnectorRouter: opts.adapter must be a ComposioAdapter');
    }
    this.#manifests = opts.manifests.slice();
    this.#fleetPolicy = opts.fleetPolicy;
    this.#audit = opts.audit;
    this.#adapter = opts.adapter;
    this.#mode = opts.mode;
    this.#credentialLoader = opts.credentialLoader;
  }

  async call(ctx: ConnectorCallContext): Promise<ConnectorCallResult> {
    // ----------------------------------------------------------------------
    // Step 0: Mode-B contract enforcement (M1.3).
    //   - native-compat REQUIRES ctx.idempotency_key + ctx.signal so that
    //     callers (Activity hooks, Temporal workflows) can dedupe replays
    //     and propagate cancellation. Legacy callers are unaffected.
    // ----------------------------------------------------------------------
    if (this.#mode === 'native-compat') {
      if (
        typeof ctx.idempotency_key !== 'string' ||
        ctx.idempotency_key.length === 0
      ) {
        throw new IdempotencyKeyRequiredError(
          'ConnectorRouter mode=native-compat requires ctx.idempotency_key',
        );
      }
      if (!(ctx.signal instanceof AbortSignal)) {
        throw new IdempotencyKeyRequiredError(
          'ConnectorRouter mode=native-compat requires ctx.signal: AbortSignal',
        );
      }
    }

    // ----------------------------------------------------------------------
    // Step 1: Manifest lookup by capability connector segment.
    // ----------------------------------------------------------------------
    const connectorSegment = extractConnectorSegment(ctx.capability);
    const manifest = this.#manifests.find((m) => m.name === connectorSegment);

    if (manifest === undefined) {
      await this.#auditSafe({
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: 'blocked',
        reason: 'unknown-connector',
        sessionId: ctx.sessionId,
        redactedArgsHash: '',
      }, ctx.args);
      return {
        outcome: 'blocked',
        reason: 'unknown-connector',
      };
    }

    // ----------------------------------------------------------------------
    // Step 2: Fleet policy fetch (may throw StalePolicyError).
    // ----------------------------------------------------------------------
    let fleetPolicy;
    try {
      fleetPolicy = this.#fleetPolicy.current();
    } catch (err) {
      if (err instanceof StalePolicyError) {
        await this.#auditSafe({
          ts: ctx.ts,
          clientId: ctx.clientId,
          tier: ctx.tier,
          depth: ctx.depth,
          capability: ctx.capability,
          outcome: 'blocked',
          reason: 'stale-policy',
          sessionId: ctx.sessionId,
          redactedArgsHash: '',
        }, ctx.args);
        return {
          outcome: 'blocked',
          reason: 'stale-policy',
        };
      }
      // Non-stale errors from the cache (e.g. "load not settled") propagate as
      // an error outcome with a generic class — should not occur in normal flow.
      const errorClass = errorClassOf(err);
      await this.#auditSafe({
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: 'error',
        reason: 'fleet-policy-unavailable',
        sessionId: ctx.sessionId,
        redactedArgsHash: '',
        errorClass,
      }, ctx.args);
      return {
        outcome: 'error',
        reason: 'fleet-policy-unavailable',
        errorClass,
      };
    }

    // ----------------------------------------------------------------------
    // Step 3: Policy evaluation.
    // ----------------------------------------------------------------------
    const decision = evaluatePolicy(ctx, manifest, fleetPolicy);

    if (decision.verdict === 'block') {
      await this.#auditSafe({
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: 'blocked',
        reason: decision.reason,
        sessionId: ctx.sessionId,
        redactedArgsHash: '',
      }, ctx.args);
      return {
        outcome: 'blocked',
        reason: decision.reason,
      };
    }

    if (decision.verdict === 'require-approval') {
      const approvalToken = issueApproval(ctx);
      await this.#auditSafe({
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: 'blocked',
        reason: 'approval-required',
        approvalToken,
        sessionId: ctx.sessionId,
        redactedArgsHash: '',
      }, ctx.args);
      return {
        outcome: 'blocked',
        reason: 'approval-required',
        approvalRequired: true,
        approvalToken,
      };
    }

    // verdict === 'allow' — determine whether this is an
    // approved-after-gate retry by consuming the supplied token. Per codex
    // iter-11 P1 #3: token consumption is ctx-bound — replay across different
    // (clientId, sessionId, capability) is rejected by consumeApproval.
    let approvedAfterGate = false;
    let consumedToken: string | undefined;
    if (
      typeof ctx.approvalToken === 'string' &&
      ctx.approvalToken.length > 0
    ) {
      if (consumeApproval(ctx.approvalToken, ctx)) {
        approvedAfterGate = true;
        consumedToken = ctx.approvalToken;
      }
    }

    // ----------------------------------------------------------------------
    // Step 4: Composio adapter call.
    //   - Mode A (legacy): single attempt, no retry, no signal threading.
    //   - Mode B (native-compat): cockatiel retry policy (3 total attempts =
    //     1 initial + 2 retries, expo backoff 100ms→5s) wraps the call;
    //     AbortSignal short-circuits the retry loop AND the in-flight fetch.
    //
    // Cockatiel 3.x semantics: maxAttempts is the retry count (NOT total).
    // Total executions = 1 initial + maxAttempts retries. So maxAttempts: 2
    // gives 3 total attempts (matches the documented "3 attempts" contract).
    // ctx.signal is passed to policy.execute() as cockatiel's parent abort
    // signal so an aborted call short-circuits the retry loop (NOT just
    // the in-flight fetch). Without this, an aborted Mode B call could
    // duplicate external writes (codex Wave 4 P1).
    // ----------------------------------------------------------------------
    const toolName = extractToolName(ctx.capability);
    let rawResult: unknown;
    try {
      if (this.#mode === 'native-compat') {
        const policy = retry(handleAll, {
          maxAttempts: 2,
          backoff: new ExponentialBackoff({ initialDelay: 100, maxDelay: 5000 }),
        });
        // exactOptionalPropertyTypes — only set `signal` when defined.
        // Mode B already validated ctx.signal is AbortSignal at Step 0 so
        // this is purely a type-narrowing courtesy.
        const adapterOpts: { signal?: AbortSignal } = {};
        if (ctx.signal !== undefined) adapterOpts.signal = ctx.signal;
        // Pass ctx.signal directly as cockatiel's parent abort signal.
        // Cockatiel 3.x: execute(fn, signal?: AbortSignal) — the second arg
        // is an AbortSignal value (NOT a context object). Wrapping in
        // { signal } would set signal.aborted=undefined and silently disable
        // abort short-circuit. Reads via signal.aborted in RetryPolicy.js.
        rawResult = await policy.execute(
          () =>
            this.#adapter.call(
              manifest.composioToolkit,
              toolName,
              ctx.args as Record<string, unknown>,
              adapterOpts,
            ),
          ctx.signal,
        );
      } else {
        rawResult = await this.#adapter.call(
          manifest.composioToolkit,
          toolName,
          ctx.args as Record<string, unknown>,
        );
      }
    } catch (err) {
      if (err instanceof ForbiddenComposioApiError) {
        await this.#auditSafe({
          ts: ctx.ts,
          clientId: ctx.clientId,
          tier: ctx.tier,
          depth: ctx.depth,
          capability: ctx.capability,
          outcome: 'error',
          reason: `forbidden-composio-api:${err.api}`,
          sessionId: ctx.sessionId,
          redactedArgsHash: '',
          errorClass: 'forbidden-composio-api',
        }, ctx.args);
        return {
          outcome: 'error',
          reason: `forbidden-composio-api:${err.api}`,
          errorClass: 'forbidden-composio-api',
        };
      }
      const errorClass = errorClassOf(err);
      await this.#auditSafe({
        ts: ctx.ts,
        clientId: ctx.clientId,
        tier: ctx.tier,
        depth: ctx.depth,
        capability: ctx.capability,
        outcome: 'error',
        reason: errorMessageOf(err),
        sessionId: ctx.sessionId,
        redactedArgsHash: '',
        errorClass,
      }, ctx.args);
      return {
        outcome: 'error',
        reason: errorMessageOf(err),
        errorClass,
      };
    }

    // ----------------------------------------------------------------------
    // Step 4b: Payload size bound (M1.5).
    //   Native/Temporal Activities and downstream transports cap payloads at
    //   ~2-4 MB. We enforce a conservative 1 MB ceiling on the RAW backend
    //   value before redaction (redacted payload is always ≤ raw size). This
    //   applies in BOTH modes — a Mode-A oversize result is just as bad for
    //   the audit log as a Mode-B one. We surface as an error outcome rather
    //   than throwing so the caller gets the standard ConnectorCallResult
    //   contract.
    // ----------------------------------------------------------------------
    if (rawResult !== undefined && rawResult !== null) {
      let valueBytes = 0;
      try {
        valueBytes = Buffer.byteLength(JSON.stringify(rawResult));
      } catch {
        // Non-serializable value — treat as oversize (defensive).
        valueBytes = MAX_PAYLOAD_BYTES + 1;
      }
      if (valueBytes > MAX_PAYLOAD_BYTES) {
        await this.#auditSafe({
          ts: ctx.ts,
          clientId: ctx.clientId,
          tier: ctx.tier,
          depth: ctx.depth,
          capability: ctx.capability,
          outcome: 'error',
          reason: `payload-too-large:${valueBytes}>${MAX_PAYLOAD_BYTES}`,
          sessionId: ctx.sessionId,
          redactedArgsHash: '',
          errorClass: 'PayloadTooLargeError',
        }, ctx.args);
        return {
          outcome: 'error',
          reason: `payload-too-large:${valueBytes}>${MAX_PAYLOAD_BYTES}`,
          errorClass: 'PayloadTooLargeError',
        };
      }
    }

    // ----------------------------------------------------------------------
    // Step 5: Apply manifest.redactPaths to result.
    // ----------------------------------------------------------------------
    const redactedResult = applyRedactPaths(rawResult, manifest.redactPaths);

    // ----------------------------------------------------------------------
    // Step 6: Audit success outcome and return.
    // (AuditSink computes redactedArgsHash internally from rawArgs +
    //  redactPaths configured at sink-construction time.)
    // ----------------------------------------------------------------------
    const successOutcome: AuditEvent['outcome'] = approvedAfterGate
      ? 'approved-after-gate'
      : 'allowed';

    await this.#auditSafe({
      ts: ctx.ts,
      clientId: ctx.clientId,
      tier: ctx.tier,
      depth: ctx.depth,
      capability: ctx.capability,
      outcome: successOutcome,
      sessionId: ctx.sessionId,
      redactedArgsHash: '',
      ...(consumedToken !== undefined ? { approvalToken: consumedToken } : {}),
    }, ctx.args);

    return {
      outcome: successOutcome,
      value: redactedResult,
    };
  }

  /**
   * Audit append wrapper that swallows audit-sink errors. The sink already
   * has a fallback path (LLD §4 audit-write-failure: tmp + stderr beacon),
   * but we add a final catch here so an audit failure NEVER crashes a call.
   * Per LLD §4 invariant: failure path must not crash.
   */
  async #auditSafe(
    event: AuditEvent,
    rawArgs: Readonly<Record<string, unknown>>,
  ): Promise<void> {
    try {
      await this.#audit.append(event, rawArgs);
    } catch {
      /* sink fallback already attempted; nothing more to do */
    }
  }
}

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

/**
 * Per spec §M1.5 — 1 MB ceiling on raw backend payload. Conservative
 * relative to native/Temporal Activity transports (~2-4 MB). Enforced in
 * Router.call() after backend resolves, before redaction.
 */
const MAX_PAYLOAD_BYTES = 1_000_000;

// Keep the symbol live so the typed-error class is exported AND referenced
// (router emits 'PayloadTooLargeError' as a string in the error outcome to
// match the existing ConnectorCallResult contract).
void PayloadTooLargeError;

/**
 * Extract the connector name (first ':'-segment) from a capability id.
 * 'slack:read-channel:#dayflow-eng' → 'slack'
 */
function extractConnectorSegment(capability: string): string {
  const idx = capability.indexOf(':');
  if (idx === -1) return capability;
  return capability.slice(0, idx);
}

/**
 * Extract the tool name (action segment) from a capability id.
 * 'slack:read-channel:#dayflow-eng' → 'read-channel'
 * 'slack:write-message'            → 'write-message'
 * 'slack'                          → '' (defensive — caller should not reach here)
 */
function extractToolName(capability: string): string {
  const parts = capability.split(':');
  if (parts.length < 2) return '';
  return parts[1];
}

/**
 * Apply manifest.redactPaths to a result value. Mirrors the audit-sink
 * redaction semantics (top-level keys, dotted nested keys, `name[*]`
 * wildcard for arrays). Non-object results pass through unchanged.
 *
 * Kept local to the router so we don't entangle the audit-sink internal
 * redactor with response shaping. Both implementations follow the same
 * path grammar so behavior is consistent.
 */
function applyRedactPaths(
  result: unknown,
  redactPaths: ReadonlyArray<string>,
): unknown {
  if (result === null || result === undefined) return result;
  if (typeof result !== 'object') return result;
  if (redactPaths.length === 0) return result;

  const cloned = deepClone(result);
  for (const p of redactPaths) {
    const segments = p.split('.');
    applyRedactionPath(cloned, segments);
  }
  return cloned;
}

const REDACTED_SENTINEL = '<REDACTED>';

function deepClone<T>(value: T): T {
  if (
    typeof (globalThis as { structuredClone?: unknown }).structuredClone ===
    'function'
  ) {
    return (
      globalThis as { structuredClone: <X>(v: X) => X }
    ).structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function applyRedactionPath(
  target: unknown,
  segments: ReadonlyArray<string>,
): void {
  if (target === null || target === undefined) return;
  if (segments.length === 0) return;

  const [head, ...rest] = segments;

  const wildcardMatch = head.match(/^(.+)\[\*\]$/);
  if (wildcardMatch) {
    const arrayKey = wildcardMatch[1];
    if (typeof target !== 'object' || Array.isArray(target)) return;
    const obj = target as Record<string, unknown>;
    const arr = obj[arrayKey];
    if (!Array.isArray(arr)) return;
    if (rest.length === 0) {
      for (let i = 0; i < arr.length; i++) arr[i] = REDACTED_SENTINEL;
    } else {
      for (const item of arr) applyRedactionPath(item, rest);
    }
    return;
  }

  if (typeof target !== 'object' || Array.isArray(target)) return;
  const obj = target as Record<string, unknown>;

  if (rest.length === 0) {
    if (head in obj) obj[head] = REDACTED_SENTINEL;
    return;
  }

  if (head in obj) {
    applyRedactionPath(obj[head], rest);
  }
}

function errorClassOf(err: unknown): string {
  if (err instanceof Error) {
    // Use constructor name as the class label; common values:
    //   'Error', 'TypeError', 'NetworkError', 'AbortError'
    // LLD §4 lists 'network' as the canonical bucket for adapter failures
    // not otherwise classified.
    const name = err.name || err.constructor.name || 'Error';
    if (name === 'Error') return 'network';
    return name;
  }
  return 'unknown';
}

function errorMessageOf(err: unknown): string {
  if (err instanceof Error && typeof err.message === 'string') return err.message;
  if (typeof err === 'string') return err;
  return 'unknown-error';
}
