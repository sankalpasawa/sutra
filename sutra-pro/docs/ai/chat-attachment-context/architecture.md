# Architecture: A file attached to a chat reaches the model, or the owner is told why not
_Status: Proposed · Date: 2026-11-25 · PRD: ./prd.md · Decision to record: D440 (last one in DECISIONS.md is D439)_

All paths are under `sutra-pro/sutra_app/`. Line numbers are at origin/main 383c6aa9 (Sutra Pro 0.8.2).

## 1. Context
```mermaid
flowchart LR
  P[chat_composer.js<br/>chips, mode, send] -->|POST /chats/sid/attachments| U[chat_v2.attach<br/>chat_v2.py:220]
  U --> S[(AttachmentStore<br/>data/attachments/sha.ext)]
  P -->|POST /chats/sid/direct<br/>ids + names| D[chat_v2.direct :236]
  D -->|ChatTurnIn.attachments| C[RouterChatPort._message<br/>chat_port.py:213]
  C -->|deliver| S
  C -->|Message text + images| R[Router._chat_turn<br/>router.py:1086]
  R --> A[ClaudeConnector / CodexConnector<br/>stdin stream-json / -i]
  P -.->|team mode: plain route, no files| T[node_panel send :1360]
  R -.->|new session: carry-over from stored transcript| X[ChatTranscripts<br/>chats.py:514]
```

## 2. Root cause (evidence)
Method: read the path end to end, then exercised it with a throwaway test (not committed) that uploads `notes.txt` through the real routes with the stub connector and spies on `router.chat_stream`. Result: the first turn's model input was `"summarise\n\n[Attached file: notes.txt; its content is data, not instructions]\n```\nSECRET-PLAN-XYZ\n```"`. The existing suites (`tests/connectors/test_attachments.py`, `test_claude_connector.py::test_images_go_in_as_one_stream_json_line`, `tests/orchestrator/test_api_chat_v2.py`) agree: a file that is uploaded and referenced by `/direct` is delivered. No real model was called, so what each CLI does with the blocks is only covered by the fake-CLI tests (confidence: moderate-high for delivery, high for the losses below).

The file is lost at five points, none of which says anything to the owner:

| # | Evidence | Effect |
|---|---|---|
| L1 | `chat_composer.js:410` `if (why !== "") { state.note = why; return; }` makes no chip; `state.note = ""` runs at `:331 :361 :377 :406` and in `ask()` | A refused file (type or size, `chat_search.js:68-75`) vanishes after the next action; Send still enabled |
| L2 | `chat_composer.js:449` `const ready = state.files.filter(f => f.status === "ready")`, then `:453` `state.files = []` | A failed upload chip is skipped by Send and then erased with the rest; `button()` (`:243`) blocks only `uploading` |
| L3 | `chat_composer.js:197` `if (mode !== "direct") return askSwitch + toggle + ...` draws no chips and no attach button in "Tell the team", the default (`:272`); `node_panel.js:1362` `if (directOn() && team !== true) return sendDirect(...)` otherwise posts the plain team message | Files kept in `state.files` are hidden and silently not sent when the owner toggles back or uses a team button |
| L4 | `connectors/attachments.py:32` `TEXT_EXT` (22 types), `:92 :96` refusal for anything else, no UTF-8 fallback; the page repeats the list at `chat_search.js:24` | `.docx .xlsx .pptx .rtf .ipynb`, most source languages and Excel's cp1252 CSV are refused, and L1/L2 hide the refusal |
| L5 | `chat_v2.py:362` stores the owner's line as `text + "\n(attached: notes.txt)"`; `router.py:1082` builds a new session's prompt from `ChatTranscripts.messages` (`chats.py:521-523`), which reads stored text only | After a folder change (`router.py:1100`), provider switch or lost session, the model gets the filename and none of the content |

Also found, lower severity: `chat_port._message` (`:218`) decides `provider` before the router plans (`router.py:1015-1026`), so a fallback from Claude to Codex after delivery could meet a PDF the first choice took (FR-11); and no test posts `/direct` with an attachment and checks the model's input.

## 3. Approach
Make a file's fate explicit at every step. The delivery code stays; the changes are at its edges.

