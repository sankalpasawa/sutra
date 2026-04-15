#!/usr/bin/env node
/**
 * Sutra OS Installer — v1.9
 *
 * One command: npx sutra-os@latest
 *
 * Ships the full Sutra OS into a company:
 *   1. gstack (32 skills) — Garry Tan's builder framework (external)
 *   2. GSD v1 (57 skills) — spec-driven development (external)
 *   3. Sutra commands + skills — orchestration layer
 *   4. Sutra hooks bundle → {claudeDir}/hooks/sutra/
 *   5. Settings template → merged into {claudeDir}/settings.json
 *   6. OS core docs → {projectRoot}/os/ (when --local)
 *   7. Company templates → {projectRoot}/CLAUDE.md, TODO.md, os/SUTRA-CONFIG.md
 *   8. Version manifest → {claudeDir}/sutra-version
 *
 * Modes:
 *   --global  install to ~/.claude/ (for all projects)
 *   --local   install to ./.claude/ + current project root (default)
 *   --uninstall  remove Sutra artifacts (keeps gstack, GSD, user content)
 */

import { execSync } from 'child_process';
import {
  existsSync, mkdirSync, writeFileSync, readFileSync,
  copyFileSync, readdirSync, rmSync, statSync
} from 'fs';
import { join, dirname, basename } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const packageRoot = join(__dirname, '..');

const SUTRA_VERSION = '1.9';

const BANNER = `
  Sutra OS v${SUTRA_VERSION}
  Operating system for building companies with AI.
`;

const args = process.argv.slice(2);
const isUninstall = args.includes('--uninstall') || args.includes('-u');
const isGlobal = args.includes('--global') || args.includes('-g');
const isLocal = args.includes('--local') || args.includes('-l') || !isGlobal;
const isHelp = args.includes('--help') || args.includes('-h');
const companyArg = args.find(a => a.startsWith('--company='));
const companyName = companyArg ? companyArg.split('=')[1] : basename(process.cwd());

if (isHelp) {
  console.log(BANNER);
  console.log(`  Usage: npx sutra-os [options]

  Options:
    -g, --global            Install to ~/.claude (all projects)
    -l, --local             Install to ./.claude + current project (default)
    -u, --uninstall         Remove Sutra (keeps gstack, GSD, user content)
    --company=NAME          Company name for CLAUDE.md template
    -h, --help              Show this help

  What installs:
    1. gstack                — 32 skills (design, QA, ship, review, security)
    2. GSD v1                — 57 skills (plan, execute, verify, debug)
    3. Sutra commands        — /sutra-onboard, /asawa, /company, /dayflow
    4. Sutra hooks bundle    — 28 hooks enforcing D27/D28/D9/D12/D13
    5. Settings template     — PreToolUse/PostToolUse/Stop/UserPromptSubmit wiring
    6. OS core docs          — 23 governance documents (os-core → os/)
    7. Templates             — CLAUDE.md, TODO.md, SUTRA-CONFIG.md
    8. Version manifest      — .claude/sutra-version

  After install:
    /sutra-onboard           — Start a new company onboarding
    /company NAME            — Open a company-scoped session
`);
  process.exit(0);
}

console.log(BANNER);

const homeDir = process.env.HOME || process.env.USERPROFILE;
const projectRoot = process.cwd();
const claudeDir = isGlobal ? join(homeDir, '.claude') : join(projectRoot, '.claude');
const commandsDir = join(claudeDir, 'commands');
const skillsDir = join(claudeDir, 'skills');
const hooksDir = join(claudeDir, 'hooks', 'sutra');
const osDir = join(projectRoot, 'os');

const mkdir = (d) => existsSync(d) || mkdirSync(d, { recursive: true });

// ─── copyTree: recursive copy with executable preservation for .sh ───────────
function copyTree(src, dst) {
  if (!existsSync(src)) return 0;
  mkdir(dst);
  let n = 0;
  for (const entry of readdirSync(src)) {
    const s = join(src, entry);
    const d = join(dst, entry);
    if (statSync(s).isDirectory()) {
      n += copyTree(s, d);
    } else {
      copyFileSync(s, d);
      if (s.endsWith('.sh')) execSync(`chmod +x "${d}"`);
      n += 1;
    }
  }
  return n;
}

