# Implementation: a file attached to a chat reaches the model, or the owner is told why not
_Branch fix/chat-attachment-context · decision D440 · release note docs/release-notes/0.8.3.md · versions not bumped_

## What was built, per loss point
| Loss | Fix | Where |
|---|---|---|
| L1 refused file vanishes | every refusal (type, size, empty, over ten) is a failed chip that stays until removed | `chat_composer.js` `addFiles` |
| L2 failed chip skipped then erased | failed or uploading chip disables Send (reason in the button title and the note); a send never erases a failed chip | `chat_composer.js` `button`, `send` |
| L3 team mode hides and drops files | chips drawn in both modes; a team send with a held file is refused with one sentence (composer, panel, home box) | `chat_composer.js`, `node_panel.js`, `home.js` |
| L4 types refused | `.docx` via python-docx, ~25 more extensions, names Makefile/Dockerfile/README/LICENSE, UTF-16 BOM and cp1252 text, secret-bearing names refused, Excel/PowerPoint refused by name, server list served at `GET /api/chats/attachment-limits` and read by the page | `attachments.py`, `docx_text.py`, `chat_v2.py`, `chat_search.js` |
| L5 rebuilt session forgets the file | the owner's line stores `attachments` in its meta; `ChatTranscripts(chats, attachments=store)` re-reads the text for a carry-over (30,000 characters of file text in all, newest line first) | `records.py`, `models.py`, `chats.py`, `chat_v2.py`, `wiring.py` |
| FR-4/5/10/13 | `RouterChatPort.preflight` runs before the owner's line is stored; the 202 carries `files`; the page draws the receipt from the stored line | `chat_port.py`, `chat_v2.py`, `chat_view.js` |
| FR-11 | a PDF in the turn makes the router plan only PDF-capable providers; no provider left is a sentence naming the file | `router.py`, `chat_port.py` |

## Deviations from architecture.md
1. T8 and T9 are one commit (the two share `chats.py` and the test rig).
2. No `docs/schemas/chat_message.v1.json` exists in this repository, so there is no schema file to regenerate or pin; the record and wire model carry the new optional field.
3. `GET /api/chats/attachment-limits` is `include_in_schema=False`: `tests/fixtures/openapi/chat_routes_before_ask.json` pins the published document byte for byte, and regenerating a fixture named "before ask" was the worse choice.
4. `FileReceipt` has an extra `total` field (the page needs "first 40,000 of 90,000").
5. Provider decided late is done in the router's plan (`PDF_PROVIDERS`), not by moving the decision into `_message`.
6. Added `same_turn` (`connectors/transcript.py`): once a stored user line carries file text in a carry-over, the router's old test "last stored line equals the new message" no longer recognises the current line (it did not on a file turn before either: the stored line ends with "(attached: ...)"), so the file text would have been carried twice.
7. `docs/TRACEABILITY.md` is generated and has not been regenerated since D419; not touched.
8. The node_panel/home guards are pinned by a source test only; those pages are not loadable in node and the browser tests (`SUTRA_BROWSER=1`) were not run.

## Tests added
`tests/ui/js/chat_composer.test.js` (failed chip, failed upload, team bar and send, source pin, limits read once), `chat_view.test.js` (receipt), `chat_search.test.js` (types, setLimits); `tests/connectors/test_attachments.py` (receipts, preflight, PDF late decision, Word, bad Word, zip bound, types, names, Excel/PowerPoint, encodings, limits); `tests/orchestrator/test_api_chat_v2.py` (cut receipt, PDF to Codex stores nothing, limits route, Word end to end, stored receipt); `tests/orchestrator/test_chat_carry_files.py` (lost session carries the text once, no repeat while the session lives, missing file, bounds, newest first, `same_turn`); `tests/orchestrator/test_chat_golden_no_file.py` (a chat with no file is unchanged; file text only in the attachment store).
Five existing JS tests and one Python test encoded the old behaviour (a refusal was a note, the sentence lacked "Word") and were updated, not weakened.

## Mutation proof
The new tests were run against the code of the base commit (aa2922a9, extracted to a scratch folder) with the new test files copied over. Every new test that asserts new behaviour fails there; the guards that are meant to pass today (provider session keeps the thread so no repeat, a no-file chat's prompt) pass on both.

## Known limitations and follow-ups
- Live retry (`/direct/retry`) still sends the words without the files of the first try; the ids are stored now, so it can read them.
- Deleting a chat does not delete its stored files.
- The five cases on a beta prerelease are the owner's review; no real model was called.

## Commands run and results
`scripts/gate.sh` was started and stopped (the whole suite in one process was over an hour); the same tests were run as eleven parallel shards, `scripts/py -m pytest tests/<dir>`, plus every node test file one by one (`node --test tests/ui/js/<file>`, all 0 failures). SUTRA_LIVE and slow suites are skipped by default and were not enabled; no real model was called.
| Shard | Result |
|---|---|
| connectors | 2086 passed, 5 skipped |
| contracts | 142 passed, 1 failed (`test_contract_route_table`: `/api/appearance`; fails the same on the base commit) |
| e2e | 40 passed, 30 skipped |
| engine | 3193 passed, 12 skipped |
| integration | 34 passed |
| library | 2374 passed, 4 skipped |
| ops | 629 passed |
| orchestrator | 3041 passed, 1 skipped, 1 failed (`test_api_live_chat::test_stop_before_the_stream_starts...`: a timing test under eleven-way load; passes alone and in the re-run with its file) |
| release | 658 passed, 8 skipped, 1 failed (`test_workflows_yaml::test_ci_is_named_ci...`: the CI workflow is manual-dispatch only since 0.8.2; same on the base commit) |
| top-level `tests/test_*.py` | 172 passed, 1 skipped |
| ui | 986 passed, 323 skipped, 2 failed (`test_fake_backend::test_the_pages_come_from...` and `test_shared_css::test_each_page_links...`: both name the avatars style added by D439; same on the base commit) |
Node: all 76 files under `tests/ui/js` pass (chat_composer 50, chat_view 78, chat_search 8, chat_composer_live 19, chat_view_workdir 5).
Run in one process in the order orchestrator then library, `test_lib_records::test_all_does_not_freeze_the_registry` failed (the orchestrator tests freeze the registry); the gate's order runs library first and each directory passes alone.
