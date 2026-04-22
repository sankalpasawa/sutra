# Codex Consult — Sutra CLI Collision Fix (Option A + D)

**Date:** 2026-04-22
**Author:** CEO of Sutra sub-agent (dispatched from Asawa holding, Depth 5)
**Parent design doc:** `2026-04-22-sutra-cli-collision.md` (339 lines)
**Consult model:** OpenAI Codex CLI v0.118.0 (`codex exec`), model `gpt-5.4`
**Status:** Consult complete — **DISAGREE verdict; surface to founder before any implementation.**

---

## 1. Invocation method used

**Path used: Direct CLI via Bash.** `codex exec --skip-git-repo-check "<prompt>"` from `/tmp/codex-consult/`.

- Path 1 (Skill tool `codex`) — not attempted; the `codex` skill lists three modes (review/challenge/consult) but its invocation surface is interactive. Direct CLI was simpler and produced faithful, auditable transcripts.
- Path 2 (Direct CLI) — **worked.** Two `codex exec` calls, ~90s and ~130s respectively, each returning ~3k-token answers grounded in live shell probes and web searches codex ran itself.
- Path 3 (escalate to main context) — not needed.

Both passes were run synchronously; raw outputs captured at `/tmp/codex-consult/pass1-output.txt` (180 lines) and `/tmp/codex-consult/pass2-output.txt` (138 lines). Full transcripts in §6 below.

Notable: during Pass 1, codex ran live probes against bash/zsh/dash to validate `type -a` / `command -v` behavior before answering, and issued 5 web searches against POSIX spec, fish docs, and nushell docs. Pass 1 is anchored in shell-level evidence, not just pattern-matching.

---

## 2. Consult verdict (Pass 1 — faithful paraphrase)

### Q1. Name choice

**Codex: `sutra-core` is correct. Confidence 0.87.**

Ranked the 6 candidates on three axes:
- Collision probability (lower is better): `sutra-plugin` < `sutra-os` < `sutra-core` < `sutra-cli` < `sutra-run` < `score`. `score` is a hard no (too short, too generic).
- Brand alignment with `core@sutra`: `sutra-core` < `sutra-plugin` < `sutra-cli` < `sutra-run` < `sutra-os` < `score`. Only `sutra-core` preserves both halves of the marketplace identifier in a human-obvious way.
- Typing ergonomics: `score` < `sutra-os` < `sutra-run` < `sutra-cli` < `sutra-core` < `sutra-plugin`.

`sutra-core` is not the shortest, but the clarity premium dominates. Codex endorses Claude's pick.

### Q2. Grace-period shim

**Codex: two releases (v1.8.x + v1.9.x), remove in v2.0.0. Disagrees with Claude's one-release proposal.**

"Renaming a documented executable is a breaking change... the strict SemVer treatment is: deprecate in a minor, remove in the next major. One release is too short because deprecation notices have weak real-world reach." Maintenance cost of the shim is negligible; migration benefit is high. The right framing: "the deprecation is minor-appropriate; the removal is major-only."

### Q3. Option D portability

**Codex: `type -a` is not portable enough. `command -v` is closer to correct, but Option D itself is conceptually wrong.**

Live-probe evidence codex gathered:
- `type -a` works in zsh and bash.
- `dash` does not support `-a`.
- `fish` has its own `type` semantics; `command -v` equivalent searches external commands and does not report alias precedence.
- `nushell` uses `which` and `scope aliases`, not POSIX `type`/`command`.
- `which -a` is non-standard, often blind to aliases/functions.
- `$BASH_SOURCE`/`$0` inside the script cannot detect a pre-invocation alias collision — because if the alias wins, the script never runs.

**The deeper point (this is where Pass 1 starts tilting against the design):** "An invoked external command cannot reliably inspect the caller shell's higher-priority alias/function table across shells. The correct implementation is to harden every internal shell-out to use the plugin's absolute binary path, and treat command-resolution diagnostics as a separate, shell-specific install check rather than a mandatory runtime gate."

