# The chat

| Field | Value |
|---|---|
| **status** | v1, 2026-09-29, RECORD of the code (Sutra Desktop v2.306.19-desktop; the organisation row from v2.306.20) |
| Code | `engine_runtime.py` (`request`, `_tell`, `chat_view`, `_own_turns`, `fn_chat_view`, `_line`, `tell_switch`), `website_api.py` (`/{ref}/chat`, `?fn=`), `static/js/22-website.js` (`wbChatHtml`, `wbChatTurn`, `wbChatAsksHtml`, `wbFnChatHtml`, `wbLoadFnChat`, `wbOrgHtml`, `wbRootPaneHtml`, `wbHidden`, `wbBorn`, the click handlers), `static/js/19-org2.js` (`o2Data`, `o2ScreenHtml`, `o2StripHtml`, `o2TreeHtml`) |

## One point of entry

The person speaks to Root from anywhere: the box on Root's chat, or a department's chat with the department as a chip (`data-wbask`; the words go to Root with `about = <dept ref>` unless the chip is taken off). Root's Identity hears (`request`, word `front`), hands the words on to the department they are about (a post from Root to the department's Identity), and the department's answers come back onto Root's board with the department they are about (`_tell`: a tell to a department born of a Root is posted on Root's board too, marked `via: Root` on the department's own copy so it is never counted twice).

## The organisation row (founder, 2026-09-29: "at the organization level, only a chat is shown, and root is not shown")

- On the Org structure screen an organisation with a Root opens Root's chat and nothing else: `o2ScreenHtml` hands the row to `wbOrgHtml`, which paints no list column; the chat is headed by the organisation's name and one button, Root settings.
- Root is not a row of the tree nor a tile of the chart: `o2Data` lifts a hidden Root's departments under the organisation (`wbHidden`: the ref's kind on `/api/native/depts` is `root`; `d.lifted` maps the organisation to its Root, `d.hidden` holds the rows not drawn). The registry is untouched: Root stays a department under the organisation. A department's parent on the strip reads the organisation (`o2StripHtml`).
- Root settings is a pane, never a chat (`wbRootPaneHtml`): what Root does (its goal), On or Off with its one switch (`data-wbstop` / `data-wbresume`), its rules, the departments it has made (chips that open them), Back to the chat.
- The clicks and the box speak for Root: the organisation's row holds Root as the selected department (`dpSelect(root)` in `wbOrgHtml`), so a stamp, Stop, Start and Send post to Root's routes.
- Founding lands on the organisation's row (`wbFoundGo`: `o2Select(org)` once the tree knows its Root, `wbRootOf`); a department Root just made slides into the tree once (`wbBorn`, marked by `wbLoadChat` when the chat learns of it; `.o2row.o2grow`).
- An organisation without a Root on the runtime paints as before (`wbOrgHtml` answers null).

## What the chat shows (`chat_view`)

- On Root: every owner-facing post of Root's board (the person's words with the department they reached, the setup ask and stamp, the hand-over) and each department's own owner-facing turns (`_own_turns`: what its Identity asked or told in threads Root did not start, and the person's own words and stamps there); the birth copy of the goal is folded (finding 3); every pending ask, with the department it belongs to (`asks`); the departments under Root.
- Inside a department: the same chat scoped to it (`about = ref`).
- A department with no Root: its own board.
- Turns are sorted by time then post number; a line is `_line(p)` (the ask's objective, the tell's `done`, the words).
- Front words nobody answered within `FRONT_WAIT_S` (60 s) are said back and shown as waiting (`front_state`; ER-9).

## A function's chat (`fn_chat_view`)

Exists from birth, never started: the function's own posts on the board and the ones addressed to it; the person's words said to it (`about.fn`) and every owner-facing turn of those threads; the tells of the line on the Brief versions those words made (each run tell carries its `chain`; the "filed in the Brief" tell's `v` names the version); its own step rows as quiet think lines ("<step name>, <rung>"; a gate as "<name>: <answer>"), in time order, identical neighbours folded. Read on the click of its Chat tab (`wbLoadFnChat`) and again on the clock while open; Send inside it keeps the person there (`wbask` starting with `fn:`).

## The tells and their buttons (`wbChatTurn`)

| Turn | Shown as |
|---|---|
| the person's words | "You", with the department's chip on Root |
| a stamp or a refusal | "Stamped" / "Refused" |
| a tell with a link, word live | the line and the button "Open the live site" (`data-wblive`: the department opens on its Live site, preview, its own tab set to now) |
| a tell with a link, any other word | the button "Open <artifact>" (`data-wbopenart`: that filed work's preview, the row lit) |
| Stop / Start | "Stopped by you: every engine stops where it is." / "Started by you: every engine looks to its own triggers." (`tell_switch`) |
| a function at work | the working line "<engine> is working: <what>" from `working_now` and the run row's `what` |

## The words the chat speaks

A tell's `word` is one of a closed set the screen knows: request, plan, filed, live, facts, finding, rule, engine, idea, answer, waits, stopped, started, question (each set by the function that says it: `identity_file`, `plan_file`, `run_engine`, `identity_finding`, `identity_engine`, `identity_idea`, `identity_wait_engine`, `tell_switch`).

provenance: {author: claude, session: 17842ce0, date: 2026-09-29, inputs: [engine_runtime.py: request, _tell, chat_view, _own_turns, fn_chat_view, _line, tell_switch, front_state; static/js/22-website.js: wbChatTurn, wbFnChatHtml, the click handlers], review: none by a second model, confidence: high}
