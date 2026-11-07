# GAP3-dept-chats as built: each team the org chat makes has its own chat, and Home can show it

The owner said: "Whenever it is actually initiating new departments, the chat sessions need to be separate. I think right now it is in a single chat
session." Branch `feat/sutra-pro-gap3-dept-chats`. The sessions were already separate in the database; what the owner met was one conversation. This
package finds out exactly where, and builds what was missing.

## What was found (a real app, two teams from one org message)

Run offline: `LiveApp` (the real app, the engine as its own process in J2's mock mode) with the chat agent's model scripted, one message to the org chat
asking for two new teams (Web and Print). What existed afterwards, before this package:

- **Sessions (already right).** `chat_sessions` held `cs_org`, one `department` session per team (`cs_24b53d58aac7` for Web, `cs_d88e9fd7286d` for Print),
  titled by the team's name, writable, plus five read-only `function` sessions per team. `chart._build_nodes` makes each through `ensure_node` in the same
  transaction as the graph node and the chart revision (invariant I1; `tests/orchestrator/test_chart_store.py` already undid a half-made team). Nothing is
  shared: `graph_nodes.chat_session_id` is unique per node.
- **Who got which line (partly wrong).** The owner's request, Sutra's template line, the chart card and a `task` card per team went to `cs_org`. The runner
  (`TurnRunner._create_tasks`) copied the owner's words into each team's session as a plain "You" line (`src_ref req:<org message>:<task>`), with nothing
  that said it was passed on. Identity's question and every later engine line went to the team's session (`projector._on_say`). **But** the projector also
  wrote a `needs_you` card into `cs_org` carrying the question's text and an answer box, so the org chat held, and let the owner answer, the team's
  conversation.
- **Provider sessions (already right).** The chat agent and the engine make one-shot calls (`call_json`, no provider session; `context.session_id` only
  labels the usage row: `cs_org` for the agent, the node's session for the engine). The only resumable provider sessions are the direct chats
  (`POST /api/chats/{sid}/direct`): the Router keys them by the chat session id (`work_root/<sid>/session.json`, `--session-id`, `--resume`) and primes a new
  one from `ChatTranscripts(sid)`, that chat's own rows. Proved below, not assumed.
- **What Home showed (the real gap).** Home's chat column is bound to `cs_org` (`const ORG`). A team's own chat opened only from the graph (the node panel
  drawer) or by leaving Home for the team page (`Open the team`). Nothing said "Started Web", and nothing named which chat a question belonged to.

## What the owner gets

- **A line in the org chat per new team.** "Started **Web**: [Open its chat]" for each department or division the turn made, after the chart card and before
  the task cards. The chip is a real `<button>` (Enter and Space work, focusable, `aria-label` names the team); the team's name and ids are escaped. A reused
  team gets no "Started" line (no new chat); a division gets one that opens its lens chat.
- **A pointer instead of a copy for a question.** When a team's Identity asks, the org chat now gets "**Web** has a question for you. [Answer in its chat]",
  which carries none of the question's words. The question, its option buttons and the answer stay in the team's chat. Once the question is answered the
  pointer reads "Web's question was answered." (the chip stays so the chat can be read).
- **One chat on show, a strip to switch.** A row of tabs above Home's chat column names the org chat ("Sutra") and each team and division; the active tab is
  selected, a team's tab shows how many of its questions wait, and the column is labelled "Chat with Web". Arrow keys move between the tabs (roving tabindex),
  Enter or Space picks. The chip, a tab, the strip's button and the Heads up row's "Open its chat" all open the same thing: the team's own chat in the chat
  column, the node panel's Chat tab shown inline (composer, "Ask the model", provider pill, search, archive, drafts, scroll: all the node panel's, none
  invented). "Back to Sutra" or Esc returns to the org chat as it was (its parts are hidden while a team's chat shows, never removed).
- **The strip names the chat.** "Needs you" says "Answer in Web's chat" (an approval still says "Answer in Chat": it waits in the org chat); it opens that
  team's chat with the question in view. A Heads up row of a team gains "Open its chat" beside "Open team".
- **The passed-on mark.** A team's first line (the owner's request, copied when the task starts) reads "Passed on from your chat with Sutra" above the
  words, in the team's chat on Home and on the team page. The words themselves are unchanged and are what the team's first direct turn carries.

## Where

Python (`sutra_app/orchestrator/`):
- `models.py`: `TeamChatCard` (`type team_chat`: `node_id`, `name`, `kind`, `session_id`, `about started|question`, `question_message_id`) added to the
  `ChatCard` union; `ChatMessageOut.passed_on` (optional int, left out of the wire when empty, like `turn`).
- `chats.py`: `_passed_on_of(session_id, src_ref)` derives `passed_on` from the copy's `src_ref` (`req:<id>:tsk_...`) in a session that is not `cs_org`. Nothing
  new is stored: the mark is read from what the runner already wrote.
- `agent/runner.py`: `_started_cards` (one `team_chat` card per added department or division, with the session id read from `graph_nodes`), written by
  `_write_outcome` between the chart card and the task cards.
- `projector.py`: `_ask` writes the `team_chat` pointer (about `question`, `question_message_id` = the question in the team's chat) instead of the `needs_you`
  card; same `src_ref`, so a replayed event is still one card.

UI (`sutra_app/ui/`):
- `static/js/chat_switch.js` (new): `ChatSwitch` (pure strings, one global, `module.exports` in node): `entries`, `bar`, `heading`, `nextIndex`, `entryOf`.
- `static/js/chat_view.js`: `teamChatCard` (the line and the chip), `passedOnHtml` (the caption); `open-team-chat` joins the documented `data-act` set.
- `static/js/node_panel.js`: `mount(host, {inline, idPrefix, onClose})`. An inline panel leaves `body.nodeopen` and the Agent drawer alone, owns only the keys
  typed inside it, uses its own element ids (`npititle`, ...), reads "Back to Sutra", focuses its heading on open, empties its host when it closes (so a page never
  finds a second hidden Chat tab by selector), and is not the panel the static `NodePanel.open()` reaches. The default mount is unchanged.
- `static/js/home.js`, `pages/home.html`, `static/css/sutra-shell.css`, `sutra-panel.css`: `#cswitch`, `#teamchat`, `renderSwitch`, `openTeamChat`,
  `showOrgChat`, the tab and key handlers, the strip button, `focusCard` opening the team's chat. `static/js/heads_up_view.js`: the Heads up button.

## Proof

- `tests/orchestrator/test_dept_chats.py` (17): two new teams from one turn: the session rows (kind, title, writable, status, no provider session yet, unique,
  the node names its session); a second team's failure after the first's node was made leaves neither node nor session; every message in exactly one chat and
  the API lens agreeing with the table id for id; the org chat holding only Sutra's lines, the owner's, and cards; each team chat holding exactly its copy of
  the owner's line with `passed_on` = the org message and its own task id; the task starting there; the started pointers; a reused team getting none; a
  division's session and its lens showing the passed-on line; `_passed_on_of` over malformed refs; the unchanged wire shape.
- `tests/e2e/test_dept_chats.py` (2), over the real app: (1) stub connector, real engine: sessions through `/api/chats`, the passed-on lines, the pointers,
  both Identities asking, `/api/needs-you` naming each team's session, none of the question text in the org chat, an answer in one team's chat finishing that
  run while the other still waits, every engine `chat.message` event addressed to a team session and none to `cs_org`. (2) The real connector router over the
  fake `claude`: three chats, three provider sessions (distinct, new `--session-id`, no `--resume`), each in its own work folder; the org chat's prompt carries
  the org chat; a team's first prompt carries only its own chat (the request passed on) and none of the org chat's lines or the other team's; its second turn
  `--resume`s its own session; the store remembers one `provider_session_id` per chat.
- `tests/ui/js/chat_switch.test.js` (11), `chat_view_teamchat.test.js` (9), one more in `heads_up_view.test.js`: the strip, the card line, the chip as a button,
  escaping, the caption, the old `needs_you` card unchanged. `tests/ui/test_home_team_chat.py` (6, `SUTRA_BROWSER=1`, headless Chrome on the fake backend):
  the line and the strip, the chip opening the team's chat (its own lines, the org chat hidden, nothing sent, focus on the name), Back, a tab and Esc, the arrow
  keys, the strip button opening the chat with the question focused and an answer going to the team's session.
- Six orchestrator tests, the e2e new-team scenario, one fake-backend browser test and the real-app browser walk (`tests/e2e/test_browser_real_app.py`) asserted
  the old shape (a `needs_you` card in `cs_org`, the card order of a turn that adds a team, "Answer in Chat" finding and answering in the org card); they now
  assert the new one. The real-app walk was run with `SUTRA_BROWSER=1` (Chrome) and passes: the brief, the "Started Web" line, the pointer, the question read and
  answered in the team's own chat (and absent from the org chat), the pointer turning "answered", the Done card, the team page.
- `tests/library/test_lib_records.py::test_all_does_not_freeze_the_registry_and_freeze_closes_it` fails when it runs after any test that builds the app in the same
  pytest session (for example `tests/orchestrator/test_startup.py` before it): the registry is already frozen. That is order dependence that was there before this
  package (reproduced with an untouched test module ahead of it); run `tests/library` in its own session, where it passes.

## Not done, and why

- **Carrying a choice into a new team.** A team's chat starts with no provider pin; the policy decides. The owner can pin it in the team's own chat (the pill). The
  brief allowed carrying "something" if the owner chose to; there is no such choice in the product, so nothing is carried (the e2e proves nothing is, by default).
- **No migration of old rows.** A `needs_you` card already stored in an org chat still validates and still draws with its answer box; only new questions use the pointer.
- **A reused team's follow-up task** has no "Started" line: it makes no chat. Its task card and the team's tab are the way in.
- **No overflow menu** for many tabs: the strip scrolls sideways. The phone layout was not looked at in a 375 px browser.
- **The old Home browser suite** (`SUTRA_BROWSER=1 tests/ui/test_home*.py`) already fails on its first assertions at this commit: the fake backend has no
  `GET /api/chats/{sid}/providers`, so the page logs a 404 that the tests count as a console error. Not touched; the new browser tests announce it with
  `expect_failed("/providers")`. The one old browser test that depended on the changed behaviour was updated and passes.
- **`dept_ext.js` and the J2 page** are untouched (the team page gets the caption through `ChatView`, which it already loads). `docs/design/ui.md` 6.6 and
  `orchestrator.md` still describe the `needs_you` mirror card; the proposed decision below supersedes them.

## Proposed decision (the merge step numbers it)

> **Each team has its own chat, and the org chat only points at it.** A department or division the org chat creates gets its own chat session, made with its
> node in one transaction (D63), titled by its name. The owner's request is copied once as the first user line of that chat and is marked as passed on from the
> org chat (`ChatMessageOut.passed_on`, read from the copy's `src_ref`); the org chat gets one `team_chat` card per new team ("Started <name>: open its chat").
> A team's replies, its questions and their answers stay in its own chat; when its Identity asks, the org chat gets a `team_chat` pointer (about `question`),
> never the question's words (this replaces the `needs_you` mirror card, which is still read and drawn when stored). A provider session is per chat session
> id: a team's first turn starts a new one primed only from that chat's own transcript, and no engine or team line is ever written to `cs_org`. Home's chat
> column shows one chat at a time with a strip of tabs; a team's chat is the node panel's Chat tab shown inline.
