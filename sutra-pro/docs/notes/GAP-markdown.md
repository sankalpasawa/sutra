# GAP-markdown as built: a model's direct reply reads as formatted text

The two verified gaps of the key "markdown" overlap (both ask for a safe markdown renderer for the direct chat), so they are built once.

## What the owner sees
- In "Ask the model" (a team's node panel) and "Ask directly" (Home), a model's reply is drawn as paragraphs, numbered and bulleted lists (nested,
  numbering kept across blank lines), a code block in a box that scrolls sideways, a table that scrolls sideways inside its bubble (never the page),
  headings, quotes and rules, with **bold**, *italic*, ~~struck~~ and `code`. Before, it showed literal backticks, pipes and hyphens.
- The streaming row ("Claude is writing...") is drawn the same way while the reply arrives. An unfinished code fence is already a code box, and a
  table row is held back until the table can be drawn, so the row does not reshape when the fence closes or the separator arrives.
- Every other line is drawn exactly as before through `ChatView.safeText`: the owner's lines, a team's Identity, Sutra's lines, notes, error lines
  (also the error line of a direct turn) and cards.

## Where
- New `sutra_app/ui/static/js/chat_markdown.js` (`ChatMarkdown`, one global, `module.exports` in node, plain ASCII):
  `render(text, {streaming})`, `hold(text)`, `fenceAt(text)`. Escape first: control characters are dropped and the whole text is escaped before any
  markdown is read; every tag in the output is authored by the module (`p br strong em del code pre h3-h6 ul ol li blockquote hr table thead tbody
  tr th td`, wrappers `div.cmd` and `div.cmd-tw`); the only attribute value taken from the text is an ordered list's `start`, digits only. The
  output is well-formed XML.
- Riders (small and local):
  - `ui/static/js/chat_view.js`: `directReply(m)` (agent, kind text, `turn` set) and one branch in `transcript()` that calls
    `root.ChatMarkdown.render` when the script is on the page, else `safeText` as before; the header comment.
  - `ui/static/js/chat_pill.js`: `indicator()` renders with `{streaming: true}`; `partial()` cuts the 4 000-character tail at a line start and, when
    the part that is cut off leaves a fence open, starts the kept part with that fence again (`bounded()`).
  - `ui/static/css/sutra-panel.css`: a `.cmd` block inserted after the streaming-row rules (J2 tokens only; contrast test green).
  - `ui/pages/home.html`: one script tag before `chat_view.js`. `ui/static/js/dept_ext.js`: `"chat_markdown"` added to the injected list, so the
    frozen `pages/j2_ui.html` is not edited.
  - `docs/design/ui.md` (4.3 rule, the module list, the node test table), `docs/design/absorb-old-sutra.md` (a row in 2.3).
- Tests: `tests/ui/js/chat_markdown.test.js` (36), `tests/ui/test_chat_markdown.py` (3 static checks, plus 2 real-Chrome layout checks run with
  `SUTRA_BROWSER=1`).

## Decisions taken here
1. **No links.** The two verified items disagreed: one keeps ui.md 4.3 ("no links, no HTML"), the other wants http(s) links that open in a new tab.
   Links are not made: the rule is the design's, the pages make no external URL (tests fail on an external `href`), and a model's link is a new
   click-through surface on an offline app. `[label](url)`, images and bare addresses stay as plain text the owner can select and copy. The
   old app's DECISION callout is not ported either.
2. Markdown applies only to a direct reply (`ChatMessageOut.turn` set) and the streaming row. Team, Sutra and J2 lines are code-written or
   J2's own and keep `safeText` byte for byte; the existing `safeText` tests ("and nothing else") still hold.
3. A direct reply keeps a leading `@name`. `stripTag` drops J2's agent-to-agent address; a model reply that starts with `@dataclass` is not one.
4. Markdown heading levels 1 to 6 are drawn as h3 to h6 inside a bubble, so a reply never adds an h1 or h2 to the page outline.
5. A single line break is a `<br/>`, as in `safeText`. An unclosed fence runs to the end of the text, both while streaming and once stored.
6. A fence inside a list item ends the list and the next item continues with `start`, so the numbering is right. This is simpler than
   CommonMark's nested containers.
7. `hold` is stricter than the old `withholdPartialRow`. It also holds a finished header line whose separator has not arrived, because the old
   rule still let the table jump once.
8. Bounds: one pass per line and no backtracking regular expression; lists 6 deep, quotes 4 deep, tables 50 columns, rows never padded. The
   tests render 25 hostile inputs (most of them 100 KB), each well under a second.
9. A table keeps its natural column widths up to 48em and scrolls in its wrapper. In a narrow bubble the columns are not squeezed to one word
   per line.

## Not done, and why
- Links, images and HTML (decision 1). No syntax highlighting and no copy button on code: the old chat had neither.
- Simplifications of CommonMark: there is no delimiter-run algorithm, so a mix like `**bold *italic***` stays literal (bold inside italic and
  italic inside bold both work). A change of bullet character does not start a new list. Setext headings (`===`), indented 4-space code
  blocks and task-list checkboxes stay as text.
- The optional rider of the second item (Home's `renderChat()` keeping the reader's place, with a "new messages" chip) is not built here.
  Transcript scrolling belongs to the chat-comfort package.
- No case is added to `tests/ui/test_view_panel.py` or `tests/ui/test_home.py`, because those files are other packages' areas in this merge.
  The layout is proven instead by `tests/ui/test_chat_markdown.py`, on the real `j2.css` and `sutra-panel.css`, in Chrome at 390 px: the page
  does not scroll sideways, the code box and the table scroll inside the bubble, and both themes read.
- `docs/DECISIONS.md` is not edited (see Needs).

## Tests run
- `node --test tests/ui/js/chat_markdown.test.js`: 36 pass.
- `node --test tests/ui/js/*.test.js`: 697 tests, 695 pass, 2 skipped (the existing opt-in J2-checkout checks), 0 fail.
- `scripts/py -m pytest tests/ui -q -p no:warnings`: 743 passed, 174 skipped (browser-gated).
- `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_chat_markdown.py`: 5 passed.
- `scripts/py -m pytest tests/test_packaging.py tests/test_layout.py tests/contracts/test_contract_route_table.py`: 28 passed, 1 skipped.
- With `SUTRA_BROWSER=1`, `test_dept_page.py`, `test_view_panel.py`, `test_home.py` and `test_fake_backend.py` fail on the base commit as
  well, because the fake backend does not serve `/api/chats/{sid}/providers` and other newer routes. The failures were compared in two runs:
  every failure on this branch also fails on the base, so this package adds none.

## Needs (for the scheduler, who edits the chassis files)
- A decision row. Proposed text:
  "D116 - A model's direct reply is drawn as safe markdown; links stay text.
  Sources: the old app's `mdHtml` (02-helpers.js) and `withholdPartialRow` (01-state.js); ui.md 4.3; D115.
  Decided: `chat_markdown.js` renders only a direct reply (`turn` set) and the streaming row. It escapes the whole text first and writes only the
  tags it authors. Paragraphs, lists, fenced code, tables, headings (as h3 to h6), quotes, rules, bold, italic, struck and code are drawn. No
  link, no image, no HTML.
  Why: a model's answer with code or a table was unreadable, and every other line keeps the three marks of `safeText`.
  Rejected: http(s) links with an allowlist (an external click-through surface on an offline app); markdown for every line (team and J2 lines
  are J2's own); a markdown library (no dependency, no CDN).
  Diagram: key only, label 'direct reply as markdown (D116)'."
  The number is the scheduler's to give, because the packages merged beside this one may take D116 first.
- Merge: chat-comfort and attention also extend the list on `dept_ext.js` line 138. Take the union of the names.
