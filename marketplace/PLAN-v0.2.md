# Sutra v0.2 — Implementation Plan

*Date: 2026-04-19*
*Design: `sutra/marketplace/design/2026-04-19-v0.2-unified-deploy.md`*
*Supersedes: PLAN.md (v0.1, now historical)*
*Execution: inline. No subagents.*

**Goal:** Ship v0.2 — plugin strips shadow skills, becomes a thin bridge that invokes npm-packaged Sutra OS installer on first `/sutra`. External user gets one-install UX that deploys the full governance into their folder.

---

## Tasks

### T1 — Fix npm package branding (5 min)

**Files:** `sutra/package/package.json`

Current leaks:
- `"author": "Asawa Inc."` (D29 violation)
- `"license": "UNLICENSED"` (per F19 default, should be MIT)
- Description mentions `gstack + GSD` — may be legacy (keep for now, not a D29 violation)

**Changes:**
```json
{
  "author": { "name": "Sutra", "url": "https://sutra.os" },
  "license": "MIT"
}
```

Validation: `jq '.author, .license' sutra/package/package.json` — outputs Sutra + MIT.

### T2 — Verify `install.mjs` integrity (15 min)

**Files:** `sutra/package/bin/install.mjs` (22KB, read-only review)

Read first + last 100 lines to understand entry point, arg parsing, + what it writes. Look for:
- Does it take `init` subcommand? `update`? `--uninstall`?
- Does it handle target dir detection (cwd)?
- Does it copy hooks/ + os-core/ into target `.claude/`?
- Does it merge settings.json non-destructively?
- Any shebang / executability concerns?
- Any `asawa` strings leaking in output messages?

Don't modify install.mjs in this session unless there's a critical bug — the founder said "use it the way it's working." Just verify.

### T3 — Run install.mjs locally in a throwaway folder (10 min)

**Commands:**
```bash
mkdir -p /tmp/sutra-test-install
cd /tmp/sutra-test-install
node /Users/abhishekasawa/Claude/asawa-holding/sutra/package/bin/install.mjs init
ls -la
cat CLAUDE.md 2>&1 | head -20
ls .claude/hooks/sutra/ 2>&1 | head
ls os/ 2>&1
```

Expected: folder has CLAUDE.md, TODO.md, os/, .claude/hooks/sutra/, .claude/os/. If it errors, document the error + decide fix scope.

### T4 — Push `sutra/package/` to `sankalpasawa/sutra-os` GitHub repo (10 min)

**Commands:**
```bash
# Copy package contents to a clean staging dir
mkdir -p ~/plod/sutra-os-staging
cp -R sutra/package/. ~/plod/sutra-os-staging/

# Run leak audit first
cd ~/plod/sutra-os-staging
grep -rniE '\basawa\b' . --exclude-dir=.git || echo "no leaks"

# If audit clean, init git + push
git init -b main
git add .
git -c user.email=sankalp@sutra.os -c user.name=Sankalp commit -m "sutra-os v1.0 — OS installer for Claude Code projects"
gh repo create sutra-os --public --source=. --remote=origin --push
```

Expected: `https://github.com/sankalpasawa/sutra-os` exists, public, with install.mjs + hooks + os-core + templates.

### T5 — Rewrite plugin (30 min)

**Files:** `~/plod/dologans/*` (the deployed plugin copy)

Strip in v0.2:
- `skills/input-routing/` (delete — duplicate of dispatcher-pretool Check 9)
- `skills/depth-estimation/` (delete — duplicate of dispatcher-pretool Check 10)
- `skills/readability-gate/` (delete — duplicate of READABILITY-STANDARD.md + stop hook)
- `skills/output-trace/` (delete — handled natively by Sutra hooks post-install)
- `hooks/depth-marker-pretool.sh` (delete — duplicate)
- `hooks/estimation-stop.sh` (delete — duplicate)
- `hooks/hooks.json` (delete — no hooks in plugin anymore)
- `commands/depth-check.md` (delete — skill handles this post-install)