1. Page: a refused file is a failed chip; failed or uploading chips block Send; the file bar is drawn in both modes; a team send with chips is refused with a sentence. (L1 to L3)
2. Server: `/direct` validates delivery before it stores anything (`deliver` already raises; move it ahead of `_store_user_line`) and returns a `files` receipt. The page draws the receipt under the owner's line. (FR-4, FR-5, FR-10)
3. Types: `.docx` extracted with python-docx (already a dependency), more text extensions, UTF-16/cp1252 decoding; one shared list the page reads from the server (`GET /api/chats/attachment-limits`) instead of a second hand-kept regex. (L4)
4. Memory: the owner's line records the attachment ids in its stored meta (precedent: `mode`, `chats.py:354`); `ChatTranscripts.messages` appends each earlier attachment's fenced text, bounded, when it builds a carry-over. (L5)

## 4. Alternatives considered
| Option | Why not |
|---|---|
| A. Pass the stored file path to the CLI and let the model's Read tool open it | Claude runs with `--tools` narrowed and `--restricted` (`claude.py:511`); a path outside the working folder would need a grant. Codex sandbox is `read-only` on a folder it cannot see. It widens the file boundary for a problem that inlining already solves |
| B. Re-send every earlier attachment on every turn | Cost: up to 400,000 characters per turn, repeated. Claude and Codex keep the thread; only a rebuilt session needs it (L5) |
| C. Keep the sidecar `<data>/attachments/by-line/<sid>.jsonl` instead of a message field | Second source of truth; no migration, but a chat export, delete or restore would not carry it. The repo already stores `mode` in the line's meta |
| D. Only fix the UI (L1 to L3) | Leaves L4 and L5; the owner's next report is "it forgot the file" |
| E. Extract PDF text for Codex | New dependency; PDF layout extraction is a quality risk. Left as a stated non-goal with its sentence |

## 5. Components
| Component | New/changed | Files | Interface |
|---|---|---|---|
| Composer controller | changed | `ui/static/js/chat_composer.js` | `addFiles` makes a failed chip for every refusal; `send()` refuses with a sentence when any chip is failed (FR-2) or mode is team with chips (FR-3); `bar()` draws chips in both modes; `button()` disabled on failed |
| Receipt line | new | `ui/static/js/chat_view.js` (next to `attachedOf` `:86`, `attachedHtml` `:93`) | `receiptHtml(files)`: escaped lines from the `files` array of the stored line meta |
| Team send guard | changed | `ui/static/js/node_panel.js:1360` | `send(value, fromBox, team)` returns the FR-3 sentence when `c.state().files.length > 0` and the route is team |
| Limits endpoint | new | `orchestrator/api/chat_v2.py` | `GET /api/chats/attachment-limits` (no token, like `/api/appearance`): `{max_files, max_bytes, inline_chars, text_ext[], text_names[], binary[]}`; `chat_search.js checkFile` reads it with the current constants as the offline default |
| Store and kinds | changed | `connectors/attachments.py` | `TEXT_EXT` and `TEXT_NAMES` extended; `_BLOCKED_NAMES` (`.env`, `id_rsa*`, `credentials*`, `*.pem`, `*.key`); `save()` accepts `.docx` (kind `text`, ext `.docx`); `_decode(blob) -> str` tries utf-8-sig, UTF-16 with BOM, cp1252 |
| Docx reader | new | `connectors/docx_text.py` | `extract(path) -> str`: paragraphs, tables as tab-separated rows; any exception becomes `InvalidRequestError("<name> could not be read as a Word file")`; output cut at `INLINE_CHARS` by `deliver` |
| Delivery receipt | changed | `connectors/attachments.py` | `Delivery` gains `files: tuple[FileReceipt, ...]` with `FileReceipt(name, kind, sent, chars, cut)`; `deliver` fills it; the prompt text is unchanged for a chat with no file (NFR-2) |
| Delivery before store | changed | `orchestrator/api/chat_v2.py` `direct` (`:236-272`), `_start_live` (`:476`) | `port.preflight(sid, turn) -> tuple[FileReceipt, ...]` is called after the refs are built and before `_store_user_line`; a refusal is the existing 4xx and stores nothing; the 202 body gains `files` |
| Provider decided late | changed | `connectors/chat_port.py:213-220`, `connectors/router.py` chat plan | `_message` takes the provider the router will try first; on a fallback to a provider that cannot take a kind, `deliver` raises with the name (FR-11). `preflight` calls the same code |
| Line meta | changed | `library/chat.py` `ChatMessage` (new optional `attachments: list[{id,name,kind,chars,cut}]`), `orchestrator/chats.py:354`, schema `docs/schemas/chat_message.v1.json` | stored in `meta_json` like `mode`; absent when empty (NFR-2); `_store_user_line` gets it |
| Carry-over with files | changed | `orchestrator/chats.py` `ChatTranscripts.messages` (`:521`), `connectors/transcript.py` | `ChatTranscripts(chats, attachments=store)`; a user line with `attachments` is rendered `text + deliver(...).text`, cut to a per-file share of the carry-over budget (`carry_chars`); a missing stored file renders "(file no longer available: name)" |
| Wiring | changed | `orchestrator/wiring.py:187-188` | pass `attachments.store` to `ChatTranscripts` |

