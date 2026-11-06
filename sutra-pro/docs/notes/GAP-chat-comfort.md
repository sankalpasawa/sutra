# GAP-chat-comfort as built: drafts and a growing box, a reader who is never pulled down, a calm Stop with Retry, paste and drop with a record

Four verified gaps of the old Sutra's chat, built once each (the Esc rider and the Stop work share the panel's keydown path and were built one after the other).
Built: `ui/static/js/chat_draft.js` (`ChatDraft`), `ui/static/js/chat_scroll.js` (`ChatScroll`), `orchestrator/direct_turns.py`; riders in `node_panel.js`, `home.js`
(chat area only), `chat_composer.js`, `chat_view.js` (two small branches), `orchestrator/api/chat_v2.py` (`DirectIn.names`, `_store_user_line`, `_post_all`, `_answer`),
`orchestrator/chats.py` (`_turn_of`, one regex), `css/sutra-panel.css`, `css/sutra-shell.css`, `pages/home.html` (two script tags and `#sjump`), `dept_ext.js` (two names in
the injected list). No J2 file, prompt, route or golden is touched; `j2.css` is not edited (its `textarea{height:56px}` is overridden by specificity and the inline height).

## 1. The message box keeps what was written, and grows with it
- `ChatDraft.create({storage, now})`: `load / save / clear / clearIf / prune`, key `sutra:draft:<sid>`, value `{t, at}`; text only, at most 8 000 characters (the direct
  route's cap), at most 30 chats (newest kept), dropped after 14 days, a blank draft is never written, a chat id that is not a session id is refused, every storage call
  in try/catch (a private window or a full storage keeps no draft and never throws). Nothing is ever sent anywhere.
- `ChatDraft.grow(el, maxPx)`: measure at auto, set the px height from the CSS `min-height:56px` up to 200 px, `overflow-y:auto` only above the ceiling. The Send
  button keeps 56 px at the bottom of the row (`align-items:flex-end`).
- Node panel: the box shows the draft of the chat on show (`syncDraft` in `paintComposer`, so a division lens switching to the whole team, an archived view and a
  read-only state each get the right box); every `input` saves; an option appended by `pickOption` saves; `close()` and `switchTab()` save; only an accepted send
  clears it (`clearIf(sid, sent text)`, also when the panel was closed while the send travelled; a box the owner kept typing in keeps its newer words).
- Esc order in the panel: a running direct answer is stopped first; otherwise the panel closes with the draft already saved. Home: Esc in `#sbox` stops a running
  direct answer (when the panel is not open).
- The composer controller is kept per session (`composers` map in the mount): closing the panel no longer drops the mode, the uploaded files or a running turn, so
  Stop is there after reopening. `ChatComposer.rejoin()` restarts the streaming row's text (pieces streamed while the panel was closed cannot be recovered; the stored
  reply has all of it).
- Home: `#sbox` is restored at boot, saved on input, cleared by an accepted send (team route and direct route).

## 2. Reading older messages is never interrupted
- `ChatScroll`: `intent` (the old parking: a wheel-up, a finger, PageUp / ArrowUp / Home inside the transcript, or a scroll that moved up parks; within 24 px of the
  bottom follows again), `plan` (own send -> bottom; nothing changed -> keep; parked or not at the bottom -> keep with the count; else bottom), `settle`, `newCount`
  (messages with a numeric id above the last one seen; a local unsent line is not counted), `pillHtml` (`1 new message below` / `N new messages below`,
  `data-act="jump-latest"`, digits and fixed words only), `watch` (the listeners), `pin` (ResizeObserver: a follower stays at the bottom when the box or a row under
  the transcript changes size), `behavior` (instant under prefers-reduced-motion), `remember` / `restore` (a Map of at most 50 chats; a place above the bottom is
  restored clamped to the new height; a place at the bottom opens at the bottom; used once).
