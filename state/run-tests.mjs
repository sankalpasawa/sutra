#!/usr/bin/env node
/**
 * Sutra Test Runner
 *
 * Walks system.yaml, for each declared rule with a mechanism, runs the
 * appropriate auto-generated or bespoke test. Reports PASS/FAIL per rule.
 *
 * Auto-adjusts: when new hook/protocol/direction is added to system.yaml,
 * this runner picks it up without code changes. Non-duplication: the runner
 * IS the test suite. Individual test files only exist when a rule needs
 * bespoke logic beyond the auto-generated template.
 *
 * Usage: node sutra/state/run-tests.mjs [--rule=ID] [--verbose]
 * Exit 0 if all PASS. Exit 1 on any FAIL.
 */

import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  simulateHook, assertBlocked, assertAllowed, assertLogged,
  clearMarkers, setMarkers, snapshotMarkers, restoreMarkers,
  currentLogLineCount, resolveHook, REPO_ROOT, testResult,
} from './test-framework.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- Load state model -------------------------------------------------------
// Reuse validate.mjs's parser by importing it would require a refactor;
// for the runner, we parse YAML inline (minimal — same subset as validate.mjs).
function parseYaml(src) {
  // Shell out to python for robust YAML when available (zero-dep preferred).
  // Here we just import via a tiny inline parser by reusing validate.mjs's
  // logic via shell exec.
  // Simplified: use node to require validate.mjs' parseYaml via import.
  return null; // placeholder — see below
}

// Easier: call validate.mjs to get the parsed state as JSON via a helper.
// For correctness, we re-implement the minimal parser here by delegating.
import { readFileSync as _read } from 'fs';
const validateSrc = _read(join(__dirname, 'validate.mjs'), 'utf8');

// Quick-and-dirty: use python yq if available to convert YAML → JSON.
// Fall back to sh if node modules absent.
import { execSync } from 'child_process';
let state;
try {
  if (execSync('command -v yq', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()) {
    const json = execSync(`yq -o=json '.' "${join(__dirname, 'system.yaml')}"`, { encoding: 'utf8' });
    state = JSON.parse(json);
  }
} catch (e) { /* yq missing */ }

if (!state) {
  // Fall back: invoke validate.mjs with a dump flag — easier: execute it as a
  // child, then parse our own in-memory structure. For v1, do a minimal YAML
  // parser here that matches validate.mjs's shape.
  const yamlSrc = readFileSync(join(__dirname, 'system.yaml'), 'utf8');
  state = parseYamlMinimal(yamlSrc);
}

// ─── Minimal YAML parser (same subset as validate.mjs — copy of the function
//     to keep this file standalone) ────────────────────────────────────────
function parseYamlMinimal(src) {
  const lines = src.split('\n');
  const root = {};
  const stack = [{ indent: -1, obj: root, key: null, arr: null }];
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    const m = line.match(/^(\s*)(.*)$/);
    const indent = m[1].length;
    let rest = m[2];
    const hashIdx = findCommentStart(rest);
    if (hashIdx >= 0) rest = rest.slice(0, hashIdx).trimEnd();
    if (!rest) continue;
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const parent = stack[stack.length - 1];
    if (rest.startsWith('- ')) {
      const item = rest.slice(2).trim();
      if (!parent.arr) {
        parent.obj[parent.key] = parent.obj[parent.key] || [];
        parent.arr = parent.obj[parent.key];
      }
      if (item.includes(':')) {
        const [k, ...vParts] = item.split(':');
        const v = vParts.join(':').trim();
        const newObj = {};
        if (v) newObj[k.trim()] = parseScalar(v);
        parent.arr.push(newObj);
        stack.push({ indent, obj: newObj, key: null, arr: null });
      } else {
        parent.arr.push(parseScalar(item));
      }
      continue;
    }
    const colonIdx = rest.indexOf(':');
    if (colonIdx === -1) continue;
    const key = rest.slice(0, colonIdx).trim();
    const value = rest.slice(colonIdx + 1).trim();
    if (value === '' || value === null) {
      parent.obj[key] = {};
      stack.push({ indent, obj: parent.obj, key, arr: null });
      for (let j = i + 1; j < lines.length; j++) {
        const nxt = lines[j];
        if (!nxt.trim() || nxt.trim().startsWith('#')) continue;
        const nxtIndent = nxt.match(/^(\s*)/)[1].length;
        if (nxtIndent <= indent) break;
        if (nxt.trim().startsWith('- ')) {
          parent.obj[key] = [];
          stack[stack.length - 1].arr = parent.obj[key];
        } else {
          parent.obj[key] = {};
          stack[stack.length - 1].obj = parent.obj[key];
        }
        break;
      }
    } else {
      stack[stack.length - 1].obj[key] = parseScalar(value);
    }
  }
  return root;
}
function findCommentStart(s) {
  let q = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (q) { if (c === q && s[i - 1] !== '\\') q = null; }
    else { if (c === '"' || c === "'") q = c; else if (c === '#') return i; }
  }
  return -1;
}
function parseScalar(v) {
  if (v === null || v === undefined) return v;
  v = String(v).trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) return v.slice(1, -1);
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v === 'null' || v === '~') return null;
  if (/^-?[0-9]+$/.test(v)) return parseInt(v, 10);
  if (/^-?[0-9]+\.[0-9]+$/.test(v)) return parseFloat(v);
  if (v.startsWith('[') && v.endsWith(']')) {
    const inner = v.slice(1, -1).trim();
    if (!inner) return [];
    return inner.split(',').map(s => parseScalar(s.trim()));
  }
  return v;
}

