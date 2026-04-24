# Upstream Feature Request — Plain-English Summary in Bash Permission Dialogs

**Proposal for Anthropic / Claude Code team.**
**Date drafted:** 2026-04-24
**Status:** Draft — local doc, not yet filed with Anthropic. Filing path (GitHub issue / email / forum) is a separate conscious step.
**Context:** Sutra plugin v1.14.0 shipped a PreToolUse hook that prepends a plain-English summary to Bash permission dialogs. This doc proposes making that behavior **native** to Claude Code so every user (not just Sutra users) benefits and the hook can retire.

---

## Problem

When Claude Code requests approval for a Bash command, the dialog shows the raw shell string and nothing else. Examples seen by real non-technical users:

```
Allow Bash command?
  curl -sSL https://example.com/install.sh | sh

[Approve]  [Deny]
```

```
Allow Bash command?
  rm -rf ./build

[Approve]  [Deny]
```

```
Allow Bash command?
  python3 -c "import os; [os.unlink(f) for f in os.listdir('.') if f.endswith('.tmp')]"

[Approve]  [Deny]
```

Non-technical users (designers, product managers, analysts, founders using Claude for their own work) cannot parse these. Three observed outcomes:

1. **Blind approval** — the worst case. Users who don't understand a command default to "probably fine" and approve. This converts the permission system from a safety layer into a ritual.
2. **Get stuck** — user doesn't approve, doesn't know what to ask, session stalls.
3. **Friction loop** — user approves, something unexpected happens, trust drops.

All three fail the population Claude Code is increasingly serving — non-developers who use Claude to do technical things without being technical themselves.

## Evidence

- One external user flagged this directly on 2026-04-24 (logged at `sutra/marketplace/FEEDBACK-LOG.md`): *"permission prompts extremely difficult to understand… raw bash scripts — curl, python3, rm -f, multi-line heredocs — unreadable without a programming background."*
- Our fleet is 14+ installs of a governance plugin built on Claude Code; the non-technical share is growing.
- The plugin's own permission friction has been a top-three adoption blocker (FEEDBACK-LOG 2026-04-21). Two mitigations already shipped: script consolidation via `bin/` (v1.3.0) cut prompt count ~95%; meta-permission auto-approve (v1.13.0) cut it further. The remaining prompts are the most important — they're the ones not safe to auto-approve. Those are the ones users can't read.

## Proposed solution

**Claude Code renders a one-sentence plain-English summary inside the permission dialog, above the raw command.**

```
Allow Bash command?

  📖 This downloads a script from 'example.com' and runs it immediately
     as shell. Anything in the script will execute on your machine.

  curl -sSL https://example.com/install.sh | sh

  [Approve]  [Deny]
```

Danger-tag for destructive patterns:

```
Allow Bash command?

  🚨 DESTRUCTIVE — will delete './build' and everything inside it. This
     cannot be undone.

  rm -rf ./build

  [Approve]  [Deny]
```

The raw command remains visible for technical users. The summary is informational only — it does not change the allow/deny decision or bypass any existing permission logic.

## Implementation options

| Option | Approach | Cost | Accuracy | Latency |
|---|---|---|---|---|
| **A. Rules-based** | Pattern-match ~30-40 common verbs (rm, curl, git, dd, chmod, pip, npm…). Covers ~80% of what users see. | Zero LLM cost. | ~90% on covered verbs; generic message on unknowns. | <10ms (string parsing). |
| **B. LLM-based** | Small model (Haiku-class) called per Bash tool call with a tight prompt. Cache by command hash. | Per-call cost; budget-tunable. | ~98% across almost all commands. | 500ms-2s depending on cache hit. |
| **C. Hybrid (recommended)** | A for fast path, B fallback only on composed commands (pipes, heredocs, subshells) or unknown verbs. | Minimal LLM cost (fallback is rare). | ~97%. | <10ms for 80%, 500-2s for 20%. |

Sutra's v1.14.0 hook implements option C as a proof-of-concept. The rules matcher covers the verbs below; LLM fallback kicks in for composed commands. 38 golden-case tests pass. See `sutra/marketplace/plugin/hooks/bash-summary-pretool.sh`.

### Reference rules coverage (from our implementation)

