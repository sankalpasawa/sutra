# Sutra — TODO

## Restructure: Separate Problem-Solving from Implementation Bureaucracy

**Source**: Maze F7 Optional Auth — full SUTRA pipeline run (2026-04-05). CEO feedback: "We don't need to follow a process if we directly know the answer."

**The Problem**: Sutra conflates two distinct things:

1. **Problem-solving process** — forcing you to think through edge cases, risks, department impacts, security implications BEFORE writing code. This is the thinking layer. It earned its keep on F7 (caught a real RLS security hole).

2. **Implementation bureaucracy** — writing INTAKE.md, SHAPE.md, SPEC.md files on disk, compliance gates between stages, artifact depth by tier, department sign-off tables. This is the paperwork layer. It added zero value for trivial features (privacy policy = 28 audit FAILs on process, but the code was fine).

**The Principle**: If you know the answer, just do it. Process should only trigger when the problem is genuinely ambiguous, risky, or cross-cutting.

**The Deeper Problem**: The process doesn't know WHERE you're entering the problem lifecycle. Every problem goes through stages:

```
1. IDENTIFY  — recognize there IS a problem ("users lose preferences when clearing cookies")
2. ANALYZE   — understand the problem deeply ("affects retention, touches auth, sessions, RLS")
3. DESIGN    — figure out WHAT to build ("magic link, session migration, scoped RLS")
4. IMPLEMENT — build it
```

But these stages don't all happen in the same session or by the same person. F7 auth was IDENTIFIED in the HOD meeting. It was ANALYZED when the CPO/CEO prioritized it. By the time it reached the build session, stages 1-2 were already done — they exist in meeting notes (`os/meetings/`), in the INTAKE, in the TODO priority order.

The current SUTRA pipeline forces you to re-document stages that already happened upstream. The INTAKE for F7 was essentially restating what the HOD meeting already decided. The process should detect: "this problem was already identified and analyzed — pick up from DESIGN."

**The principle**: decisions need to be traceable (you should be able to find WHY something was decided), but the trace doesn't need to be a fresh artifact. It can be a pointer to where the thinking already lives — a meeting note, a TODO comment, a prior session's output.

### What to Restructure

- [ ] **Split process into thinking vs artifacts** — the thinking prompts (edge cases? RLS? sign-out path? department impact?) are valuable. The mandatory file artifacts (INTAKE.md, SHAPE.md, SPEC.md as separate files with section requirements) are overhead when the answer is obvious.
- [ ] **Auto-route by complexity** — trivial/standard features go DIRECT with optional thinking prompts. Significant/horizontal features get the full problem-solving layer. The current complexity tiers exist but don't affect the process depth enough.
- [ ] **Kill artifact-as-compliance** — the compliance agent should check "did you think about X?" not "does SHAPE.md have a per-department section?" Checking for thinking is valuable. Checking for word counts and section headers is bureaucracy.
- [ ] **Make the compliance agent problem-focused** — instead of "file exists? section exists? depth matches tier?", it should ask: "did you consider RLS implications? is there a rollback plan? what happens on sign-out?" Problem-solving questions, not format compliance.
- [ ] **Evidence from Maze F7**: SUTRA compliance caught 1 security hole, 1 incomplete migration, 2 scope gaps, 1 missing risk. All of these were *thinking* catches, not *artifact format* catches. The value was in the questions asked, not the documents produced.
- [ ] **Evidence from Maze INIT-0.1/0.2**: 28 FAIL verdicts on process compliance, but code quality was 7-8/10. The process was theater — auditing paperwork, not catching bugs. DIRECT mode would have shipped identical code faster.
- [ ] **Reconcile the three competing pipelines** into one that scales: minimal for trivial (just build), thinking-prompts for standard (are there edge cases?), full problem-solving for horizontal (per-department analysis, compliance audit).
- [ ] **Detect lifecycle entry point** — when a task arrives, ask: "where in the lifecycle is this?" If IDENTIFY and ANALYZE are already done (HOD meeting decided priority, INTAKE exists), skip to DESIGN. If DESIGN is also done (SPEC exists from a prior session), skip to IMPLEMENT. Don't re-document what's already documented elsewhere.
- [ ] **Trace decisions with pointers, not duplicates** — instead of writing a fresh INTAKE that restates the HOD meeting, write: "See `os/meetings/2026-04-04-hod-q2-kickoff.md` — priority decided there. Problem: users lose preferences. Why now: retention is the bet." One paragraph pointing to the source of truth, not a re-creation of it.
- [ ] **Make org knowledge cumulative** — the HOD meeting notes, TODO priorities, feature INTAKEs, and session outputs should form a connected graph. Each artifact should reference where the upstream thinking lives. The process adds value by connecting existing knowledge, not by generating fresh paperwork that duplicates it.
- [ ] **Remove mandatory artifacts for trivial features** — a one-file bug fix does not need INTAKE.md + SHAPE.md + SPEC.md + VERIFY.md + LEARN.md. A commit message with "what and why" is sufficient.
- [ ] **Keep LEARN.md for ALL features** — the one artifact that consistently produced value across every feature, including trivial ones. The "every increment needs a decrement" insight from INIT-0.3 came from LEARN. Learnings compound; paperwork doesn't.

### When to Restructure

Now. This blocks the next version (v2.0). The current process creates friction that makes companies fake compliance instead of doing real thinking. That's worse than no process at all.

---

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