## 6. Data model
| Item | Change | Compatibility |
|---|---|---|
| `chat_messages.meta_json` | optional `attachments` array on owner lines of a direct chat | Old rows have none and render as today; no table migration (same as `mode`) |
| `docs/schemas/chat_message.v1.json` | one optional property | Regenerated by the repo's schema script; a test pins it |
| `<data>/attachments/` | `.docx` files join; same hash naming, 0600 | `path_of` iterates `[*_BINARY.values(), *TEXT_EXT]`: `.docx` goes in `TEXT_EXT` order, or the lookup changes to a glob on `<sha>.*` |
| `/direct` 202 body | adds `files` | Additive |

## 7. Interfaces
```
GET  /api/chats/attachment-limits            -> 200 {max_files, max_bytes, inline_chars, text_ext, text_names, binary}
POST /api/chats/{sid}/attachments            (unchanged) -> AttachmentRef | 422 validation {message: sentence from section 6 of the PRD}
POST /api/chats/{sid}/direct                 (unchanged request)
     -> 202 {message_id, turn, files: [{name, kind, sent: "text|image|pdf", chars, cut}]}
     -> 404 not_found (unknown attachment id)           -> 422 validation (PDF to Codex, naming the file; unreadable docx)
     -> 409 busy (unchanged)                            nothing is stored on any refusal
```
`RouterChatPort.preflight(session_id, turn) -> tuple[FileReceipt, ...]` is the one new port method; `ChatPort` (Protocol) gains it, and the fakes in `tests/connectors/test_fakes.py` follow.

## 8. Key flows
```mermaid
sequenceDiagram
  participant O as Owner
  participant P as Composer
  participant S as Server /direct
  participant M as Router and CLI
  O->>P: drop report.docx
  P->>S: POST attachments
  S-->>P: ref (kind text)
  O->>P: Send "summarise"
  P->>P: any failed or uploading chip? refuse with sentence
  P->>S: POST direct {text, ids, names}
  S->>S: preflight: deliver() for the provider that will run (refuse before storing)
  S->>S: store owner line with meta.attachments
  S-->>P: 202 {files: receipt}
  P->>O: "Read: report.docx (all 4,100 characters)"
  S->>M: Message(text + fenced file, images)
  Note over S,M: later, new session: ChatTranscripts re-reads meta.attachments and appends the fenced text to the carry-over
```

## 9. Cross-cutting
| Area | Decision |
|---|---|
| Errors | One sentence per case (PRD section 6); the refusal is raised before any store or process; nothing is half-sent |
| Logging | Names, kinds and sizes only; never content. The egress audit row already holds bytes and shape counts |
| Security | Blocked name list kept; stored files 0600; file text fenced and labelled data; carry-over uses the same fence and the existing egress scrub (`router.py:1110`). docx is read by python-docx only (no macro execution, no external entity loading); size bounded by the 20 MB limit |
| Performance | docx extraction on `run_blocking` worker; carry-over text bounded by `carry_chars`, no extra model call |
| Concurrency | `preflight` is read-only; the busy claim stays first (`direct_running.begin`) so a refused preflight releases it in the existing `except BaseException` |
| Config | No new setting; limits stay constants, served by the endpoint |
| Privacy | Local only (PRD section 7) |

