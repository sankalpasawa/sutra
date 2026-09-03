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
- **Never let the model decide when to spend money.** Code decides: since 2.240.0 there are no approval stops for cost (the user asked for none), so every paid step pre-flights the DataForSEO balance itself and says plainly when it skipped
- **Never add a sixth stop.** Five is the budget: the brand pack once at setup, then the topics, the brief, the plan and the draft per article
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


---

## 2.240.0 — the rebuild as a port of the whole workflow (2026-09-04)

The first agent was a sketch: one-shot research, a word-overlap link picker, a
voice profile. This release replaces it with a port of the SEO workflow in
`Backlink gets Automated`, layer by layer. Each layer was built by reading the
original scripts and prompts and copying them, not from memory. `CONTRACTS.md`
is the build contract every layer followed.

| # | Thing | How it was proven |
|---|---|---|
| 00a | **`tools/index_site.py` + `foundation/`**: four enumeration sources (CMS API, sitemaps with the 17 probes and index recursion, web archive with capped liveness, link crawl as last resort), reconcile with provenance and the tracking-param blocklist, per-host token bucket with cooldowns, the keep-everything extractor with `#`/`##`/`###` markers and hidden-element stripping, per-language de-boilerplate, the bulk `ranked_keywords` traffic pull with Traffic_clean, the coverage gates and the report | `tests/test_foundation.py`, 75 checks on a fake site served through `httpx.MockTransport` |
| 00b | **Sites behind a bot challenge are read through a real browser.** Found live: testlify.com moved to Next.js on Vercel with Attack Challenge Mode; robots.txt, the sitemaps and every page answered 429 to any plain client, and cookies from a browser did not carry over. `tools/_browser.py` recognises a challenge (header markers, then body markers, only on 403/429/503), switches that host to the browser for the run, and fetches with an in-page `fetch()` so XML and text come back raw. Two backends: the desktop shell's hidden window (`main.js` loopback service, token per launch, one request in flight, three windows max) and Playwright on a dev machine, driven from ONE thread because the sync API is thread-bound (with a plain lock, 12 of the first 19 pages failed) | `tests/test_browser.py` 18 checks against a fake shell service; `test_shell_browser_fetch.py` 8 pins on main.js; live: one navigation cleared the challenge in 4.6s, then six threads fetched six pages, all 200, in 9.7s |
| 00c | Liveness probes on a challenged host go through the browser too. Found live: all 300 archived pages read as "gone" because HEAD got the challenge | pinned in `test_browser.py` |
| 0i | **`tools/_index.py` + `tools/voyage.py` + `tools/build_page_index.py`**: the two-vector Voyage index (voyage-4-large, one vector per title, 4,800-char body chunks with 600 overlap, resumable per page, atomic .npy saves), the blended score (0.5 title + 0.5 best body chunk), and an embedding map (PCA of the title vectors) for the Knowledge screen | `test_research.py` and `test_write.py` build a tiny index with a deterministic fake Voyage; the map is served by `/knowledge/embedding-map` |
| 01 | **`brand/` + `tools/learn_brand.py`**: the twelve builders (type roles, brand facts with ⚠️ rows, brand voice with the shortlist and the quality gate, style guide, features and cta-pages, writing examples, persona, voices, writing integrity, the writer brief with the verdict order and the loss check, brand cards from 8001, field sources verified on old.reddit) saved under `knowledge/brand/`, templates lifted byte-for-byte from the recipes | `tests/test_brand.py`, 140 checks |
| 03 | see the Layer 03 section above | 69 checks |
| 04 | **`write/` + `tools/write_article.py` + `editing/links_pass.py`**: planner (gather, select at 0.45, verify sources, freeze), architect (format router over eight archetypes, shape by road, brand cards with caps in code, allocate, section keywords with the free gate then the DataForSEO buy, headings with locked keywords), writer (body per section from its own facts and the writer brief, blend, wrapper with the CTA check, coherence with the invented-number block, readable, sentence pass, slop pass, the links pass, clean, assemble with the coverage checklist counted in code). The links pass is the workflow's: per-section blend + rerank over real page text, the judge sees the page excerpts, tolerant anchor placement, the integrity diff | `tests/test_write.py`, 141 checks |
| ui | Five stages (Setup first), five checkpoints (the brand pack), no credit talk anywhere, plain-English Tools rows from `registry.for_screen()`, Voyage in Connections, Knowledge with the company record, the searchable catalogue and its gates, the page index and its map, every brand file readable and editable, the draft panel with the links placed and their match scores | `test_agents.js` 30, `test_agents_api.py` 16 |
| mem | Memory reaches the work: `sh.memory_block()` is `{{MEMORY}}` in every prompt that shapes or writes prose and in the research prompts that decide topic and angle | pinned per suite |

