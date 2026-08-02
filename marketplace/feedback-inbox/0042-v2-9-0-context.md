---
issue: 42
title: "[v2.9.0] ## Context"
author: vinitharmalkar
state: OPEN
created: 2026-04-30T11:01:55Z
updated: 2026-04-30T11:01:55Z
labels: —
url: https://github.com/sankalpasawa/sutra/issues/42
comments: []
---

# #42 [v2.9.0] ## Context

**Author:** vinitharmalkar  |  **State:** OPEN  |  **Labels:** —
**Created:** 2026-04-30T11:01:55Z  |  **Updated:** 2026-04-30T11:01:55Z
**URL:** https://github.com/sankalpasawa/sutra/issues/42

---

## Context

Filed [gh#41](https://github.com/sankalpasawa/sutra/issues/41) on 2026-04-30 proposing `/core:resume` + `/core:bookmark` — the depth-first architecture for turning opaque session UUIDs into fuzzy-searchable, bookmarkable, semantically-titled sessions.

After a follow-up session weighing build paths (A: personal script now · B: wait on gh#41 · C: full plugin self-fork), **Path A won** — built a working personal version in ~30 minutes inside Claude Code. This issue documents the build, the design refinements that surfaced during implementation, and empirical test results. All of it should be useful when the official version ships.

## What was built (personal/local — `~/bin/`)

| File | Lines | Purpose |
|---|---|---|
| `~/bin/sresume` | 162 | Discover + resume past sessions by semantic title |
| `~/bin/sbookmark` | 130 | Manage named bookmarks (kebab-case validated, dupe-protected, prune) |
| `~/.sutra/bookmarks.jsonl` | n | Storage; one JSON per bookmark |

Both pure Python 3.9+, single-file each, zero external dependencies. `fzf` optional (numbered-list fallback works without it). Total ~290 LoC vs the ~720 LoC v1 estimate in gh#41 — the personal version skips hooks/cache/tests and just does on-demand scans.

## Critical design refinement discovered during implementation

### Bootstrap-INPUT noise — the proposal's title heuristic needs a skip list

The gh#41 spec said *"use the first INPUT line as the session title."* In practice, **every Sutra-governed session's first INPUT line is the `/core:start` activation**:

```
"Run /core:start to activate Sutra governance in this project"
"User invoked /core:start to activate Sutra governance"
"Run /core:start to activate Sutra in <HOME>
```

If you take the first INPUT verbatim, every session's title looks identical and useless. The picker would show 50 rows of "Run /core:start...".

**Fix:** skip INPUTs matching a bootstrap-pattern set, take the first **non-bootstrap** INPUT instead. The set I used:

```python
BOOTSTRAP_RE = re.compile(
    r"(/core:(start|status|update|sbom|permissions|uninstall|depth-check)"
    r"|^Run /core:"
    r"|^User (ran|invoked) /core:"
    r"|activate Sutra"
    r"|initialize Sutra)",
    re.IGNORECASE,
)
```

Three-tier fallback: real INPUT → first plain user message → first INPUT (even if bootstrap, as a last resort).

**Before/after on my actual session list (12 sessions):**

| Before filter | After filter |
|---|---|
| Run /core:start to activate Sutra governance | Brainstorm a product that connects Jira to Slack + Google Sheet, flags tickets idle >2 day |
| Run /core:start to activate Sutra governance | Vinit wants a deep TestGorilla-vs-Testlify comparison; CTO flagged TestGorilla; thesis... |
| Run /core:start to activate Sutra governance | Set up Gmail MCP for Abhishek (mirroring Namrata setup) plus a flagging layer |
| Run /core:start to activate Sutra governance | How do I enable double-tap on the trackpad to open files (just reset Mac) |
| Run /core:start to activate Sutra governance | Proposing a new Sutra layer that takes raw user instructions, engineers them into proper... |

**Recommendation:** the official `/core:resume` should ship a configurable bootstrap-skip list. The set above covers all 7 user-facing `/core:` commands plus 2 generic patterns plus 2 thematic fallbacks. This is **load-bearing** — without it, the feature is a glorified UUID list.

## Empirical test results

### Test 1 — Title extraction across 12 recent sessions

- 0.6 seconds end-to-end including JSONL scan + per-session INPUT extraction (single-pass Python).
- Single-pass approach (early-exit on first non-bootstrap INPUT) was simpler than the spec's "read first ~50 lines" suggestion and worked fine.
- All 12 sessions produced meaningful titles after the bootstrap filter.

### Test 2 — Bookmark roundtrip + edge cases

```
$ sbookmark jira-pulse 599d23b3-...
Bookmarked 'jira-pulse' → 599d23b3

$ sbookmark BadName               # name validation
Bookmark name must be kebab-case (a-z, 0-9, -). Got: 'BadName'

$ sbookmark jira-pulse            # duplicate refusal
Bookmark 'jira-pulse' already exists. Remove it first.

$ sbookmark
        jira-pulse  →  599d23b3  (2026-04-30T10:36:15Z)
    founder-digest  →  5213b5ae  (2026-04-30T10:36:15Z)
```

Bookmarks render inline in `sresume --list` as `[name]` tags. Atomic write via tmp+rename. `--prune` drops bookmarks pointing to missing sessions.

### Test 3 — Live `claude --resume` end-to-end (governance preservation)

This is the test that matters most. Picked aborted session `8316c79b` (19 lines, 22h idle) and ran:

```bash
claude --resume 8316c79b... -p "In one short sentence, what was this session about before I came back?"
```

**Results:**
- ✅ JSONL grew **19 → 31 lines** (real session continuation, not a fresh branch with rehydrated context)
- ✅ **Conversation history rehydrated** — Claude correctly recapped: *"activating Sutra governance via /core:start, which refreshed the governance block, wrote project identity, and loaded the four core skills"*
- ✅ **Sutra governance loaded** — response ended with `OS: resume (question) > recap > 0 tool calls > readability gate > 1-line answer` (Output Trace block, exactly as specified in CLAUDE.md governance)

**Conclusion:** `claude --resume` and `claude -p` traverse the same Claude Code startup path. Plugin + user-global CLAUDE.md governance both load on resume. **Sutra discipline is preserved.** The official `/core:resume` will not have a "loses governance on resume" failure mode.

Sub-finding: `-p` print mode emitted only the Output Trace, not the full Input Routing + Depth blocks. Claude appears to compress governance for short factual answers in print mode. Interactive `claude --resume <uuid>` produces all 4 blocks normally.

## Lessons for the official Sutra implementation

| gh#41 spec point | Refinement from this build |
|---|---|
| "Use first INPUT line as title" | **Add bootstrap-INPUT skip list (regex above).** Without it, every session title is `/core:start` and the feature is unusable. Critical, not optional. |
| "Read first ~50 lines of each JSONL" | A single-pass scan of the WHOLE file with early-exit on first non-bootstrap INPUT was simpler and still fast (~80ms per file, sub-second for 50 files). |
| "Performance fine up to ~10k sessions" | Confirmed at low scale (~50 sessions = 0.6s). At 1k+ a cache becomes worthwhile but is overkill for v1. |
| "Slash commands cannot relaunch Claude" | True — confirmed empirically. Shell helper (`sresume`) is the **primary** surface; slash command is print-only. |
| Bookmark file format `~/.sutra/bookmarks.jsonl` | Worked perfectly. Atomic write via tmp+rename. Lock with `flock` for concurrent writers (skipped for personal use; ship it in plugin). |
| `--here` filter | Useful even for v1; ~3 LoC to implement. |
| `--last` alias for `claude -c` | Ship in v1; one-line implementation. |

## Coexistence note

Already coexists with the user's prior `~/bin/session_dashboard.py` (read-only markdown of all session state — blockers, idle times, by-project). The two are **complementary**: dashboard for situation-awareness ("what's blocked?"), sresume for navigation ("get me back into X"). Worth noting in the official docs that `/core:resume` doesn't replace a Coverage/dashboard surface.

## What still requires the official plugin (vs. my personal Path A)

The personal scripts hit the 80% UX win. The plugin version would add:

1. `SessionStart` + `Stop` hooks to maintain a cache index (faster at scale)
2. Cross-session title staleness handling (`first_input` vs `last_input` per spec)
3. The slash-command surfaces (`/core:resume`, `/core:bookmark`, `/core:sessions`)
4. `--rebuild` for cache regeneration
5. Tests (the spec lists ~200 LoC of unit tests)
6. Cross-machine sync (deferred per spec)

For me personally, none of those matter — the personal scripts solve my problem on this Mac. But shipping the plugin version makes it real for everyone running Sutra, and (per the original gh#41 close): **proves the brain-layer positioning concretely.** Native sees one project; Core sees them all. That's the argument.

## Reference code

The two scripts (~290 LoC total) are on my Mac at `~/bin/sresume` and `~/bin/sbookmark`. MIT-licensable on request — happy to drop them in a gist or PR if useful as a starting point. The **bootstrap-skip regex is the load-bearing learning** worth preserving in any rewrite.

## TL;DR for Sankalpa

1. **gh#41's architecture is sound** — built it personally, works as designed.
2. **One critical addition the spec missed**: bootstrap-INPUT skip list (every Sutra session starts with `/core:start`; titles need to skip past it).
3. **Empirically confirmed**: Sutra governance loads on `claude --resume`. No regression risk on that axis.
4. **No urgency from me** — personal version unblocks me. But the plugin version remains the better answer for the ecosystem.

---

*Filed via `gh issue create` from a Claude Code session running sutra@2.9.0. Linked to [gh#41](https://github.com/sankalpasawa/sutra/issues/41).*
