# Build log

What is actually built and verified. **A line is only ticked when it has been run and looked at.**
"It should work" is not done.

Spec: `Ai for org/sutra-seo-agent-build-spec.md`

---

## Done and proven

| # | Thing | How it was proven |
|---|---|---|
| 1 | **Run folder + state** — `store.py` | Created a run, killed the process, re-read state from disk. Atomic writes (temp + rename in the same dir) |
| 2 | **Event log** — `store.emit` / `events.jsonl` | 13 events in the right order in the lifecycle test |
| 3 | **Tool registry** — `registry.py` | 10 tools. Costs and gates stripped from what the model sees, verified |
| 4 | **The loop** — `loop.py` | Lifecycle test: tools run, results feed back, it finishes |
| 5 | **Pause and resume** | Stops at a question, state survives on disk, resume puts the answer back as the tool result, carries on |
| 7 | **The money gate** | Stops before a paid tool, names the cost, does NOT run it when declined. Enforced in the loop, never asked of the model |
| — | **The server** — `app.py` | Boots. `/api/health` and `/api/tools` return real data |
| — | **The mount** — `mount/agent.json` | A manifest. No coupling either way |

| 10 | **The five work tools** + the DataForSEO client | Real crawl of mastersunion.org, 12 pages. All five tools drive with a stubbed model and write the right artifact shapes |
| 12 | **Topic suggester** | Six topics with angles, competitor rotation verified |
| 13b | **Sub-step nesting** | Every substep carries a parent. Fixed a real bug where `step_id` never reached the tools |
| 13d | **Library** | Saves the draft plus the research and blueprint behind it |
| 14a | **One chat, many runs** | Two runs, separate folders, separate logs, one shared conversation |
| 14b | **A tool that breaks** | Amber not red, the reason kept, a traceback kept, the agent told what failed, the run survives |
| 14e | **Four stops, in order** | approval → topic_list → approval → research_brief → blueprint → approval → article |

**79 checks across four suites. `./tests/run_all.sh` runs them all.**

| Suite | Checks | What it proves |
|---|---|---|
| `test_loop.py` | 14 | The lifecycle: gates, pause, resume, decline |
| `test_tools.py` | 23 | Each tool reads the right inputs and writes the right artifact |
| `test_endtoend.py` | 26 | The whole stack over HTTP, as the browser drives it |
| `test_behaviour.py` | 16 | The spec's claims, checked against the real thing |

**A real bug the tests caught:** approving a paid step used to bounce back to the model and hope
it asked again. It now runs the exact call the user approved. Wasting a turn was the small
problem; letting the model change its mind about a step someone just paid for was the real one.

---

| 6 | **The screen** | Six tabs render. Chat with the stage bar, nested step log, the artifact panel with all four viewers, question and approval cards. Screenshotted and compared to the Unify reference |
| 8 | **The checks** | Blueprint: 6 gates. Draft: 8 gates including orphaned cross-references and AI-writing. Each one fired on the fault it exists for |
| 9 | **Targeted editing** | One block rewritten, every other block byte-identical, drift raises, the model cannot smuggle in extra blocks |
| 11 | **Knowledge / Connections / Memory tabs** | All three render. Keys are never returned to the browser, only whether they are set |
| 13 | **Library, Tools tab, hash routing** | Library saves and lists. Tools shows cost and gate per tool. Deep links work |

---

## Bugs the tests and screenshots caught

| Bug | Where | How it was found |
|---|---|---|
| **Approving a paid step asked the model again** instead of running the approved call | `loop.py` | The end-to-end test walked the stops and the sequence was wrong |
| **`step_id` never reached the tools**, so substeps had no parent and could not nest | `loop.py` | Flagged during the tool build, confirmed by a test |
| **`drawPanel` set its cache key before awaiting the fetch**, so a second draw rendered a null artifact. The panel looked broken at random | `static/app.js` | Screenshots. It rendered sometimes and not others |
| **The middle column would not shrink** (flexbox min-width:auto), pushing the panel off the right edge | `static/app.css` | Measured in the browser after guessing at it three times and being wrong |
| **`claims_have_sources` excused any sentence containing the word "source"** | `checks/draft_checks.py` | A test whose own example said "with no source in sight" |

**The lesson worth keeping: every one of these was found by running it and looking, not by reading
the code.**

---

## Not done

| # | Thing | Why |
|---|---|---|
| — | **A real run against real APIs** | No DataForSEO credentials and no model key on this machine. Every path is exercised with a stub and demo data. **The wiring is proven. The writing quality is not** |
| — | Blueprint drag-to-reorder | The viewer renders and edits; reordering is not wired |
| — | Per-paragraph inline edit in the article viewer | The `/edit` endpoint and the safety net exist and are tested. The affordance is not on the page yet |
| — | Electron wrapper | Runs as a local server. Wrapping is the last step, deliberately |

---

## The rules, restated because they are easy to drop under pressure

- **Never take a shortcut.** If you think "close enough, fix it later", stop
- **Never hold run state in memory.** The folder is the truth
- **Never send the whole document to edit one paragraph.** Block only, then prove the rest is byte-identical
- **Never let a check fail silently**
- **Never reference anything outside this folder**
- **Never put a key in a file that could reach git**
- **Never let the model decide when to spend money.** The loop decides
- **Never add a fifth stop.** Four is the budget
- **Never hide a failure to make the log look clean.** The failures are the trust

## Verify like this

Build it. Run it on real data. **Screenshot it.** Compare to the reference in
`Ai for org/projects/unify-gtm/_raw/screenshots/`. Then tick it.

---

## Layer 03 — the content machine (research → blueprint), ported 2026-09-04

| # | Thing | How it was proven |
|---|---|---|
| 03a | **`tools/run_research.py`** + `research/` (one module per step): world → seeds → tight net → filter → metrics + intent → scorer panel + judge (the world check) → live SERP + snapshot → winners + extract → verdict/build spec → cannibalisation → topic gate → spine → persona → evidence → gap check (≤3 fill rounds) → own pages via the Voyage index + reuse verdict → `research.json` + `cards.json` | `tests/test_research.py`, 69 checks, DataForSEO faked at the wire so the real parsers run; every step resumable under `artifacts/_work/`; a second run spends nothing |
| 03b | **`tools/build_blueprint.py`**: spine filter (PROTECT, fail closed) → MECE clustering (asserted in code) → name + split → attach → orphan → FAQ + order (valid permutation only) → keyword set → `blueprint.json` | Same suite: PROTECT rescues a numeric off-spine card, MECE holds, an invalid order is rejected, a dead scorer aborts the build |
| 03c | **The evidence engine is NOT STORM.** 11-storm is a vendored research engine with its own venv and cannot ship in this package. `research/evidence.py` is the honest substitute: live SERP (depth 10) on the primary + up to 6 secondaries → free page reads → 1,200-char passages, 14 per page → one LLM harvest per page → every quote checked as an exact substring of the page, invented ones dropped. Narrower than STORM's interviews and outline; the run notes say so | The suite drops a planted fake quote and records the count |

Left out on purpose: the ranked net (s1b, needs the asset engine's vetted competitor URLs), the research-notes.md commentary file (the agent's substeps are that log), the HTML viewer, the queue/sheet bookkeeping and the spoke minting (topics come from the chat, not a CSV).
