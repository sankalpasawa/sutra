# Devin parity: developer notes (DV-1 and later)

What the builder found and decided while building a package of `docs/design/devin-parity.md` (the owner's spec; it is not on `main` yet, so this file does not link to it). One section per package.
Everything here is also in the decision log (D350 to D353) where it is a decision; this file holds the deviations, the limits and what was not verified. Paths are relative to `sutra-pro/`.

## DV-1. Ask: cited answers, read only (`SUTRA_ASK_V1`, default 0)

Branch `feat/sutra-pro-devin-ask`. Decisions D350 (the turn), D351 (the check), D352 (flag off), D353 (the card and the draft).

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

1. **Decision numbers D350 to D353, not the next free number on `main` (D253).** `origin/feat/sutra-pro-agent-nodes` already holds D253 to D345 and is still adding (it was at D331 when this package started and at D345 when it was pushed), so D253 would have collided the day both land. DV-1 therefore takes a small block of its own above what that branch has used; the numbers between D252 and D350 are simply not on `main` until the nodes branch lands. `tests/test_diagram_decisions.py` and the traceability generator only need the log and `decisions.json` to agree, which they do. If the nodes branch grows past D349 before either lands, whoever lands second renumbers: four headings, four `decisions.json` entries, and the mentions of "D350 to D353" (`config.py`, `ask_mode.py`, `ENVIRONMENT.md`, `OPERATIONS.md`, this file, four tests), then `scripts/py scripts/build_traceability.py`.
2. **`mode` is a field of the body that the route class takes out, not a field of `DirectIn`.** The spec says "`mode=ask`" and "refused or ignored exactly as today when the flag is off". Today a body that names an unknown field is a 422 `extra_forbidden` (the request models are closed), so the way to keep today's bytes is to leave the models alone and to take `mode` out of the body only when the flag is on (`ask_mode.AskRoute`). Consequence: `mode` is not listed in the OpenAPI document of the two routes (the request schemas are what they were). A query parameter would have been ignored by a flag-off server, which would answer an Ask as an ordinary chat; that is why it was not used.
3. **The mode of a Retry is named again by the page.** The server stores no mode (no new table, no new column), so `POST /direct/retry` takes `mode` too. The page remembers how it sent each line (in memory, 50 lines) and a Retry of an Ask asks again, even after the switch went back to Do. A line from before a reload follows the switch as it is now. A Retry with no mode is a Retry of the chat as it was (no card). Not tied to the stored line on purpose: it keeps the stored shape of every row unchanged.
4. **The limits of a function's question reach a chat turn as a gate before each model process, not as a cap inside it.** `agent_ask.py` has 2 calls, $0.25, 120 s; they go through `ChatTurnIn.allowance` into the router's own gate. Calls and the deadline hold (the deadline also shortens the turn's timeout). The dollar figure is checked before each spawn against what earlier spawns of the turn cost; the connector's chat plan has no per-call budget, so a single spawn can pass $0.25 (the usage ledger books it). A hard cap inside the CLI for chat turns needs a connector change and was not made.
5. **No instruction is added to the owner's line.** The Ask words go in the system text (`ASK_RULES`, last in the grounding). Claude reads that text on every turn. Codex keeps the system text of the first turn of a thread: in a chat whose thread began in Do, an Ask turn is still read only (the sandbox is set per turn by the router) but may not have heard the citation form, and then its card says "No sources given". Putting the words in the user's line would have made the stored line differ from the sent one and duplicated the question in the carry-over of a new session.
6. **A stopped or failed Ask has no card.** The kept partial text may contain marks; they are shown as the text the model wrote, without a label. A card on a half answer would say "checked" about words the owner was told were cut.
7. **The monthly limit and plan window hold Ask back (409 `busy`, their own words)**, as `agent_ask` does; a plain direct chat is not gated today and is still not. Offline (the stub) an Ask runs and its card says "no sources given".
8. **What a mark may be.** `[path:12-18]`, `[path:12]`, `[path:12-18 "words"]` (also an en dash and curly quotes). Marks inside a fenced code block are examples and are skipped; marks in inline code count. At most 30 marks are checked (`more` counts the rest). An absolute path is accepted only when the file system puts it inside the folder and it has no `..`. A path with a backslash, a colon (so `C:x` and `file:stream`), a drive letter, `~`, a trailing dot or space, a device name (`CON`, `NUL`, `COM1`, `LPT1`, ...) or a character a path never needs is refused on every machine, so a result does not depend on the platform the test ran on. A file larger than 4 MB, not text (a NUL in the first 8 KB) or a range wider than 400 lines is "could not find" with the reason. Quotes under 4 characters prove nothing and are not used (the lines are checked and the card says so); over 300 characters are refused.
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
- **The in-CLI dollar cap** (item 4) and a Windows run of the path rules (they are written not to depend on the platform; CI is the first Windows run).
- **The beta app** was not installed from this branch.

### Follow-ups

- The $0.25 as a per-call budget of a chat turn in the Claude connector (item 4).
- A stored mode on the owner's line (one more sibling key of `meta_json`) so that a Retry after a reload is exactly the first turn's mode.
- DV-2 (the work list) can show a "Turn this into work" draft as a task source; nothing here prevents it.
