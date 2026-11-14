# Memory evaluation for Sutra Pro

Audience: the owner and the team, including the shared-library maintainer.
Status: proposal for decision (revised after a verification pass). Version context: Sutra Pro 0.4.0. Date: 2026-11-13.

Facts are tagged **[verified]** when read from a repo, PyPI or docs page during this pass, and **[unverified]** when not. Untagged candidate facts in section 4 rest on a README or package page only. Nothing was benchmarked or installed. Retrieval quality, footprint, concurrency, Windows wheel availability and full-tree licences are unmeasured for every candidate. No LICENSE file was opened for any candidate, so every licence claim rests on README or page text. All numeric thresholds in section 3 are proposed targets, not measured baselines.

## 1. Summary and recommendation

1. No open-source memory layer was found that fits Sutra as a drop-in dependency without a Sutra-owned wrapper. The popular layers (mem0, Letta, LangMem, Graphiti/Zep, Cognee) write through an LLM and most default to hosted models [verified for mem0: OpenAI gpt-5-mini and text-embedding-3-small]. Basic Memory is AGPL-3.0. The reference MCP memory server needs Node 24+ and a separate process.
2. One candidate is close: **agentrecall-db** (MIT, stdlib sqlite3, FTS5/BM25, TTL, purge, optional semantic extra). It meets the hard environment constraints on its PyPI page. It lacks the gate, provenance, scope and budget features, which Sutra must write in any case. Its source was never opened.
3. Recommendation (weakened from the first draft): build the Sutra-owned **memory provider** on SQLite FTS5 with bm25, with the record family and `GATE.check` as the owned layer. Whether the storage engine under it is Sutra's own table or a vendored agentrecall-db is **not decided on evidence**. No effort estimate or code read supports either side. Make that choice in the first spike (section 6).
4. Borrow patterns: mem0's scoping and extract-then-store idea (model only proposes), agentrecall-db's TTL and forget, Graphiti's validity window, the MCP server's atomic-replace write.
5. Vectors are a later step, only if the 50-item fixture shows lexical recall below the 80 percent top-5 target. Evaluate the light path first (agentrecall-db's model2vec extra, about 10 MB, with sqlite-vec) and a numpy brute-force fallback, before bge-small or MiniLM. Switch triggers are in section 6.

## 2. What memory means for Sutra today, and what is missing

"Library" means two things in Sutra, and memory must not mix them up.

- **The Interface library** (`sutra_app/library/`, closed pydantic models, one write gate, tolerant reply parser). It validates and does no I/O. A memory record type would be one more registered family here.
- **The Template library** (vendored `j2_template_lib.py`, `library/templates.py`). It stores reusable section specs, not facts or experience. Memory stays separate from it (see section 5).

**Memory-like facilities today** (five narrow ones over three stores):

| Facility | Store | Retrieval | Read by |
|---|---|---|---|
| J2 lessons and playbooks | per-department JSONL files (D26) | word overlap on `[a-z]{4,}`, top 5 lessons; playbooks by business_type, top 2 | Adaptation prompt only |
| Owner notes | SQLite meta key `owner_notes` | none (all injected, capped 2400 and 1200 chars) | org agent and direct chats |
| Standing rules | meta key `rules:<dept_id>` | none | framed into a run as team-lead context |
| Chat transcripts and search | `chat_messages` plus FTS5 `chat_search` | FTS5, max 50 rows, scoped in SQL | search route, carry-over |
| Team find and chat grounding | SQL rows | word match, 3000 chars | direct chats |

**What is missing:**

- No agent-writable, owner-visible memory with provenance. Lessons come only from Adaptation after Audit.
- No scope by chart node. Memory is per department, so nothing crosses teams or nodes, and nothing survives a chart merge by design.
- Only Adaptation reads lessons. Playbooks are website-shaped and not catalogued as a family.
- No ranking beyond word overlap, no expiry or decay for lessons, and no owner edit or delete UI.
- Deleting a department leaves `memory/` behind (ENGINE_OWNED).
- No single interface. Each facility has its own caps and format.

## 3. Fit criteria (tightened, testable)

Each criterion is a pass/fail test. Numbers are proposed targets chosen for this evaluation; none is derived from a baseline measurement. Day 4 of the trial (section 6) measures the baseline and may revise them.

1. **Offline and keyless.** Store and retrieve with sockets blocked and no provider key variable set, and the tests pass.
2. **Embedded, one folder.** In-process or a plain file/SQLite store under `SUTRA_DATA_DIR`, with no daemon, container or port. A backup, wipe, restore round trip restores all memory, and deleting the folder removes all of it.
3. **Python 3.11 on Mac and Windows.** Installs from wheels on macOS arm64/x64 and Windows x64 with `uv pip install`, no compiler, no POSIX-only call. Any file lock goes through `oslayer.py`.
4. **Licence.** The full transitive tree is MIT, Apache-2.0, BSD or ISC. A scan finds no GPL, AGPL, SSPL, BUSL or non-commercial term, and a LICENSE file can ship beside any vendored code.
5. **Scoped keys.** Write and query by node id, department, function and optionally task or run. A test with two departments and a division shows no cross-scope leakage. An explicit org-wide scope exists. Scopes re-point on merge, move or archive through carry_links and the alias map without losing items.
6. **Retrieval quality.** On a fixture of at least 50 real lessons, playbooks and notes, the labelled item is in the top 5 for at least 80 percent of queries and beats `relevant_lessons`, using keyword, BM25, FTS5 or a locally shipped embedding model only.
7. **Gate validation.** The record is a closed, strict, versioned family (extra=forbid, canonical JSON plus sha256, schema export and drift test). Model-proposed memory is accepted only via `GATE.check`. Over-long text, unknown keys and secret shapes are rejected with Violation rows, and there is no direct model write path.
8. **Secrets safe.** A planted fake key (egress `SHAPES`, a KEY/TOKEN/SECRET/PASSWORD/AUTH env value, or a `.env` value) is refused or redacted before storage. It never appears in the egress audit row or the prompt text.
9. **Provenance and owner control.** Each item records writer (owner, agent function, system), time, source run/task/message id and a mock/test flag. It supports delete and expiry, is listable and editable by the owner, and mock/test items never reach a live run.
10. **Bounded, reproducible recall.** At most N items under a hard character budget, in stable order (score, then recency, then id). An empty store adds nothing, not even a heading, and golden prompt tests do not flap.
11. **Concurrency and crash safety.** The server plus 3 engine processes can read while one writes. A kill -9 mid-write loses at most the last item. 50 concurrent appends from 4 processes lose none. Tested on both OSes.
12. **Scale and graceful failure.** At 10,000 items a recall takes under 100 ms, the store stays under 50 MB, startup adds under 1 s and 100 MB. Any failure or lock timeout returns fewer or no items and never fails a run.
13. **Fit with what exists.** Ingests `lessons.jsonl`, `playbooks.jsonl`, owner notes and `chat_search` content without loss. Can sit behind the per-department files or replace them behind one interface. Stays separate from the template library. Vendored J2 text stays byte-identical except through a numbered patch.

**Criteria not yet in the list (to decide, see open questions):** owner data portability (export format), encryption at rest, multilingual tokenization, schema migration and index rebuild cost, telemetry and egress behaviour per candidate (checked only for some), maintainer bus factor and release cadence, and the cost of ownership (code size and test burden) of building versus vendoring.

## 4. Candidates compared

Dates are from PyPI where the GitHub Releases section was empty. Where a version or date could not be confirmed from the page read, it is marked [unverified]. "Unverified" notes apply to the full transitive tree, Windows wheels and measured performance unless stated.

| Name | Licence | Maturity | Local-first | Integration shape | Fit | Main risk |
|---|---|---|---|---|---|---|
| mem0 (mem0ai) | Apache-2.0 [verified] | 68.9k stars [verified]; PyPI 2.2.1 (Sep 2026) [unverified] | Only with custom glue; defaults to OpenAI gpt-5-mini and text-embedding-3-small [verified] | In-process library; needs an LLM and embedder | Fails criteria 1, 7, 9 out of the box | Hosted defaults; heavy tree [unverified]; README mentions a v3 migration and local-only configs (e.g. Ollama) that were not assessed |
| OpenMemory (mem0) | mem0 Apache-2.0; subfolder [unverified] | Status [unverified] (docs 404) | Docker stack | Several services, own ports | Fails 2 and 12 | Docker plus an OpenAI key by default [unverified] |
| Letta | Apache-2.0 [verified] | 25.4k stars [verified]; PyPI 0.34.12 (Oct 2026) [unverified] | Needs own server (`letta server`) [verified] | Agent runtime and server, not an importable store | Fails 1, 7 and the process model | A second agent framework; the claim that repo focus moved to a coding CLI is [unverified] |
| LangMem | MIT [verified] | 1.8k stars [verified]; PyPI 0.0.30 (Oct 2025) [unverified] | Needs custom store | Library over LangGraph BaseStore | Namespace scoping is a good idea; fails 1, 2, 7 | Release staleness [unverified]; Postgres-centred persistence |
| Graphiti / Zep | Apache-2.0 [verified] (Zep hosted: proprietary) | 32.8k stars [verified]; release date [unverified] | Needs a graph DB | Library (Python 3.10+) plus Neo4j, FalkorDB, Neptune or Kuzu | Fails 1 and 2; fails 3 only on the embedded path (FalkorDB Lite needs Python 3.12+, Kuzu deprecated) [verified] | Telemetry on by default, opt-out via PostHog [verified] |
| Cognee | Apache-2.0 [verified] | 33.3k stars; v1.6.1 (24 Sep 2026) [verified] | Keyless local operation claimed on its page [verified]; uses GLiNER and a local embedding model downloaded on first use [verified] | Library with embedded DBs | Closest of the heavy group; 5, 11, 12 unverified | Model downloads and footprint [unverified]; storage format not examined |
| MCP memory server | MIT (README) | In the official MCP org; v2.1.1 (Nov 2026) [unverified] | Yes | Node.js 24+ stdio process, JSONL file, temp file plus rename, `.lock` file [verified] | Fails 3 and the process model | Search behaviour (substring only) [unverified]; a "two lock schemes" claim from the first draft is not supported and is dropped |
| Basic Memory | AGPL-3.0 [verified] | 4.6k stars [verified]; pre-release status [unverified] | Anonymous Umami events (cloud promos and login), off with `BASIC_MEMORY_NO_PROMOS=1` [verified]; update checks [unverified] | MCP server, Python 3.12+ [verified] | Licence blocker if Sutra links or ships the code. Used purely as an external MCP tool the blocker is weaker, but it would still be a second process and a second store | AGPL; Python 3.12+ |
| agentrecall-db | MIT (PyPI) [verified] | 0.2.0 (16 Aug 2026) [verified]; single maintainer [unverified] | Yes; no third-party core dependencies, TTL and `purge_expired` [verified] | stdlib sqlite3, FTS5, BM25, TTL; optional semantic extra (model2vec about 10 MB plus sqlite-vec, hybrid RRF) [verified] | Meets hard constraints 1-4 on its page; lacks 5, 7-10 as far as the page shows (code not read) | Very young; repo, code and LICENSE not opened |
| Mnemosyne | MIT (README) | 3.6k stars; no releases listed | Yes (remote embeddings off) | SQLite plus sqlite-vec, optional fastembed | Scopes roughly map; embeddings break the memory budget | About 800 MB RAM with local embeddings (page figure) |
| SQLite FTS5 (already in Sutra) | Public domain | Core SQLite | Yes | Table plus FTS5 index in the data folder | Expected to meet 1-3, 5, 7-12 by design; not measured | Lexical only; English tokenizer |
| sqlite-vec | Apache-2.0 and MIT [verified] | 8.3k stars [verified]; pre-v1 [verified]; single maintainer plausible (repo owned by asg017) but weakly supported; release [unverified] | Yes | Loadable extension in the same db | Possible later option | Extension loading on Python 3.11 and Windows wheels [unverified] (Windows listed as supported) |
| Chroma | Apache-2.0 | PyPI 1.5.9 (May 2026) | Partly | Separate persistent store | Second store; heavy | Model download [unverified]; index-drift concern is [unverified] |
| LanceDB | Apache-2.0 | PyPI 0.41.0 (Oct 2026) | Yes | Embedded folder store | More than needed | Native tree, footprint [unverified] |
| txtai | Apache-2.0 | PyPI 9.14.0 (Oct 2026) | Partly | Framework with Transformers | Too heavy | Large install |
| Qdrant local mode | Apache-2.0 | PyPI 1.20.0 (Oct 2026) | Yes | In-process path store | Positioned as dev mode | Single-process access likely [unverified] |
| FastEmbed + bge-small | Apache-2.0; model MIT | 0.9.1 (Oct 2026) | After the model is on disk | ONNX embedder | Candidate for the vector step | First-use download |
| MiniLM-L6-v2 | Apache-2.0 | Model card | After files are on disk | Via ONNX | Smaller; 256-piece truncation | Truncates playbooks |
| Kuzu | MIT [verified] | Archived 2025-10-10 [verified] | Embedded | Graph DB only | Dead end | No maintenance |
| Claude Code memory files (a convention) | n/a | Official docs | Yes | Markdown files plus index | Format idea only | Bypasses the gate if relied on |

**Not evaluated** (listed so the gap is visible): Zep Community Edition, MemGPT-style stores, Hindsight, Supermemory, Memori, Redis-based layers, sqlite-vss (predecessor of sqlite-vec), DuckDB VSS, Turso/libSQL vectors, Tantivy/Whoosh for pure lexical search, Ollama-backed configurations of mem0, Letta or LangMem, and static or small embedders other than those above (model2vec is covered only through agentrecall-db's page).

### Serious candidates

**agentrecall-db.** The closest ready-made match on its PyPI page: stdlib only, FTS5/BM25, TTL, forget, purge, and an optional semantic extra (model2vec plus sqlite-vec). Its namespace is one string, and from the page it has no schema gate, provenance, mock flag or character budget. Those would be Sutra's wrapper in any design. It was seen only on its PyPI page, so code quality, tests, Windows behaviour and its LICENSE are unknown. Options: vendor it with its LICENSE beside it behind the Sutra gate, or use it as a design reference. This is a live alternative to building the table ourselves. Decide after reading its source in the spike.

**SQLite FTS5 plus a Sutra-owned record family.** FTS5 is already shipped for `chat_search`, so it adds no dependency. The server stays the only writer, and engine processes read through the server or a file, as the architecture requires. Scope columns live in the base table, bm25 ranks, and ties break by recency then id. Weaknesses: it matches words, not meaning, and the porter tokenizer is English only. Contentless-delete needs SQLite 3.43 or later, so use external content with triggers. Windows FTS5 availability is expected, because `chat_search` already relies on it, but memory-specific behaviour there is untested. That owning the store is cheaper than the alternatives is an assumption, not a finding.

**mem0.** It has the right scoping vocabulary (user, agent, run) and the most adoption, but its write path is LLM extraction against hosted defaults. Making it keyless means an LLM and embedder wrapper over the connector router, and the extraction step would still need replacing by gated records. The belief that this glue costs more than the FTS5 table is an unestimated judgement. Borrow the idea of the model proposing and code storing.

**Cognee.** The only heavy option that plausibly runs keyless and embedded. Its model downloads (GLiNER and a local embedder), size, scoping, concurrency across 3 engine processes, Windows wheels and storage format are unverified. A measured spike is the way to rule it in or out later, not a starting point.

**Vector step.** If lexical recall is not enough, evaluate in this order: (a) agentrecall-db's model2vec extra, (b) a numpy blob column with brute force at this scale, (c) sqlite-vec with FastEmbed bge-small or MiniLM. Risks for sqlite-vec: pre-v1 API, extension loading disabled in some Python builds, Windows wheels unverified. Any model must ship with the install or be fetched with the owner's consent.

**Graph memory (Graphiti, Zep, Kuzu).** Not now. Graphiti as a library supports Python 3.10+, but it needs a graph database server, and the embedded paths are deprecated (Kuzu) or need Python 3.12+ (FalkorDB Lite). Borrow only the valid-from/valid-to idea.

## 5. Integration and reuse through the library

**Library entry kind "memory provider".** A provider is a small registered interface, not a store of content. It exposes `propose`, `write`, `recall`, `list`, `forget`, `expire` and `repoint(scope_map)`. The Interface library registers the record family and a provider spec (name, version, scope kinds, char budget, N). The Template library is not touched, because section specs are reusable structure while memory holds facts and experience.

How each option would plug in:

| Aspect | Recommended (FTS5 provider; engine may be own table or vendored agentrecall-db) | mem0 / LangMem style | Graph / MCP / Chroma style |
|---|---|---|---|
| Provider shape | Built in, default | Adapter around a third-party object | Adapter plus a service or second store |
| Data lives | Table in `db.sqlite3` or a sibling file, in the backup tarballs | Their own vector store beside the data folder [unverified] | Own folder, server or Node file |
| Agent write | Agent returns a proposal parsed by `ReplyParser`; code checks it with `GATE.check`; only then insert | The library's LLM extracts and writes by itself (conflicts with the rule) | Tool calls write directly (conflicts) |
| Agent read | Code runs `recall(scope, query, budget)` and injects the text block; the agent never queries | Library search | Library search or tool call |

**Scoping.** Each record carries `node_id` (chart NodeId), `department`, `function` (identity, adaptation, priority, coordination, audit), optional `task_id` or `run_id`, and an explicit `org_wide` scope. A recall for a node returns its own items, optionally its ancestors' and org-wide items, and never another node's. On a chart merge, move or archive, `carry_links` and the alias map produce a scope map and `repoint` rewrites the scope columns in one transaction. Department deletion removes that department's memory rows, which also closes the leftover-`memory/` gap.

**Scrubbing.** Two passes. On write, the gate rejects over-long text, unknown keys and secret shapes (egress `SHAPES`, Redactor values, `.env` values) with Violation rows. On recall, the assembled block goes through the same egress scan as every prompt. A proposal that fails is dropped and logged, never stored half-redacted.

**Provenance and owner control.** Each row records writer kind (owner, agent function, system), time, source run/task/message id, a mock/test flag, an optional expiry, and a schema version with sha256. The owner can list, edit, delete and expire items, as with notes. Mock and test items are filtered in SQL for live runs.

**Recall.** Hard budget in characters and N items (for example the current 2400, 1200 and 5 caps), ordered by bm25, then recency, then id. An empty result adds nothing, not even a heading.

**Offline and stub behaviour.** With `SUTRA_OFFLINE=1` the provider works unchanged, since it needs no model. The stub connector can return canned proposals so write-path tests run deterministically. The default suite stays free of model and network calls.

**Engine processes.** The engine writes files only. It reads memory from a recall block the server prepares into the run folder, or by a server call. It writes proposals as files that the server ingests through the gate. Vendored J2 text stays byte-identical except through a numbered patch in `VENDORED.md` (P5 already gave lessons explicit paths, so this is the natural seam).

**Concurrency and locks.** SQLite WAL with the server as the single writer. Any file-based fallback uses atomic replace plus `oslayer` locks, never a second lock scheme. A lock timeout returns fewer or no items.

**Windows.** The provider needs only stdlib `sqlite3` with FTS5 and no POSIX calls. Slugs avoid Windows device names. Any vector extension must prove it loads on Windows x64 first.

**Ingestion.** `lessons.jsonl` and `playbooks.jsonl` are copied row by row into the family. Owner notes and `chat_search` content are linked by source id rather than duplicated until a need is shown.

**Data portability.** Open item: define an export format (for example canonical JSONL of `memory_item` rows) so owners are not locked to the SQLite layout.

## 6. Recommended starting option

**Sutra-owned memory provider on SQLite FTS5, lexical only.** The gate, record family, scope and budget layer is Sutra's regardless of the engine. The engine choice (own table versus vendored agentrecall-db) is settled on Day 1 below.

**Minimal first slice:**

1. Register one closed family, `memory_item` v1: id, scope (node_id, department, function, optional task/run, org_wide), kind (lesson, note, playbook), text (bounded), writer, source id, mock flag, expires_at, created_at.
2. One table plus an external-content FTS5 index with triggers, behind a `MemoryStore` interface (`write`, `recall`, `list`, `forget`, `repoint`).
3. A one-way import of lessons and playbooks, with the current word-overlap path kept as a fallback behind a switch.
4. Wire reading into Adaptation only (the existing slot), using the same prompt block and budget.
5. Gate, scrub and scope tests as in section 3, plus a Violation test for a planted key.

**Trying it in a week:**

- Day 1: read agentrecall-db source and LICENSE, install it on Mac and Windows 3.11, and estimate the wrapper effort for vendoring versus an own table. Record the choice. Day 1-2: family, table, gate and scrub tests (offline, sockets blocked).
- Day 3: import seed lessons and playbooks; build a 50-item labelled fixture.
- Day 4: measure top-5 hit rate against `relevant_lessons`, plus recall time at 10,000 synthetic items. Revise the section 3 targets if the baseline shows they were badly set.
- Day 5: two-department-plus-division scope test and a chart-merge `repoint` test.
- Day 6-7: crash test (kill -9), 4-process append test, Windows runner check, and a decision note.

**What would make us switch or add to it:**

- Top-5 recall below 80 percent on the fixture, or no clear win over the baseline: try model2vec, then a numpy brute-force column, then sqlite-vec with a bundled small model, all behind owner opt-in and a consented model download where a download is needed.
- sqlite-vec fails to load on Python 3.11 on either OS, or its wheels are missing: use the numpy blob column or stay lexical.
- A measured Cognee spike (footprint, wheels, licence scan, model bundling) passes every hard criterion and clearly beats the above on recall: reconsider as a derived index with the gated SQL row canonical.
- Owners need relations or temporal queries over memory: add valid-from and valid-to fields before any graph store.

## 7. Decision record candidates, risks, open questions

**Decision candidates** (D numbers assigned later):

- **Decision A.** Memory is a Sutra-owned library entry kind ("memory provider") with a closed `memory_item` family behind `GATE.check`. Third-party memory layers with their own write path are not dependencies. A small vendored store such as agentrecall-db remains open until the Day 1 check.
- **Decision B.** The first store is SQLite FTS5 with bm25 in the existing data folder, with deterministic ordering and a hard character budget. Vectors only after the fixture fails the bar, light options first.
- **Decision C.** Scope is keyed on chart NodeId, department and function, with an explicit org-wide scope. This supersedes the per-department-only rule of D26 for the new store, while the old files stay readable. Re-pointing goes through carry_links.
- **Decision D.** Models only propose memory. Code validates through `GATE.check`, scrubs and writes. No model has a direct write or query path.
- **Decision E.** The memory provider stays separate from the template library, which keeps holding section specs.
- **Decision F.** Any embedding model must ship with the install or be downloaded only with the owner's consent. No hosted embedding, ever (D7).
- **Decision G.** A candidate needs a permissive full-tree licence scan before use, including LICENSE files. AGPL and similar are excluded when linked or shipped (Basic Memory).

**Risks:**

- Lexical recall misses paraphrases, and the English-only tokenizer limits other languages.
- The index can diverge from content, so a rebuild command is needed.
- Migrating memory from per-department to scoped rows must not lose or leak items.
- Owning the store means owning its bugs. Coverage for crash, concurrency and Windows is mandatory. The cost of ownership is not estimated.
- Thresholds (80 percent, 100 ms, 50 MB) are untested targets.
- This evaluation rests on repo and package pages only. Any candidate fact marked unverified, or a candidate not evaluated, could change a ranking.

**Open questions:**

1. Should recall also include ancestor-node and org-wide items by default, or only on request?
2. Do playbooks stay website-shaped, or become a general `memory_item` kind?
3. Do other functions (not just Adaptation) read memory, and under which budget?
4. Should chat messages become memory automatically, or only on an owner or agent proposal that passes the gate?
5. What expiry defaults apply to agent-written items versus owner-written ones?
6. Is a dependency audit in CI (G27) a prerequisite for any later vector step?
7. Which real lessons and playbooks, and how many, go into the labelled fixture, and who labels them?
8. Vendor agentrecall-db or own the table? (Resolve on Day 1; blocks the store design, not the record family.)
9. Which extra criteria apply: export format, encryption at rest, multilingual tokenization, bus factor?
