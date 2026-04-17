#!/usr/bin/env node
/**
 * gen-protocols-md — reconcile PROTOCOLS.md with system.yaml
 *
 * Problem it solves (PROTO-000 drift):
 *   sutra/state/system.yaml is the typed source of truth (what validate.mjs
 *   and run-tests.mjs check). sutra/layer2-operating-system/PROTOCOLS.md is
 *   the prose clients read. They drift — protocols retired in yaml can still
 *   read as SHIPPED in prose. PROTO-000 forbids prose-only protocols.
 *
 * What this script does:
 *   Rewrites the "## Protocol Index" table in PROTOCOLS.md (between the
 *   GEN markers below) from the protocols[] entries in system.yaml. Every
 *   row shows id, name, yaml status, enforcement, mechanism path, test
 *   path, last_updated (meta.updated). All content OUTSIDE the markers is
 *   preserved verbatim (historical prose for retired protocols stays, with
 *   [RETIRED]/[ABSORBED] markers inserted by the reconciliation author —
 *   not by this script).
 *
 * Idempotent:
 *   Running twice produces no diff. The INDEX is fully derived from yaml;
 *   section order + content are stable.
 *
 * Usage:
 *   node sutra/package/bin/gen-protocols-md.mjs
 *
 * Exit 0 on success (file unchanged or successfully rewritten).
 * Exit 1 on read/parse/IO failure.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { execSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveRepoRoot() {
  if (process.env.SUTRA_REPO_ROOT) return process.env.SUTRA_REPO_ROOT;
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
  } catch {
    return join(__dirname, '../../..');
  }
}
const repoRoot = resolveRepoRoot();

const statePath = join(repoRoot, 'sutra/state/system.yaml');
const mdPath = join(repoRoot, 'sutra/layer2-operating-system/PROTOCOLS.md');

if (!existsSync(statePath)) {
  console.error(`ERROR: ${statePath} not found`);
  process.exit(1);
}
if (!existsSync(mdPath)) {
  console.error(`ERROR: ${mdPath} not found`);
  process.exit(1);
}

// ── Minimal YAML reader for the protocols[] + meta.updated fields ───────────
// Purpose-built to match the exact shape sutra/state/system.yaml uses.
// Not a general YAML parser — mirrors the style of validate.mjs.
function parseState(src) {
  const lines = src.split('\n');
  const protocols = [];
  let meta_updated = '';
  let inMeta = false, inProtocols = false;
  let current = null;
  let sawFirstProtocol = false;

  for (const raw of lines) {
    const line = raw.replace(/\r$/, '');
    // top-level section marker
    if (/^meta:\s*$/.test(line)) { inMeta = true; inProtocols = false; continue; }
    if (/^protocols:\s*$/.test(line)) {
      if (current) protocols.push(current);
      current = null;
      inMeta = false;
      inProtocols = true;
      sawFirstProtocol = false;
      continue;
    }
    // any new top-level key (non-indented, non-comment, not a list dash) ends
    // both sections
    if (/^[A-Za-z_]/.test(line)) {
      if (inProtocols && current) { protocols.push(current); current = null; }
      inMeta = false;
      inProtocols = false;
      continue;
    }

    if (inMeta) {
      const m = line.match(/^\s+updated:\s*"?([^"#\n]+)"?\s*$/);
      if (m) meta_updated = m[1].trim();
      continue;
    }

    if (!inProtocols) continue;
    // ignore comment lines inside protocols:
    if (/^\s*#/.test(line)) continue;

    // New entry: "  - id: PROTO-XXX"
    const idM = line.match(/^\s*-\s*id:\s*(\S+)/);
    if (idM) {
      if (current) protocols.push(current);
      current = { id: idM[1], name: '', status: '', enforcement: '', mechanism: '', test: '', reason: '' };
      sawFirstProtocol = true;
      continue;
    }
    if (!current) continue;

    const kv = line.match(/^\s{4,}(\w+):\s*(.*)$/);
    if (!kv) continue;
    const key = kv[1];
    let val = kv[2].trim();
    // strip inline comment
    val = stripInlineComment(val);
    // strip surrounding quotes
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (key in current) current[key] = val;
  }
  if (current) protocols.push(current);
  return { protocols, meta_updated };
}

function stripInlineComment(s) {
  let inQuote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inQuote) {
      if (c === inQuote && s[i - 1] !== '\\') inQuote = null;
    } else {
      if (c === '"' || c === "'") inQuote = c;
      else if (c === '#') return s.slice(0, i).trimEnd();
    }
  }
  return s;
}

// ── Build index table + header ──────────────────────────────────────────────
const { protocols, meta_updated } = parseState(readFileSync(statePath, 'utf-8'));

if (protocols.length === 0) {
  console.error('ERROR: no protocols parsed from system.yaml');
  process.exit(1);
}

function truncate(s, n) {
  if (!s) return '';
  s = s.replace(/\|/g, '\\|');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

function rowFor(p) {
  const status = (p.status || '').toUpperCase();
  const enf = (p.enforcement || '—').toUpperCase();
  // retired/absorbed protocols have no mechanism/test — show "—"
  const mech = p.mechanism ? truncate(p.mechanism, 60) : '—';
  const test = p.test ? truncate(p.test, 50) : '—';
  return `| ${p.id} | ${truncate(p.name, 50)} | ${status} | ${enf} | ${mech} | ${test} | ${meta_updated} |`;
}

const header = [
  '> WARNING: GENERATED section — source of truth is `sutra/state/system.yaml`.',
  '> Hand-edits below the INDEX table may be overwritten on next reconcile.',
  '> Regenerate: `node sutra/package/bin/gen-protocols-md.mjs`',
  '>',
  '> Prose sections below the INDEX are historical record. RETIRED/ABSORBED',
  '> protocols are marked inline but not deleted — they document what once',
  '> shipped and why the system moved past them.',
].join('\n');

const indexLines = [
  '## Protocol Index',
  '',
  header,
  '',
  `_Last reconciled from system.yaml: **${meta_updated}** · ${protocols.length} protocols total_`,
  '',
  '| ID | Name | yaml_status | enforcement | mechanism | test | last_updated |',
  '|----|------|-------------|-------------|-----------|------|--------------|',
  ...protocols.map(rowFor),
  '',
  '**Status legend**: ACTIVE = shipped and enforced per mechanism · RETIRED = removed, see `reason` in system.yaml · ABSORBED = folded into another protocol (see pointer below)',
  '',
  '**Enforcement legend**: HARD = blocking hook (exit 2 on violation) · SOFT = advisory / agent-behavior',
];

// ── Splice the INDEX into PROTOCOLS.md between markers ──────────────────────
const START = '<!-- GEN:PROTOCOL-INDEX:START -->';
const END = '<!-- GEN:PROTOCOL-INDEX:END -->';

let md = readFileSync(mdPath, 'utf-8');

const generated = [START, ...indexLines, END].join('\n');

if (md.includes(START) && md.includes(END)) {
  // Replace between markers (inclusive)
  const before = md.slice(0, md.indexOf(START));
  const after = md.slice(md.indexOf(END) + END.length);
  md = before + generated + after;
} else {
  // First run: replace the hand-written "## Protocol Index" block. We detect
  // the original block as everything from "## Protocol Index" to the first
  // "---" separator that follows it.
  const idxHeaderRe = /\n## Protocol Index\b[\s\S]*?\n---\n/;
  if (idxHeaderRe.test(md)) {
    md = md.replace(idxHeaderRe, `\n${generated}\n\n---\n`);
  } else {
    // Fallback: insert after the first blank line past the H1
    const parts = md.split('\n\n');
    if (parts.length >= 2) {
      parts.splice(2, 0, generated);
      md = parts.join('\n\n');
    } else {
      md = md + '\n\n' + generated + '\n';
    }
  }
}

// Normalize trailing newlines (single newline at EOF)
md = md.replace(/\n+$/, '\n');

writeFileSync(mdPath, md, 'utf-8');

// Summary output
const counts = protocols.reduce((acc, p) => {
  const s = (p.status || 'unknown').toLowerCase();
  acc[s] = (acc[s] || 0) + 1;
  return acc;
}, {});
const summary = Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(', ');
console.log(`gen-protocols-md: wrote ${mdPath}`);
console.log(`  protocols: ${protocols.length} (${summary})`);
console.log(`  meta.updated: ${meta_updated}`);
process.exit(0);
