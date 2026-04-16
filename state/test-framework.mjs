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

// ─── Hook file resolution — codex P1 round 2 (2026-04-16) ──────────────────
// The test must validate the hook that the runtime actually invokes. Read
// .claude/settings.json and derive the search root from its command strings.
// Fall back to a layered search when settings don't exist.
//
// Also: detect drift between copies and fail loudly if they diverge.
const DEFAULT_HOOK_PATHS = [
  'holding/hooks',         // what .claude/settings.json in holding invokes today
  'sutra/package/hooks',   // shipping source (companies install from here)
  '.claude/hooks/sutra',   // installed in company sessions
  'package/hooks',         // standalone sutra checkout
];

function readSettings() {
  const settingsPath = join(REPO_ROOT, '.claude/settings.json');
  if (!existsSync(settingsPath)) return null;
  try { return JSON.parse(readFileSync(settingsPath, 'utf8')); } catch (e) { return null; }
}

function hookRootFromSettings() {
  const s = readSettings();
  if (!s?.hooks) return null;
  for (const event of Object.values(s.hooks)) {
    for (const rule of event) {
      for (const h of rule.hooks || []) {
        const m = (h.command || '').match(/bash\s+([^\s]+\/hooks(?:\/[^\s/]+)?)\/[^\s]+\.sh/);
        if (m) return m[1];  // e.g., "holding/hooks"
      }
    }
  }
  return null;
}

export function resolveHook(hookFile) {
  // Priority 1: whatever .claude/settings.json actually invokes
  const runtimeRoot = hookRootFromSettings();
  const orderedPaths = runtimeRoot
    ? [runtimeRoot, ...DEFAULT_HOOK_PATHS.filter(p => p !== runtimeRoot)]
    : DEFAULT_HOOK_PATHS;
  for (const p of orderedPaths) {
    const full = join(REPO_ROOT, p, hookFile);
    if (existsSync(full)) return full;
  }
  return null;
}

// Drift detector — reports hook files that exist in multiple trees but differ.
export function detectHookDrift() {
  const seen = new Map();  // hookFile -> { path, content }[]
  for (const p of DEFAULT_HOOK_PATHS) {
    const dir = join(REPO_ROOT, p);
    if (!existsSync(dir)) continue;
    const files = execSync(`ls "${dir}" 2>/dev/null || true`, { encoding: 'utf8' }).split('\n').filter(f => f.endsWith('.sh'));
    for (const f of files) {
      const full = join(dir, f);
      if (!existsSync(full) || !statSync(full).isFile()) continue;
      const content = readFileSync(full, 'utf8');
      if (!seen.has(f)) seen.set(f, []);
      seen.get(f).push({ path: p, content });
    }
  }
  const drift = [];
  for (const [file, copies] of seen) {
    if (copies.length < 2) continue;
    const first = copies[0].content;
    const differs = copies.filter(c => c.content !== first);
    if (differs.length > 0) {
      drift.push({ file, paths: copies.map(c => c.path) });
    }
  }
  return drift;
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
