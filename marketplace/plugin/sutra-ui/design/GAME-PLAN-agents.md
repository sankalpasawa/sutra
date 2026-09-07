# Game plan — Agents: the SEO Writer inside Sutra

Status: executing · 2026-09-03 · Depth 5
Repo: `sankalpasawa/sutra`, `marketplace/plugin/sutra-ui`
Reference surfaces: Unify GTM (the run log, the checkpoint cards, the review panel),
Dust (the agent list), Sutra's own chat surface (bubbles, tool rows, composer).

Building a SECOND agent: `NEW-AGENT-plan.md` is the recipe extracted from this
one, and `NEW-AGENT-plain.md` is the same recipe in plain English.

---

## What ships

A rail destination, **Agents**, between Chats and Routines, and its first agent, the
**SEO Writer**. It is a port of the SEO workflow in `Backlink gets Automated` into an
agent that works in front of you:

1. **Setup, once.** You give the website. It catalogues every page the way the
   workflow's site-catalogue engine does (CMS API, sitemaps, web archive, crawl, with
   coverage gates), indexes every page by meaning with Voyage (one vector per title,
   many per body), and builds the brand pack: voice, style guide, product facts, readers,
   real numbers, stories, brand cards, the pages a call to action may link to, and the
   writer brief every article is written from. You confirm the flagged rows.
2. **Per article.** Topic (named or suggested) → research the way the content machine
   does (the world statement, real keyword numbers with the world check, the live
   results with Google's answer, the winning pages, evidence cards with verbatim quotes
   and sources, the gap check, your own pages found by meaning) → the blueprint (the
   spine filter with PROTECT, clustering, headings, links attached) → the write phase
   (planner, architect by format, writer with its editing passes, internal links laid
   in by meaning and judged on real page text, sources numbered).

Five stages on the bar: Setup › Topic › Research › Blueprint › Draft. Five checkpoints:
the brand pack, the topics, the brief, the plan, the draft. No credit gates: paid steps
do a DataForSEO balance pre-flight and say plainly when they skipped.

The agent runs on the `claude` CLI the panel already drives, so it bills the same
subscription the chat does. No API key. DataForSEO and a free Voyage key are the setup.

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

---

## What shipped, and how it was verified (2026-09-04, release 2.240.0)

| Lane | Result |
|---|---|
| `seo_agent/tests/run_all.sh` | ALL SUITES PASS, eleven suites: store, loop (18, incl. the Knowledge block), registry, behaviour, CLI provider, foundation (14 gates and reconcile checks), index, browser fetch (incl. the write-phase and research fallbacks), brand, research, write phase |
| `pytest -q` | 708 passed, 21 failed: the same 21 as the baseline in `/tmp/base.txt` (shadow / runtime-state tests that need a live flag). `test_agents_api.py` 16, `test_shell_browser_fetch.py` 8, `test_update_install_guard.py` 14 |
| Node suites | `test_agents.js` 30; panel 224, nav 46, charter 31, governance 104, connectors 28, provider switch 41, workspace 55, update attach 9, update banner 7, usage 7, three shadow suites green |
| Live setup, testlify.com, repo backend on :7011 | the site answered every plain request with a Vercel challenge; read through the browser. 11,656 sitemap URLs, 9,792 archive URLs (261 live of 300 probed), settled to 400 pages with text; 1,050 passages embedded with Voyage; brand pack built from the pages: writer brief 2,089 words, 4 personas, 26 flagged stats, features 7,946 words after a failed-then-passed quality gate, 25 CTA pages |
| Live article, demo mode ($0) | no DataForSEO login, so every keyword number and ranking page was demo data, marked as such at every step. Research: 29 seeds, world statement, primary keyword chosen with the split-world check, 96 evidence cards + 120 from the gap fill, 7 own pages found by meaning (111 passages), reuse verdict, brief checkpoint. Blueprint: the spine filter dropped 307 of 327 cards, and every dropped card was demo text from the fake ranking pages; the 20 kept were real Testlify passages; 6 sections, 14 links attached, plan checkpoint. The agent then noticed the plan had no formula section and asked before the long write. Write: 8 sections, 2,402 words of body, the coherence edit blocked once for two invented numbers and passed on the retry, sentence pass 18.0 to 13.2 words, 6 internal links placed by meaning and judged on page text (integrity clean, 10 rejected), assembled at 3,100 words with 5 FAQ and 4 sources, the keyword checklist reported honestly (primary not in the H1), draft checkpoint, saved to the library |
| Screenshots, light and dark | fresh hero, ready hero, Knowledge (catalogue, gates, page index and map), brand pack, a brand file, Tools, Connections, the research brief panel, the blueprint panel, the draft panel |
| Not run here | `qa-shell/run.sh`; a real-account research or article (DataForSEO balance is below zero until topped up) |

The findings from running it are in `seo_agent/HISTORY.md` under "Found by running it, not by reading it (this release)".

## What shipped, and how it was verified (2026-09-03)

| Lane | Result |
|---|---|
| `node test_agents.js` | 24 passed: block ids agree with the Python splitter byte for byte; substeps nest; an answered approval shows its decision; an interrupted step never spins; hostile labels are escaped; the topic footer needs a pick |
| `node test_panel.js` / `test_nav.js` / `test_charter_filter.js` / `test_governance.js` | 224 / 46 / 31 / 104 passed. `test_nav.js` now pins eight destinations |
| `pytest -q` (all `test_*.py`) | 685 passed, 21 failed — the same 21 as before this work (shadow / runtime-state tests that need a live flag on this machine). `test_agents_api.py`: 15 passed |
| `seo_agent/tests/run_all.sh` | ALL SUITES PASS, including the 529-retry and crawl-refused fallback checks |
| `electron/test_provision.js` | 17 passed |
| Live, repo backend on :7011 | the `claude` CLI answered through the subscription (turns of 4.7–5.2 s when the API was quiet, 529s retried with the retry visible in the log); DataForSEO indexed 108 ranking pages of testlify.com after the site refused the crawl |
| Screenshots, light and dark | the run log with a real failed-and-explained crawl; the hero; Connections; Tools. The pane measured 942 px wide beside an open chat pane after the `agwide` fix (385 px before) |
| Not run here | `qa-shell/run.sh` (needs `/Applications/Sutra.app`, not installed on this Mac); `qa/run.sh` |

### Found by running it, not by reading it

1. A `note` class on a run-log entry picked up Sutra's callout style (`.note`). Renamed `quiet`.
2. The browse pane shrank to 385 px beside an open chat pane. `render()` now pins the Agents pane to the row, the way it pins the Shadow screen.
3. `(compatible; seo-agent/1.0)` as a User-Agent got a 429 on the first request. The crawler now presents as a browser; the site still refuses, so the index falls back to search data.
4. `API Error: 529 Overloaded` on one turn killed a run and was reported as "not signed in". Transient errors are retried with backoff and named in the log; only a login failure is a login failure.
5. Pytest collected the engine's script-style tests and hit their `sys.exit`, aborting the whole session. `conftest.py` excludes them; they have their own runner.
6. The Playwright wait for `networkidle` never fired: the panel holds an SSE stream open.

### Left for a later release

- Drag-to-reorder in the blueprint (arrows ship).
- A "try again" button on a failed run (typing a message starts a new run).
- The Electron shell lane, once an app is installed on the QA machine.
- Speed: a model turn on the CLI's default model took 2–5 minutes when the API was loaded. `SEO_AGENT_MODEL=sonnet` is the knob; not set by default because writing quality wins.
