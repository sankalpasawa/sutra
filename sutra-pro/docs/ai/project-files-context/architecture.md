# Architecture: Files and earlier context stay with a project
_Status: Proposed · Date: 2026-11-26 · PRD: ./prd.md · Decision to record: D451 (see section 13) · Base: origin/main e59d3ea0, Sutra Pro 0.8.3_

All paths are under `sutra-pro/sutra_app/` unless they start with `tests/` or `docs/`. Method: read the paths named here at e59d3ea0 and traced them end to end; no model was called, no code was run. Confidence is stated where a claim rests on reading only.

## 1. Context
```mermaid
flowchart LR
  subgraph Pages
    S[j2_ui.html start box + follow-up box<br/>lform / sform -> sendText]
    H[home.js Attention box]
    C[chat_composer.js direct chat]
    N[create_project.js]
  end
  S -->|POST /api/say?dept| E[engine/api/commands.say<br/>engine/views.py]
  H -->|picked project: /api/say, else cs_org messages| E
  H -->|cs_org| R[agent/runner.py planner]
  C -->|POST /chats/sid/direct| D[chat_v2.direct :236]
  E --> T[tasks.deliver_to_department -> _follow_up -> _insert]
  R --> T
  T -->|_start: RunSpec + run folder| L[engine host loop.py<br/>"Context from the team lead" line, upstream/ precedent]
  D --> G[chat_ground.ground -> ChatPort.set_system]
  D --> P[RouterChatPort._message -> Router._chat_turn]
  A[(AttachmentStore<br/>data/attachments/sha.ext, D440)] --- T
  A --- D
  X[(NEW project_files table, meta pinstr / pmem)] --- T
  X --- G
  X --- P
```
What is new is the bottom-left store and the arrows into it. Everything else is an existing path that gains a field or a block.

