"""Plan usage: rate-limit windows, read-only, for the panel.

WHY THIS EXISTS SEPARATELY FROM bin/sutra-usage
-----------------------------------------------
`bin/sutra-usage` is the GUARD: a CLI plus a PreToolUse hook that decides whether
to warn or block. It reads two hardcoded keys (`five_hour`, `seven_day`) because
two numbers are all a threshold check needs.

The panel needs to SHOW the same thing Claude Code's own usage popover shows, and
that is a different job. The endpoint returns a `limits` LIST whose entries carry
`kind`, `group`, `percent`, `resets_at` and a `scope` — including per-model rows
(`weekly_scoped`, e.g. "Weekly · Fable") that the two hardcoded keys cannot
express at all. Rendering the list means a window Anthropic adds later appears on
its own rather than waiting for this file to learn its key.

BOTH READ THE SAME CACHE FILE ON PURPOSE. The guard and the panel must never
disagree about utilization -- an operator blocked at 80% while the panel says 60%
would have no way to tell which was lying -- and sharing the cache also means
opening the screen does not cost an extra request against the same account.

WHAT NEVER CROSSES THIS BOUNDARY
--------------------------------
The OAuth access token. It is read to make the request and is not returned, not
logged, and not stored anywhere by this module. `sanitize()` builds an explicit
allow-list of fields rather than filtering a denylist out of the raw payload: a
new secret-bearing key added upstream would then have to be opted IN to leak,
instead of leaking until someone notices.

FAILS OPEN, ALWAYS. No token, no network, a shape change, a permissions error --
every one of them returns `available: False` with a reason. The panel says it does
not know. Nothing here may raise into a request handler.
"""

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

# Same directory the guard uses, so the two share one cache and one truth.
GUARD_DIR = os.environ.get(
    "SUTRA_USAGE_GUARD_DIR", os.path.expanduser("~/.sutra-usage-guard"))
CACHE = os.path.join(GUARD_DIR, "cache.json")

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"

CACHE_TTL = 60.0     # seconds a cache entry is served without re-fetching
STALE_MAX = 600.0    # how stale a cache may be when the network is down
HTTP_TIMEOUT = 4.0

# Human labels for the `kind` values observed on a real Max account. An UNKNOWN
# kind is rendered under its own raw name rather than dropped: a limit the
# operator is subject to must never be invisible because this map is out of date.
KIND_LABELS = {
    "session": "Session (5h)",
    "weekly_all": "Weekly · all models",
    "weekly_scoped": "Weekly",          # refined with scope.model below
}

# Which legacy top-level window key describes the same window as a `limits` kind.
# Used ONLY to backfill a reset time the list left null -- never a percentage,
# because the list is authoritative for utilization and two sources of truth for
# one number is how a panel and its guard end up disagreeing.
# `weekly_scoped` has no legacy equivalent: per-model windows only exist in the list.
_LEGACY_KEY_FOR_KIND = {
    "session": "five_hour",
    "weekly_all": "seven_day",
}


def _credentials():
    """The parsed `claudeAiOauth` record, or None. It CONTAINS the tokens:
    callers take the one field they need and never hand the dict onward."""
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        if raw:
            return json.loads(raw)["claudeAiOauth"]
    except Exception:
        pass
    try:
        p = os.path.expanduser("~/.claude/.credentials.json")
        return json.load(open(p))["claudeAiOauth"]
    except Exception:
        return None


def _token():
    """The OAuth access token, or None. Never returned to a caller."""
    c = _credentials()
    try:
        return c["accessToken"] if c else None
    except Exception:
        return None


# The NON-secret half of the credential record, by name. The record also holds
# accessToken / refreshToken / expiry; none of those is in this map and so none
# can be emitted -- a new key upstream has to be opted in here to reach a screen.
_SUBSCRIPTION_FIELDS = {
    "subscriptionType": "subscription_type",   # "max", "pro", ...
    "rateLimitTier": "rate_limit_tier",        # "default_claude_max_20x"
}


def subscription():
    """Which subscription the credentials were issued for, or None.

    Lives here and not in claude_local.py because that module is Keychain-free
    by rule and this one already owns the credential read. Corroborates the
    plan ~/.claude.json describes from the token's own point of view.
    """
    c = _credentials()
    if not isinstance(c, dict):
        return None
    out = {new: (c.get(old) or None) for old, new in _SUBSCRIPTION_FIELDS.items()}
    return out if any(out.values()) else None


def account():
    """The Claude account this panel runs on: profile + subscription, or an
    explicit unavailability. Local reads only -- no network, and independent of
    snapshot() and the cache the guard shares. Never raises."""
    try:
        import claude_local
        prof = claude_local.profile()
        sub = subscription()
    except Exception as e:
        return {"available": False,
                "reason": "account lookup failed (%s)" % type(e).__name__,
                "profile": None, "subscription": None}
    if prof is None and sub is None:
        return {"available": False,
                "reason": "no Claude account is signed in on this machine",
                "profile": None, "subscription": None}
    return {"available": True, "profile": prof, "subscription": sub,
            "sources": ["~/.claude.json",
                        "Claude Code credentials (non-secret fields only)"]}


def _valid(d):
    """A payload worth caching. Deliberately loose: `limits` is the shape this
    module wants, but an older account may only return the window keys, and a
    response carrying either is still usable."""
    if not isinstance(d, dict):
        return False
    return (isinstance(d.get("limits"), list)
            or isinstance(d.get("five_hour"), dict)
            or isinstance(d.get("seven_day"), dict))


