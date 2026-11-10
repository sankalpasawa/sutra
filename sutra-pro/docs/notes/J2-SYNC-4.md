# J2 sync 4, the UI test tooling as built (lane E3a): the capture, the fixtures, the goldens and the page render tests
Built for `docs/design/j2-sync-4.md` 4.8 (E3.1 and the page_render part of E3.3), D137, D140, D141, D147, D148 and D150. The one J2 source is the folder `prototypes/j2` of this repository at commit `025e265c594564f47a2365874cd5a5cc5d0d20a6` (tree `21c67045fe3230c1ab9be381c2f21465ea91849c`, the studio redesign), extracted with `git archive`: nothing else is read, run or compared.

## Re-capture and check (every command from the project folder)
```
J2SRC="$(mktemp -d)"            # a new, empty folder, never inside the repository
git archive 025e265c594564f47a2365874cd5a5cc5d0d20a6 prototypes/j2 | tar -x --strip-components=2 -C "$J2SRC"
test "$(git rev-parse 025e265c594564f47a2365874cd5a5cc5d0d20a6:prototypes/j2)" = 21c67045fe3230c1ab9be381c2f21465ea91849c
scripts/py scripts/capture_j2_fixtures.py --j2 "$J2SRC" --commit 025e265c594564f47a2365874cd5a5cc5d0d20a6           # writes tests/ui/fixtures/j2
scripts/py scripts/capture_j2_fixtures.py --j2 "$J2SRC" --commit 025e265c594564f47a2365874cd5a5cc5d0d20a6 --check   # ok: 80 files equal a fresh capture
SUTRA_J2_CHECKOUT="$J2SRC" node --test tests/ui/js/page_render.test.js                                               # 53 of 53, J2's own harness included
```
J2's server runs on Sutra's own Python (`--j2-python` defaults to the one that runs the script, the shared virtualenv under `scripts/py`). Mock mode needs only the standard library and `pydantic`, which the venv has; it has neither `anthropic` nor `google-genai`, and J2 imports both inside the functions that call a live model (`llm.py`), so a capture never needs them. `--commit` records the pin in `MANIFEST.json` (an extraction is not a repository); without it `--check` still passes and says the commit was not compared.

## What a capture holds: 80 files, 1.41 MB, about a second to make
| Files | J2 route | n |
|---|---|---|
| `state`, `runs`, `runlist`, `changes`, `map`, `plan`, `plan-map`, `docs`, `library`, `catalog`, `run-templates`, `artifacts`, `artifacts-tree`, `artifacts-groups`, `board`, `story`, `audits`, `refs` (`.json`), `site-latest.html` | the same names under `/api/`, `/site/latest` | 19 |
| `doc-prd.html`, `view-site.html`, `view-goal.html` | `/doc/prd`, `/view?name=site/index.html`, `/view?name=goal.json` | 3 |
| `agent-<who>.json`: the five functions, `W-1`, `agent-unknown.json` | `/api/agent?who=` | 7 |
| `activity-<who>.json`: J2's six functions (the validator too), `activity-unknown.json` | `/api/activity?who=` | 7 |
| `record-W-1` to `record-W-6`, `record-art-Website` | `/api/record?sec=` for each of `state.studio.parts`, `?art=` for each deliverable of `/api/artifacts` | 7 |
| `ask-<who>.json`: the six functions | `POST /api/ask` with one question, "Which AI calls did you make, and why?" (J2 answers from the records in mock mode: `from: records`) | 6 |
| `previews`, `preview-replies`, `render-docs`, `maps` | derived: the harness inputs | 4 |
| `golden-<key>.json`: 25 keys and `layout` | J2's two harnesses on J2's own page | 26 |
| `MANIFEST.json` | commit, brief, clock, harness, size and sha256 of every file | 1 |

The run is the Brew Lab brief of the first capture: `status` waiting for the owner's answer, `total` 48, `versions` 5, six workflows, `state.json` 121,902 bytes (limit 150,000). Not captured: `POST /api/settings` (the Decide for me switch changes the live run and answers with the switch's own value), `/doc/hld` and `/doc/lld` (the same "not written yet" page as the PRD for a website run), and the refusals of `/api/ask` and `/api/record`.

