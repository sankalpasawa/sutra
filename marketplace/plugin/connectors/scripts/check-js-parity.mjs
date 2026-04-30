#!/usr/bin/env node
// Release prerelease guard — asserts every lib/*.ts (excluding .test.ts) has
// a matching committed lib/*.js sibling. Plugin install path does NOT run
// `npm install`, so .js artifacts must ship in the git tree.
//
// Exits non-zero if any .js is missing.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..');

const dirs = ['lib', 'lib/backends'];
const missing = [];

for (const d of dirs) {
  const full = path.join(root, d);
  if (!fs.existsSync(full)) continue;
  for (const f of fs.readdirSync(full)) {
    if (!f.endsWith('.ts') || f.endsWith('.test.ts') || f.endsWith('.d.ts')) continue;
    const js = f.replace(/\.ts$/, '.js');
    if (!fs.existsSync(path.join(full, js))) {
      missing.push(`${d}/${f} -> ${d}/${js}`);
    }
  }
}

if (missing.length > 0) {
  console.error('FAIL: .ts files without matching .js:');
  for (const m of missing) console.error('  ' + m);
  process.exit(1);
}

console.log('PASS: all .ts have matching .js sibling.');
