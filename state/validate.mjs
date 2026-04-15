#!/usr/bin/env node
/**
 * Sutra State Validator
 *
 * Checks:
 *  1. system.yaml parses as valid YAML
 *  2. Conforms to schema.json (minimal in-file validator — no external deps)
 *  3. Meta invariants:
 *     - active protocol count <= meta.caps.protocols_active_max
 *     - active direction count (core + ergonomics) <= meta.caps.directions_active_max
 *     - every active+hard protocol has a mechanism
 *     - every active+hard direction has a mechanism
 *     - every hook's implements[] references exist in protocols or directions
 *     - invariants with severity=fail have at least one enforces[] ref OR notes
 *
 * Usage: node sutra/state/validate.mjs [path/to/system.yaml]
 * Exit 0 if valid. Exit 1 on failure.
 */

import { readFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const yamlPath = process.argv[2] || join(__dirname, 'system.yaml');

if (!existsSync(yamlPath)) {
  console.error(`ERROR: ${yamlPath} not found`);
  process.exit(1);
}

// --- Minimal YAML parser for our subset (avoid npm dep for Phase 1) ---------
// This handles: scalars, arrays, nested objects, quoted strings, comments.
// NOT a general YAML parser — it assumes the specific shape we write.
function parseYaml(src) {
  const lines = src.split('\n');
  const root = {};
  const stack = [{ indent: -1, obj: root, key: null, arr: null }];

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    const raw = line;
    // strip comments but preserve inline quoted values
    const m = line.match(/^(\s*)(.*)$/);
    const indent = m[1].length;
    let rest = m[2];
    // strip trailing comment (naive: not inside quotes)
    const hashIdx = findCommentStart(rest);
    if (hashIdx >= 0) rest = rest.slice(0, hashIdx).trimEnd();
    if (!rest) continue;

    // pop stack until parent indent < current
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) {
      stack.pop();
    }
    const parent = stack[stack.length - 1];

    // array item?
    if (rest.startsWith('- ')) {
      const item = rest.slice(2).trim();
      if (!parent.arr) {
        // parent.obj[parent.key] should become an array
        parent.obj[parent.key] = parent.obj[parent.key] || [];
        parent.arr = parent.obj[parent.key];
      }
      if (item.includes(':')) {
        // object item: "- key: value" → new object with that key
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

    // key: value
    const colonIdx = rest.indexOf(':');
    if (colonIdx === -1) continue;
    const key = rest.slice(0, colonIdx).trim();
    const value = rest.slice(colonIdx + 1).trim();

    if (value === '' || value === null) {
      // nested object or array (determined by next non-empty line)
      parent.obj[key] = {};  // will be reassigned to array if a dash follows
      stack.push({ indent, obj: parent.obj, key, arr: null });
      // Look ahead: if next content line starts with "- ", make it an array
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
      // scalar
      const target = parent.arr && parent.arr.length ? parent.arr[parent.arr.length - 1] : (stack[stack.length - 1].obj);
      if (stack[stack.length - 1].arr && stack[stack.length - 1].arr.length) {
        // We're inside the current array item's object; use the last stack frame's obj
        stack[stack.length - 1].obj[key] = parseScalar(value);
      } else {
        stack[stack.length - 1].obj[key] = parseScalar(value);
      }
    }
  }
  return root;
}

function findCommentStart(s) {
  let inQuote = null;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inQuote) {
      if (c === inQuote && s[i - 1] !== '\\') inQuote = null;
    } else {
      if (c === '"' || c === "'") inQuote = c;
      else if (c === '#') return i;
    }
  }
  return -1;
}

function parseScalar(v) {
  if (v === null || v === undefined) return v;
  v = String(v).trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    return v.slice(1, -1);
  }
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

