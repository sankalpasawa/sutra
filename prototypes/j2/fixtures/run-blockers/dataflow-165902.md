## Data flow

The morning run moves data in this order.

1. C8 starts the run.
2. Integration with the team inboxes: C1 reads the threads and keeps those that are quiet on the team's side.
3. C2 labels each quiet thread urgent or can-wait and stores the reason.
4. C4 attaches the one owning team lead to each thread.
5. C5 removes threads that were replied to or closed since the last run, and any reminder that would break the per-thread cap, the minimum gap, the daily limit or the one-per-thread-per-run rule. C3 puts urgent threads first.
6. C9 decides what happens to each remaining reminder. In shadow mode, the reminder is written to a would-have-sent record and nothing is posted to team leads. After the Requester has seen the agent work and approved, C6 posts it to the team lead (integration with chat).
7. chat interaction: the team lead replies to the thread or marks it closed from the reminder. the agent reads this back as a close or reply and stops reminding about closed threads.
8. C7 counts reminders with no reply and no close, and creates one report per thread when the ignore threshold is reached.
9. At the end of the run C10 posts the daily report to the Requester on chat: threads that have waited longer than 3 days, the would-have-sent reminders while in shadow mode, and the ignore-threshold reports.

the agent has no web forms. Its integrations are the team inboxes (read) and chat (reminders, close actions, daily report). Reminder history, close status and counts are kept between runs so the cross-day limits and the ignore count work.

Assumption: marking a thread closed on chat is done with a chat reaction or button on the reminder.

Assumption: the team inboxes are read-only for the agent, and it never sends messages.

Assumption: reminder history and close status are kept in a small data store that the scheduled run can read and write between days.

