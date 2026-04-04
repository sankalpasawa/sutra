# Sutra — TODO

## Version Upgrade Pipeline (major — build when ready for multi-company upgrades)

When Sutra pushes a new version, existing companies can break. Every company has different tiers, stages, conventions, and file structures. A one-size-fits-all push will cause conflicts.

**Required capability: staged rollout with per-company compatibility testing.**

### The Pipeline

```
Sutra builds new version
    → Compile per company (tier-aware, not one-size-fits-all)
    → Dry run: diff new OS against company's current OS
    → Compatibility report per company (conflicts, breaking changes)
    → Resolve: auto-fix path differences, flag process conflicts for CEO
    → Push only clean updates to company repos
    → Verify: next session confirms hooks fire, no crashes
```

### What to Build

- [ ] **Per-company compiler** — takes Sutra version + Asawa framework + company config → produces company-specific bundle. Already conceptually defined in CLIENT-ONBOARDING.md Phase 7, but needs to handle UPGRADES not just first-time installs.
- [ ] **Diff engine** — compare new compiled OS against company's current OS. Flag: new files, changed files, removed files, hook conflicts, process conflicts.
- [ ] **Compatibility report generator** — for each company, produce a report: what changes, what conflicts, what needs manual resolution.
- [ ] **Auto-resolver** — handle simple conflicts automatically (path renames, config key additions, hook reordering).
- [ ] **Manual conflict protocol** — when auto-resolve can't handle it, produce a clear question for the company CEO: "New version adds X, but your setup has Y. Choose: A) adopt X and migrate Y, B) keep Y and skip X, C) custom."
- [ ] **Rollback mechanism** — if an upgrade breaks a company, revert to previous version. Git makes this possible (revert the commit), but the tooling should make it one command.
- [ ] **Version compatibility matrix** — track which companies are on which version, what's required for each upgrade path (v1.0→v1.1, v1.0→v2.0, v1.1→v2.0).
- [ ] **`/sutra-upgrade` command** — single command that runs the full pipeline for one or all companies.

### When to Build

Not now. Build this when:
- There are 3+ companies on different versions
- A version upgrade has broken a company at least once
- The manual push-and-pray approach becomes painful

### Current State
- Manual file copying works for 3 companies (DayFlow, Maze, PPR)
- All on v1.0/v1.1, minimal divergence
- No upgrade has broken anything yet (because upgrades are rare and manual)
