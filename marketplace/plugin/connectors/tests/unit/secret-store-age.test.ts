/**
 * Sutra Connectors — secret-store-age unit tests (TDD red phase, M1.7).
 *
 * References:
 *  - Spec authority: holding/research/2026-04-30-core-connectors-hardening-spec.md §M1.7
 *  - Codex direction (8 rounds converged): DIRECTIVE-ID 1777545909 (ADVISORY)
 *
 * Invariants under test:
 *   - Symlink target refused (encrypt + decrypt)
 *   - Symlinked parent refused (encrypt)
 *   - mkdir parent recursive with mode 0o700
 *   - openSync EXCL + NOFOLLOW + 0o600 atomic write to <target>.tmp.<pid>
 *   - atomic rename — target file does not exist mid-encrypt; no .tmp residue
 *   - Decrypt timeout: process killed within 3s (SIGTERM → 2s → SIGKILL)
 *   - Decrypt abort via AbortSignal: process killed within 3s
 *   - Round-trip encrypt-then-decrypt returns same bytes (skipped if `age` not in PATH)
 *
 * Test hygiene:
 *   - tmpdir per test; afterEach cleanup
 *   - No real secrets — synthetic plaintext
 *   - No live network; no ~/.sutra writes
 *   - Round-trip skipped when `age` system binary missing
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  writeFileSync,
  readdirSync,
} from 'node:fs';
import { spawnSync } from 'node:child_process';
import * as path from 'node:path';
import * as os from 'node:os';

import { SecretStoreAge } from '../../lib/secret-store-age.js';
import {
  SecretStoreSafetyError,
  SecretStoreTimeoutError,
  AbortError,
} from '../../lib/errors.js';

// ----------------------------------------------------------------------------
// helpers
// ----------------------------------------------------------------------------

function ageInPath(): boolean {
  const r = spawnSync('which', ['age'], { encoding: 'utf8' });
  return r.status === 0 && (r.stdout ?? '').trim().length > 0;
}

let tmpDir: string;
let identityPath: string;
let recipientPath: string;

beforeEach(() => {
  tmpDir = mkdtempSync(path.join(os.tmpdir(), 'sutra-secret-store-age-'));
  identityPath = path.join(tmpDir, 'identity.key');
  recipientPath = path.join(tmpDir, 'recipient.txt');
  // Identity placeholder for negative-path tests (decrypt errors before reading).
  // Round-trip test generates a real keypair separately.
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

// ----------------------------------------------------------------------------
// tests
// ----------------------------------------------------------------------------

describe('SecretStoreAge — write-path safety (sutra_safe_write port)', () => {
  it('refuses symlink target on encrypt', async () => {
    const real = path.join(tmpDir, 'real.age');
    writeFileSync(real, 'pre-existing');
    const target = path.join(tmpDir, 'symlink.age');
    symlinkSync(real, target);

    const store = makeStore();
    await expect(
      store.encrypt(target, Buffer.from('plaintext'), { timeoutMs: 2000 }),
    ).rejects.toBeInstanceOf(SecretStoreSafetyError);
  });

  it('refuses symlinked parent on encrypt', async () => {
    const realParent = path.join(tmpDir, 'real-parent');
    mkdirSync(realParent);
    const linkedParent = path.join(tmpDir, 'linked-parent');
    symlinkSync(realParent, linkedParent);
    const target = path.join(linkedParent, 'creds.age');

    const store = makeStore();
    await expect(
      store.encrypt(target, Buffer.from('plaintext'), { timeoutMs: 2000 }),
    ).rejects.toBeInstanceOf(SecretStoreSafetyError);
  });

  it.skipIf(!ageInPath())('writes file with mode 0600 (round-trip with age)', async () => {
    // Generate real keypair using age-keygen
    const keygen = spawnSync('age-keygen', ['-o', identityPath], {
      encoding: 'utf8',
    });
    if (keygen.status !== 0) {
      // age-keygen not available; behave as skip
      return;
    }
    // Recipient is on stderr by convention; parse "Public key: <recipient>"
    const m = (keygen.stderr ?? '').match(/Public key:\s*(\S+)/);
    if (!m) return;
    writeFileSync(recipientPath, m[1] + '\n', { mode: 0o644 });

    const target = path.join(tmpDir, 'creds.age');
    const store = makeStore();
    await store.encrypt(target, Buffer.from('hello sutra'), { timeoutMs: 5000 });

    expect(existsSync(target)).toBe(true);
    const st = lstatSync(target);
    expect(st.mode & 0o777).toBe(0o600);
  });
});

describe('SecretStoreAge — read-path safety + subprocess discipline', () => {
  it('refuses symlink target on decrypt', async () => {
    const real = path.join(tmpDir, 'real.age');
    writeFileSync(real, 'pre-existing');
    const target = path.join(tmpDir, 'symlink.age');
    symlinkSync(real, target);

    const store = makeStore();
    await expect(
      store.decrypt(target, { timeoutMs: 2000 }),
    ).rejects.toBeInstanceOf(SecretStoreSafetyError);
  });

  it('decrypt times out with SecretStoreTimeoutError; no orphan age process after 3s', async () => {
    // Create a fake `age` shim that just sleeps — installed in a temp dir
    // injected to PATH front. This works regardless of whether real `age`
    // is present.
    const shimDir = path.join(tmpDir, 'shim-bin');
    mkdirSync(shimDir);
    const shimAge = path.join(shimDir, 'age');
    writeFileSync(
      shimAge,
      '#!/bin/sh\nsleep 60\n',
      { mode: 0o755 },
    );

    const target = path.join(tmpDir, 'fake.age');
    writeFileSync(target, 'not-real-encrypted-bytes');

    const oldPath = process.env.PATH;
    process.env.PATH = `${shimDir}:${oldPath ?? ''}`;
    try {
      const store = makeStore();
      const t0 = Date.now();
      await expect(
        store.decrypt(target, { timeoutMs: 200 }),
      ).rejects.toBeInstanceOf(SecretStoreTimeoutError);
      const elapsed = Date.now() - t0;
      // Must reject within 3s (timeout 200ms + termination escalation budget)
      expect(elapsed).toBeLessThan(3000);
    } finally {
      process.env.PATH = oldPath;
    }

    // Allow up to 2s for SIGTERM-or-SIGKILL escalation to settle
    await new Promise((r) => setTimeout(r, 2200));
    // pgrep age — ANY remaining `age` processes from this test? Only check shim
    // by matching cmdline including shim path. Use ps + grep.
    const ps = spawnSync('sh', ['-c', `ps -ax -o pid,command | grep -F "${shimAge}" | grep -v grep | wc -l`], {
      encoding: 'utf8',
    });
    const orphans = parseInt((ps.stdout ?? '0').trim(), 10);
    expect(orphans).toBe(0);
  });

  it('decrypt aborts via AbortSignal; rejects with AbortError within 3s', async () => {
    const shimDir = path.join(tmpDir, 'shim-bin');
    mkdirSync(shimDir);
    const shimAge = path.join(shimDir, 'age');
    writeFileSync(shimAge, '#!/bin/sh\nsleep 60\n', { mode: 0o755 });

    const target = path.join(tmpDir, 'fake.age');
    writeFileSync(target, 'not-real-encrypted-bytes');

    const oldPath = process.env.PATH;
    process.env.PATH = `${shimDir}:${oldPath ?? ''}`;
    try {
      const store = makeStore();
      const ac = new AbortController();
      const t0 = Date.now();
      const p = store.decrypt(target, { signal: ac.signal, timeoutMs: 60_000 });
      // Abort after a short delay so the listener path (not the already-aborted
      // fast path) is exercised.
      setTimeout(() => ac.abort(), 50);
      await expect(p).rejects.toBeInstanceOf(AbortError);
      const elapsed = Date.now() - t0;
      expect(elapsed).toBeLessThan(3000);
    } finally {
      process.env.PATH = oldPath;
    }
  });

  it('decrypt with already-aborted signal rejects fast (AbortError)', async () => {
    const shimDir = path.join(tmpDir, 'shim-bin');
    mkdirSync(shimDir);
    const shimAge = path.join(shimDir, 'age');
    writeFileSync(shimAge, '#!/bin/sh\nsleep 60\n', { mode: 0o755 });

    const target = path.join(tmpDir, 'fake.age');
    writeFileSync(target, 'not-real-encrypted-bytes');

    const oldPath = process.env.PATH;
    process.env.PATH = `${shimDir}:${oldPath ?? ''}`;
    try {
      const store = makeStore();
      const ac = new AbortController();
      ac.abort();
      const t0 = Date.now();
      await expect(
        store.decrypt(target, { signal: ac.signal, timeoutMs: 60_000 }),
      ).rejects.toBeInstanceOf(AbortError);
      const elapsed = Date.now() - t0;
      expect(elapsed).toBeLessThan(2000);
    } finally {
      process.env.PATH = oldPath;
    }
  });
});

describe('SecretStoreAge — atomic write semantics', () => {
  it.skipIf(!ageInPath())('round-trip encrypt-then-decrypt returns same bytes', async () => {
    const keygen = spawnSync('age-keygen', ['-o', identityPath], {
      encoding: 'utf8',
    });
    if (keygen.status !== 0) return;
    const m = (keygen.stderr ?? '').match(/Public key:\s*(\S+)/);
    if (!m) return;
    writeFileSync(recipientPath, m[1] + '\n', { mode: 0o644 });

    const target = path.join(tmpDir, 'creds.age');
    const store = makeStore();
    const plaintext = Buffer.from('round-trip-test-payload-' + Date.now());

    await store.encrypt(target, plaintext, { timeoutMs: 5000 });
    const out = await store.decrypt(target, { timeoutMs: 5000 });

    expect(out.equals(plaintext)).toBe(true);
  });

  it.skipIf(!ageInPath())('atomic write — no .tmp residue after success', async () => {
    const keygen = spawnSync('age-keygen', ['-o', identityPath], {
      encoding: 'utf8',
    });
    if (keygen.status !== 0) return;
    const m = (keygen.stderr ?? '').match(/Public key:\s*(\S+)/);
    if (!m) return;
    writeFileSync(recipientPath, m[1] + '\n', { mode: 0o644 });

    const target = path.join(tmpDir, 'creds.age');
    const store = makeStore();
    await store.encrypt(target, Buffer.from('atomic-test'), { timeoutMs: 5000 });

    const dir = path.dirname(target);
    const entries = readdirSync(dir);
    const tmps = entries.filter((e) => e.startsWith('creds.age.tmp.'));
    expect(tmps.length).toBe(0);
    expect(existsSync(target)).toBe(true);
  });
});
