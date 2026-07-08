# Sutra — Current Version

## v2.39.20 (2026-07-08, HEAD)

**Blueprint marker visibility + out-of-repo guard (Testlify field incident 2026-07-08).** A fleet client emitted a correct prose BLUEPRINT (Output + Verified-by included) and `blueprint-check.sh` still HARD-blocked Write twice — the hook reads ONLY `.claude/blueprint-registered`, and no fleet-visible surface (per-turn reminder, hook stderr) said to write it; the marker contract lived solely in the non-auto-invoked `core:blueprint` skill. The model's only advertised exit (`BLUEPRINT_ACK=1`, unusable on Write tool calls) taught a Bash+ACK bypass of the gate. Fix 1: `per-turn-discipline-prompt.sh` now states the marker contract (write the marker via the Write tool with `HAS_OUTPUT`/`HAS_VERIFY`/`HAS_PER_STEP_VERIFY`) before the first Edit/Write of each turn. Fix 2: `blueprint-check.sh` out-of-repo guard — absolute paths outside `$CLAUDE_PROJECT_DIR` (`~/.claude/**` memory files, sibling repos) are out of scope; they could never match any whitelist and were blocked by accident. Inside-repo enforcement unchanged. Tests: `test-blueprint-marker-visibility.sh` 6/6. Fix + bump ship together (self-shipping PR #80). (#78 depth-gate + error-text split ships separately; A4 text-validation via #73.)


## v2.39.19 (2026-07-06, HEAD)

**#63 — /core:start documents the H-Sutra header contract it enforces.** `h-sutra-enforce.sh` HARD-blocks every response whose first line isn't a valid header, but `/core:start` wrote a CLAUDE.md governance block with zero references to that header (`grep "H-Sutra|DIRECTION|VERB"` → 0 hits) — an invisible rule that caused repeated "redo with the header" blocks. `scripts/start.sh` now writes an **"H-Sutra Header"** section (exact format, DIRECTION/VERB vocabulary, example, STAGE-1-FAIL variant) as the first documented behavior; the hook's diagnostic points to it. Verified: generated-block grep → 5 hits. The fix + this version bump ship together in this PR (self-shipping). After update, clients re-run `/core:start` to regenerate the block. (A4 block-text validation ships separately via #73.)


## v2.39.18 (2026-06-30, HEAD)

**loop-budget-guard: per-turn reset + agent-orchestration exemption (fixes the session-wide hard-stop).** The guard's tool-call counter was cumulative-per-session and never reset, so a long working session crossed the 250 ceiling on ordinary Bash/Read/Write calls and hard-stopped itself ("tool-budget guard hard-stopped further file reads this session") — and the deadlock blocked the very Bash needed to update out of it. New `loopguard-turn-reset.sh` (UserPromptSubmit) truncates the counter at the start of each real user turn → budget is now **per-turn** (a 250-call runaway in one turn still blocks; synthetic turns skipped, so within-turn loop detection is intact). `Agent`/`Task`/`Workflow` dispatches are exempt from counting (a fan-out is not a loop; opt back in with `LOOP_GUARD_COUNT_AGENTS=1`). Guard suite 12/12. Also ships **A4 block-text validation** (`perturn-text-validate.sh` — validates the emitted Input Routing / Depth / Output Trace; `blueprint-text-validate.sh` detection hardening; profile-aware). D13 cascade: risk LOW, backward-compatible.


## v2.39.17 (2026-06-25, HEAD)

**Loop/tool-budget guard promoted to L0 (A6).** Always-on PreToolUse hook blocks runaway agents + infinite loops before execution; fail-open. Per-session budget (250) + frequency-in-window repeat detection; kill-switches + LOOP_GUARD_ACK. 8/8 tests. D13 cascade: risk LOW.


## v2.39.13 (2026-06-14, HEAD)

**Flow fires every turn like the H-Sutra header — emission_mode literal-text fix.** Root cause: Flow was the only per-turn block with `emission_mode: skill_invocation` (a Skill tool call), which the model rationalized skipping on light turns while literal-text blocks (header/routing/depth) fired reliably. Fix: fast-path now emits a literal one-line `FLOW: <type> · fast-path · <n> atom · classify->answer` block as TEXT every turn; the `core:flow` Skill is invoked only on substantive/multi-step/mutation turns. Two files: `sutra-defaults.json` `.per_turn_blocks.flow` + `hooks/per-turn-discipline-prompt.sh` FLOW ACTIVATION block (duplicate Backstop line collapsed).

