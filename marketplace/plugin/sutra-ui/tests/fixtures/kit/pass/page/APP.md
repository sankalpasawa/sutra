frameworkKit: {"kit":"apps-frameworks","version":"1.0.0","digest":"2a31acac6fcd","created_at":"2026-09-12T09:00:00Z","kind":"page"}

---

# Loan book by bucket

the late loans, oldest first, with the owner beside each

| Angle | Decision | Why | Applies? | Source | Checks | Owner notes |
|---|---|---|---|---|---|---|
| Product | | | yes | product v1.0.0 | | |
| Strategy | | | yes | strategy v1.0.0 | | |
| Design | | | yes | design v1.0.0 | | |
| Engineering | | | yes | engineering v1.0.0 | | |
| Backend | | | yes | backend v1.0.0 | | |
| Frontend | | | yes | frontend v1.0.0 | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this, and what are they trying to get done? | A collections analyst opens it to see which loans slipped past 60 days late this week and who owns each one. |
| P2 | Say it in one line someone else would understand. What should it be called? | Loan book by bucket: the late loans, oldest first, with the owner beside each. |
| P3 | You open it tomorrow. What do you see that tells you it worked? | When I open it tomorrow the top row reads LN-1877 at 63 days and the count of loans over 60 days matches the collections sheet. |
| P4 | Walk me through using it once, start to finish. | Open the app, scan the top rows, click Sort by days late, note the owners of the top three, close it. |
| P5 | What is the worst wrong thing it could show, what should it show instead, and what do you do then? | The worst wrong thing is a paid-off loan still shown as late; it should show the paid date instead, and I re-paste the rows from the ledger export. |
| P6 | Who fixes it when it breaks, and what date should it be looked at again? | Priya (collections lead) keeps it; look at it again on 2026-12-12. |
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
| DS1 | When it opens, what is the first thing on the screen? | A table of loans sorted by days late, the oldest at the top. |
| DS2 | A table of rows, a few numbers, a short reading view, or one answer? | A table of rows. |
| DS3 | Is anything on this page good, warning or blocked, and what makes it so? | Over 60 days is blocked, 30 to 60 is warning, under 30 is good. |

## Engineering

| id | question | answer |
|---|---|---|
| E1 | Which files is this app made of, and which one opens first? | index.html opens first; module.json is the manifest; APP.md is this record |
| E2 | What must still be true after a future edit? | Open the app and see the top row read LN-1877 at 63 days after any edit. |
| E3 | What is the smallest real example it has to handle, and what does it show for it? | One loan row: LN-1877, 63 days late, owner Priya; it shows as blocked at the top. |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What information does it work with, and where does that live? | Three loan rows pasted from the ledger export; they live inside the file itself. |
| B2 | Does any of it name a real borrower, account or loan number? (real, masked, made-up or aggregate) | Made-up: the loan numbers are examples, not real borrowers. |

## Frontend

| id | question | answer |
|---|---|---|
| F1 | What can they do on it? One control per line, starting with a dash. | - Sort by days late |
| F2 | Does anything need to still be there next time? (resets each time, or baked into the file) | Resets each time; the rows are baked into the file. |
| F3 | Any pictures, icons or fonts? | No pictures, icons or fonts. |

## Checks

(written by the check, never by hand)

## Changes

- 2026-09-12 - created from the page starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v1.0.0; the first line is the stamp and is never edited by hand.
