"""Every usage window of a plan, named in words, and the plan named in words (GAP-providers; the old app's usage.py `_rows`, `_label`,
`_claude_windows`, `_codex_window_label`, `_codex_windows`, `_claude_plan_label`, `_codex_plan_label`).

    windows_from_claude(info)          a `rate_limit_event.rate_limit_info` -> [QuotaWindow]: every entry of `unifiedWindows` (five_hour,
                                       seven_day and any key the CLI adds), else the one window `rateLimitType` names
    windows_from_codex(rate_limits)    a rollout `rate_limits` -> [QuotaWindow]: primary, then secondary, keyed by `window_minutes`
    window_key(minutes)                a Codex duration -> a key: 300 five_hour, 10080 seven_day, 43200 thirty_day, else "<n>_min"
    window_label(key)                  a key -> words ("5-hour", "Weekly", "Monthly", "2-hour"); a key nobody listed still gets words
    plan_label(provider, plan)         "max" -> "Claude Max", "go" -> "ChatGPT Go"; an unknown plan is title-cased, never dropped

Pure: no file, no clock, no process, no model call. `used` is a fraction (0.62 = 62 %), like Claude's utilization; a figure the
provider did not send stays None, never 0, because an empty bar is a claim. NOT taken from the old app: the OAuth usage endpoint and
the read of ~/.claude.json (D34), so the "20x" tier, which lives only there, is not shown.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping, Optional

from .models import QuotaWindow

__all__ = ["windows_from_claude", "windows_from_codex", "window_key", "window_label", "plan_label", "CLAUDE_PLANS", "CODEX_PLANS"]

_KEY = re.compile(r"[a-z0-9_]{1,40}")
_MINUTES = re.compile(r"(\d{1,6})_min")
_CODEX_KEYS = {300: "five_hour", 10080: "seven_day", 43200: "thirty_day"}
_LABELS = {"five_hour": "5-hour", "seven_day": "Weekly", "thirty_day": "Monthly", "one_day": "Daily"}
_ORDER = ("five_hour", "one_day", "seven_day", "thirty_day")
_CONTROL = re.compile(r"[\u0000-\u001f\u007f]+")

# A clean label, never a raw tier string; a plan that ships next month is title-cased instead of disappearing (old usage.py).
CLAUDE_PLANS = {"free": "Free", "pro": "Pro", "max": "Max", "team": "Team", "enterprise": "Enterprise"}
CODEX_PLANS = {"free": "Free", "go": "Go", "plus": "Plus", "pro": "Pro", "team": "Team", "business": "Business",
               "enterprise": "Enterprise", "edu": "Edu"}
_PRODUCT = {"claude": ("Claude", CLAUDE_PLANS), "codex": ("ChatGPT", CODEX_PLANS)}


def _number(value: Any) -> Optional[float]:
    """A finite, non-negative number, else None (a bool is not a number here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def window_key(minutes: Any) -> Optional[str]:
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes <= 0:
        return None
    whole = int(minutes)
    return _CODEX_KEYS.get(whole, f"{whole}_min")


def window_label(key: str) -> str:
    if key in _LABELS:
        return _LABELS[key]
    found = _MINUTES.fullmatch(key)
    if found:
        minutes = int(found.group(1))
        if minutes % 1440 == 0:
            return f"{minutes // 1440}-day"
        if minutes % 60 == 0:
            return f"{minutes // 60}-hour"
        return f"{minutes}-minute"
    if key.startswith("seven_day_"):                       # Claude's per-model weekly windows (seven_day_opus, seven_day_sonnet)
        rest = key[len("seven_day_"):].replace("_", " ").strip()
        return f"Weekly ({rest.title()})" if rest else "Weekly"
    words = key.replace("_", " ").strip()
    return (words[:1].upper() + words[1:])[:60] if words else "Limit"


def _sorted(windows: Iterable[QuotaWindow]) -> list[QuotaWindow]:
    seen: dict[str, QuotaWindow] = {}
    for w in windows:
        seen.setdefault(w.key, w)                          # the first figure for a key wins
    rank = {key: i for i, key in enumerate(_ORDER)}
    return sorted(seen.values(), key=lambda w: (rank.get(w.key, len(_ORDER) + (0 if w.key.startswith("seven_day") else 1)), w.key))


def _window(key: Any, used: Optional[float], resets_at: Optional[float]) -> Optional[QuotaWindow]:
    if not isinstance(key, str) or _KEY.fullmatch(key) is None:
        return None                                        # a key names nothing but itself: anything else is dropped, not shown
    return QuotaWindow(key=key, label=window_label(key), used=used, resets_at=resets_at)


def windows_from_claude(info: Mapping[str, Any]) -> list[QuotaWindow]:
    """Claude's `rate_limit_info`: `unifiedWindows` holds every window ({five_hour: {utilization, resetsAt}, seven_day: {...}}). When it
    is missing, the window `rateLimitType` names, with the event's own `utilization` and `resetsAt`."""
    found: list[QuotaWindow] = []
    unified = info.get("unifiedWindows")
    if isinstance(unified, Mapping):
        for key, entry in unified.items():
            if isinstance(entry, Mapping):
                window = _window(key, _number(entry.get("utilization")), _number(entry.get("resetsAt")))
                if window is not None:
                    found.append(window)
    if not found:
        window = _window(info.get("rateLimitType"), _number(info.get("utilization")), _number(info.get("resetsAt")))
        if window is not None:
            found.append(window)
    return _sorted(found)


def windows_from_codex(rate_limits: Mapping[str, Any]) -> list[QuotaWindow]:
    """Codex's rollout `rate_limits`: `primary` and `secondary`, each {used_percent, window_minutes, resets_at}. The window names come
    from the duration (the measured account has ONE 43 200-minute window and no secondary), so a duration nobody listed still renders."""
    found: list[QuotaWindow] = []
    for slot in ("primary", "secondary"):
        entry = rate_limits.get(slot)
        if not isinstance(entry, Mapping):
            continue
        percent = _number(entry.get("used_percent"))
        window = _window(window_key(entry.get("window_minutes")) or slot, None if percent is None else percent / 100.0,
                         _number(entry.get("resets_at")))
        if window is not None:
            found.append(window)
    return _sorted(found)


def plan_label(provider: str, plan: Any) -> Optional[str]:
    """The plan in words with the product in front ("Claude Max", "ChatGPT Plus"); None when the provider named no plan."""
    if not isinstance(plan, str):
        return None
    words = " ".join(_CONTROL.sub(" ", plan).replace("_", " ").replace("-", " ").split())[:40]
    if not words:
        return None
    product, table = _PRODUCT.get(provider, ("", {}))
    if product and words.lower().startswith(product.lower() + " "):
        words = words[len(product) + 1:]
    known = table.get(words.lower().replace(" ", "_"))
    word = known or words.title()
    return f"{product} {word}" if product else word
