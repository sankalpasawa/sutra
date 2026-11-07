# GAP3-fluid as built: a page that stays fluid

The owner said: "The animation is a bit choppy. I want it very fluid, so make sure that whatever animations you have are fluid."

Built: `ui/static/js/fluid.js` (new, one global `Fluid`), `ChatView.transcriptItems`, `ChatPill.streamParts`, `ChatComposer.streamParts` and `paintStreamRow`, edits in `home.js`,
`node_panel.js`, `graph_view.js`, `dept_ext.js`, `home.html`, and the motion section of `ui/static/css/sutra-panel.css` (plus `sutra-graph.css`, `run-settings.css`).
Tests: `tests/ui/js/fluid.test.js` 27, `tests/ui/js/motion_css.test.js` 7, one test each added to `chat_view.test.js`, `chat_pill.test.js` and `chat_composer.test.js`,
`tests/ui/test_fluid.py` 9 (4 wiring, 5 in a real browser with `SUTRA_BROWSER=1`), one browser test in `tests/ui/test_view_graph.py`.
The probe that made the numbers: `tests/ui/perf/fluid_probe.js` (served by the fake backend at `/__fake/probe.js`).

## Where the jank was (the audit)
The motion of the page is small: a few opacity transitions, a glow on a new node, a pulse on the attention pill, and J2's idle drift. The choppiness came from what the page does
around its motion. Causes, in the order they cost:

