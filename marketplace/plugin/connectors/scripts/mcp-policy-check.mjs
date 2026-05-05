#!/usr/bin/env node
/**
 * Sutra MCP Policy Check
 *
 * Called by hooks/mcp-connector-gate.sh on every claude.ai MCP tool invocation.
 * Loads connector manifests, maps tool name → capability, enforces tier + depth.
 *
 * Usage:
 *   node mcp-policy-check.mjs --tool <mcp_tool_name> [options]
 *
 * Options:
 *   --tool           claude.ai MCP tool name (e.g. mcp__claude_ai_Slack__slack_send_message)
 *   --manifests-dir  path to manifests/ directory (default: ../manifests relative to this file)
 *   --depth-file     path to .claude/depth-registered (default: .claude/depth-registered)
 *   --project-file   path to .claude/sutra-project.json (default: .claude/sutra-project.json)
 *   --tier           override tier (T1|T2|T3|T4) — skips project-file lookup
 *   --depth          override depth (1-5) — skips depth-file lookup
 *
 * Exit codes:
 *   0  — allowed (or tool not in any manifest → pass-through, not our connector)
 *   2  — blocked (reason printed to stderr for Claude to display)
 *
 * Fail-open policy: manifest parse errors, missing files, and unknown tools
 * all exit 0. Only explicit policy violations exit 2.
 */

import { readFileSync, readdirSync, existsSync, appendFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse as parseYaml } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── CLI arg helpers ───────────────────────────────────────────────────────────

const argv = process.argv.slice(2);
function arg(flag) {
  const i = argv.indexOf(flag);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : null;
}

const toolName = arg('--tool');
if (!toolName || !toolName.startsWith('mcp__claude_ai_')) process.exit(0);

// ── Load and search manifests ─────────────────────────────────────────────────

const manifestsDir = arg('--manifests-dir') ?? join(__dirname, '../manifests');

let manifest = null;
let capability = null;

try {
  const files = readdirSync(manifestsDir).filter(f => f.endsWith('.yaml'));
  for (const file of files) {
    const raw = readFileSync(join(manifestsDir, file), 'utf8');
    const m = parseYaml(raw);
    if (m?.mcp_tool_map?.[toolName]) {
      manifest = m;
      capability = m.mcp_tool_map[toolName];
      break;
    }
  }
} catch (err) {
  process.stderr.write(`[sutra-mcp] manifest load error (fail-open): ${err.message}\n`);
  process.exit(0);
}

// Tool not in any manifest — not a Sutra-governed connector, pass through.
if (!manifest || !capability) process.exit(0);

// ── Read current depth ────────────────────────────────────────────────────────

let currentDepth = 1;
const depthOverride = arg('--depth');
if (depthOverride) {
  currentDepth = parseInt(depthOverride, 10) || 1;
} else {
  const depthFile = arg('--depth-file') ?? '.claude/depth-registered';
  if (existsSync(depthFile)) {
    const m = readFileSync(depthFile, 'utf8').match(/DEPTH=(\d)/);
    if (m) currentDepth = parseInt(m[1], 10);
  }
}

// ── Read current tier ─────────────────────────────────────────────────────────

let tier = 'T1';  // fail-safe default: Asawa (founder) context
const tierOverride = arg('--tier');
if (tierOverride) {
  tier = tierOverride;
} else {
  const projectFile = arg('--project-file') ?? '.claude/sutra-project.json';
  if (existsSync(projectFile)) {
    try {
      const cfg = JSON.parse(readFileSync(projectFile, 'utf8'));
      if (cfg.tier && /^T[1-4]$/.test(cfg.tier)) tier = cfg.tier;
    } catch {}
  }
}

// ── Find capability declaration in manifest ───────────────────────────────────

const capDecl = (manifest.capabilities ?? []).find(c => {
  if (!c?.id) return false;
  if (capability === c.id) return true;
  // Pattern match: 'slack:read-channel:#*' decl covers 'slack:read-channel:#ops'
  const prefix = c.id.replace(/:\*$/, ':');
  return capability.startsWith(prefix) && !c.id.endsWith(':*')
    ? false
    : capability === c.id || capability.startsWith(prefix);
});

if (!capDecl) {
  block(`Capability '${capability}' not declared in ${manifest.name} manifest — contact Asawa to add it`);
}

// ── Check tier access ─────────────────────────────────────────────────────────

const tierGrants = manifest.tierAccess?.[tier] ?? [];
const tierAllowed = tierGrants.some(granted => {
  if (capability === granted) return true;
  const prefix = granted.replace(/:\*$/, ':');
  return granted.endsWith(':*') && capability.startsWith(prefix);
});

if (!tierAllowed) {
  const tiersWithAccess = Object.entries(manifest.tierAccess ?? {})
    .filter(([, caps]) =>
      caps.some(c => capability === c || (c.endsWith(':*') && capability.startsWith(c.replace(/:\*$/, ':'))))
    )
    .map(([t]) => t)
    .join(', ') || 'none';

  block(
    `${manifest.name} '${capability}' is not available for tier ${tier}. ` +
    `Tiers with access: ${tiersWithAccess}`
  );
}

// ── Check depth floor ─────────────────────────────────────────────────────────

if (currentDepth < (capDecl.minDepth ?? 1)) {
  block(
    `${manifest.name} '${capability}' requires depth ≥ ${capDecl.minDepth} ` +
    `(session is at depth ${currentDepth}). ` +
    `Emit a Depth ${capDecl.minDepth}/5 block before using this connector.`
  );
}

// ── All checks passed — audit + exit 0 ───────────────────────────────────────

writeAudit({ outcome: 'allowed' });
process.exit(0);

// ── Helpers ───────────────────────────────────────────────────────────────────

function block(reason) {
  writeAudit({ outcome: 'blocked', reason });
  process.stderr.write(`[Sutra] BLOCKED — ${reason}\n`);
  process.exit(2);
}

function writeAudit(extra) {
  try {
    const logPath = '.enforcement/connector-audit.jsonl';
    const dir = dirname(logPath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    appendFileSync(
      logPath,
      JSON.stringify({
        ts: Date.now(),
        connector: manifest?.name ?? 'unknown',
        tool: toolName,
        capability: capability ?? '?',
        tier,
        depth: currentDepth,
        ...extra,
      }) + '\n'
    );
  } catch {
    // audit write failure is best-effort — never block on it
  }
}