### Found by running it, not by reading it (this release)

1. The site refused every plain request (429, Vercel challenge). Browser fetch, above.
2. DataForSEO answered 401 to everything, including the free balance call that had worked three hours earlier: the user had changed the API password. The truth for credentials is the user's `.env`; re-synced.
3. Playwright's sync API is bound to its creating thread. Six crawler threads through one lock: 12 of 19 pages failed with "fetch failed (HTTP 0)". One worker thread and a queue fixed it.
4. Archived pages all read as "gone" on a challenged host because the HEAD probe was still plain HTTP.
5. The knowledge block in `agents_api.py` was replaced wholesale and took the library routes with it; the API test caught it.
6. A fresh chat re-ran the whole setup on a site that was already catalogued, embedded and brand-packed, because nothing told the model what Knowledge held. `loop._knowledge_block()` now writes that state into the system prompt with a plain "Setup is complete, do not run it again".
7. With no angle given, the research brief said "Anchors (title + angle) missing" a moment before the topic gate wrote the angle. The brief is now assembled after the gate.
8. Demo traffic names made-up pages, so the catalogue's traffic cross-check "failed" on every demo run. It now says "not checked: demo traffic" instead.
9. The demo article run (no DataForSEO login) proved the whole chain end to end at $0: research → brief checkpoint → blueprint checkpoint → draft. The blueprint filter dropped 307 of 327 cards, and that was right: every dropped card was demo text from the fake ranking pages, and the 20 kept were real Testlify passages. The agent then noticed on its own that the blueprint had no formula section and asked before the long write, which is the kind of question it should ask.
10. The write phase's source check and the research page reader still fetched with a plain client, so on the walled site every own-page source "could not be read". Both now recognise the challenge and read through the browser like the crawl does. And the brand-cards step said the file was "not on file" when it was on file but empty (no confirmed story, no research report); it now says which.
11. The readable rewrite was asked for about 2,100 words and returned 2,899; the assembled draft came in at 3,100 against a 2,200 to 2,800 band, and the report says so. The pass is ported as it was; the length drift is the original's, not a porting slip, and is worth a tighter prompt later.
12. The FAQ answers the wrapper writes can carry general-knowledge numbers (an agency fee range, for one) that no card supports. The body's numbers are source-checked; the wrapper's are not. Listed under "Not done".
13. The agent closed the demo run with "Saved. It's in the Library" and the Library was empty: saving was a button, and the model narrated a step it never took. Approving the draft now saves it in code (`loop.save_to_library`, the same function the button calls), the run log gets a `saved_to_library` row, the model only learns of it from the tool result, and the item is titled from the draft's own H1 rather than the blueprint's. Loop suite +6.
14. A fresh chat on the finished site went straight to research, no setup re-run, once the Knowledge block was in the prompt (checked live after the restart).

### Not done, and said so

- STORM does not ship. `research/evidence.py` is the named substitute (see Layer 03).
- The paid replacement-source hunt and the paid enrichment search in the write phase are skipped and reported.
- Voices from the field (Reddit/Blind/LinkedIn per article) is not ported.
- The ranked net (s1b) needs the asset engine's vetted competitor URLs, which this agent does not have.
- The bundled app has no Playwright; it uses the shell's window. A source checkout without Playwright says plainly that a challenged site needs the app.
- The wrapper's FAQ and close are not run through the source check, so a number there can be unsupported. The body is checked; the wrapper is the next place to check.