### 1.1 Current-state findings (what exists for projects, files, memory)
| # | Finding | Evidence |
|---|---|---|
| C1 | A project is a team (`departments` + `org_nodes`), with a folder (`departments/<id>/workdir.json`), one active chat session per team (`chat_sessions_active` unique on `node_id` where active) and many runs. Hiding keeps rows and files (D426, DL5). | `schema.py:102`, `api/teams.py`, `team_admin.py` |
| C2 | Archiving a team's chat creates a fresh active session; the archived one is read-only and unconnected to it. | `chat_v2.py` `ChatArchive.archive` / `_replace` (:118-145) |
| C3 | "+ New run" writes `page.json.since_run`; the next brief starts with no seed. | `tasks.py` `_follow_up`, `_reset_marker` (:960-1000) |
| C4 | A run is given: `user_text` (the owner's words), `framing` = rules block + chat-agent paragraph (20,000 characters, rules never cut), `upstream` files of other runs. It posts the framing as one system chat line "Context from the team lead: ...". `standing_rules.py` says this is "guidance, not enforcement; never read by J2's prompts or files". The one hook that changes a J2 prompt is `system_addendum(fn)` (P9, node-context file). | `tasks.py` `_run_spec` (:735-743), `engine/host/loop.py:664-669`, `engine/hooks.py:114`, `standing_rules.py:13` |
| C5 | The start box and follow-up box post `{text, template?, workflows?, usd_budget?}` to `/api/say`; the engine's parser (`views.py` `_say_*`), `commands.say` and `TaskService.deliver_to_department(dept, text, settings=)` have no file field; `tasks` has no column for one. | `j2_ui.html:1783`, `engine/views.py:740-800`, `engine/api/commands.py:101`, `tasks.py:878` |
| C6 | The direct chat grounding is 3,000 characters: node record, three task outcomes, owner notes, folder, rules. A new provider session is primed from the stored transcript only (`ChatTranscripts`, 20 messages; D440 added file text). Codex keeps the system text of a thread's first turn and never re-reads it; Claude gets it every turn. | `chat_ground.py:36`, `chats.py:530`, `router.py:1076-1100` |
| C7 | D440 gave the chat: stored files by hash, receipts, carry-over of earlier message files (30,000 characters), and made "Tell the team" refuse a held file (`TEAM_FILES`). Files belong to one chat line only (`meta.attachments`). | `attachments.py`, `chat_composer.js`, `home.js:664` |
| C8 | Memory-like stores today: owner notes (global, `meta owner_notes`), standing rules (`meta rules:<dept>`), J2 lessons (per department, Adaptation only), chat FTS search. None carries chat or run history into a new chat. | `docs/design/memory-evaluation.md` section 2 |
| C9 | Upload route is `POST /api/chats/{sid}/attachments` and the 413 guard raises its limit only for that path; a start page has no chat session id in hand. | `main.py:119-125` |
| C10 | Schema is at v9 (`departments.hidden_at`); migrations are DDL tuples or callables; an older app refuses a newer database. | `schema.py:342` |

## 2. Approach
One new concept, **project context**, with three parts per team: files, instructions, memory. It is read at three delivery points and written at five.

1. **Bytes**: reuse the D440 `AttachmentStore` unchanged (hash-named, 0600, deduped, kinds and limits). A new table `project_files` (schema v10) lists a project's files and holds their flags; instructions and memory are JSON documents in the `meta` table (`pinstr:<dept>`, `pmem:<dept>`), the same way rules and notes are kept (no table, in every backup).
2. **Per-request files** (the start box and every "Tell the team" route): ids travel with the request, are stored on the task (`tasks.input_files_json`, one snapshot of name, kind, size, characters per file) and are given to the run: copied into the run folder, named and excerpted in the framing.
3. **A new module `orchestrator/project_context.py`** (pure composition; no I/O except through two small ports) decides what is given, within fixed budgets: `compose_run_block`, `compose_chat_block`, `excerpts_for`, `receipt`. The run path and the chat path call it; no other module knows the budgets.
4. **Chat delivery**: the stable part (instructions, memory, manifest, and the files themselves while they fit) goes in the system text through `ground()`; per-message excerpts, when the files do not fit, are appended to that turn's user text, not to the system text. This keeps the system text stable, so a Codex thread (which reads it once) is reset only when the owner changes the project, not on every message.
5. **Memory** is code-written from rows already stored (the owner's request, the outcome sentence). No model call. The owner sees, edits and turns it off.
6. **UI**: one shared chip controller (`attach_bar.js`, extracted from `chat_composer.js`) used by the start box, the follow-up box, Attention, the composer and Create project; one Project panel (Files, Instructions, Memory, "What will be sent").

This follows the repo's current architecture: no new service or dependency, a project stays a team (D426), the engine gains no patch to J2 (only the host's own files and the vendored page's recorded edit E30), and DL5's "nothing is deleted behind the owner" holds.

## 3. Alternatives considered
| Option | Trade-off | Why rejected |
|---|---|---|
| A. Keep project files inside the project's folder (`<folder>/.sutra/knowledge/`) | Visible on disk, versionable | The folder is the owner's repo: writes there need edit access, pollute commits, clash with the export manifest (D428) and cannot hold files for a read-only folder. D428 already says Sutra's records stay in Sutra |
| B. Only per-message attachments, with an "attach again" habit | Zero new model | It is the current state; P2(d) in the PRD |
| C. Embeddings plus a vector index now | Better recall on large sets | New dependency or a model call, a download, no measured need. Word match with whole-fit up to 20,000 characters covers the target; the memory evaluation's own fixture can trigger it later |
| D. Model-written project summary as memory | Reads like Claude's | A paid call per update, can drift or leak file content into an entry, hard to verify against the record. Deterministic entries are checkable and editable. Left as OQ-2 |
| E. Put instructions into the standing rules | One place | Rules are tagged lines with a revision check and a practice pack; free text does not fit that shape and would change its schema |
| F. Replay the archived chat's whole transcript into the new chat | Complete | Up to 20 messages of mostly stale text, repeated every new session, unbounded in a long chat; an entry per chat is a bounded summary |
| G. Send all project files in every prompt | Simplest | Unbounded cost; breaks NFR-3 |
| H. One table for files, instructions and memory | One migration | Instructions and memory are small documents the owner edits as a whole with a `rev` check; the repo already stores those in `meta` |

## 4. Components
| Component | New/changed | Files | Public interface |
|---|---|---|---|
| Schema v10 | new | `orchestrator/schema.py` (`DDL_V10_PROJECT_FILES`, appended to `MIGRATIONS`) | section 5 |
| Project files store | new | `orchestrator/project_files.py` | `ProjectFiles(db, attachments, clock)`: `list(dept) -> FilesOut`, `add(dept, ref) -> FileOut` (from an `AttachmentRef`; limits; duplicate returns the existing row), `promote(dept, attachment_id, name)`, `patch(dept, fid, enabled=, name=)`, `remove(dept, fid)`, `remove_all(dept)`, `enabled(dept) -> list[FileRow]`, `text_of(row) -> str` (reads the store once and caches the length). Refuses a hidden project's writes (`ReadOnly`, D426) |
| Composition | new | `orchestrator/project_context.py` | pure: `compose_run_block(instructions, memory, files, attached, limits) -> Block`, `compose_chat_block(...) -> Block`, `excerpts_for(files, message, budget) -> Excerpts`, `receipt(block) -> list[dict]`, `context_sig(block) -> str`. `Block` = text, parts (name, chars, cut), mode (`whole`/`excerpts`/`none`) |
| Instructions and memory | new | `orchestrator/project_memory.py` | `ProjectMemory(db, redact)`: `instructions(dept)`, `put_instructions(dept, text, rev)`, `memory(dept)`, `put_memory(dept, entries, rev)`, `add_entry(...)`, `record_run_end(tx, task)`, `record_chat_archive(tx, session)`, `seed(dept)`, `set_enabled(dept, on)`. Storage in `meta`, like `standing_rules.py` (same `rev` rule, `owner_words.json_meta/save_meta`) |
| Routes | new | `orchestrator/api/project_context.py` (router, wired like `api/teams.py`), `main.py` body-limit path | section 7 |
| Task input path | changed | `orchestrator/tasks.py` (`create`, `_insert`, `_follow_up`, `_deliver`, `deliver_to_department`, `_run_spec`, the start block ~:690, retry :1134), `orchestrator/models.py` (`RunSpec.inputs`), `orchestrator/standing_rules.py` (`compose_framing(..., middle=)`), `library/practice.py` | `deliver_to_department(dept, text, *, scope_id, settings, input_files=())`; `RunSpec.inputs: list[InputFile]` |
| Engine adapter | changed | `engine/views.py` (`_say_files`), `engine/api/commands.py` (`say(..., files=)`), `engine/port.py`/`connectors/engine_port.py` (the `say` signature and the services fake) | `POST /api/say` body gains `files: [{id, name}]` (at most 10); the route checks shape, `commands.say` passes them, the port resolves them to refs |
| Run materialiser | new | `orchestrator/project_context.py` `materialize(run_dir, project_files, attached, store)` called from the start block of `tasks.py` | copies into `<run>/inputs/knowledge/` and `<run>/inputs/attached/` (0600); a text or Word file also gets `<name>.txt`; failure raises and the existing start-failure path rolls the run folder back |
| Chat grounding | changed | `orchestrator/chat_ground.py` (`ground(services, sid, *, ask, message="")` gains the project block), `orchestrator/api/chat_v2.py` (`_ground`, `direct`, `_start_live`) | grounding order: record, owner notes, folder, **project block**, rules |
| Per-turn excerpts | changed | `connectors/chat_models.py` (`ChatTurnIn.context: str = ""`), `connectors/chat_port.py` (`_message` appends it after the attachments text; `set_system(sid, text, *, context_sig="")`), `connectors/router.py` (session state `context_sig`, `moved` rule for Codex) | the 202 body gains `context` (receipt) |
| Memory writers | changed | `orchestrator/projector.py` `mark_ended` (call inside its transaction), `orchestrator/chat_v2.py` `ChatArchive.archive` | one append each, same transaction as the state change |
| Org request files (phase B) | changed | `orchestrator/models.py` `ChatPost.files`, `orchestrator/agent/runner.py` (`_store_user_line` keeps ids in `meta`; the planner prompt gets the manifest and openings; each task it makes gets `input_files`) | section 7 |
| Shared chip controller | new (extracted) | `ui/static/js/attach_bar.js` | `AttachBar.create({api, url, readFile, onChange, limits})` -> `state()`, `addFiles`, `take`, `removeFile`, `refs()`, `ready()`, `blocked()` (sentence or ""), `html()`; `chat_composer.js` uses it, behaviour and its tests unchanged |
| Start box and follow-up | changed | `ui/pages/j2_ui.html` (recorded edit E30: a button, a chips row, `sendText(text, usd, files)`), `ui/static/js/start_files.js` (mounts the bar on `lform` and `sform`, like `budget_chip.js` mounts on `lbudget`), `ui/static/css/sutra-panel.css` | `StartFiles.mount(el, {dept, api}) -> {refs(), reset(), blocked()}` |
| Attention and composer | changed | `ui/static/js/home.js` (:272, :664-676), `ui/static/js/node_panel.js` (:1360), `ui/static/js/chat_composer.js` (`TEAM_FILES` removed; "Add to project" on chips and receipts) | the team send carries `files` |
| Project panel | new | `ui/static/js/project_context_view.js`, menu entry in `project_pick.js`, chip under the start box | pure `filesHtml`, `instructionsHtml`, `memoryHtml`, `previewHtml`; one controller with the api |
| Create project | changed | `ui/static/js/create_project.js` | a "Project files" drop area; after `POST /api/teams` returns, each file uploads to `POST /api/teams/{dept}/files`; a failure keeps the project and lists the failed files |
| Page type list | changed | `ui/static/js/chat_search.js` | unchanged (reads the server list); one more consumer |

## 5. Data model
### 5.1 Migration v10 (DDL only; no data work, so a rollback that keeps the DDL is harmless, D426 rule)
```
CREATE TABLE project_files (
  id TEXT PRIMARY KEY,                                   -- "pf_" + 12 hex
  dept_id TEXT NOT NULL,                                 -- the project (a team); no FK: rows outlive a hidden team (DL5), like work_tags
  sha TEXT NOT NULL CHECK (length(sha) = 64),            -- the AttachmentStore id; bytes are not here
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  kind TEXT NOT NULL CHECK (kind IN ('text','image','pdf')),
  size INTEGER NOT NULL CHECK (size >= 0),
  chars INTEGER NOT NULL DEFAULT 0,                      -- characters of extracted text (0 for image and pdf)
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  added_at INTEGER NOT NULL, removed_at INTEGER)         -- a remove sets removed_at (so the row can be audited), the bytes are released when unreferenced
CREATE UNIQUE INDEX project_files_live ON project_files(dept_id, sha) WHERE removed_at IS NULL
CREATE INDEX project_files_dept ON project_files(dept_id, removed_at)
ALTER TABLE tasks ADD COLUMN input_files_json TEXT NOT NULL DEFAULT '[]'    -- [{id: sha, name, kind, size, chars}] of the files given with this request
```
`SCHEMA_VERSION` becomes 10. `TABLES` gains `project_files`. A task row read by older code simply ignores the column.

### 5.2 Documents in `meta` (no migration)
| Key | Body | Notes |
|---|---|---|
| `pinstr:<dept>` | `{text (<= 4000), rev, updated_at}` | refused: a secret shape (the owner-notes check). `rev` is a hash of the text; a save names the `rev` it read |
| `pmem:<dept>` | `{enabled: bool, seeded: bool, rev, entries: [{n, text (<= 300), source: "run"|"chat"|"owner"|"history", at, ref, on: bool}]}` | at most 30 entries; a 31st append drops the oldest auto entry (never an owner entry; with 30 owner entries the append is skipped and counted); `ref` is a task id or session id |

### 5.3 Where each byte lives
| What | Where | Removed when |
|---|---|---|
| File bytes | `<data>/attachments/<sha>.<ext>` (D440) | `ProjectFiles.remove` and no other `project_files` row, task snapshot, or chat line meta names the sha |
| File list and flags | `project_files` | soft remove sets `removed_at` |
| A run's copies | `<run>/inputs/knowledge/`, `<run>/inputs/attached/` | with the run folder (`prune` leaves them; they are not in its list) |
| Instructions, memory | `meta` | edit or delete; "Remove all files" does not touch them |

### 5.4 Backward compatibility and migration of existing projects
| Concern | Behaviour |
|---|---|
| Existing projects | v10 adds an empty table and an empty column; with no file, no instructions and memory off the prompts are byte-equal (NFR-1, golden) |
| Memory for old projects | seeded lazily on the first read or first delivery (`seeded` flag), not in the migration: its last 10 finished runs (request first 120 characters + outcome sentence) and last 5 archived chats (first owner line + last reply), `source: "history"`, in time order, all editable. Lazy seeding keeps the migration DDL-only and rollback-safe |
| Memory default | On for a project with history (the owner asked for context to be kept); the Project panel shows it and the switch. A project with no history starts with it on and empty |
| Old tasks | `input_files_json = '[]'` |
| D440 chat lines | unchanged; their files stay chat-scoped; "Add to project" is available from their receipts |
| Older app on a newer database | refused, as at v9 (`db.migrate`) |

## 6. Delivery rules and budgets
### 6.1 Budgets (constants in `project_context.py`, served by `GET /api/teams/{dept}/files`)
| Part | Run framing | Chat turn |
|---|---|---|
| Instructions | 2,500 | 4,000 |
| Memory ("Earlier in this project", newest enabled entries first) | 1,500 | 3,000 |
| Knowledge manifest (every enabled file: name, kind, size, characters, "reference only" for image and PDF) | in the digest | 3,000 |
| Knowledge content | digest 4,000 (opening of each text file, 800 characters, whole when it fits) and the files themselves in `inputs/knowledge/` | whole up to 20,000 in the system text, else excerpts up to 20,000 in the turn |
| Per-request attached files | 6,000 (opening of each, 1,500 characters) and the files in `inputs/attached/` | D440 inline, 40,000 a file |
| Project block total | 8,000 | 30,000 |

Cut order when over: knowledge, then memory, then instructions; every cut ends in a sentence ("[cut: showing the first N of M characters; the rest is in inputs/knowledge/name]" for a run, "[N of M files shown for this message]" for a chat). The brief (`framing`) keeps at least 2,000 characters; the rules block is never cut (existing behaviour); if rules plus project block would leave the brief less, the project block shrinks further in the same order.

### 6.2 Team run
```
framing = rules block                      (unchanged)
        + "From the owner, for this project:" instructions            (if any)
        + "Earlier in this project (data):" memory entries            (if memory on)
        + "Project files (data; opened in inputs/knowledge/):" digest (if any enabled)
        + "Attached to this request (data; in inputs/attached/):" per-request digest
        + chat agent's paragraph / attempts note   (squeezed, as today)
```
Text is fenced and labelled as data with D440's `_fenced`. Word files are read through `docx_text.extract` once, at add time, and the text is kept as `<name>.txt` beside the copy in the run so agents without a Word reader can open it. Images and PDFs are copied and named only.

**Channel risk (confidence moderate).** C4 shows the framing reaches the run as a system chat line and the rules already travel this way, but `standing_rules.py` says J2's prompts do not read it, and J2 summarises older chat. Two protections: the files exist in the run folder for agents with tools (builders have tools live, D245), and T2 is a spike that reads the engine's prompt assembly to say exactly which calls see a chat system line. If the Requester or builders do not, the project block moves into the node-context file that `system_addendum(fn)` (P9) already reads for nodes; that is a host-side change with no J2 patch. The beta check (T17) reads a real run's calls to confirm.

### 6.3 Direct chat
1. `_ground` builds the **stable block** from instructions, memory and the manifest; when the enabled files' text totals at most 20,000 characters it also holds each file whole (fenced). `context_sig = sha256(stable block)`.
2. Over 20,000 characters, `excerpts_for(files, message, 20_000)` ranks 1,500-character chunks by word overlap with the owner's message (lower-cased `[a-z0-9]{3,}` tokens; a chunk scores the count of distinct query tokens it holds, +2 when the token is in the file name; ties by file order then chunk order); an empty or stopword-only message takes each file's opening. The result goes in `ChatTurnIn.context`, appended after the attachment text of the turn only, never stored in the owner's line (the line keeps its text, as D440).
3. Claude is given the system text every turn. Codex reads it at the thread's first turn: `Router._chat_turn` compares `context_sig` with the one saved in the thread's `SessionState` and, when it differs and the provider is Codex, treats the turn as `moved` (new thread with the carry-over, the existing mode rule at `router.py:1100`). A file added mid-chat therefore reaches the next Codex turn; the cost is one re-primed thread per project edit.
4. A project's block is not given to the org chat (no project) or to a function or step chat.

### 6.4 Earlier context
| Event | Entry written (no model; passed through the egress scrub) |
|---|---|
| A run ends `done`, `done_with_open_items` or `stopped` | `"<date>: asked '<request, 120 chars>'. Result: <outcome sentence, 160 chars>"`, `ref` = task id |
| A chat is archived | `"<date>: chat '<first owner line, 120>'. Last: <last team or model line, 160>"`, `ref` = session id; skipped when the chat has no owner line |
| The owner adds one | `source: "owner"`; never dropped by the cap |
| First read of an old project | the seed in 5.4 |

Delivery: newest enabled entries first until 3,000 characters (chat) or 1,500 (run). Entries copy no file content and no reasoning (FR-19). With memory off nothing is read and nothing is appended.

## 7. Interfaces / APIs
All writes need the token (`require_token`); ids in the path match `DEPT_ID_RE`; the body-size guard (`main.py` `_limit_for`) raises its cap for `POST /api/teams/{dept}/attachments` and `POST /api/teams/{dept}/files` as it does for chat attachments (C9). Responses go through the redactor like the other team routes.

| Route | Body -> response | Errors |
|---|---|---|
| `GET /api/teams/{dept}/files` | -> `{files: [{id, name, kind, size, chars, enabled, added_at, reference_only}], totals: {files, bytes, chars}, mode: "whole"\|"excerpts"\|"none", limits}` | 404 unknown project |
| `POST /api/teams/{dept}/files` | `{name, content_b64}` -> 201 `FileOut` (upload straight to the project) | 422 the D440 sentence or a limit sentence; 403 `ReadOnly` for a deleted project; 413 body |
| `POST /api/teams/{dept}/files/promote` | `{attachment_id, name}` -> 200 `FileOut` (a file already stored becomes a project file; `already: true` when present) | 404 `not_found` (no such stored file); 422 limit |
| `PATCH /api/teams/{dept}/files/{fid}` | `{enabled?, name?}` -> 200 `FileOut` | 404, 422 name |
| `DELETE /api/teams/{dept}/files/{fid}`, `DELETE /api/teams/{dept}/files` | -> 204 | 404 |
| `POST /api/teams/{dept}/attachments` | `{name, content_b64}` -> `AttachmentRef` (a per-request file for a start box: stored, not yet in the project) | as `/api/chats/{sid}/attachments` |
| `GET` / `PUT /api/teams/{dept}/instructions` | `{text, rev}` -> `{text, rev, updated_at}` | 422 too long or secret shape; 409 `stale` when `rev` is not current |
| `GET /api/teams/{dept}/memory`, `PUT` (whole list with `rev`), `POST` (one entry), `DELETE /{n}`, `PUT /settings {enabled}` | -> `{enabled, entries, rev}` | 409 `stale`, 422 length or count |
| `GET /api/teams/{dept}/context?message=` | -> `{instructions, memory, files, mode, parts: [{name, chars, cut}], run_block, chat_block, sig}` the exact text a run and a chat would be given now (FR-17) | 404 |
| `POST /api/say?dept=` (engine adapter) | body gains `files: [{id, name}]` (<= 10) -> existing 200 / 409 busy | 400 `files must be a list of {id, name}`; 404 an id not stored; 409 busy as today; nothing stored on any refusal |
| `POST /api/chats/{sid}/direct` | request unchanged -> 202 gains `context: [{name, chars, cut, mode}]` | as D440 |
| `POST /api/chats/cs_org/messages` (phase B) | `ChatPost` gains `files: [{id, name}]` | as above |
| `POST /api/tasks` | `TaskIn` gains `files: list[{id, name}] = []` | as above |

`GET /api/chats/attachment-limits` stays as the one list of types and sizes; `files` in the first response reads it for the types and adds the project limits.

## 8. Key flows
### 8.1 Start box with a file, run reads it
```mermaid
sequenceDiagram
  participant O as Owner
  participant P as start box (E1)
  participant S as server
  participant T as TaskService
  participant R as run folder / engine host
  O->>P: drop spec.docx, type the brief, Go
  P->>S: POST /api/teams/{dept}/attachments (ref)
  S-->>P: ref kind text
  P->>S: POST /api/say?dept= {text, files:[{id,name}]}
  S->>S: resolve ids in the store (404 stops here, nothing stored)
  S->>T: deliver_to_department(..., input_files)
  T->>T: _follow_up -> _insert: tasks.input_files_json
  T-->>P: 200 (receipt in the team chat line meta)
  T->>R: _start: RunSpec(framing = rules + project block + attached digest); copy files to inputs/
  R->>R: host posts "Context from the team lead: ..." ; agents may open inputs/
  O->>P: "Add to project" on the chip
  P->>S: POST /api/teams/{dept}/files/promote
```
### 8.2 Archive a chat, ask in the new one
```mermaid
sequenceDiagram
  participant O as Owner
  participant A as ChatArchive.archive
  participant M as ProjectMemory
  participant D as /direct
  participant G as ground + Router
  O->>A: archive the team chat
  A->>M: record_chat_archive(tx, session): entry (first line, last line)
  A->>A: _replace: fresh active session
  O->>D: "what did we decide about the pricing page?"
  D->>G: ground(sid, message): stable block (instructions, memory, manifest) ; context = excerpts for this message
  G->>G: Codex: context_sig differs -> new thread + carry-over; Claude: system text every turn
  G-->>O: answer uses the entry and the file excerpt; receipt "Using 4 project files (excerpts for this message), memory on"
```

## 9. Cross-cutting
| Area | Decision |
|---|---|
| Errors | One sentence per case (PRD 5.3), raised before anything is stored or started; reuse `InvalidRequestError` -> `AppError("validation")`, `NotFound`, `ReadOnly`, a new `Stale` mapped to 409 (as the rules `rev` refusal) |
| Logging | Names, kinds, sizes, character counts, project id. Never content (extends D440). The egress audit row already counts shapes |
| Security | D440 fence, name blocklist, 0600 files, egress scan with replacement on every block; instructions are labelled "from the owner" and secret-shape refused on save; hashes never reach a prompt or the UI; paths cleaned (`clean_name`); the materialiser writes only inside the run folder, refuses symlink targets and names with `..`; docx read by python-docx only |
| Privacy | PRD 7; `GET /context` is the audit tool |
| Performance | Extraction once at add (chars stored); one query lists a project's files; the run reads at most the budgeted characters; the 50-file, 100 MB, 400,000-character caps bound the worst case |
| Concurrency | Writes in the one transaction; the partial unique index serialises two adds of one file; `rev` guards instructions and memory; memory append inside the end-of-run transaction |
| Config | No new setting; constants in one module and served |
| Feature flag | None for the data and routes (additive). A kill switch for delivery only: `SUTRA_PROJECT_CONTEXT=0` makes `compose_*` return empty and writers append nothing (default on), so a bad release can be neutralised without a database change |
| Accessibility | NFR-7; the chip row is `role="status"`; the panel's controls are buttons |
| Docs | D451, `docs/diagram/decisions.json`, release note |

## 10. Test strategy
Rule from the owner's memory: verify by exercising; a test that cannot fail when the feature is broken is not a check. Every row below fails on 0.8.3 unless marked guard. Each new test is mutation-proved in T17 (revert its fix, see red).

| Test (file) | Level | Fails today because | Covers |
|---|---|---|---|
| `tests/engine/test_say_files.py`: `POST /api/say?dept=` with two stored ids -> task row `input_files_json` lists them; unknown id -> 404 and zero tasks | API, stub engine | body field and column do not exist | FR-2, FR-3 |
| `tests/orchestrator/test_task_inputs.py`: stub run; run folder holds `inputs/attached/spec.docx` and `spec.docx.txt`; `task.json` framing names the file and holds its opening; file removed from store before start -> task `crashed` "could not start: spec.docx" | integration | no materialiser | FR-4 |
| `tests/orchestrator/test_project_files.py`: add, duplicate, 51st file, 100 MB, enable off, rename, remove (bytes released only when unreferenced), promote from a chat attachment, hidden project is read-only, two threads add the same file | unit + sqlite | no store | FR-7, FR-9, NFR-6 |
| `tests/orchestrator/test_project_context_compose.py`: whole under 20,000; ranked excerpts over; empty message; budget never exceeded with oversized inputs; cut sentences; stable `sig`; image and PDF listed not pasted; fence escapes backticks in a file | pure unit | no module | FR-10, FR-11, NFR-3, NFR-4 |
| `tests/orchestrator/test_chat_project_files.py`: team chat, turn 1, add a file, turn 2 on a Codex session; the spy on the connector shows the file in turn 2's input and a new thread; Claude: system text holds it | API, fake CLI | grounding has no project block | FR-8 |
| `tests/orchestrator/test_project_memory.py`: run end -> one entry; archive -> one entry; new chat's input holds it; memory off -> nothing sent, nothing appended; edit, delete; stale `rev` -> 409; seed on a v9 fixture db; secret shape replaced | integration | no memory | FR-13 to FR-19 |
| `tests/orchestrator/test_project_context_golden.py`: no files, no instructions, memory off -> `_run_spec.framing`, `ground()` text and the router's carry-over byte-equal to a stored 0.8.3 sample | golden (guard, passes today) | | NFR-1 |
| `tests/orchestrator/test_run_export_inputs.py`: a finished run with `inputs/` exports no `inputs/` path and the manifest is unchanged | integration (guard) | | FR-12 |
| `tests/contracts/test_contract_route_table` + `tests/fixtures/openapi` update: only additions | contract | new routes | NFR-1 |
| `tests/ui/js/attach_bar.test.js`: chips, failed chip stays, blocked sentence, limits from the server list, drop and paste | JS unit | module does not exist | FR-1 |
| `tests/ui/js/chat_composer.test.js`: existing tests pass unchanged after extraction (T8); team mode no longer refuses; send carries `files` (the old `TEAM_FILES` test is replaced) | JS unit | the refusal exists | FR-2 |
| `tests/ui/js/start_files.test.js`, `create_project.test.js`, `front_door.test.js`: the control is in each page's markup; the submit carries `files`; Go disabled while a chip uploads | JS unit + source pin for `j2_ui.html` (not loadable in node; D440 precedent) | no control | FR-1 |
| `tests/ui/js/project_context_view.test.js`: panel text equals `GET /context` text; empty states; switch, rename, remove, promote calls; standing privacy sentence | JS unit | module does not exist | FR-17, NFR-7, NFR-8 |
| Browser tests (`SUTRA_BROWSER=1`): drag a file on the start box, Go, the chip becomes a receipt | e2e, run by the developer once | | FR-1, FR-5 |
| Beta prerelease checklist (owner, `desktop-runs-published-release` rule: a beta prerelease, never a local build): start a run with a CSV; ask "what is in the file"; archive; ask what was decided; remove the file | manual e2e | | all |

Meta-check (dashboard eval doctrine): for each new test, revert its fix and confirm red; record the table in `implementation.md`, as D440 did.

## 11. Rollout and risk
| Item | Plan |
|---|---|
| Order | Tests first (T1), the riskiest unknown next (T2 channel spike), then data (T3), composition (T4), delivery (T5, T6), routes (T7), then UI (T8 to T12), instructions and memory (T13, T14), org chat (T15), docs and proof (T16, T17) |
| Release | A Sutra Pro minor, 0.9.0 (new schema, new surface), beta prerelease first, promote after the owner's checklist. Versions are bumped in the release commit, not in T1 to T16 (D440 precedent) |
| Rollback | Revert the commits and keep `DDL_V10_PROJECT_FILES` (the table and column are harmless to older code, which cannot open v10 anyway: the D426 rule); `SUTRA_PROJECT_CONTEXT=0` neutralises delivery without a revert |
| R1 | The channel into J2 (6.2) may not reach builders. Mitigation: T2 spike, files in the run folder, fallback to `system_addendum`, beta check of real calls |
| R2 | `j2_ui.html` is a vendored page (E-numbered edits, `scripts/port_j2_ui.py`): a re-port would drop E30. Mitigation: record E30 in the patch list and the port script's edits, a source-pin test fails when it is gone |
| R3 | Codex thread resets after a project edit lose the native thread (carry-over rebuilds it). Accepted: rare, bounded, said in the receipt |
| R4 | Memory entries could surface stale or wrong facts. Mitigation: owner-visible, editable, deletable, a switch, entries are only stored rows |
| R5 | Prompt cost rises for a project with many files. Mitigation: NFR-3 caps, receipt shows what was used, per-file switch |
| R6 | `tasks` is a hot table; `ALTER ... ADD COLUMN` with a default is O(1) in SQLite |
| R7 | Removing the D440 refusal (`TEAM_FILES`) reverses a shipped sentence. Mitigation: replaced test, release note says so |

## 12. Traceability
| Id | Component | Test |
|---|---|---|
| FR-1 | `attach_bar.js`, `start_files.js`, `home.js`, `create_project.js`, composer | attach_bar, start_files, create_project, front_door JS tests |
| FR-2, FR-3 | engine adapter, `deliver_to_department`, `TaskIn`, `ChatPost` | test_say_files; chat_composer.test.js |
| FR-4, FR-5, FR-6 | `tasks.py`, materialiser, receipt | test_task_inputs; retry test; receipt JS test |
| FR-7, FR-9 | `project_files.py`, routes | test_project_files |
| FR-8, FR-10, FR-11 | `project_context.py`, `chat_ground.py`, router `context_sig` | test_project_context_compose, test_chat_project_files |
| FR-12 | materialiser location, export rule | test_run_export_inputs |
| FR-13, FR-14 | `project_memory.py` instructions | test_project_memory |
| FR-15 to FR-19 | `project_memory.py`, `projector.py`, `ChatArchive` | test_project_memory |
| NFR-1 | `compose_*` empty path, additive routes | test_project_context_golden, contract tests |
| NFR-2 | egress scan, no network in stub | compose test, log test |
| NFR-3, NFR-4 | budgets, fence | test_project_context_compose |
| NFR-5, NFR-6 | stored chars, unique index | test_project_files |
| NFR-7, NFR-8 | panel markup | project_context_view.test.js |

## 13. Decisions
Proposed number: **D451**. `docs/DECISIONS.md` on origin/main ends at D450 (D441 to D445 are unused; D446 to D450 are the script-sandbox and output-panel decisions), so the number after D440 is not free; D451 is the next free one. Re-check on merge (the file is the registry; another branch may take it first). Title: "A project keeps its files, instructions and earlier context, and every start box takes files (amends D440)". `docs/diagram/decisions.json` gets the matching entry (`tests/test_diagram_decisions.py`).

| Id | Decision | Reason | Consequence |
|---|---|---|---|
| A1 | Project context is files, instructions and memory per team; a project stays a team (D426) | the owner's model; no new layer | no new concept for the chart |
| A2 | Bytes stay in the D440 store; the list is a table; instructions and memory are `meta` documents | reuse; the repo's own pattern for owner-edited documents | one migration (v10), DDL only |
| A3 | A per-request file belongs to its task; "Add to project" is the owner's act | Claude's separation of chat files and knowledge; avoids silent growth of a project | a snapshot column on `tasks` |
| A4 | Whole when it fits 20,000 characters, else word-match excerpts per message; no embeddings | automatic switch like Claude's, no dependency, testable | recall limits stated; revisit on measured failure |
| A5 | Stable system block plus per-turn excerpts in the user text | Codex reads the system text once; keeps threads | a context change resets a Codex thread once |
| A6 | Memory is code-written entries from stored rows, editable, switchable, previewable | no cost, no drift, verifiable | less fluent than a model summary (OQ-2) |
| A7 | "Tell the team" takes files; D440's `TEAM_FILES` refusal is removed | the owner's report P1 | amends D440 FR-3 |
| A8 | Project files are never written into the project's folder or exported | D428: Sutra's records stay in Sutra | files are visible only in the panel and the run's `inputs/` |
| A9 | Delivery to a run is framing plus run-folder copies; the J2 channel is verified before building on it (T2) | rules already travel this way; honest about the unknown | a possible move to `system_addendum` |
| A10 | Delivery can be switched off with `SUTRA_PROJECT_CONTEXT=0` | cheap, database-free rollback | one more env name in the settings list |

## 14. Open questions (founder-owned; none blocks T1 to T6, OQ-1 blocks T16)
| # | Question | My default if you do not answer |
|---|---|---|
| OQ-1 | The number: take D451 (D441 to D445 are unused gaps, perhaps held by another branch) or another? | D451 |
| OQ-2 | Allow an optional, owner-pressed "Summarise with the model" for memory (one paid call, shown cost, result lands as an editable entry)? | No; deterministic only in this release |
| OQ-3 | Dependencies: PDF text (e.g. a PDF reader library) and Excel/PowerPoint (D440 OQ-3). Until decided, PDFs and images are reference-only and Excel/PowerPoint are refused | No new dependency |
| OQ-4 | Limits: 50 files, 100 MB, 400,000 characters a project. Higher, or lower? | as written |
| OQ-5 | Memory on by default for existing projects (seeded from history), or off until the owner turns it on? | On, visible in the panel with the switch |
| OQ-6 | Files on `POST /api/projects` (the multi-agent project, flag off) and in answers to a team's question: in this release or later? | Later |

## 15. Implementation plan
Branch: feat/project-files-context   Base: main. Each step is one commit, leaves the build green, and names its tests. Impact and effort in the last column (S under half a day, M about a day, L two days or more).

| Step | Do | Files | Tests | Covers | Impact / Effort |
|---|---|---|---|---|---|
| T1 | Write the failing tests of section 10 for the run path, store, compose and memory, each marked with its requirement id; run them red for the stated reasons | `tests/...` listed above | the new tests (red) | all FR | High / M |
| T2 | Spike, no production change: read J2's prompt assembly and the host loop; add a test that records which calls see a chat system line; write the finding in `docs/ai/project-files-context/channel-spike.md`; decide framing-only or `system_addendum` for T5 | `engine/j2.py` (read), `engine/host/loop.py` (read), one characterisation test | the characterisation test | A9, R1 | High / S |
| T3 | Schema v10 and `ProjectFiles` store with limits, duplicate rule, soft remove, byte release, promote, hidden-project guard | `schema.py`, `orchestrator/project_files.py`, `wiring.py` | test_project_files; migration test; `tests/orchestrator/test_schema.py` | FR-7, FR-9, NFR-6 | High / M |
| T4 | `project_context.py` composition: budgets, whole or excerpts, receipts, sig, fence, cut sentences; pure | `orchestrator/project_context.py` | test_project_context_compose | FR-10, FR-11, NFR-3, NFR-4 | High / M |
| T5 | Run path: `files` on `/api/say` (views, commands, port, fake), `TaskIn.files`, `deliver_to_department(input_files)`, `_insert` column, `RunSpec.inputs`, `compose_framing(middle=)`, materialiser in the start block, retry keeps files, export ignores `inputs/`; `SUTRA_PROJECT_CONTEXT` switch | `engine/views.py`, `engine/api/commands.py`, `engine/port.py`, `connectors/engine_port.py`, `tasks.py`, `models.py`, `standing_rules.py`, `library/practice.py`, `api/tasks.py` | test_say_files, test_task_inputs, test_run_export_inputs, golden (run part) | FR-2 to FR-4, FR-6, FR-12 | High / L |
| T6 | Chat path: project block in `ground()`, per-turn excerpts in `ChatTurnIn.context`, `context_sig` in `set_system` and the router's Codex rule, 202 `context` receipt, live path `_start_live` | `chat_ground.py`, `api/chat_v2.py`, `connectors/chat_models.py`, `chat_port.py`, `router.py`, `connectors/transcript.py` | test_chat_project_files, golden (chat part), existing router tests | FR-8, FR-5 | High / L |
| T7 | Routes: files, promote, attachments for a team, context preview; body-limit path; route table and OpenAPI fixtures | `api/project_context.py`, `main.py`, `wiring.py`, `tests/fixtures/openapi/` | route tests, contract tests | FR-7, FR-9, FR-17 | Med / M |
| T8 | Extract `attach_bar.js` from `chat_composer.js` (pure refactor): chips, limits, drop and paste, refs; composer uses it | `ui/static/js/attach_bar.js`, `chat_composer.js`, the pages' script tags | attach_bar.test.js; all existing composer tests unchanged and green | FR-1 | Med / M |
| T9 | Start box and follow-up box: E30 in `j2_ui.html` (button, chips row, `sendText` carries `files`), `start_files.js`, css, E30 recorded in the patch list and the port script | `ui/pages/j2_ui.html`, `start_files.js`, `sutra-panel.css`, `scripts/port_j2_ui.py`, `engine/VENDORED.md` | start_files.test.js, source pin | FR-1, FR-2 | High / M |
| T10 | Attention (picked project) and the composer's team mode: carry `files`, remove `TEAM_FILES`, "Add to project" on chips and receipts | `home.js`, `node_panel.js`, `chat_composer.js`, `chat_view.js` | front_door/chat_composer/chat_view tests (the `TEAM_FILES` test replaced) | FR-1, FR-2, FR-5, FR-7 | High / M |
| T11 | Project panel: Files section, the "Using N files, memory on" line under the start box and composer, menu entry, privacy sentence, limits note | `project_context_view.js`, `project_pick.js`, `start_files.js`, css | project_context_view.test.js | FR-7, FR-9, FR-17, NFR-7, NFR-8 | High / M |
| T12 | Create project box: Project files drop area, upload after create, partial-failure list | `create_project.js`, `team_admin.py` (no change expected) | create_project.test.js | FR-1, FR-7 | Med / S |
| T13 | Instructions: store, `rev`, compose, routes, panel section | `project_memory.py`, `api/project_context.py`, `project_context_view.js` | test_project_memory (instructions part), panel test | FR-13, FR-14 | Med / S |
| T14 | Memory: appenders in `mark_ended` and `ChatArchive.archive`, lazy seed, routes, panel section, switch, scrub | `project_memory.py`, `projector.py`, `chat_v2.py`, `api/project_context.py`, panel | test_project_memory (rest) | FR-15 to FR-19 | High / L |
| T15 | Org chat files (phase B): `ChatPost.files`, line meta, planner prompt gets manifest and openings, each created task gets `input_files`; Attention "Let Sutra choose" control | `models.py`, `agent/runner.py`, `agent/prompts.py`, `home.js` | `tests/orchestrator/test_runner_files.py` | FR-1, FR-2 (E4) | Med / L |
| T16 | Docs: D451 in `docs/DECISIONS.md` and `docs/diagram/decisions.json`, release note, TROUBLESHOOTING lines, `implementation.md` | `docs/` | `tests/test_diagram_decisions.py`, `tests/test_docs.py` | NFR-1 | Med / S |
| T17 | Mutation proof of every new test; shard runs as D440 (`scripts/py -m pytest tests/<dir>`, `node --test`); beta prerelease checklist for the owner; the T2 real-call check | `docs/ai/project-files-context/implementation.md` | all | all | High / M |

Order rationale: T1 proves the gaps. T2 resolves the one unknown that could reshape T5. T3 and T4 are pure and cheap and every later step needs them. T5 and T6 are the two delivery paths and carry the risk; the UI (T8 to T12) lands after the server accepts files, so each UI step has a working endpoint. T13 and T14 are independent of the file UI. T15 is last because it needs the planner path and a second owner decision on its UX.
