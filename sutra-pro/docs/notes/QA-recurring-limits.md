# QA recurring-limits: what QA found on 2ae63d11 and what was done

QA drove the recurring work (standing tasks on a schedule), the monthly spending limit, the plan-window guard, quiet hours and the hourly cap through the real app
(the end-to-end harness with a controlled clock, HTTP against a live server, and a headless Chrome on the Settings page). Eight bugs: two P2, six P3. Seven are
fixed, one is left as a documented omission. Nothing in J2's own code is involved (`engine/j2*.py`, `engine/llm.py`, `engine/port.py`, `ui/pages/j2_ui.html` are
untouched).

| # | Sev | Bug | Result |
|---|-----|-----|--------|
| 1 | P2 | A schedule goes silent for the length of a clock error (the cursor stays in the future) | fixed |
| 2 | P2 | One unreadable stored schedule makes `GET /api/recurring` a 500 for the whole list | fixed |
| 3 | P3 | Run now (and the history) says "working" for a task a limit holds back | fixed |
| 4 | P3 | `GET /api/limits` is a 500 when a plan window's reset time is out of the datetime range | fixed |
| 5 | P3 | "Quiet right now." goes stale until a reload | fixed |
| 6 | P3 | Focus falls to the page after every Recurring action; Enter in the limit field does nothing | fixed |
| 7 | P3 | After 84 days an hourly schedule reports "folded 1999" as if exact | fixed |
| 8 | P3 | No way to edit a standing task in the page | skipped (by omission, now documented) |

## 1. The cursor in the future (P2)

**Root cause.** `recurring.cursor_at` is "the last due time dealt with". A catch-up on a clock that had run a month ahead moved it to that future time; once the
clock was corrected, `owed(schedule, cursor, now)` saw `now <= cursor` and returned nothing on every tick until the clock reached the cursor again. The list kept
promising `next_due_at` because that is worked out from `now`, not from the cursor. `create`, `update` and switching on set the cursor to the clock's "now", so a
schedule made on an ahead clock stalled the same way.

**Fix** (`orchestrator/recurring.py`, `_tick_in_tx`). A cursor later than the tick's `now` is moved back to `now` (and saved) before the schedule is asked what is
owed. The unique row on (recurring_id, due_at) still refuses a due time that already ran on the early clock. The busy branch now reports a skip only when it wrote a
row (a refused repeat is not a new skip).

**Tests.** `test_recurring.py`: `test_a_clock_that_ran_ahead_and_was_corrected_does_not_silence_the_schedule`,
`test_a_schedule_made_while_the_clock_was_ahead_fires_once_the_clock_is_right`,
`test_an_hour_the_clock_ran_ahead_does_not_run_a_slot_twice_when_it_is_corrected`. The first two fail before the fix (the cursor stays at the future time; nothing
fires); the third guards the new branch (it fails if a refused repeat is counted as a skip).

**Known limit.** A due time that falls between the moment the clock is corrected and the next tick (at most one tick, 30 s) is not owed: the cursor can only be
moved to a time the app has seen. The alternative (moving it to the last due time before now) would run slots from before a schedule existed.

## 2. One unreadable schedule hides the list (P2)

**Root cause.** `_out()` parsed `schedule_json` with `Schedule.model_validate_json` and no guard. The tick path (`_tick_in_tx`, `_pause`) planned for an unreadable
schedule (it pauses the row and says "Set it again."), but `listing()` and `get()` did not, so the page lost the whole Recurring group, including the message and
the Remove button. The same parse was unguarded in `run_now`.