// ─── Template substitution ───────────────────────────────────────────────────
function renderTemplate(srcPath, dstPath, vars) {
  let content = readFileSync(srcPath, 'utf8');
  for (const [k, v] of Object.entries(vars)) {
    content = content.replaceAll(`{{${k}}}`, v);
  }
  writeFileSync(dstPath, content);
}

// ─── Settings merge: preserve existing user hooks, add Sutra bundle ──────────
function mergeSettings(templatePath, targetPath) {
  const template = JSON.parse(readFileSync(templatePath, 'utf8'));
  let existing = { hooks: {}, permissions: { allow: [] } };
  if (existsSync(targetPath)) {
    try { existing = JSON.parse(readFileSync(targetPath, 'utf8')); } catch (e) { /* keep template as fallback */ }
  }

  // If existing file is already Sutra-managed, just overwrite.
  if (existing._sutra_managed) {
    writeFileSync(targetPath, JSON.stringify(template, null, 2) + '\n');
    return 'replaced';
  }

  // Otherwise merge: append Sutra hooks, preserve user hooks + permissions.
  const merged = {
    ...existing,
    _sutra_version: SUTRA_VERSION,
    _sutra_managed: false,
    _sutra_note: 'User-managed file with Sutra hooks appended. Sutra upgrades will not overwrite.',
    permissions: {
      ...(existing.permissions || {}),
      allow: [...new Set([...(existing.permissions?.allow || []), ...template.permissions.allow])]
    },
    hooks: { ...(existing.hooks || {}) }
  };

  for (const [event, rules] of Object.entries(template.hooks)) {
    merged.hooks[event] = [...(merged.hooks[event] || []), ...rules];
  }

  writeFileSync(targetPath, JSON.stringify(merged, null, 2) + '\n');
  return 'merged';
}

// ─── Uninstall ───────────────────────────────────────────────────────────────
if (isUninstall) {
  console.log('  Removing Sutra artifacts...');
  // Hooks bundle
  if (existsSync(hooksDir)) {
    rmSync(hooksDir, { recursive: true, force: true });
    console.log('  ✓ Removed .claude/hooks/sutra/');
  }
  // Version manifest
  const vfile = join(claudeDir, 'sutra-version');
  if (existsSync(vfile)) { rmSync(vfile); console.log('  ✓ Removed .claude/sutra-version'); }
  // Sutra-managed settings: revert to minimal template, user-managed: strip sutra hooks
  const settingsFile = join(claudeDir, 'settings.json');
  if (existsSync(settingsFile)) {
    try {
      const s = JSON.parse(readFileSync(settingsFile, 'utf8'));
      if (s._sutra_managed) {
        rmSync(settingsFile);
        console.log('  ✓ Removed Sutra-managed settings.json');
      } else if (s.hooks) {
        // Strip any hook entry whose command references .claude/hooks/sutra/
        for (const event of Object.keys(s.hooks)) {
          s.hooks[event] = s.hooks[event].filter(rule =>
            !(rule.hooks || []).some(h => (h.command || '').includes('.claude/hooks/sutra/'))
          );
          if (s.hooks[event].length === 0) delete s.hooks[event];
        }
        delete s._sutra_version;
        delete s._sutra_managed;
        delete s._sutra_note;
        writeFileSync(settingsFile, JSON.stringify(s, null, 2) + '\n');
        console.log('  ✓ Stripped Sutra hooks from settings.json');
      }
    } catch (e) { console.log(`  ⚠ settings.json parse failed: ${e.message}`); }
  }
  // Sutra commands (leave gstack and GSD)
  if (existsSync(join(packageRoot, 'commands'))) {
    for (const f of readdirSync(join(packageRoot, 'commands'))) {
      const t = join(commandsDir, f);
      if (existsSync(t)) { rmSync(t); console.log(`  ✓ Removed command ${f}`); }
    }
  }
  console.log('\n  Sutra removed. gstack, GSD, and user content are untouched.');
  process.exit(0);
}

// ─── Install ─────────────────────────────────────────────────────────────────
mkdir(claudeDir);
mkdir(commandsDir);
mkdir(skillsDir);

// Step 1: gstack check (external)
console.log('  [1/8] gstack...');
if (existsSync(join(skillsDir, 'gstack'))) {
  console.log('  ✓ gstack already installed');
} else {
  console.log('  → gstack not found. See https://github.com/garrytan/gstack');
  console.log('  ⚠ continuing without gstack (some skills unavailable)');
}

