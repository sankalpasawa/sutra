"""Appearance choices that belong to this app profile, not to one browser port: today the team avatar style.

    store = AppearanceStore(data_dir)
    store.load()                                # {"version": 1, "avatars": "classic" | "illustrated"}; anything missing, unreadable or unknown reads as the default
    store.avatars()                             # the style alone; never raises
    store.save({"avatars": "illustrated"})      # checks the choice, writes it, returns the document as kept (ValueError on a value that is not a style)

"classic" is the avatars Sutra Pro has always drawn and is the default for a new install, an old install, an unknown value and a failed read.
"illustrated" is the portrait artwork, chosen under Settings & logs > Appearance > Team avatars.

Storage: `<data_dir>/ui/appearance.json`, written whole to a temp file in the same folder and swapped in with `oslayer.replace` (the way the sidebar
sections are kept). Browser storage is not used: it is per port, and the desktop app's port can change between launches. The API route writes the
file; the page server learns the style through `Services.avatars` (the UI package imports no other part of the app) and writes it into the boot
block of Home and of a team page.
"""
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from sutra_app import oslayer

__all__ = ["AppearanceStore", "AVATAR_STYLES", "DEFAULT_AVATARS", "VERSION", "FILE_PARTS", "default_doc", "is_avatar_style"]

log = logging.getLogger(__name__)
VERSION = 1
AVATAR_STYLES = ("classic", "illustrated")
DEFAULT_AVATARS = "classic"
FILE_PARTS = ("ui", "appearance.json")  # under the data folder
_LOCK = threading.Lock()                # one writer at a time for every store of this process (the owner changes this rarely)


def default_doc() -> dict[str, Any]:
    return {"version": VERSION, "avatars": DEFAULT_AVATARS}


def is_avatar_style(value: object) -> bool:
    return isinstance(value, str) and value in AVATAR_STYLES


class AppearanceStore:
    """The one appearance file of a data folder. Holds no state but its path, so a route builds one per call."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self.path = Path(data_dir).joinpath(*FILE_PARTS)

    def load(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return default_doc()
        except OSError as exc:
            log.warning("appearance: cannot read %s (%s); showing the classic avatars", self.path, exc)
            return default_doc()
        try:
            doc = json.loads(text)
        except ValueError:
            doc = None
        if not isinstance(doc, dict) or not is_avatar_style(doc.get("avatars")):
            log.warning("appearance: %s is damaged; showing the classic avatars until the next save", self.path)
            return default_doc()
        return {"version": VERSION, "avatars": doc["avatars"]}

    def avatars(self) -> str:
        """The avatar style to draw. Never raises: a page is served with the default when anything at all goes wrong."""
        try:
            return str(self.load()["avatars"])
        except Exception:  # noqa: BLE001  (a page must not fail because of a look choice)
            log.warning("appearance: could not read the avatar style; showing the classic avatars", exc_info=True)
            return DEFAULT_AVATARS

    def save(self, doc: object) -> dict[str, Any]:
        style = doc.get("avatars") if isinstance(doc, dict) else None
        if not is_avatar_style(style):
            raise ValueError("avatars must be one of: " + ", ".join(AVATAR_STYLES))
        kept = {"version": VERSION, "avatars": style}
        with _LOCK:
            self._write(json.dumps(kept, ensure_ascii=False, indent=2) + "\n")
        return kept

    def _write(self, text: str) -> None:
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{self.path.name}.", suffix=".tmp")      # the same folder: the swap is atomic
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            oslayer.replace(tmp, self.path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
