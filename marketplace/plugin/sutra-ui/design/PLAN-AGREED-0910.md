# Agreed with the owner, 2026-09-10 evening

Everything below is decided and waiting to be built. Nothing here is implemented yet.
Written after 2.259.1 shipped, so this is the queue on top of that.

Order is by value, not by effort. Item 1 is far and away the biggest.

---

## 1. The destination lag — MEASURED, and it is not what it looked like

**The complaint.** "Going from agents to org takes a hell of a lot of time. Org to agents is
fine. Agents to chat takes so long."

**What is actually happening.** Nothing to do with the Agents tab. Measured on his own data:

| hop | main thread frozen | DOM nodes on arrival |
|---|---|---|
| org -> agents | 38 ms | 258 |
| agents -> org | 1017 ms | 61,688 |
| agents -> now | 856 ms | 61,647 |

Arriving at Agents is fast because that screen is 258 nodes. Arriving ANYWHERE ELSE is slow
because every other destination re-renders the open chat pane, and his open chat
("Dust spaces and connections") has **600 turns = 61,400 DOM nodes**.

**Proof by removal.** Same hops with that one pane closed:

| hop | frozen |
|---|---|
| agents -> org | 30 ms |
| agents -> now | 31 ms |

1017 ms -> 30 ms. A 34x difference from one pane. The chat length is the whole cause.

**Why it costs anything at all:** `render()` replaces `#panes` wholesale via innerHTML. The
codebase already knows this — the comment on test_panel 22a says so, and streaming was moved
off `scheduleRender()` for exactly this reason. Destination switching never got the same
treatment, so every hop rebuilds all 600 turns from scratch.

**The fix, in order of what it buys:**

1. **Do not rebuild a pane that did not change.** A destination switch changes which screen is
   shown; it does not change the contents of an open chat. This is the real fix and it makes
   every hop fast regardless of chat length.
2. **Windowing/virtualising a long transcript.** Only render turns near the viewport. Helps
   scrolling and first open too, but it is a bigger job. Do it second, if at all.

Do NOT "fix" this by capping how many turns a chat may hold. The chat is not the bug.

---

## 2. Only the Sutra nav collapses, not the Chats list

**Owner:** "It is also collapsing the chat one. I don't want the chat to get collapsed, I only
want the left part, the Sutra thing, to get collapsed."

**Careful, this reverses an earlier deliberate fix.** `panel.css` today:

```css
.app.threecol.railcol .rail,.app.threecol.railcol .plane{display:none}
```

with the comment: *"Without these rules railcol left the 4-track grid intact, so the plane slid
into the rail's 224px track and the DETAIL crammed into the plane's 240px track (clipped, third
track empty) — the overlap the founder reported."*

And `test_nav.js` asserts it: *"collapsed must hide BOTH lanes — hiding only the rail is the
shipped overlap bug."*

So hiding both was the blunt fix for a real overlap the owner himself reported.

**The correct fix** is to make the grid drop exactly ONE track when the rail collapses, instead
of leaving four tracks and letting every lane shift left by one:

```
open:      rail | plane | detail | term
collapsed:        plane | detail | term      <- one track fewer, plane SURVIVES
```

The test has to change with it, and its new wording must record why: the old rule existed to
stop an overlap, and the new rule must prove the overlap does not come back. Cover the
`noplane` destinations too (Now, Agents) — those already have no plane and must not regress.

---

## 3. Cap the sidebar drag tighter

Today: min 176, max 420, collapses below 132. So it IS bounded already; 420 is just too
generous and reads as "stretchy" rather than "a lane you nudge".

**Change:** max 420 -> ~300. One number, `RAIL_MAX` in `static/js/09-tail.js`.

Worth stating: the Chats column beside it is a fixed 240px and is not draggable at all, which
is why the nav is the only thing that moves.

---

## 4. The chat pane composer is too small

**Owner:** "The agent size is fine. The chats part is not really fine."

So this is the app-wide chat pane composer (`.pc` in `panel.css`), NOT `.ag-field`. It is shared
by every pane, so this changes the whole app at once. That is intended, but it is one decision
affecting everything.

| thing | now | to |
|---|---|---|
| input text | 12px | 13px |
| input padding | 8px 11px | ~10px 13px |
| send button | 24px | 28px |
| the ···, attach and chat icons | ~24px | 28px |

**One notch, not two.** A taller bar takes height from the conversation above it, and with two
panes open side by side that is the space actually being read.

---

## 5. Notifications (approved)

There are none today: no `new Notification` anywhere in the app or the shell.

**The rule: only notify for things the person is NOT watching.** A notification for something
on screen in front of you is noise, and noise is how people turn notifications off for good.

- Only when the Sutra window is **not focused**
- Only for finished / failed / waiting-on-you, never step-by-step progress
- Clicking it opens that chat at that point

| when | what it says |
|---|---|
| the draft is ready | "Your article on cost per hire is ready to read" |
| it needs an answer | "Sutra needs an answer before it can carry on" |
| a run failed | "The site read stopped: the site refused the crawl" |
| a long refresh finished | "Knowledge is up to date: 37 new, 4 gone" |

**Ask for permission LATE.** macOS prompts on the first notification. Asking on first launch,
before the person knows what Sutra would tell them, gets a "no" that is hard to undo. Ask the
first time something actually takes a while, so the request has a visible reason behind it.

---

## 6. The DMG window should look like an installer

We already ship the drag target: `make-dmg.sh:421` creates the `Applications` symlink, so
mounting shows `Sutra.app` beside `Applications`. What is missing is the styling every other
Mac app has: a background image, the dashed arrow, and the icons placed deliberately.

