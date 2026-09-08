# ADR-036: Writing style has one home, MINIMIZE first, enforced at Stop

**Status**: Accepted (implemented 2026-09-08, plugin core 2.248.0)
**Date**: 2026-09-08
**Driver**: founder direction 2026-09-02 — "add 'minimize', and let's put everything into one place so that it is followed very strictly" — recorded as D72 in `holding/FOUNDER-DIRECTIONS.md`.

## Context

Until this decision Sutra's writing rules lived in four authoritative places plus prose copies: the plugin skills `caveman` (D51 grammar compression), `anti-glaze-tone` (D58 founder-facing candor), `readability-gate` (shape rules) with `sutra/layer2-operating-system/READABILITY-STANDARD.md` (a self-declared Tier 1 sealed document), and `writing-llm-md` with its byte-identical L1 twin `holding/skills/writing-llm-md.md` whose promote-by date (2026-09-05) had passed. Root `CLAUDE.md`, `sutra/CLAUDE.md` and the `/core:start` governance block each carried their own diverging paraphrase. No hook enforced any prose rule; `output-behavior-lint.sh` logged two advisory patterns and `md-standard-gate.sh` checked 3 of 12 markdown rules. An inventory run (7 readers, 3 sweeps) found 267 rules and 189 cross-references, 19 pairwise contradictions between the copies, and the sealed standard contradicting itself on box glyphs.

## Decision

1. **One home.** `sutra/marketplace/plugin/skills/writing-style/SKILL.md` (L0, fleet) is the only authoritative writing document. It holds six principles — P0 MINIMIZE, P1 STRUCTURE, P2 COMPRESS, P3 CANDOR, P4 GROUND, P5 FILE-SHAPE — a surface-by-principle scope matrix, the budgets, the shapes, the markdown rules R1-R12, activation and revoke, and the enforcement contract, in 220 lines.
2. **MINIMIZE is principle 0.** It chooses what to say (remove-and-diff: a unit stays only if deleting it changes what the reader does next) and is distinct from COMPRESS, which chooses how to say what survives. Rules M1-M8 with budgets: outcome in 5 lines, 40 prose lines per turn advisory, 60 hard.
3. **HARD Stop gate.** `hooks/writing-style-gate.sh` reads the current turn's assistant text, strips everything that is not prose, and blocks on banned phrases, structural glyphs, the 60-line budget, task tables without Impact + Effort, and ask-to-run in pinned projects. The banned regex list lives inside the skill file between HTML comment markers and is read at runtime; no second copy exists (a unit test asserts this).
4. **Deterministic revoke.** `per-turn-discipline-prompt.sh` matches whole-line phrases and writes a session-scoped dotfile; the model never writes the marker.
5. **ASCII only.** Box-drawing and block glyphs (U+2500-U+259F) are banned in prose; progress bars use `#` and `.`. This resolves the sealed standard's contradiction in favour of D-UX-1.
6. **Legacy homes become redirect stubs** whose frontmatter keeps the original trigger phrases; full bodies are archived under `sutra/archive/2026-09-08-writing-style-consolidation/`. The sealed READABILITY-STANDARD.md is unsealed by D72 and stubbed the same way.
7. **Fleet default HARD after `/core:start`**, uniform across tiers (D34). Per-project opt-down (`writing_style: advisory`) is configuration; `asawa-holding` and `sutra` are pinned hard.

## Consequences

- Every Sutra session reads one document; the seven paraphrases collapse to pointers.
- A turn that glazes, narrates, pads past 60 lines, or ships a task table without Impact + Effort is redone once (loop-safe via `stop_hook_active`).
- Customer-facing copy is protected three ways: file and fence contents are never judged, a keyword classifier on the ask downgrades P2/P3, and an audience marker exists as a fallback.
- Six shipped skills already exceed the 250-line cap; MD-5 blocks growth, not existence, for tracked files.
- Codex consult (thread 01a0807d): 5 P1 (2 accepted, 3 refuted with wording folds), 4 P2 accepted. DeepSeek lane SKIPPED (account unfunded).
- Reversal path: the archive restores any legacy body byte-for-byte; the gate has a four-level kill ladder.

## Not adopted

Unicode bar glyphs as a single exception (two authorities), a long-form user-cue escape from the hard budget, a per-repo baseline allowlist for tracked markdown (breaks T4 installs without a fresh-install gate), and removal of the `/caveman` Desktop autotype in this release (Desktop lane).

---

provenance: {author: claude, date: 2026-09-08, inputs: [D72, workflow wf_5cf3e80e inventory + design, codex consult 01a0807d, skills/writing-style/SKILL.md], review: codex, supersedes: none, confidence: high, gaps: [deepseek lane unfunded]}
