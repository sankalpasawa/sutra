# Design

| Field | Value |
|---|---|
| **status** | apps frameworks kit, design angle |
| **updated** | 2026-09-12 |

Make the app look and read like the rest of the desktop, in both themes and in a narrow pane.

## What you will be asked

- Page: when it opens, what is the first thing on the screen?
- Page (filled in; correct it): is it a table of rows, a few numbers, a short reading view, or one answer? Is anything on it good, warning or blocked, and what makes it so?
- Chat: who is this chat talking to, and what must it never say?
- Link: what should the row say, and what does it look like next to the others?
- Only if you want it, page: does anything need to stay side by side when the window is narrow?

## What it produces

The Design row of the record. The design itself lands in the page's inline style, in the chat's opening message, or in the link's row text.

## Rules in plain words

| Rule | Applies to | Why |
|---|---|---|
| Colour, type and radius come only from the app's own set of names, never typed as hex or rgb | page | the desktop injects the set; the page then reads right in dark and light |
| The page never redefines that set | page | a page that overrides the theme breaks in one of the two themes |
| One main heading at most, then headings in order | page | the header above the page already names the app |
| Contrast comes from the pairings that already pass: ink on background, muted for secondary text | page | the faint colour is for crumbs and pills, never body text |
| The page draws no chrome of its own: no repeated name, no crumb, no pills | page | the header above it carries all of that |
| No animation; a helpful transition stays under 150 ms and respects reduced motion | page | motion is not what the desktop does |
| One column by default, no fixed widths over 320 px, no sideways scroll | page | the pane can be narrow |
| The opening message is a visible first message: who you are, at most eight short rules, one closing ask, under 4000 characters | chat | there is no hidden prompt |
| A link has one design decision, the row text, and borrows the screen it opens | link | nothing else to draw |

## What "done" checks here

For a page: only the app's own colour, type and radius names are used, and the theme set is not redefined. Everything else here is a suggestion.

---
provenance: part of the Sutra apps frameworks kit; the rules of record with their sources are in `design.rules.md` next to this file.
