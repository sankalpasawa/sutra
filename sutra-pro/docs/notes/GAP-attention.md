# GAP-attention as built: know what needs you without looking (title count, desktop notice, Heads up lane, Try again, the corner pill, how long an ask waited)

Five verified gaps of the old-Sutra absorb review, built as one package (branch `feat/sutra-pro-gap-attention`). Two of them overlapped (the "Heads up"
lane and "work that ended while you were away comes back with Try again"): they are built once, as the Heads up lane plus a Try again on the done card.

Built:
- `sutra_app/orchestrator/waiting.py` (new, pure): `age_words`, `ask_state` (waited seconds, stale past `ASK_STALE_S` = 24 h), `why_waiting`.
- `sutra_app/orchestrator/headsup.py` (new): `HeadsUp(db).items(now)` -> `HeadsUpOut[]`, read at request time from `tasks`; `STOP_KEY = "_stopped_by"`.
- `sutra_app/orchestrator/api/chat.py`: `GET /api/heads-up` (read, no token); `GET /api/needs-you` passes `services.clock.now()`.
- `sutra_app/orchestrator/chats.py` `needs_you(now=)` and `models.py` `NeedsYouOut.waiting_s` (int or null) and `stale` (bool): additive, optional.
- `sutra_app/orchestrator/tasks.py`: `_prepare_next` uses `why_waiting`; `_mark_stop(task_id, "owner"|"app")` is called by `_stop` (the owner's Stop and
  reset) and by `shutdown` before the stop ladder.
- `sutra_app/orchestrator/agent/planner.py` `TaskLine.since`, `status_report(now=)`; `agent/runner.py` `_status_text` passes the time of the task's
  open question and the clock.
- `sutra_app/ui/static/js/heads_up_view.js` (new, pure, global `HeadsUpView`), `chat_attention.js` (new, global `ChatAttention`), `attention_pill.js`
  (new, global `AttentionPill`).
- Riders: `home.js` (the needs-you area: strip, lane, Try again, badge, title, notices, a one-minute redraw; one `retryTasks` key in `renderChat`'s
  transcript options and one `retry-task` branch in `onChatClick`), `chat_view.js` (`doneCard(c, ctx)` draws Try again when `ctx.retry`; the transcript
  passes `opts.retryTasks`), `dept_ext.js` (`attention()` adds the three scripts with `async = false`, called from `init`; not exported), `home.html`
  and `console.html` (script tags), `css/sutra-shell.css` (the lane, in the needs block), `css/sutra-panel.css` (the pill, after `.nempty`).
- Tests: `tests/orchestrator/test_waiting.py` 20, `tests/orchestrator/test_headsup.py` 13, `tests/ui/js/chat_attention.test.js` 12,
  `tests/ui/js/heads_up_view.test.js` 8, `tests/ui/js/attention_pill.test.js` 6, `tests/ui/js/chat_view_retry.test.js` 3, `tests/ui/test_home_attention.py`
  1 + 3 browser, `tests/ui/test_dept_attention.py` 3 browser (`SUTRA_BROWSER=1`). `tests/ui/fake_backend.py` serves `GET /api/heads-up`,
  `POST /api/tasks/{task_id}/retry` (token; the row leaves the lane, `task.updated`) and the control `POST /__fake/heads-up {items}`.

## What the owner sees
- **Tab title.** Home reads `(2) Sutra`, a team page `(2) Web · Sutra`, the console `(2) Usage and log - Sutra`. The count is questions and approvals plus
  Heads up problems not marked "Got it"; it goes back to the plain title at 0, and a `(N) ` already in front is replaced, never stacked.
- **One desktop notice per new thing** ("Web has a question for you", "Sutra needs your approval for a change to the org chart", or the problem's own
  sentence), only while the window is not focused and permission is granted. What is listed at the first read is not news; a key falls due 20 s after it
  was first seen, so an ask answered within seconds makes no noise; a key is announced once per browser (localStorage `sutra:notified`, plus the
  notice `tag`), so two tabs do not both ring. Clicking it brings the tab forward and, on Home, the card (a question), the org chat row (an approval)
  or the strip (a problem). Permission is never asked on load: the strip offers "Get a desktop notice ... Turn on / No thanks" once something waits and
  the browser has not been asked; "No thanks" is kept (`sutra:notify = off`) and the offer never returns, nor after a browser No.
- **Needs you strip** (Home): each ask says how long it has waited ("waiting 3 days", red past 24 h, "asked just now" under a minute), from the server's
  `waiting_s` plus the time since that read; the strip is redrawn every minute. With a Heads up lane present the strip gains a one-glance line
  ("1 question, 2 to try again") and the lane titles "Waiting on you" and "Heads up".
- **Heads up lane** (Home): a crash, or a stop the owner did not ask for, in the last 24 h that nothing newer replaced, with Try again, Open team and
  Got it ("Web ran into a problem on "Menu"", "Web was working on "Menu" when the app closed"); a running team with no event for 10 minutes ("has gone
  quiet ... no sign of work for 11 minutes", clears itself); work finished in 24 h as quiet FYI rows, three shown then "+N more" (done with open items
  also offers Try again until replaced). Problems count on the badge, the strip and the title; quiet and FYI rows never count. Got it is per browser
  (localStorage `sutra:headsup:seen`, marks of rows that are gone are dropped). The lane is read again on `task.updated` and every minute.
- **Try again** calls the existing `POST /api/tasks/{id}/retry` with the token. The crashed task's done card in the org chat shows the same button for
  exactly as long as the lane offers it, so it disappears once retried or replaced. A refusal is shown in the banner in the server's words.
