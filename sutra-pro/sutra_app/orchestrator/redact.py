"""Secret redaction (port of J2's `j2_server.py:29-43`, orchestrator 2, S1-contracts-19, D71).

The secret set is every value of an environment variable whose name contains KEY, TOKEN, SECRET, PASSWORD or AUTH, plus every
value in the `.env` file, minimum length 8, longest first. The caller can add explicit secrets (the launch token, the
override key); those are always redacted, whatever their length. `redact` is applied to every API body, SSE payload, log
line, stored chat text and stderr tail. The environment is read on every call (it may change); the `.env` file is re-read
only when its size or modification time changes.
"""
import os
import threading
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from sutra_app.config import read_env_file

__all__ = ["REDACTED", "NAME_WORDS", "MIN_SECRET_LENGTH", "Redactor"]

REDACTED = "[redacted]"
NAME_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")
MIN_SECRET_LENGTH = 8


class Redactor:
    """`Redactor(env_file)(text)` returns `text` with every secret value replaced by `[redacted]`."""

    def __init__(self, env_file: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None,
                 extra: Iterable[str | Callable[[], str | None]] = ()) -> None:
        self._env_file = Path(env_file) if env_file is not None else None
        self._environ = environ
        self._extra = tuple(extra)
        self._lock = threading.Lock()
        self._file_stamp: tuple[int, int] | None = None
        self._file_values: frozenset[str] = frozenset()

    def _env_file_values(self) -> frozenset[str]:
        if self._env_file is None:
            return frozenset()
        try:
            stat = self._env_file.stat()
            stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        with self._lock:
            if stamp != self._file_stamp:
                self._file_stamp = stamp
                self._file_values = frozenset(
                    [*read_env_file(self._env_file).values(), *read_env_file(self._env_file, whole_line=True).values()]) if stamp is not None else frozenset()
            return self._file_values

    def secrets(self) -> list[str]:
        """The values to hide, longest first (so a secret that contains another is replaced whole)."""
        env = os.environ if self._environ is None else self._environ
        found = {value for name, value in env.items() if any(word in name.upper() for word in NAME_WORDS)}
        found |= self._env_file_values()
        found = {value for value in found if isinstance(value, str) and len(value) >= MIN_SECRET_LENGTH}
        for item in self._extra:
            value = item() if callable(item) else item
            if isinstance(value, str) and value:
                found.add(value)
        return sorted(found, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        for value in self.secrets():
            text = text.replace(value, REDACTED)
        return text

    def scrub(self, obj: Any) -> Any:
        """`obj` (JSON-like: dicts, lists, strings) with every secret removed from every string and every key. Done on the
        data, before it is written as JSON, so a secret that JSON would escape (a quote, a backslash, a non-ASCII letter) is
        still found."""
        secret_list = self.secrets()
        if not secret_list:
            return obj

        def clean(text: str) -> str:
            for value in secret_list:
                text = text.replace(value, REDACTED)
            return text

        def walk(item: Any) -> Any:
            if isinstance(item, str):
                return clean(item)
            if isinstance(item, dict):
                return {(clean(k) if isinstance(k, str) else k): walk(v) for k, v in item.items()}
            if isinstance(item, (list, tuple)):
                return [walk(v) for v in item]
            return item

        return walk(obj)