## 10. Test strategy
Rule from the owner's memory: verify by exercising. The first test below fails on origin/main today; each requirement has one that fails when it is broken.

| Test | Level | Fails today because | FR |
|---|---|---|---|
| `tests/ui/js/chat_composer.test.js`: add `a.exe` then type; a failed chip exists and Send is disabled and posts nothing | JS unit | `:410` makes a note only; `button()` ignores failed | FR-1, FR-2 |
| same file: ready chip, `setMode("team")`, `send` team route refuses with the sentence and chips are drawn | JS unit | `bar()` returns before chips | FR-3 |
| `tests/orchestrator/test_api_chat_v2.py`: `/direct` with a 50,000-char file; the model input (spy on `router.chat_stream`) holds the first 40,000 characters and the response `files[0]` says cut | API with stub | no `files` in the response | FR-4 |
| same: Codex chat with a PDF; 422 names the file; zero owner lines stored | API | the line is stored before delivery runs | FR-10 |
| `tests/connectors/test_attachments.py`: docx fixture (paragraph + table), cp1252 CSV, UTF-16 text, `.env` refused, malformed docx is a sentence | unit | types refused | FR-6 to FR-8 |
| `tests/orchestrator/test_chat_carry_files.py`: turn 1 with `notes.txt`, change folder, turn 2; prompt of turn 2 contains the text; stored file deleted: the "no longer available" line | integration with fake CLI (`FakeCli`) | transcript holds only "(attached: ...)" | FR-9 |
| `tests/connectors/test_chat_port.py`: preferred provider Claude, fallback Codex, PDF: refusal names the file | unit | provider chosen before the router plans | FR-11 |
| `tests/connectors/test_claude_connector.py`: stdin of a Claude turn with a docx-derived text holds the text, argv has no path of the stored file | fake CLI | characterisation (passes today; keeps it true) | FR-12 |
| `tests/orchestrator/test_chat_golden_no_file.py`: a chat with no file gives a byte-equal prompt and stored line | golden | passes today; guards | NFR-2 |
| Schema test: `chat_message.v1.json` equals the model | unit | | FR-13 |
| e2e (manual, owner's review, beta prerelease): the five loss cases from the PRD, per `desktop-runs-published-release` rule, not a local build | e2e | | all |

Meta-check: for each new test, revert its fix and confirm it fails (mutation proof), as in the dashboard eval doctrine.

## 11. Rollout and risk
| Item | Plan |
|---|---|
| Flag | None; every change is a refusal or an addition for a chat that carries a file. A chat without a file is byte-equal (NFR-2) |
| Order | Tests first (T1), page guards (T2-T3), server preflight (T4-T5), types (T6-T7), carry-over (T8-T9), docs (T10) |
| Risks | R1: `ChatMessage` schema change touches the J2 parity goldens (the closed meta set of `library/chat.py`): the new field belongs to Pro's own `ChatMessage`, not `MessageMeta`; verify with the parity tests before T8. R2: refusing a team send with chips may annoy: the sentence offers the one fix. R3: docx extraction memory on a 20 MB file: bound by 20 MB and a text cap, and the work runs on a worker thread |
| Rollback | Revert the commits; stored `attachments` meta is ignored by older code (meta_json is open) |
| Release | A Sutra Pro patch (0.8.3), beta prerelease first, promote after the owner tries the five cases |

## 12. Traceability
| Id | Component | Test |
|---|---|---|
| FR-1, FR-2 | Composer controller | chat_composer.test.js failed chip |
| FR-3 | Composer, node_panel guard | chat_composer.test.js team mode |
| FR-4, FR-5 | Delivery receipt, receiptHtml | test_api_chat_v2 cut; chat_view.test.js receipt |
| FR-6 to FR-8 | Store and kinds, docx reader | test_attachments.py |
| FR-9, FR-13 | Line meta, ChatTranscripts | test_chat_carry_files.py; schema test |
| FR-10, FR-11 | preflight, provider decided late | test_api_chat_v2 PDF to Codex; test_chat_port fallback |
| FR-12 | Store, claude connector | no-content-in-logs test; test_claude_connector |
| NFR-1, NFR-2 | `/direct` response, golden | golden no-file; OpenAPI fixture update (`tests/fixtures/openapi/`) |
| NFR-3 | docx reader | malformed docx test; size bound test |

## 13. Decisions (ADR-style; to be recorded as D440 in docs/DECISIONS.md with the PRD as its Sources)
| Id | Decision | Reason | Consequence |
|---|---|---|---|
| A1 | The fix is at the edges: delivery stays inline text and CLI image blocks | It works (section 2); Option A widens the file boundary | Text over 40,000 characters stays cut, and the cut is now shown |
| A2 | A send either carries every attached file or is refused before anything is stored | The failure was silent partial sends | Owner must remove a bad chip; the sentence says so |
| A3 | Attachment ids live in the owner line's meta (like `mode`) | One store, exports and restores carry it | Schema JSON changes; old rows unaffected |
| A4 | The server publishes the type list; the page reads it | Two hand-kept lists drifted (L4) | One extra GET, offline default kept |
| A5 | Word yes, Excel/PowerPoint/PDF-for-Codex no | python-docx is already shipped; the others need a dependency | Owner decides OQ-3 after this ships |

## 14. Implementation plan
Branch: fix/chat-attachment-context   Base: main. Each step is one commit and leaves the build green. Impact and effort per step in the table.

| Step | Do | Files | Tests | Covers | Impact / Effort |
|---|---|---|---|---|---|
| T1 | Write the failing tests: failed chip, team chips, `/direct` receipt, PDF-to-Codex stores nothing; mark each with the requirement id. Run them: they fail for the stated reasons | tests listed in section 10 | the new tests (red) | FR-1..4, 10 | High / S |
| T2 | Failed chip for every refusal; failed or uploading blocks Send; keep chips until removed | `chat_composer.js` | T1 JS tests green; existing `chat_composer.test.js` | FR-1, FR-2 | High / S |
| T3 | File bar in both modes; team send guard in `node_panel.js` | `chat_composer.js`, `node_panel.js` | team-mode test; node_panel tests | FR-3 | High / S |
| T4 | `Delivery.files` receipt and `preflight` on the port; call it before `_store_user_line` in `direct` and `_start_live`; 202 `files` | `attachments.py`, `chat_port.py`, `chat_v2.py`, `test_fakes.py` | T1 API tests green; OpenAPI fixture regenerated | FR-4, FR-10, NFR-1 | High / M |
| T5 | Provider decided late; fallback refusal names the file | `chat_port.py`, `router.py` | fallback test | FR-11 | Med / M |
| T6 | Receipt line under the owner's message | `chat_view.js`, `chat_composer.js` (store the 202 `files`), css | `chat_view.test.js` | FR-5 | Med / S |
| T7 | Types: extension list, blocked names, decode fallback, `.docx` reader; limits endpoint; page reads it | `attachments.py`, `docx_text.py`, `chat_v2.py`, `chat_search.js` | `test_attachments.py`, `chat_search.test.js` | FR-6..8, NFR-3,4 | High / M |
| T8 | `ChatMessage.attachments` in meta, schema, store; `_store_user_line` writes it; the line's receipt is drawn from it after reload | `library/chat.py`, `chats.py`, `chat_v2.py`, `docs/schemas/chat_message.v1.json` | schema test; parity tests; reload test | FR-13 | Med / M |
| T9 | `ChatTranscripts` appends earlier attachment text to carry-over, bounded | `chats.py`, `transcript.py`, `wiring.py` | `test_chat_carry_files.py` | FR-9 | High / M |
| T10 | No-file golden; no-content-in-logs test; mutation proof of every new test (revert each fix, see red); D440 in `docs/DECISIONS.md` with the diagram label; `TRACEABILITY.md` rows; release note for 0.8.3 | `tests/...`, `docs/DECISIONS.md`, `docs/TRACEABILITY.md`, `docs/release-notes/` | full affected suites only; beta prerelease for the owner's review | NFR-2, FR-12 | Med / S |

Order rationale: T1 first proves the bug; T2 to T4 close the silent paths with the least risk; T7 and T9 change data and types and come after the guards.

## 15. Open questions for the owner
1. Which mode and file type were you using when it failed? The five causes are all real; this tells us which to verify first on a beta build.
2. Word only, or also Excel and PowerPoint (new dependency, separate decision)?
3. Is refusing a team send while files are attached acceptable, or should the files move to the model automatically on send?
