# Frontend

| Field | Value |
|---|---|
| **status** | apps frameworks kit, frontend angle |
| **updated** | 2026-09-12 |

Fix what a person sees and can do the moment the app opens, and prove a page actually renders inside its sandbox.

## What you will be asked (page only, filled in; correct it)

- What can they do on it? Every button, field and list, one per line starting with a dash.
- If they change something, does it need to still be there next time? The page cannot save anything by itself.
- Any pictures, icons or fonts? They get embedded into the file, so keep them small.
- Only if you want it: anything that should move or refresh on its own? Any colour outside the app's own set, such as a chart palette?

## What it produces

The Frontend row of the record. The check adds whether the page rendered in both themes.

## Rules in plain words

| Rule | Applies to | Why |
|---|---|---|
| `index.html` is a fragment, not a whole document: one root element with a language, inline style and script | page | the desktop wraps it with the theme and the colour set |
| Every control is a real button, link, input, select or text area with a name, reachable by keyboard | page | no click handlers on plain boxes |
| The page cannot remember anything between opens; durable state lives in the file | page | storage is sealed off; say "resets each time" or "baked into the file" |
| Fit the pane, not a monitor: about 260 px of usable width at the worst | page | the pane can be narrow |
| A page counts as ready when it has rendered in both themes with no errors | page | when the check cannot render, the record says "render: not run" and the run is incomplete |
| A link's whole surface is its row and the Open control | link | nothing to render |
| A chat has nothing to render; its surface is the opening message | chat | every chat check is a static read of that message |

## What "done" checks here

Page: a fragment with a root element and a language, no storage use, and an honest answer about state. The render itself and the control audit are suggestions in this version.

---
provenance: part of the Sutra apps frameworks kit; the rules of record with their sources are in `frontend.rules.md` next to this file.
