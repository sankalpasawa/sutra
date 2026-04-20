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

// Single source of truth: read version from package.json at runtime.
// Keeps install banner + .claude/sutra-version + update-check comparisons aligned.
const _pkgPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'package.json');
const SUTRA_VERSION = JSON.parse(readFileSync(_pkgPath, 'utf8')).version;

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
// R1 from billu feedback 2026-04-15: tiered profiles. Tier controls which pieces install.
//   tier-1-governance: governance tools (Billu). Minimal — boundary + SUTRA-CONFIG + feedback dirs.
//   tier-2-product (default): full OS — hooks + engines + OS core + templates.
//   tier-3-platform: meta — everything plus protocol harvester (future).
const tierArg = args.find(a => a.startsWith('--tier='));
const tier = tierArg ? tierArg.split('=')[1] : '2';
const TIER_CONFIG = {
  '1': { name: 'governance', hooks: ['enforce-boundaries.sh', 'reset-turn-markers.sh', 'dispatcher-pretool.sh'], installOsCore: false, installTemplates: true },
  '2': { name: 'product',    hooks: null /* all */,                                                           installOsCore: true,  installTemplates: true },
  '3': { name: 'platform',   hooks: null /* all */,                                                           installOsCore: true,  installTemplates: true },
};
if (!TIER_CONFIG[tier]) {
  console.error(`ERROR: unknown --tier=${tier}. Valid: 1 (governance), 2 (product, default), 3 (platform).`);
  process.exit(1);
}
const tierConfig = TIER_CONFIG[tier];

