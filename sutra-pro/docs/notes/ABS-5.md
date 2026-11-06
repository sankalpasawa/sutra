# ABS-5 as built

`connectors/tool_kinds.py`: `classify(name, input, provider)` -> read|edit|run|search|web|other (never raises; unknown = other), `title_of`.
`RouterChatPort._map` builds the typed `block` events (a result inherits the kind and name of its call by id) and `turn_done` carries all blocks; `ChatTurnOut.blocks` keeps them.
Riders: `claude.py` tool_result events gain `truncated` (the parser already cut content at 2 000 characters; now it says so). The parsers themselves keep emitting `ConnectorEvent`s; the typing happens in the port, so J2's one-shot path sees no change.
Not built: `thinking` blocks (neither CLI parser exposes them today; the type exists in the closed model for ABS-6).
