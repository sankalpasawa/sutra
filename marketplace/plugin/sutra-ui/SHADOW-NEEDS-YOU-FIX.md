# Shadow — Needs You dropped the turn list and the conversation

Founder report, 2026-09-18: "the bottom part where we are seeing Turn 1, Turn 2,
and the conversation ... disappeared." Fixed under mission m-55fe2e9465a0.

## 1. Root cause

    marketplace/plugin/sutra-ui/static/panel.css:3428

That rule (`.shwright>.shcard2`) was `flex:0 0 auto` — unshrinkable — inside a
clipping column, so the sign-off list that only NEEDS YOU draws grew the brief
card from 192px to 330px and the conversation scroller underneath it was
squeezed to 0px, with no scrollbar anywhere to reach it.

## 2. The fix

| file | what changed |
|---|---|
| `static/panel.css:3428,3446` | card is `flex:0 1 auto` capped at 32% and scrolls itself; conversation floor `min(220px,40%)` with weighted shrink, so it yields last |
| `static/panel.css:3865` | new `.shwright>.shiv`: question pinned, capped at 38%, scrolls itself |
| `static/js/16-shadow-home.js:3652` | question moved OUT of `.shwscroll`, pinned between the conversation and the composer |
| `test_shadow_v4_shell.js` | block 10 covers both halves; all 10 blocks pass |

## 3. Evidence — measured on 127.0.0.1:8330, the desktop app

Bytes fetched over HTTP from 8330, real 10-turn mission `m-af6443fda631`, drawn
by the app's own code in headless Chrome. The page never scrolls; all 10 turn
rows are in the scroller and reachable.

| window | card | conversation | question | turn rows visible |
|---|---|---|---|---|
| 1100px | 333px | 266px | 159px | 2 of 10 |
| 900px | 255px | 220px | 83px | 4 of 10 |
| 660px | 79px | 195px | 43px | 1 of 10 |

Send, clicked for real through the app's own delegation. Live 8330, no question
on the record: `409 no intervention is waiting`, and the 10 turn rows + 2 founder
lines were still there after the re-render. An isolated byte-identical copy with
a real pending question: **200** — paused → running, `founder_response` stored,
question retired, ledger row written, and **the 10 turn rows and 2 founder lines
survived the re-render**, plus a new "You answered" row.

Status sweep at 900px, same mission — every status but one is untouched:

| status | result |
|---|---|
| running | 10 turns, 5 visible, 298px conversation, no question — unchanged |
| queued | unchanged |
| brief_confirm (READY) | unchanged |
| draft | unchanged |
| paused (app_restart etc.) | unchanged |
| done | unchanged |
| failed | unchanged |
| stopped | unchanged |
| paused + founder_confirm (NEEDS YOU) | 10 turns, 4 visible, 220px conversation, 83px pinned question — **the fix** |

## 4. Known gap

Shadow's own replies do NOT render on 8330: that stream (`shadowTalkTurns`,
`task_chat_session`, `shadow_task_chat.py`) is absent from the installed
release, front end and backend, so no front-end change can produce it. What shows
there is the worker turns, the founder's own asides and the "You answered" row.
Closing it needs a full release install — 541 files, 12 changed backend modules,
app quit and relaunched. **Not run.**