This is codex quietly signaling that Option D is structurally broken as specified. Pass 2 makes it explicit.

### Q4. Helper namespace

**Codex: rename helpers to `sutra-core-*`. Disagrees with Claude's "keep helpers as `sutra-*`" proposal.**

"Keeping `sutra-go`, `sutra-reset`, and friends while renaming only the primary binary leaves you with a split namespace that teaches the wrong mental model... `sutra-*` reads like vendor-global namespace, not `core@sutra` namespace. The double-breakage cost is real, but that is exactly why you should pay it once and do the namespace cleanup coherently, with shims for the helpers on the same deprecation schedule as the main binary."

`sutra-core-*` is the right long-term shape because it distinguishes "plugin family" from "ecosystem brand."

### Q5. Open failure modes

**Codex surfaced five missed failure modes:**

1. **False confidence from Option D.** If internal calls are already rewritten to absolute paths, the runtime self-check adds no protection — but it can still produce false positives under wrappers, symlinks, or managed installs where the resolved path is not byte-for-byte the canonical plugin path.
2. **Shim stdout contamination.** If deprecation warnings go to stdout (or if stderr is consumed by slash commands / status parsing / update logic), the shim breaks machine-facing flows. Every shim warning must go to stderr and must be suppressible for internal calls.
3. **Stale references outside the obvious binaries.** Completions, docs, install scripts, examples, tests, telemetry labels, and update/uninstall code commonly keep the old basename and silently reintroduce the bug after the rename.
4. **Shell hashing / cached completions.** Shim removal can interact badly with shell command hashing and cached completions, creating "works in one tab, fails in another" behavior after a clean upgrade.
5. **The collision class is not actually closed.** If a user later binds `alias sutra-core=...`, the same bug returns. The real fix is absolute-path invocation, not faith that the new name stays collision-free forever.

**Pass 1 summary verdict:** **PARTIAL** — adopt Option A, keep shims through v2.0.0, rename helpers to `sutra-core-*`, and replace Option D with absolute-path internal invocation plus optional shell-specific diagnostics, not a mandatory runtime self-check.

---

## 3. Challenge verdict (Pass 2 — adversarial)

**Codex went harder in Pass 2 and escalated to FATAL FLAW. This is load-bearing — Pass 2 supersedes Pass 1.**

Codex picked three attack vectors:

### Attack 1 — The bug is `!sutra <sub>`, not `bin/sutra`

> Your slash commands are shelling out by bare name. In a shell, bare-name lookup is explicitly user-overridable by alias/function/hash/PATH order. That is expected behavior, not an edge case. If plugin internals need the plugin binary, they must invoke the plugin binary by absolute path or a runtime-provided resolved path. Full stop. Rename does not fix that design error. It just changes which bare name is vulnerable.

This is surgical. The design doc §2 (Root cause) correctly identifies shell name-resolution order as the mechanism, but then §4 Option A treats "change the name" as the fix rather than "stop using bare-name resolution." Codex is right that these are not the same intervention.

### Attack 2 — Option D is fake safety

> If `alias sutra=...` wins, `bin/sutra-core` never runs, so its self-check never fires. The only time the self-check runs is when you already succeeded in invoking `sutra-core`. And once you invoke the plugin binary directly, the check is redundant because the caller already resolved the right binary. Worse, if your internal calls stay as bare `sutra` during the shim window, the shim can also be bypassed by the same alias collision. The proposal claims defense-in-depth, but the defense is not on the path where failure happens.

This is the strongest single finding of the entire consult. Claude's design doc §4 Option D proposes the self-check as a "belt-and-suspenders" safety net. Codex correctly identifies that the self-check is **on the wrong code path**. The failure mode is "alias wins → plugin binary never runs." A self-check inside the plugin binary cannot fire when the plugin binary never runs. Option D only fires for benign cases where resolution already succeeded — which is the case that doesn't need a safety net.

