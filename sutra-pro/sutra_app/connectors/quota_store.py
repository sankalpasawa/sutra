"""The last quota snapshot of each provider, kept across restarts (GAP-providers).

    <data>/connectors/quota.json    {"version": 1, "providers": {"claude": Quota, "codex": Quota}}   mode 0600, written atomically

    store = attach_quota_store(router.health, data_dir / "connectors" / QUOTA_FILE)      # the factory, at start-up

`attach_quota_store` loads the file into the HealthBook (`restore_quota`: a snapshot keeps its own `seen_at`, so an exhausted one
still blocks until its `resets_at`, or the quota cooldown from when it was seen) and writes the file again on every change the book
reports. Before this, a restart said "No quota signal yet" until the next call, and a provider out of quota was tried again.

A file that does not read or does not validate is ignored (logged, then replaced by the next snapshot); only claude and codex are
written. The file holds the figures the CLIs reported and nothing else: no account, no credential, no prompt.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Literal, Optional

from pydantic import ValidationError

from sutra_app import oslayer

from .base import write_private_file
from .health import HealthBook
from .models import M, Quota

__all__ = ["QuotaStore", "QuotaFile", "attach_quota_store", "QUOTA_FILE"]

log = logging.getLogger("sutra_app.connectors.quota_store")

QUOTA_FILE = "quota.json"
_KEPT = ("claude", "codex")
_MAX_BYTES = 256 * 1024


class QuotaFile(M):
    version: Literal[1] = 1
    providers: dict[Literal["claude", "codex"], Quota] = {}


class QuotaStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._held: dict[str, Quota] = {}

    def load(self) -> dict[str, Quota]:
        """The stored snapshots; {} when there is no file or it does not read (never raises)."""
        try:
            if self.path.stat().st_size > _MAX_BYTES:
                log.warning("the quota file %s is larger than %d KB and is not read", self.path, _MAX_BYTES // 1024)
                return {}
            parsed = QuotaFile.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("the quota file %s is not used (%s); the next snapshot replaces it", self.path, type(exc).__name__)
            return {}
        with self._lock:
            self._held = dict(parsed.providers)
        return dict(parsed.providers)

    def save(self, provider: str, quota: Optional[Quota]) -> None:
        """Keep `quota` for `provider` (None forgets it) and write the whole file, atomically and private. Raises OSError."""
        if provider not in _KEPT:
            return
        with self._lock:
            if quota is None:
                self._held.pop(provider, None)
            else:
                self._held[provider] = quota
            body = QuotaFile(providers=dict(self._held)).model_dump_json(indent=2)       # type: ignore[arg-type]
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            tmp = self.path.parent / f".{self.path.name}.{uuid.uuid4().hex[:8]}.tmp"
            try:
                write_private_file(tmp, body)
                oslayer.replace(tmp, self.path)
            finally:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass


def attach_quota_store(book: HealthBook, path: Path) -> QuotaStore:
    """Load the stored snapshots into `book`, then keep the file in step with it."""
    store = QuotaStore(path)
    for provider, quota in store.load().items():
        book.restore_quota(provider, quota)              # type: ignore[arg-type]
    book.on_quota_change(store.save)
    return store
