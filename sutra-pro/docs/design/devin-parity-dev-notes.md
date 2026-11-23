# Devin parity: developer notes (DV-1 and later)

What the builder found and decided while building a package of `docs/design/devin-parity.md` (the owner's spec; it is not on `main` yet, so this file does not link to it). One section per package.
Everything here is also in the decision log (D350 to D358) where it is a decision; this file holds the deviations, the limits and what was not verified. Paths are relative to `sutra-pro/`.

## DV-1. Ask: cited answers, read only (`SUTRA_ASK_V1`, default 0)

Branch `feat/sutra-pro-devin-ask`. Decisions D350 (the turn), D351 (the check), D352 (flag off), D353 (the card and the draft), and from the review round D354 to D358 (each says which it amends).

### What was built

| Part | Where |
|---|---|
| The checker: marks, path rules, lines, quote, labels | `sutra_app/orchestrator/citations.py` (pure; reads local files only) |
| The mode: route class, the turn, the card, the limits, the limits gate | `sutra_app/orchestrator/ask_mode.py`; `sutra_app/orchestrator/api/chat_v2.py` (`/direct`, `/direct/retry`, the pill's `ask`) |
| The read cap | `sutra_app/connectors/router.py` (`_chat_turn`: a tag with `workspace: read` never gets an editable folder); `ChatTurnIn.allowance` (`connectors/chat_models.py`, `chat_port.py`) |
| The words the model gets | `sutra_app/orchestrator/chat_ground.py` (`ASK_RULES`, `ground(ask=True)`) |
| The card | `sutra_app/orchestrator/models.py` (`AnswerSource`, `AnswerCard`, a member of `ChatCard`); `direct_turns.py` (`CardEnding`, ref `direct-sources:<line>[.N]`); `chats.py` (`_DIRECT_REF` reads it) |
| The page | `ui/static/js/chat_composer.js` (switch, `mode: "ask"`, draft, `fillBox`), `chat_view.js` (`answerCard`, `workDraft`), `home.js` and `node_panel.js` (wiring), `ui/static/css/sutra-panel.css` |
| The flag | `sutra_app/config.py` (`ask_v1`), `docs/ENVIRONMENT.md`, `docs/OPERATIONS.md` section 12 |

No new table, no new route, no new script on any page, no migration.

### Decisions taken, and where they differ from the spec's wording

1. **Decision numbers D350 to D358, not the next free number on `main` (D253).** `origin/feat/sutra-pro-agent-nodes` already holds D253 to D345 and is still adding (it was at D331 when this package started and at D345 when it was pushed), so D253 would have collided the day both land. DV-1 therefore takes a small block of its own above what that branch has used; the numbers between D252 and D350 are simply not on `main` until the nodes branch lands. `tests/test_diagram_decisions.py` and the traceability generator only need the log and `decisions.json` to agree, which they do. If the nodes branch grows past D349 before either lands, whoever lands second renumbers: nine headings, nine `decisions.json` entries, and the mentions of "D350 to D358" (`config.py`, `ask_mode.py`, `ENVIRONMENT.md`, `OPERATIONS.md`, this file, four tests), then `scripts/py scripts/build_traceability.py`.
2. **`mode` is a field of the body that the route class takes out, not a field of `DirectIn`.** The spec says "`mode=ask`" and "refused or ignored exactly as today when the flag is off". Today a body that names an unknown field is a 422 `extra_forbidden` (the request models are closed), so the way to keep today's bytes is to leave the models alone and to take `mode` out of the body only when the flag is on (`ask_mode.AskRoute`). Consequence: `mode` is not listed in the OpenAPI document of the two routes (the request schemas are what they were). A query parameter would have been ignored by a flag-off server, which would answer an Ask as an ordinary chat; that is why it was not used.
3. **The mode of an Ask is stored with the owner's line, and a Retry can only narrow it** (D354; the first version left it to the page, review M2). A sibling key `mode` in the line's `meta_json` (no new table, no new column); the wire shows `mode: "ask"` only on such a line. A Retry of an Ask is an Ask whatever the body says; a body `do` for it is refused; a body `ask` for a Do line narrows it. The page passes the line's own mode to Retry.
4. **The limits of a function's question reach a chat turn as a gate before each model process, and for Claude also as a cap inside it** (D356, review M4). Calls (2) and the deadline (120 s, which also shortens the turn's timeout) hold for both providers, and the second round after a lost provider session goes through the same gate (a test proves it; the review's "third process" does not happen). $0.25 is `--max-budget-usd` for Claude (the remaining budget of the turn); Codex has no such flag, so for it the dollars are a check before each process and the code, the decisions and the owner's note say so.
5. **No instruction is added to the owner's line; a Codex thread is one mode** (D355, review M3). The Ask words go in the system text (`ASK_RULES`, last in the grounding). Claude is given that text on every turn. Codex reads it on a thread's first turn only, so a turn of the other mode starts a new Codex thread with the carry-over (`session.json` keeps `thread_mode` only for a thread an Ask started): the Ask words never reach a Do turn and always reach an Ask turn, tested in both orders. Claude keeps its thread. An Ask with no folder is read only on Codex too (`read_only`, review m3).
6. **A stopped or failed Ask has no card.** The kept partial text may contain marks; they are shown as the text the model wrote, without a label. A card on a half answer would say "checked" about words the owner was told were cut.
7. **The monthly limit and plan window do not hold an Ask back** (D356, review m9; the first version refused an Ask with a 409 while a plain chat still worked). Offline (the stub) an Ask runs and its card says "no sources given".
8. **What a mark may be.** `[path:12-18]`, `[path:12]`, `[path:12-18 "words"]` (also an en dash and curly quotes). Marks inside a fenced code block are examples and are skipped; marks in inline code count. At most 30 marks are checked (`more` counts the rest). A path with a backslash, a colon (so `C:x` and `file:stream`), a drive letter, a leading `//` (UNC), `~`, a control character or a character a path never needs is refused from its text alone BEFORE any file-system call (D357, review M1: on Windows `realpath` of a UNC path connects to the host); so are a trailing dot or space and a device name (`CON`, `NUL`, `COM1`, ...). An absolute path (one `/`) is compared with the folder as text first; on Windows only relative marks are accepted. All of it is refused the same on every machine, so a result does not depend on the platform the test ran on. Only text with the shape of a citation is a mark that is checked: a `/` in the path or an extension that starts with a letter, or a bare name that is a file in the folder, so `x[0:5]` and `[12:30]` do not become sources that "could not be found" (review m6). A file larger than 4 MB, not text (a NUL in the first 8 KB) or a range wider than 400 lines is "could not find" with the reason. Quotes under 4 characters prove nothing and are not used (the lines are checked and the card says so); over 300 characters are refused.
9. **`GET /api/config` and `sutra-pro config show` list `ask_v1` only when it is on**; `sutra-pro config init` adds one commented reference line for the new variable (the generated file, not a setting). `ChatComposer.bar` without `{ask: true}` and the state of a controller without Ask are what they were (a test proves it, including the key list of the state).
10. **CSS.** New classes only (`.c-answer`, `.asrc`, `.ccask` and their parts) in `sutra-panel.css`. The stylesheet file is not byte-identical with the flag off (nothing on any page uses the new classes then); the HTML of every page is.

### What the tests hold

- `tests/orchestrator/test_citations.py`: the marks, every path rule with hostile paths (`..`, absolute, `~`, backslash, drive letters, UNC, `\\?\`, ADS, trailing dot or space, device names, control characters, wildcards, links out of the folder, a pipe), that no file outside the folder is opened for any of them, the label that a model's words cannot change, limits and the time budget.
- `tests/orchestrator/test_api_ask.py`: flag off (a `mode` is refused exactly like any unknown field, every value of it, on both routes, the token first; no new key in the pill or in `/api/config`; the system text, the turn given to the port and the stored rows of a chat without a mode are identical with the flag off and on); flag on (bad modes, read-only tag, limits, grounding, the card for some, no and all-wrong sources, no folder, the scrub, no card on a failed turn, the limits gate, Retry with and without a mode, the legacy turn, Ask and a plain turn in one chat).
- `tests/connectors/test_chat_ask_cap.py`: against the fake CLIs, a plain turn with the owner's "edit" has the write tools and an Ask turn has only the four read tools (and no git read), also on a resumed Codex thread; switching between Ask and Do keeps the provider session; the allowance reaches the router's gate.
- `tests/orchestrator/test_answer_card.py`: the closed shape of the card, the store, the endings of an ordinary turn unchanged.
- `tests/ui/js/chat_ask.test.js`: the switch, the payloads (a Do sends exactly what it always sent), the retry rule, the draft (posts nothing), `fillBox`, the card for every case (some checked, no sources, all wrong, all checked, a label that is not exactly "checked", escaping, well-formed markup) and the draft text. It found one wording bug of the card ("could not be found" after "None of the 3 sources"), fixed.

### Checked in a browser, and not

Checked by hand in the browser pane of the desktop tool against `python -m sutra_app --offline` with `SUTRA_ASK_V1=1` and three cards written into the org chat's store (some sources checked, none given): Home's chat and a team's chat panel both draw the Ask | Do switch once the pill says `ask`; Ask shows the plain note, the file link and a Send button that reads Ask; the sources card reads right on a desktop and a phone width; "Turn this into work" switches back to Do (Plan with Sutra), puts the draft in the box with the caret at its end and focus in it, and sends nothing; with the flag off the same server draws no switch, the pill and `/api/config` have no new key, and `mode` is refused with the ordinary `extra_forbidden`. That walk found two page bugs (the bar was drawn before the pill was read, so the switch only showed after another repaint; and the draft was refused in a chat whose box was closed only because no model can answer an Ask), both fixed in the same branch. A card stored while the flag was on is still drawn after the flag is turned off (it is an ordinary stored message).

Not verified:
- **No real model answer.** Every test uses scripted ports and the fake CLIs. Whether a real Claude or Codex follows `ASK_RULES` (the mark form, relative paths, no marks in code formatting) is unknown; the card is honest either way (a missing or wrong mark is "no sources given" or "could not find"). Live smoke was not run (it spends the owner's quota). The offline run above has no model, so no real Ask turn was sent from the page either.
- **Other browsers and assistive technology.** Only the desktop tool's Chromium-based pane was used. Keyboard use of the switch (two buttons with `aria-pressed`) and a screen reader were not tried. The card has no dark theme to check (the app has none).
- **Windows.** The path rules are pure and tested with trapped file-system entries and `ntpath` strings, but nothing ran on a Windows machine (CI is the first). **A real Codex turn**, so the new-thread-per-mode rule is proved only against the fake Codex. **The in-CLI cap against a real Claude** (the command carries `--max-budget-usd`; what Claude does at the cap is its own, mapped to the existing `envelope_exceeded` error).
- **The beta app** was not installed from this branch.

### Review round (APPROVE WITH CHANGES: 4 majors, 9 minors)

| Item | What was done | Decision |
|---|---|---|
| M1 UNC or device path resolved before refusal | spelling refusal first, absolute paths compared as text, tests trap the file system and simulate `ntpath` | D357 |
| M2 a Retry widened an Ask | the mode is stored on the owner's line; a retry only narrows | D354 |
| M3 Codex thread keeps the other mode's words | one Codex thread per mode, tested both ways | D355 |
| M4 $0.25 not a ceiling | `--max-budget-usd` for Claude; Codex said to have none | D356 |
| m1 lone surrogate was a 500 | ASCII re-encode, 401 first, 422 after | D358 |
| m2 OpenAPI path order | registered in the old place; byte-identical, proved against a fixture from the base commit | D358 |
| m3 Ask with no folder on Codex | `read_only` forces the read-only sandbox | D355 |
| m4 claim too strong; `tool_kinds` unused | truthful words in code and owner words; edit/web tool calls counted from the blocks and said on the card | D355 |
| m5 Ask reads outside the folder | **not changed, said here**: Claude's `Read` is not confined to the folder in a chat turn and Codex's read-only shell reads the whole disk, so a model can read a file outside the folder and paraphrase it; the checker refuses outside paths as SOURCES but cannot stop the model reading them. More generally, a model can paraphrase a file it did read wrongly and still cite it: the card proves the citation (file, lines, quoted words), never the claim. Confining Ask to the folder (Claude's `blockReadsOutsideWorkingDirectories`, a Codex sandbox with only the folder readable) is a separate change | D355 |
| m6 `x[0:5]` became a source | only path-shaped text is a citation | D357 |
| m7 developer words | plain limit message and plain reasons | D356, D357 |
| m8 begin on the event loop; silent `askToWork` | `run_blocking`; the note under the box says when the draft could not be written | - |
| m9 Ask refused at the monthly limit; a third process after a lost session | Ask follows Do; tests prove the second round is gated (the review's third process does not happen) | D356 |

Not done on purpose: nothing in the review was left open except m5 (a question for the owner).

### Follow-ups

- Confine Ask's reading to the working folder (m5), for Claude and for Codex.
- DV-2 (the work list) can show a "Turn this into work" draft as a task source; nothing here prevents it.
