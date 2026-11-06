# ABS-1 as built

`connectors/chat_models.py` (closed models) and `connectors/chat_port.py` (`ChatPort` protocol, `RouterChatPort`). No existing file edited.

- `providers(session_id)`: claude and codex only (the stub is for tests), each with `ready`/`why_not` from `Router.provider_summary` and the policy; an API-key provider is not ready (D7).
- `choose` pins through `Router.chat_pin` (session.json plus the in-memory pin); the policy default is never written. ABS-6/8 make the pin durable and read it in `Router.plan` for every surface.
- `plan_switch` reads `session.json` and the TranscriptSource only; tier none/full/digest follows the J2 rule of `render_carry_over`; `scrub` and `window_source` stay empty/`j2-cap` until ABS-2 and ABS-3.
- `stream` maps connector events: `text_delta` -> `partial`, `text` -> `block` (only when no partial was seen), `tool_call`/`tool_result` -> `block` with `kind: other` until ABS-5; it ends with `usage`, `switched` (when the provider changed during the turn) and `turn_done`.
- Attachments are refused by name until ABS-4 provides the delivery.
- One deviation from the spec text: the pill reads `Router._pins` for a not-yet-persisted choice (no public getter); ABS-6 removes that.