## v2.39.12 (2026-06-14)

**flow-gate HARD fleet-wide.** Edit/Write to non-whitelisted path or Task/Agent dispatch without core:flow markers → exit 2.

## v2.39.11 (2026-06-14)

**Flow on EVERY input/type + 1-step fast-path for trivial; gate widened to Task/Agent.** sutra-defaults all-types + cost_model, per-turn reminder, flow-gate Task branch.

## v2.39.10 (2026-06-14)

**Flow auto-activation — core:flow fires per turn, TYPE-gated** (work-bearing turns run the spine; trivial skip). sutra-defaults.json per_turn_blocks.flow + per-turn-discipline-prompt.sh reminder + flow-gate backstop.

## v2.39.9 (2026-06-14)

**The Flow — work-resolution spine shipped as skills (core:flow + workflow-type-resolve + lens + cynefin) + SOFT flow-gate hook.** Canon ADR-026 + ADR-027. See plugin CHANGELOG.

## v2.39.6 (2026-05-31)

**Prompt-capture hook (UserPromptSubmit) — fleet L0.** Every founder prompt is appended losslessly to the project's `holding/state/prompts/<YYYY-MM>.jsonl` (ts · session_id · prompt). Non-blocking; kill via `PROMPT_CAPTURE_DISABLED=1` or `~/.prompt-capture-disabled`. Registered in `hooks/hooks.json` UserPromptSubmit. Promoted from Asawa-local L1 same day.

## v2.39.5 (2026-05-28)

**`h-sutra-enforce` hook — actionable mis-cased-header error.** Malformed (Title-case/lowercase DIRECTION·VERB) headers now report "DIRECTION·VERB must be UPPERCASE" with a canonical example, instead of the misleading "header missing". Valid-header pass/block logic unchanged (regression-tested).

## v2.39.4 (2026-05-13)

**`prd-discipline` skill v2** — REFACTOR pass plugs 5 baseline-test rationalizations.

- Skill body at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- v2 additions: §1 namespace-collision check + naming-with-alternatives · §3 scale-undershoot surface · §4 canon-typed-entity rule · §5 TODO-is-not-an-alibi.
- Baseline test at `.enforcement/skill-tests/2026-05-13-prd-discipline-baseline.md`.
- Run `/reload-plugins` to activate.

## v2.39.3 (2026-05-13)

**Add `prd-discipline` skill** — product-document writing discipline.

- New skill at `sutra/marketplace/plugin/skills/prd-discipline/SKILL.md`.
- 5 invariants: STRUCTURED · VISUAL FIRST · RESTRUCTURE-ON-BULK · CONNECTED · GAP-SURFACING.
- Composes with ADR-020 Layer-B Product Authoring Template.
- Run `/reload-plugins` to activate in-session.

## v2.39.2 (2026-05-13)

**Remove 15-min hard cap on `codex-sutra` + `deepseek` skills** (founder D2026-05-13).

- 900-s wrapper kill removed from both skills; replaced with SIGINT trap (founder Ctrl-C → SIGTERM/SIGKILL on the whole process group).
- Heartbeat warnings now fire every 10 min during long-running calls (was one-shot at 10 min). Stall warn at 5 min no-progress unchanged.
- `deepseek`: `curl --max-time 900` flag removed — DeepSeek API server-side timeout is the only network bound.
- `sutra-defaults.json`: `deepseek.limits.wall_seconds_hard_cap` is now `null`.
- Fail-closed: `Hard-cap timeout / reason=timeout / exit 124` → `Founder interrupt (Ctrl-C) / reason=interrupted / exit 130`.
- Native canon: `phase-D-codex-review.md` + `HS-7-codex-queue-stale.md` updated with amendment line. HS-7 itself unchanged (watches review-backlog health, not per-call duration).

Rationale: long-reasoning runs were being killed before completion. Founder Ctrl-C is the only interrupt path now; stall + heartbeat keep silent hangs observable.

For prior release history, see `marketplace/plugin/CHANGELOG.md`.