Ours is a bare Finder window with two icons. It works and it looks unfinished.

Needs a background image plus an AppleScript step at build time to set the window bounds and
icon positions. Nothing about the app changes, only the first thing anyone ever sees.

The `READ ME FIRST.txt` we ship is the honest fallback for an unstyled window. With a proper
background it stops being necessary.

---

## 7. One dishonest sentence in the move-to-Applications dialog

The dialog says **"You will not be asked again."** That is only true if the person ticks the
checkbox. Click "Not now" without ticking and it asks again next launch.

Small, but a message that promises something the code does not do costs trust in every other
message the app shows. Either make the sentence conditional, or make "Not now" mean it.

---

## Not doing

- **A drag edge on the agent's own chat sidebar.** The owner's screenshot settled that "the left
  one" means the main Sutra nav. Built it once, reverted it: it was unrequested surface and it
  broke five tests while it existed.
- **Capping chat length to fix the lag.** See item 1. The chat is not the bug.

---

## 8. Workspace faces in the agent header (agreed 2026-09-10, later)

**Owner:** "on the top right we could show icons of all the people who have joined that
workspace."

**The data already exists.** `public.members` holds `member_id, name, joined_at, last_seen_at`,
and `_ws_member_rows()` in `agents_api.py` already reads it (20s cache) for the Connections
tab's "who is in it".

`last_seen_at` is touched every minute by every client, so this can show **who is around now**,
not just who ever joined. That is what makes a row of faces worth looking at.

- Initials in a circle, not photos. The table stores a name and no image; syncing images is a
  much bigger job for very little.
- A green ring for anyone seen in the last few minutes; flat for the rest. Hover gives the name.
- Renders ONLY when a workspace is joined. One face on your own is noise.
- Goes in the header beside "SEO Writer · Testlify", not floating top-right, so it reads as
  "who is on this agent".
- Reuse the existing 20s cache. Do not add a second poll.

---
---

# WHAT ACTUALLY SHIPPED, 2026-09-11 (v2.260.0)

## Item 1, the lag: fixed, but NOT the way this plan predicted

The plan said "do not rebuild a pane that did not change". Built it, measured it, **it bought
nothing** and it broke three tests. Reverted. Two dead ends worth recording so nobody tries them
again:

1. **A keyed per-pane reconciler** instead of one `#panes` innerHTML. No measurable change.
2. **Hiding the session panes on Agents instead of deleting them.** Also no change (695ms ->
   679ms), and it undid the "Agents opens alone" rule three tests exist to protect.

The reason both failed is that the cost was never DOM *construction*. Measured: building the
6.6MB HTML string takes 50ms and a whole `render()` takes 57ms. The half-second was the browser
**laying out and painting 61,400 elements** once they became visible. No amount of not-rebuilding
helps with that; only having fewer elements does.

**What worked: draw the tail of a long transcript, not all of it.** `TURN_WINDOW = 60`, with a
"Show N earlier turns" fold above it, which is the shape `agSubsHtml` already used on the agent
timeline. Nothing is discarded; one click brings it all back.

| hop | before | after |
|---|---|---|
| agents -> org | 695 ms | 90 ms |
| agents -> chats | 509 ms | 93 ms |
| agents -> now | 499 ms | 65 ms |
| DOM nodes | 61,966 | 7,457 |

The owner's instinct was right and my first recommendation was wrong: he asked about VS Code
limiting what it draws, I said do the cheap structural fix first, and the cheap fix did nothing.

## Items 2, 3, 4, 7: shipped as planned

- Collapse hides the Sutra nav only; the Chats list survives. The grid drops a TRACK rather than
  hiding a lane, so the old overlap cannot return, and test_nav asserts the track count.
- RAIL_MAX 420 -> 300.
- Chat composer one notch up: 13px text, 28px send, 28px icons, scoped to `.pc`.
- The move-to-Applications dialog no longer claims "You will not be asked again".

## Item 5, notifications: shipped

Fires only when the window is unfocused, only on a transition, only for runs over 20s (a run
that is WAITING is exempt: being blocked on you is always worth saying). Permission is requested
at the first real notification, never on launch. A hidden window now keeps polling **while work
is live**, because otherwise the news would arrive as you returned to find it anyway.

## Item 6, the DMG window: shipped

Builds a writable image, asks Finder to set the window bounds and the three icon positions,
converts to UDZO. Every step is best-effort: a headless build machine ships an undressed DMG
rather than failing. Verified end to end on a throwaway image; the `.DS_Store` carrying the
positions survives the conversion.

No background bitmap on purpose: it would need redrawing per theme and per Retina scale, and it
is the icon POSITIONS that tell somebody what to do.

## Item 8, the faces: shipped, with an emoji pack

The owner asked for emoji rather than initials. `seo_agent/workspace/faces.py` holds 32, chosen
against four rules that `test_faces` asserts rather than merely documents: legible at 24px,
distinct in silhouette, nothing about a person (no faces, body parts, skin tones or flags), and
nothing that reads as status. All animals.

- `members.emoji`, added by **migration 4**. SCHEMA_VERSION 3 -> 4, and schema.sql now writes 4
  in all three places it states a version.
- A workspace that has not migrated has no such column, and PostgREST answers 400 for a column
  it does not have -- which would have taken the member list down for everyone still on 3,
  including the owner's own live workspace. The read falls back to the old column list.
- Initials remain the fallback for a teammate on an older Sutra.
- The picker offers free faces first; taken ones are dimmed, not disabled, because past 32
  people somebody has to share.
- The owner's face: 🐙.