Keep:
- `.claude-plugin/plugin.json` (bump to 0.2.0)
- `README.md` (rewrite for v0.2)
- `LICENSE`
- `CHANGELOG.md` (add v0.2.0)
- `scripts/leak-audit.sh`

Rewrite:
- `commands/sutra.md` — new content: check for `.claude/hooks/sutra/`, install if absent via `npx github:sankalpasawa/sutra-os init`, else show CEO day.

### T6 — Commit + push plugin update (5 min)

```bash
cd ~/plod/dologans
git add -A
git commit -m "v0.2: strip shadow skills, make plugin a thin bridge to sutra-os npm"
git push
```

### T7 — Sync back to asawa-holding source (10 min)

The plugin source in `asawa-holding/sutra/marketplace/plugin/` is the canonical copy. After v0.2 lands in ~/plod/dologans, sync back to the monorepo so they don't diverge.

```bash
# Remove v0.1 shadow skills from asawa-holding copy
rm -rf sutra/marketplace/plugin/skills/{input-routing,depth-estimation,readability-gate,output-trace}
rm -rf sutra/marketplace/plugin/hooks
rm sutra/marketplace/plugin/commands/depth-check.md

# Copy v0.2 plugin from ~/plod/dologans back into asawa-holding
cp -R ~/plod/dologans/. sutra/marketplace/plugin/
# (except .git/)
rm -rf sutra/marketplace/plugin/.git

# Commit in sutra submodule
cd sutra && git add marketplace/ && git commit -m "marketplace v0.2: unified deploy (plugin = thin bridge; sutra-os npm = real OS)"
cd ..
git add sutra && git commit -m "bump sutra: marketplace v0.2 unified deploy"
```

---

## Validation (before handing to founder)

```bash
# 1. npm package branding clean
jq '.author, .license' sutra/package/package.json

# 2. Leak audit — no asawa strings in published surface
grep -rniE '\basawa\b' ~/plod/sutra-os-staging --exclude-dir=.git
grep -rniE '\basawa\b' ~/plod/dologans --exclude-dir=.git --exclude="leak-audit.sh"

# 3. Plugin structure correct
find ~/plod/dologans -type f -not -path '*/.git/*' | sort
# Expect: plugin.json, README.md, LICENSE, CHANGELOG.md, commands/sutra.md, scripts/leak-audit.sh
# That's 6 files. No skills/, no hooks/.

# 4. install.mjs works in throwaway
cd /tmp/fresh-test && node ~/plod/sutra-os-staging/bin/install.mjs init
ls -la
```

---

## Test command for founder (once T1-T7 done)

```bash
cd /tmp && rm -rf sutra-new-user && mkdir sutra-new-user && cd sutra-new-user
git clone https://github.com/sankalpasawa/sutra-plugin
claude --plugin-dir ./sutra-plugin
# Then inside Claude Code:
/sutra
# Should detect absent install → run npx → deploy OS → activate
```

---

## What this ships

- Plugin v0.2 (6 files, zero governance logic)
- sutra-os on GitHub (published installer + hooks + OS docs)
- One-command UX for external users: install plugin → type /sutra → get the full Sutra OS

## What this does NOT ship (deferred)

- npm registry publish (GitHub-hosted for now)
- Hook auto-update (user runs `npx sutra-os@latest update` manually when prompted)
- CEO day data pulls (v0.3 — requires the post-install os/*.md files to have real content)
- Managed Agent / service architecture (Route 2 — Q3+)

---

## Self-review

- [x] No recreation — plugin has zero hook logic, zero governance docs
- [x] Single install UX — plugin triggers npm installer on first /sutra
- [x] Subagent inheritance — via folder-scoped `.claude/hooks/sutra/` after install
- [x] D29 compliance — leak audits on both plugin + sutra-os surfaces
- [x] Maintainability — one source of truth (asawa-holding), synced to sankalpasawa/sutra-os
- [x] External users — GitHub-hosted install works without npm publish credentials