## Why two captures are the same, and why J2 stays as it is
- J2's process runs in a scrubbed environment (no key, token or `J2_*` setting of the developer) under a frozen clock, with a scratch home, runs folder and memory files; node runs J2's render harness twice with `Date.now()` frozen at the same instant (`--require`), and the capture stops unless the two outputs are equal.
- The extraction is proved untouched: `git status` when it is a repository, and a sha256 of every file before and after when it is not (a stray write names the file).
- R5: J2's seed library index records, for six of its own development runs, the home folder of the machine they ran on, and `/api/catalog` passes the field through. The capture makes those six values `not recorded` (the rule of patch P15 for the vendored seed, so the catalog fixture equals what the app answers for the same library) and refuses any finished file that still holds the absolute home folder of a macOS or Linux user. This is the one change to J2's bytes.

## The harness inputs and the goldens
`render-docs.json` feeds J2's harness from J2's own routes: `docs`, `map`, `railtabs` (the page's rail panel, the Map's own tab left out as J2's flow test does), `plan`, `planmap`, `activity` (Adaptation's feed: calls, messages, plans, judgements, revisions), `changes` (empty here: the brief has no change request), `journey` (true), `msgs` (the chat), `arts` (the studio's output tabs read `/api/artifacts`), `artifacts` (`tree` and `groups`) and `agent` (Identity). The 25 goldens are the seven of the first capture, `finish`, `journey`, `journeyhtml`, `sframe`, `needids`, `railst`, `planmap`, `msgfns`, `feed`, and the studio's `teamwork`, `plan`, `team`, `status`, `views`, `files`, `parts`, `tabs`, `inline`. Two are empty in this run: `finish` and `files` (they fill once a run is done), so the finish card is checked by a test that gives the harness a finished state. `sframe` is `/site/v5?x=1` at this pin (the time no longer reaches the address; the clock stays frozen anyway).

## `tests/ui/js/page_render.test.js`: 53 tests, under a second
The ported page and J2's goldens agree on all 25 keys (the E13 wording applied), the harness prints J2's 39 keys in J2's order, and, with `SUTRA_J2_CHECKOUT` naming the extraction, J2's own harness on J2's own page equals the ported page on every key. The E13 pairs are read from `scripts/port_j2_ui.py` and each must be in the page as often as the script counts, the old words nowhere. Behaviour of the edits: the page's first calls and the team added once (E4; a saved run also asks `/api/changes`), the finish card's links (run first, team last), E5 and E7 (the strips), E2 (three preview frames, all sandboxed without `allow-same-origin`), E20 (`libHref`, `runHref`, `CAT.on`: the team's paths, J2's own without a team), E21 (`loadFeed` hydrates before it paints, and paints when the module fails or is absent), E22, the feed's thinking input, `showTab` for the two Sutra panes, and J2's native Run settings (list, filters, search, escaping, `viewHref`).

## Choices beyond the design (for lane G to number)
1. The capture takes an extraction and `--commit` (D136's extraction rule applied to the fixtures); the Python is Sutra's own.
2. R5 scrub and guard of the fixtures, as above.
3. More goldens than 4.8 lists: `railst`, `planmap`, `msgfns`, `feed` and the nine of the studio harness; `activity-unknown.json`; `record-*`, `doc-prd.html`, `view-*.html`; a node clock frozen in the capture and in the tests.
4. The strip in the Simple view is `steamstrip` (not `shome`: the studio has an element with that id); lane e2's `sutra-panel.css` must style `.steamstrip`.

## Motion (D122, design 4.9): not in this lane
The probe and its numbers belong to lane e3b (`tests/ui/fake_backend.py` and the browser). Paste them here at integration, beside the D122 table:

| State | Gaps over 20 ms per 400 ticks | Overrides in `sutra-panel.css` |
|---|---|---|
| (to fill: the five states of 4.9) | | |
