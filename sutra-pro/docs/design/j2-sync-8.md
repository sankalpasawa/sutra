# J2 sync 8 as built: the engine takes J2 main `ee659fb5` (note of record)

_Status: As built on branch `sync-8` · Date: 2026-11-17 · Pin: commit `ee659fb54aec75bf7f5139516791aee20a0474fa`, tree `ddc9a7875b4e4d0d2d6af1d8f8764e1f0ddd2d37` · Page: unchanged (J2's page at the pin equals `133942b1`, ported in sync 7) · Decision D244._

## A. What moved

- **Engine** (`scripts/vendor_j2.py`, D244): 527 files, 11 changed. In from J2 main since `dee83d5c`:
  - Kaivan's reuse fixes (#205) and the review of 17 Nov. A rework is never served an old section; a section is served only when the documents before it match the source run's; another business's template is adapted only above `adapt_min_similarity`; the same job worded anew is reused (rule `j`); a source run that did not end workable is `build`. A workable run is saved as a run template by itself when run templates are on.
  - The dry-run fix (#206). A real run's command must pass every stated folder; a build that holds a real folder path is refused; the real folders are read before and after the dry run, and a change stops the run. Identity's charter lists only files the build produces; a charter file no workflow writes is a plan gap.
- **Builder tools stay off** (D240). The #206 code is carried, but J2 takes its section path in a live run, so a real run is not offered yet.
- **Page**: `port_j2_ui.py --check` is ok at the pin, with no anchor moved.

## B. Patch verdicts

| Patch | Verdict at ee659fb5 |
|---|---|
| P1 to P5, P7 to P12, P14 to P19 | applied unchanged |
| re-anchored | none |
| dropped | none |

## C. Where Sutra met the new J2

1. **The library's closed models** refused three new keys of a `templates.json` decision: `same_job`, `not_similar` and `fresh_start`. They are added to `TemplateDecision`. The new door rules (`rework`, `inputs-changed`, `same-job`, `same-job-facts`, `source-not-workable`) are free strings in `ReuseDecision`, so nothing changed there.
2. **The run-template host test**: with run templates on, J2 now posts "Saved run template <name>." when a run ends workable. The two tests that check the host adds no run-template line leave J2's own line out (`host_lines`).

## D. Tests that moved

- **Legacy flow test**: three-way merge (base J2 `dee83d5c`, ours the sync 7 copy, theirs `ee659fb5`), with 0 conflicts. One port edit: `dry_run_real_folders` reads its fixture through `page_file` and is `skippable`. `--fast` gives 119 ok lines, and 183 with an extraction.
- **New legacy copies**: `reuse_fixes_test.py` (97 checks) and `auto_save_test.py` (24 checks). They are carried for the reason D192 gives: the flow test doesn't exercise the library. Their sibling imports point to `sutra_app.engine`, and the library is the engine's seed library.
- **Scope**: `fixtures/dry-run-real/*` is excluded as J2 test data.
- **Goldens re-recorded from J2 at the pin**: the seven prompt goldens, the fn golden and `run_events.jsonl` (only Identity's system prompt changed: the new line of `identity.md`), and `api_shapes.json` (the commit only).
