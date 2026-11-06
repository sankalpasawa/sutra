# ABS-7 as built

`orchestrator/api/chat_v2.py` (registered in `main.ROUTERS` BEFORE `agent` and `chat`, so `/api/chats/search` is never read as a session id):
GET `/api/chats/search`, POST `/archive` and `/unarchive`, GET `/providers`, PUT `/choice` (stored in `chat_sessions.pinned` and pinned in the Router; a provider that cannot run is 422), POST `/attachments` (JSON `{name, content_b64}`, no multipart dependency), POST `/direct`.
Deviation from the spec text, decided here: the free-form node chat is its own route `POST /api/chats/{sid}/direct` (202, one turn at a time per chat, 409 `busy`) instead of extending `POST /api/chats/{sid}/messages`. That route belongs to the chat agent (org) and to the team's Identity (department, division), and changing its meaning would touch `api/agent.py` and the J2 delivery path. `direct` is explicit: the owner asks the chat model, the team's J2 run is not involved. The org chat's staged agent path is untouched.
Streaming: `chat.partial` joined `events.CONTROL_TYPES` (seq 0, never in the ring); the reply is stored once at `turn_done` with its typed blocks (a failed turn stores an `error` message). Text goes through the app's `Redactor` on the way in and out.
Riders: `wiring.AppServices` gained `chat_port` and `attachments` (built from the connector router; in a test app with an injected connector the router is stub-only, so the pill is empty there); `main.ROUTERS`; `events.py`.
Not done: attachments on the org chat message (its staged agent calls take no files); the UI is ABS-9/10.