// --- Minimal JSON Schema validator (subset supported: type, required,
//     properties, additionalProperties, enum, pattern, items, $defs, $ref,
//     minimum, minItems, allOf with if/then) ----------------------------------
// Zero deps. Not a full Draft 2020-12 implementation — covers what schema.json uses.
function validateSchema(data, schema, rootSchema, path = '$') {
  const errs = [];
  const push = (msg) => errs.push(`${path}: ${msg}`);

  // $ref resolution
  if (schema && schema.$ref) {
    const refPath = schema.$ref.replace(/^#\//, '').split('/');
    let target = rootSchema;
    for (const seg of refPath) target = target[seg];
    return validateSchema(data, target, rootSchema, path);
  }

  // type
  if (schema.type) {
    const t = Array.isArray(data) ? 'array' : (data === null ? 'null' : typeof data);
    if (schema.type === 'integer') {
      if (t !== 'number' || !Number.isInteger(data)) push(`expected integer, got ${t}`);
    } else if (schema.type !== t) {
      push(`expected type ${schema.type}, got ${t}`);
    }
  }

  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    // required
    if (schema.required) {
      for (const key of schema.required) {
        if (!(key in data)) push(`missing required property "${key}"`);
      }
    }
    // properties + additionalProperties
    if (schema.properties) {
      for (const [k, v] of Object.entries(data)) {
        if (schema.properties[k]) {
          errs.push(...validateSchema(v, schema.properties[k], rootSchema, `${path}.${k}`));
        } else if (schema.additionalProperties === false) {
          push(`unexpected property "${k}"`);
        }
      }
    }
  }

  // arrays
  if (Array.isArray(data)) {
    if (schema.minItems !== undefined && data.length < schema.minItems) {
      push(`expected at least ${schema.minItems} items, got ${data.length}`);
    }
    if (schema.items) {
      data.forEach((item, i) => {
        errs.push(...validateSchema(item, schema.items, rootSchema, `${path}[${i}]`));
      });
    }
  }

  // scalars
  if (schema.enum && !schema.enum.includes(data)) {
    push(`value "${data}" not in enum [${schema.enum.join(', ')}]`);
  }
  if (schema.pattern && typeof data === 'string' && !new RegExp(schema.pattern).test(data)) {
    push(`value "${data}" does not match pattern ${schema.pattern}`);
  }
  if (schema.minimum !== undefined && typeof data === 'number' && data < schema.minimum) {
    push(`value ${data} below minimum ${schema.minimum}`);
  }

  // allOf with if/then (conditional required)
  if (schema.allOf) {
    for (const clause of schema.allOf) {
      if (clause.if && clause.then) {
        // Check the "if" — if it passes, apply "then"
        const ifErrs = validateSchema(data, clause.if, rootSchema, path);
        if (ifErrs.length === 0) {
          errs.push(...validateSchema(data, clause.then, rootSchema, path));
        }
      } else {
        errs.push(...validateSchema(data, clause, rootSchema, path));
      }
    }
  }

  // oneOf (accept if exactly one subschema matches)
  if (schema.oneOf) {
    const matches = schema.oneOf.filter(sub => validateSchema(data, sub, rootSchema, path).length === 0);
    if (matches.length !== 1) push(`expected exactly 1 of oneOf to match, got ${matches.length}`);
  }

  return errs;
}

// --- Validation -------------------------------------------------------------
function fail(msg) { console.error(`FAIL: ${msg}`); process.exit(1); }
function warn(msg) { console.warn(`WARN: ${msg}`); }
function pass(msg) { console.log(`PASS: ${msg}`); }

const src = readFileSync(yamlPath, 'utf8');
let state;
try {
  state = parseYaml(src);
} catch (e) {
  fail(`YAML parse error: ${e.message}`);
}

// --- JSON Schema validation (codex P1 fix 2026-04-15) -----------------------
const schemaPath = join(__dirname, 'schema.json');
if (!existsSync(schemaPath)) {
  fail(`schema.json missing at ${schemaPath}`);
}
const schema = JSON.parse(readFileSync(schemaPath, 'utf8'));
const schemaErrs = validateSchema(state, schema, schema);
if (schemaErrs.length > 0) {
  console.error(`FAIL: schema validation found ${schemaErrs.length} error(s):`);
  for (const e of schemaErrs.slice(0, 20)) console.error(`  ${e}`);
  if (schemaErrs.length > 20) console.error(`  ... and ${schemaErrs.length - 20} more`);
  process.exit(1);
}
pass(`schema.json validated (${schemaErrs.length} errors)`);

// Check: required top-level keys
for (const key of ['meta', 'tiers', 'protocols', 'directions', 'hooks', 'invariants', 'companies']) {
  if (!state[key]) fail(`missing top-level key: ${key}`);
}
pass('top-level keys present');

// Check: meta caps
const caps = state.meta.caps;
if (!caps || !caps.protocols_active_max || !caps.directions_active_max) {
  fail('meta.caps incomplete');
}
pass(`caps: protocols<=${caps.protocols_active_max}, directions<=${caps.directions_active_max}`);

// Count active protocols
const activeProtocols = (state.protocols || []).filter(p => p.status === 'active');
if (activeProtocols.length > caps.protocols_active_max) {
  fail(`I-7 violated: ${activeProtocols.length} active protocols > cap ${caps.protocols_active_max}`);
}
pass(`I-7 protocol budget: ${activeProtocols.length}/${caps.protocols_active_max}`);

// Count active directions
const coreActive = ((state.directions || {}).core || []).filter(d => d.status === 'active');
const ergActive = ((state.directions || {}).ergonomics || []).filter(d => d.status === 'active');
const totalActive = coreActive.length + ergActive.length;
if (totalActive > caps.directions_active_max) {
  fail(`I-8 violated: ${totalActive} active directions > cap ${caps.directions_active_max}`);
}
pass(`I-8 direction budget: ${totalActive}/${caps.directions_active_max} (core=${coreActive.length}, ergonomics=${ergActive.length})`);

// Every active+hard protocol must have mechanism
for (const p of activeProtocols) {
  if (p.enforcement === 'hard' && !p.mechanism) {
    fail(`protocol ${p.id} (active+hard) has no mechanism`);
  }
}
pass('every active+hard protocol has mechanism');

// Every active+hard direction must have mechanism
for (const d of [...coreActive, ...ergActive]) {
  if (d.enforcement === 'hard' && !d.mechanism) {
    fail(`direction ${d.id} (active+hard) has no mechanism`);
  }
}
pass('every active+hard direction has mechanism');

