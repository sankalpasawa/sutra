/**
 * Sutra Connectors — CLI integration tests for scripts/connect.sh (iter 10).
 *
 * References:
 *  - Foundational spec §7 scenario 1:
 *      holding/research/2026-04-30-sutra-connectors-foundational-design.md
 *  - Test plan §4 row 6 (CLI integration) + §10 iter 6 mapping:
 *      holding/research/2026-04-30-connectors-test-plan.md
 *
 * Behavior under test:
 *   1. `connect.sh slack` with SUTRA_CONNECTORS_DRY_RUN=1 → exit 0, stdout
 *      mentions slack, no real ~/.sutra-connectors/oauth/ writes.
 *   2. `connect.sh nonexistent-connector` → exit 1, stderr explains.
 *   3. `connect.sh` (no arg) → exit != 0, usage printed.
 *
 * Hygiene: HOME is reassigned to a per-test tmpdir so that even a buggy
 * script can never touch the real ~/.sutra-connectors/. afterEach cleans
 * the tmpdir.
 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { promises as fs } from 'node:fs';
import * as fsSync from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const CONNECT_SH = path.resolve(
  __dirname,
  '..',
  '..',
  'scripts',
  'connect.sh',
);

let tmpHome: string;

beforeEach(async () => {
  tmpHome = await fs.mkdtemp(path.join(os.tmpdir(), 'sutra-connectors-cli-'));
});

afterEach(async () => {
  try {
    await fs.rm(tmpHome, { recursive: true, force: true });
  } catch {
    /* best-effort */
  }
});

function run(args: ReadonlyArray<string>, env: Record<string, string> = {}) {
  return spawnSync('bash', [CONNECT_SH, ...args], {
    env: {
      ...process.env,
      HOME: tmpHome,
      ...env,
    },
    encoding: 'utf8',
  });
}

describe('cli: connect.sh slack with SUTRA_CONNECTORS_DRY_RUN=1', () => {
  it('exits 0, mentions slack in stdout, no ~/.sutra-connectors/oauth/ writes', () => {
    const r = run(['slack'], { SUTRA_CONNECTORS_DRY_RUN: '1' });

    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/slack/i);
    // dry-run banner makes the no-op explicit
    expect(r.stdout).toMatch(/dry-run/i);

    // Confirm zero writes under HOME — the dry-run path must not mkdir or
    // append to the OAuth state directory.
    const oauthDir = path.join(tmpHome, '.sutra-connectors', 'oauth');
    expect(fsSync.existsSync(oauthDir)).toBe(false);
  });

  it('summary block lists capability count > 0 for slack manifest', () => {
    const r = run(['slack'], { SUTRA_CONNECTORS_DRY_RUN: '1' });
    expect(r.status).toBe(0);
    expect(r.stdout).toMatch(/capabilities:\s*[1-9]/);
    expect(r.stdout).toMatch(/manifest:/);
  });
});

describe('cli: connect.sh nonexistent-connector', () => {
  it('exits 1 and stderr explains manifest-not-found', () => {
    const r = run(['nonexistent-connector-xyzzy'], {
      SUTRA_CONNECTORS_DRY_RUN: '1',
    });
    expect(r.status).toBe(1);
    expect(r.stderr).toMatch(/manifest not found/i);
    // Available connectors hint should be helpful.
    expect(r.stderr).toMatch(/available connectors/i);
  });
});

describe('cli: connect.sh with no argument', () => {
  it('exits non-zero and prints usage to stderr', () => {
    const r = run([], { SUTRA_CONNECTORS_DRY_RUN: '1' });
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/usage:/i);
    expect(r.stderr).toMatch(/connect\.sh/i);
  });
});

describe('cli: connect.sh rejects path-y / traversal connector names', () => {
  it('rejects names containing slashes or .. components', () => {
    const r = run(['../etc/passwd'], { SUTRA_CONNECTORS_DRY_RUN: '1' });
    expect(r.status).not.toBe(0);
    expect(r.stderr).toMatch(/invalid connector name|manifest not found/i);
  });
});

// ---------------------------------------------------------------------------
// M2.7 — call.mjs --dev-bypass FAIL-LOUD on unwritable audit log
// ---------------------------------------------------------------------------
//
// Codex Wave 6 P1 advisory residual: emitDevBypassBeacon() in scripts/call.mjs
// uses appendFileSync to .enforcement/connector-audit.jsonl. If the write
// fails (parent dir read-only / fs full / etc.), the bypass MUST refuse to
// proceed — running the bypass without a forensic record defeats the gate
// behind SUTRA_DEV=1. Commit fa252df wired the fail-loud path; this test
// asserts the contract directly.
//
// Strategy: spawn `node scripts/call.mjs slack post-message --dev-bypass`
// with cwd set to a tmpdir whose `.enforcement/` directory is chmod 0500
// (read-only). appendFileSync inside emitDevBypassBeacon raises EACCES,
// which propagates to the top-level try/catch (call.mjs:119) → exit 1
// with the error on stderr. Backend is never reached.

