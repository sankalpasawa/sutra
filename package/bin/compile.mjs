#!/usr/bin/env node
/**
 * Sutra Compiler (Phase 2 MVP — dry-run)
 *
 * Reads sutra/state/system.yaml (the source of truth) and reports divergence
 * between the declared hooks[] and what actually exists on disk in:
 *   - sutra/package/hooks/     (the shippable bundle — what install.mjs copies)
 *   - holding/hooks/           (the Asawa-local live copy — current runtime)
 *   - sutra/package/templates/settings.json (hook registration for companies)
 *
 * Dry-run only. Does NOT write files. Next chunks will add actual emission:
 *   - copy holding/hooks/<file> → sutra/package/hooks/<file>
 *   - synthesize settings.json from state.hooks[]
 *   - emit CLAUDE.md sections (DEPTH, INPUT ROUTING, etc.) from yaml
 *
 * Usage:
 *   node sutra/package/bin/compile.mjs           # dry-run divergence report
 *   node sutra/package/bin/compile.mjs --strict  # exit 1 if any divergence
 *
 * Phase 2 D-3 note: compiler obsoletes PROTO-018 auto-propagation (disabled).
 */

import { readFileSync, existsSync, statSync } from 'fs';
import { createHash } from 'crypto';
import { execSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Repo root resolution (codex P1 fix): env var > git rev-parse > package-root
// fallback. Avoids hard-coded monorepo layout so the compiler also works in
// installed sutra-os checkouts without a sibling `holding/` tree.
function resolveRepoRoot() {
  if (process.env.SUTRA_REPO_ROOT) return process.env.SUTRA_REPO_ROOT;
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
  } catch {
    // Last resort: assume we're in the bundled monorepo layout
    return join(__dirname, '../../..');
  }
}
const repoRoot = resolveRepoRoot();

// State file location: prefer sutra/state in monorepo, fall back to package-
// bundled state if we're running from an installed copy.
const statePath = existsSync(join(repoRoot, 'sutra/state/system.yaml'))
  ? join(repoRoot, 'sutra/state/system.yaml')
  : join(__dirname, '../../state/system.yaml');
if (!existsSync(statePath)) {
  console.error(`ERROR: state file not found at ${statePath}`);
  console.error('Set SUTRA_REPO_ROOT or run from a directory with sutra/state/system.yaml');
  process.exit(1);
}
const strict = process.argv.includes('--strict');

// Reuse the minimal YAML parser by spawning validate.mjs? Simpler: inline a
// small parse of the fields we need (hooks:, protocols:, directions:). We only
// need hook names and metadata here — not full YAML fidelity.
const src = readFileSync(statePath, 'utf-8');

// Extract hook entries from the YAML hooks: section. Matches the shape the
// state model writes: "  - file: <name>\n    event: <event>\n    ..."
function parseHookList(yaml) {
  const hooks = [];
  const lines = yaml.split('\n');
  let inHooks = false, inInvariants = false;
  let current = null;
  for (const raw of lines) {
    const line = raw.replace(/\r$/, '');
    if (/^hooks:\s*$/.test(line)) { inHooks = true; continue; }
    if (/^invariants:\s*$/.test(line)) { inHooks = false; inInvariants = true; continue; }
    if (!inHooks) continue;
    if (/^\S/.test(line) && !/^\s*#/.test(line) && !/^hooks:/.test(line)) {
      // Started a new top-level key → exit hooks section
      inHooks = false;
      if (current) { hooks.push(current); current = null; }
      continue;
    }
    // Entry start: "  - file: <name>"
    const m = line.match(/^\s*-\s*file:\s*(\S+)/);
    if (m) {
      if (current) hooks.push(current);
      current = { file: m[1], event: '', matcher: '', blocking: false, implements: [] };
      continue;
    }
    if (!current) continue;
    const evtM = line.match(/^\s+event:\s*(\S+)/);
    if (evtM) { current.event = evtM[1]; continue; }
    const matchM = line.match(/^\s+matcher:\s*["']?([^"'\n]*)["']?\s*$/);
    if (matchM) { current.matcher = matchM[1].trim(); continue; }
    const blkM = line.match(/^\s+blocking:\s*(true|false)/);
    if (blkM) { current.blocking = blkM[1] === 'true'; continue; }
    const implM = line.match(/^\s+implements:\s*\[([^\]]*)\]/);
    if (implM) {
      current.implements = implM[1].split(',').map(s => s.trim()).filter(Boolean);
      continue;
    }
  }
  if (current) hooks.push(current);
  return hooks;
}

function sizeOf(path) {
  try { return statSync(path).size; } catch { return -1; }
}

function fmtSize(n) {
  if (n < 0) return 'MISSING';
  if (n === 0) return 'EMPTY';
  if (n < 1024) return `${n}B`;
  return `${(n / 1024).toFixed(1)}K`;
}

// codex P2 fix: use content hash instead of size threshold — catches small
// but meaningful drift that a byte-size heuristic misses.
function hashOf(path) {
  try {
    const content = readFileSync(path);
    return createHash('sha1').update(content).digest('hex').slice(0, 12);
  } catch { return null; }
}

