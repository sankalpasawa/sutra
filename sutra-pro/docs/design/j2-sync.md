# J2 sync: what changed in the prototype after the design baseline

The design was written and measured against J2_Prototype `ce2631f` (2026-11-03). On 2026-11-04 the prototype's `main` moved to
`33aeeda` (PR #30 `template-library`, 3 commits, 5 files, +189/-17). **The vendoring baseline is now `33aeeda`.** Line numbers quoted
in the design (`j2.py:n`, `j2_ui.html:n`) are those of `ce2631f`: locate by symbol or anchor text, not by line (in `j2.py` everything after
line 8313 moves down by 7). `VENDORED.md` (E1) records the real commit and the sha256 of every vendored file.

## The change: a run keeps its own copy of every template it used
- `j2_template_lib.py`: new `FILES`, `load_dir(d)`, `run_tpl_rel(rec)`, `run_saved_dir(run_dir, rec)`, `save_into_run(run_dir, rec, t=None)`,
  `run_templates(run_dir)`, `_source(run_dir, d)`, `_library_view_of(...)`; `template_view(..., run_dir=None)` now serves the run's own copy
  first (`"source": "from this run"`), then the library (`"from library"`), else a stub (`"not recorded"`); `load()` is built on `load_dir()`.
- `j2.py` (J2Run, template routing, about line 8316): after a routing decision is saved, each new decision gets `saved` = the path of the run's
  copy relative to the run folder (`templates/<artifact>/<section-slug>/<slug>@v<N>/` holding `spec.json`, `model.py`, `schema.json`,
  `meta.json`), written once per version; a failure never blocks the run: `saved` is `None` and a system event `template_save` is logged.
  Only when `J2_TEMPLATE_LIBRARY=1`.
- `j2_server.py`: `GET /api/library/<artifact>/<section>/<slug>/v<N>` passes `run_dir`; `GET /api/run-templates` returns
  `j2_template_lib.run_templates(run_dir)`: each decision plus `source` ("from this run" | "from library" | "not recorded").
- `j2_ui.html` (Library view, `renderLibrary` and `renderTplViewer`): a "From" column in the routing table and the source in the viewer header;
  a "not recorded" notice when neither the run nor the library has that version. None of the 12 page edits of the UI port touches these lines
  (the port script's per-edit counts and `--check` prove it at port time).
- `j2_flow_test.py` (+67 lines): checks for the above; E5 vendors it as part of the legacy suites.

## What it means for the work packages
| Package | Needed |
|---|---|
| E1 (vendor J2) | Take the files from `33aeeda`; record that commit in `VENDORED.md`; patches P1-P11 are located by anchor text. The new `save_into_run` writes inside `self.dir` (the run folder), which is already the engine's contract. |
| E2 (views) | The two handlers above change: `/api/library/...` passes `run_dir`; `/api/run-templates` answers `run_templates(d)`. Record the new API shapes in the goldens (`api_shapes.json`). |
| E5 (legacy suites, goldens) | Use the `33aeeda` copy of `j2_flow_test.py`; prompt goldens are unaffected (no prompt changed). |
| L7 / L8 (templates, record catalogue) | `templates.json` decisions carry a new optional key `saved` (str or null) and `/api/run-templates` adds `source`; a run folder now holds `templates/<artifact>/<section-slug>/<slug>@v<N>/{spec,schema,meta}.json + model.py`. The closed models and `gate_record` must accept them (log mode first, as for every J2 record). |
| UI-2 (port of the J2 page) | Port from `33aeeda`; run `scripts/port_j2_ui.py --check`: all 12 anchors must still match with the stated counts (they did on a read of the diff). |
| Orchestrator / projector | No change: the run folder is the engine's; the copies are files the Library tab reads through the engine's routes. |

Diagram: the Template library box can say "each run keeps its own copy" (next diagram version, with D88 to D90).

## Later syncs (see `j2-sync-2.md`)
- 2026-11-06: baseline moved to `9200cf6` (PR #31 `template-library-fixes`): `parse_decision` negation, the extend-under-0.5 overrule, the first page builder's inline definitions, the refused-schema report. `j2-sync-2.md` lists where each is covered.
- 2026-11-06 (sync 3, `j2-sync-3.md`): the Run settings tab, `GET /api/runlist` and `GET /api/changes` landed from the old repository's copy of the prototype as patch P13 and page edits E14 to E18 (D114 allows it); J2's own repository still does not have them.
- 2026-11-10 (sync 4, `j2-sync-4.md`, ships as 0.3.0): the source is the folder `prototypes/j2` of this repository at `025e265c` (tree `21c67045`, the Studio redesign), the only J2 source from here on (D136, D153, D154): 208 files and 17 code modules (`j2_agent_models`, `j2_agent_views` and `j2_studio` are new), patches P1 to P5, P7 to P12 and P14 to P16 (P13 retired into `engine/runlist.py`, P15 a data patch on the seed, P16 Decide for me's `settings.json`), the page re-ported with 33 edits, the shared library under the team at `/d/{dept}/library`, a function's answer as a turn of its own session (D147 to D149), the late judge on, and a seed sync that delivers new versions without overwriting (D144). The Simple-view redesign that sync 3 left pending is part of the pin and is ported (D137); `build-on-run` (a design document, no code) and `backend-builder` (not in the copy) stay pending.
- **Pending, not vendored:** J2 branch `build-on-run` (`80f8704`): a design for "build on a run" (fork a finished run with a new brief through `J2_CHANGE`), `docs/build-on-run-design.md`, 552 lines, no code. When it is implemented in the prototype it needs its own sync note: a new entry point in `J2Run`, a new route and probably a patch beside P11 (`rehydrate`).
- **Pending, not vendored:** J2 branch `backend-builder` (5 commits, tip `7cce55c`): the Backend workflow (`j2_backend.py`, `agents/j2/backend.md`, API-endpoint and data-model LLD templates, `templates/backend/generic.json`, `rates.json`, `j2.py` +722, `docs/backend-design.md`). Not on J2 `main`. After it merges: add its files to `vendor_j2.py`, re-derive P1, P2, P7, P8, P10 and P12 by anchor, re-record the prompt goldens through a recorded vendoring patch, and write a sync note.
- **Pending, raised to the owner and the J2 team:** the old copy's Simple-view redesign (landing with the Client Lead bot, journey, finish card, floating chat panel): not in J2's own repository, so not ported (`j2-sync-3.md`).
