# ABS-4 as built

`connectors/attachments.py`: `AttachmentStore` (`<data>/attachments/<sha256>.<ext>`, 0600, once per content, kind by sniffing, 20 MB, text only with an allowed extension), `deliver(store, refs, provider)` -> `Delivery(images, text)`.
`orchestrator/attachments.py`: `Attachments` (upload, upload_many with the 10-per-message limit, get). The upload route is ABS-7.
`RouterChatPort(attachments=store)` resolves the provider of the turn (pin, else the plan's first) and builds the `Message`: images (and PDFs for Claude) as `Message.images` paths, text inline.
Riders: `claude._image_line` now also builds gif/webp images and `document` blocks for PDFs. `codex.py` needed no change (`-i` already goes before `-m`; images only). A PDF to Codex is refused with its name (no PDF text extraction is available without a new dependency).
`AttachmentRef` fields were already complete in ABS-1.
Known gap: the owner's stored message has no file text, so the carry-over's own-message dedupe does not match a message that carried text; harmless (the message appears once as history and once as the new message only on a provider switch).