// codex P2 fix: check multiple candidate locations for the "live" hook —
// Asawa holding repo uses holding/hooks/, some hooks live in .claude/hooks/,
// some in .claude/hooks/sutra/ (nested installs). First non-empty wins.
function findLiveHook(repoRoot, file) {
  const candidates = [
    join(repoRoot, 'holding/hooks', file),
    join(repoRoot, '.claude/hooks', file),
    join(repoRoot, '.claude/hooks/sutra', file),
  ];
  for (const p of candidates) {
    if (existsSync(p) && statSync(p).size > 0) return { path: p, size: statSync(p).size };
  }
  return { path: null, size: -1 };
}

// codex P1 fix: parse settings.json as JSON and verify event+matcher
// alignment, not just filename substring. Falls back to naive includes if the
// file isn't valid JSON (defensive).
function checkSettingsWiring(settingsSrc, hook) {
  let parsed = null;
  try { parsed = JSON.parse(settingsSrc); } catch { return { registered: settingsSrc.includes(hook.file), matched: false }; }
  const events = parsed?.hooks || {};
  const eventGroups = events[hook.event] || [];
  for (const group of eventGroups) {
    const matcher = group.matcher || '';
    const entries = group.hooks || [];
    const refsThisFile = entries.some(e => (e.command || '').includes(hook.file));
    if (refsThisFile) {
      // Normalize matcher comparison — treat missing/empty as match-all
      const declared = (hook.matcher || '').trim();
      const actual = (matcher || '').trim();
      const matches = declared === actual || (declared === '' && actual === '');
      return { registered: true, matched: matches, actual, declared };
    }
  }
  return { registered: false, matched: false };
}

const hooks = parseHookList(src);
const settingsPath = join(repoRoot, 'sutra/package/templates/settings.json');
const settingsSrc = existsSync(settingsPath) ? readFileSync(settingsPath, 'utf-8') : '';

console.log('Sutra Compiler (Phase 2 MVP — dry-run)');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log(`State file: ${statePath}`);
console.log(`Declared hooks: ${hooks.length}`);
console.log('');

// Header
console.log(
  'hook'.padEnd(32) +
  'event'.padEnd(18) +
  'pkg'.padEnd(10) +
  'live'.padEnd(10) +
  'settings'.padEnd(10) +
  'status'
);
console.log('─'.repeat(96));

let divergences = 0;
for (const h of hooks) {
  const pkgPath = join(repoRoot, 'sutra/package/hooks', h.file);
  const pkgSize = sizeOf(pkgPath);
  const pkgHash = hashOf(pkgPath);
  const live = findLiveHook(repoRoot, h.file);
  const liveHash = live.path ? hashOf(live.path) : null;
  const wiring = checkSettingsWiring(settingsSrc, h);

  const statuses = [];
  if (pkgSize === -1) statuses.push('PKG_MISSING');
  else if (pkgSize === 0) statuses.push('PKG_EMPTY');
  if (live.size === -1) statuses.push('LIVE_MISSING');
  // codex P2 fix: content-hash drift detection, not byte-size heuristic
  if (pkgHash && liveHash && pkgHash !== liveHash) statuses.push('HASH_DRIFT');
  if (!wiring.registered) statuses.push('NOT_REGISTERED');
  else if (!wiring.matched && h.matcher) statuses.push('MATCHER_DRIFT');
  const status = statuses.length === 0 ? 'OK' : statuses.join(',');
  if (status !== 'OK') divergences++;

  const settingsCell = wiring.registered
    ? (wiring.matched ? 'yes' : 'drift')
    : 'no';

  console.log(
    h.file.padEnd(32) +
    (h.event || '?').padEnd(18) +
    fmtSize(pkgSize).padEnd(10) +
    fmtSize(live.size).padEnd(10) +
    settingsCell.padEnd(10) +
    status
  );
}

console.log('─'.repeat(96));
console.log(`Divergences: ${divergences}/${hooks.length}`);
console.log('');
console.log('Legend:');
console.log('  PKG_EMPTY       sutra/package/hooks/<file> is 0 bytes (no shippable content)');
console.log('  PKG_MISSING     sutra/package/hooks/<file> does not exist');
console.log('  LIVE_MISSING    no non-empty live copy in holding/hooks, .claude/hooks, or .claude/hooks/sutra');
console.log('  HASH_DRIFT      package sha1 ≠ live sha1 (any content difference, however small)');
console.log('  NOT_REGISTERED  hook file not referenced in sutra/package/templates/settings.json');
console.log('  MATCHER_DRIFT   wired in settings.json but with different matcher than state.hooks[] declares');
console.log('');
if (divergences === 0) {
  console.log('✓ No divergence — package bundle matches state.');
  process.exit(0);
} else {
  console.log(`✗ ${divergences} divergence(s). Next chunk: actual emission will reconcile.`);
  process.exit(strict ? 1 : 0);
}