// Step 2: GSD check (external)
console.log('\n  [2/8] GSD v1...');
const gsdDir = join(commandsDir, 'gsd');
if (existsSync(gsdDir)) {
  console.log('  ✓ GSD already installed');
} else {
  try {
    execSync(`npx get-shit-done-cc@latest --claude ${isGlobal ? '--global' : '--local'}`, { stdio: 'inherit' });
    console.log('  ✓ GSD installed');
  } catch (e) {
    console.log(`  ⚠ GSD install failed: ${e.message}`);
  }
}

// Step 3: Sutra commands
console.log('\n  [3/8] Sutra commands...');
const sutraCommandsDir = join(packageRoot, 'commands');
if (existsSync(sutraCommandsDir)) {
  const n = copyTree(sutraCommandsDir, commandsDir);
  console.log(`  ✓ ${n} commands copied`);
} else {
  console.log('  — no commands/ in package (skipped)');
}

// Step 4: Hooks bundle
console.log('\n  [4/8] Sutra hooks bundle...');
const n4 = copyTree(join(packageRoot, 'hooks'), hooksDir);
console.log(`  ✓ ${n4} hooks installed to ${hooksDir}`);

// Step 5: Settings template (merge)
console.log('\n  [5/8] Settings template...');
const settingsFile = join(claudeDir, 'settings.json');
const mergeResult = mergeSettings(join(packageRoot, 'templates', 'settings.json'), settingsFile);
console.log(`  ✓ settings.json ${mergeResult}`);

// Step 6: OS core docs (only --local; --global doesn't clobber cwd)
if (isLocal) {
  console.log('\n  [6/8] OS core docs...');
  mkdir(osDir);
  const n6 = copyTree(join(packageRoot, 'os-core'), osDir);
  console.log(`  ✓ ${n6} governance docs copied to ${osDir}`);
} else {
  console.log('\n  [6/8] OS core docs — skipped (global install)');
}

// Step 7: Company templates (only --local, only if absent — never clobber)
if (isLocal) {
  console.log('\n  [7/8] Company templates...');
  const templatesDir = join(packageRoot, 'templates');
  const vars = { COMPANY_NAME: companyName, SUTRA_VERSION };
  const renderIfAbsent = (tplName, dst) => {
    if (!existsSync(dst)) {
      renderTemplate(join(templatesDir, tplName), dst, vars);
      console.log(`  ✓ rendered ${basename(dst)}`);
    } else {
      console.log(`  — ${basename(dst)} exists (preserved)`);
    }
  };
  renderIfAbsent('CLAUDE.md.template', join(projectRoot, 'CLAUDE.md'));
  renderIfAbsent('TODO.md.template', join(projectRoot, 'TODO.md'));
  renderIfAbsent('SUTRA-CONFIG.md.template', join(osDir, 'SUTRA-CONFIG.md'));
  // os-layout stubs
  const osLayoutDir = join(templatesDir, 'os-layout');
  if (existsSync(osLayoutDir)) {
    for (const f of readdirSync(osLayoutDir)) {
      const dst = join(osDir, f);
      if (!existsSync(dst)) {
        renderTemplate(join(osLayoutDir, f), dst, vars);
        console.log(`  ✓ rendered ${f}`);
      } else {
        console.log(`  — ${f} exists (preserved)`);
      }
    }
  }
} else {
  console.log('\n  [7/8] Company templates — skipped (global install)');
}

// Step 8: Version manifest
console.log('\n  [8/8] Version manifest...');
const manifestPath = join(claudeDir, 'sutra-version');
writeFileSync(manifestPath, `${SUTRA_VERSION}\n${Math.floor(Date.now() / 1000)}\n`);
console.log(`  ✓ ${manifestPath}`);

console.log(`\n  Done! Sutra OS v${SUTRA_VERSION} installed.`);
if (isLocal) {
  console.log(`\n  Next steps:`);
  console.log(`    1. Review and customize CLAUDE.md`);
  console.log(`    2. Review os/SUTRA-CONFIG.md for depth and enforcement settings`);
  console.log(`    3. Open Claude Code in this directory → type /sutra-onboard`);
  console.log(`\n  Smoke test: bash .claude/hooks/sutra/reset-turn-markers.sh`);
}
