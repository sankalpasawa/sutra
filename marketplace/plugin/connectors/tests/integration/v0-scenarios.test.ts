/**
 * Sutra Connectors — v0 done-scenarios integration tests (iter 10).
 *
 * Scope: foundational spec §7 (the 6 v0 scenarios) end-to-end against
 * ConnectorRouter (lib/index.ts), wired with real parseManifest, AuditSink,
 * FleetPolicyCache, ComposioAdapter; ComposioClient mocked via vi.fn().
 *
 * No real Composio install. No live network. No real Slack OAuth. No writes
 * outside os.tmpdir() per test (afterEach cleanup).
 *
 * Refs:
 *  - holding/research/2026-04-30-sutra-connectors-foundational-design.md §7
 *  - holding/research/2026-04-30-connectors-LLD.md §3
 *  - holding/research/2026-04-30-connectors-test-plan.md §5
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { promises as fs } from 'node:fs';
import * as fsSync from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import {
  ConnectorRouter,
  AuditSink,
  FleetPolicyCache,
  ComposioAdapter,
  parseManifest,
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
const CONNECT_SH = path.resolve(__dirname, '..', '..', 'scripts', 'connect.sh');
const FROZEN_NOW = 1_777_500_000_000;
const STALE_AFTER_MS = 60_000;

// ---------------------------------------------------------------------------
// Fixtures + helpers
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

function makePolicy(overrides: Partial<FleetPolicy> = {}): FleetPolicy {
  return {
    version: overrides.version ?? '1',
    lastUpdated: overrides.lastUpdated ?? FROZEN_NOW,
    freezes: overrides.freezes ?? [],
    tierOverrides: overrides.tierOverrides ?? {},
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
  return {
    source,
    emit: (p: FleetPolicy) => {
      next = p;
      for (const l of listeners) l(p);
    },
  };
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
  tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'sutra-connectors-v0-int-'));
  auditPath = path.join(tmpRoot, 'connector-audit.jsonl');
  manifest = parseManifest(await fs.readFile(MANIFEST_PATH, 'utf8'));
});

afterEach(async () => {
  try { await fs.rm(tmpRoot, { recursive: true, force: true }); } catch { /* ignore */ }
  vi.restoreAllMocks();
});

async function readAuditLines(): Promise<Array<Record<string, unknown>>> {
  const raw = await fs.readFile(auditPath, 'utf8');
  return raw.split('\n').filter(Boolean).map((l) => JSON.parse(l));
}

async function buildRouter(opts: {
  composio?: ReturnType<typeof makeComposioClient>;
  fleetSource?: ReturnType<typeof makeFleetSource>;
} = {}) {
  const composio = opts.composio ?? makeComposioClient();
  const fleetSource = opts.fleetSource ?? makeFleetSource(makePolicy());
  const cache = await buildCache(fleetSource.source);
  const audit = new AuditSink({ path: auditPath, redactPaths: manifest.redactPaths });
  const adapter = new ComposioAdapter(composio.client);
  const router = new ConnectorRouter({
    manifests: [manifest], fleetPolicy: cache, audit, adapter,
  });
  return { router, audit, composio, fleetSource };
}

function makeCtx(overrides: Partial<ConnectorCallContext>): ConnectorCallContext {
  return {
    clientId: overrides.clientId ?? 'sutra-dayflow-001',
    tier: overrides.tier ?? 'T2',
    depth: overrides.depth ?? 1,
    capability: overrides.capability ?? 'slack:read-channel:#dayflow-eng',
    args: overrides.args ?? { channel: '#dayflow-eng' },
    ts: overrides.ts ?? FROZEN_NOW,
    sessionId: overrides.sessionId ?? 'TEST_SESSION_v0',
    ...(overrides.approvalToken !== undefined ? { approvalToken: overrides.approvalToken } : {}),
  };
}

// ---------------------------------------------------------------------------
// v0 scenarios
// ---------------------------------------------------------------------------

