# J2S6-l as built: library records, seed sync, schemas, lane L

Owns `sutra_app/library/**`, `docs/schemas/**` (by the export only), `sutra_app/ops/doctor.py` (and the seven lines of `ops/cli.py` that print the
`config sync-library` report), `tests/library/**`, `tests/ops/**`, this note. Spec: `docs/design/j2-sync-6.md` D185, D186 and lane L;
`docs/design/shared-library.md` section 7. Paths are relative to `sutra-pro/`. Base: `lane/s6-library-docs`; `lane/s6-v` (V-core, `42f76ad6`) is
merged in, so the vendored tree and the new seed (437 files) are the ones the tests use.

## What was built

- **L1 records (D186).** Every key was found by validating mock runs of J2 1adb8ecd in strict mode, not by reading the design:
  - `reuse.json` has its row in `ROUTES` (`artifact_reuse`, J2's `artifact-reuse/1`): `ArtifactReuse`, `ReuseDecision`, `ReuseSource`, all closed.
  - `TemplatesFile` gains `run_template` (`RunTemplateUse`) and `auto_reuse` (`AutoReuse`, `AutoScore`). `TemplateDecision` gains `run_template`,
    `from_template`, `template_workflow`, `adapted_from`, `new_family`, `first_refused`, `nearest`, `nearest_refused` and `door` (the last is in the
    design and was not seen in any mock run; `first_refused`, `nearest` and `nearest_refused` were found in J2's `route()`).
  - `TemplateMeta` gains `renamed_from`, `adapted_from` and also the four sync 4 provenance keys (`made_by` with `date`, `business`, `mock`,
    `collected_from`): a run's copy of a library version carries them, and the design did not list them.
  - `MessageMeta` gains `humans_only`, `run_template`, `content_door` (62 keys become 65).
  - The first line of `chat.jsonl` is now a closed `RunHeader` (payload `run_header`; `by` is a name, never a path). The design says "checked against
    `RunMessage`"; the header is not a message, so it has its own model. It was open JSON before.
  - `RunTemplateBundle` (payload `run_template.bundle`, a `Value`, not a family record) is J2's `run-template/1`, with every check J2's own model makes.
    `RunTemplate` of `templates.py` keeps its name and gains `group` and `kind_shown` (`reuse_rows`), which V's golden of `GET /api/run-templates` holds.
  - `wire.py`: `ArtifactRow.reused_from` (`ReusedFrom`), written by `j2_artifacts.rows` when the content door served a section.
- **L2 export.** `python -m sutra_app.library.export` wrote `artifact_reuse`, `run_header`, `run_template.bundle` and changed six more files; `--check` is clean (46 files).
- **L3 seed sync (D185).** `_apply_seed` also syncs `run_templates` (`_apply_run_templates`): per seed id, present (left alone), restore (row but no folder),
  adopt (folder with the seed's `template.json` id and `made_from_run`, no row), skipped (any other folder; no seed folder; an id that is not a slug),
  add (folder copied, row appended); rows in J2's order (name, case-insensitive); the key is written only when a row is added. `_fill` adds `renamed_from` and
  `adapted_from`. The report has `run_templates` and `renamed` (version -> `name@N` it was renamed from; an added version only). `missing_seed_run_templates`, the
  doctor check (`library`: "N seed run template(s)") and `config sync-library` count and name them. No folder is moved or renamed.
- **L4.** The four seed run templates validate against `RunTemplateBundle` (`test_lib_reuse.py`).

## Measured

- Old library = the sync 5 seed (32 families, 39 versions, 157 files, 0 run templates, 8 runs). Synced with the shipped seed: 81 families, 107 versions,
  4 run templates, 437 files, 49 new families, 67 versions listed as renamed, 3 runs added, 0 skipped, 0 files lost, only `index.json` changed,
  every old row still there with its sha, 0.15 s. A second sync changes nothing byte for byte; a new install gets the whole seed (snapshot equal).
  The old families (for example `still-point-yoga-components`) stay where they are and the renamed family is added beside it, so one spec sha is held by two families
  (D185's accepted cost). `provenance filled` is 0: the sync 5 seed already carried the sync 4 keys, and none of its rows lacks a key the seed has.
- Six mock runs of the vendored engine (`tests/library/reuse_runs.py`: flags off, `J2_AUTO_REUSE`, content door three times, a run template chosen by name with two
  workflows), 10 s together: strict mode accepts every file (about 2,100 records), `reuse.json` appears only with the door on, `templates.json` only with the library on.
- Tests: `tests/library tests/ops tests/test_ownership.py tests/test_docs.py tests/test_traceability.py` 3,070 passed, 4 skipped.

## Decisions (text for `docs/DECISIONS.md`, in number order; amendments of the design's D185 and D186)

## D185 — The seed sync adds run templates, their folders and the two provenance keys; it stays additive
- Sources: D144, D26, `ops/doctor.py` `_apply_seed`, `_fill`, J2 seed (`run_templates`, `renamed_from`, `adapted_from`).
- Decided: `_apply_seed` also syncs the index key `run_templates`, per seed id: the library has row and folder (present: left alone, its `used_by` is the library's own),
  the row only (restore: the seed's folder is copied back), the folder only (adopt: its `template.json` is the seed's, by id and `made_from_run`; any other folder is
  reported and kept), neither (add: folder `library/run-templates/<id>/` and row). An id that is not a slug, a seed row without a folder and a `run_templates` value that is not a list
  are reported `skipped`. `_fill` adds `renamed_from` and `adapted_from` to a present version's row and `meta.json` when absent, never changes one that is there. A seed family
  J2 renamed is added under the seed's name beside the old one (nothing is moved or renamed on disk) and its added versions are listed in the report's `renamed`. The report
  gains `run_templates` and `renamed`; `missing_seed_run_templates`, the doctor check and `config sync-library` count them. A first run and `_seed_whole` copy the whole seed; the
  marker (`.seed-sync`, the sha of the seed index) changes with the seed index, so an install syncs once at its next start.
- Why: existing installs must gain what is new without losing what they made; J2's resolver already opens an old reference through `renamed_from`.
- Rejected: following J2's renames on disk (changes what an old run points at); skipping a version whose sha exists under the old name (the new J2 routing and the seed's run templates name the new family).
- Diagram: label "seed library: + run templates", pill on Template library.

## D186 — The records catalogue and the closed models learn the new run files and keys; J2's run-template bundle is `RunTemplateBundle`
- Sources: D47, D172, D151, `docs/design/library.md` sections 9 and 10.
- Decided: `records.py` has a row for `reuse.json` (`artifact-reuse/1`, closed `ArtifactReuse`). `TemplatesFile` gains `run_template` and `auto_reuse`; `TemplateDecision` gains `run_template`,
  `from_template`, `template_workflow`, `adapted_from`, `new_family`, `first_refused`, `nearest`, `nearest_refused`, `door`; `TemplateMeta` (closed) gains `renamed_from`, `adapted_from` and the provenance
  keys of a library version (`made_by` with `date`, `business`, `mock`, `collected_from`); `MessageMeta` (closed) gains `humans_only`, `run_template`, `content_door`; `RunTemplate` (a row of
  `GET /api/run-templates`) gains `group` and `kind_shown`; an artifact row gains `reused_from`. The first line of `chat.jsonl` is a closed `RunHeader` (`by` is a name, never a path). The new closed class
  `RunTemplateBundle` (payload `run_template.bundle`, J2's `run-template/1`) validates `library/run-templates/<id>/template.json` with J2's own checks; the existing `RunTemplate` keeps its name.
  `docs/schemas/` is regenerated by the export. Each key was found by strict-mode validation of mock runs of the vendored J2 with the flags off, on and with the content door; a test repeats that
  (`tests/library/test_lib_reuse_runs.py`). Default log mode only warns; strict mode is what the tests run.
- Why: the library's closed models are what makes `GATE.check` mean something; every key J2 adds and the model refuses is a strict-mode failure of a run.
- Rejected: leaving the new files in `UNCHECKED` (D172's reason); renaming the existing `RunTemplate` (a published payload name and schema file); checking the run header as a `RunMessage` (it is not a message).
- Diagram: label "records: reuse, run template bundle", pill on band:DEPARTMENT RUNTIME.

## Deviations from the design

- `TemplateMeta` and `RunTemplate` and the artifact row gained keys the design did not list (above); `RunHeader` instead of "checked against `RunMessage`"; `RunTemplateBundle` is a payload, not a record family.
- `tests/ops/fixtures/seed-sync5/` (157 files, 816 KB) is new: the sync-4 and sync-5 tests now take the sync 5 seed from it (`sync5_seed` in `tests/ops/conftest.py`, a monkeypatch of `doctor.seed_dir`)
  instead of from the shipped seed, because the shipped seed no longer is that seed. Their assertions are unchanged except the report keys (`run_templates`, `renamed`) and the fixture's name.
- Two other edits of existing assertions: `tests/ops/test_doctor.py` (the ok text of the library check) and `tests/library/test_lib_chat.py` / `test_lib_records.py` (65 meta keys; the header's family is `run_header`).
- `ops/cli.py` is not in the design's list for lane L; two `if` blocks print the new report keys of `config sync-library` (and the "filled" line is as before).

## For the integrator

- `tests/library/test_lib_reuse_runs.py` runs `reuse_runs.py` in a child with the vendored engine: if lane E changes the engine's environment reads or `LOCKED` settings, it still needs only the J2 variables it sets itself. If V's later commits move the seed, `test_seed_sync_shipped.py` pins 81, 107, 4 and 67 renamed on purpose; change them in the commit that moves the seed.
- The flag-on mock runs used `J2_REALIZATION=0` (the classic path, as J2's own flow test does). The realization path with the flags on was not run here.
- Add to the diagram key and `DECISIONS.md`: D185 and D186 above (they replace the design's text of the same number). Nothing for `ENVIRONMENT.md` from this lane.

## For J2's maintainers (reported, not patched)

- `library/index.json` rows of renamed families keep the old name only in `renamed_from`; a family list that shows both the old and the new family for one spec sha has no field that says which one is current. A `superseded_by` on the old row would let hosts hide it.
- `meta.json` of a run's copy of a library version carries the library's provenance (`made_by`, `business`, `mock`, `collected_from`): `docs/` of J2 names none of them as run file keys.
- `TemplateDecision.door` is described in the design; no run of J2 1adb8ecd writes it into `templates.json` (the content door's decision is in `reuse.json` only).
