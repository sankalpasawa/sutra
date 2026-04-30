/**
 * Sutra Connectors — Wave 4 Router Mode A / Mode B integration tests.
 *
 * Covers:
 *   M1.2 / M1.9  — Router accepts ConnectorRouterOpts with explicit
 *                  mode='legacy'|'native-compat' (no default); Mode B
 *                  requires credentialLoader at construction.
 *   M1.3         — Mode B Router.call() throws IdempotencyKeyRequiredError
 *                  when ctx.idempotency_key OR ctx.signal is missing.
 *                  Mode A passes legacy ctx without those fields.
 *   M1.5         — Router enforces 1 MB payload bound (both modes); oversize
 *                  result returns outcome:'error', reason:'payload-too-large:*',
 *                  errorClass:'PayloadTooLargeError' (does NOT throw).
 *
 * Out of scope here (covered upstream / downstream):
 *   - cockatiel retry semantics (M1.6) — verified by adapter unit tests.
 *   - Live network — all backends mocked.
 *
 * No real Composio install, no live network, no ~/.sutra writes.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { promises as fs } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ConnectorRouter,
  AuditSink,
  FleetPolicyCache,
  ComposioAdapter,
  CredentialLoader,
  SecretStoreAge,
  parseManifest,
  IdempotencyKeyRequiredError,
} from '../../lib/index.js';
import type {
  ComposioClient,
  ConnectorCallContext,
  ConnectorManifest,
  FleetPolicy,
  FleetPolicySource,
} from '../../lib/types.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const MANIFEST_PATH = path.resolve(__dirname, '..', '..', 'manifests', 'slack.yaml');
const FROZEN_NOW = 1_777_500_000_000;
const STALE_AFTER_MS = 60_000;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeComposioClient(opts: {
  isAuthenticated?: boolean;
  executeToolImpl?: (
    toolkit: string,
    tool: string,
    args: Record<string, unknown>,
  ) => Promise<unknown>;
} = {}) {
  const authenticate = vi.fn(async () => undefined);
  const executeTool = vi.fn(
    opts.executeToolImpl ??
      (async () => ({ ok: true, messages: [{ ts: '1.0', text: 'hi' }] })),
  );
  const isAuthenticated = vi.fn(async () => opts.isAuthenticated ?? true);
  const client: ComposioClient = {
    authenticate: authenticate as unknown as ComposioClient['authenticate'],
    executeTool: executeTool as unknown as ComposioClient['executeTool'],
    isAuthenticated:
      isAuthenticated as unknown as ComposioClient['isAuthenticated'],
  };
  return { client, authenticate, executeTool, isAuthenticated };
}

function makePolicy(): FleetPolicy {
  return {
    version: '1',
    lastUpdated: FROZEN_NOW,
    freezes: [],
    tierOverrides: {},
  };
}

function makeFleetSource(initial: FleetPolicy) {
  let next = initial;
  const listeners = new Set<(p: FleetPolicy) => void>();
  const source: FleetPolicySource = {
    load: async () => next,
    watch(onChange) {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
  };
  return { source };
}

async function buildCache(source: FleetPolicySource): Promise<FleetPolicyCache> {
  const cache = new FleetPolicyCache(source, STALE_AFTER_MS);
  await Promise.resolve();
  await Promise.resolve();
  return cache;
}

let tmpRoot: string;
let auditPath: string;
let manifest: ConnectorManifest;

beforeEach(async () => {
  tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'sutra-connectors-mode-b-'));
  auditPath = path.join(tmpRoot, 'connector-audit.jsonl');
  manifest = parseManifest(await fs.readFile(MANIFEST_PATH, 'utf8'));
});

afterEach(async () => {
  try { await fs.rm(tmpRoot, { recursive: true, force: true }); } catch { /* ignore */ }
  vi.restoreAllMocks();
});

