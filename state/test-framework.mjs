/**
 * Sutra Test Framework
 *
 * Data-driven testing for the enforcement stack. Auto-adjusts to system.yaml:
 * when a new hook / protocol / direction is added, tests are generated from
 * the state model's declared mechanism + test fields.
 *
 * Used by:
 *   - sutra/state/run-tests.mjs (full-stack regression runner)
 *   - Individual test files (when a rule needs bespoke logic beyond the
 *     auto-generated template — opt-in, referenced from system.yaml `test:`)
 *
 * Primitives:
 *   simulateHook(hookFile, toolName, filePath, opts)  → { stdout, stderr, exitCode, side_effects }
 *   assertBlocked(result, [pattern])                   → throw on pass
 *   assertAllowed(result)                              → throw on block
 *   assertLogged(logFile, pattern, sinceLines)         → throw if pattern absent
 *   clearMarkers()                                     → reset .claude markers
 *   withMarkers(scope, fn)                             → scoped marker lifecycle
 *
 * Zero external deps (uses node stdlib + sh). jq optional for robust JSON.
 */

import { execSync } from 'child_process';
import { readFileSync, writeFileSync, existsSync, rmSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ─── Repo root discovery (same logic as validate.mjs) ───────────────────────
let REPO_ROOT;
try {
  REPO_ROOT = execSync('git rev-parse --show-toplevel', { cwd: __dirname, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
} catch (e) {
  REPO_ROOT = join(__dirname, '..', '..');
}
if (!existsSync(join(REPO_ROOT, 'holding')) && existsSync(join(REPO_ROOT, '..', 'holding'))) {
  REPO_ROOT = join(REPO_ROOT, '..');
}
export { REPO_ROOT };

// ─── Hook file resolution — same search paths as validate.mjs ───────────────
const HOOK_PATHS = [
  'holding/hooks',
  'sutra/package/hooks',
  '.claude/hooks/sutra',
  'package/hooks',
];

export function resolveHook(hookFile) {
  for (const p of HOOK_PATHS) {
    const full = join(REPO_ROOT, p, hookFile);
    if (existsSync(full)) return full;
  }
  return null;
}

// ─── Marker lifecycle ────────────────────────────────────────────────────────
const MARKER_FILES = [
  '.claude/input-routed',
  '.claude/depth-registered',
  '.claude/depth-assessed',
  '.claude/sutra-deploy-depth5',
];

export function clearMarkers() {
  for (const f of MARKER_FILES) {
    const full = join(REPO_ROOT, f);
    if (existsSync(full)) rmSync(full, { force: true });
  }
}

export function setMarkers(opts = {}) {
  const ts = Math.floor(Date.now() / 1000);
  if (opts.routing !== false) writeFileSync(join(REPO_ROOT, '.claude/input-routed'), `${ts}\n`);
  if (opts.depth !== false) writeFileSync(join(REPO_ROOT, '.claude/depth-registered'), `${opts.depth || 5} ${ts} test\n`);
  if (opts.sutraDepth5 !== false) writeFileSync(join(REPO_ROOT, '.claude/sutra-deploy-depth5'), `${ts}\n`);
}

// Snapshot → restore pattern so test setup doesn't clobber real markers
export function snapshotMarkers() {
  const snap = {};
  for (const f of MARKER_FILES) {
    const full = join(REPO_ROOT, f);
    if (existsSync(full)) snap[f] = readFileSync(full, 'utf8');
  }
  return snap;
}

export function restoreMarkers(snap) {
  for (const f of MARKER_FILES) {
    const full = join(REPO_ROOT, f);
    if (snap[f] !== undefined) writeFileSync(full, snap[f]);
    else if (existsSync(full)) rmSync(full, { force: true });
  }
}

// ─── Hook simulation ────────────────────────────────────────────────────────
/**
 * Invoke a hook script with a simulated Claude Code tool call payload.
 *
 * @param {string} hookFile   e.g. 'dispatcher-pretool.sh'
 * @param {string} toolName   'Edit' | 'Write' | 'Bash' | etc.
 * @param {object|string} input  If object: passed as tool_input JSON. If string for Bash, treated as command.
 * @param {object} opts
 *   opts.env          extra env vars
 *   opts.cwd          default REPO_ROOT
 *   opts.timeoutMs    default 10s
 * @returns {object}   { stdout, stderr, exitCode }
 */
export function simulateHook(hookFile, toolName, input, opts = {}) {
  const hookPath = resolveHook(hookFile);
  if (!hookPath) {
    throw new Error(`hook not found in any search path: ${hookFile}`);
  }

  const toolInput = typeof input === 'string' && toolName === 'Bash'
    ? { command: input }
    : typeof input === 'string'
      ? { file_path: input }
      : input;

  const stdinJson = JSON.stringify({
    tool_name: toolName,
    tool_input: toolInput,
  });

  const env = {
    ...process.env,
    CLAUDE_PROJECT_DIR: REPO_ROOT,
    TOOL_NAME: toolName,
    ...(opts.env || {}),
  };

  let stdout = '', stderr = '', exitCode = 0;
  try {
    stdout = execSync(`bash "${hookPath}"`, {
      input: stdinJson,
      env,
      cwd: opts.cwd || REPO_ROOT,
      timeout: opts.timeoutMs || 10000,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    stdout = (e.stdout || '').toString();
    stderr = (e.stderr || '').toString();
    exitCode = e.status ?? 1;
  }
  return { stdout, stderr, exitCode };
}

// ─── Assertions ──────────────────────────────────────────────────────────────
export function assertBlocked(result, pattern) {
  if (result.exitCode === 0) {
    throw new Error(`expected block (non-zero exit) but got exit 0\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  }
  if (pattern && !result.stdout.includes(pattern) && !result.stderr.includes(pattern)) {
    throw new Error(`expected block message containing "${pattern}" but not found\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  }
}

export function assertAllowed(result) {
  if (result.exitCode !== 0) {
    throw new Error(`expected allowed (exit 0) but got exit ${result.exitCode}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  }
}

export function assertLogged(logFile, pattern, sinceLines = null) {
  const logPath = join(REPO_ROOT, logFile);
  if (!existsSync(logPath)) {
    throw new Error(`log file does not exist: ${logFile}`);
  }
  const content = readFileSync(logPath, 'utf8');
  const lines = content.split('\n');
  const scope = sinceLines != null ? lines.slice(sinceLines) : lines;
  const found = scope.some(l => l.includes(pattern));
  if (!found) {
    throw new Error(`expected log entry matching "${pattern}" in ${logFile}\nscope: ${scope.length} lines (since ${sinceLines})\nlast 3: ${scope.slice(-3).join(' | ')}`);
  }
}

export function currentLogLineCount(logFile) {
  const logPath = join(REPO_ROOT, logFile);
  if (!existsSync(logPath)) return 0;
  return readFileSync(logPath, 'utf8').split('\n').length;
}

// ─── Test result format ─────────────────────────────────────────────────────
export function testResult(name, passed, details) {
  return { name, passed, details: details || '' };
}