- Home `renderChat` no longer sets `scrollTop = scrollHeight` on every paint: it follows the plan; the owner's own line (`S.own`, set by `send`, `sendDirect`,
  `retryDirect`) still goes to the bottom. The pill is `#sjump` (`.cjump`, zero height, sticky on the transcript's bottom edge); a click goes to the newest line.
- Node panel `paintMessages` follows the same plan; `open()` and a tab switch restore the remembered place (`st.reopen`), `close()` and leaving the Chat tab remember it;
  `reconcileTurn` no longer forces the bottom for a parked reader. `refreshMessages` no longer resets `st.stick`, so the owner's own send always reaches the bottom
  (before, a fresh message in the same refetch cancelled it and only the 48 px rule applied).
- `keepFollowing()` (panel: end of `paintComposer`, `paintBar`, `paintPill`; Home: end of `renderBar`, `renderComposer`): a follower is pinned again when a row under the
  transcript changes size. Found on the way: in the headless test Chrome the page is `hidden`, so ResizeObserver and requestAnimationFrame never fire there; the
  explicit calls make the behaviour the same in tests and in a page that renders.

## 3. A stopped or failed direct answer keeps what was written
- `orchestrator/direct_turns.py` (values in, values out): `finished` (a switch note "Switched Claude to Codex; carried 40 messages", the same words as
  `ChatPill.switchNotice`, then the reply), `stopped` (the kept reply and the note "Stopped. What was written is kept."; with nothing written, one note "Stopped before
  the model wrote anything."), `failed` (the kept reply and the error line with the real reason). `Ending` is a closed Value model.
- `chat_v2._answer` accumulates what was streamed (`shown`, redacted exactly as it was sent), maps `CallCancelledError` to `stopped` (never an error), any other failure
  to `failed`, and stores every message of one ending in ONE transaction (`_post_all`), so a page never reads half an ending. src_refs: `direct:<id>` for the reply (or
  the only message), `direct-note:`, `direct-error:`, `direct-switch:` for the others (`ChatStore.post` refuses a repeated src_ref); `chats._turn_of` reads the owner's line
  back from all four, so `ChatComposer.reconcile` ends the turn on any of them and the page finds the line to retry. Notes and errors are not carried over to the next
  model (`ChatTranscripts` takes text and questions); a kept partial reply is, because the model wrote it.
- `chat_view.js`: a direct error (`kind error` with `turn`) of the owner's newest line in a writable live chat has `Retry` (`data-act="retry-direct" data-turn`); a team
  error, an older failure, a read-only or archived chat has none. The stop note is the existing calm `.nmsg.note`.
- `ChatComposer.retry(lineId, text, {files})`: the same words once, on the model whatever the mode (a second press while it answers is refused); with the same files
  when this page sent them (kept in memory per line id), else text only and the note "Sent again without its files: attach them again to include them."
- `docs/notes/ABS-15.md` said "the switch notice is still not shown on a page": it is now stored in the transcript where the switch happened.

## 4. Paste a screenshot, drop a file, see a thumbnail, and see afterwards what was attached
- `ChatComposer.filesOf(clipboardData | dataTransfer)` -> files or null (null: a text paste or a text drop happens as before); `hasFiles` for `dragover`;
  `take(transfer, {pasted})` attaches (in team mode the box switches to the model, note "Files go only to the model, so this message now asks the model directly.").
  A pasted `image.png` (or a nameless image) becomes `pasted-image-<n>.<ext>`, so two pastes differ. An image chip shows its thumbnail (`URL.createObjectURL`, only a
  `blob:` URL is ever drawn, revoked on Remove and on Send); a PDF or text file shows a tile (`PDF`, `TXT`). The 11th file is refused with the existing note.
- `DirectIn.names` (optional, at most 10, each at most 200 characters): the owner's names of the files, in order. The server cannot know them otherwise, because
  the attachment store is content-addressed (`<sha256>.<ext>`). `_store_user_line` appends a last line `(attached: a.png, b.pdf)` built from the validated refs
  (names cleaned with the store's rule; without names, what each file is: "an image", "a PDF", "a text file"), passed through the same redaction and egress scan;
  the model still gets `body.text` and the files exactly as before. History, search and carry-over see the names.
- `ChatView.attachedOf(text)` splits that line off; the owner's bubble shows the words and the names as chips (`.cattached`). Node panel: `paste` on the box, `dragover`
  and `drop` on the composer. Home: `paste` on `#sbox`, `dragover` and `drop` on `#scompose`.

## Deviations from the suggested packages
- The first message of a turn does not always carry `direct:<id>`: with a provider switch the note is stored first (where the switch happened) as `direct-switch:<id>`
  and the reply keeps `direct:<id>`. This is safe because `_turn_of` reads all four refs and all of a turn's messages are stored in one transaction.
- The attachment record uses names the page sends (`DirectIn.names`) instead of `attachments.path_of` (which returns hash names). The existing composer test that
  pinned the `/direct` body gained `names` (an intended contract change, nothing weakened).
- Drafts are restored per session id, not per node; the scroll memory is per page (in memory), as in the old app.
- `tests/ui/test_view_panel.py::test_a_refusal_from_the_server_hides_the_box_or_closes_it_or_says_the_chat_is_gone` reopened the same chat and typed into what used
  to be an empty box; it now asserts that the refused words came back (the new behaviour) and empties the box before typing the next line.

## Tests
- `tests/ui/js/chat_draft.test.js` (9): per-sid isolation, reload, blank never written, clearIf, over-cap, TTL and the 30-chat cap, a storage that throws or is full,
  a hostile sid, grow.
- `tests/ui/js/chat_scroll.test.js` (13): blocks 1a-1f of the old `test_chat_chrome.js` re-expressed, the plan, the count, the pill words, reduced motion, remember and
  restore (clamped, used once, bounded), pin.
- `tests/ui/js/chat_composer.test.js` (+9, 25 in all): text paste is null, a paste attaches once with its own name and a thumbnail, only blob: thumbnails and tiles,
  revoked on remove and send, the 11th file, the team-mode switch, Retry once, Retry with and without known files, rejoin.
- `tests/ui/js/chat_view.test.js` (+4, 69 in all): the calm stop, Retry only on a direct error of the newest line, hostile text escaped, the attached chips.
- `tests/orchestrator/test_direct_turn_endings.py` (17): a fake ChatPort that yields partials then raises CallCancelledError, CrashedError, RuntimeError, or ends with
  `switched`; the stored sequence and src_refs; the replay ring holds no partial; the switch words; the attached line; the route stores the names and the model gets the
  words unchanged; `_turn_of` for every ref.
- Real Chrome (opt-in, `SUTRA_BROWSER=1`): `tests/ui/test_view_panel.py` +4 (draft through Esc, tab switch, reload and a refused send; the box grows; parking and the
  pill; own send to the bottom and the reopened place), `tests/ui/test_home.py` +2 (Home keeps the reader's place and counts; the draft across a reload),
  `tests/e2e/test_browser_chat_composer.py` extended (the attached record and chip, Stop is a note and no error, a pasted screenshot on Home switches the mode, shows its
  thumbnail and is recorded).

## Found, not mine, left as it is
- `tests/ui/fake_backend.py` has no `GET /api/chats/{sid}/providers` (ABS-9's pill), so most opt-in Home browser tests fail on the 404 at teardown, and two fail on the
  rail's "Usage and log" link (GAP-CONSOLE) that their lists predate. The two new Home tests announce that 404 (`expect_failed`) so they test only what they are about.

## Not done, and why
- No typed `attachment` ChatBlock (a record migration in the closed library schema) and no thumbnail after send (Pro has no route that serves an attachment): names
  and kind tiles are the record.
- Retry after a reload sends the words only (the page no longer knows the file ids; the note says so).
- Focus and caret restored across a rebuild (the old `_focusedInputSelector`): Pro rebuilds the box only on open and on a tab switch, both the owner's own action.
- Windowing a very long chat (the old 60-turn window) stays for later, as the area note of the gap says.
- The staged org path (Plan with Sutra) has no stop or switch note: only the direct turn was in the gap.