function makeCtx(overrides: Partial<ConnectorCallContext>): ConnectorCallContext {
  return {
    clientId: overrides.clientId ?? 'sutra-dayflow-001',
    tier: overrides.tier ?? 'T2',
    depth: overrides.depth ?? 1,
    capability: overrides.capability ?? 'slack:read-channel:#dayflow-eng',
    args: overrides.args ?? { channel: '#dayflow-eng' },
    ts: overrides.ts ?? FROZEN_NOW,
    sessionId: overrides.sessionId ?? 'TEST_SESSION_mode_b',
    ...(overrides.approvalToken !== undefined ? { approvalToken: overrides.approvalToken } : {}),
    ...(overrides.idempotency_key !== undefined ? { idempotency_key: overrides.idempotency_key } : {}),
    ...(overrides.signal !== undefined ? { signal: overrides.signal } : {}),
    ...(overrides.event_id !== undefined ? { event_id: overrides.event_id } : {}),
  };
}

/** Stub CredentialLoader instance (Mode B construction guard only). */
function makeStubCredentialLoader(): CredentialLoader {
  // We only need an instance that passes the Router's `truthy`-style check,
  // not a working secret store — Mode-B construction never invokes load() in
  // these tests because backends are mocked at the ComposioClient layer.
  const stubSecretStore = {
    encrypt: async () => undefined,
    decrypt: async () => Buffer.from('{}', 'utf8'),
  } as unknown as SecretStoreAge;
  return new CredentialLoader({ secretStore: stubSecretStore });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConnectorRouter Mode A / Mode B contract (Wave 4)', () => {
  it('throws when constructed without explicit mode (M1.2)', async () => {
    const composio = makeComposioClient();
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);

    expect(() =>
      new (ConnectorRouter as unknown as new (opts: unknown) => unknown)({
        manifests: [manifest],
        fleetPolicy: cache,
        audit,
        adapter,
      }),
    ).toThrow(/mode must be/);
  });

  it('Mode B construction without credentialLoader throws (M1.9)', async () => {
    const composio = makeComposioClient();
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);

    expect(() =>
      new ConnectorRouter({
        mode: 'native-compat',
        manifests: [manifest],
        fleetPolicy: cache,
        audit,
        adapter,
      }),
    ).toThrow(/credentialLoader/);
  });

  it('Mode A call without idempotency_key succeeds (legacy contract preserved)', async () => {
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => ({ ok: true, messages: [] }),
    });
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);
    const router = new ConnectorRouter({
      mode: 'legacy',
      manifests: [manifest],
      fleetPolicy: cache,
      audit,
      adapter,
    });

    const result = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001', depth: 1,
      capability: 'slack:read-channel:#dayflow-eng',
      args: { channel: '#dayflow-eng' },
    }));
    await audit.close();

    expect(result.outcome).toBe('allowed');
    expect(composio.executeTool).toHaveBeenCalledTimes(1);
    // Mode A: 3-arg call (no opts) — legacy assertion shape preserved.
    expect(composio.executeTool).toHaveBeenCalledWith('slack', 'read-channel', { channel: '#dayflow-eng' });
  });

  it('Mode B call without idempotency_key throws IdempotencyKeyRequiredError (M1.3)', async () => {
    const composio = makeComposioClient({ isAuthenticated: true });
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);
    const router = new ConnectorRouter({
      mode: 'native-compat',
      manifests: [manifest],
      fleetPolicy: cache,
      audit,
      adapter,
      credentialLoader: makeStubCredentialLoader(),
    });

    // No idempotency_key, no signal → expect typed throw.
    await expect(
      router.call(makeCtx({
        tier: 'T2', clientId: 'sutra-dayflow-001',
        capability: 'slack:read-channel:#dayflow-eng',
      })),
    ).rejects.toBeInstanceOf(IdempotencyKeyRequiredError);

    // Backend was never reached.
    expect(composio.executeTool).not.toHaveBeenCalled();
  });

  it('Mode B call with idempotency_key + AbortSignal succeeds (signal threaded to adapter)', async () => {
    let receivedOpts: { signal?: AbortSignal } | undefined;
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async (
        _toolkit: string,
        _tool: string,
        _args: Record<string, unknown>,
        // 4th arg surfaces opts when adapter threads them.
        ...rest: unknown[]
      ) => {
        receivedOpts = rest[0] as { signal?: AbortSignal } | undefined;
        return { ok: true, messages: [] };
      },
    });
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);
    const router = new ConnectorRouter({
      mode: 'native-compat',
      manifests: [manifest],
      fleetPolicy: cache,
      audit,
      adapter,
      credentialLoader: makeStubCredentialLoader(),
    });

    const controller = new AbortController();
    const result = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
      idempotency_key: 'idem-key-001',
      signal: controller.signal,
    }));
    await audit.close();

    expect(result.outcome).toBe('allowed');
    expect(composio.executeTool).toHaveBeenCalledTimes(1);
    expect(receivedOpts).toBeDefined();
    expect(receivedOpts!.signal).toBe(controller.signal);
  });

  it('Mode B AbortSignal short-circuits cockatiel retry loop (M2.8 / Wave 4 residual)', async () => {
    // Codex Wave 4 P1 advisory residual: lib/index.ts wraps backend.execute in
    // a cockatiel retry policy with maxAttempts:2 (= 3 total attempts) and
    // initialDelay:100ms exponential backoff. ctx.signal is passed to
    // policy.execute(fn, signal) as the parent abort signal so an aborted
    // call SHORT-CIRCUITS the retry loop instead of exhausting attempts.
    // Wave 4 fold (commit 83364ac) wired this; this test locks the contract.
    //
    // Strategy: backend always throws a retryable error and counts invocations.
    // Schedule signal.abort() at ~50ms — inside the first backoff delay —
    // and assert backend.invocations < 3 (full cap). If cockatiel honored
    // the signal, we should see exactly 1 invocation (no retry happened).
    let invocations = 0;
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => {
        invocations += 1;
        // Throw a generic retryable error — handleAll matches everything.
        throw new Error('transient backend failure');
      },
    });
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);
    const router = new ConnectorRouter({
      mode: 'native-compat',
      manifests: [manifest],
      fleetPolicy: cache,
      audit,
      adapter,
      credentialLoader: makeStubCredentialLoader(),
    });

    const controller = new AbortController();
    // Abort during the first retry backoff (initialDelay=100ms in lib/index.ts).
    // 50ms places the abort firmly inside that window.
    const abortTimer = setTimeout(() => controller.abort(), 50);

    const result = await router.call(makeCtx({
      tier: 'T2',
      clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
      idempotency_key: 'idem-key-abort-001',
      signal: controller.signal,
    }));
    clearTimeout(abortTimer);
    await audit.close();

    // Router catches the policy.execute() rejection and returns error outcome.
    expect(result.outcome).toBe('error');

    // The proof: backend was called fewer than the full retry budget (3).
    // With abort short-circuit, we expect exactly 1 invocation (the initial
    // attempt; the abort fires during backoff before any retry runs).
    // Strict bound `< 3` is what the advisory called for; the typical
    // observed value is 1.
    expect(invocations).toBeLessThan(3);
  });

  it('Router rejects payload > 1MB with payload-too-large error outcome (M1.5)', async () => {
    // Build a backend response just over the 1 MB cap.
    const oversizePayload = 'x'.repeat(1_500_000);
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => ({ ok: true, blob: oversizePayload }),
    });
    const fleetSource = makeFleetSource(makePolicy());
    const cache = await buildCache(fleetSource.source);
    const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
    const adapter = new ComposioAdapter(composio.client);
    const router = new ConnectorRouter({
      mode: 'legacy',
      manifests: [manifest],
      fleetPolicy: cache,
      audit,
      adapter,
    });

    const result = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
      args: { channel: '#dayflow-eng' },
    }));
    await audit.close();

    // Returns standard ConnectorCallResult — does NOT throw unhandled.
    expect(result.outcome).toBe('error');
    expect(result.reason).toMatch(/^payload-too-large:/);
    expect(result.errorClass).toBe('PayloadTooLargeError');

    // Audit log captured the rejection (no value leak).
    const raw = await fs.readFile(auditPath, 'utf8');
    const lines = raw.split('\n').filter(Boolean).map((l) => JSON.parse(l));
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      tier: 'T2',
      capability: 'slack:read-channel:#dayflow-eng',
      outcome: 'error',
      errorClass: 'PayloadTooLargeError',
    });
    expect(String(lines[0].reason)).toMatch(/^payload-too-large:/);
  });
});
