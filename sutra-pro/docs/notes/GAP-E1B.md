# GAP-E1B as built: follow-up after a finished document chain (G15, engine design phase E1-b)

## Built
- `sutra_app/engine/rehydrate.py`: a source with `documents.json` / `stage-*.json` is no longer refused. `_chain()` reads and checks it
  (nothing is written before the checks pass), `_restore_chain()` sets `RESTORED_CHAIN`: docset, stages, stage_i (last index), docs,
  chain (each document's `agent_output`), stage_archive (the `stage-<stage>.json` files in stage order), past_workflows / workflows,
  site_tag, stage_calls0, lld_revisions, the last stage's output (`_apply_output`: doc, out, WF_FMT, GRANT_FMT, ATOM_RULES) and the
  LLD blueprint when the chain ended on the website. Document files named by `documents.json` (`prd.md`, `prd.docx`, ...) are copied.
  `sites` are the last stage's versions (`site/<stage>-vN.md` for a document, `site/vN.html` for the website).
- `sutra_app/engine/j2.py` is NOT edited: the vendored hash recorded in `VENDORED.md` (not owned here) would no longer match. The
  blueprint lines of `_begin_stage` are repeated in `_restore_chain`; the state test compares WF_FMT / GRANT_FMT with a live run.
- Tests: `tests/engine/test_engine_rehydrate_chain.py` (22, about 6 s): state equals the live J2 run after Done (website-ending and
  documents-only chain), change request on the website chain (new `site/v8.html`, documents and old versions kept, no second chain),
  documents-only chain, the host path (`seed_from` -> `Continuing from run <id>` line), every refusal.

## Decisions and deviations
1. The spec says the change request "runs `_turn_change`". `_turn_change` is the J2_CHANGE=1 path for realization websites and is
   skipped for documents (`_change_applies` is False when `doc`/`blueprint`). J2 itself sends a change after Done to Adaptation for the
   last stage; the rehydrated run does the same (checked against the live J2 object). No J2 code was changed for this.
2. "A new version of the affected document": in mock mode the change lands on the last stage. Design-docs scenario: the website, so
   `site/v8.html` is the new version. For a documents-only chain J2's mock Adaptation proposes no workflow, so no new LLD version is
   written (the live J2 run behaves the same); the test asserts exactly that, plus Audit and Done again. A real model writes the version.
   A change to an earlier document (HLD) is J2's board mechanism (J2_BOARD, off by default), not restored.
3. The chat header check (output `website`) does not apply to a chain: the header holds the output of the first message
   (`J2_OUTPUT`), the chain state comes from `summary.json` `design_documents`. A plain single-document run (no `documents.json`)
   is still refused ("built a prd, not a website").
4. A chain is refused (not an error, the host starts fresh) when `summary.json` has no usable `design_documents` (requested, stages),
   `documents.json` is missing, unreadable or lacks a requested document, or a `stage-*.json` is unreadable. Stray chain files on a
   website run are therefore refused with "document chain cannot be read". Unfinished, stopped, crashed and unreadable stay refused.
5. Split of `workflows.json` (J2 saves past + current in one file): past = workflows listed under another document in
   `documents.json` plus send-deed workflows (`deed-send` check); the rest are the last stage's. `info["workflows"]` counts both.
6. `stage_calls0` = the last document's `calls.from - 1` (website: the highest `calls.to`).
7. Existing tests changed in `test_engine_rehydrate.py` (E1): the strict `xfail` test became `test_rehydrate_continues_a_finished_document_chain`
   (passes); `test_a_source_with_a_document_chain_is_refused` became `test_a_stray_document_chain_file_without_a_described_chain_is_refused`
   (new reason text). Nothing weakened.

## Known limits
- Not restored (as for the classic path): intake Q&A (`intake`), message board, template-library state, deed/milestone logs,
  `lld_conflicts` counters, J2_BOARD state. A chain whose last stage is a send deed is restored with the deed as past and an empty
  current stage.
- Proven in mock mode only.

## Follow-ups for other packages
- `docs/design/engine.md` 4.8, F4, ENG-D11 and the E1-b item still say a document chain is refused; the scheduler should update them
  (chassis/design files are not owned here).
