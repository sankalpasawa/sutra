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
- **Status:** open
- **Founder re-escalated 2026-04-21** — "A lot of permissions" — friend has installed, friction is real. Priority bumped to P0 for v1.3.0. Recommended approach: **bin/** pattern per Claude Code plugin docs — plugin executables in `bin/` are auto-added to PATH and treated as bare commands (no Bash permission prompt). Single `sutra` executable with subcommands replaces 6 scripts.

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
