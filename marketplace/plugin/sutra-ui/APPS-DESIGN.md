# Apps design system and strategy

Every visual and verbal element the Apps screen uses, traced to the panel's own tokens and components so the screen reads as the app it lives in, not as a page bolted onto it.

| Field | Value |
|---|---|
| **status** | ACTIVE — program steps 33-40 |
| **updated** | 2026-09-11 |
| Design of record | `holding/departments/experience/desktop-app/2026-09-08-modules-design.md` §v12 (D-M16..D-M22) |
| Frames of record | `holding/departments/experience/desktop-app/mocks/2026-09-11-modules-v3-{a-department,b-module,c-edit-chat,d-new-chat}.jpg` — rendered by the running panel on 2026-09-11 |
| Tokens + components | `static/panel.css` (`:root` block; Directory rules from line 719) |

## <a id="s0"></a>§0 Sign-off

Design approved 2026-09-11 by the founder (Apps wording, header-only app view, Edit in chat button, New app via chat). This document records the approved design; it does not reopen it.

## <a id="s1"></a>§1 Token inventory (step 33)

Only tokens the Apps screen uses. Every row exists in `panel.css` `:root` (dark) with a light twin.

| Token | Used for |
|---|---|
| --serif | app name in the app header (`h1`), department name in the department header |
| --sans | everything else that is prose |
| --mono | D-chips, count pills, the crumb "<department> › <kind>", folder paths in seeds |
| --bg | page-app body background when drawn inline (captures only); the sandboxed iframe carries its own tokens (D-M5) |
| --surface | the rail column background |
| --card | app rows, the app body frame |
| --line | borders on hover, the app body frame |
| --line-soft | resting borders on app rows, group rules |
| --ink | names, headers |
| --muted | taglines, hints, secondary buttons |
| --faint | crumbs, department pills on rows, the Unassigned node |
| --acc | selected D-chip border, selected row border, links |
| --acc-bg | selected rail node, selected row background, chip background |
| --ok | status dot for `ready` |
| --inset | search field, kind pill background, count pill background |
| --r | corner radius of the app body frame (10px) |

## <a id="s2"></a>§2 Component inventory (step 34)

| Component | Where it lives | Used by Apps for |
|---|---|---|
| `.facets` + `.seg` | `panel.css:404` | the Live · Draft · Directory · Apps segment and the `+ New app` button on the right |
| `.dpage` grid (200px rail + main) | `panel.css:719` | the two-column layout; collapses to one column under the 720px container query |
| `dirRail()` | `static/js/03-org.js` (rail-helpers region) | the department tree; Apps passes its own `link` (data-moddept), `count` (subtree app total) and `open` (ancestors of the selection) |
| `.navgrp` / `.navkids` / `.dsub` | `panel.css:762-774` | tree groups, indentation, leaf rows; app rows are `.dsub.modleaf` |
| `.navcount` | `panel.css:771` | subtree app counts |
| `.dpage .chip` / `.chip.big` | `panel.css:735-737` | D-path chips in the rail and the header |
| `.btn` | panel button | the one `Edit in chat` button, with a chat glyph |
| `.newBtn` | panel primary button | `+ New app` |
| `.pill.mod-kind` | `panel.css:2193` | the kind pill (chat · page · link) |
| `.mod-dot` | panel.css Apps block | status dot (draft · ready · archived) |
| `.ws-crumb` pattern | `static/js/13-workspace.js:1077` | the narrow-pane crumb "‹ <department> · n apps" |
| `.zero` | panel empty-state | "Nothing here yet." and the empty-registry message |
| `.note.b` / `.note.w` | panel notes | "Apps unavailable" and the "building…" warning |

## <a id="s3"></a>§3 State inventory (step 35)

| State | Trigger | What renders | Decision |
|---|---|---|---|
| empty department | selected department has no apps and no apps below | "Nothing here yet. New app puts it in <department>." | D-M16 |
| empty registry | no domains at all | one Unassigned node in the rail; System + Unassigned on the right; nothing is minted | D-M14 |
| narrow | browse pane under 720px | tree stacks above the list; with an app open the crumb replaces the tree | D-M20 |
| error | `/api/modules` unreachable | "Apps unavailable." with Try again and `+ New app`; no fallback list | v1 codex fold |
| building | a folder whose `module.json` does not parse | a row with the "building…" warning that never disappears | D-M21 |
| unassigned | an app with no live department | listed under Unassigned (rail and root view), department pill "—" | D-M13 |

