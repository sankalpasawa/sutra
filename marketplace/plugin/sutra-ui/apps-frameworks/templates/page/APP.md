frameworkKit: {{STAMP}}

---

# {{NAME}}

{{TAGLINE}}

| Angle | Decision | Why | Applies? | Source | Checks | Owner notes |
|---|---|---|---|---|---|---|
| Product | | | yes | product v{{KIT_VERSION}} | | |
| Strategy | | | yes | strategy v{{KIT_VERSION}} | | |
| Design | | | yes | design v{{KIT_VERSION}} | | |
| Engineering | | | yes | engineering v{{KIT_VERSION}} | | |
| Backend | | | yes | backend v{{KIT_VERSION}} | | |
| Frontend | | | yes | frontend v{{KIT_VERSION}} | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this, and what are they trying to get done? | |
| P2 | Say it in one line someone else would understand. What should it be called? | |
| P3 | You open it tomorrow. What do you see that tells you it worked? | |
| P4 | Walk me through using it once, start to finish. | |
| P5 | What is the worst wrong thing it could show, what should it show instead, and what do you do then? | |
| P6 | Who fixes it when it breaks, and what date should it be looked at again? | |
| P7 | Is anyone besides you going to use this? | |

## Strategy

| id | question | answer |
|---|---|---|
| S1 | What do you do today without it? | |
| S2 | Does it replace or extend something you already have? | |
| S3 | Department: keep it where it is filed, or move it? | {{DEPARTMENT}} |

## Design

| id | question | answer |
|---|---|---|
| DS1 | When it opens, what is the first thing on the screen? | |
| DS2 | A table of rows, a few numbers, a short reading view, or one answer? | |
| DS3 | Is anything on this page good, warning or blocked, and what makes it so? | |

## Engineering

| id | question | answer |
|---|---|---|
| E1 | Which files is this app made of, and which one opens first? | index.html opens first; module.json is the manifest; APP.md is this record |
| E2 | What must still be true after a future edit? | |
| E3 | What is the smallest real example it has to handle, and what does it show for it? | |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What information does it work with, and where does that live? | |
| B2 | Does any of it name a real borrower, account or loan number? (real, masked, made-up or aggregate) | |

## Frontend

| id | question | answer |
|---|---|---|
| F1 | What can they do on it? One control per line, starting with a dash. | |
| F2 | Does anything need to still be there next time? (resets each time, or baked into the file) | |
| F3 | Any pictures, icons or fonts? | |

## Checks

(written by the check, never by hand)

## Changes

- {{DATE}} - created from the page starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v{{KIT_VERSION}}; the first line is the stamp and is never edited by hand.