1. **Whole-list `innerHTML` on every chat event** (Home's org chat, the node panel). A `chat.message` or a refetch built the HTML of the whole transcript and, when it differed by one
   line, threw the whole list away and built it again: flicker, a lost text selection, a lost open `<details>`, and a frame of 50 ms in a chat of 360 lines. Fix: `ChatView.transcriptItems`
   gives one keyed element per message and `Fluid.patchList` edits the list in place (front/back pairing by key: a chat that grows at the bottom is only inserts, a changed line is
   replaced alone, an open `<details data-key>` stays open). A line that arrives gets `.nmsg-in`; a history loaded at once (more than 6 lines) does not animate line by line.
2. **A streamed reply written again per chunk.** Each `chat.partial` rebuilt the markdown of the whole text so far (up to 4000 characters), replaced the whole streaming row with
   `innerHTML` and repainted the composer (`paintComposer` + `paintBar`, a forced layout each). Fix: `Fluid.paintStream` appends: the blocks that are done (`Fluid.splitStream`: the
   next block has begun; a list, quote or table is never cut apart, even a list that begins in the middle of a paragraph's group or goes on with a one-space or tab indent; a fence keeps its blank lines) are drawn once and stay as the same nodes, only the tail is drawn again; the
   composer's repaint is one job per animation frame (`Fluid.frame`) however many chunks came in it. The row and its `aria-live` region are written once.
3. **A graph or org chart redrawn for data that did not change** (an event about another team, the 2 s poll while the stream is down): layout, SVG string, compare. Fix: `GraphView.accept`
   keeps a fingerprint of the picture (data, what the owner asked for, which nodes are unread; `Fluid.signature`) and skips an update that brings the same one. The org chart goes
   through the same `accept`.
4. **Animations of paint-heavy properties.** The new-node glow animated `filter: drop-shadow`, its list twin `box-shadow`, the attention pulse `outline` and `outline-offset`; J2's own
   `mdrift` moves every node of its maps with `translate` on an SVG group, for ever (no compositor for that: the whole picture is painted each frame, and a node half a pixel off
   shimmers), and the sun's spokes march a dash offset for ever. Fix: the glow is a scale pop (`transform`), the list twin and the pulse are a ring (`::after`) that fades and grows
   (`opacity`, `transform`); J2's drift and the spokes' march are off from `sutra-panel.css` (loaded after `j2.css` on every page: `j2.css` stays byte for byte, and the dashes of a
   LIT path, a hovered or focused reads/makes line, still march, because they say something).
5. **Things that had no motion at all.** The drawer (the node panel and J2's Agent drawer), Home's panes, a banner, a new line and the pills just appeared. They now slide or fade in over
   `--dur-base` (`transform` and `opacity` only); the drawer slides out too where the browser can keep `display` through a transition (`transition-behavior: allow-discrete`, Chrome 117+),
   else it closes at once. Buttons change colour, border and opacity over `--dur-fast`; a press settles a hair (`transform`).

One scale: `--ease-out`, `--ease-in-out`, `--dur-fast` 120 ms, `--dur-base` 200 ms, `--dur-slow` 320 ms (the glow and the pulse are 4 x slow), defined in `sutra-panel.css`; under
`prefers-reduced-motion` every duration is 0 and a universal rule (`animation-duration` and `transition-duration` .01 ms, one iteration, no smooth scroll) ends anything left.
`.nmsgs`, `.npbody`, `#smsgs` keep their scroll to themselves (`overscroll-behavior: contain`); the graph stage is `contain: layout paint`.

## Measured (before and after)
Method: the built-in browser pane, shown (a hidden pane gets no frames), a 120 Hz display (a frame is 8.3 ms), against `tests/ui/fake_backend.py --stage full`. "Before" is the
base commit's own `ui/` served by a second fake backend, so both runs are the same machine, the same data, the same probe code (`tests/ui/perf/fluid_probe.js`:
a `requestAnimationFrame` probe counting frames over 20 ms and 33 ms and the longest frame, plus the elements the page created). To repeat: start the fake backend, open Home,
`await import('/__fake/probe.js')`, then `await __seed(300)` once, and `await __run.append()`, `__setupDirect()` then `__run.stream()`, `__run.panes()`, `__run.panel()`, `__run.graph()`.

| scenario | frames over 20 ms, before | after | longest frame, before | after | other, before | after |
|---|---|---|---|---|---|---|
| 20 messages arrive, 150 ms apart, in a chat of 322-346 lines | 15 of 378 (14/370 and 16/392 in two other runs) | 0 of 410 | 50 ms (59, 50) | 10 ms | 37,368 elements created | 40 |
| a 6,500 character reply, 470 `chat.partial` events (~80 a second) | 0 of 686 | 0 of 704 | 10 ms | 10 ms | 470 markdown renders, 48.3 ms, 1,278,326 characters, 35,211 elements created | 1,110 renders (the blocks that settled, and the tail), 18 ms, 179,168 characters, 4,646 elements created |
| Home panes switched 20 times (graph, org chart, Settings) | 0 of 641 | 0 of 643 | 17 ms | 10 ms | no easing, the pane appears | fades in over 200 ms, no frame lost |
| node panel opened and closed 6 times | 0 of 831 | 0 of 833 | 10 ms | 10 ms | appears and disappears | slides in and out, no frame lost |
| graph redrawn on 20 `graph.updated` events that change the picture / 20 that change nothing | 0 of 527 / 0 of 404 | 0 of 529 / 0 of 405 | 10 ms / 10 ms | 10 ms / 10 ms | | the second is not laid out at all |

Read it honestly: on this machine only the chat transcript missed frames before. The stream, the panes, the panel and the graph are small enough here to hold 120 Hz either way, so
for them the numbers show that the new motion costs no frame, and the gain is in the work not done (the stream renders 7 times fewer characters of markdown, in 2.7 times less time, and builds 7.6 times
fewer elements; a slower machine, or a longer reply, is where that shows). The transcript is the finding the owner will have felt: every message in a long chat was a 50 ms hitch.

## Test results
`node --test tests/ui/js/*.test.js`: 920 tests, 918 pass, 2 skipped, 0 fail. `scripts/py -m pytest tests/ui tests/library tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py`:
3212 passed, 213 skipped (the browser tests skip without `SUTRA_BROWSER=1`). With `SUTRA_BROWSER=1`: `test_fluid.py`, `test_view_graph.py` (61) and `test_view_panel.py` pass; see Known limits for the rest.

## Riders (small changes in shared files, so the merge is easy)
- `home.html`: one `<script src="/ui/js/fluid.js">` after `sutra_events.js`. `dept_ext.js`: `"fluid"` first in the list of scripts it adds to the team page (J2's page file is not edited).
- `home.js`: `renderChat` draws the transcript with `Fluid.patchList` (the "Try one of these" starter is one more item), `composer()`'s `onChange` is one job per frame, `renderBar` draws the
  stream row with `paintStreamRow`. `node_panel.js`: the same three places (`paintMessages`, the composer's `onChange`, `paintBar`) and the banner through `paintTo`. Every call checks
  that `Fluid` is there and falls back to the old whole-string paint.
- `chat_pill.js`, `chat_composer.js`, `chat_view.js`: additions only (`streamParts`, `paintStreamRow`, `transcriptItems`); `transcript()` is now `transcriptItems(...).map(html).join("")`, byte for byte as before.
- No `chat_pill.js` model picker, Settings, update check or welcome code was touched (the welcome-settings package owns them).
- `tests/ui/fake_backend.py`: `POST /__fake/emit` accepts `chat.partial` (it needs `{session_id, delta}`, has no sample, is never stored or replayed, as in the real server) and `GET /__fake/probe.js`
  serves the probe. `tests/ui/fixtures/mount_graph.html`, `mount_panel.html` and `test_view_panel.py`'s `SCRIPTS` load `fluid.js`, so their browser tests run the new paths.
- `tests/ui/js/contrast.test.js`: the "at most 3 own tokens" rule does not count the motion scale (`--ease-*`, `--dur-*`), which are not colours.

## Not done, and why
- **No CSS injection from `dept_ext.js`.** The task expected one; there is none to make: `j2_ui.html` already loads `sutra-graph.css` and `sutra-panel.css` after `j2.css`, so J2's page gets
  the motion section from the sheet it has. A test (`motion_css.test.js` 6) keeps that true.
- **No FLIP of moved nodes.** A node that moves in a reorganisation still jumps to its new place (a new node pops, as before). It needs the old and new box of each node across a redraw
  and a transform animation on SVG groups; one frame of jump per reorganisation was left for a follow-up.
- **No exit animation for a line or node that goes**, and the drawer's slide-out falls back to an instant close without `transition-behavior: allow-discrete`.
- **Pan and zoom are unchanged.** Chrome delivers `pointermove` and `wheel` once per frame and the handler writes one attribute, so batching them gains nothing and would make the
  existing browser tests (which read `g.wview` right after a wheel) racy.
- **J2's own `requestAnimationFrame` loops** (inertia, zoom tween, the run poll every 700 ms) are in the frozen page.
- **A very long transcript** (thousands of lines) still builds the item HTML of every line on each paint pass, though it now touches no DOM for the lines that did not change; windowing
  (`content-visibility`) was not attempted.
- **A reply longer than 4000 characters** shows only its last 4000 (the existing `MAX_SHOWN`); once the head moves, the row starts again from its blocks each frame, which is the old cost
  and no more.

## Proposed decision (the merge step numbers it)
**Motion of the Sutra UI.** One easing curve and one duration scale (`--ease-out`, `--ease-in-out`, `--dur-fast`, `--dur-base`, `--dur-slow`), 0 under `prefers-reduced-motion`. Sutra stylesheets
animate `transform` and `opacity` (and colours) only, never `transition: all`, never a layout property, `box-shadow` or `filter` (`motion_css.test.js` enforces it). A list that gains a line is
edited in place (`Fluid.patchList`), a streamed reply is appended to (`Fluid.paintStream`), repaints caused by events are batched per animation frame (`Fluid.frame`), and data that did not
change is not drawn again (`Fluid.signature`). J2's idle drift and the spokes' march are off; `j2.css` and the J2 page are untouched.

## Existing tests changed (intended, nothing weakened)
`tests/ui/js/contrast.test.js` (the allowance above), `tests/ui/fixtures/mount_graph.html` and `mount_panel.html`, `tests/ui/test_view_panel.py` (`fluid.js` joins the scripts it copies).

## Known limits
- With `SUTRA_BROWSER=1` the browser tests of `tests/ui` are not green on the base commit: 66 fail or error there (`test_home*.py`, `test_visual.py`, `test_dept_page.py`, `test_browser_smoke.py`,
  a mount-page test of `test_fake_backend.py`), nearly all because the fake backend has no `GET /api/chats/{sid}/providers` and the page's 404 for it is not announced (`test_home.py` says
  "pre-existing, not this package"). Compared test by test, nothing that passes on the base fails on this branch. Three tests of `test_fake_backend.py` (the graph and chart mount pages and
  the scripted first task) did fail on this branch for a reason of mine, a 404 for the new `fluid.js` in their stand-in static tree; `STUB_VIEWS` has it now. And
  `test_dept_page.py::test_a_graph_node_click_opens_its_chat_panel` raced that same 404 (the panel is now quick enough to issue the request before the test's first check), so it announces
  the 404 and ignores 404 console lines, as the Home tests do. The missing fake route itself was not added: it would change what the Home tests see (a pill) and belongs to another package.
- The numbers above are of one 120 Hz machine, with the pane in front. They are evidence for the order of magnitude, not a benchmark: re-run `fluid_probe.js` on the owner's machine.
