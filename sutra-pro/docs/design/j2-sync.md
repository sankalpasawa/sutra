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
