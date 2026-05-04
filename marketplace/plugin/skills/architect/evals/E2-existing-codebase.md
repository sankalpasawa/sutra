# Eval E2 — Existing Codebase (grounded in observed files)

## Input

> Architect from the existing files in `~/Claude/asawa-holding/sutra/marketplace/plugin/`. The architecture is currently implicit — there's no ARCHITECTURE.md. Document what's actually here: the skills system, the hooks system, the marketplace catalog, the build-layer enforcement, and how they wire together. Risk profile: developer tooling shipped to fleet of T2/T3/T4 clients.

## Required assertions (output MUST contain)

| # | Assertion | Where to check |
|---|---|---|
| 1 | All 8 main sections emitted | grep section headings |
| 2 | C4 Level 2 references containers that ACTUALLY exist in the inspected directory (e.g., `skills/`, `hooks/`, `.claude-plugin/`, `lib/`, `commands/`) | section 3 + cross-check with `ls` of the path |
| 3 | No fabricated file paths — every cited file path can be `ls`-confirmed against the real directory; AND each C4 L3 section references at least one specific file path within the container being decomposed (not just directory names) | section 3, section 4 |
| 4 | C4 L3 emits for 1-3 high-leverage containers (hook system, build-layer enforcer, or comparable distinctive surfaces); each L3 cites at least one real file or function name from the directory | section 4 |
| 5 | At least one ADR addresses a decision visible in the actual codebase (any decision recorded in CHANGELOG.md, hooks.json, or plugin.json description history qualifies) — grounded in observable history, not invented | section 5 |
| 6 | STRIDE entries reflect actual fleet-distribution surface (e.g., MCP connector tool execution, plugin auto-update from marketplace, hook execution sandbox) | section 6 |
| 7 | Scaling axes addresses fleet size growth (T4 client count) as a real axis | section 7 |
| 8 | Build-Layer table is explicit about D38 enforcement scope: PLUGIN-RUNTIME paths must be L0; LEGACY-HARD paths require markers; SOFT paths are advisory | section 8 |
| 9 | Architecture acknowledges sutra is a submodule of asawa-holding (parent/child relationship) | section 1 or 3 |
| 10 | At least one open-question or "noted limitation" entry — the skill should not pretend to have full visibility on first pass | end of document |

Pass = ≥8/10 assertions hit.

## Anti-assertions (output MUST NOT contain)

- Cited file paths that don't exist (would fail `ls` check)
- Inferred / hallucinated containers not present in the real directory
- Generic SaaS architecture pattern applied to a CLI plugin codebase (taste violation)
- Build-Layer table that ignores the actual D38 categories visible in `holding/hooks/build-layer-check.sh`

## Baseline comparison

Without the skill, Claude typically:
- Describes the codebase narratively without a C4 hierarchy
- Doesn't ground every reference in observed files (mixes real + plausible)
- Misses the parent/submodule relationship
- Doesn't surface D38 build-layer rules as part of the architecture

Skill should win on assertions 2, 3, 5, 8, 9 vs baseline. This eval is the strongest test of "no fabrication" discipline.