`rm`, `rm -rf`, `sudo rm -rf /` (catastrophic), `curl`, `wget`, `curl | sh`, `git` (reset --hard, clean -fdx, push --force, push, clone, commit, pull, checkout, restore, add, read-only subcommands), `dd`, `> /dev/*`, `sudo <anything>`, `ssh`, `scp`, `rsync`, `mkdir`, `cp`, `mv`, `chmod`, `chown`, `touch`, `ln`, `tar`/`zip`/`unzip`, `cat`, `head`, `tail`, `ls`, `pwd`, `whoami`, `date`, `find`, `grep`/`rg`, `>` (overwrite) vs `>>` (append), `python`/`python3`, `python -c`, `pip install`/`uninstall`, `npm install`, `npm run`, `node`, `brew install`/`uninstall`, `apt`/`yum`/`dnf`/`pacman`, `kill`, `kill -9`, `pkill`/`killall`, `open`, `code`, `echo`, `printf`.

## Integration with existing Claude Code permission flow

- **No change to allow/deny semantics.** Summary is displayed; user still approves/denies through existing UI.
- **No change to existing hooks.** If a PreToolUse hook already sets `permissionDecisionReason` via the existing JSON output contract, keep that behavior; the native summary appears in addition (or, if the hook returns one, the native summary is suppressed — design choice).
- **Allow-listed commands skip the summary entirely** — they don't show a dialog, so there's nothing to summarize. Zero cost on the common path.
- **Available to all users by default.** Non-technical users benefit without any opt-in. Technical users see it too (costs them nothing; often useful for long commands).

## Why this belongs upstream (and not in every plugin)

1. **Uniform safety floor for all Claude Code users.** Plugins reach a fraction; the dialog reaches 100%. The population that needs this most is the one not using plugins yet.
2. **No fork of the approval UI.** Plugins can only prepend to the dialog via `permissionDecisionReason`; they cannot restructure the layout. Native support can render the summary distinctly from the command with proper typography and danger-highlighting.
3. **Single source of rules / prompt.** One well-tuned rules table / LLM prompt beats N plugin authors each writing their own and drifting.
4. **Zero maintenance burden on plugin ecosystem.** Every plugin currently shipping a summarizer hook (ours, likely others) retires cleanly.

## Open questions for the Anthropic team

1. Rules-based, LLM-based, or hybrid? (Happy to share our telemetry on verb distribution.)
2. Opt-in, opt-out, or always-on? (We default to always-on; our users don't know to opt in.)
3. Does the summary live in `permissionDecisionReason` (same existing channel plugins use) with a native-vs-plugin precedence rule, or does it get a separate field like `nativeSummary`?
4. Localization — our v0 is English only. Claude Code's existing locale handling would apply.

## Reference material

- **Our v0 hook implementation (MIT):** `sutra/marketplace/plugin/hooks/bash-summary-pretool.sh`
- **Our golden-case test suite:** `sutra/marketplace/plugin/tests/bash-summary-cases.sh` (38 cases, all passing)
- **Design doc:** `holding/research/2026-04-24-permission-summary-plan.md`
- **User feedback that triggered the work:** `sutra/marketplace/FEEDBACK-LOG.md` (2026-04-24 entry)
- **Integration with our human-agent principles:** `sutra/layer2-operating-system/c-human-agent-interface/HUMAN-AGENT-INTERFACE.md` § Part 4 (registry); `holding/HUMAN-AI-INTERACTION.md` (P7 "Human Is the Final Authority", P11 "Human Confidence Through Clarity")

## Filing path (when you decide to send this)

This doc is ready to ship to Anthropic via any of:

| Channel | Shape | Best for |
|---|---|---|
| **GitHub issue** on `anthropics/claude-code` | Issue title + paste body + link to repo files | Public visibility, maintainer routing, version-tracking |
| **Email** to Claude Code devrel / product team | Doc attached or inlined | Higher-touch, private, executive relationship |
| **Forum / Discord post** | Linked + summarized | Community awareness, getting signal on demand |
| **Direct Slack/DM** | Linked + short pitch | Fastest if you have a relationship |

The doc itself is agnostic to channel. Sending is a separate conscious step — not done by this build cycle.

## Contact

- Maintainer: Sutra (https://sutra.os)
- Repo: https://github.com/sankalpasawa/sutra
- Author: asawa@nurix.ai
- We are happy to contribute the rules table, LLM prompt, and test suite under MIT for native adoption — or refactor into whatever shape the Claude Code team prefers.
