# GAP-E2E as built: end-to-end scenarios with the real app, the real engine process and the stub or fake-CLI connector (G05)

## Built (`tests/e2e/`, 32 tests incl. 1 slow; default set about 50 s, slow test +35 s)
- `harness.py`: `LiveApp` (real `create_app` + `ProcessLauncher` on a temp data dir, uvicorn in a thread on a free port, token header, `SseRecorder` thread
  that keeps every SSE frame, `stop()` = the owner closes the app, `crash()` = the server dies without its ladders, `kill_engines()`), `Journey`/`run_new_team`,
  reply builders for the scripted chat agent, `FakeCliBin` (fake `claude`/`codex` fed from a reply queue), `ControlledClock`, `pid_alive`, `atoms_left_open`.
- `test_scenario_new_team.py` (12, steps 1, 2, 4, 5, 6, 7), `test_scenario_fake_cli.py` (2, step 3: claude through `AsyncConnector`/`Router`; quota -> codex),
  `test_scenario_followup.py` (6), `test_scenario_restart_stop.py` (6 + 1 slow), `test_scenario_parallel.py` (4), `test_cli_boot.py` (1, a real `python -m sutra_app`).
- No existing test of another package was changed.

## Deviations from the specification
- Chrome: not `SUTRA_HOOKS`, and not absent either. Without a Chrome J2's render check says "the browser check didn't run" and the run can never pass Audit (it pauses
  with a question), so `J2_CHROME` names a tiny stand-in executable (`harness.FAKE_CHROME`) that answers J2's two wrapper pages like a clean page. J2's check code and the default hooks run as in production.
- Follow-up scenario: GAP-E1B is merged, so a finished DOCUMENT CHAIN is continued ("Continuing from run ..."), not started fresh. The fresh fallback with the fixed system line and
  `upstream/<old run>/` is tested with a STOPPED source instead. Realization stays on (off changes J2's mock script); the mock follow-up then pauses with J2's known "keep going or finish as it is"
  question (mock Adaptation sends no `estimated_resources`, E1 notes) and the test answers "Option 2" in the department chat.
- "A hung engine is declared crashed after 30 s of silence": a live silent process is only FLAGGED by the watcher ("no signal for N s" on the step node); the crash verdict and the ladder
  belong to the next start (`reconcile`). The test does both with `ControlledClock.jump(40)`; the slow test waits the real 31 s with no clock hook.

## Decisions
- `create_app` cannot take a `ConnectorConfig`, so the harness swaps `wiring.build_connector_router` for the duration of `create_app` (real router, fake executables). The engine of those tests plays
  the mock through `SUTRA_MOCK=1`; the fake CLI call log proves it made no model call.
- `FAKE_REPLY_JSON` is one value per process but a chat turn makes three different calls, so `FakeCliBin` wraps each fake in a script that pops the next reply from a queue (probes and `--help` take none).
- `crash()` sets `services.stopped = True` before uvicorn stops, so the lifespan runs no ladder and settles nothing; the engine processes live on (own session), as after a real kill -9 of the server.
- Slowed runs (`STUDIO_MOCK_DELAY`) make the mid-run kill and the parallel test overlap for real; max-runs is sampled every 20 ms (peak 2, never 3).
- A killed server's engine becomes a zombie of the test process (its reaper loop is gone); `pid_alive` reaps it before it calls `kill(pid, 0)`.
- Harness hygiene: uvicorn empties the `uvicorn.access` logger when `access_log` is off; `LiveApp` puts it back at stop, or `tests/ops/test_logsetup.py` fails when it runs after the e2e suite (found by the merge gate).

## Known limits
- Chrome/browser behaviour (`behavior`, screenshots) is not exercised: the stand-in gives no answer to those wrappers, as the E7 recordings. Real Chrome and real CLIs are GAP-LIVE.
- The CLI test runs without the stand-in Chrome (the launcher does not pass `J2_CHROME`): its run only has to reach Identity's question.
- The SSE recorder does not reconnect; `Last-Event-ID` and the browser resync are GAP-E2E-UI.

## Findings for other packages
- Every mock run prints `record_rejected workflows.json: 0: version: Input should be greater than or equal to 1` on stderr (records validator vs J2's workflow rows): GAP-TUNE / records owner.
- After a stop (or a crash) the team's unanswered question stays in `GET /api/needs-you` until the owner writes in the team chat (`_follow_up` answers it and keeps it as framing). By design, but the UI may want to hide it.
- A run answered by hand-written inbox lines (server down) leaves the question unanswered in the database after the next start settles it; harmless, noted.

## Mutation check (one pass, copy in /tmp)
14 breakages (max_runs off by one, stop without `abandon_open`, reconcile never re-attaches, reconcile skips the ladder, continuing line reworded, follow-up never seeded, usage rows lose the atom id,
default hooks fall back to plain, no CSP header, shutdown skips the task ladders, silent flag never set, no codex fallback, empty digest in the assign prompt, inbox numbering): 12 killed at once; 2 survived
(the engine's own books were hidden by the projector's server-side abandon; the test compared the line with the same module's constant) and got `atoms_left_open` and the literal wording; both killed after.
