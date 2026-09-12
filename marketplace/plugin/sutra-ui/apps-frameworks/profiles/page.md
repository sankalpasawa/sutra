# Building a page app

| Field | Value |
|---|---|
| **status** | apps frameworks kit, page profile |
| **updated** | 2026-09-12 |

A page app is one `index.html` shown inside the desktop. It is sealed off: no network, no storage, nothing loads from outside the file. The folder already exists when you read this: a starter `index.html`, the record `APP.md`, and the manifest `module.json`.

## Steps

1. Read `APP.md` first. Its first line is a stamp; never edit that line.
2. Ask the six questions in `APP.md`'s Product, Design and Backend rows that are still empty, one at a time, and wait for each answer:
   who opens this and what they are trying to get done; one line that names it; the first thing on the screen when it opens; what information it works with, where it lives, and one real row as the smallest example; what it should show when a number is missing or there is nothing to show; what tells them tomorrow that it worked.
3. Then send ONE message with the rest already filled in, for the builder to correct in a line or two: how they would use it once, the shape you will use (table, numbers, reading view, one answer), the controls one per line starting with a dash, whether anything resets when it closes, which rows count as good, warning or blocked, which part of the success answer must still be true after a future edit, the files, who keeps it and the date to look at it again, what it replaces, and the department it is filed under. Ask at the very end whether it names a real borrower or account, and whether anyone besides the builder will use it.
4. Replace the starter `index.html` with the page. Keep it a fragment: one root element with `lang`, inline `<style>` and `<script>`, the data baked in, images as `data:` URLs, and colour, type and radius only from the names the desktop provides (the list is in the chat that opened you).
5. Fill every row of `APP.md` with the answers. Set `name` and `tagline` in `module.json`. Change nothing else in `module.json`.
6. Run the check before you say done:

```text
python3 <kit>/check.py <folder> --kind page
```

   Fix every result marked must-fix and run it again. Read the suggestions out as they are; they do not block. If a must-fix result is wrong about an answer, say which one and why, and let the builder decide whether to waive it.
7. Report what the page shows when it opens and the check result. Plain words, no headings, no status lines. Say "app", never the internal word.

## Rules for a page

| Rule | Why |
|---|---|
| No network: nothing the page fetches, loads or sends goes anywhere | it runs sealed inside the desktop |
| Data lives inside `index.html`; files next to it are not served | a relative image is a dead image |
| Colour, type and radius come only from the provided names; never hex or rgb | it must read right in dark and light |
| Never redefine the theme names | that breaks one of the two themes |
| One main heading at most, headings in order; no repeated app name, crumb or pill | the header above the page already carries them |
| No storage: the page cannot remember anything between opens | say "resets each time" or "baked into the file" |
| One column by default, no fixed width over 320 px | the pane can be narrow |
| Every control is a real button, link or field with a name, reachable by keyboard | no click handlers on plain boxes |
| Under 512 KB | shared apps must stay small |

## What "done" means

The must-fix results are green: the record is complete, the name and line are set, no system jargon anywhere a person reads, only the provided colour names, the theme is not redefined, the manifest matches the folder, only allowed files are present, the caps hold, the stamp agrees, no network call, nothing referenced outside the file, no secret, a fragment with a root element, no storage use, and an honest answer about state.

---
provenance: part of the Sutra apps frameworks kit; the checks and rules of record are in `../angles/*.rules.md`.
