# Manual tests: What Shadow knows (memory, personality, switches)

Run against the `shadow-memory-personality` branch. Started 2026-10-08.

**Setup at the start:** all Shadow tasks and chats deleted (backup:
`~/.sutra-ui/shadow-backup-20261008-085515`). Memory kept: CEO of Sutra,
Sankalp has final say, main repo is sutra, friendly/direct tone for
customer-facing writing, rule "Always keep replies short". Switches at their
defaults: Acting = **Just do it**, Before "done" = **Prove everything**,
Replies = **Short**, Checking in = **At milestones** (3 alerts/hour).

**Why phases:** switches are global and read every turn, so tasks that run at
the same time share them. Phase A runs on the defaults; Phase B changes one
switch after Phase A is under way.

| # | Phase | What it tests | How it starts | What you should see in the UI | Pass? |
|---|---|---|---|---|---|
| 1 | You | First message: a question needs no worker | **You type** in the main box: *Who has final say on Shadow, and what's our main repo?* | A direct answer ("Sankalp; sutra"). The rail shows it under **CHATS**; no task appears | |
| 2 | You | First message: "remember" needs no worker | **You type**: *Remember: our design system is called Lotus.* | "Remembered" in one line; **Your work** or **Your preferences** gains "design system is called Lotus"; no task | |
| 3 | A | Acting = Just do it: no needless questions | Started by Claude: *Create pricing-tiers.md with three pricing plans for Sutra.* | Finishes with **no NEEDS YOU**; Shadow picks plan names and prices itself (marked as placeholders) | |
| 4 | A | Before "done" = Prove everything | Started by Claude: *Write fizzbuzz.py that prints FizzBuzz for 1 to 15, and make sure it works.* | Under **Verification**, a check settled by a command (e.g. running the script), not only by reading it | |
| 5 | A | Memory passed when relevant | Started by Claude: *Write a welcome email for new Sutra customers in welcome3.md.* | Open the worker chat: its first message mentions the **friendly, direct tone**. The email reads that way | |
| 6 | A | Memory withheld when irrelevant | Started by Claude: *Create a .gitignore for a Python project in gitignore-test/.gitignore* | Worker's first message has **no** tone, CEO or Sankalp lines | |
| 7 | A | Nothing to do asks to be closed | Started by Claude: *Fix the typo in notes-clean.md* (the file has no typo) | **NEEDS YOU**: "Nothing to do here: …" with **Close the task - nothing to do / Keep going**. Close it: it moves to DONE TODAY as **NOTHING TO DO** | |
| 8 | A | Learning from your answer | Started by Claude: *Write a short internal memo in memo.md about the new memory feature. Ask me who it is addressed to before writing.* | NEEDS YOU asks who. Answer **"the whole team"** (no "always"). Expect a **Remember for next time … [Keep] [Drop]** card on that task only, or nothing if Shadow judges it task-only | |
| 9 | B | Acting = Ask first holds the first instruction | Claude sets **Acting on its own → Ask first**, then starts: *Create hello.txt containing the word hello.* | The task stops before doing anything and asks you to confirm the first step. Confirm it and it finishes. (Claude switches Acting back to Just do it afterwards) | |
| 10 | You | A switch changed by voice, then used | After 9, **you type**: *From now on, give me detailed replies.* Then open What Shadow knows | **Replies → Detailed** is now selected. Later Shadow updates are longer | |

**Also check while these run**
- Text fields keep your cursor while tasks stream (type into a NEEDS YOU answer box).
- Keep/Drop cards show only on the task they came from.
- What Shadow knows stays short: suggestions as one line, groups folded.
- After 3 or more tasks, a **switch suggestion** may appear (rule 2), e.g. if you approve several held steps unchanged.
