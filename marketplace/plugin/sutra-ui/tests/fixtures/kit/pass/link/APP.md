frameworkKit: {"kit":"apps-frameworks","version":"1.1.1","digest":"c354f0ad0008","created_at":"2026-09-12T09:00:00Z","kind":"link"}

---

# Balance shortcut

the late loans, oldest first, with the owner beside each

| Angle | Decision | Why | Applies? | Source | Checks | Owner notes |
|---|---|---|---|---|---|---|
| Product | | | yes | product v1.1.1 | | |
| Strategy | | | yes | strategy v1.1.1 | | |
| Design | | | yes | design v1.1.1 | | |
| Engineering | | | yes | engineering v1.1.1 | | |
| Backend | | | yes | backend v1.1.1 | | |
| Frontend | | | n-a (link) | frontend v1.1.1 | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this, and what are they after? | A collections analyst opens it to see which loans slipped past 60 days late this week and who owns each one. |
| P2 | What should the row say, and one line under it? | Loan book by bucket: the late loans, oldest first, with the owner beside each. |
| P3 | What tells you it is the right shortcut? | When I open it tomorrow the top row reads LN-1877 at 63 days and the count of loans over 60 days matches the collections sheet. |
| P5 | What should you see if that screen is empty or gone, and what do you do then? | The worst wrong thing is a paid-off loan still shown as late; it should show the paid date instead, and I re-paste the rows from the ledger export. |
| P6 | Who keeps this row, and what date should it be looked at again? | Priya (collections lead) keeps it; look at it again on 2026-12-12. |
| P7 | Is anyone besides you going to use this? | Just me for now. |

## Strategy

| id | question | answer |
|---|---|---|
| S2 | Does it replace something you click through by hand today? | It replaces the weekly filtered spreadsheet; it extends nothing else. |
| S3 | Department: keep it where it is filed, or move it? | Unassigned |

## Design

| id | question | answer |
|---|---|---|
| DS6 | What does the row look like next to the other rows? | Late loans, one line under it; it sits next to the Balance row and looks the same. |

## Engineering

| id | question | answer |
|---|---|---|
| E1 | Which files is this app made of? | module.json only, plus this record |
| E2 | What must still work after a future edit? | the row opens balance; click Open and land on it |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What does that screen show, and where does that live? | Three loan rows pasted from the ledger export; they live inside the file itself. |
| B5 | Which screen should this open? | balance |

## Checks

(written by the check, never by hand)

## Changes

- 2026-09-12 - created from the link starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v1.1.1; the first line is the stamp and is never edited by hand.
