/**
 * Sutra Connectors — credential-loader unit tests (M1.8).
 *
 * Spec authority: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.8
 * Wave 3 of Core/Connectors Hardening.
 *
 * Invariants under test:
 *   - throws CredentialNotFoundError when neither .age nor .json exists
 *   - falls back to .json plaintext during migration window AND emits
 *     MIGRATION_PENDING beacon to auditLogPath
 *   - save() round-trips a GmailOAuthBundle through .age (skipped if `age` not in PATH)
 *   - load() reads .age in preference to .json when both exist (skipped if `age` not in PATH)
 *   - discriminated union narrows correctly (kind === 'composio' → toolkit)
 *
 * Test hygiene:
 *   - tmpdir per test; afterEach cleanup
 *   - no real secrets — synthetic bundles
 *   - no live network; no ~/.sutra writes
 *   - round-trip + .age-precedence skip cleanly when `age` system binary missing
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { spawnSync } from 'node:child_process';
import * as path from 'node:path';
import * as os from 'node:os';

import { SecretStoreAge } from '../../lib/secret-store-age.js';
import {
  CredentialLoader,
  type CredentialBundle,
  type SlackBotBundle,
  type GmailOAuthBundle,
  type ComposioToolkitBundle,
} from '../../lib/credential-loader.js';
import { CredentialNotFoundError } from '../../lib/errors.js';

// ----------------------------------------------------------------------------
// helpers
// ----------------------------------------------------------------------------

function ageInPath(): boolean {
  const r = spawnSync('which', ['age'], { encoding: 'utf8' });
  return r.status === 0 && (r.stdout ?? '').trim().length > 0;
}

function ageKeygenInPath(): boolean {
  const r = spawnSync('which', ['age-keygen'], { encoding: 'utf8' });
  return r.status === 0 && (r.stdout ?? '').trim().length > 0;
}

let tmpDir: string;
let keyDir: string;
let identityPath: string;
let recipientPath: string;
let auditLogPath: string;

beforeEach(() => {
  tmpDir = mkdtempSync(path.join(os.tmpdir(), 'sutra-credential-loader-'));
  keyDir = path.join(tmpDir, 'oauth');
  mkdirSync(keyDir, { recursive: true, mode: 0o700 });
  identityPath = path.join(tmpDir, 'identity.key');
  recipientPath = path.join(tmpDir, 'recipient.txt');
  auditLogPath = path.join(tmpDir, 'connector-audit.jsonl');
  // Placeholder identity/recipient. Round-trip test regenerates real keypair.
  writeFileSync(identityPath, 'AGE-SECRET-KEY-1placeholder\n', { mode: 0o600 });
  writeFileSync(recipientPath, 'age1placeholder\n', { mode: 0o644 });
});

afterEach(() => {
  try {
    rmSync(tmpDir, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
});

function makeStore(): SecretStoreAge {
  return new SecretStoreAge({ identityPath, recipientPath });
}

function makeLoader(): CredentialLoader {
  return new CredentialLoader({
    secretStore: makeStore(),
    keyDir,
    auditLogPath,
  });
}

// ----------------------------------------------------------------------------
// tests
// ----------------------------------------------------------------------------

describe('CredentialLoader — load() error paths', () => {
  it('throws CredentialNotFoundError when neither .age nor .json exists', async () => {
    const loader = makeLoader();
    await expect(loader.load('slack')).rejects.toBeInstanceOf(
      CredentialNotFoundError,
    );
  });
});

describe('CredentialLoader — .json migration fallback', () => {
  it('falls back to .json plaintext + emits MIGRATION_PENDING beacon', async () => {
    const bundle: SlackBotBundle = {
      type: 'slack-bot',
      token: 'xoxb-test-pat-1234',
      obtained_at: 1745971200000,
    };
    const jsonPath = path.join(keyDir, 'slack.json');
    writeFileSync(jsonPath, JSON.stringify(bundle), { mode: 0o600 });

    const loader = makeLoader();
    const result = await loader.load('slack');

    expect(result).toEqual(bundle);
    expect(result.type).toBe('slack-bot');

    // Audit beacon emitted
    expect(existsSync(auditLogPath)).toBe(true);
    const auditLines = readFileSync(auditLogPath, 'utf8')
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
    expect(auditLines.length).toBeGreaterThan(0);
    const lastLine = auditLines[auditLines.length - 1];
    if (lastLine === undefined) {
      throw new Error('expected at least one audit beacon line');
    }
    const last = JSON.parse(lastLine) as {
      ts: number;
      event: string;
      connector: string;
      path: string;
      msg: string;
    };
    expect(last.event).toBe('MIGRATION_PENDING');
    expect(last.connector).toBe('slack');
    expect(last.path).toBe(jsonPath);
    expect(typeof last.ts).toBe('number');
    expect(typeof last.msg).toBe('string');
    expect(last.msg.length).toBeGreaterThan(0);
  });
});

describe('CredentialLoader — .age round-trip (requires age binary)', () => {
  it.skipIf(!ageInPath() || !ageKeygenInPath())(
    'save() round-trips a GmailOAuthBundle through .age',
    async () => {
      // Generate real keypair
      const keygen = spawnSync('age-keygen', ['-o', identityPath], {
        encoding: 'utf8',
      });
      if (keygen.status !== 0) return;
      const m = (keygen.stderr ?? '').match(/Public key:\s*(\S+)/);
      if (!m) return;
      writeFileSync(recipientPath, m[1] + '\n', { mode: 0o644 });

      const bundle: GmailOAuthBundle = {
        type: 'gmail-oauth',
        clientId: 'client-id-test',
        clientSecret: 'client-secret-test',
        accessToken: 'access-token-test',
        refreshToken: 'refresh-token-test',
        expiresAt: 1745971200000 + 3_600_000,
        obtained_at: 1745971200000,
      };
      const loader = makeLoader();
      await loader.save('gmail', bundle);

      const agePath = path.join(keyDir, 'gmail.age');
      expect(existsSync(agePath)).toBe(true);

      const round = await loader.load('gmail');
      expect(round).toEqual(bundle);
      expect(round.type).toBe('gmail-oauth');
    },
  );

  it.skipIf(!ageInPath() || !ageKeygenInPath())(
    'reads .age in preference to .json when both exist',
    async () => {
      const keygen = spawnSync('age-keygen', ['-o', identityPath], {
        encoding: 'utf8',
      });
      if (keygen.status !== 0) return;
      const m = (keygen.stderr ?? '').match(/Public key:\s*(\S+)/);
      if (!m) return;
      writeFileSync(recipientPath, m[1] + '\n', { mode: 0o644 });

      const ageBundle: SlackBotBundle = {
        type: 'slack-bot',
        token: 'xoxb-from-age',
        obtained_at: 1745971200000,
      };
      const jsonBundle: SlackBotBundle = {
        type: 'slack-bot',
        token: 'xoxb-from-json-stale',
        obtained_at: 1745000000000,
      };
      // Write both; .age via SecretStore (saved through loader), .json plaintext
      const loader = makeLoader();
      await loader.save('slack', ageBundle);
      const jsonPath = path.join(keyDir, 'slack.json');
      writeFileSync(jsonPath, JSON.stringify(jsonBundle), { mode: 0o600 });

      const result = await loader.load('slack');
      expect(result).toEqual(ageBundle);

      // No migration beacon should fire when .age wins
      if (existsSync(auditLogPath)) {
        const lines = readFileSync(auditLogPath, 'utf8')
          .trim()
          .split('\n')
          .filter((l) => l.length > 0);
        for (const line of lines) {
          const evt = JSON.parse(line) as { event: string };
          expect(evt.event).not.toBe('MIGRATION_PENDING');
        }
      }
    },
  );
});

describe('CredentialLoader — discriminated union narrowing', () => {
  it('narrows ComposioToolkitBundle.kind === "composio" to access .toolkit', async () => {
    const bundle: ComposioToolkitBundle = {
      type: 'composio',
      toolkit: 'GITHUB',
      obtained_at: 1745971200000,
    };
    const jsonPath = path.join(keyDir, 'github.json');
    writeFileSync(jsonPath, JSON.stringify(bundle), { mode: 0o600 });

    const loader = makeLoader();
    const result: CredentialBundle = await loader.load('github');

    // Type-narrow without `as` — discriminant on `kind`
    if (result.type === 'composio') {
      expect(result.toolkit).toBe('GITHUB');
      expect(result.obtained_at).toBe(1745971200000);
    } else {
      throw new Error(
        `expected type='composio', got ${result.type satisfies 'slack-bot' | 'gmail-oauth'}`,
      );
    }
  });
});
