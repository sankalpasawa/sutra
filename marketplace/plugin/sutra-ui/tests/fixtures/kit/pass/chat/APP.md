frameworkKit: {"kit":"apps-frameworks","version":"1.1.1","digest":"c354f0ad0008","created_at":"2026-09-12T09:00:00Z","kind":"chat"}

---

# Late loans desk

the late loans, oldest first, with the owner beside each

| Angle | Decision | Why | Applies? | Source | Checks | Owner notes |
|---|---|---|---|---|---|---|
| Product | | | yes | product v1.1.1 | | |
| Strategy | | | yes | strategy v1.1.1 | | |
| Design | | | yes | design v1.1.1 | | |
| Engineering | | | yes | engineering v1.1.1 | | |
| Backend | | | yes | backend v1.1.1 | commands it may run, word for word: |
| Frontend | | | n-a (chat) | frontend v1.1.1 | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this chat, and what are they trying to get done? | A collections analyst opens it to see which loans slipped past 60 days late this week and who owns each one. |
| P2 | Say it in one line someone else would understand. What should it be called? | Loan book by bucket: the late loans, oldest first, with the owner beside each. |
| P3 | You open it tomorrow. What in the opening message tells you it worked? | When I open it tomorrow the top row reads LN-1877 at 63 days and the count of loans over 60 days matches the collections sheet. |
| P4 | Walk me through one use, start to finish. | Open the app, scan the top rows, click Sort by days late, note the owners of the top three, close it. |
| P5 | When the information is missing or wrong, what should it say instead of guessing? | The worst wrong thing is a paid-off loan still shown as late; it should show the paid date instead, and I re-paste the rows from the ledger export. |
| P6 | Who keeps it, and what date should it be looked at again? | Priya (collections lead) keeps it; look at it again on 2026-12-12. |
| P7 | Is anyone besides you going to use this? | Just me for now. |

## Strategy

| id | question | answer |
|---|---|---|
| S1 | What do you do today without it? | I open the ledger export in a spreadsheet and filter by days late by hand. |
| S2 | Does it replace or extend something you already have? | It replaces the weekly filtered spreadsheet; it extends nothing else. |
| S3 | Department: keep it where it is filed, or move it? | Unassigned |

## Design

| id | question | answer |
|---|---|---|
| DS4 | Who is this chat talking to, and what must it never say? | It talks to the collections analyst on shift; it must never quote a borrower's phone number or promise a settlement. |

## Engineering

| id | question | answer |
|---|---|---|
| E2 | What must still be true after a future edit? | Open the app and see the top row read LN-1877 at 63 days after any edit. |
| E3 | What is the smallest real thing someone will bring to it, and what does it do with it? | One loan row: LN-1877, 63 days late, owner Priya; it shows as blocked at the top. |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What information does it work with, and where does that live? | Three loan rows pasted from the ledger export; they live inside the file itself. |
| B2 | Does any of it name a real borrower, account or loan number? (real, masked, made-up or aggregate) | Made-up: the loan numbers are examples, not real borrowers. |
| B3 | Which folder may this chat read and write? | Only the collections folder under my home. |
| B4 | Anything it must never do on its own: run commands, install things, send messages? | It must never run commands, install anything or send messages on its own. |

## Checks

(written by the check, never by hand)

## Changes

- 2026-09-12 - created from the chat starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v1.1.1; the first line is the stamp and is never edited by hand.