- **Corner pill** on every team page and the console (never on Home, which has the strip): "1 needs you", "2 need you 1 to try again", a link to Home;
  nothing at 0; it pulses once (not under reduced motion) when the count went up, and a calm pill keeps its count. Bottom right on a desktop, under the
  header on a phone (clear of the message box), below the node drawer. Amended (0.3.2): "under the header" sat on J2's Needs you box and its Answer in Chat
  button in the Detailed view and on the console's links, so at 900px and under the pill rides in a row at the very top that the page keeps free for it while
  it shows (the Simple view's strip, a row above the Needs you box, a row above the console's header at 600px and under); `css/sutra-panel.css` has the rules
  and `tests/ui/test_dept_page.py` and `test_dept_attention.py` measure them from 320 to 1920px. From 901px it rides above J2's Chat button; on a team's library page the
  page keeps 34px under the catalog's card for it while it shows (J2's card ended 26px inside the pill's box and covered the catalog's last row buttons), and no other tab's card is resized.
- **Why a task waits.** A queued task behind a team that waits for the owner reads "waiting for your answer: the team's current task asked you
  something" (it said "waiting for the team to finish its current task"); a full house of teams waiting for answers reads "waiting for a free slot: 12
  teams are waiting for your answers".
- **Status answer** of the org chat: '- Web: waiting for you on "Menu" for 2 days.'

## Decisions
- A separate read `GET /api/heads-up` rather than a new `NeedsYouOut.kind`: a problem has no chat message (`message_id` and `session_id` are required
  there) and the J2 team page's own strip keeps its meaning. No new event type: `Projector._finish` already announces `task.updated` through
  `TaskGraph.sync`, and the page reads the lane again on it. `HeadsUpOut` lives in `headsup.py` so `models.py` and its `__all__` are not touched by it.
- **The owner's own stop is never listed.** The engine ends every stopped run with the same words ("Stopped: stopped on request"), whoever asked, so the
  outcome cannot tell an owner Stop from the app closing. `TaskService._mark_stop` writes `_stopped_by` ("owner" from `_stop`, which serves Stop and
  reset; "app" from `shutdown`) into the task's `settings_json` before the ladder, beside `_seed_from`; the first writer wins; underscore keys never
  reach the task's J2 settings (`_row_of` drops them) and a retry does not copy it. Without a mark, the server's own words "stopped by you" and "reset by
  you" also mean the owner. Any other stop (the app closed, the engine stopped itself) is a problem with Try again.
- "Replaced" = a retry of it (`parent_task_id`) or any task of the same team created at or after it ended (the owner wrote to the team). A task created
  before the crash (queued behind it) does not hide it.
- Badge = asks + problems (the old app counted only the decide lane; Pro counts crashes because a crash otherwise leaves only a card). Got it on a
  problem removes it from the count in this browser.
- The pill **reads, it does not listen**: both lists every 5 s while the tab is in front, 15 s while it is not, at once when it comes back. A team page
  keeps one event stream (pinned by `test_dept_page.py::test_the_live_chip_follows_the_stream_of_both_views`), and every open stream holds one of the
  browser's six connections to this host for as long as the tab is open; a second stream per team tab would starve the pages after a few tabs.
- Stale window: a constant (`waiting.ASK_STALE_S`, 24 h), not a setting: no new environment variable and no `config.py` change (other packages edit it).
- The status answer says "for 2 days" (not "since 2 days"); the time is the `at` of the task's oldest unanswered question (the same time
  Needs you uses), not `last_event_at`: a waiting team's engine stays alive and its heartbeat moves `last_event_at` every 5 s.

## Existing tests changed (intended behaviour change, nothing weakened)
- `tests/orchestrator/test_api_chat_read.py`: the needs-you key set gains `waiting_s` and `stale` (and checks their types).
- `tests/ui/test_fake_backend.py`: `WRITES` gains `POST /api/tasks/{task_id}/retry` (so it is checked for the token like every write).
- `tests/ui/test_home.py` (browser): Home's first reads include `/api/heads-up`.
- `tests/ui/test_dept_page.py` (browser): the boot title may carry the count once read, `(1) Web · Sutra` at stage 2.

## Not done, and why
- **A notice while no tab is open** (G26's other half: a macOS notification from the launcher, osascript): a launcher job, out of this package.
- **A per-attempt brief on retry** and **the done-card receipt** belong to model-quality (`TaskService.retry`, `DoneCard`); this package only calls the
  retry route and adds one button to the done card's actions row.
- **A Try again in the department chat's crash line** ("Something went wrong. Try again.", `node_panel.js`): node_panel is chat-comfort's file; the
  lane and the org chat's done card cover it.
- **The J2 team page's own strip** does not show the age of an ask: that is J2's page (frozen).
- **A movable pill or a quiet-hours setting** (the old Shadow overlay): not wanted in Pro (the review said so); the pill keeps the old rule that a calm
  state never hides the count.
- `docs/design/*` and the absorb table are not edited here (the docs package records new routes); this file is the record.

## Known limits
- The browser suites of `test_home.py` and two cases of `test_dept_page.py` already fail on the base commit: the fake backend has no
  `GET /api/chats/{sid}/providers` (the provider pill of ABS-9), so a page that opens a chat 404s, and Home's rail test predates the "Owner" section. The
  new browser tests announce that one 404 (`expect_failed`) and pass. Fix belongs to whoever owns the fake's provider routes.
- The age of an ask is measured by the server at the read plus the browser's clock since; a sleeping laptop shows the right age at the next minute tick.
- A crash older than 24 h leaves the lane even if never retried (the old app's grace).