describe('v0 scenarios — 6 done-conditions from foundational spec §7', () => {
  it('v0/01: connect.sh slack registers OAuth (mocked dry-run) on first run', () => {
    const r = spawnSync('bash', [CONNECT_SH, 'slack'], {
      env: { ...process.env, SUTRA_CONNECTORS_DRY_RUN: '1', HOME: tmpRoot },
      encoding: 'utf8',
    });
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/slack/i);
    expect(r.stdout).toMatch(/dry-run/i);
    expect(fsSync.existsSync(path.join(tmpRoot, '.sutra-connectors', 'oauth'))).toBe(false);
  });

  it('v0/02: DayFlow T2 reads #dayflow-eng → allowed + audited', async () => {
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => ({ ok: true, messages: [{ ts: '1.0', text: 'hi' }] }),
    });
    const { router, audit } = await buildRouter({ composio });

    const ctx = makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001', depth: 1,
      capability: 'slack:read-channel:#dayflow-eng',
      args: { channel: '#dayflow-eng' }, sessionId: 'session-v02',
    });

    const result = await router.call(ctx);
    await audit.close();

    expect(result.outcome).toBe('allowed');
    expect((result.value as { ok?: boolean }).ok).toBe(true);
    expect(composio.executeTool).toHaveBeenCalledTimes(1);
    expect(composio.executeTool).toHaveBeenCalledWith('slack', 'read-channel', { channel: '#dayflow-eng' });

    const lines = await readAuditLines();
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      tier: 'T2', capability: 'slack:read-channel:#dayflow-eng',
      outcome: 'allowed', clientId: 'sutra-dayflow-001', sessionId: 'session-v02',
    });
  });

  it('v0/03: DayFlow posts to #public-launch at D5 → blocked → token → re-call → approved-after-gate', async () => {
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => ({ ok: true, ts: '2.0' }),
    });
    const { router, audit } = await buildRouter({ composio });

    const baseCtx = makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001', depth: 5,
      capability: 'slack:post-message:#public-launch',
      args: { channel: '#public-launch', text: 'launch!' },
      sessionId: 'session-v03',
    });

    const first = await router.call(baseCtx);
    expect(first.outcome).toBe('blocked');
    expect(first.reason).toBe('approval-required');
    expect(first.approvalRequired).toBe(true);
    expect(typeof first.approvalToken).toBe('string');
    expect(first.approvalToken!.length).toBeGreaterThan(0);
    expect(composio.executeTool).not.toHaveBeenCalled();

    const second = await router.call(makeCtx({ ...baseCtx, approvalToken: first.approvalToken }));
    expect(second.outcome).toBe('approved-after-gate');
    expect((second.value as { ok?: boolean }).ok).toBe(true);
    expect(composio.executeTool).toHaveBeenCalledTimes(1);

    await audit.close();
    const lines = await readAuditLines();
    expect(lines).toHaveLength(2);
    expect(lines[0]).toMatchObject({
      outcome: 'blocked', reason: 'approval-required', tier: 'T2',
      capability: 'slack:post-message:#public-launch',
    });
    expect(lines[0].approvalToken).toBe(first.approvalToken);
    expect(lines[1]).toMatchObject({
      outcome: 'approved-after-gate', tier: 'T2',
      capability: 'slack:post-message:#public-launch',
    });
    expect(lines[1].approvalToken).toBe(first.approvalToken);
  });

  it('v0/04: Testlify T3 reads Asawa #ops → blocked, audit reason=tier-denied', async () => {
    const composio = makeComposioClient({ isAuthenticated: true });
    const { router, audit } = await buildRouter({ composio });

    const result = await router.call(makeCtx({
      tier: 'T3', clientId: 'sutra-testlify-001', depth: 3,
      capability: 'slack:read-channel:#ops',
      args: { channel: '#ops' }, sessionId: 'session-v04',
    }));
    await audit.close();

    expect(result.outcome).toBe('blocked');
    expect(result.reason).toBe('tier-denied');
    expect(composio.executeTool).not.toHaveBeenCalled();

    const lines = await readAuditLines();
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      tier: 'T3', outcome: 'blocked', reason: 'tier-denied',
      capability: 'slack:read-channel:#ops',
    });
  });

  it('v0/05: jq filter audit log to tier=T2 returns DayFlow events only', async () => {
    const { router, audit } = await buildRouter();

    await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng', sessionId: 'session-dayflow',
    }));
    await router.call(makeCtx({
      tier: 'T3', clientId: 'sutra-testlify-001',
      capability: 'slack:read-channel:#ops',
      args: { channel: '#ops' }, sessionId: 'session-testlify',
    }));
    await router.call(makeCtx({
      tier: 'T1', clientId: 'asawa-holding',
      capability: 'slack:read-channel:#ops',
      args: { channel: '#ops' }, sessionId: 'session-asawa',
    }));

    await audit.close();
    const lines = await readAuditLines();
    expect(lines).toHaveLength(3);

    const t2Only = lines.filter((l) => l.tier === 'T2');
    expect(t2Only).toHaveLength(1);
    expect(t2Only[0].clientId).toBe('sutra-dayflow-001');
    expect(t2Only[0].capability).toBe('slack:read-channel:#dayflow-eng');
    expect(t2Only.every((l) => l.tier === 'T2')).toBe(true);
  });

  it('v0/06: fleet-policy push freeze of slack:* for T2 → next T2 call blocks within 1 evaluation', async () => {
    const composio = makeComposioClient({ isAuthenticated: true });
    const fleetSource = makeFleetSource(makePolicy());
    const { router, audit } = await buildRouter({ composio, fleetSource });

    const before = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
    }));
    expect(before.outcome).toBe('allowed');

    fleetSource.emit(makePolicy({
      version: '2',
      freezes: [{
        id: 'merge-freeze-2026-04-30',
        capabilityPattern: 'slack:*',
        tierScope: ['T2'],
        reason: 'merge-freeze',
      }],
    }));

    const t2After = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
      sessionId: 'session-after-freeze',
    }));
    expect(t2After.outcome).toBe('blocked');
    expect(t2After.reason).toMatch(/^active-freeze:/);
    expect(t2After.reason).toContain('merge-freeze-2026-04-30');

    const t1After = await router.call(makeCtx({
      tier: 'T1', clientId: 'asawa-holding',
      capability: 'slack:read-channel:#ops',
      args: { channel: '#ops' }, sessionId: 'session-t1-after',
    }));
    expect(t1After.outcome).toBe('allowed');

    await audit.close();
    const lines = await readAuditLines();
    expect(lines).toHaveLength(3);
    expect(lines[0].outcome).toBe('allowed');
    expect(lines[1].outcome).toBe('blocked');
    expect(lines[1].reason).toMatch(/^active-freeze:/);
    expect(lines[2].outcome).toBe('allowed');
  });
});

// ---------------------------------------------------------------------------
// Edge cases — network error, malformed manifest at parse time
// ---------------------------------------------------------------------------

describe('v0 edges', () => {
  it('network error from Composio → outcome=error with errorClass set, audited', async () => {
    const composio = makeComposioClient({
      isAuthenticated: true,
      executeToolImpl: async () => {
        const e: Error & { name?: string } = new Error('ECONNREFUSED');
        e.name = 'NetworkError';
        throw e;
      },
    });
    const { router, audit } = await buildRouter({ composio });

    const result = await router.call(makeCtx({
      tier: 'T2', clientId: 'sutra-dayflow-001',
      capability: 'slack:read-channel:#dayflow-eng',
    }));

    expect(result.outcome).toBe('error');
    expect(typeof result.errorClass).toBe('string');
    expect(result.errorClass).not.toBe('');

    await audit.close();
    const lines = await readAuditLines();
    expect(lines).toHaveLength(1);
    expect(lines[0].outcome).toBe('error');
    expect(typeof lines[0].errorClass).toBe('string');
  });

  it('malformed manifest rejected by parseManifest — never reaches router', () => {
    expect(() => parseManifest(': : not yaml at all : :::')).toThrow();
  });
});