**Fix.** One reader, `Recurring._read(raw) -> Schedule | None`, used by the list, the tick, the pause note and Run now. An unreadable row is listed as paused
with "Paused: its schedule could not be read. Set it again.", no `next_due_at`, `schedule: null` (the field is now `Schedule | None`; the page reads `human`, not
`schedule`), and the other rows list as usual. Run now and switching a paused row on refuse with a 422 that says why (switching on would only be paused again,
with another note in the team's chat). Setting a new schedule with `PUT` repairs the row; Remove works.

**Tests.** `test_recurring.py::test_one_unreadable_schedule_does_not_hide_the_others_and_is_listed_as_paused_with_its_reason`,
`::test_an_unreadable_schedule_can_be_set_again_and_a_manual_run_of_it_says_so_instead_of_failing`;
`test_api_recurring.py::test_one_unreadable_schedule_leaves_the_list_a_200_and_can_still_be_removed`. All three failed before (the ValidationError QA saw).

## 3. "working" for a held run (P3)

**Root cause.** The run's word is read from the task's status; `queued` mapped to `working`. A queued task that the spending limit or the plan-window guard holds is
not working: `TaskService` gives it the waiting words `waiting: ...` and leaves it `queued`. Run now also answered before `start_ready` had decided anything.

**Fix.** The run query joins the task's step node, and `result_of(outcome, status, detail)` returns the new result `held` for a task that is `queued` and whose detail
begins with `waiting:` (both limit holds, `limits.WAIT_SPEND` and `WAIT_GUARD`; a test pins that they begin with the constant `HELD`). `POST /api/recurring/{id}/run`
reads the run again after `start_ready`. The page says "queued by you, waiting on a limit" (`recurring_view.js`).

**Tests.** `test_recurring.py::test_a_run_whose_task_the_spending_limit_holds_is_not_called_working` (manual and scheduled; held, then working once the limit is raised),
`::test_both_limit_holds_begin_with_the_words_a_held_run_is_told_by`, `::test_a_queued_task_that_waits_for_a_slot_or_the_team_is_still_working` (the control);
`test_api_recurring.py::test_run_now_under_a_used_up_limit_answers_held_not_working`; `recurring_view.test.js` ("a run held back by a limit is queued ...").

## 4. A reset time out of range (P3)

**Root cause.** `QuotaWindow.resets_at` accepts any finite float; `guard_reading` and `reset_words` turned it into a date without a range check, and
`Limits.state()` (unlike `gate()`) had no fail-open guard. A CLI that reports milliseconds (about 1.8e12) raised `ValueError: year 58000 is out of range`.

**Fix** (`orchestrator/limits.py`). A reset time that is not between 0 and 2100-01-01 is a figure that cannot be trusted: that window is left out (holds nothing, like
a stale snapshot, as the module says it fails open) and `reset_words` answers "". `state()` falls back to an empty reading if the windows cannot be read at all. The
other window of the same provider still counts. The connector layer (`QuotaWindow`, `_number`) is not touched; it belongs to another package.

**Tests.** `test_limits.py::test_a_reset_time_no_clock_can_show_is_a_figure_that_cannot_be_trusted_and_holds_nothing` (4 values),
`::test_the_state_answers_even_when_the_plan_windows_cannot_be_read`; `test_api_limits.py::test_a_plan_window_with_an_impossible_reset_time_does_not_make_the_answer_a_500`
(2 values). All failed before.

## 5. "Quiet right now." stale (P3)

**Root cause.** The Notifications group printed `prefs.quiet_now` from the last `GET /api/ops/attention`, and the minute timer and the events only re-read
`/api/limits`. The notices themselves were right (they use the page's own twin of the rule), only the label was stale.

**Fix.** `noticesHtml` takes an optional boolean `form.quietNow`; `home.js` (`quietNowOf`) computes it at each paint with the same twin the notices use
(`ChatAttention.windowActive`) and falls back to the server's reading when there is no twin or no answer yet. The minute refetch already repaints the group.

**Tests.** `limits_view.test.js` ("'Quiet right now.' follows the clock the page hands in ..."); browser test
`test_home_limits.py::test_quiet_right_now_follows_the_pages_clock_not_the_servers_reading_at_the_last_fetch` (the fake backend always answers `quiet_now: false`,
so a window around the browser's own minute reads as quiet only through the twin; it times out before the fix).

## 6. Focus and Enter (P3)

**Root cause.** `ctx.paint` replaces the group's HTML; the button the owner had used from the keyboard disappeared with it, and focus fell to the page. While an
action ran the buttons were also disabled, which takes focus away. The limit field had no key handling, and the group is not repainted while a text field has
focus, so a save from the field could not show "Saved." either.

**Fix** (`home.js`; `sutra_ctx.js` is shared and is left alone). `paintGroup` wraps the paint of the three groups: it remembers the control that had focus (by
`data-act`, `data-id`, `data-input`, not the element) and focuses the same one after the repaint; it keeps the key across the disabled period of an action; Remove
asks and focus lands on "No" (the safe answer), "No" returns to Remove; a removed row leaves focus on the group heading (the three `h3`s got `tabindex="-1"`). Enter in
the monthly-limit field and in the three notice fields saves like the Save button and repaints although the owner is in the field (the caret stays at the end).

**Tests.** Browser: `test_the_keyboard_keeps_its_place_in_the_recurring_group_after_each_action`, `test_enter_in_the_limit_and_notice_fields_saves_like_the_button`
(both fail before); `limits_view.test.js` and `recurring_view.test.js` pin the focusable headings.

## 7. "folded 1999" (P3)

**Root cause.** `owed` counts due times only up to `COUNT_CAP` (2000) so a long absence is cheap; `folded = count - 1` was stored and printed as if exact, against the
module's own comment ("told many, not an exact figure").

**Fix.** A count at the cap is told as "many earlier due times were missed ..." in the run's reason and the team's note; the stored `folded` stays the least it was
(`COUNT_CAP - 1`). The page prints "many earlier times folded in" from that value (`MANY_FOLDED` in `recurring_view.js`; a test reads the file and checks it equals
`COUNT_CAP - 1`).

**Tests.** `test_recurring.py::test_an_absence_past_the_count_cap_is_told_as_many_and_a_shorter_one_as_a_figure`,
`::test_the_page_names_the_same_cap_as_the_schedule_counts_to`; `recurring_view.test.js` ("a folded count that reached the cap ..."). Both Python tests failed before.

## 8. No edit control (P3): skipped

By omission, not a defect in what exists: `PUT /api/recurring/{id}` works and the flow list for this feature lists "edit", but a page with an edit form (words, time,
team, and a way to re-point a schedule whose team left) is a feature, not a safe one-line fix, and it would grow `recurring_view.js` and `home.js` that other
branches also touch. Recorded in `docs/notes/GAP2-routines-limits.md` under "Not done, and why" so the omission is no longer silent.

## Not reproduced, by design, or J2's

Nothing was skipped on those grounds. Every bug reproduced (the QA scripts, copied and adapted as tests) and none is in J2's own code.

## Tests run

| Command | Result |
|---------|--------|
| `node --test tests/ui/js/*.test.js` | 970 tests: 968 pass, 0 fail, 2 skipped |
| `scripts/py -m pytest tests/orchestrator/test_recurring.py test_api_recurring.py test_limits.py test_api_limits.py test_schedule.py` | 133 passed |
| `scripts/py -m pytest tests/orchestrator tests/ui tests/test_docs.py tests/test_traceability.py tests/test_ownership.py tests/test_layout.py` | exit 0: 2169 passed, 215 skipped (the browser tests skip without `SUTRA_BROWSER=1`) |
| `scripts/py -m pytest tests/library` (own command) | 2347 passed, 4 skipped |
| `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_home_limits.py -k "keyboard_keeps or enter_in_the or quiet_right"` | 3 passed (the three new browser tests) |
| `SUTRA_BROWSER=1 scripts/py -m pytest tests/ui/test_home_limits.py` | the other 5 error at teardown and 1 flakes, exactly as on 2ae63d11 (below) |

The connectors are not touched, so `tests/connectors/test_env_process.py` was not run.

Baseline noise on 2ae63d11, same with and without this branch (compared against a pristine `git archive` of the base commit): the browser tests of
`tests/ui/test_home_limits.py` that open Home error at teardown because the fake backend has no `GET /api/notes` (the rules-notes package merged without a fake route),
and `test_the_guard_switch_saves_at_once` flakes. The three new browser tests announce that one 404 with `expect_failed`, so they end clean.