## <a id="s4"></a>§4 Copy deck (step 36)

User-facing strings. The word for the thing is **App**; "module" never appears where a user reads (D-M22).

| Where | String |
|---|---|
| Org rail row | Apps |
| Pane title | Apps · ~/.sutra-ui/modules · one department each |
| Facet | Apps |
| Primary button | + New app |
| Rail search placeholder | Search departments and apps… |
| Group headings | Apps · In sub-departments · System · Unassigned |
| Subtree toggle | this department only / include sub-departments |
| Department hint | Select an app to open it. Below an app's header is the app itself; Edit in chat changes it. + New app opens a chat that asks what to build. |
| App header button | Edit in chat |
| App header crumb | <department> › <kind> |
| Edit chat title | Edit · <app> |
| New chat title | New app · <department> |
| Edit seed, line 1 | ROUTING PIN — file this session under <D-path> <department> (<ref>). Do not re-classify. |
| Edit seed, line 2 | You are editing the app "<name>" (<kind>) in department <D-path> <department>. |
| Edit seed, closing | You can also move this app to another department or archive it — tell me and I apply it as a structured change. First: read both files, then ask me what should change. |
| New seed, line 2 | Create a new app in department <D-path> <department>. |
| New first reply (expected) | What kind of app do you want to create — a chat, a page, or a link? |
| No provider | Connect a chat provider in Settings to create or edit apps. |
| Empty department | Nothing here yet. New app puts it in <department>. |
| Building | building… — this app's manifest is not readable yet |
| Error | Apps unavailable. |
| API 404 (kind) | no app named <id> |

## <a id="s5"></a>§5 Accessibility (step 37)

| Rule | Detail |
|---|---|
| Current marker | exactly one `aria-current="true"` in the rail: the selected department, or the selected app row |
| Keyboard | Tab reaches the search field, every department link and every app row in document order; Enter activates; the tree's `details` toggles with Space on the summary |
| Focus after paint | `render()` restores focus and caret for the focused input (existing panel rule), so typing in the search field never loses the cursor |
| Names | the rail is `<nav aria-label="Departments">`; the `Edit in chat` button carries a title naming the folder and department |
| Contrast | only tokens that already pass the panel's 4.5:1 floor are used; no new colours |
| Motion | none added |

## <a id="s6"></a>§6 Frames of record and parity (step 38)

| Frame | File | Parity check against production |
|---|---|---|
| A department view | `2026-09-11-modules-v3-a-department.jpg` | rail shell, accordion, facets, `.dpage` grid all from the running panel |
| B app view | `2026-09-11-modules-v3-b-module.jpg` | header + body only; page drawn inline for the capture (production: sandboxed iframe) |
| C Edit in chat | `2026-09-11-modules-v3-c-edit-chat.jpg` | real chat pane, seeded turn, narrow crumb |
| D New app | `2026-09-11-modules-v3-d-new-chat.jpg` | real chat pane, first reply asks the kind |

Parity rule: a build step is accepted only when the qa-shell STATE lane (`PUBLISH-CHECK.md` lane 1) reproduces the frame's DOM claims; the frame is the target, not the proof.

## <a id="s7"></a>§7 Publish placeholder (step 39)

| Rule | Detail |
|---|---|
| Visibility | no Publish control renders while `flags.apps_publish` is off (default) |
| When on (later program) | a secondary `.btn` "Publish…" joins the app header next to `Edit in chat`; it opens a chat seeded with the export contract (APPS-THREATS.md X-1..X-10) rather than a form |
| Never | no Publish control on the department view; no store browsing in v1.2 |

---
provenance: authored 2026-09-11 (session c0a2923c, atom a-c0a2923c-12) from spec §v12, the captured frames, `static/panel.css` `:root` and Directory rules, and the codex reviews r2 (`.ws-crumb` precedent) and r4 (label sweep); program steps 33-40.