if (isHelp) {
  console.log(BANNER);
  console.log(`  Usage: npx sutra-os [options]

  Options:
    -g, --global            Install to ~/.claude (all projects)
    -l, --local             Install to ./.claude + current project (default)
    -u, --uninstall         Remove Sutra (keeps gstack, GSD, user content)
    --company=NAME          Company name for CLAUDE.md template
    --tier=N                Deployment tier (default 2):
                              1  governance  (billu-style: boundary + SUTRA-CONFIG only)
                              2  product     (full OS + all hooks + OS core)
                              3  platform    (meta, same as 2 today + future harvester)
    -h, --help              Show this help

  What installs:
    1. gstack                — 32 skills (design, QA, ship, review, security)
    2. GSD v1                — 57 skills (plan, execute, verify, debug)
    3. Sutra commands        — /sutra, /sutra-help, /sutra-update, /company
    4. Sutra hooks bundle    — 28 hooks enforcing D27/D28/D9/D12/D13
    5. Settings template     — PreToolUse/PostToolUse/Stop/UserPromptSubmit wiring
    6. OS core docs          — 23 governance documents (os-core → os/)
    7. Templates             — CLAUDE.md, TODO.md, SUTRA-CONFIG.md
    8. Version manifest      — .claude/sutra-version

  After install:
    /sutra                   — Activate Sutra for this session (CEO day)
    /sutra-help              — Show commands + install state
    /sutra-update            — Pull the latest Sutra OS
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

// ─── Orphan-sweep + lint helpers (v1.9.1 — billu Stop-hook RCA 2026-04-17) ───
//
// Root cause: `_sutra_managed: false` boxes conflated two rules
//   (a) "don't clobber user keys"  (b) "don't clean up Sutra's own stale keys".
// The user-managed path already strips Sutra hooks before append; these helpers
// generalise the same sweep to the sutra-managed path and add a final
// verification so no settings.json points at a missing script.
function sweepOrphanSutraHooks(hooks, installedHookNames) {
  // Remove any hook rule whose command references `.claude/hooks/sutra/<script>`
  // when <script> is NOT part of the current tier's installed set.
  const out = {};
  for (const event of Object.keys(hooks || {})) {
    out[event] = (hooks[event] || []).filter(rule =>
      !(rule.hooks || []).some(h => {
        const cmd = h.command || '';
        const m = cmd.match(/\.claude\/hooks\/sutra\/([a-zA-Z0-9_-]+\.sh)/);
        if (!m) return false;
        return !installedHookNames.has(m[1]);
      })
    );
    if (out[event].length === 0) delete out[event];
  }
  return out;
}

function verifyHookRegistrations(settingsPath, hooksDir) {
  // Post-install lint: every settings.json entry that references
  // `.claude/hooks/sutra/*.sh` must resolve to an existing, executable file.
  // If not — orphan, fail loudly.
  if (!existsSync(settingsPath)) return { orphans: [], ok: true };
  let s;
  try { s = JSON.parse(readFileSync(settingsPath, 'utf8')); } catch (e) { return { orphans: [], ok: true, parseError: e.message }; }
  const orphans = [];
  for (const event of Object.keys(s.hooks || {})) {
    for (const rule of s.hooks[event]) {
      for (const h of (rule.hooks || [])) {
        const m = (h.command || '').match(/\.claude\/hooks\/sutra\/([a-zA-Z0-9_-]+\.sh)/);
        if (!m) continue;
        const script = m[1];
        const path = join(hooksDir, script);
        if (!existsSync(path)) orphans.push({ event, script, reason: 'file missing' });
      }
    }
  }
  return { orphans, ok: orphans.length === 0 };
}

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
let n4;
if (tierConfig.hooks === null) {
  n4 = copyTree(join(packageRoot, 'hooks'), hooksDir);
} else {
  // Tier 1: only specific hooks
  mkdir(hooksDir);
  n4 = 0;
  for (const hookName of tierConfig.hooks) {
    const src = join(packageRoot, 'hooks', hookName);
    if (existsSync(src)) {
      copyFileSync(src, join(hooksDir, hookName));
      execSync(`chmod +x "${join(hooksDir, hookName)}"`);
      n4 += 1;
    }
  }
}
console.log(`  ✓ ${n4} hooks installed (tier ${tier}-${tierConfig.name}) to ${hooksDir}`);

// Step 5: Settings template (merge) — tier-aware: only register hooks that
// this tier actually installed, so we never wire references to missing files
// (codex P1 #3). For --global, use absolute path under ~/.claude; for
// --local, use the CLAUDE_PROJECT_DIR-rooted path (codex P1 #1).
console.log('\n  [5/8] Settings template...');
const settingsFile = join(claudeDir, 'settings.json');
const hookCmdPrefix = isGlobal
  ? `bash "${hooksDir}"`
  : 'cd "$CLAUDE_PROJECT_DIR" && bash .claude/hooks/sutra';
// Only the hooks this tier installed get wired
const installedHookNames = new Set(
  (tierConfig.hooks || readdirSync(join(packageRoot, 'hooks'))).filter(n => n.endsWith('.sh'))
);
const wantsHook = (name) => installedHookNames.has(name);
const mkCmd = (h) => `${hookCmdPrefix}/${h}`;
const tierSettings = {
  _sutra_version: SUTRA_VERSION,
  _sutra_managed: true,
  _sutra_note: 'Sutra-managed. User additions MUST be made under a top-level "user_hooks" key; those are preserved across upgrade.',
  _sutra_tier: tier,
  permissions: { defaultMode: 'bypassPermissions', allow: ['Read','Write','Edit','Bash','Glob','Grep','WebSearch','WebFetch','Agent','Skill','TaskCreate','TaskUpdate','TaskGet','TaskList','TaskOutput','TaskStop','AskUserQuestion','EnterPlanMode','ExitPlanMode','NotebookEdit','ToolSearch'] },
  hooks: { PreToolUse: [], PostToolUse: [], Stop: [], UserPromptSubmit: [], SessionStart: [] },
};
// Wire only installed hooks. dispatcher-pretool gets Edit|Write|Bash (codex P1 #4).
if (wantsHook('dispatcher-pretool.sh')) {
  tierSettings.hooks.PreToolUse.push({ matcher: 'Edit|Write|Bash', hooks: [{ type: 'command', command: mkCmd('dispatcher-pretool.sh') }] });
}
if (wantsHook('policy-coverage-gate.sh')) {
  tierSettings.hooks.PreToolUse.push({ matcher: 'Edit|Write|Bash', hooks: [{ type: 'command', command: mkCmd('policy-coverage-gate.sh') }] });
}
if (wantsHook('enforce-boundaries.sh')) {
  tierSettings.hooks.PreToolUse.push({ matcher: 'Edit|Write', hooks: [{ type: 'command', command: mkCmd('enforce-boundaries.sh') }] });
}
if (wantsHook('agent-completion-check.sh')) {
  tierSettings.hooks.PostToolUse.push({ matcher: 'Bash|Edit|Write', hooks: [{ type: 'command', command: mkCmd('agent-completion-check.sh') }] });
}
if (wantsHook('onboarding-self-check.sh')) {
  tierSettings.hooks.PostToolUse.push({ matcher: 'Write', hooks: [{ type: 'command', command: mkCmd('onboarding-self-check.sh') }] });
}
if (wantsHook('process-fix-check.sh')) {
  tierSettings.hooks.PostToolUse.push({ matcher: 'Edit|Write', hooks: [{ type: 'command', command: mkCmd('process-fix-check.sh') }] });
}
if (wantsHook('dispatcher-stop.sh')) {
  tierSettings.hooks.Stop.push({ matcher: '', hooks: [{ type: 'command', command: mkCmd('dispatcher-stop.sh') }] });
}
// D31 (2026-04-20): coverage-gate surfaces enabled+required method gaps at session end.
// SOFT Phase 1 (warns + exit 0); HARD rollout 2026-05-04 (will exit 2 on gaps).
if (wantsHook('coverage-gate.sh')) {
  tierSettings.hooks.Stop.push({ matcher: '', hooks: [{ type: 'command', command: mkCmd('coverage-gate.sh') }] });
}
// D31 Phase 3 v0 (2026-04-20): auto-coverage fires log-coverage.sh on tool events
// via declarative path mappings. Closes the invocation gap — clients no longer
// rely on LLM discipline to log every method fire.
if (wantsHook('auto-coverage.sh')) {
  tierSettings.hooks.PostToolUse.push({ matcher: 'Edit|Write|Bash', hooks: [{ type: 'command', command: mkCmd('auto-coverage.sh') }] });
}
// D32 (2026-04-20): hot-reloadable hook dispatcher. Reads os/hooks/posttool-registry.jsonl
// + enabled_hooks block in SUTRA-CONFIG.md on every fire. Future hooks land without
// requiring a settings.json edit — add to registry + flip enablement via PROTO-018.
// Default for every declared hook: OFF (client config must opt in, Sutra-owned).
if (wantsHook('dispatcher-posttool.sh')) {
  tierSettings.hooks.PostToolUse.push({ matcher: 'Edit|Write|Bash', hooks: [{ type: 'command', command: mkCmd('dispatcher-posttool.sh') }] });
}
if (wantsHook('reset-turn-markers.sh')) {
  tierSettings.hooks.UserPromptSubmit.push({ matcher: '', hooks: [{ type: 'command', command: mkCmd('reset-turn-markers.sh') }] });
}
// v0.2.2: SessionStart update-check prints a notice when a newer Sutra ships.
if (wantsHook('update-check.sh')) {
  tierSettings.hooks.SessionStart.push({ matcher: '', hooks: [{ type: 'command', command: mkCmd('update-check.sh') }] });
}
// Merge into existing (preserving user_hooks + non-Sutra entries) or write fresh
let existing = null;
if (existsSync(settingsFile)) {
  try { existing = JSON.parse(readFileSync(settingsFile, 'utf8')); } catch (e) { existing = null; }
}
let finalSettings;
let mergeAction;
if (!existing) {
  finalSettings = tierSettings;
  mergeAction = 'created';
} else if (existing._sutra_managed) {
  // Sutra-managed: replace Sutra sections but keep user_hooks (codex P2 #5)
  // v1.9.1: also sweep any orphan Sutra hooks from prior-tier installs
  // (billu RCA 2026-04-17: tier downgrade left dispatcher-stop.sh registered
  // pointing at a file the Tier 1 bundle doesn't ship).
  finalSettings = { ...tierSettings };
  if (existing.user_hooks) finalSettings.user_hooks = existing.user_hooks;
  mergeAction = 'replaced (user_hooks preserved, orphan Sutra hooks swept)';
} else {
  // User-managed: strip ALL prior Sutra hooks (codex P2 #6 — no duplicate appends;
  // billu RCA 2026-04-17 — sweep orphans from prior-tier installs), then append
  // the current tier's hooks. "Strip all" is correct here because every Sutra
  // hook rule is about to be re-added from tierSettings if it belongs to this tier.
  const stripSutra = (rules) => (rules || []).filter(r =>
    !(r.hooks || []).some(h => /\.claude\/hooks\/sutra\//.test(h.command || '') || /\/hooks\/sutra\//.test(h.command || ''))
  );
  finalSettings = {
    ...existing,
    _sutra_version: SUTRA_VERSION,
    _sutra_managed: false,
    _sutra_tier: tier,
    permissions: { ...(existing.permissions || {}), allow: [...new Set([...(existing.permissions?.allow || []), ...tierSettings.permissions.allow])] },
    hooks: { ...(existing.hooks || {}) },
  };
  for (const event of Object.keys(tierSettings.hooks)) {
    const swept = stripSutra(finalSettings.hooks[event]);
    finalSettings.hooks[event] = [...swept, ...tierSettings.hooks[event]];
    if (finalSettings.hooks[event].length === 0) delete finalSettings.hooks[event];
  }
  // Also sweep any Sutra-hook references in events NOT present in tierSettings
  // (e.g., Stop left behind on Tier 1 downgrade).
  for (const event of Object.keys(finalSettings.hooks)) {
    if (!(event in tierSettings.hooks)) {
      const swept = stripSutra(finalSettings.hooks[event]);
      if (swept.length === 0) delete finalSettings.hooks[event];
      else finalSettings.hooks[event] = swept;
    }
  }
  mergeAction = 'merged (Sutra sections refreshed, orphan Sutra hooks swept, user entries preserved)';
}
writeFileSync(settingsFile, JSON.stringify(finalSettings, null, 2) + '\n');
const wiredCount = Object.values(tierSettings.hooks).reduce((a, arr) => a + arr.length, 0);
console.log(`  ✓ settings.json ${mergeAction} — ${wiredCount} Sutra hook rules (tier ${tier})`);

// Post-install lint: every settings.json hook reference must resolve to an
// extant script in the installed bundle. Fail the install if any orphan remains
// (billu RCA 2026-04-17 Fix B).
const lint = verifyHookRegistrations(settingsFile, hooksDir);
if (!lint.ok) {
  console.error(`  ✗ orphan hook registrations detected after install:`);
  for (const o of lint.orphans) console.error(`      ${o.event}: ${o.script} (${o.reason})`);
  console.error(`  The installer wrote a settings.json that references scripts it did not install.`);
  console.error(`  This is the billu-2026-04-17 failure mode. Please file a bug and re-run with --uninstall then install.`);
  process.exit(1);
}
console.log(`  ✓ post-install lint — no orphan hook registrations`);

// Step 6: OS core docs (only --local + tier 2/3; tier 1 = governance, skip OS core)
if (isLocal && tierConfig.installOsCore) {
  console.log('\n  [6/8] OS core docs...');
  mkdir(osDir);
  const n6 = copyTree(join(packageRoot, 'os-core'), osDir);
  console.log(`  ✓ ${n6} governance docs copied to ${osDir}`);
} else if (!tierConfig.installOsCore) {
  console.log(`\n  [6/8] OS core docs — skipped (tier ${tier}-${tierConfig.name} is minimal)`);
} else {
  console.log('\n  [6/8] OS core docs — skipped (global install)');
}

// Step 7: Company templates (only --local, only if absent — never clobber)
// Ensure osDir exists even if Step 6 was skipped (tier 1) so SUTRA-CONFIG.md and
// os-layout/ stubs don't ENOENT on fresh repos (codex P1 #2).
if (isLocal) {
  console.log('\n  [7/8] Company templates...');
  mkdir(osDir);
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
  console.log(`    3. Open Claude Code in this directory (\`claude\`).`);
  console.log(`       First open will ask "Trust this folder?" — say yes. It's your folder.`);
  console.log(`    4. Type /sutra to activate Sutra mode and see your CEO day.`);
  console.log(`\n  Smoke test:  bash .claude/hooks/sutra/reset-turn-markers.sh`);
  console.log(`  Help:        type /sutra-help inside Claude Code`);
}
