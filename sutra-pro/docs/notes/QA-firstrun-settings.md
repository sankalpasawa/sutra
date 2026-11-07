# QA firstrun-settings: thirteen reported bugs (found on commit 2ae63d11)

Branch `feat/sutra-pro-qa-firstrun-settings`. The first agent of this flow was cut off by a usage limit after two commits and one unfinished
edit; this round kept the finished work, finished the unfinished edit, and went through the rest in order of severity. Every bug that was
fixed here was reproduced first (QA's scripts and evidence, or a failing test), traced to its cause, fixed locally, and given a test that fails
without the fix. The J2 engine files, J2's prompts, routes and goldens were not touched.

## Summary

| # | Sev | Bug | Result |
|---|-----|-----|--------|
| 1 | P2 | The org chat's session state is shared by every data folder | Skipped here: owned and fixed by the direct-chat branch (see below) |
| 2 | P2 | The pill says "after your next message" and shows no picker after a provider switch | Fixed (`d4f2663d`, first agent) |
| 3 | P2 | A dead token shows "A valid X-Sutra-Token header is required" in most Settings groups | Fixed (`c1c9a151`) |
| 4 | P2 | Windows: the CLI file chosen in Settings is dropped at the next start; the box is worded for macOS | Fixed (`6e4a1266`, `e901b18b`) |
| 5 | P3 | Enter does nothing in any Settings field | Fixed (`b8145cc6`, placement `18a5a290`); Limits and Notifications are also covered by recurring-limits |
| 6 | P3 | "Saved." stays beside a new unsaved edit | Fixed (`19a1e9cf`) |
| 7 | P3 | Notifications cap 11 to 999 is saved as 10, 1000 is refused | Fixed (`b4b13262`) |
| 8 | P3 | An empty note shows pydantic's sentence | Fixed (`318531ac`) |
| 9 | P3 | `--offline`: red "Your saved choice could not be used" in Default model | Fixed (`b037b710`) |
| 10 | P3 | Offline demo: task labels start with "OWNER NOTES (facts and house rules" | Skipped here: fixed by the org-chat-teams and security-privacy branches (see below) |
| 11 | P3 | "(D7)" and "(D34)" are printed in owner-facing sentences | Fixed (`0fbbca32`) |
| 12 | P3 | Locked Engine fields say "edit data/engine.json" | Fixed (`ec4e2335`) |
| 13 | P3 | 33 Tab stops to reach Settings | Skipped (not trivial or safe, see below) |

## Fixed

### 2 (P2) The pill is read again when the chat's session moves
**Cause.** Home read `GET /api/chats/cs_org/providers` once and again only after a click on the pill; a reply (which pins the model and effort) and
`connector.switch` never invalidated it, so after a switch it kept the "can be chosen after your next message" note until a reload.
**Fix.** (`home.js`) A message of the org chat, a `connector.switch` of it and any fetch that brings new messages mark the pill stale; the pill on
screen stays until the new answer is in, a failed re-read keeps it, an older answer never replaces a newer one.
**Test.** `tests/ui/test_home_welcome_settings.py` (browser): the pickers appear after the chat answers on the other model without a reload, and a
switch of another chat does not re-read it.

### 3 (P2) A write refused with the dead token says to reload, in every group
**Cause.** Limits, the guard, Notifications, Engine, Default model, About and the Connectors Test print `e.message` of the ApiError; the server's
401 `bad_token` message names a header the owner cannot act on. Only Notes and the chat mapped the 401 to "Reload it from the app".
**Fix.** (`sutra_ctx.js failure()`) The ApiError built for a 401 `bad_token` carries "This page was opened without its access token. Reload it from
the app." with its status, code and details unchanged, so every view says it with no change of its own. Another 401 code, and a `bad_token` that
is not a 401, keep the server's words. The fake backend now answers the real server's words (`orchestrator/api/deps.py`), so the browser test
meets the bug; its own test of the 401 was updated to the real words.
**Tests.** `tests/ui/js/ctx.test.js` (two tests: the reword for three shapes of the server message; only the dead token is reworded);
`tests/ui/test_home_limits.py::test_a_write_the_heal_cannot_rescue_says_to_reload_the_page_beside_its_field_not_the_name_of_a_header` (browser:
Limits save, the guard, Notifications and About all say it and "X-Sutra-Token" is nowhere on the pane). Fails without the fix.

### 4 (P2) Windows keeps the CLI file the owner chose
**Cause.** `discover.connector_config()` returned early on Windows, before it read `bins.json`, so the file the page confirmed with "Using that
file." was applied to the running connector and forgotten at the next start. The box was also drawn with `/full/path/to/claude` and "In Terminal,
`which claude` prints the full path".
**Fix.** (`discover.py`) On Windows the stored choice is read as on a Mac (still no folder search there); a field handed in by a caller wins; a
vanished file is still ignored. (`bins.py`, `settings_view.js`, `home.js`) The box shows `C:\full\path\to\claude.exe` and "`where claude`" on
Windows, the refusals of `check_path` say `where` and "a drive letter, like C:\", and `~\` is the home folder. The Mac wording is unchanged. The
Windows flag comes from the browser's user agent (the page runs on the machine the app runs on), handed to the Connectors paint.
**Tests.** `tests/connectors/test_discover_windows.py` (6, run on every platform: they switch `oslayer.IS_WINDOWS` on where the machine is not
Windows); `tests/ui/js/settings_connectors.test.js` (Windows and Mac wording). The first two fail without the fix. Not run on a Windows machine.

### 6 (P3) "Saved." goes when a field of its group is edited
**Cause.** A group is not repainted while the owner types in it (`typingIn`), and only Limits cleared its flag in the state; the status line itself
was never cleared, and Engine and Notifications kept their flag.
**Fix.** (`home.js staleSaved`) Any `input` event in a Settings group clears that group's status line in place and the flag the next repaint reads
(Engine, Limits, Notifications, Notes, Recurring work).
**Test.** `tests/ui/test_home_limits.py::test_saved_goes_as_soon_as_a_field_of_its_group_is_edited_again` (browser, Limits, Notifications, Engine).

### 5 (P3) Enter saves
**Cause.** There is no `<form>` and no key handler in the Settings groups.
**Fix.** (`home.js wireEnterSaves`) One keydown handler on the Settings pane presses the Save of the place a text, number, time or date field sits
in: the note row, the CLI file box or the Recurring add form first, else the group's (Limits, Notifications, Engine, Notes add). The button takes
focus first, as a mouse press does, because a group is not repainted while a field holds the focus. A disabled button, a composing IME, a
modifier, a checkbox, a select and a key another handler already took (`defaultPrevented`) are left alone. The handler is registered after the
pane's others and lives in its own function so that it sits beside, not on top of, the recurring-limits branch's Enter handler for Limits and
Notifications (trial merge below: one request per Enter, not two).
**Test.** `tests/ui/test_home_limits.py::test_enter_in_a_settings_field_presses_the_save_of_its_group` (browser: Limits, Notifications, Engine; one
request each). The helper `press()` of that file now focuses the button first, like a mouse press.

### 7 (P3) A cap above 10 is refused
**Cause.** `noticesBody` accepted `^\d{1,3}$` and clamped to 10, so 11 to 999 were saved as 10 with "Saved." while 1000 was refused.
**Fix.** (`limits_view.js`) Any number above the ceiling is refused with "The cap is a whole number from 0 to 10." before a request. The server
still clamps (API unchanged).
**Test.** `tests/ui/js/limits_view.test.js`: the old "99 becomes 10" expectation was the bug and now expects the refusal for 11, 50, 99 and 999;
10 itself is saved.

### 8 (P3) An empty note is not sent
**Cause.** `notes_view` sent an empty or blank text and printed the server's first pydantic message.
**Fix.** (`notes_view.js send()`) An empty text stops before the request with "Write the note first." (as Recurring work does); the draft stays.
**Test.** `tests/ui/js/notes_view.test.js`: add and edit, three empty shapes, no request made; a forget still goes.

### 9 (P3) `--offline` Default model is calm
**Cause.** Under `--offline` the health answer holds only the stub, so a saved Claude or Codex choice read as "not ready" and the first row showed
the red "no other model is ready either".
**Fix.** (`settings_view.js policyRow`) When a ready stub is in the answer the first row says, without the alert role, "Kept for when the app is
not offline: its built-in demo answers for now."; a stub that cannot answer still gives the red line.
**Test.** `tests/ui/js/settings_policy.test.js` (offline answer, and a stuck stub).

### 11 (P3) Plain words, no decision ids
**Cause.** `API_KEY_REFUSED` ("API-key login refused (D7): ...", in `health.py` and `codex.py`) and the doctor's detail ("... refused (D34)").
**Fix.** "API-key login is refused: sign in with your subscription" and "signed in with an API key, which is refused". The connectors design doc
quotes the new reason. Tests that pinned the old literal follow (`test_health.py` also asserts "(D7)" is absent, `test_doctor.py` "(D34)").
The `NoProviderError` test in `test_errors.py` builds its own sample reason and is unchanged.

### 12 (P3) The locked rows name the real file
**Cause.** `NOTE_LOCKED = "edit data/engine.json"`; the installed apps keep their data in `~/.sutra-pro` and have no `data/` folder.
**Fix.** (`settings_view.js lockedNote`, `home.js`) The rows read "edit <data folder>/engine.json" with the separator of the folder's system, escaped,
from the data folder About reads (`GET /api/ops/info`); the Engine group is painted again when it is known. Until then, or if the read failed:
"edit engine.json in your data folder (About shows where it is)".
**Tests.** `tests/ui/js/settings_engine.test.js` (posix, trailing slash, Windows, empty, hostile markup); `tests/ui/test_home.py` (browser).
Not changed: the same `data/engine.json` wording in the console's "Engine settings from" line and in J2-facing design text (other surfaces).

## Skipped

- **1 (P2) shared work root / session state.** The direct-chat branch fixes the same cause and owns it (`b1b5aa0d`: the work root carries the
  data folder's realpath and a random id, so a folder deleted and made again also starts clean). The first agent had made the same change a
  third way (`ce5fd7aa`: a hash of the realpath); both edit `ConnectorConfig.resolved_work_root`, its tests and the connectors design doc and
  conflicted. That commit is reverted here (`680f4cec`; history kept, net change nil). QA's `t25_bleed.py` should be re-run on the merged result.
- **10 (P3) demo task label with the notes block.** The org-chat-teams branch (`69b61e04`) and the security-privacy branch (`54bc82eb`) fix the same
  lines of `orchestrator/agent/demo.py`. A fix and a test were written here (`d8c7501f`: cut the request at `AGENT_HEADING`; it also showed
  that a note about "leads" sent an unrelated request to a Sales Leads team) and reverted (`70b101c1`) so a third variant does not conflict.
  The test worth keeping after the merge: a request plus an `AGENT_HEADING` block must name the task from the request and choose the team from its words alone.
- **13 (P3) 33 Tab stops.** The rail follows the chat in the DOM, so the fix is a skip link or a change of DOM order and focus handling on the
  welcome card. That changes `home.html` layout, the visual goldens and the focus order of every pane: not a one-line guard. Suggested follow-up:
  a visually hidden "Skip to Settings" link first in the page that shows on focus, plus returning focus to the first control after the welcome
  card closes (`welcome.js close()` restores focus to the body).

## Merge notes

Every other QA branch was trial-merged (git plumbing only, no ref or worktree touched). After the moves in `e901b18b`, `18a5a290` and `10817567`, this branch merges with recurring-limits, direct-chat, security-privacy, desktop-shell, dept-run, ops-cli and
org-chat-teams one at a time without a textual conflict. Merged together (recurring-limits, direct-chat, security-privacy, desktop-shell) the three browser tests of
Enter, "Saved." and the dead token pass and the Node suite passes (one file there, `page_render.test.js`, needs the project's `.venv` that a
copied tree does not have). The GAP3 packages (autoupdate, dept-chats, workdir) conflict with this branch in `home.js`, `settings_view.js`,
`home.html` and `fake_backend.py`, as they do with every branch that touches those files: for the person who merges them.
The direct-chat branch also re-reads the pill when a direct turn ends (`686bccfd`); with this branch's re-read on a message or a switch of the org
chat the two are redundant, not in conflict.

## Found, not fixed (not in the reported list)

- The existing browser tests of `test_home_limits.py`, `test_home_welcome_settings.py` and `test_home.py` error at teardown at 2ae63d11 already:
  the fake backend serves neither `GET /api/chats/cs_org/providers` nor `GET /api/notes`, and the tests do not announce the two 404s with
  `expect_failed`. The tests written or touched here announce them. `test_the_guard_switch_saves_at_once` also fails about two runs in three on a
  real mouse press that straddles a repaint (same on the base commit). Browser tests run only with `SUTRA_BROWSER=1`, outside the merge gate.
- `tests/ops/test_logsetup.py::test_the_access_log_loses_its_query_string` fails when run after the UI and connector tests in one session and
  passes alone (same on the base commit).

## Commands run

All from `sutra-pro/` in the worktree, with a private TMPDIR; no server was started and the owner's data folder, app and port 8780 were not touched.

- `node --test tests/ui/js/*.test.js`: 971 tests, 969 pass, 0 fail, 2 skipped.
- `scripts/py -m pytest tests/ui tests/connectors tests/ops tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py -q -p no:warnings`:
  2817 passed, 221 skipped, 1 failed (`test_logsetup`, above).
- `scripts/py -m pytest tests/connectors/test_env_process.py`: 67 passed (foreground).
- `scripts/py -m pytest tests/library`, on its own: 2347 passed, 4 skipped.
- `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_home_limits.py -k "enter_in_a_settings or saved_goes or heal_cannot"`: 3 passed, four runs in a row
  (also on the trial merge, twice); `tests/ui/test_home.py -k engine_group_shows`: passed.
