# Engineering

| Field | Value |
|---|---|
| **status** | apps frameworks kit, engineering angle |
| **updated** | 2026-09-12 |

Fix what the app is made of, what must still work after a later edit, and keep the record current without touching the fields the desktop owns.

## What you will be asked

- What is the smallest real example it has to handle, and what does it show for it?
- Filled in from your success answer; correct it: what must still be true after a future edit?
- Page, filled in; correct it: which files is this app made of, and which one opens first?
- Only when editing later: is anything in here temporary that a future edit should not trust?

## What it produces

The Engineering rows and the Changes list of the record. The record's first line is a stamp the desktop writes; you never edit it.

## Rules in plain words

| Rule | Why |
|---|---|
| The folder is the app and its manifest is `module.json`; the folder name is the app's id | one place, one identity |
| Content files first, the manifest last and complete | a half-written manifest shows as "building" until it is whole |
| Version numbers and timestamps belong to the desktop | the chat never bumps or writes them |
| The chat never writes event logs | the desktop records what happened |
| Only the manifest, `index.html` and `assets/` travel when an app is shared | the record stays on this machine; its stamp is mirrored into the manifest |
| Size caps: 200 files, 5 MB per file, 20 MB total, a page under 512 KB | shared apps must stay small |
| Sharing needs the current manifest format | an older app updates itself on its next edit |
| The stamp is written once, when the app is created | a newer desktop never rewrites an existing app; you decide when to move it over |
| Every edit session adds one dated line to Changes | the history is in the folder |

## What "done" checks here

The manifest is valid and matches the folder, the folder holds only the files this kind allows plus the record, the size caps hold, and the stamp is present and agrees between the record and the manifest. The regression check and the Changes line are suggestions in this version.

---
provenance: part of the Sutra apps frameworks kit; the rules of record with their sources are in `engineering.rules.md` next to this file.
