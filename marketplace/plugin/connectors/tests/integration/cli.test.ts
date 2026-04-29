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
