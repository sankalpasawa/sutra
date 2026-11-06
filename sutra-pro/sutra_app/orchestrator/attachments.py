"""The orchestrator's face of attachments (ABS-4): one store under the data folder, limits checked on upload (the route is ABS-7)."""
from __future__ import annotations

import os

from sutra_app.connectors.attachments import MAX_PER_MESSAGE, AttachmentStore
from sutra_app.connectors.chat_models import AttachmentRef

__all__ = ["Attachments"]


class Attachments:
    def __init__(self, data_dir: "str | os.PathLike[str]") -> None:
        self.store = AttachmentStore(data_dir)

    def upload(self, name: str, blob: bytes) -> AttachmentRef:
        """Stores one file (refused with a sentence for a kind or size we do not take)."""
        return self.store.save(name, blob)

    def upload_many(self, files: "list[tuple[str, bytes]]") -> list[AttachmentRef]:
        if len(files) > MAX_PER_MESSAGE:
            from sutra_app.connectors.errors import InvalidRequestError
            raise InvalidRequestError(f"up to {MAX_PER_MESSAGE} files per message")
        return [self.store.save(n, b) for n, b in files]

    def get(self, ref_id: str):
        return self.store.path_of(ref_id)
