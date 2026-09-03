# Game plan — Agents: the SEO Writer inside Sutra

Status: executing · 2026-09-03 · Depth 5
Repo: `sankalpasawa/sutra`, `marketplace/plugin/sutra-ui`
Reference surfaces: Unify GTM (the run log, the checkpoint cards, the review panel),
Dust (the agent list), Sutra's own chat surface (bubbles, tool rows, composer).

---

## What ships

A new rail destination, **Agents**, between Chats and Routines. It opens the first
agent, **SEO Writer**: you name a topic or ask for ideas, it studies the site, researches
the keyword, builds a structure, writes the draft, and stops at four checkpoints for
you to look, edit, or redirect. Anything that costs credits asks first, with the number.

The agent runs on the `claude` CLI the panel already drives, so it bills the same
subscription the chat does. No API key. DataForSEO credentials are the only setup.

## Where it lives

| Layer | Path | Notes |
|---|---|---|
| Agent engine | `seo_agent/` (package) | loop, store, registry, tools, checks, editing, prompts, llm. Standalone; no import of anything in sutra-ui. |
| Server routes | `agents_api.py` → `/api/agents/seo/*` | thin: read a file or kick the loop. Mounted from `app.py`. |
| Screen | `static/js/17-agents.js` + `static/agents.css` | `SCREENS.agents` + `TITLES.agents`; self-mounts into the shell it returns. |
| Data | `~/.sutra-ui/agents/seo/` | chats, runs, artifacts, knowledge, memory, library, connections. Never inside the bundle: the .app is read-only once signed. |

## The shell contract (how the screen coexists with `render()`)

`render()` rewrites `#panes` wholesale and `#scBody` whenever the screen's HTML string
changes. So `SCREENS.agents` returns a **constant** shell:

```html
<div class="ag" id="agRoot" data-ag-shell></div>
```

A `MutationObserver` on `#panes` notices the empty shell and calls `agMount()`, which
draws from `S.ag` (all state lives there, never in the DOM). A repaint from an
unrelated websocket frame therefore costs one remount, and nothing is lost: the
transcript scroll offset and the composer draft are in `S.ag`.

While the screen is showing, the pane gets `.agwide` (padding 0, three columns).
Removed when another screen opens.

## The layout

```
┌ Agents ──────────────────────────────────────────────────────────────────────┐
│ ┌ agent column 232px ┐ ┌ conversation (flex) ─────────┐ ┌ review panel 0/44% ┐│
│ │ ● SEO Writer        │ │ stage bar  Topic › Research › │ │ Topic ideas   ×    ││
│ │   ready · 3 credits │ │            Blueprint › Draft  │ │ ─────────────────  ││
│ │                     │ │                               │ │ six cards, pick 1  ││
│ │ [+ New chat]        │ │  you: "Write about X"         │ │                    ││
│ │ RECENT              │ │                               │ │                    ││
│ │  · Exec ed for CHROs│ │  Worked for 2m 14s · 6 steps  │ │                    ││
│ │  · Onboarding guide │ │  ✓ Reading the website        │ │                    ││
│ │                     │ │    "Found 212 pages…"         │ │                    ││
│ │                     │ │    · 212 pages catalogued     │ │                    ││
│ │                     │ │  ✓ Learning how you write     │ │                    ││
│ │ ─────────────────── │ │  ◐ Studying a competitor      │ │                    ││
│ │ Knowledge           │ │                               │ │                    ││
│ │ Memory       3      │ │  [question card / approval]   │ │                    ││
│ │ Library      2      │ │  [artifact card → panel]      │ │ Approve & continue ││
│ │ Tools               │ │                               │ │ Ask for changes    ││
│ │ Connections  !      │ │ ⋯  ┌ Ask or answer… ┐  ↑      │ │                    ││
│ └─────────────────────┘ └───────────────────────────────┘ └────────────────────┘│
```

