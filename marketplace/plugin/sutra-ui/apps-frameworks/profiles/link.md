# Building a link app

| Field | Value |
|---|---|
| **status** | apps frameworks kit, link profile |
| **updated** | 2026-09-12 |

A link app is a row that opens a screen the desktop already has. It has no page and no message. The folder already exists when you read this: the record `APP.md` and the manifest `module.json`, whose `surface.screen` names the screen.

## Steps

1. Read `APP.md` first. Its first line is a stamp; never edit that line.
2. Ask one question at a time, in this order, and wait for each answer:
   which screen it should open (offer the list the chat that opened you carries; never the terminal or usage); what the row should say and one line under it; who opens it and what they are after; what tells them it is the right shortcut and what they should see if that screen is empty or gone; what that screen shows and where that lives; whether to keep it filed under the department shown or move it.
3. Then send ONE message with the rest filled in: who keeps it and the review date, and what it replaces by hand today. Two answers are fixed by the kind; state them and ask for a nod: the files are `module.json` plus the record, and what must still work is "the row opens the screen; click Open and land on it". Ask at the end whether anyone besides the builder will use it.
4. Set `surface.screen`, `name` and `tagline` in `module.json` and fill every row of `APP.md`. Change nothing else in `module.json`.
5. Run the check before you say done:

```text
python3 <kit>/check.py <folder> --kind link
```

   Fix every must-fix result.
6. Report the row and the screen it opens, and the check result. Plain words, no headings, no status lines. Say "app", never the internal word.

## Rules for a link

| Rule | Why |
|---|---|
| The target is one live screen of the desktop; never a web address, never the terminal | that is all a link is |
| The manifest's surface carries the screen and nothing else | nothing else to configure |
| The row text is the one design decision | it borrows the screen it opens |
| A link is ready the moment it is created | there is nothing a draft state would protect |

## What "done" means

The must-fix results are green: the record is complete, the name and line are set, no system jargon, the manifest matches the folder, only `module.json` and the record are present, the caps hold, the stamp agrees, no secret anywhere, and the screen is live.

---
provenance: part of the Sutra apps frameworks kit; the checks and rules of record are in `../angles/*.rules.md`.