### Attack 3 — Migration cost is upside-down relative to the bug

> You are proposing: 1) rename the primary executable, 2) add a deprecation shim, 3) add runtime warning noise, 4) plan a v2 removal, 5) keep helper names inconsistent, 6) still leave the general collision class unsolved, because `sutra-core` can also be shadowed. That is a lot of churn to avoid fixing one line of architecture: stop calling plugin internals through shell name resolution. The blast radius of the observed incident is narrow and specific... not evidence for a binary rename program, let alone a marketplace-blocking one. It is evidence that your internal execution contract is wrong.

Codex also flags governance failure: this is "complexity without proof... shipping mechanism before data." One dogfood collision → rename + shim + self-check + version choreography + naming asymmetry. That violates `feedback_case_by_case_implementation` (ship mechanism only when feedback demands) and the simplicity test of the Founding Doctrine.

### Codex's counter-proposal

- **Keep `bin/sutra`.** No rename.
- **Change every internal slash-command shell-out** from `!sutra <sub>` to an absolute path (or an injected resolved executable path — e.g., `${CLAUDE_PLUGIN_ROOT}/bin/sutra <sub>`).
- **Add a test** that aliases/functions named `sutra` do not affect plugin internal execution.
- Optionally add diagnostics in user-facing commands, but **not as the primary fix**.
- If you later want to rename for branding or long-term namespace reasons, make that a **separate decision with actual collision data** — not the fix for this incident.

**Pass 2 verdict:** **FATAL FLAW — the design cannot proceed as specified.**

---

## 4. Convergence assessment

**Verdict: DISAGREE.**

Codex found a fatal flaw Claude's design missed: **Option D's self-check cannot fire when the failure mode activates.** If the user's `sutra` alias wins name resolution, the plugin's binary never executes, so the self-check never runs. The "belt-and-suspenders" layer is not on the code path where the bug happens.

Claude's Pass 1 PARTIAL verdict is now superseded by Pass 2's FATAL FLAW because Pass 1 addressed specific design parameters (name choice, shim duration, portability, helper namespace) while treating the *shape* of the fix (rename + self-check) as valid. Pass 2 attacks the shape itself and wins the attack cleanly.

The real bug is in `sutra/marketplace/plugin/commands/*.md` — the `!sutra <sub>` invocations. These are the actual attack surface. The binary name is downstream of that.

This is the founder decision point. Per `feedback_converge_and_proceed`, codex and Claude **do not converge**. Escalation to founder is required before any implementation.

### Why this lands on DISAGREE and not PARTIAL

Pass 1 produced a PARTIAL verdict (4 revisions to apply). If the design were fundamentally sound, PARTIAL would be the right call and implementation could proceed with those revisions. But Pass 2 showed that the **primary mechanism of Option D is structurally broken** — not a parameter choice, the mechanism itself. That moves the verdict across the PARTIAL/DISAGREE line.

Additionally, codex's counter-proposal (absolute-path internal invocation) is:
- **Smaller scope** than the rename (6 slash-command files, no README/website/shim/version choreography).
- **Actually closes the bug class** (absolute-path invocation is immune to alias/function/hash collision for ANY name, now and forever).
- **Preserves v1.x muscle memory** for terminal-direct users.
- **Aligns with governance** — case-by-case, ship mechanism only when feedback demands, simplicity.

This is a strictly better fix. Not marginally better — strictly, on every axis the design doc lists.

---

## 5. Recommended next action

**Present codex's counter-proposal to founder. Do not proceed with Option A+D as specified.**

### The counter-proposal (codex's Attack 1 + 3 synthesized)

**Option E: Absolute-path internal invocation (no rename).**

