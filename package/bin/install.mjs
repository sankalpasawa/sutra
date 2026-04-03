#!/usr/bin/env node

/**
 * Sutra OS Installer
 *
 * One command: npx sutra-os@latest
 *
 * Installs:
 * 1. gstack (32 skills) — open source, Garry Tan's builder framework
 * 2. GSD v1 (57 skills) — open source, spec-driven development
 * 3. Sutra commands (proprietary) — the orchestration layer
 *
 * The founder gets /sutra-onboard and all 89+ skills.
 * Sutra's internal logic (templates, classification, onboarding process)
 * stays in compiled form — not readable as plain markdown.
 */

import { execSync } from 'child_process';
import { existsSync, mkdirSync, writeFileSync, copyFileSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const packageRoot = join(__dirname, '..');

const BANNER = `
  ███████╗██╗   ██╗████████╗██████╗  █████╗
  ██╔════╝██║   ██║╚══██╔══╝██╔══██╗██╔══██╗
  ███████╗██║   ██║   ██║   ██████╔╝███████║
  ╚════██║██║   ██║   ██║   ██╔══██╗██╔══██║
  ███████║╚██████╔╝   ██║   ██║  ██║██║  ██║
  ╚══════╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝

  Sutra OS v1.0.0
  Operating system for building companies with AI.
`;

const args = process.argv.slice(2);
const isUninstall = args.includes('--uninstall') || args.includes('-u');
const isGlobal = args.includes('--global') || args.includes('-g');
const isLocal = args.includes('--local') || args.includes('-l');
const isHelp = args.includes('--help') || args.includes('-h');

if (isHelp) {
  console.log(BANNER);
  console.log(`  Usage: npx sutra-os [options]

  Options:
    -g, --global      Install globally (to ~/.claude)
    -l, --local       Install locally (to ./.claude)
    -u, --uninstall   Remove Sutra (keeps gstack and GSD)
    -h, --help        Show this help

  What gets installed:
    1. gstack (32 skills) — builder framework by Garry Tan
    2. GSD v1 (57 skills) — spec-driven development system
    3. Sutra commands    — company onboarding & orchestration

  After install, open Claude Code and type:
    /sutra-onboard      — Start building a new company
`);
  process.exit(0);
}

console.log(BANNER);

// Determine install location
const homeDir = process.env.HOME || process.env.USERPROFILE;
const claudeDir = isLocal ? join(process.cwd(), '.claude') : join(homeDir, '.claude');
const commandsDir = join(claudeDir, 'commands');
const skillsDir = join(claudeDir, 'skills');

if (isUninstall) {
  console.log('  Removing Sutra commands...');
  // Remove sutra commands only, leave gstack and GSD
  const sutraCommands = readdirSync(join(packageRoot, 'commands'));
  for (const file of sutraCommands) {
    const target = join(commandsDir, file);
    if (existsSync(target)) {
      execSync(`rm "${target}"`);
      console.log(`  ✓ Removed ${file}`);
    }
  }
  console.log('\n  Sutra removed. gstack and GSD are untouched.');
  process.exit(0);
}

// Step 1: Install gstack
console.log('  [1/3] Installing gstack...');
try {
  // Check if gstack is already installed
  if (existsSync(join(skillsDir, 'gstack'))) {
    console.log('  ✓ gstack already installed');
  } else {
    console.log('  → gstack not found. Install manually:');
    console.log('    See https://github.com/garrytan/gstack');
    console.log('  ⚠ Continuing without gstack (some skills will be unavailable)');
  }
} catch (e) {
  console.log(`  ⚠ gstack check failed: ${e.message}`);
}

// Step 2: Install GSD
console.log('\n  [2/3] Installing GSD v1...');
try {
  const gsdDir = join(claudeDir, 'commands', 'gsd');
  if (existsSync(gsdDir)) {
    console.log('  ✓ GSD already installed');
  } else {
    console.log('  → Installing GSD...');
    execSync(`npx get-shit-done-cc@latest --claude ${isGlobal ? '--global' : '--local'}`, {
      stdio: 'inherit'
    });
    console.log('  ✓ GSD installed');
  }
} catch (e) {
  console.log(`  ⚠ GSD install failed: ${e.message}`);
  console.log('  → Install manually: npx get-shit-done-cc@latest --claude --global');
}

// Step 3: Install Sutra commands
console.log('\n  [3/3] Installing Sutra commands...');
if (!existsSync(commandsDir)) mkdirSync(commandsDir, { recursive: true });

const sutraCommandsDir = join(packageRoot, 'commands');
if (existsSync(sutraCommandsDir)) {
  const commands = readdirSync(sutraCommandsDir);
  for (const file of commands) {
    copyFileSync(join(sutraCommandsDir, file), join(commandsDir, file));
    console.log(`  ✓ Installed ${file}`);
  }
}

// Write version marker
writeFileSync(join(claudeDir, 'sutra-version'), '1.0.0\n');

console.log(`
  Done! Sutra OS v1.0.0 installed.

  What you got:
    gstack  — 32 skills (design, QA, ship, review, security)
    GSD     — 57 skills (plan, execute, verify, debug, autonomous)
    Sutra   — Company onboarding & orchestration

  To start building a company:
    Open Claude Code → type /sutra-onboard

  To check what's available:
    /gsd:help         — GSD commands
    /sutra-onboard    — Start a new company

  Questions? https://github.com/asawa-inc/sutra
`);