The agent column is Sutra's `.nav` vocabulary (rows, counts, warn badge). The
conversation is Sutra's `.turn .u` bubble, its `.pc` composer and `.send` button, and
its `.trow` idiom for sub-steps. The review panel opens only when the agent has
something to show, and closes with the checkpoint.

## The run log (from Unify, in Sutra's tokens)

One assistant block per run. It opens with a strip: while live, the Sutra `runstrip.live`
sweep and "Working · 1m 12s"; when done, "Worked for 2m 14s · 6 steps" with a
Collapse/Expand toggle. Below, a hairline on the left and one entry per step:

| Entry | Glyph | Title | Body | Sub-rows |
|---|---|---|---|---|
| step_started/finished | ✓ / spinner / ✕ | the human label (`Reading the website`) | the model's sentence before it acted | substeps as `.trow` rows with duration |
| note (log_step) | · | the sentence itself | — | — |
| waiting: question | ? | `Asked you a question` | the question | option chips, chosen one highlighted after |
| waiting: approval | ₡ | `Asked before spending` | "8 credits · about 12 minutes" | Go ahead / Not now, then the decision |
| waiting: artifact | ▣ | `Showed you the research brief` | the prompt | a card that reopens the panel |
| message | — | the model's prose, rendered markdown | | |
| step_failed | ✕ | label | reason, and "trying another way" when recovering | detail fold |
| memory_saved | ★ | `Saved a standing rule` | the rule | |

No invented numbers: no percentage, no ETA. Durations come from `ms` on the event.

## The four checkpoints (the review panel)

| View | What it shows | Footer |
|---|---|---|
| `topic_list` | six topic cards: title, angle, why it fits, competitor it beats, a radio | **Use this topic** (needs a pick) · Ask for different ideas |
| `research_brief` | primary keyword with volume + difficulty, PAA questions, top pages, the gap | **Approve & continue** · Ask for changes |
| `blueprint` | sections with covers/words/links, reorder with ↑↓, per-section rewrite instruction | **Approve & continue** · Ask for changes |
| `article` | rendered draft; each block has an Edit affordance → instruction → diff + checks | **Save to Library** · Ask for changes · Download .md |

"Ask for changes" focuses the composer with a prefilled prompt; the message becomes
the tool result of `show_artifact`, so the model reads the request in place. An edit
goes through `/edit`: one block rewritten, byte-identity of the rest asserted, checks
run, diff shown.

## Settings views (the agent column's lower rows)

| Row | Shows | Actions |
|---|---|---|
| Knowledge | site index summary, voice profile, competitors | re-index, edit competitors |
| Memory | standing rules, on/off | add, toggle |
| Library | saved articles with status | open, mark ready, delete |
| Tools | the six tools with cost and gate | read-only |
| Connections | DataForSEO login + password (set/unset only, never echoed), model provider status | save, clear |

## Binding constraints (inherited from the shell)

1. **Every string through `esc()`**, attributes through `escAttr()`.
2. `09-tail.js` stays last; `17-agents.js` loads before it.
3. `test_nav.js` pins the destination list: it moves from seven to eight, and the
   change is documented in the test.
4. No new backend dependency beyond `httpx` for DataForSEO, pinned in
   `requirements.txt` so the DMG bundle carries it.
5. The panel token header travels on every request (`apiGet`/`apiPost`).
6. Polling, not a socket: 1 s while a run is live, 4 s idle, paused when the
   screen is hidden or the window is not visible.

## Verification lanes

| Lane | Command | Asserts |
|---|---|---|
| L1 projection | `node test_agents.js` | `agStepsFromEvents()`, `agStageOf()`, `agRunStrip()` on a captured events fixture |
| L2 DOM | `node test_agents.js` | rendered HTML of the run log, a question card, the topic list, escaping |
| backend | `.venv/bin/python -m pytest test_agents_api.py` | routes, panel-token guard, secrets never echoed, data dir under home |
| engine | `python -m pytest seo_agent/tests` | the 99 + CLI-provider checks |
| L3/L4 | Playwright against the repo backend | screenshots of each checkpoint, light and dark |
