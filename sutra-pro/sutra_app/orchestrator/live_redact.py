"""The live-text redactor: hold back only what could still become a secret (streaming design D204, work package STR-4).

`Redactor` replaces whole secret values. A model streams its text in arbitrary pieces, so a secret can arrive split across two pieces, and a piece-by-piece
`redact` would let both halves through. Holding back the last word is no answer: a secret can contain spaces and newlines, and the set changes while the app
runs. So the hold-back works from the secrets themselves.

    hold = HoldBack(services.redact)
    shown = hold.push(delta)        # what may be shown now (redacted); the tail that could still grow into a secret stays held
    shown = hold.finish()           # at the end of the block: the rest, redacted (a partial prefix is not a secret)

Rule: after `held + delta`, the longest trailing piece that is a proper prefix of a CURRENT secret is held back; everything before it is redacted and returned.
Properties, each tested:
  * no secret value, however it is split into pieces and whatever it contains (spaces, newlines), appears in the pieces returned;
  * in the normal case nothing is held (the tail starts no secret), so there is no added latency;
  * at most `longest secret - 1` characters are held; a complete secret that the cut would split is redacted whole and shown, not held;
  * the concatenation of everything returned is the text that is stored (the caller stores what it showed);
  * the set of secrets is read on every push (`redact.secrets()`): a secret that enters the environment mid-turn applies from the next push; text that was already
    shown is not changed afterwards.
A `redact` without `.secrets()` (a plain function) holds nothing and redacts each piece as it comes.
"""
from __future__ import annotations

from typing import Callable, Optional

__all__ = ["HoldBack", "holdback_factory"]


class HoldBack:
    def __init__(self, redact: Callable[[str], str]) -> None:
        self._redact = redact
        self._held = ""

    @property
    def held(self) -> str:
        return self._held

    def _secrets(self) -> list[str]:
        found = getattr(self._redact, "secrets", None)
        if not callable(found):
            return []
        try:
            return [s for s in found() if isinstance(s, str) and s]
        except Exception:                 # noqa: BLE001  a redactor that cannot list its secrets must not break a turn: nothing is held then
            return []

    def push(self, delta: str) -> str:
        """The part of `held + delta` that is safe to show now, redacted. The rest stays held."""
        text = self._held + (delta or "")
        if not text:
            return ""
        secrets = self._secrets()
        cut = self._cut(text, secrets)
        self._held = text[cut:]
        return self._redact(text[:cut]) if cut else ""

    def finish(self) -> str:
        """The held remainder, redacted: a block that ended with a partial prefix of a secret shows it (a partial prefix is not a secret)."""
        text, self._held = self._held, ""
        return self._redact(text) if text else ""

    @staticmethod
    def _cut(text: str, secrets: list[str]) -> int:
        """Where the shown part ends: the start of the longest trailing piece that is a proper prefix of some secret, moved forward past any complete secret that
        this cut would split. `len(text)` when nothing needs to be held."""
        if not secrets:
            return len(text)
        end = len(text)
        cut = end
        for secret in secrets:
            first = secret[0]
            lowest = max(0, end - (len(secret) - 1))
            i = text.find(first, lowest)
            while i != -1 and i < cut:
                if secret.startswith(text[i:]):          # text[i:] is shorter than the secret (i >= end - len + 1) and begins it
                    cut = i
                    break
                i = text.find(first, i + 1)
        # a complete secret that starts before the cut and ends after it: show (redact) it whole now, so the cut never splits it. The cut only moves forward, so what
        # is held stays a suffix of the piece found above, and is never longer than the longest secret minus one
        moved = True
        while moved:
            moved = False
            for secret in secrets:
                i = text.find(secret, max(0, cut - len(secret) + 1))
                while i != -1 and i < cut:
                    if i + len(secret) > cut:
                        cut, moved = i + len(secret), True
                        break
                    i = text.find(secret, i + 1)
                if moved:
                    break
        return cut


def holdback_factory(redact: Callable[[str], str]) -> Callable[[], HoldBack]:
    """A factory of one `HoldBack` per text block (the block accumulator makes one for every text block it opens)."""
    return lambda: HoldBack(redact)
