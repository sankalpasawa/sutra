## Interactive elements
- **E1** in S1: `#reply-action` trigger click; behaviour: the team lead goes to the thread to reply. When a reply is seen, the agent skips the thread at the next run.
- **E2** in S1: `#close-action` trigger click; behaviour: the agent records the thread as closed by that team lead on chat and stops reminding about it.
- **E3** in S4: `#shadow-mode-switch` trigger change; behaviour: on holds back all team lead reminders and records them as would-have-sent entries in S2; off lets reminders go to team leads. It starts on, and it is turned off only after the Requester has seen the agent work.
- **E4** in S3: `#morning-trigger` trigger schedule (every morning, no manual launch); behaviour: runs the message list read, labelling, ordering, owner lookup, limiting, reminders or shadow recording, ignore check and finally the daily report once.
