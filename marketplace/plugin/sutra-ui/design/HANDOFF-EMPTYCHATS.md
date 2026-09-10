# Handoff — empty "New session" chats in the Chats list

Written by the agent that fixed the panel's Chats list. Everything under
`seo_agent/`, plus `static/js/17-agents.js`, `static/agents.css`, `agents_api.py`
and `test_agents.js`, was owned by another agent at the time and is untouched.

## What was wrong

Clicking **New chat** minted a row every time, so the Chats list filled with
`New session · 0 turns` entries nobody had typed in — six of them in front of the
one real conversation, with nothing to tell them apart.

## What was changed (panel only)

`static/js/07-loaders.js`
- `chatUntouched(s)` — the one definition of an empty chat.
- `reusableEmptyChat(cwd, department)` — the focused chat if it is untouched and
  does not already name a different folder or department.
- `startNewChat(cwd, department)` — reuse if there is one, otherwise
  `newSession()`. The rail's New chat button now calls it, and so does the `+` on
  a department heading.

`static/js/08-boot.js` — Cmd/Ctrl+N calls `startNewChat`, so the keyboard cannot
mint what the button would reuse.

Tests: nine cases in `test_panel.js`, section "empty chats".

## What was deliberately NOT done

**No empty chat is deleted, swept, or archived.** A panel chat lives in
`S.sessions` and nowhere else — `saveLayout()` persists `S.ui`, never the session
list — and a chat only reaches disk once a turn is sent (the server mints the
`chat_store` record after the transport returns a session id, in `ws_chat`). So
the empty rows already on screen clear themselves on the next launch, and a sweep
would trade that for a delete predicate one missed field away from taking real
work with it.

If a sweep is ever wanted anyway, `chatUntouched()` is the predicate to build it
on, and it must additionally skip anything in `S.openPanes`.

## The agents surface — checked, nothing owed

`static/js/17-agents.js` has its own **New chat** button. It does *not* have this
bug: `case "new"` only clears `a.chatId` (17-agents.js:2872) and the record is
minted lazily on the first send (`POST /chats` at 17-agents.js:2795), titled from
the message text. So no empty `c-*` chat directory is created by pressing the
button.

Two notes for whoever owns that surface:

1. Its chats are **on disk** (`seo_agent/store.py: new_chat()` writes
   `chat.json` + `messages.json` immediately), unlike the panel's. Any tidying
   there is a real file delete, not a dropped in-memory row — a different risk
   class from anything in this change.
2. `POST /api/agents/seo/chats` (`agents_api.py:141`) creates a chat with no
   messages on request. Nothing in the shipped UI calls it before a send, but any
   new caller that does would recreate exactly the problem fixed here.
