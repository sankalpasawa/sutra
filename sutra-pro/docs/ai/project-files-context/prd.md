# PRD: Files and earlier context stay with a project
_Status: Proposed · Date: 2026-11-26 · Base: origin/main e59d3ea0 (Sutra Pro 0.8.3) · Architecture: ./architecture.md · Builds on: ../chat-attachment-context/ (D440)_

Words: in the app and in this document a **project** is a team (D426: one project = one team, its chat, its runs, its folder). "Run" is one task of the team. "Chat" is a team's chat session. "Ask the model" is the direct chat (`POST /api/chats/{sid}/direct`); "Tell the team" is the team route (`/api/say`, the org chat's planner, a team chat's plain message).

## 1. Problem
Two reports from the owner, one screenshot (the team start box "What should we make in App Development?": box, "Try:" chips, "$20 budget", Go, "What should we make?", the team's avatars, Decide for me, Recent).

| # | Report | Verified cause (code at 0.8.3) |
|---|---|---|
| P1 | There is no way to give a file when starting work. | Only the direct-chat composer has an attach button (`chat_composer.js`, `node_panel.js`). The start box (`ui/pages/j2_ui.html` `lform` -> `sendText` -> `POST /api/say`), the follow-up box (`sform`), Attention's box (`home.js:664-676` -> `POST /api/chats/cs_org/messages`, or `/api/say?dept=` for a picked project, `home.js:272`) and the Create project box (`create_project.js`) have none. `/api/say` and `ChatPost` have no file field. 0.8.3 made "Tell the team" refuse a held file with "Files go only to the model" (`TEAM_FILES`): honest, but it states the gap. |
| P2 | A project loses what happened in its earlier chats. | (a) Archiving a chat (`chat_v2.ChatArchive._replace`) makes a fresh active session for the team; nothing of the archived one reaches it. (b) "+ New run" sets `page.json.since_run`, and the next run starts with no seed (`tasks._follow_up`, `fresh`). (c) A direct chat's grounding is the node record, three recent task outcomes, the owner's global notes, the folder and the rules, 3,000 characters in all (`chat_ground.GROUND_CHARS`); no chat line but the open question is read. (d) A file lives only in one chat's line meta (`attachments`, D440): no other chat, and no run, can see it. |

What exists today that this builds on (so nothing is rebuilt):

| Exists | Where | Role here |
|---|---|---|
| Content-addressed file store, kinds, limits, fenced delivery, carry-over, receipts | `connectors/attachments.py` (D440) | the only byte store; reused |
| Standing rules per team (always/ask/never lines, practice pack) | `orchestrator/standing_rules.py`, `framing_for` | stay as they are; "Instructions" is a new free-text field beside them |
| The folder's own `CLAUDE.md` / `AGENTS.md` | `connectors/workdir.py` (D125) | stays; shown in the context preview as "from the folder" |
| Owner notes (global, all chats) | `orchestrator/notes.py` | stay global; project memory is per project |
| `upstream/<run id>/` copied into a run plus one chat line | `engine/host/loop.py` `_upstream_line` | the precedent for putting files in front of a run |
| Chat search (FTS5) | `orchestrator/chat_v2.py` `ChatSearch` | unchanged; finds old chats; not memory |

## 2. How Claude's Projects work, and what Sutra takes
Sources: Anthropic help center "What are projects?" (knowledge files, per-project instructions, their own chat histories) and "Retrieval augmented generation (RAG) for projects" (knowledge is read into the context until it nears the window, then a search tool retrieves from it; the switch is automatic and reversible); Anthropic's memory help (memory is kept per project, the owner can view and edit it). The help pages do not state a chat-attachment-to-project rule or a memory size; those rows are Sutra's own choice and are marked.

| Claude Projects | Sutra Pro | Why this way |
|---|---|---|
| Project knowledge: files added once, in every chat of the project | **Project files**: added once to a project, given to every run and every chat of that project | the ask |
| Automatic whole-or-search switch at the context limit | **Whole or excerpts**: all text goes in when it fits a fixed budget, else the best-matching excerpts for this message (word match, no embedding, no model call); the page says which | local-first; no new dependency, no cost; same visible behaviour |
| Project instructions (free text) | **Project instructions**: one free-text field, 4,000 characters, beside the existing standing rules | rules are structured lines with their own revision check; they stay |
| A chat's attachment belongs to that chat | Same: a file attached to a message or a run belongs to it. **"Add to project"** promotes it (Sutra's choice) | Claude's own pages do not say; promotion is the owner's explicit act |
| Per-project memory the owner can view and edit | **Project memory**: a short list of dated entries, newest first, written by code from what happened (run ended, chat archived), editable, deletable, switchable off | no model call by default: cost, privacy, and an entry the owner can verify against the stored row |
| Sharing with a team | Not adopted | Sutra Pro is one owner on one machine |
| Incognito chat | **Memory off** per project (not per chat) | smaller; a per-chat switch is a follow-up |

