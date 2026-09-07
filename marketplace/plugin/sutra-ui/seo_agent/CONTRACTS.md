# seo_agent build contract (read fully before writing a line)

The agent is a faithful port of the SEO workflow at
`/Users/devanshasawa/Desktop/SEO by Devansh/Backlink gets Automated/workflows/` (layers 00, 01, 03, 04;
02 is skipped except the Voyage page index, already ported in `tools/_index.py` + `tools/voyage.py`).
READ THE ORIGINAL SCRIPT AND PROMPT for every step you port. Copy prompts near-verbatim into
`prompts/<area>/<name>.md`; replace company-specific tokens with `{{BRAND}}` etc. Keep the original
constants and their comments. Where the original has a rule enforced in code, enforce it in code here.

## Package layout (relative to seo_agent/)
- `store.py`      run folders, knowledge, artifacts. `store.knowledge(name)` / `store.save_knowledge(name, data)`
                  read/write `knowledge/<name>`; name may include a subfolder, e.g. `brand/writer-brief.md`.
                  JSON when the name ends .json, else text. `store.knowledge_dir()`, `store.write_json`,
                  `store.now()`, `store.load_artifact(chat, run, name)`, `store.save_artifact(chat, run, name, data)`.
- `llm.py`        `llm.json_call(prompt, system=..., retries=1)` -> dict/list; `llm.text(prompt, system=...)` -> str.
                  Claude CLI only. Up to `llm.PARALLEL` (3) calls may run at once: use ThreadPoolExecutor(max_workers=llm.PARALLEL).
- `tools/_shared.py` `sh.reporter(ctx, tool)` -> `say(label, note)` emits a substep (ALWAYS emit progress: a silent
                  minute reads as a hang). `sh.load_prompt("area/name")` reads prompts/area/name.md. `sh.fill(tpl, **kw)`
                  fills `{{KEY}}` (keys are upper-cased). `sh.company()` -> the company record dict.
                  `sh.pages_with_bodies()` -> [(url, title, body)] from knowledge/content-database.jsonl.
                  `sh.page_bodies()` -> {url_without_trailing_slash: body}. `sh.brand_file(name)` -> text or "".
- `tools/dfs.py`  DataForSEO client. `dfs.post(path, payload)`; `dfs.available()`; helper calls. Location/language
                  come from the company record (`location_name`, `language_code`; defaults "United States"/"en").
                  ADD new endpoint helpers here, never call httpx directly from a step.
- `tools/voyage.py` `voyage.embed(texts, "document"|"query")` -> normalised float32 rows; `voyage.rerank(q, docs, k)`;
                  `voyage.available()`. `tools/_index.py`: `_index.status()`, `_index.build(pages, say)`,
                  `_index.load_title()`, `_index.body_best(Q, order)`, `_index.score(Q, alpha)` -> (blend, T, B, meta, order).
- Tools the model calls live in `tools/<name>.py` with `def run(ctx, **kwargs) -> dict` returning at least
  `{"summary": str}`; `"artifact": "<file>"` when one was written; `"error": str` for a soft failure the model should
  react to. `ctx` = {chat_id, run_id, step_id, emit}. Long pipelines live in a sub-package (`brand/`, `research/`,
  `write/`) with one module per step, each `def run(<inputs>) -> <output dict>`; the tool sequences them.
- Every step writes its output to disk (artifact or knowledge) before the next reads it. Resume: if the output
  exists and `redo` is false, reuse it. Atomic writes only (store helpers do this).

## The company record: knowledge/brand/company.json
`{brand, domain, wordpress_url, brand_oneliner, niche_definition, location_name, language_code, about}`.
index_site fills domain/wordpress_url/brand (from the homepage title/og:site_name); brand builders fill the rest.

## Knowledge layout (what the UI shows the user)
```
knowledge/site_index.json             {domain, page_count, pages:[...light rows...], indexed_at, report:{...}}
knowledge/content-database.jsonl      one line per page: {url, type, title, body}   (body carries #/##/### markers)
knowledge/top-pages.json              [{url, traffic, traffic_clean, top_keyword, intent}]
knowledge/catalogue-report.json       {gates:[{name, pass, detail}], coverage_by_type:{...}, provenance:{...}, gaps:[...]}
knowledge/content-index/              the Voyage index (tools/_index.py owns it)
knowledge/brand/*.md|*.json           the brand context files (see below)
knowledge/competitors.json            {competitors:[{domain, why}]}
```
Light page row in site_index.json: `{url, type, title, description, h1, word_count, body_chars, body_status,
traffic, traffic_clean, top_keyword, intent, keywords:[{keyword, position, volume}], modified, lang, source, extractor}`.
Keep `text` (first 400 chars) too, older code reads it.

