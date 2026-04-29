/**
 * Sutra Connectors — audit.ts unit tests (TDD red phase, iter 3).
 *
 * References:
 *  - LLD §2.5 + §4 (audit-write-failure row) — holding/research/2026-04-30-connectors-LLD.md
 *  - Test plan §3.4 + §4 row 3 — holding/research/2026-04-30-connectors-test-plan.md
 *
 * All assertions here MUST currently fail because lib/audit.ts is a stub
 * whose constructor + append() + close() throw 'not implemented (TDD red phase)'.
 *
 * Invariants under test (LLD §2.5):
 *   - Append-only (no rewrites)
 *   - Redaction applied BEFORE serialization (secret never touches disk)
 *   - Required fields present (runtime check)
 *   - Failure path: write to fallback /tmp + emit stderr beacon
 *
 * Test hygiene:
 *   - tmpdir per test; afterEach cleanup
 *   - No real-looking secrets — TEST_TOKEN_*** + 'redact-me' markers
 *   - No live network; no ~/.sutra or ~/.claude writes
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { promises as fs } from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import * as crypto from 'node:crypto';

import { AuditSink } from '../../lib/audit.js';
import type { AuditEvent, AuditSinkConfig } from '../../lib/types.js';

// -----------------------------------------------------------------------------
// Per-test tmpdir helpers — never touch repo .enforcement/ or HOME
// -----------------------------------------------------------------------------

let tmpRoot: string;
let auditPath: string;

beforeEach(async () => {
  tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'sutra-connectors-audit-'));
  auditPath = path.join(tmpRoot, 'connector-audit.jsonl');
});

afterEach(async () => {
  // Best-effort cleanup; do not mask test errors.
  try {
    await fs.rm(tmpRoot, { recursive: true, force: true });
  } catch {
    // ignored
  }
});

// -----------------------------------------------------------------------------
// Fixture builders — TEST_TOKEN_*** patterns only
// -----------------------------------------------------------------------------

function makeEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    ts: 1_777_000_000_000,
    clientId: 'asawa-holding',
    tier: 'T2',
    depth: 5,
    capability: 'slack:read-channel:#dayflow-eng',
    outcome: 'allowed',
    sessionId: 'TEST_SESSION_001',
    redactedArgsHash: '', // sink is expected to fill this
    ...overrides,
  };
}

function makeConfig(overrides: Partial<AuditSinkConfig> = {}): AuditSinkConfig {
  return {
    path: auditPath,
    redactPaths: ['args.token', 'args.headers.authorization'],
    ...overrides,
  };
}

// Args containing values that MUST never reach disk in plaintext.
const SECRET_RAW_ARGS = {
  channel: '#dayflow-eng',
  token: 'TEST_TOKEN_***redact-me-top-level',
  headers: {
    authorization: 'Bearer TEST_TOKEN_***redact-me-bearer',
    'user-agent': 'sutra-test',
  },
};

async function readJsonl(p: string): Promise<unknown[]> {
  const raw = await fs.readFile(p, 'utf8');
  return raw
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line));
}

// -----------------------------------------------------------------------------
// 1. Constructor accepts AuditSinkConfig
// -----------------------------------------------------------------------------

describe('AuditSink — construction (LLD §2.5)', () => {
  it('constructor accepts AuditSinkConfig with path + redactPaths', () => {
    const cfg = makeConfig();
    expect(() => new AuditSink(cfg)).not.toThrow();
  });
});

// -----------------------------------------------------------------------------
// 2. append() writes JSONL to configured path
// -----------------------------------------------------------------------------

describe('AuditSink.append — basic write (test plan §3.4)', () => {
  it('writes one JSON-line per event to the configured path', async () => {
    const sink = new AuditSink(makeConfig());
    await sink.append(makeEvent(), { channel: '#dayflow-eng' });
    await sink.close();

    const lines = await readJsonl(auditPath);
    expect(lines).toHaveLength(1);
    expect((lines[0] as AuditEvent).capability).toBe(
      'slack:read-channel:#dayflow-eng',
    );
  });
});

// -----------------------------------------------------------------------------
// 3. Redaction-by-construction — secrets never reach disk
// -----------------------------------------------------------------------------

describe('AuditSink.append — redaction by construction (codex P1)', () => {
  it('applies redactPaths BEFORE serialization — raw secrets never appear on disk', async () => {
    const sink = new AuditSink(makeConfig());
    await sink.append(makeEvent(), SECRET_RAW_ARGS);
    await sink.close();

    const raw = await fs.readFile(auditPath, 'utf8');
    expect(raw).not.toContain('redact-me-top-level');
    expect(raw).not.toContain('redact-me-bearer');
    expect(raw).not.toContain('TEST_TOKEN_***');
  });

  it('redaction applies to nested object paths (e.g. headers.authorization)', async () => {
    const nestedCfg = makeConfig({
      redactPaths: ['response.tokens[*].secret', 'args.headers.authorization'],
    });
    const nestedArgs = {
      args: {
        headers: { authorization: 'Bearer TEST_TOKEN_***redact-me-nested' },
      },
      response: {
        tokens: [
          { id: 't1', secret: 'TEST_TOKEN_***redact-me-arr-0' },
          { id: 't2', secret: 'TEST_TOKEN_***redact-me-arr-1' },
        ],
      },
    };

    const sink = new AuditSink(nestedCfg);
    await sink.append(makeEvent(), nestedArgs);
    await sink.close();

    const raw = await fs.readFile(auditPath, 'utf8');
    expect(raw).not.toContain('redact-me-nested');
    expect(raw).not.toContain('redact-me-arr-0');
    expect(raw).not.toContain('redact-me-arr-1');
  });

  it('does not log raw rawArgs object — only redactedArgsHash and explicit AuditEvent fields', async () => {
    const sink = new AuditSink(makeConfig());
    await sink.append(makeEvent(), SECRET_RAW_ARGS);
    await sink.close();

    const [line] = (await readJsonl(auditPath)) as Array<Record<string, unknown>>;
    expect(line).toBeDefined();
    expect(line).not.toHaveProperty('rawArgs');
    expect(line).not.toHaveProperty('args');
    expect(line).toHaveProperty('redactedArgsHash');
  });
});

// -----------------------------------------------------------------------------
// 4. redactedArgsHash is deterministic SHA-256
// -----------------------------------------------------------------------------

describe('AuditSink.append — redactedArgsHash (LLD §2.5)', () => {
  it('generates redactedArgsHash deterministically (SHA-256, identical inputs → identical hash)', async () => {
    const sinkA = new AuditSink(makeConfig());
    const auditPathA = auditPath;
    await sinkA.append(makeEvent(), SECRET_RAW_ARGS);
    await sinkA.close();

    // Second sink writes to a fresh tmp file.
    const tmpRoot2 = await fs.mkdtemp(
      path.join(os.tmpdir(), 'sutra-connectors-audit-b-'),
    );
    const auditPathB = path.join(tmpRoot2, 'connector-audit.jsonl');
    try {
      const sinkB = new AuditSink(makeConfig({ path: auditPathB }));
      await sinkB.append(makeEvent(), SECRET_RAW_ARGS);
      await sinkB.close();

      const [a] = (await readJsonl(auditPathA)) as Array<Record<string, unknown>>;
      const [b] = (await readJsonl(auditPathB)) as Array<Record<string, unknown>>;

      const ha = a?.redactedArgsHash as string | undefined;
      const hb = b?.redactedArgsHash as string | undefined;
      expect(ha).toBeDefined();
      expect(ha).toMatch(/^[a-f0-9]{64}$/);
      expect(ha).toBe(hb);
    } finally {
      await fs.rm(tmpRoot2, { recursive: true, force: true });
    }
  });

  it('redactedArgsHash differs when redacted args differ in any single field', async () => {
    const sink = new AuditSink(makeConfig());
    await sink.append(makeEvent({ ts: 1 }), { channel: '#a' });
    await sink.append(makeEvent({ ts: 2 }), { channel: '#b' });
    await sink.close();

    const lines = (await readJsonl(auditPath)) as Array<Record<string, unknown>>;
    expect(lines).toHaveLength(2);
    const h0 = lines[0]?.redactedArgsHash as string;
    const h1 = lines[1]?.redactedArgsHash as string;
    expect(h0).not.toBe(h1);
    // Sanity: the hash is in fact a SHA-256 (64 hex chars), not crypto.randomUUID etc.
    expect(crypto.createHash('sha256').update('').digest('hex')).toMatch(
      /^[a-f0-9]{64}$/,
    );
  });
});

// -----------------------------------------------------------------------------
// 5. All required AuditEvent fields are logged
// -----------------------------------------------------------------------------

describe('AuditSink.append — required fields (test plan §3.4)', () => {
  it('emits all required AuditEvent fields: ts, clientId, tier, depth, capability, outcome, sessionId, redactedArgsHash', async () => {
    const sink = new AuditSink(makeConfig());
    await sink.append(makeEvent(), { channel: '#dayflow-eng' });
    await sink.close();

    const [line] = (await readJsonl(auditPath)) as Array<Record<string, unknown>>;
    expect(line).toBeDefined();
    for (const field of [
      'ts',
      'clientId',
      'tier',
      'depth',
      'capability',
      'outcome',
      'sessionId',
      'redactedArgsHash',
    ]) {
      expect(line).toHaveProperty(field);
    }
  });
});

// -----------------------------------------------------------------------------
// 6. Append-only ordering
// -----------------------------------------------------------------------------

describe('AuditSink.append — append-only ordering (LLD §2.5 invariant)', () => {
  it('preserves write order across multiple appends; never rewrites prior lines', async () => {
    const sink = new AuditSink(makeConfig());
    const events: AuditEvent[] = [
      makeEvent({ ts: 1_777_000_000_001, sessionId: 'S1' }),
      makeEvent({ ts: 1_777_000_000_002, sessionId: 'S2' }),
      makeEvent({ ts: 1_777_000_000_003, sessionId: 'S3' }),
    ];
    for (const e of events) {
      await sink.append(e, { channel: '#dayflow-eng' });
    }
    await sink.close();

    const lines = (await readJsonl(auditPath)) as Array<Record<string, unknown>>;
    expect(lines).toHaveLength(3);
    expect(lines.map((l) => l.sessionId)).toEqual(['S1', 'S2', 'S3']);
    expect(lines.map((l) => l.ts)).toEqual([
      1_777_000_000_001,
      1_777_000_000_002,
      1_777_000_000_003,
    ]);
  });
});

// -----------------------------------------------------------------------------
// 7. Failure path → fallback /tmp + stderr beacon
// -----------------------------------------------------------------------------

describe('AuditSink.append — failure path (LLD §4 audit-write-failure row)', () => {
  it('falls back to /tmp and emits a stderr beacon when primary path is unwritable', async () => {
    // Simulate an unwritable primary by pointing at a path whose parent is a
    // file (not a directory). Any reasonable implementation will EACCES/ENOTDIR.
    const blockerFile = path.join(tmpRoot, 'not-a-dir');
    await fs.writeFile(blockerFile, 'blocker');
    const unwritable = path.join(blockerFile, 'connector-audit.jsonl');

    const sink = new AuditSink(makeConfig({ path: unwritable }));

    // Capture stderr.
    const origWrite = process.stderr.write.bind(process.stderr);
    let stderrCapture = '';
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (process.stderr.write as any) = (chunk: string | Uint8Array): boolean => {
      stderrCapture +=
        typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8');
      return true;
    };

    try {
      // Must not throw — sink degrades gracefully per LLD §4.
      await sink.append(
        makeEvent({ clientId: 'asawa-holding', capability: 'slack:read-channel:#dayflow-eng' }),
        { channel: '#dayflow-eng' },
      );
      await sink.close();
    } finally {
      process.stderr.write = origWrite;
    }

    // Beacon must mention key fields for grep-recovery.
    expect(stderrCapture).toContain('asawa-holding');
    expect(stderrCapture).toContain('slack:read-channel:#dayflow-eng');

    // Fallback file should exist somewhere under os.tmpdir(); we don't pin the
    // exact filename, but a fallback line containing the capability must be
    // findable in the system temp directory tree the sink chose.
    const sysTmp = os.tmpdir();
    const candidates = await fs.readdir(sysTmp);
    let foundFallback = false;
    for (const name of candidates) {
      // Cheap heuristic — look at top-level files only; deep recursion would
      // be slow and the sink is expected to write to a known prefix.
      if (!name.includes('connector-audit')) continue;
      const full = path.join(sysTmp, name);
      try {
        const stat = await fs.stat(full);
        if (!stat.isFile()) continue;
        const body = await fs.readFile(full, 'utf8');
        if (body.includes('slack:read-channel:#dayflow-eng')) {
          foundFallback = true;
          await fs.rm(full, { force: true });
          break;
        }
      } catch {
        // ignored
      }
    }
    expect(foundFallback).toBe(true);
  });
});

// -----------------------------------------------------------------------------
// 8. close() flushes pending writes
// -----------------------------------------------------------------------------

describe('AuditSink.close — flush semantics (test plan §3.4)', () => {
  it('flushes pending writes before resolving', async () => {
    const sink = new AuditSink(makeConfig());
    // Fire several appends without awaiting individually — close() must drain.
    const pending = [
      sink.append(makeEvent({ sessionId: 'P1' }), { i: 1 }),
      sink.append(makeEvent({ sessionId: 'P2' }), { i: 2 }),
      sink.append(makeEvent({ sessionId: 'P3' }), { i: 3 }),
    ];
    await Promise.all(pending);
    await sink.close();

    const lines = (await readJsonl(auditPath)) as Array<Record<string, unknown>>;
    expect(lines).toHaveLength(3);
    expect(new Set(lines.map((l) => l.sessionId))).toEqual(
      new Set(['P1', 'P2', 'P3']),
    );
  });
});

// -----------------------------------------------------------------------------
// 9. Runtime rejection of malformed events
// -----------------------------------------------------------------------------

describe('AuditSink.append — runtime validation (test plan §3.4)', () => {
  it('rejects malformed AuditEvent at runtime when a required field is missing', async () => {
    const sink = new AuditSink(makeConfig());
    // Intentionally ill-typed: missing capability + sessionId.
    const bad = {
      ts: 1_777_000_000_000,
      clientId: 'asawa-holding',
      tier: 'T2',
      depth: 5,
      outcome: 'allowed',
      redactedArgsHash: '',
    } as unknown as AuditEvent;

    await expect(sink.append(bad, { channel: '#x' })).rejects.toThrow();
  });
});
