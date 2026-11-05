# GAP-LIVE as built: live smoke with the real CLIs (G07)
Built: `scripts/live_smoke.py` (one module, about 1,190 lines), `tests/live/test_live_app_smoke.py` (32 tests, about 12 s, 1 of them `live`).
NOT RUN against the real CLIs (D8, owner away); checked with `--fakes` and the offline tests. No existing test was changed. Run it on the owner's go-ahead: `SUTRA_LIVE=1 scripts/py scripts/live_smoke.py --max-usd 5` (or `SUTRA_LIVE=1 scripts/py -m pytest tests/live -q -rs`).

## What it does
- Steps (ids for `--only` / `--skip`): doctor, suites, app, t1, followup, t9, t14, image, tools, budget. Report: `live-smoke-report.json` + `.md` in `--out`
  (default a new `/tmp/sutra-live-smoke-*` folder, kept); a real run also splices the markdown between `<!-- live-smoke:begin/end -->` into this file (below the notes).
- The ceiling: `Meter` is fed by the usage sink of the app (the engine's calls arrive through the projector) and by a patch of `ModelConnector._spawn`
  for the direct calls (suites, image, tools, budget). Trips when usd > `--max-usd` or calls > `--max-calls`; a direct call is refused once the count is reached;
  `--max-minutes` (150) is a third limit. A trip stops the live tasks, closes the server, writes the report and exits 3 (1 = a step failed, 0 = clean).
- The eight open items of G07 are judged by `judge_items` (pure, tested): confirmed / fallback needed (with the switch) / not testable. `--fakes` marks all eight not testable.
- Evidence per run: time, calls, usd, tokens, atoms by state and by function, verify_failed by check (Atom log `body.verify.template`), touches_miss (trace.jsonl),
  Audit verdict (audits.json), site renders (static check, plus headless Chrome `--dump-dom` when a Chrome exists).

## Deviations from the specification
- Step order: T1, then the follow-up, then T9 and T14. The follow-up (step 5) IS the test plan's T13 (change request after the goal), so "T1, T9, T13, T14 as three short runs"
  is three direct runs (T1, T9, T14) plus the T13 follow-up of the T1 run. T1 runs at J2_BUDGET 40 (the plan says 200) and T9 at 60, to keep within the ceiling; T14 at 15.
- Added: a step `budget` (one Claude call with `--max-budget-usd 0.0005`; open item 6 has no other probe) and the limit `--max-minutes`.
- The pytest suites run IN this process (`pytest.main`), so a `live` test that calls `live_smoke` must skip `suites` (it does). The engine suite's own engine process is not
  metered while it runs; its usage events are read from its run folder afterwards and added.
- `--fakes` imports `tests/e2e/harness.py` (the queue-fed fake claude/codex, the stand-in Chrome, the new-team script) and runs J2's mock engine (`SUTRA_MOCK=1`) with
  the default budget 100 (the mock needs it). Fake cost is forced to 0 so `--max-usd 0` holds. In a dry run the `suites` step only collects the four files.

## Decisions
- D-LIVE-1: the reply-class item is `confirmed` when at most 10% of the judged function atoms ended verify_failed by `reply-valid`, else `fallback needed` (loosen the L5 classes).
  The 10% is an arbitrary first threshold; G18 wants "near zero" before enforcement.
- D-LIVE-2: the follow-up is `fallback needed` (put `realization == 0` back in `rehydrate.py`) only when it crashes or is refused for rehydration; a stop or a pause says nothing.
- D-LIVE-3: the MCP probe asks for `sutra_chart_read` (reads the database, so it also proves G04). Item 8 (browsers) is always `not testable` and carries the manual Safari checklist
  of G10; item 6 is `confirmed` when the CLI stops at the limit and when it accepts the flag.
- D-LIVE-4: answers to Identity come from a fixed list (`ANSWERS`, the first one gives name, place, menu and hours), the last repeats, at most 6 per task; then the task is stopped.

## Known limits
- Codex usd is unknown (no rate card), so `--max-usd` guards Claude only; Codex is bounded by `--max-calls`. Tokens are reported per provider.
- The sink check runs after the call; the engine's calls reach it by the watcher poll (0.4 s), so a trip can overshoot by the calls of that second. Stopping the tasks follows.
- Never executed live: expect to fix a prompt or a timeout after the first real run (every wait has a timeout and a stop).

## Findings / needs
- `tests/conftest.py` skips a test when "live" is in `item.keywords`; the folder `tests/live` puts that word on every test in it. The test module therefore registers a small
  plugin while it is imported (finds the running config in the importing frame) that removes the folder-made skip from its UNMARKED tests, so the offline tests run in the gate.
  Better fix for the conftest owner: `item.get_closest_marker(marker)` instead of `marker in item.keywords`.

## Mutation check (one pass, copy in /tmp)
20 breakages (usd comparison, call comparison, before-call comparison, replayed row counted, stub row counted, no pre-call guard, run id prefix, trace type, recheck kept,
reply-rate comparison, inverted image verdict, splice replace, PNG colour order, exit code, answer repeat, follow-up verdict, browser and/or, fakes judge off, junit error,
skipped step): 20 killed at once, no survivor.
