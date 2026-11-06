# J2 sync 2: the prototype has forked (ABS-0, status: held)

Baseline in the engine today: J2_Prototype `33aeeda` (see `j2-sync.md`). Two newer lines exist and neither contains the other:

| Source | What it adds over `33aeeda` | What it lacks |
|---|---|---|
| J2 prototype's own repository, `main` at `9200cf6` (PR #31 `template-library-fixes`, 9 commits) | engine fixes: router extend threshold, `parse_decision` negation, first page builder schema, template-library edits (`j2.py`, `j2_artifact_models.py`, `j2_template_lib.py`, `llm.py`, `j2_flow_test.py`; 234 added, 39 removed lines) | `GET /api/runlist`, `GET /api/changes`, the Run settings tab of the page |
| the copy `prototypes/j2` in the old repository (`e7800503`) | the two routes, the Run settings tab (appearance cards, searchable run list) | the PR #31 fixes |

Rule of the design (absorb-old-sutra.md risk 7): the prototype's own repository is the source of truth and the copy is used only when the change has
not reached it. Here the change has not reached it, and the two lines differ in five shared files, so vendoring either one now would drop the other's
work, and a hand merge of a file would make `VENDORED.md` claim a commit that never existed. **Nothing is re-vendored; the baseline stays `33aeeda`.**

What the owner (or the prototype's maintainer) has to do, once: land the Run settings change into the prototype's own repository on top of
`9200cf6`. Then ABS-0 is mechanical: `scripts/vendor_j2.py --source <checkout> --commit <sha>`, `scripts/port_j2_ui.py --check` (all anchors must
match), `scripts/record_api_shapes.py` for the two routes, expose them in `engine/views.py`, and the prompt goldens must not change.

No ABS package depends on ABS-0 for its code. The chat work leaves every vendored file untouched either way.