// ─── Auto-generated tests per rule type ─────────────────────────────────────
//
// For each active+hard rule with mechanism_type=hook:
//   Negative test: no marker → expect block with the rule's error text
//   Positive test: marker present + correct path → expect allow + log entry
//
// For mechanism_type=agent-behavior: skip auto-test (no runnable harness yet)
// For mechanism_type=reconciler: run validate.mjs + assert no inverse-fail
// For mechanism_type=compiler: skip until Phase 2 compiler ships
//
// Rules with bespoke test scripts (declared via `test:`) run that script
// instead of the auto-generated template.

const results = [];

function runAutoHookTest(rule, hookForRule) {
  const ruleId = rule.id;
  // Pick a representative file path based on what the hook gates on.
  // For D27 (sutra-deploy): use sutra/ or */os/ path.
  // For D28 routing/depth: use any deliverable path.
  const samplePath = ruleId === 'D27' || ruleId === 'PROTO-013'
    ? `${REPO_ROOT}/sutra/state/.__test_sample.md`
    : `${REPO_ROOT}/tmp/__test_sample.md`;

  const snap = snapshotMarkers();
  try {
    // Negative: no markers → expect gate to block on its specific check
    clearMarkers();
    const neg = simulateHook(hookForRule.file, 'Write', samplePath);
    // Positive: markers set → gate allows
    setMarkers();
    const pos = simulateHook(hookForRule.file, 'Write', samplePath);

    // Assertion depends on rule. For D27 specifically: negative must block.
    if (ruleId === 'D27') {
      try {
        assertBlocked(neg, 'SUTRA→COMPANY');
        assertAllowed(pos);
        results.push(testResult(`${ruleId} (auto)`, true, 'block without marker ✓, allow with marker ✓'));
      } catch (e) {
        results.push(testResult(`${ruleId} (auto)`, false, e.message));
      }
    } else if (ruleId === 'D28') {
      try {
        assertBlocked(neg, 'ROUTING');
        assertAllowed(pos);
        results.push(testResult(`${ruleId} (auto)`, true, 'block without marker ✓, allow with marker ✓'));
      } catch (e) {
        results.push(testResult(`${ruleId} (auto)`, false, e.message));
      }
    } else {
      // Soft rules without rule-specific block/allow assertions: we can only
      // prove the hook is invokable, NOT that its logic catches violations.
      // Codex P2 2026-04-16: mark these PARTIAL, not GREEN — don't false-green
      // hard rules whose mechanism-specific branch was never exercised.
      try {
        assertAllowed(pos);
        results.push(testResult(`${ruleId} (auto)`, true, 'PARTIAL: hook invokable only; rule-specific logic not exercised'));
      } catch (e) {
        results.push(testResult(`${ruleId} (auto)`, false, e.message));
      }
    }
  } finally {
    restoreMarkers(snap);
  }
}

function runBespokeTest(rule) {
  try {
    execSync(`bash "${join(REPO_ROOT, rule.test)}"`, { stdio: ['ignore', 'pipe', 'pipe'], cwd: REPO_ROOT });
    results.push(testResult(`${rule.id} (bespoke: ${rule.test})`, true, 'test exited 0'));
  } catch (e) {
    results.push(testResult(`${rule.id} (bespoke: ${rule.test})`, false, `exit ${e.status}: ${e.stdout || e.stderr || ''}`.slice(0, 400)));
  }
}

function runValidator() {
  try {
    execSync(`node "${join(__dirname, 'validate.mjs')}"`, { stdio: ['ignore', 'pipe', 'pipe'], cwd: REPO_ROOT });
    results.push(testResult('state-model validator', true, 'validate.mjs exit 0'));
  } catch (e) {
    results.push(testResult('state-model validator', false, `exit ${e.status}: ${(e.stdout || e.stderr || '').toString().slice(0, 400)}`));
  }
}

// ─── Main ───────────────────────────────────────────────────────────────────
runValidator();

const hooks = state.hooks || [];
const hooksById = new Map();
for (const h of hooks) {
  for (const ref of h.implements || []) {
    if (!hooksById.has(ref)) hooksById.set(ref, []);
    hooksById.get(ref).push(h);
  }
}

const active = [
  ...((state.protocols || []).filter(p => p.status === 'active')),
  ...((state.directions?.core || []).filter(d => d.status === 'active')),
  ...((state.directions?.ergonomics || []).filter(d => d.status === 'active')),
];

