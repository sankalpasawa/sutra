# SUT-27 — the centre panel shows any output, not only websites

Approved by the owner. Branch `sut-27-output-agnostic-result`, cut from `origin/main` at f21add06.

## Problem

The centre panel is built for websites. For scripts and reports it shows grey placeholder bars that never fill, "The page, version 3", "Open the site", and the actual output is not shown.

## Build now (UI only, no engine changes)

1. Same tabs for every project: Result, Files, How it was made. Result opens by default when the run is done.
2. Show files by type with generic viewers: HTML as a page (reuse today's page preview), text/markdown as text, code with line numbers, CSV/JSON as a table, images as pictures, anything else as download. No per-project-type screens.
3. Result shows the main output. Until the plan names a main result (coming with Kaivan's engine side, SUT-23), fall back to the run's single output if there is only one, otherwise the Files list. Never guess by file name.
4. Plan cards on "How it was made": each finished part shows its builder's one-line summary and its files. Grey bars only while a part is in progress.
5. Wording follows the output: no "site"/"page"/"Open the site" unless the result is a web page.
6. "Copy share link" does not share a result built from private data unless the user turns sharing on. Find what marks a run as private today; if nothing does, propose how.

## Owner decisions after the spec (2026-11-25)

- Item 6 is dropped. The share link opens only on this Mac, so the only change is the note "Link copied — opens on this computer only". No private-data detection, no sharing switch.
- Builder summary: the last builder message's human_output, any leading @name removed, first sentence, one line.
- Planned engine names (pending Kaivan's OK): main result is `result` on the real-run proposal (`workflows[].real_run.result` in /api/state), falling back to the type's entry_file. Real-run output is the stdout/stderr tails plus created/changed/deleted on the real_run receipt row, served by /api/artifacts/groups `real_runs`. The UI builds its hook against these.
- Download for a non-page run is per file, no zip. engine/views.py stays untouched; CSV/JSON are parsed in the page. The button keeps the name "Copy share link".
- Before the run is done, "How it was made" opens by default and Result shows a placeholder line. A web-page run whose only output is the site shows the site preview in Result.

## Owner decisions at plan review (2026-11-25)

- Plan approved. Developer starts at T1.
- Q-2: a website run's Result keeps showing the live site while it builds, as today.
- Q-3: "Copy share link" copies the main file's `/view` link instead of `/site/latest`.
- Q-1 (answered by Kaivan): the names are `workflows[].real_run.result` and the type's `entry_file`. `result` is a path inside the folder the real run works on (the user's folder), not the run folder, so `/view` cannot load it. Its text will come from `run_output/<receipt-id>.json` (Kaivan's P45; result text up to 64 KB), linked from the real_run receipt row as `run_output` (owner update; key pending Kaivan's OK). P45 does not exist yet: the UI leaves a hook only.
- Consequence for the main-result rule: `real_run.result` is never one of the run's outputs, so it is not matched against them. When a real-run result is named and its run_output link exists, Result shows that text; until P45 lands, that step is skipped and the rule falls through to the entry file, the single output, then the Files list.
- Known clash to raise with Kaivan: the approved real_run receipt row already has an `output` key, holding the last 1,500 characters of stdout+stderr (j2.py:949-952, spread at :6171). Owner update: P45's link goes in a new key, `run_output` (a string of the form `run_output/<id>.json`); the UI reads only `run_output` as the link and never interprets `output`, which stays the stdout+stderr tail. The row also has no top-level created/changed/deleted for the real run itself today, only `dry_run.{created,changed,deleted}` and the plan's `expect`.

## Later (plan for it, do not build)

When Kaivan's engine records a real run's stdout and files (SUT-28 / SUT-23): show "what changed in the folder" and "what the script printed" (folded) in Result.

## Design intent

Keep it simple: one main result, everything else folded or one tab away. Mocks (outside the repo, they contain a home path): `~/sutra-demo/mocks/sutra-result-before.png`, `~/sutra-demo/mocks/sutra-result-after.png`. The red line in "before" is an annotation: "report.txt, the file that was actually written to your folder, isn't shown anywhere." The "after" mock shows a real-run result (folder path, "1 file created", "What the script printed") — those parts belong to the Later section.

## Constraints

- Another session works on SUT-28 (real-run network, engine) in parallel. Do not touch engine real-run or sandbox code.
- Run only targeted tests; the full `scripts/gate.sh` is not free until the owner says so.
- Never install the beta without asking.
- Do not push. Commit as the repo git identity; no Co-Authored-By trailer.
- Decision numbers: D448 is the highest on every branch. SUT-28 will likely take D449, so this task uses D450 onward.
- No home paths or owner names in any file under `sutra-pro/` (`tests/test_ownership.py`).