1. **No binary rename.** `bin/sutra` stays.
2. **Rewrite every `!sutra <sub>` invocation** in `sutra/marketplace/plugin/commands/*.md` to use `${CLAUDE_PLUGIN_ROOT}/bin/sutra <sub>` (or equivalent absolute-path form that Claude Code's slash-command runtime can resolve at render time).
   - Files to edit (from design doc §7):
     - `commands/start.md` line 11
     - `commands/status.md` line 9
     - `commands/update.md` line 9
     - `commands/permissions.md` line 9
     - `commands/uninstall.md` line 10
     - `commands/depth-check.md` (verify for `!sutra ...` patterns)
3. **Audit `scripts/*.sh` and `hooks/*.sh`** for any `sutra <sub>` bare-name self-invocations. Replace with absolute-path form.
4. **Ship as v1.7.1 patch**, not v1.8.0 minor. This is a bug fix, not a feature.
5. **Add a regression test** (new T-file in `plugin/tests/`) that installs `alias sutra='echo HIJACKED'` and asserts that `/core:start` still activates correctly. This locks the class closed.
6. **Optionally** — and ONLY optionally — add a lightweight install-time warning in `scripts/onboard.sh` that runs `command -v sutra` and warns the user if the resolved path is not the plugin's binary. This is diagnostic, not a runtime gate. Low effort, informative, does not block.

### What to do with the rename idea

Park it. If branding pressure or ecosystem namespace cleanup justifies `sutra-core` later, revisit with real collision data. Right now there is one dogfood incident. That is not a dataset. That is an anecdote that triggered correct architectural analysis.

### What Claude's original design got right

- Correctly diagnosed the root cause (shell name resolution order, aliases winning).
- Correctly identified the blast radius (power users with `sutra` in rc files).
- Correctly enumerated downstream deps in §7.
- Correctly parked Options B and C on collision grounds.

The error was in the fix, not the diagnosis.

### Files the implementation PR will touch (under Option E)

| File | Change |
|---|---|
| `sutra/marketplace/plugin/commands/start.md` line 11 | `!sutra start` → `!${CLAUDE_PLUGIN_ROOT}/bin/sutra start` (or equivalent) |
| `sutra/marketplace/plugin/commands/status.md` line 9 | Same pattern |
| `sutra/marketplace/plugin/commands/update.md` line 9 | Same pattern |
| `sutra/marketplace/plugin/commands/permissions.md` line 9 | Same pattern |
| `sutra/marketplace/plugin/commands/uninstall.md` line 10 | Same pattern |
| `sutra/marketplace/plugin/commands/depth-check.md` | Audit + update if present |
| `sutra/marketplace/plugin/scripts/*.sh` | Audit all 6 scripts for `sutra <sub>` bare calls; replace with `"$(dirname "$0")/../bin/sutra" <sub>` or absolute path |
| `sutra/marketplace/plugin/hooks/*.sh` | Audit all 8 hooks for same pattern |
| `sutra/marketplace/plugin/.claude-plugin/plugin.json` | Version bump `1.7.0` → `1.7.1` (PATCH, not MINOR) |
| `sutra/marketplace/plugin/CHANGELOG.md` | Add v1.7.1 entry: "fix: internal slash-command shell-outs now use absolute plugin binary path, immune to user `sutra` alias/function collision. No user-facing changes." |
| `sutra/marketplace/plugin/tests/T9-alias-collision-regression.sh` (new) | Regression test — install alias, run `/core:start`, assert activation succeeded. |
| `sutra/marketplace/plugin/README.md` | No change — user-facing invocation is unaffected. |
| `sutra/website/**` | No change — no rename. |

**Total: ~15 file edits, 1 PATCH version bump, 1 new regression test, 0 docs/website/shim churn.**

Versus Option A+D's ~35 file edits, MINOR version, deprecation shim, self-check code, website updates, and helper-namespace decision carried forward.

### Immediate action for founder

1. **Decide.** Option A+D (Claude's original) vs Option E (codex's counter) vs something else.
2. If Option E — open implementation PR targeting v1.7.1 patch. Estimated effort: half a day. Depth 5 per `feedback_sutra_deploy_max_depth` (Sutra→company deploy).
3. If Option A+D anyway — apply Pass 1's four PARTIAL revisions (two-release shim, `sutra-core-*` helpers, drop `type -a` for `command -v`, harden stdout/stderr split) AND accept that Option D's self-check is theater, AND still fix the bare-name invocations in commands/. This is more work than Option E for less benefit.
4. If hybrid — could ship Option E *first* as v1.7.1 (closes the bug), then consider rename as a separate v1.8.0 branding decision later with real collision data.

---

## 6. Raw codex output

### Pass 1 — Consult (5 questions, PARTIAL verdict)

Full transcript captured at `/tmp/codex-consult/pass1-output.txt` (180 lines). Final answer block:

```
**Q1. Name choice**

`sutra-core` is the right target. On collision probability, I rank the six names:
`sutra-plugin` < `sutra-os` < `sutra-core` < `sutra-cli` < `sutra-run` < `score`;
`score` is a hard no because it is short, generic, and far more likely to collide
with existing commands than any `sutra-*` form. On brand alignment with `core@sutra`,
I rank: `sutra-core` < `sutra-plugin` < `sutra-cli` < `sutra-run` < `sutra-os` <
`score`; only `sutra-core` preserves both halves of the marketplace identity in a
human-obvious way. On typing ergonomics, I rank: `score` < `sutra-os` < `sutra-run`
< `sutra-cli` < `sutra-core` < `sutra-plugin`; `sutra-core` is not the shortest,
but it is still easy enough to type and materially clearer than every serious
alternative. Winner: `sutra-core`. Confidence: 0.87.

**Q2. Grace-period shim**

The shim should ship for two releases: `v1.8.x` and `v1.9.x`, with removal in
`v2.0.0`. Renaming a documented executable is a breaking change if any user can
invoke it directly, so the strict SemVer treatment is: deprecate in a minor,
remove in the next major. One release is too short because deprecation notices
have weak real-world reach and users do not all upgrade every minor immediately;
you would turn a survivable migration into an avoidable support burden. The
maintenance cost of carrying a trivial shim for one extra minor is negligible,
while the migration benefit is high. So the right framing is not "is this
MINOR-appropriate?" but "the deprecation is minor-appropriate; the removal is
major-only."

**Q3. Option D portability**

Claude's `type -a sutra-core` check is not portable enough to base the rollout
on. It works in `zsh` and `bash`, but `dash` does not support `-a`; `fish` has
its own `type` semantics and its `command -v` equivalent searches external
commands rather than reporting alias precedence; `nushell` uses `which` and
`scope aliases`, not POSIX `type`/`command` behavior. The most portable detector
in POSIX shells is `command -v`, not `type -a` and definitely not `which -a`;
`which` is non-standard and often blind to aliases/functions, and
`$BASH_SOURCE`/`$0` inside the script cannot detect a pre-invocation alias
collision because if the alias won, your script never ran. The deeper issue is
that Option D is conceptually wrong as a runtime self-check inside the binary:
an invoked external command cannot reliably inspect the caller shell's
higher-priority alias/function table across shells. The correct implementation
is to harden every internal shell-out to use the plugin's absolute binary path,
and treat command-resolution diagnostics as a separate, shell-specific install
check rather than a mandatory runtime gate.

**Q4. Helper namespace**

Rename the helpers to `sutra-core-*`. Keeping `sutra-go`, `sutra-reset`, and
friends while renaming only the primary binary leaves you with a split namespace
that teaches the wrong mental model: users now have to remember that "the main
thing is `sutra-core`, except the related things are still `sutra-*`." That
inconsistency will age badly once the ecosystem grows beyond one dominant
plugin, because `sutra-*` reads like vendor-global namespace, not `core@sutra`
namespace. The double-breakage cost is real, but that is exactly why you should
pay it once and do the namespace cleanup coherently, with shims for the helpers
on the same deprecation schedule as the main binary. `sutra-core-*` is the
right long-term shape because it distinguishes "plugin family" from "ecosystem
brand."

**Q5. Open failure modes**

The biggest missed failure mode is false confidence from Option D itself: if
internal calls are already rewritten to absolute paths, the runtime self-check
adds no protection, but it can still produce false positives under wrappers,
symlinks, or managed installs where the resolved path is not byte-for-byte the
canonical plugin path. Second, the shim can break machine-facing flows if it
prints deprecation warnings on stdout and contaminates output consumed by slash
commands, status parsing, or update logic; every shim warning must go to stderr
and be suppressible for internal calls. Third, stale references will survive
outside the obvious binaries: completions, docs, install scripts, examples,
tests, telemetry labels, and update/uninstall code commonly keep the old
basename and silently reintroduce the bug after the rename. Fourth, removal of
the shim can interact badly with shell command hashing and cached completions,
creating confusing "works in one tab, fails in another" behavior even after a
clean upgrade. Fifth, if users have their own `sutra-core` alias or function
later, the same class of bug returns; the real fix is absolute-path invocation,
not faith that the new name will remain collision-free forever.

Summary verdict: **PARTIAL**: adopt Option A, keep shims through `v2.0.0`,
rename helpers to `sutra-core-*`, and replace Option D with absolute-path
internal invocation plus optional shell-specific diagnostics, not a mandatory
runtime self-check.

Sources: POSIX `command` spec
https://pubs.opengroup.org/onlinepubs/9799919799.2024edition/utilities/command.html ;
fish `type` https://fishshell.com/docs/4.1/cmds/type.html ;
fish `command` https://fishshell.com/docs/3.7/cmds/command.html ;
Nushell `which` https://www.nushell.sh/commands/docs/which.html ;
Nushell aliases https://www.nushell.sh/book/aliases.html
```

Live shell probes codex executed during Pass 1 (excerpt):

```
exec: /bin/zsh -lc "bash -lc 'alias sutra=echo; shopt -s expand_aliases;
     type -a sutra; printf \"---\\n\"; command -v sutra'"
  sutra is aliased to `echo'
  sutra is /Users/abhishekasawa/.claude/plugins/cache/sutra/core/1.6.1/bin/sutra
  alias sutra='echo'

exec: /bin/zsh -lc "dash -c 'command -v sh; command -v echo;
     (type sutra) 2>&1 || true'"
  /bin/sh
  echo
  sutra is /Users/abhishekasawa/.claude/plugins/cache/sutra/core/1.6.1/bin/sutra

exec: /bin/zsh -lc "zsh -lc 'alias sutra=echo; type -a sutra;
     printf \"---\\n\"; command -v sutra'"
  sutra is an alias for echo
  sutra is /Users/abhishekasawa/.claude/plugins/cache/sutra/core/1.6.1/bin/sutra
  alias sutra=echo
```

Tokens used: 67,476.

### Pass 2 — Challenge (adversarial, FATAL FLAW verdict)

Full transcript captured at `/tmp/codex-consult/pass2-output.txt` (138 lines).

```
The design is wrong because it treats a local invocation bug as a naming crisis,
then pays ecosystem-wide migration cost for a fix that does not actually close
the failure mode.

The strongest attack is this:

`!sutra <sub>` is the bug. Not `bin/sutra`.

Your slash commands are shelling out by bare name. In a shell, bare-name lookup
is explicitly user-overridable by alias/function/hash/PATH order. That is
expected behavior, not an edge case. If plugin internals need the plugin binary,
they must invoke the plugin binary by absolute path or a runtime-provided
resolved path. Full stop. Rename does not fix that design error. It just
changes which bare name is vulnerable.

That leads to the second fatal point:

Option D is mostly fake safety.

If `alias sutra=...` wins, `bin/sutra-core` never runs, so its self-check never
fires. The only time the self-check runs is when you already succeeded in
invoking `sutra-core`. And once you invoke the plugin binary directly, the
check is redundant because the caller already resolved the right binary. Worse,
if your internal calls stay as bare `sutra` during the shim window, the shim
can also be bypassed by the same alias collision. The proposal claims
defense-in-depth, but the defense is not on the path where failure happens.

Third: the migration cost is upside-down relative to the bug.

You are proposing:
1. Rename the primary executable.
2. Add a deprecation shim.
3. Add runtime warning noise.
4. Plan a v2 removal.
5. Keep helper names inconsistent.
6. Still leave the general collision class unsolved, because `sutra-core` can
   also be shadowed.

That is a lot of churn to avoid fixing one line of architecture: stop calling
plugin internals through shell name resolution. The blast radius of the
observed incident is narrow and specific: users who define a conflicting
`sutra` alias/function and then trigger slash commands that use `!sutra ...`.
That is not evidence for a binary rename program, let alone a
marketplace-blocking one. It is evidence that your internal execution contract
is wrong.

The shim also makes things worse, not better:
- It preserves the old broken entrypoint, so people keep depending on it.
- It emits stderr warnings into flows that may parse output or treat stderr
  as failure signal.
- It prolongs ambiguity about which command name is canonical.
- It creates a two-name support matrix for no real gain.

This also violates the stated governance instincts. It is complexity without
proof. You are shipping mechanism before data. You have one dogfood collision
caused by a bare-name shell-out and are responding with rename, shim,
self-check, version choreography, and naming asymmetry. That is not simplicity.
That is evasive action around the real bug.

The non-broken fix is obvious:
- Keep `bin/sutra`.
- Change every internal slash-command shell-out from `!sutra <sub>` to an
  absolute path or injected resolved executable path.
- Add a test that aliases/functions named `sutra` do not affect plugin
  internal execution.
- Optionally add diagnostics in user-facing commands, but not as the primary
  fix.

If you want to rename for branding or long-term namespace reasons, make that
a separate decision with actual collision data. Do not pretend it is the fix
for this incident. It is not.

FATAL FLAW (the design cannot proceed)
```

Tokens used: 28,828.

---

## Appendix — Convergence math

| Dimension | Pass 1 verdict | Pass 2 verdict | Final |
|---|---|---|---|
| Name choice (`sutra-core`) | Endorse, 0.87 confidence | Challenge — "rename does not fix the bug" | **Rename unnecessary if Option E is adopted.** |
| Shim duration | 2 releases (v1.8.x + v1.9.x) | Shim makes things worse | **No shim needed under Option E.** |
| Option D portability | `type -a` inadequate; use `command -v` | Option D is fake safety regardless of detector | **Option D dropped.** |
| Helper namespace | Rename to `sutra-core-*` | Helpers are irrelevant if no rename | **No change under Option E.** |
| Missed failure modes | 5 enumerated | 3 attack vectors synthesized | **Fix is architecturally smaller, bug class actually closed.** |
| **Overall** | **PARTIAL** (4 revisions) | **FATAL FLAW** (counter-proposal Option E) | **DISAGREE → surface to founder** |

---

## Appendix — Telemetry + audit

- Codex session IDs: Pass 1 = `019db47c-8528-7692-a84d-0bec9ae4acf9`; Pass 2 = `019db48c-ce10-7803-a3cd-782c9aaba20c`.
- Codex CLI version: `0.118.0`; model: `gpt-5.4`.
- Token spend: Pass 1 = 67,476; Pass 2 = 28,828; **total ~ 96,300 codex tokens** (separate budget from Claude's).
- Raw transcripts preserved at `/tmp/codex-consult/pass1-output.txt` and `/tmp/codex-consult/pass2-output.txt` for the session — recommend archiving to `sutra/feedback/` if the counter-proposal is accepted.
- This report is the sole artifact of the consult. Design doc `2026-04-22-sutra-cli-collision.md` is unchanged per dispatch constraint.
