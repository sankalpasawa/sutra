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
| Frontend | | | n-a (link) | frontend v{{KIT_VERSION}} | | |

## Product

| id | question | answer |
|---|---|---|
| P1 | Who opens this, and what are they after? | |
| P2 | What should the row say, and one line under it? | |
| P3 | What tells you it is the right shortcut? | |
| P5 | What should you see if that screen is empty or gone, and what do you do then? | |
| P6 | Who keeps this row, and what date should it be looked at again? | |
| P7 | Is anyone besides you going to use this? | |

## Strategy

| id | question | answer |
|---|---|---|
| S2 | Does it replace something you click through by hand today? | |
| S3 | Department: keep it where it is filed, or move it? | {{DEPARTMENT}} |

## Design

| id | question | answer |
|---|---|---|
| DS6 | What does the row look like next to the other rows? | |

## Engineering

| id | question | answer |
|---|---|---|
| E1 | Which files is this app made of? | module.json only, plus this record |
| E2 | What must still work after a future edit? | the row opens {{SCREEN}}; click Open and land on it |

## Backend

| id | question | answer |
|---|---|---|
| B1 | What does that screen show, and where does that live? | |
| B5 | Which screen should this open? | {{SCREEN}} |

## Checks

(written by the check, never by hand)

## Changes

- {{DATE}} - created from the link starter

---
provenance: the record of this app, created by Sutra Desktop from the apps frameworks kit v{{KIT_VERSION}}; the first line is the stamp and is never edited by hand.
