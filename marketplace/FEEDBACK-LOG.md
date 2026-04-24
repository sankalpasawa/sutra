# Sutra Plugin — Feedback Log

*Append-only record of every feedback item from users (founder or external). Each entry gets a timestamp + status. Close by adding `Resolution:` + `Closed-in:` fields when fixed.*

*Location intent: `sutra/marketplace/FEEDBACK-LOG.md` — lives with the marketplace dept so plugin work has direct line-of-sight. Referenced by OKRs KR 4.1.*

*Capture format* — minimal so logging stays 30-second work:

```
## YYYY-MM-DD — [open | fixing | closed] short title
Reporter: [founder | external-user | @handle]
Context: [where encountered — session flow, command run, step]
Description: [what was observed / what was wrong]
Impact: [who this hurts, how often]
Proposed fix: [optional — if there's an obvious one]
Resolution: [fill when closed]
Closed-in: [version / commit sha]
```

---

## 2026-04-21 — [open] Too many permission prompts during plugin use

- **Reporter:** Founder (CEO of Asawa, in-session)
- **Context:** Using Sutra plugin v1.2.1 in a Claude Code session after install
- **Description:** Plugin triggers many permission prompts from Claude Code. Observed categories include:
  - File/folder access requests
  - Photos / system folder access
  - Multiple distinct Bash permission prompts for different scripts
  - (Founder indicated "etc" — more categories possible; need full audit)
- **Impact:** Breaks first-run UX. New users face a wall of approval dialogs before Sutra does anything. Directly undermines the "60-second onboarding" promise on the website.
- **Root-cause hypotheses** (from on-disk audit 2026-04-21):
  1. `commands/*.md` each run `!bash ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.sh` — each distinct path = separate Bash permission scope
  2. Scripts internally run `git clone`, `git push`, `mkdir`, `curl`, etc. — each sub-command can prompt separately
  3. `install-shell-helpers.sh` appends to `~/.zshrc` or `~/.bashrc` — file-write permission outside project dir
  4. `push.sh` reaches `~/.sutra/sutra-data-cache/` — home-dir write + network
  5. Plugin hooks fire on every Edit/Write/Stop — in theory plugin hooks are trusted, but some surfaces may still prompt
- **Proposed fixes (options):**
  - **A.** Consolidate scripts into one `sutra-runner.sh` with subcommand arg → one allow = all commands pass
  - **B.** Ship recommended `.claude/settings.json` snippet in README so users paste once
  - **C.** Move logic from `commands/*` into `hooks/*` where possible (plugin hooks bypass prompts)
  - **D.** Use `userConfig` for opt-in of heavy features (push, shell-helpers) so defaults are minimal
  - **E.** Explicit list in README of what the plugin will ask for and why