## Brand files (knowledge/brand/), in build order, each with the ORIGINAL's structure
type-roles.json · stats.md · stories.md · opinions.md · page-shortlist.md · brand-voice.md · style-guide.md ·
features.md · cta-pages.md · writing-examples.md · persona.md · voices.md · writing-integrity.md ·
writer-brief.md · writer-brief-rulings.md · brand-cards.json · field-sources.md · seo-aeo-geo-checklist.md
Human gates become checkpoints: the tool saves everything, then the agent shows the pack (`show_artifact`
view `brand_pack`) for the user to confirm; ⚠️ rows stay marked until confirmed.

## Artifacts per run (chats/<c>/runs/<r>/artifacts/)
- `topics.json`         {topics:[{id, topic, angle, why_us, sparked_by, est_volume, est_difficulty}], recommended}
- `research.json`       the research brief: {topic, angle, world:{about, not_about}, spine, keywords:{primary:{keyword,
                        volume, kd, intent, split_world, why}, variations:[], secondary:[], in_body:[], spokes:[]},
                        serp:{who_ranks:[{rank,domain,title,url}], featured_snippet, ai_overview:{text, cites}, paa_on:[],
                        paa_off:[], related_on:[], related_off:[]}, winners:{format, common_h2s:[], drift:[], gaps_to_own:[]},
                        verdict:[...], build_spec:{word_band:{min,max}, ...}, cannibalisation:{keyword, rank, url}|null,
                        persona:{name, lens, why}, cost_usd}
- `cards.json`          [{id, gloss, verbatim, source_urls:[], internal_link|null, tag:"evidence"|"ownpage"|"brand-research"|"brand-result",
                        heading, origin, protected, relevance}]  ids continuous; ownpage cards from the Voyage index.
- `blueprint.json`      {h1, keyword_set:{primary, variations, secondaries, in_body}, sections:[{h2, job, target_keyword|null,
                        evidence:[card ids], internal_links:[], external_links:[], h3:[{h3, evidence:[], internal_links:[],
                        external_links:[]}]}], faq:[...], orphan_keywords:[], persona, format_archetype, word_band,
                        angle_filter:{kept, dropped}}
- `article.json`        {h1, intro, quick_answer, sections:[{heading, prose, h3s...}], faq:[{q,a}], close, close_heading,
                        cta_link, sources:[{n, url}], links:{inline:[], read_more:[]}, keywords:{...}, checks:{...}, length:{...}}
- `draft.md`            the rendered article (H1, intro, Quick answer, sections, close, FAQ, Sources)
- `links-report.json`   the links pass receipts (placed with sim/rr, failed, rejected, integrity)
- `write-report.json`   per step: what changed, what was blocked, coverage checklist

## Rules
1. Nothing invented: every number comes from a tool; every fact carries a card id + verbatim + source.
2. Code counts, AI judges. If you can count it, code does it. Guards (tag loss, invented number, heading change)
   are code and all-or-nothing where the original was.
3. NO credit/cost gating. Do not stop for approval before a paid call. Do a DataForSEO balance pre-flight and
   report it; below $0.50 skip paid calls and say so in the summary (never crash).
4. Memory: `store.memory_rules()` returns the user's standing rules. EVERY prompt that writes or shapes prose
   (shape, headings, write body, blend, wrapper, coherence, readable, slop) receives them as `{{MEMORY}}`
   (a bulleted list, or "(none)"). Research prompts that decide topic/angle receive them too.
5. Plain English in everything a user reads: summaries, substep notes, artifact text. No jargon, no tool names.
6. Tests: each sub-package gets `tests/test_<area>.py` in the house style (print PASS/FAIL, sys.exit), using
   `tests/_fixture.py` stubs. No network in tests: stub `llm.json_call`/`llm.text`, `dfs.*`, `voyage.embed`/`rerank`
   (deterministic vectors from a hash). Add the suite to `tests/run_all.sh`. `SEO_AGENT_NO_CLI=1 bash seo_agent/tests/run_all.sh`
   must print ALL SUITES PASS before you report done.
7. Do not edit files outside your area except: `tests/_fixture.py` (add stub branches, never remove), `tests/run_all.sh`
   (append your suite), `tools/_shared.py` (append helpers only), `tools/dfs.py` (append endpoint helpers only).
   Never touch registry.py, loop.py, agents_api.py, static/*.
8. Report back: files written, prompts ported (original -> new path), constants kept, what you deliberately
   left out and why, and the test output tail.