## 3. Users and goals
| User | Needs |
|---|---|
| The owner starting work | to drop a spec, a brief, a CSV or a Word file on the box where they type, and have the team and the model work from it |
| The owner coming back to a project | the next chat and the next run to know what the project is, what was decided and which files matter, without re-explaining |
| The owner who minds privacy | to see exactly what a project hands to a model, remove it, and know it never leaves the machine except to the chosen model |

Goals: G1 every place work is started takes files; G2 files can be kept at project level; G3 earlier work reaches new chats and runs, bounded, visible, editable; G4 a file is never dropped silently (D440's rule, extended).
Non-goals: see section 8.

## 4. Requirements
Each has a testable acceptance criterion (AC). FR-n are functional, NFR-n are not. "Fails today" means the test exists in architecture.md section 10 and fails on 0.8.3.

### 4.1 Attaching where work starts
| Id | Requirement | AC |
|---|---|---|
| FR-1 | Every entry point in 5.1 shows an attach control, a drop target and chips (uploading, ready, failed with a reason), with the same types and limits as D440 (20 MB a file, 10 a message, the server's list from `GET /api/chats/attachment-limits`). | node test per page module: add a file, a chip appears; drop and paste work; a refused type makes a failed chip that stays until removed |
| FR-2 | "Tell the team" (`/api/say`, the org chat, a team chat's plain message) carries the files. The 0.8.3 refusal `TEAM_FILES` is removed. | API test: `POST /api/say?dept=` with two ids -> the created task lists both ids; the page test no longer expects the refusal; the old test is replaced, not weakened |
| FR-3 | A send is all-or-nothing, as in D440: a failed or uploading chip blocks Send with a sentence; a stored file that is gone, or one that cannot be read, refuses the send before anything is stored or started. | API test: unknown id -> 404 `not_found`, zero tasks, zero chat lines |
| FR-4 | A team run is given its files: each file is copied into the run folder under `inputs/attached/`, and the run's brief says which files, their size and kind, and, for text and Word, the opening of each (budget in architecture 6.2). A run never starts with a file silently missing. | integration test with the stub engine: the run folder holds the files; the `task.json` framing names them; a file removed from the store between send and start fails the task start with the file's name |
| FR-5 | The owner sees what the team and the model received: under the owner's line "Given to the team: notes.txt (all 12,000 characters)", "big.csv (first 8,000 of 90,000 characters, the rest is in inputs/)" or "Sent as an image / kept as a reference file" (receipt, as D440). | JS test on the receipt; API test on the 201/202 body `files` |
| FR-6 | A retry of a run keeps its files; a follow-up run does not repeat the earlier run's attached files (project files still apply). | test: `POST /api/tasks/{id}/retry` -> the new task has the same `input_files`; a follow-up task has none of the earlier task's `start` files |

### 4.2 Project files
| Id | Requirement | AC |
|---|---|---|
| FR-7 | The owner can add files to a project once, from the project's Files panel, the Create project box, or "Add to project" on any attached file or receipt. Types and limits as D440. Limits per project: 50 files, 100 MB in all, 400,000 characters of extracted text in all; over a limit is a sentence naming it. | API tests: 51st file refused with "A project can hold 50 files"; a duplicate (same content) is one row and says "already in the project" |
| FR-8 | Every run and every direct chat of the project is given the project's enabled files (the budget rules in architecture 6). A file added after a chat began reaches that chat's next turn on both providers. | API test: add a file after turn 1 of a Codex chat; turn 2's model input (spy on the connector) holds it; fails today (no such file) |
| FR-9 | Per file the owner can switch "Use in this project" off and on, rename it, and remove it. Remove deletes the row and, when nothing else uses the stored bytes, the bytes. Removing a file used by a run that is running does not touch that run's copy. | API test: remove -> a new run no longer lists it; `AttachmentStore.path_of(sha)` is None when unreferenced, a path when a chat line still references it |
| FR-10 | Whole or excerpts: when the enabled files' text totals at most 20,000 characters every file goes in whole; above that, each message gets the best-matching excerpts up to 20,000 characters, and the manifest line says "excerpts for this message, N of M files". The owner sees which in the Files panel and in the receipt. | unit tests of `select_knowledge` (whole; ranked; stable order; empty message -> opening of each; budget never exceeded) |
| FR-11 | Images and PDFs can be project files too, marked "reference only": they are listed to the model by name, copied into a run's `inputs/knowledge/`, and are not pasted (no text extraction, D440 A5). The Files panel says so on the row. | unit test: manifest lists a PDF with the sentence; no bytes in the prompt |
| FR-12 | Project files are never written into the project's folder, never exported with a run's results (D428), and never listed as a run's deliverable. | test: a finished run with `inputs/` exports no `inputs/` path; manifest unchanged |

### 4.3 Instructions
| Id | Requirement | AC |
|---|---|---|
| FR-13 | One free-text "Project instructions" field (up to 4,000 characters) per project. It goes in front of every run's brief and every direct chat's grounding of that project, after the standing rules, before memory and files. A secret-shaped line is refused when saved (the owner-notes rule). | API tests: PUT stores; a run's framing starts with the rules block then the instructions; a key-shaped string is a 422 |
| FR-14 | Saving carries a `rev`; a stale save is refused, never overwritten (the standing-rules rule). | API test: two saves from one rev -> 409 |

### 4.4 Earlier context
| Id | Requirement | AC |
|---|---|---|
| FR-15 | Project memory is a list of at most 30 entries, each at most 300 characters, newest first, each with date, source (run, chat, owner) and an on/off mark. Code appends an entry when a run ends (done, done with open items, stopped) and when a chat is archived. No model is called. | integration tests: finish a stub run -> one entry with the owner's request (first 120 characters) and the outcome sentence; archive a chat -> one entry with its first owner line and its last team or model line |
| FR-16 | Memory reaches every new chat and run of the project: the newest enabled entries up to 3,000 characters, under "Earlier in this project", labelled data. A new session after an archive, a folder change or a provider switch gets it. | API test: archive a chat, send in the fresh chat; the model input holds the entry; fails today |
| FR-17 | The owner can read, edit, add, delete and disable entries, and turn project memory off. Off means nothing of it is sent and nothing new is appended. What will be sent is previewable: `GET /api/teams/{dept}/context` returns the exact text, sizes and sources. | API tests; JS test that the panel text equals the endpoint text |
| FR-18 | An existing project gets its first entries from its stored history without the owner doing anything: its last 10 finished runs and last 5 archived chats, once, marked "from earlier history", all deletable. | migration test on a database built at v9 with two runs and one archived chat |
| FR-19 | Memory entries never copy file content, model-written reasoning or a secret: only the owner's request line and the outcome sentence, both already stored, passed through the egress scrub. | unit test: an entry made from a line with a key shape has the shape replaced |

### 4.5 Non-functional
| Id | Requirement | AC |
|---|---|---|
| NFR-1 Backward compatible | A project with no files, no instructions and memory off gets prompts byte-equal to 0.8.3 (run framing, chat grounding, carry-over). Routes only gain fields. Database: schema v10 adds one table and one column; an older app refuses the newer database as at v9. | golden tests; OpenAPI fixture regenerated with additions only |
| NFR-2 Privacy | Files, instructions and memory stay on the machine (section 7). Nothing is sent anywhere but the model the owner chose for that chat or run, through the existing egress scan with replacement. | test: no network call in the stub path; egress scan applied to the block; no content in logs |
| NFR-3 Budgets | Prompt cost is bounded: the project block is at most 8,000 characters in a run's framing and 30,000 in a chat turn (architecture 6.1); truncation is always said in the text and in the receipt. | unit tests on the composer with oversized inputs |
| NFR-4 Safety | File text is fenced and labelled data (D440's fence). Secret-bearing names refused as in D440. Instructions are the owner's words and are not fenced; they are labelled "from the owner". | existing fence tests extended to the new block |
| NFR-5 Performance | Project files are read and extracted once at upload (text length stored); a run or turn reads at most the budgeted characters. Listing 50 files is one query. Docx extraction on the worker thread (D440). | unit test: second use of a file does not re-extract (counter) |
| NFR-6 Concurrency | Uploads and edits use the one write transaction; a promote and a remove of the same file cannot both win (unique index plus transaction). | test with two threads |
| NFR-7 Accessibility and plain words | The UI says "project", "files", "memory", never department, node or sha. Controls are real buttons with labels; chips announce failures (`role="status"`). | node tests on markup |
| NFR-8 Honest limits | The panel states: Excel, PowerPoint and PDF text are not read (D440); PDFs and images are reference only. | markup test |

## 5. UX
### 5.1 Entry points
| Entry point | Today | After | Where the file goes |
|---|---|---|---|
| E1 Team start box (the screenshot): `lform` in `j2_ui.html` | text, Try chips, budget, output, Go | a paperclip button on the box's bottom row, left of the "$20 budget" chip; drop and paste on the box; chips under the box; Go disabled while a chip uploads or failed | this run (origin "start"); each chip has "Add to project" |
| E2 Team follow-up box `sform` (after work began) | text | the same paperclip and chips, compact | this run (the follow-up task) |
| E3 Attention box with a project picked (`home.js`, `/api/say?dept=`) | text | same control; the picked project is the target | this run |
| E4 Attention box with "Let Sutra choose" (`cs_org` messages) | text | same control; the line says "Files go to the teams Sutra picks and are read by the planner" | each task the request makes (phase B) |
| E5 Direct chat composer, "Ask the model" | attach exists | unchanged, plus "Add to project" on each chip and receipt; project files are used automatically; a line under the box: "Using 4 project files, memory on" | this message |
| E6 Direct chat composer, "Tell the team" | files refused (0.8.3) | files go with the team message | this run |
| E7 Create project box | name, folder, access | optional "Project files" drop area under the folder field; files upload after the project exists | project files |
| E8 Project Files panel (new) | none | list with name, kind, size, added, "Use in this project" switch, rename, remove; add button and drop target; totals ("12 of 50 files, 3.1 MB"); the whole/excerpts line; sections Instructions and Memory under it | project files |
| E9 Retry, recurring runs, recipes, the org agent's follow-ups | none | no file control; they use project files and memory automatically; retry keeps the run's own files | project files |
| E10 `POST /api/projects` (multi-agent, behind `SUTRA_NODES_V1`, off by default) | none | no per-request file in this release; its steps are tasks of a team, so they are given project files and memory | project files |

The panel is reached from the project name menu on Attention and the team page ("Project files and memory"), and from a chip under the start box: "3 files · memory on" (hidden when there is nothing).

### 5.2 Team run versus ask the model
| | Tell the team (run) | Ask the model (chat) |
|---|---|---|
| Per-message files | copied into the run's `inputs/attached/`; opening of text in the brief; images and PDFs by name | inlined as D440 (text fenced, images as blocks, PDF to Claude) |
| Project files | text in the brief up to 6,000 characters; every file copied into `inputs/knowledge/` | excerpts or whole up to 20,000 characters in the turn's system text; PDF and images by name |
| Instructions, memory | in the brief | in the grounding |
| Who may open a file | the team's agents, from the run folder | the model sees only what was pasted |
| Receipt | under the owner's line in the team chat | under the owner's line, as D440 |

### 5.3 Failure UX
One sentence each; the box keeps the words and the chips; nothing half-sent.

| Case | What the owner sees |
|---|---|
| File type refused | red chip "notes.xlsx: Excel and PowerPoint files cannot be attached. Save it as CSV or PDF, or paste the text." (D440 text); Go waits |
| Over 20 MB / empty / 11th file | chip with the D440 sentence |
| Upload fails (server down) | chip "Could not upload. Remove it or try again" with a Retry on the chip; Go waits |
| Stored file gone when sent | "report.docx is no longer stored. Attach it again." 404; nothing stored |
| Project limit reached | "This project holds 50 files. Remove one to add another." |
| Same file twice | "report.docx is already in this project." (not an error: the existing row is shown) |
| Run could not copy a file at start | the task ends `crashed` with "could not start: <name> could not be copied" (the existing start-failure path, `tasks._launch`) |
| Memory off, file switched off | the context line says what is off: "Using 3 of 5 files; memory off" |
| Instructions saved by another window | "Changed since you opened it. Reload to see the new text." (409) |
| PDF to a Codex chat as a message file | D440's refusal |
| Project deleted (hidden, D426) | files panel read-only; new work already refused ("This project was deleted.") |

## 6. Limits (all in one constants module, served by `GET /api/teams/{dept}/files` so the page and the server cannot drift)
| Limit | Value |
|---|---|
| File size, files per message, types | D440 (20 MB, 10, the served list) |
| Project files | 50; 100 MB; 400,000 characters of extracted text in all |
| Instructions | 4,000 characters |
| Memory | 30 entries of 300 characters; delivered up to 3,000 characters |
| Project block in a run's framing | 8,000 characters (instructions 2,500, memory 1,500, knowledge digest 4,000) |
| Project block in a chat turn | 30,000 characters (instructions 4,000, memory 3,000, manifest 3,000, knowledge 20,000) |
| A run's own attached files in its brief | opening of each text file, 1,500 characters, 6,000 in all; the rest in `inputs/attached/` |
| Carry-over of earlier message files | D440 (30,000 characters) |

The run framing limit is 20,000 characters (`RunSpec.framing`) and the rules block is never cut (`compose_framing`): the project block fits in what is left and is cut by its own parts, in reverse order of importance (knowledge digest, memory, instructions), each cut said.

## 7. Privacy
1. Local only. Bytes live under `<data>/attachments/` (0600, D440), never in a project folder, never in an export, never in a log; instructions and memory live in the database. Nothing is uploaded to any Sutra or third-party service.
2. The one outbound path is the model the owner picked for the chat or the run, the same path every prompt takes; the block goes through the egress scan with replacement (credential shapes) like every other prompt text.
3. The owner can see everything that will be sent (`/context` preview), switch a file or memory off, delete any entry or file, and remove a project's files in one action ("Remove all files").
4. Removing a file deletes the bytes when nothing else uses them (FR-9). Deleting (hiding) a project keeps its rows and files, as D426 keeps its runs (DL5); "Remove all files" is the way to clear them.
5. Names that usually hold secrets are refused as in D440 (`.env`, keys, `credentials*`).
6. The panel carries one standing sentence: "Files you add are sent to the model you choose (Claude or Codex) when a chat or run uses them."

## 8. Non-goals (each with its reason)
| Not now | Reason |
|---|---|
| Embeddings or a vector store | a new dependency and a model or a download; word match meets the target and is testable. Revisit if retrieval recall fails the 50-item fixture (docs/design/memory-evaluation.md) |
| A model-written project summary | costs money and can drift from the record; entries are built from stored rows and are editable. Offered as an owner decision (OQ-2) |
| PDF text, Excel, PowerPoint | each needs a dependency (D440 A5); PDF and images are reference-only meanwhile |
| Sharing a project with other people | single-owner product |
| Per-request files on `POST /api/projects` | behind a flag that is off; its steps get project files anyway |
| Files in an answer to a team's question (needs-you card) | the answer path is a different route; the owner can add the file to the project first |
| Deleting a chat deletes its files | still a known limit of D440; the orphan sweep is a follow-up |
| Cross-project memory | memory is per project; the owner's global notes remain the cross-project place |
| A per-chat "don't remember" switch | follow-up; the project switch covers privacy now |

## 9. Success measures
| Measure | Target |
|---|---|
| The two reports reproduce no more | on a beta prerelease: attach a CSV on the start box, run, see it read; archive the chat, ask in the new one "what did we decide", the answer uses the entry |
| Silent drops | 0: every file is in a receipt or a sentence |
| Prompt growth for a project with nothing added | 0 bytes (NFR-1 golden) |
| Prompt growth with 12 files and a full memory | at most 30,000 characters a chat turn, 8,000 a run framing |

## 10. Open questions the owner owns
See architecture.md section 14. None blocks T1 to T6; OQ-1 (number) blocks T16.