- **Next action:** founder decision on A-E before fix ships
- **Status:** **closed**
- **Founder re-escalated 2026-04-21** — "A lot of permissions" — friend has installed, friction is real. Priority bumped to P0 for v1.3.0. Recommended approach: **bin/** pattern per Claude Code plugin docs — plugin executables in `bin/` are auto-added to PATH and treated as bare commands (no Bash permission prompt). Single `sutra` executable with subcommands replaces 6 scripts.
- **Resolution (2026-04-21):** Shipped `bin/sutra` unified dispatcher in **plugin v1.3.0** — single executable routes `onboard | go | status | push | install-shell-helpers | leak-audit`. All 5 command files updated from `!bash ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.sh` to `!sutra <sub>`. Plus breaking rename: `/sutra:sutra-onboard` → `/sutra:onboard` (and peers) to drop redundant prefix inside the `sutra:` namespace. Friend's Claude Code will auto-pull v1.3.0 on next session start.
- **Closed-in:** v1.3.0 (commit `a93f19d`)

---

## 2026-04-21 — [closed-immediately] "I thought we had already worked on tracking"

- **Reporter:** Founder
- **Context:** After friend started using plugin, founder asked about tracking
- **Description:** Tracking infra IS built — just wasn't surfaced. As of 2026-04-21 19:38 local:
  - `sankalpasawa/sutra-data`: **10 distinct install_id** dirs (vs. 9 yesterday — +1 today, could be friend)
  - GitHub `sankalpasawa/sutra` clone traffic 14-day window: **283 clones, 62 UNIQUE cloners** (concentrated on 2026-04-20)
  - Analytics collector: 90 metrics collected + published to ANALYTICS-PULSE.md this session
  - Launchd cadences LIVE: `os.sutra.analytics-collect` (3h), `com.asawa.observability` (3h), `com.asawa.observability-daily`
- **Impact:** None — this was a surfacing problem, not a build problem. Founder now has signal.
- **Resolution:** Ran `bash holding/departments/analytics/collect.sh` + `publish.sh` to refresh pulse. Cadence already active via launchd.
- **Follow-up (open):** Surface install count + unique cloners prominently in Daily Pulse so founder sees it on every session start without asking.
- **Status:** closed (core) / open (pulse-integration follow-up)

---

## 2026-04-21 — [answered] "Is there auto-update?"

- **Reporter:** Founder (after friend began using plugin)
- **Context:** Worried friend is stuck on v1.2.0 with brand leaks / missing walkthrough
- **Answer:** **YES — plugin auto-updates.**
  - Anthropic docs: "Background auto-updates run at startup" for public marketplaces like ours (no token needed)
  - Claude Code checks `sankalpasawa/sutra` marketplace on session start → pulls latest → applies to plugin cache
  - Friend's next Claude Code session will pull v1.2.1 automatically
  - Manual force-update (in case friend wants it now): `claude plugin marketplace update sutra && claude plugin update sutra@sutra`
- **What auto-update does NOT do yet:**
  - No in-session banner telling user "you've been updated to v1.2.1"
  - No changelog surfacing at update time
  - No rollback UX if v1.2.1 breaks something
- **Status:** core behavior = answered / UX polish = open (v1.3.x)

---

<!-- APPEND NEW ENTRIES BELOW THIS LINE — use the capture format above -->

## 2026-04-24 — [closed] Permission prompts unreadable to non-technical users

- **Reporter:** external-user (routed via founder, in-session 2026-04-24)
- **Context:** Using Claude Code (with Sutra plugin). When Claude requests tool approval, the dialog displays raw shell: `curl`, `python3`, `rm -f`, multi-line heredocs. User is non-technical, cannot parse what the command actually does.
- **Description:** The permission dialog shows the raw command string and nothing else. A non-developer has two bad options: blindly approve commands they don't understand, or get stuck. There is no plain-English description of the action, its blast radius, or its reversibility.
- **Impact:**
  - **Accessibility** — hard-blocks non-developer adopters. Breaks the "60s onboarding" promise for non-technical segments of the fleet.
  - **Safety hole** — blind approval is worse than refusal. Users click through destructive commands because they don't know what `rm -f` means. "I don't understand but it's probably fine" is the default failure mode.
  - **Doctrine violation** — Founding Doctrine Principle 0 (Customer Focus First): "If the customer needs explanation to understand, fix it." This is exactly that case.
- **Reporter's proposed fix:** Before any permission dialog, prepend a 1-2 sentence plain-English summary of what the command does. Example: *"This will delete 3 files from your Downloads folder and update a spreadsheet to show which tenders are still open."* Raw command remains visible below for technical users.
- **Relation to prior feedback:** Distinct from the 2026-04-21 entry ("too many permission prompts" — closed in v1.3.0 via `bin/sutra` consolidation). That one reduced **count**; this one improves **readability** of the prompts that remain. They compound — ship both, don't substitute.
- **Fit analysis:**
  - **Home:** `sutra/marketplace/plugin/hooks/` — a PreToolUse hook on Bash that prints a summary line before the dialog appears.
  - **Build-layer:** L0 (fleet — every non-technical user benefits).
  - **Technical constraint:** the hook cannot modify the Claude Code dialog UI itself (Anthropic-owned). Hook emits summary text into the conversation stream; user reads it, then approves via the native dialog. Must verify Claude Code does not buffer hook stdout below the dialog — if it does, this approach fails and we pitch upstream instead.
- **Implementation options:**
  - **v0 — Rule-based summarizer (1-2 days).** Pattern-match common verbs: `rm`, `curl`, `git <sub>`, `mkdir`, `cp`, `mv`, `chmod`, `python3 -c`, heredocs. Emit `"This will delete N files in <dir>"`, `"This downloads a file from <host>"`, etc. ~80% coverage of what users actually see. Zero LLM cost, zero added latency.
  - **v1 — LLM summarizer (2-3 days).** Haiku call per Bash tool with a tight prompt and aggressive caching. Higher accuracy on long/composed commands, but adds $/latency per prompt across the fleet. Requires budget decision.
  - **v2 — Upstream pitch to Anthropic.** Best long-term home — the summary belongs inside the dialog, not in hook stdout. Write it up as a Claude Code feature request referencing this feedback. Does not block v0/v1.
- **Open questions (for founder):**
  1. Ship v0 now, or wait for v1 (LLM) to avoid rewriting?
  2. Summary on **all** Bash calls, or only risky verbs (rm / curl / chmod / write-to-home / network)?
  3. Upstream pitch before or after shipping v0? (If Anthropic builds it natively, we retire the hook.)
- **Status:** closed.
- **Resolution (2026-04-24):** Shipped Option D (big bang) in plugin **v1.14.0** — v0 rules-based summarizer + v1 LLM fallback + upstream pitch doc to Anthropic.
  - Hook: `sutra/marketplace/plugin/hooks/bash-summary-pretool.sh` (~400 lines; rules for ~30 verbs + Haiku fallback for composed commands; always exits 0; three kill-switches).
  - Registered in `sutra/marketplace/plugin/hooks/hooks.json` under `PreToolUse[Bash]`, ordered after `rtk-auto-rewrite` + `codex-directive-gate` so blocked commands never pay summarization cost.
  - Tests: `sutra/marketplace/plugin/tests/bash-summary-cases.sh` — 38 golden cases, all passing.
  - Plan: `holding/research/2026-04-24-permission-summary-plan.md`.
  - Upstream pitch: `sutra/marketplace/UPSTREAM-PITCH-permission-summary.md` — local doc ready for founder to file with Anthropic (channel TBD).
  - H-Agent Interface registry: entry added in `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` § Part 4; backlinks in `holding/HUMAN-AI-INTERACTION.md` under P7 + P11.
  - Live smoke test: `rm -rf /tmp/foo` → 🚨 DESTRUCTIVE summary; `ls -la` → 📖 read-only summary; `SUTRA_BASH_SUMMARY=0` → silent (kill-switch works).
- **Closed-in:** plugin v1.14.0 (commit SHA recorded on commit approval).
