"""DeepSeek balance: pay-as-you-go credit remaining, read-only, for the panel.

WHY THIS IS A SEPARATE MODULE FROM usage.py
--------------------------------------------
usage.py reports Claude's plan rate-limit WINDOWS (percent utilized, resets_at)
-- Claude has no dollar figure the panel can show. DeepSeek is the inverse:
pay-as-you-go, no five-hour/weekly window, no plan tier -- the only account-wide
fact the API exposes is a USD balance. Different shape, different meaning,
different severity thresholds. Sharing one module (or one cache file) would mean
`_valid()` growing branches that only exist to keep two unrelated payloads apart.

WHAT NEVER CROSSES THIS BOUNDARY
---------------------------------
DEEPSEEK_API_KEY. It is read from the server environment to make the request
and is never returned, logged, or stored by this module. `sanitize()` builds an
explicit allow-list of fields, same discipline as usage.py: a new key the
DeepSeek API adds later has to be opted IN here before it can reach a screen.

FAILS OPEN, ALWAYS. No key, no network, a shape change -- every one of them
returns `available: False` with a reason. Nothing here may raise into a route.
"""

import json
import os
import time
import urllib.request

# Own cache, own directory entry -- NOT usage.py's CACHE. That file is shared
# with the Claude-only PreToolUse guard (bin/sutra-usage) and its `_valid()`
# only recognises Claude's `limits` / `five_hour` / `seven_day` shapes; a
# DeepSeek payload written there would just be ignored, but two unrelated
# writers sharing one file is a race worth not having regardless.
GUARD_DIR = os.environ.get(
    "SUTRA_USAGE_GUARD_DIR", os.path.expanduser("~/.sutra-usage-guard"))
CACHE = os.path.join(GUARD_DIR, "deepseek-balance-cache.json")

BALANCE_URL = "https://api.deepseek.com/user/balance"

CACHE_TTL = 60.0     # seconds a cache entry is served without re-fetching
STALE_MAX = 600.0    # how stale a cache may be when the network is down
HTTP_TIMEOUT = 4.0


def _valid(d):
    """A payload worth caching: the one field this module needs, present."""
    return isinstance(d, dict) and isinstance(d.get("balance_infos"), list)


def _cached(max_age):
    try:
        if time.time() - os.path.getmtime(CACHE) <= max_age:
            d = json.load(open(CACHE))
            return d if _valid(d) else None
    except Exception:
        pass
    return None


def _fetch():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None, "DEEPSEEK_API_KEY is not set in the server environment"
    req = urllib.request.Request(
        BALANCE_URL, headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return None, "could not reach the balance endpoint (%s)" % type(e).__name__
    if not _valid(d):
        return None, "the balance endpoint returned a shape this build does not recognise"
    try:
        os.makedirs(GUARD_DIR, exist_ok=True)
        tmp = CACHE + ".tmp." + str(os.getpid())
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, CACHE)
    except Exception:
        pass          # a cache we could not write is not a failed read
    return d, None


# Allow-list per row. `total_balance` is the figure the panel leads with;
# `granted_balance` / `topped_up_balance` are documented DeepSeek fields kept
# behind the same allow-list discipline as usage.py -- forwarded when present,
# never invented when absent.
_ROW_FIELDS = ("currency", "total_balance", "granted_balance", "topped_up_balance")


def _rows(d):
    out = []
    for e in d.get("balance_infos") or []:
        if not isinstance(e, dict):
            continue
        out.append({k: e.get(k) for k in _ROW_FIELDS if k in e})
    return out


def sanitize(d, source):
    """Allow-list projection of the raw payload. The key never appears here."""
    return {
        "available": True,
        "source": source,                       # "live" | "cache" | "stale-cache"
        "fetched_at": time.time(),
        "is_available": bool(d.get("is_available")),
        "balances": _rows(d),
    }


def snapshot():
    """Current DeepSeek balance, or an explicit unavailability. Never raises."""
    try:
        d = _cached(CACHE_TTL)
        if d is not None:
            return sanitize(d, "cache")
        d, err = _fetch()
        if d is not None:
            return sanitize(d, "live")
        stale = _cached(STALE_MAX)
        if stale is not None:
            return sanitize(stale, "stale-cache")
        return {"available": False, "reason": err or "no balance data available",
                "is_available": None, "balances": []}
    except Exception as e:
        return {"available": False,
                "reason": "balance lookup failed (%s)" % type(e).__name__,
                "is_available": None, "balances": []}