const CALL_MJS = path.resolve(__dirname, '..', '..', 'scripts', 'call.mjs');

// call.mjs preflights the `age` binary on import (defense in depth — see
// scripts/preflight-age.mjs). In environments without age, the script exits
// before reaching emitDevBypassBeacon, so the fail-loud contract under test
// is unobservable. Skip-pattern matches secret-store-age.test.ts +
// credential-loader.test.ts (5 currently-skipped tests in this repo).
function ageInPath(): boolean {
  const r = spawnSync('which', ['age'], { encoding: 'utf8' });
  return r.status === 0 && r.stdout.trim().length > 0;
}

describe('cli: call.mjs --dev-bypass fail-loud on unwritable audit log (M2.7)', () => {
  it.skipIf(!ageInPath())('exits non-zero with diagnostic when .enforcement/ is read-only', async () => {
    // Build a sandboxed cwd with a read-only .enforcement/ dir. The dev-bypass
    // beacon path is `${cwd}/.enforcement/connector-audit.jsonl` — making the
    // dir 0500 forces EACCES on appendFileSync without affecting anything
    // else (PATH, node_modules) since we resolve CALL_MJS to its real path.
    const cwd = await fs.mkdtemp(
      path.join(os.tmpdir(), 'sutra-connectors-dev-bypass-'),
    );
    const enforcementDir = path.join(cwd, '.enforcement');
    await fs.mkdir(enforcementDir, { recursive: true });
    await fs.chmod(enforcementDir, 0o500);

    try {
      const r = spawnSync(
        'node',
        [CALL_MJS, 'slack', 'post-message', '--dev-bypass', '--channel=#x', '--text=hi'],
        {
          cwd,
          env: {
            ...process.env,
            HOME: tmpHome,
            SUTRA_DEV: '1',
          },
          encoding: 'utf8',
        },
      );

      // Fail-loud contract: non-zero exit, no silent bypass.
      expect(r.status).not.toBe(0);

      // The error surfaces via call.mjs's top-level try/catch (line ~119)
      // which prints `✘ <message>` for the EACCES from appendFileSync.
      // Accept any of: explicit EACCES, "permission denied", or generic
      // "✘" diagnostic — what matters is the loud failure, not the wording.
      const combined = `${r.stderr}\n${r.stdout}`;
      expect(combined).toMatch(/EACCES|permission denied|✘/i);

      // The fail-loud "beacon emitted" success line MUST NOT have printed —
      // that line only fires AFTER the appendFileSync succeeds.
      expect(r.stderr).not.toMatch(/beacon emitted to audit log/i);
    } finally {
      // Restore writable mode so afterEach + tmpdir cleanup can rm the tree.
      try { await fs.chmod(enforcementDir, 0o700); } catch { /* best effort */ }
      try { await fs.rm(cwd, { recursive: true, force: true }); } catch { /* best effort */ }
    }
  });

  it.skipIf(!ageInPath())('fails fast WITHOUT calling the slack backend', async () => {
    // Same setup, additional assertion: nothing should reach the network.
    // Because we set HOME to an empty tmpdir, ~/.sutra-connectors/oauth/slack.json
    // does not exist — but the fail-loud beacon writes happen BEFORE
    // credential read, so the test discriminates between "bypass exited
    // for missing-cred reason" vs "bypass exited for unwritable-audit reason".
    const cwd = await fs.mkdtemp(
      path.join(os.tmpdir(), 'sutra-connectors-dev-bypass-pre-'),
    );
    const enforcementDir = path.join(cwd, '.enforcement');
    await fs.mkdir(enforcementDir, { recursive: true });
    await fs.chmod(enforcementDir, 0o500);

    try {
      const r = spawnSync(
        'node',
        [CALL_MJS, 'slack', 'post-message', '--dev-bypass', '--channel=#x', '--text=hi'],
        {
          cwd,
          env: { ...process.env, HOME: tmpHome, SUTRA_DEV: '1' },
          encoding: 'utf8',
        },
      );

      // Discriminator: the post-beacon "no credential for slack" message
      // must NOT appear (we exited before reaching runDevBypass).
      expect(r.stderr).not.toMatch(/no credential for slack/i);
      expect(r.status).not.toBe(0);
    } finally {
      try { await fs.chmod(enforcementDir, 0o700); } catch { /* best effort */ }
      try { await fs.rm(cwd, { recursive: true, force: true }); } catch { /* best effort */ }
    }
  });
});
