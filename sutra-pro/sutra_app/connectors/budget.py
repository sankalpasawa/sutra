"""How many characters of carry-over fit THIS model's window (absorb design 2.5, D110; ported from the old app's `budget.py`).

The ceiling is per model, not per provider ("Claude's window" is not a number). Unknown model: the smallest catalogued window is assumed
(`window_source="assumed-floor"`): a needlessly short carry-over is a degraded success, an overrun is a rejected request. Characters to tokens
uses 3.0 (dense tool text), which overstates prose, on purpose; the result is an ESTIMATE and says so.

LOWER ONLY: `carry_chars` is `min(J2 cap, budget)`. J2's rule (`transcript.FULL_CHARS`, `TAIL_MESSAGES`, `DIGEST_CAP_CHARS`) stays the ceiling
for every model, so a large window never makes a carry-over bigger than J2's; a small one makes it smaller.
"""
from __future__ import annotations

from typing import Literal, Optional

from .transcript import DIGEST_CAP_CHARS, FULL_CHARS

__all__ = ["WINDOWS", "DEFAULT_WINDOWS", "FLOOR_WINDOW", "CHARS_PER_TOKEN", "REPLY_RESERVE_TOKENS", "USABLE_FRACTION", "window_for",
           "for_target", "estimate_tokens", "fits", "carry_chars"]

WINDOWS: dict[str, dict[str, int]] = {
    "claude": {"fable": 1_000_000, "opus": 1_000_000, "sonnet": 1_000_000, "haiku": 200_000, "best": 1_000_000,
               "opus[1m]": 1_000_000, "sonnet[1m]": 1_000_000,
               # the pinned snapshots of the model picker (model_catalog.py): DECLARED, NOT MEASURED, carried over from their siblings as the old
               # app did; if one is smaller the failure is an over-sized carry-over, which is why the assumption is written here
               "claude-opus-4-8": 1_000_000, "claude-opus-4-7": 1_000_000, "claude-opus-4-6": 1_000_000, "claude-sonnet-4-6": 1_000_000},
    "codex": {},
}
DEFAULT_WINDOWS = {"codex": 258_400}          # what codex enforces (a provider whose default is knowable)
FLOOR_WINDOW = 200_000                        # the smallest catalogued window (Haiku)
CHARS_PER_TOKEN = 3.0
REPLY_RESERVE_TOKENS = 32_000                 # an answer and the turns that follow the switch
USABLE_FRACTION = 0.90

Source = Literal["known", "provider-default", "assumed-floor"]


def window_for(target: str, model: Optional[str] = None) -> dict:
    """`{tokens, source, model}`: declared for this exact model, the provider's default, or the assumed floor."""
    model = (model or "").strip()
    declared = WINDOWS.get(target, {}).get(model)
    if declared:
        return {"tokens": declared, "source": "known", "model": model}
    if target in DEFAULT_WINDOWS and (not model or model not in WINDOWS.get(target, {})):
        return {"tokens": DEFAULT_WINDOWS[target], "source": "provider-default", "model": model}
    return {"tokens": FLOOR_WINDOW, "source": "assumed-floor", "model": model}


def estimate_tokens(chars: int) -> int:
    """Rounded UP: a check that rounds down can pass a payload that does not fit."""
    return 0 if chars <= 0 else -(-int(chars * 1000) // int(CHARS_PER_TOKEN * 1000))


def for_target(target: str, model: Optional[str] = None) -> dict:
    win = window_for(target, model)
    usable = int(max(win["tokens"] - REPLY_RESERVE_TOKENS, 0) * USABLE_FRACTION)
    return {"target": target, "model": win["model"], "window_tokens": win["tokens"], "window_source": win["source"],
            "usable_tokens": usable, "chars_per_token": CHARS_PER_TOKEN, "budget_chars": int(usable * CHARS_PER_TOKEN), "estimate": True}


def fits(chars: int, target: str, model: Optional[str] = None) -> bool:
    return chars <= for_target(target, model)["budget_chars"]


def carry_chars(target: str, model: Optional[str] = None) -> dict:
    """The carry-over limits for this model: `full_chars` and `digest_cap` are J2's caps, lowered to the budget when that is smaller."""
    info = for_target(target, model)
    budget = info["budget_chars"]
    return {"full_chars": min(FULL_CHARS, budget), "digest_cap": min(DIGEST_CAP_CHARS, budget), "window_source": info["window_source"],
            "window_tokens": info["window_tokens"], "lowered": budget < FULL_CHARS}
