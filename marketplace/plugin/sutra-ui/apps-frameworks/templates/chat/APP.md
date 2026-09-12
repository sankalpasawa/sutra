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
| Backend | | | yes | backend v{{KIT_VERSION}} | commands it may run, word for word: |
| Frontend | | | n-a (chat) | frontend v{{KIT_VERSION}} | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this chat, and what are they trying to get done? | |
| P2 | Say it in one line someone else would understand. What should it be called? | |
| P3 | You open it tomorrow. What in the opening message tells you it worked? | |
| P4 | Walk me through one use, start to finish. | |
| P5 | When the information is missing or wrong, what should it say instead of guessing? | |
| P6 | Who keeps it, and what date should it be looked at again? | |
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
| DS4 | Who is this chat talking to, and what must it never say? | |

## Engineering

| id | question | answer |
|---|---|---|
| E2 | What must still be true after a future edit? | |
| E3 | What is the smallest real thing someone will bring to it, and what does it do with it? | |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What information does it work with, and where does that live? | |
| B2 | Does any of it name a real borrower, account or loan number? (real, masked, made-up or aggregate) | |
| B3 | Which folder may this chat read and write? | |
| B4 | Anything it must never do on its own: run commands, install things, send messages? | |

## Checks

(written by the check, never by hand)

## Changes

- {{DATE}} - created from the chat starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v{{KIT_VERSION}}; the first line is the stamp and is never edited by hand.