const onlyRule = process.argv.find(a => a.startsWith('--rule='))?.split('=')[1];

for (const rule of active) {
  if (onlyRule && rule.id !== onlyRule) continue;
  if (rule.test) {
    runBespokeTest(rule);
  } else {
    const candidates = hooksById.get(rule.id) || [];
    if (candidates.length > 0) {
      runAutoHookTest(rule, candidates[0]);
    } else {
      // No hook, no bespoke test — soft or agent-behavior rule
      results.push(testResult(rule.id, true, 'skipped (no hook/bespoke test — soft or agent-behavior)'));
    }
  }
}

// ─── Coverage matrix — every active rule → tests that cover it ──────────────
// Industry pattern: DO-178C requirements-traceability matrix. Catches rules
// that exist in doctrine but have no test coverage.
//
// Codex P2 2026-04-16 fix: skipped results → UNCOVERED (not GREEN). Otherwise
// --strict green-lights unshipped hard mechanisms. Skipped is the absence of
// coverage, not a pass.
const coverage = [];
for (const rule of active) {
  const covered = results.find(r => r.name.startsWith(rule.id));
  const enforcement = rule.enforcement || 'unknown';
  const scope = rule.scope || '';
  const isSkipped = covered?.details.includes('skipped');
  const isPartial = covered?.details.includes('PARTIAL');
  let status;
  if (!covered) status = 'UNCOVERED';
  else if (isSkipped) status = 'UNCOVERED';
  else if (!covered.passed) status = 'RED';
  else if (isPartial) status = 'PARTIAL';
  else status = 'GREEN';
  coverage.push({
    id: rule.id,
    enforcement,
    scope,
    covered_by: covered && !isSkipped ? covered.name : null,
    status,
    skip_reason: isSkipped ? covered.details : null,
  });
}

// ─── Strict / output-format flags ───────────────────────────────────────────
const strict = process.argv.includes('--strict');
const jsonOut = process.argv.includes('--json');
const junitOut = process.argv.includes('--junit');

// ─── Report ─────────────────────────────────────────────────────────────────
const pass = results.filter(r => r.passed).length;
const fail = results.filter(r => !r.passed).length;
const skipped = results.filter(r => r.details.includes('skipped')).length;
const hardUncovered = coverage.filter(c => c.enforcement === 'hard' && c.status === 'UNCOVERED').length;

if (jsonOut) {
  const out = {
    summary: { pass, fail, skipped, total: results.length, hard_uncovered: hardUncovered },
    results,
    coverage,
    timestamp: new Date().toISOString(),
  };
  console.log(JSON.stringify(out, null, 2));
} else if (junitOut) {
  // JUnit XML — consumable by CI (GitLab, Jenkins, etc.)
  const esc = (s) => String(s).replace(/[<>&'"]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[c]);
  console.log('<?xml version="1.0" encoding="UTF-8"?>');
  console.log(`<testsuite name="sutra-state" tests="${results.length}" failures="${fail}" skipped="${skipped}">`);
  for (const r of results) {
    if (r.details.includes('skipped')) {
      console.log(`  <testcase classname="sutra.state" name="${esc(r.name)}"><skipped message="${esc(r.details)}"/></testcase>`);
    } else if (r.passed) {
      console.log(`  <testcase classname="sutra.state" name="${esc(r.name)}"/>`);
    } else {
      console.log(`  <testcase classname="sutra.state" name="${esc(r.name)}"><failure message="${esc(r.details.slice(0, 200))}"/></testcase>`);
    }
  }
  console.log('</testsuite>');
} else {
  console.log('');
  console.log('SUTRA TEST FRAMEWORK — RESULTS');
  console.log('━'.repeat(70));
  for (const r of results) {
    const icon = r.passed ? '✓' : '✗';
    const status = r.passed ? 'PASS' : 'FAIL';
    console.log(`  ${icon} ${status}  ${r.name.padEnd(42)}  ${r.details.slice(0, 80)}`);
  }
  console.log('━'.repeat(70));
  console.log(`  ${pass} pass, ${fail} fail, ${skipped} skipped  (of ${results.length} total)`);
  console.log('');
  console.log('COVERAGE MATRIX — active rules vs test coverage');
  console.log('━'.repeat(70));
  for (const c of coverage) {
    const icon = c.status === 'GREEN' ? '✓' : (c.status === 'RED' ? '✗' : '⚠');
    console.log(`  ${icon} ${c.status.padEnd(10)} ${c.id.padEnd(12)} enforcement=${c.enforcement.padEnd(8)} ${c.skip_reason ? 'skipped' : (c.covered_by || 'no test')}`);
  }
  console.log('━'.repeat(70));
  console.log(`  hard rules uncovered: ${hardUncovered}  (must be 0 by phase-3)`);
  console.log('');
}

let exitCode = fail > 0 ? 1 : 0;
if (strict && hardUncovered > 0) exitCode = 1;
process.exit(exitCode);
