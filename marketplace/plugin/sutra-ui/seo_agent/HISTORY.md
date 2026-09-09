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

### 2.242.0 — the audit against the original, and what it found (2026-09-04)

Five readers were pointed at `Backlink gets Automated` and the port side by side, one per layer.
The port turned out faithful in most places (every DataForSEO endpoint byte-identical, all of
engine 13's code discipline intact, 20 of 23 prompts differing only by the memory block) and
badly short in two. Both are now closed.

15. **The catalogue was 400 pages of an 11,917-URL site, and every gate said PASS.** The 400 came
    from the user's own first message ("read at most 400 pages") and then froze: the stage reuse
    key compared only the domain, so every later uncapped run reused the capped file. The report
    contradicted itself in writing, "11517 URLs found but not read (max_pages 3000)" beside
    "read: 400", and still passed. Fixed three ways: the reuse key carries the run parameters, the
    default cap is gone (the original ships none), and URLs found but never read now FAIL the
    accounting gate. The original's rule, quoted in its own plan: a short catalogue must never look
    like success. Re-crawled: 11,734 pages, all 13,016 URLs read, 99.7% with text.
16. **Every thin brand file was downstream of that.** stories.md was empty because the 46
    customer-story pages were never crawled; brand-cards.json was empty because it reads stories;
    features.md was one-seventh the original's Integrations section because the builder saw 3
    integration pages instead of 153; writing-examples picked the homepage because type-roles had
    collapsed to one type. Nothing was wrong with the builders. All twelve are faithful ports.
17. **The research asked no questions.** `evidence.py` searched the article's own ranking keywords
    and read what came back: 7 searches where STORM asked 36 generated questions across 132 pages.
    A card could only ever be a sentence copied off one page. Ported the method as plain Python
    (`research/curate.py`, `research/dossier.py`): four mixed personas interview an expert, each
    question seeing the previous answers, then a written dossier, then cards lifted from that.
    Live on real pages: 16 questions, a 14,856-word dossier, 483 cards, **256 of them citing more
    than one source**. The shim is deliberately not ported; it exists only because dspy speaks the
    OpenAI HTTP API.
18. **The run ended with data, not documents.** The original writes `research-doc-<slug>.md`,
    `bundle-<slug>.md` and a numbered proof folder. The port computed every input and rendered
    none, so a run could only be checked by reading JSON. `research/render.py` writes both, and the
    trail names all twenty working files in plain English, clickable in the panel.

### Found by looking at the screen, not by testing (this release)

19. The catalogue opened on a screen of red. Only 31 of 11,734 pages failed to extract, but with no
    traffic pulled every page sorted equal, so the failures came out on top.
20. The title index checked only that its file existed, not that it covered the pages we have. The
    catalogue went 400 to 11,703 and the title index quietly stayed at 400, so an internal link
    could only ever match one of the first 400 titles.
21. `serp_advanced` had no balance guard, so a research conversation would have fired ~48 requests
    at a balance of -$0.07 for every one to be refused. The first version of that guard compared
    against a constant that does not exist, failed open, and was caught by running it.
22. The bundle's numbered pointers filtered out missing brand files without renumbering, so the
    list read "1." then "10.".
23. The research conversation's progress line reported every page as newly read even when it had
    been read already.

## 2.254.0 — the audit's findings, built

An audit of his 223 scripts and 119 prompts against Sutra found 25 gaps. He ruled on every one:
eighteen to build, four to skip with his reasons recorded, and the workspace held. This release is
the eighteen, plus the eight things he could see were broken on screen, plus three he asked for.

### The eight things that were broken on screen

24. **"Check for changes" and "Import a traffic file" did nothing.** Both endpoints were healthy the
    whole time — `refresh_site.run(preview=True)` was proved against his own 11,656-page catalogue,
    and `traffic_import.apply` imported from both a path and pasted text. `agAction` simply had no
    arm for either button, so the click fell through to `default: break`. A silent no-op is worse
    than a missing button, because there is nothing to report.
25. The traffic import button is gone. The importer stays and the agent offers it in chat when an
    account runs dry, which is the only moment it was ever for.
26. Chats from VS Code and elsewhere stopped appearing in Sutra's own chat list.
27. The right-hand panel no longer renders beside the SEO Writer at all.
28. Three of the twelve work tools had no plain name, so the Tools tab drew "Refresh site",
    "Import traffic" and "Build assets" between "Learning the brand" and "Writing the article".
    `registry.label()` falls back to the function name with its underscores taken out, and that
    fallback looks like a name, which is why it survived. Two tests now refuse it.
29. "Improve one of our existing pages" is deleted. It was a starter button with nothing behind it,
    written before the reuse check existed.
30. The Library's Format column reads the archetype off the article, not off the run, so an article
    still says what shape it was written to after its run folder is gone.
31. The byline questions are gone entirely: two interview questions, `voices.md`, its builder, the
    "Who writes" row and the byline half of the writer brief. His call. The brief is built from
    three sources now, not four.

### The eighteen findings

32. **`refresh_site` never re-read a changed page.** Two independent causes. The survey read the
    sitemaps and the CMS listing out of the raw cache, so it compared last week's list against
    itself; and the fetch pass could not refetch even when asked, because a page already read sits
    in the frontier as `done` and no worker ever claims it. The reported "N re-read" is now counted
    from what provably came off the wire.
33. **A failed catalogue gate stops the run.** His exits with "the catalogue is NOT trustworthy
    yet"; Sutra reported it and carried on, so a brand pack could be built on a catalogue that
    failed its own counting. Nothing is written now, and the refusal names what failed. This is the
    400-page-catalogue failure mode, closed.
34. Extraction has a real 20-second per-page kill and 4 worker processes, his numbers. It was
    restored without the guard trafilatura needs, so one page could hang a whole crawl.
35. The WordPress enumeration bisects again, 100 → 50 → 25 → 5 → 1. A large site was silently
    truncated. (The audit said it bisects the date range; his script bisects the page size. What the
    file does is what shipped.)
36. JavaScript-rendered pages get the fifth rung of his ladder — rendered in the browser Sutra
    already ships — instead of being recorded as failed.
37. **The gap fill is the real research conversation.** He re-runs the full four-researcher
    conversation per gap; Sutra did one keyword search, so the holes that mattered most got the
    thinnest answer. He called this the most important finding.
38. **A dossier under 1,500 words is refused, with one retry.** His reason, quoted: "a dud run
    poisons everything downstream." A 300-word dossier used to pass silently.
39. **A number can no longer be credited to a page that never said it.** A numeric card that lost
    its citation used to be handed the whole section's source list, up to ten pages. It is now
    matched against the passages the researchers actually read, or stamped `needs_source`.
40. A failed source hunt no longer deletes cards. Both cut paths became keep-strip-flag.
41. The digit guard is back: every figure in the draft checked against the cards, in code, once, at
    the end. Every step-level guard he has was already here; none of them could see whether a
    figure was real to begin with.
42. The brand-section rule matches his 2026-09-05 review: never volunteer a limitation. Sutra
    shipped the pre-fix wording while already carrying the post-fix rule byte-identical in two
    format profiles, so two of its own files disagreed.
43. **The relevance recheck.** It reads the finished sheet whole and proposes drops, because the
    generator is generous judging one page at a time. Atomic per idea, never per group; an idea
    backed by 50+ domains is never even shown to the judge; every verdict and every drop is written
    to an audit file. A proposed drop keeps its row and its proof and is ranked last rather than
    deleted, because Sutra's sheet is live and a consequence-free proposal would leave junk at
    rank 1. The 15% cap gained a floor of three, or on a sheet of two dozen ideas one honest drop
    is 17% and the pass refuses itself for ever.
44. Competitor candidates are enriched and every domain is checked to resolve before anything is
    paid for. Without enrichment his own run missed vervoe, criteriacorp, eskill and testdome;
    without validation he paid for two domains that did not exist. When *nothing* resolves, that is
    our network and not a dead list, so everything is kept and said out loud.
45. Soft-404s and duplicate bodies are killed. 70 rows in his real run were "Page Not Found" served
    with a 200; in Sutra they became content ideas.
46. Semantic dedup inside the competitor pool, his G2.5, worth 97 merges a string key misses. The
    comment justifying its absence — "each method already de-duplicated its own pool" — was false
    for competitors, whose only dedup was a normalised string key.
47. Format canonicalisation, his F0. He measured 127 distinct labels across 1,202 pages, so one
    strong format read as three weak ones, which is the only question the step exists to answer.
48. `tool_escalation` reaches the sheet. Step B asked for it and wrote it; the assembler never
    copied it, so every method-2 idea arrived flagged False. A comment claimed the schema had
    nowhere to record it, which had not been true since the schema was written.
49. **`pricing.md`.** Some product facts are drawn by JavaScript and are in neither the catalogue
    nor the raw HTML — his whole pricing table is one, verified 2026-07-20. He solved it with a
    hand-written seed file, and Sutra read that file and called it authoritative while having no
    way on earth to write it: not a question, not an editor, not a row on any screen. It now has a
    door in the Knowledge tab, the builder puts a blank form on disk so the door is never disabled,
    and saving it rebuilds `features.md` from the cached crawl in two model calls. One hop, and no
    further, by his decision. The old seed file is read and migrated once so nobody's typing is
    lost.

### The three he asked for

50. **The system prompt knows the state.** It had a four-step setup that never mentioned the asset
    engine or the interview, both of which had already shipped, so a new company was offered
    neither. It is now a table of every state the run can be in and what to do in each. The one he
    named: asked what to write with no asset sheet, it says the engine has not run rather than
    inventing a topic. `loop.py` says "Asset ideas: NO sheet" out loud, because the absence of a
    line is not a state a model can act on.
51. **"This isn't coming out right."** `find_prompt` hands the agent the map of all fourteen
    editable prompts and, on request, one prompt's live text. The agent names the step, quotes the
    lines and proposes replacement wording; the person edits it in the Prompts tab. The tool has no
    write path — not a disabled one, none — and a test asserts that, because an agent that quietly
    rewrites its own instructions is a thing nobody can debug afterwards.
52. One design pass over the Knowledge and Asset ideas screens rather than six patches.

### Found while merging, not by testing

53. **`check_internal_links` could only ever fail.** `site_urls()` returns `(set, domain)` and the
    caller read the pair as one value, so every URL was compared against a 2-tuple and came back
    missing, and the honest "no site index on file" warning was unreachable because a 2-tuple is
    always truthy. The suite had accepted "fail or warn", which is exactly how it survived. The
    passing case is now asserted in both directions.
54. `index_site`'s schema advertised "Default 3000" for `max_pages`. The default is 0, no cap. A
    model that believed it would have capped a large site and then been refused by finding 33 with
    no way to explain why.
55. **A refresh counted pages the last read had deliberately thrown away as NEW.** Soft-404s,
    robots-disallowed pages, machine paths and collapsed redirect aliases were all re-fetched every
    single time, and the aliases came back into the catalogue as separate pages duplicating their
    canonical target. So the first honest number the fixed button would have shown was wrong, and
    the catalogue would have grown a little every time it was clicked. They are now a fourth pile,
    reported as "already judged and dropped by the last read" with the reason for each, and an
    address can only return if the site says it changed since the moment we judged it. A second
    guard resolves genuinely-new addresses through their redirect and canonical before adding them,
    which catches the case the buckets cannot know about.
56. **And the other direction was worse: one broken sitemap file could delete every page it
    listed.** A page was ruled gone if any sitemap answered at all — but a child sitemap returning
    a 500, or timing out (which arrives as status 0), is filed as blocked and simply returns fewer
    URLs. On a site with a dozen child sitemaps, one bad response silently deleted a twelfth of the
    catalogue. Same for a CMS content type whose endpoint broke. A page is now gone only when every
    source that found it was asked again AND answered for that page, decided per page rather than
    per site, so one broken file costs only its own pages. Writing the test found the second-order
    version: the survey was overwriting the full read's URL listings, so a failure would have become
    the new baseline and the next check would have deleted everything the first one protected. A
    refresh now writes to its own work folder and only ever reads the full read's files, which also
    stops it corrupting `index_site`'s resume state.

### Not done, and said so

- STORM does not ship. `research/evidence.py` is the named substitute (see Layer 03).
- ~~The paid replacement-source hunt and the paid enrichment search in the write phase are skipped
  and reported.~~ **Both shipped in 2.253.0.**
- ~~Voices from the field (Reddit/Blind/LinkedIn per article) is not ported.~~ **Shipped in
  2.253.0.** Reddit reads through a real browser: plain HTTP gets a 403, and old.reddit serves a
  login page with a 200, which is worse.
- ~~The ranked net (s1b) needs the asset engine's vetted competitor URLs, which this agent does not
  have.~~ **Dropped by the owner, 2026-09-09:** *"you can skip this competitor keyword thing for
  sure, remove it, don't include it at all."* Not to be raised again.
- The `{{MEMORY}}` block appended to seven write prompts tells the model that a user's saved rules
  "win over any rule above that they contradict". That is a live override channel which could in
  principle defeat the fabrication rule, the product rule or the banned openers. It is not a bug
  anyone has hit and it was not in scope for this release, so it ships as it is — recorded here
  because it deserves a bound and nobody should discover it by accident.
- The bundled app has no Playwright; it uses the shell's window. A source checkout without Playwright says plainly that a challenged site needs the app.
- The wrapper's FAQ and close are not run through the source check, so a number there can be unsupported. The body is checked; the wrapper is the next place to check.
