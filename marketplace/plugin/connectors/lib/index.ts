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
import { evaluatePolicy, consumeApproval, issueApproval } from './policy.js';
import {
  StalePolicyError,
  ForbiddenComposioApiError,
} from './errors.js';

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

  constructor(deps: {
    manifests: ReadonlyArray<ConnectorManifest>;
    fleetPolicy: FleetPolicyCache;
    audit: AuditSink;
    adapter: ComposioAdapter;
  }) {
    if (!deps || typeof deps !== 'object') {
      throw new Error('ConnectorRouter: deps must be an object');
    }
    if (!Array.isArray(deps.manifests)) {
      throw new Error('ConnectorRouter: deps.manifests must be an array');
    }
    if (!(deps.fleetPolicy instanceof FleetPolicyCache)) {
      throw new Error('ConnectorRouter: deps.fleetPolicy must be a FleetPolicyCache');
    }
    if (!(deps.audit instanceof AuditSink)) {
      throw new Error('ConnectorRouter: deps.audit must be an AuditSink');
    }
    if (!(deps.adapter instanceof ComposioAdapter)) {
      throw new Error('ConnectorRouter: deps.adapter must be a ComposioAdapter');
    }
    this.#manifests = deps.manifests.slice();
    this.#fleetPolicy = deps.fleetPolicy;
    this.#audit = deps.audit;
    this.#adapter = deps.adapter;
  }

  async call(ctx: ConnectorCallContext): Promise<ConnectorCallResult> {
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
    // ----------------------------------------------------------------------
    const toolName = extractToolName(ctx.capability);
    let rawResult: unknown;
    try {
      rawResult = await this.#adapter.call(
        manifest.composioToolkit,
        toolName,
        ctx.args as Record<string, unknown>,
      );
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