def _cached(max_age):
    try:
        if time.time() - os.path.getmtime(CACHE) <= max_age:
            d = json.load(open(CACHE))
            return d if _valid(d) else None
    except Exception:
        pass
    return None


def _fetch():
    tok = _token()
    if not tok:
        return None, "no Claude Code credentials on this machine"
    req = urllib.request.Request(
        USAGE_URL,
        headers={"Authorization": "Bearer " + tok, "anthropic-beta": OAUTH_BETA})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return None, "could not reach the usage endpoint (%s)" % type(e).__name__
    if not _valid(d):
        return None, "the usage endpoint returned a shape this build does not recognise"
    # 0600, atomic replace: the guard reads this file too, and a half-written
    # cache read by a PreToolUse hook would fail it open on garbage.
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


def _iso_to_epoch(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _label(entry):
    """A row's display name, including the model for a scoped window.

    `weekly_scoped` is how the per-model row arrives ("Weekly · Fable"). The model
    name lives at scope.model.display_name; when it is absent the row still
    renders, unlabelled, because a limit with no name is still a limit.
    """
    kind = entry.get("kind") or ""
    base = KIND_LABELS.get(kind, kind.replace("_", " ") or "limit")
    scope = entry.get("scope") or {}
    model = (scope.get("model") or {}).get("display_name")
    if kind == "weekly_scoped":
        return "Weekly · %s" % model if model else "Weekly · scoped"
    return base


def _rows(d):
    """Normalised limit rows, newest API shape first.

    Falls back to the two legacy window keys when `limits` is absent, so an
    account or build that predates the list still shows something true.
    """
    limits = d.get("limits")
    if isinstance(limits, list) and limits:
        out = []
        for e in limits:
            if not isinstance(e, dict):
                continue
            pct = e.get("percent")
            if not isinstance(pct, (int, float)):
                continue
            # The two sources inside ONE payload can disagree about the reset
            # time: an inactive window's `limits` row carries resets_at=null while
            # the legacy window key still holds the real timestamp. Observed on a
            # live account the moment the five-hour window rolled over -- the CLI
            # (which reads the window keys) printed "resets 07:30Z" while this
            # list said nothing. Prefer the row, fall back to the key, so the
            # panel never shows an em dash for a time the payload actually knows.
            resets = e.get("resets_at") or (
                (d.get(_LEGACY_KEY_FOR_KIND.get(e.get("kind") or "")) or {})
                .get("resets_at") if isinstance(
                    d.get(_LEGACY_KEY_FOR_KIND.get(e.get("kind") or "")), dict) else None)
            out.append({
                "label": _label(e),
                "kind": e.get("kind") or "",
                "group": e.get("group") or "",
                "percent": float(pct),
                "severity": e.get("severity") or "normal",
                # is_active means "this is the window currently metering you".
                # Forwarded rather than collapsed: an inactive weekly at 2% and an
                # active session at 13% are different facts about the same account.
                "active": bool(e.get("is_active")),
                "resets_at": resets,
                "resets_epoch": _iso_to_epoch(resets),
            })
        if out:
            return out
    out = []
    for key, label in (("five_hour", "Session (5h)"), ("seven_day", "Weekly · all models")):
        w = d.get(key)
        if not isinstance(w, dict):
            continue
        u = w.get("utilization")
        if not isinstance(u, (int, float)):
            continue
        out.append({
            "label": label, "kind": key, "group": "", "percent": float(u),
            "severity": "normal", "active": False,
            "resets_at": w.get("resets_at"),
            "resets_epoch": _iso_to_epoch(w.get("resets_at")),
        })
    return out


def _extra(d):
    """Pay-as-you-go credits, which is where a DAILY and a MONTHLY figure live.

    Plan rate limits have neither -- they are five-hour and weekly only. These
    fields are all None until the operator enables extra usage, and are reported
    as such rather than rendered as zeros: "no limit configured" and "a limit of
    zero" are opposite statements.
    """
    e = d.get("extra_usage")
    if not isinstance(e, dict):
        return None
    return {
        "enabled": bool(e.get("is_enabled")),
        "utilization": e.get("utilization"),
        "daily": e.get("daily"),
        "weekly": e.get("weekly"),
        "monthly_limit": e.get("monthly_limit"),
        "used_credits": e.get("used_credits"),
        "currency": e.get("currency"),
        "limit_reached": bool(e.get("spend_limit_reached")),
    }


def sanitize(d, source):
    """Allow-list projection of the raw payload. The token never appears here,
    and neither does any field this function has not been taught to emit."""
    return {
        "available": True,
        "source": source,                 # "live" | "cache" | "stale-cache"
        "fetched_at": time.time(),
        "limits": _rows(d),
        "extra_usage": _extra(d),
        # Stated so the UI can say WHY a figure is missing instead of showing 0.
        "member_dashboard_available": bool(d.get("member_dashboard_available")),
    }


def snapshot():
    """Current usage, or an explicit unavailability. Never raises."""
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
        return {"available": False, "reason": err or "no usage data available",
                "limits": [], "extra_usage": None}
    except Exception as e:
        return {"available": False,
                "reason": "usage lookup failed (%s)" % type(e).__name__,
                "limits": [], "extra_usage": None}