// Hooks implements[] reference validation (forward: every reference resolves)
const allIds = new Set([
  ...(state.protocols || []).map(p => p.id),
  ...coreActive.map(d => d.id),
  ...ergActive.map(d => d.id),
]);
for (const h of state.hooks || []) {
  for (const ref of h.implements || []) {
    if (!allIds.has(ref)) {
      warn(`hook ${h.file} references unknown id in implements: ${ref}`);
    }
  }
}
pass('hook implements[] references checked (forward)');

// Inverse coverage — every active+hard rule must have a mechanism that
// resolves to something concrete: either a blocking hook, the reconciler,
// the compiler, or an explicit agent-behavior gate (AskUserQuestion). Codex
// P1 fix 2026-04-15: previously only forward references were checked,
// which false-greened D20, D23, PROTO-015 etc.
function mechanismKind(mech) {
  if (!mech) return null;
  const m = mech.toLowerCase();
  if (m.includes('reconciler') || m.includes('doctor')) return 'reconciler';
  if (m.includes('compiler')) return 'compiler';
  if (m.includes('askuserquestion') || m.includes('agent behavior') || m.includes('agent-behavior')) return 'agent-behavior';
  if (m.includes('claude.md')) return 'agent-behavior';
  if (m.includes('.sh') || m.includes('dispatcher')) return 'hook';
  return 'unknown';
}

const hooksById = new Map();
for (const h of state.hooks || []) {
  for (const ref of h.implements || []) {
    if (!hooksById.has(ref)) hooksById.set(ref, []);
    hooksById.get(ref).push(h);
  }
}

let inverseFail = 0;
const checkInverse = (item, label) => {
  if (item.enforcement !== 'hard' || item.status !== 'active') return;
  const kind = mechanismKind(item.mechanism);
  if (kind === 'hook') {
    const matching = hooksById.get(item.id) || [];
    const blocking = matching.filter(h => h.blocking === true);
    if (blocking.length === 0) {
      console.error(`FAIL: I-1 violated: ${label} ${item.id} (hard, mechanism=hook) has no blocking hook with implements[${item.id}]`);
      inverseFail++;
    }
  } else if (kind === 'unknown') {
    console.error(`FAIL: I-1 violated: ${label} ${item.id} (hard) has unparseable mechanism "${item.mechanism}" — cannot classify as hook/reconciler/compiler/agent-behavior`);
    inverseFail++;
  }
  // reconciler/compiler/agent-behavior: accepted without hook, but tracked
};

for (const p of activeProtocols) checkInverse(p, 'protocol');
for (const d of [...coreActive, ...ergActive]) checkInverse(d, 'direction');
if (inverseFail > 0) {
  console.error(`FAIL: inverse-coverage failed for ${inverseFail} active+hard rule(s)`);
  process.exit(1);
}
pass('I-1 inverse coverage: every active+hard rule has a resolvable mechanism');

// Test coverage for active+hard rules — WARN in Phase 1, promoted to FAIL in Phase 3.
let testMissing = 0;
const checkTest = (item, label) => {
  if (item.enforcement !== 'hard' || item.status !== 'active') return;
  const kind = mechanismKind(item.mechanism);
  // reconciler/compiler will be tested by their own builds in Phase 2-3; hook/agent need explicit test.
  if ((kind === 'hook' || kind === 'agent-behavior') && !item.test) {
    warn(`${label} ${item.id} (hard, ${kind}) has no test — will become FAIL in Phase 3 when doctor enforces I-1 fully`);
    testMissing++;
  }
};
for (const p of activeProtocols) checkTest(p, 'protocol');
for (const d of [...coreActive, ...ergActive]) checkTest(d, 'direction');
if (testMissing > 0) {
  console.warn(`NOTE: ${testMissing} active+hard rule(s) missing test field. Phase 3 doctor will fail on these.`);
} else {
  pass('every active+hard hook/agent-behavior rule has a test');
}

// Invariants must have enforces or notes
for (const inv of state.invariants || []) {
  if (inv.severity === 'fail' && (!inv.enforces || inv.enforces.length === 0) && !inv.notes) {
    warn(`invariant ${inv.id} has severity=fail but no enforces[] or notes`);
  }
}
pass('invariants sanity');

// Duplicate ID check across protocols
const protoIds = (state.protocols || []).map(p => p.id);
const protoDupes = protoIds.filter((id, i) => protoIds.indexOf(id) !== i);
if (protoDupes.length) fail(`duplicate protocol IDs: ${protoDupes.join(', ')}`);
pass('no duplicate protocol IDs');

// Duplicate direction IDs across core+ergonomics+retired
const dirAll = [
  ...coreActive.map(d => d.id),
  ...ergActive.map(d => d.id),
  ...((state.directions || {}).retired || []).map(d => d.id),
];
const dirDupes = dirAll.filter((id, i) => dirAll.indexOf(id) !== i);
if (dirDupes.length) fail(`duplicate direction IDs: ${dirDupes.join(', ')}`);
pass('no duplicate direction IDs');

console.log('\nSTATE MODEL VALID');
process.exit(0);
