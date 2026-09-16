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


# ======================================================= every provider =====
# ONE SHAPE FOR THREE UNRELATED FACTS, so a usage screen can draw four rows
# without a branch per provider.
#
# The three underlying reads stay exactly where they are and keep their own
# routes: this module's snapshot() (Claude's rate-limit windows),
# codex_models.refresh_plan_if_stale() (a ChatGPT plan's windows) and
# deepseek_usage.snapshot() (a pay-as-you-go balance). Nothing about
# /api/usage, /api/account or /api/deepseek/usage changes; this is a fourth
# view built on top of them.
#
# WHY A SHARED SHAPE IS SAFE HERE WHEN IT WAS NOT BEFORE. The reason usage.py
# and deepseek_usage.py were kept apart is that their PAYLOADS share no fields,
# so one `_valid()` would have grown branches only to keep them separate. That
# is still true of the raw payloads and they are still separate. What is shared
# is the much smaller thing a SCREEN needs -- is this thing usable, who is it,
# what plan, which meters, how much money is left -- and every field below is
# optional precisely because no provider answers all of them.
#
# `state` IS THE FIRST THING A ROW READS, and every value is a different
# instruction to the client:
#   ok            draw the row
#   not_installed there is no CLI here; offer to install it
#   signed_out    there is a CLI and no credential; offer to sign in
#   unsupported   this provider has no usage fact to report, ever. Not an error
#                 and not a gap -- a catalogued provider with no usage reader
#                 here has nothing metered to show. No provider lands on it
#                 today; it is the fallback for one added before its reader.
#   error         we asked and could not find out. `error` says what happened.
#
# NEVER 5xx AND NEVER A NUMBER WE DO NOT HAVE. Every arm below is wrapped, and
# an unavailable figure is absent rather than zero -- "no limit configured" and
# "a limit of zero" are opposite statements (see _extra above).

#: How long one whole-report answer is reused. Short, because the point of the
#: screen is a live figure, and long enough that a client polling after every
#: turn does not re-probe three CLIs each time. The per-provider caches
#: underneath (this module's CACHE_TTL, codex_models.PLAN_TTL_SECONDS,
#: deepseek_usage.CACHE_TTL) still apply on top of it.
ALL_TTL = 30.0

#: `codex login status` is a SUBPROCESS, and the whole-report path must not
#: spawn it on every poll. Cached here rather than in providers.codex_auth()
#: because that function's contract is "ask now"; the caching is this caller's
#: policy, not a change to what it means.
CODEX_AUTH_TTL = 60.0

_ALL_CACHE = {"at": 0.0, "report": None}
_CODEX_AUTH_CACHE = {"at": 0.0, "auth": None}


def _reset_all_for_tests():
    _ALL_CACHE.update({"at": 0.0, "report": None})
    _CODEX_AUTH_CACHE.update({"at": 0.0, "auth": None})


def _row(pid, name, state, **kw):
    """One provider row with every optional key present as None.

    Present-and-null rather than absent, deliberately: the client reads
    `row.plan` on every row, and a key that exists only sometimes turns every
    read into a guard. `windows` is the one exception and is always a list, so
    iterating it needs no guard either.
    """
    out = {"id": pid, "name": name, "state": state, "account": None,
           "plan": None, "windows": [], "balance": None, "error": None}
    out.update({k: v for k, v in kw.items() if k in out})
    return out


# ----------------------------------------------------------- plan labels ----
# A CLEAN LABEL, NEVER A RAW TIER STRING. `default_claude_max_20x` and `go` are
# internal identifiers; putting either on a screen tells the operator nothing
# and looks like a bug. Both maps fall through to a title-cased version of
# whatever arrived, so a plan that ships next month renders as its own name
# instead of disappearing -- the same rule usage._label follows for an unknown
# window kind.

def _claude_plan_label():
    """"Max (20x)", "Pro", … or None.

    Reuses claude_local.plan_label(), which already turns organizationType plus
    organizationRateLimitTier into "Claude Max (20x)" -- the product word is
    dropped here because the row is already labelled "Claude Code" and
    "Claude · Claude Max (20x)" reads as a stutter.

    Falls back to the credential record's own subscriptionType/rateLimitTier,
    which is the same fact from the token's point of view and is present on a
    machine whose ~/.claude.json has not been written yet.
    """
    try:
        import claude_local
        prof = claude_local.profile() or {}
        label = prof.get("plan")
        if label:
            return label[7:] if label.startswith("Claude ") else label
    except Exception:
        pass
    sub = subscription() or {}
    kind = (sub.get("subscription_type") or "").strip()
    if not kind:
        return None
    import re as _re
    m = _re.search(r"_(\d+)x$", str(sub.get("rate_limit_tier") or ""))
    base = kind.title()
    return "%s (%sx)" % (base, m.group(1)) if m else base


#: ChatGPT plan ids, from the Codex protocol's own PlanType enum (recorded in
#: codex_models' plan section). Anything not listed is title-cased rather than
#: dropped.
_CODEX_PLAN_LABELS = {
    "free": "Free", "go": "Go", "plus": "Plus", "pro": "Pro",
    "team": "Team", "business": "Business", "enterprise": "Enterprise",
    "edu": "Edu",
}

#: What an API-key credential is on. Not a plan at all -- an API key has no
#: allowance to have a percentage of -- so the label says how it bills instead,
#: which is the only true thing there is to say.
CODEX_API_KEY_PLAN = "Pay as you go"

#: DeepSeek has no subscription path: every request is billed against a key.
DEEPSEEK_PLAN = "Pay as you go"


def _codex_plan_label(plan_type):
    if not plan_type:
        return None
    return _CODEX_PLAN_LABELS.get(str(plan_type).lower(),
                                  str(plan_type).replace("_", " ").title())


# --------------------------------------------------------------- windows ----

def _claude_windows(snap):
    """usage.snapshot()'s `limits` rows in the shared shape.

    label/percent/kind are lifted verbatim -- this module already built them --
    and resets_at is already an ISO string there.
    """
    out = []
    for row in snap.get("limits") or []:
        out.append({"label": row.get("label") or "Limit",
                    "percent": row.get("percent"),
                    "resets_at": row.get("resets_at"),
                    "resets_epoch": row.get("resets_epoch"),
                    "kind": row.get("kind") or "",
                    "active": bool(row.get("active"))})
    return out


#: Window durations Codex reports, in minutes, and what to call them. DERIVED
#: FROM THE DATA, never hardcoded into the request: codex_models' plan section
#: is explicit that the measured account returns ONE 43,200-minute window and
#: no `secondary`, so naming a duration in the protocol layer would have
#: described that account wrongly. This map is presentation only, and a
#: duration it does not know is labelled from its own number.
_CODEX_WINDOW_NAMES = {
    300: ("Session (5h)", "session"),
    10080: ("Weekly", "weekly_all"),
    43200: ("Monthly (30d)", "monthly"),
}


def _codex_window_label(mins):
    known = _CODEX_WINDOW_NAMES.get(mins)
    if known:
        return known
    if not isinstance(mins, int) or mins <= 0:
        return ("Limit", "window")
    if mins % 1440 == 0:
        return ("%d-day" % (mins // 1440), "window")
    if mins % 60 == 0:
        return ("%d-hour" % (mins // 60), "window")
    return ("%d-minute" % mins, "window")


def _codex_windows(plan):
    """codex_models' plan windows in the shared shape.

    `resetsAt` arrives as Unix SECONDS there and every other provider's reset is
    an ISO string, so it is converted -- and the epoch is kept beside it, since
    a countdown wants the number and a tooltip wants the date.
    """
    out = []
    for w in (plan or {}).get("windows") or []:
        label, kind = _codex_window_label(w.get("duration_mins"))
        epoch = w.get("resets_at")
        iso = None
        if isinstance(epoch, (int, float)):
            try:
                iso = datetime.fromtimestamp(epoch, timezone.utc).isoformat()
            except Exception:
                iso = None
        out.append({"label": label, "percent": w.get("used_percent"),
                    "resets_at": iso, "resets_epoch": epoch,
                    "kind": kind, "active": True})
    return out


# --------------------------------------------------------------- balances ---

def _claude_balance(snap):
    """Extra-usage credits, when the operator has turned them on. None is the
    ordinary answer and means "no pay-as-you-go here", not "zero left"."""
    extra = snap.get("extra_usage")
    if not isinstance(extra, dict) or not extra.get("enabled"):
        return None
    used = extra.get("used_credits")
    if used is None and extra.get("monthly_limit") is None:
        return None
    return {"currency": extra.get("currency"), "amount": None,
            "used": used, "limit": extra.get("monthly_limit"),
            "note": "extra usage credits"}


def _codex_balance(plan):
    """The credits snapshot codex reports, or None. Follows _credits()' null
    rule: no credits at all is None, never a zero balance."""
    credits = (plan or {}).get("credits")
    if not isinstance(credits, dict):
        return None
    if credits.get("unlimited"):
        return {"currency": None, "amount": None, "unlimited": True,
                "note": "unlimited credits"}
    bal = credits.get("balance")
    if bal is None:
        return None
    return {"currency": None, "amount": bal, "unlimited": False,
            "note": "credits"}


def _deepseek_balance(snap):
    rows = snap.get("balances") or []
    if not rows:
        return None
    first = rows[0]
    return {"currency": first.get("currency"),
            "amount": first.get("total_balance"),
            "granted": first.get("granted_balance"),
            "topped_up": first.get("topped_up_balance"),
            "note": "account balance"}


# ---------------------------------------------------------- per provider ----

def _claude_row(name):
    import providers
    if not providers.provider_bin("claude"):
        return _row("claude", name, "not_installed",
                    error="the `claude` CLI is not on this Mac.")
    account = None
    try:
        import claude_local
        acct = claude_local.account() or {}
        account = acct.get("email") or acct.get("display_name") or None
    except Exception:
        account = None
    plan = _claude_plan_label()
    snap = snapshot()
    if not snap.get("available"):
        reason = snap.get("reason") or "usage is unavailable"
        # "no credentials" is a SIGN-IN state, not a failure -- the difference
        # decides whether the client offers a sign-in button or an error.
        signed_out = "credential" in reason.lower()
        return _row("claude", name, "signed_out" if signed_out else "error",
                    account=account, plan=plan, error=reason)
    return _row("claude", name, "ok", account=account, plan=plan,
                windows=_claude_windows(snap), balance=_claude_balance(snap))


def _codex_auth(refresh=True):
    """providers.codex_auth(), cached. See CODEX_AUTH_TTL."""
    import providers
    now = time.time()
    if _CODEX_AUTH_CACHE["auth"] is not None \
            and (now - _CODEX_AUTH_CACHE["at"]) < CODEX_AUTH_TTL:
        return _CODEX_AUTH_CACHE["auth"]
    if not refresh:
        return _CODEX_AUTH_CACHE["auth"]
    try:
        auth = providers.codex_auth()
    except Exception as e:
        auth = {"state": "unknown", "detail": "the sign-in probe failed (%s)"
                                              % type(e).__name__}
    _CODEX_AUTH_CACHE.update({"at": now, "auth": auth})
    return auth


def _codex_row(name, refresh=True):
    import providers
    if not providers.provider_bin("codex"):
        return _row("codex", name, "not_installed",
                    error="the `codex` CLI is not on this Mac.")
    auth = _codex_auth(refresh=refresh) or {"state": "unknown"}
    state = auth.get("state")
    if state == "no_binary":
        return _row("codex", name, "not_installed",
                    error=auth.get("detail"))
    if state == "logged_out":
        return _row("codex", name, "signed_out",
                    error="nothing is signed in to `codex` on this Mac.")
    if state == "api_key":
        # NO WINDOWS, AND THAT IS THE ANSWER. An API key has no plan, so it has
        # no allowance to report a percentage of -- see codex_models' plan
        # section. Reporting ok with an empty window list says "usable, nothing
        # metered", which is exactly true.
        return _row("codex", name, "ok", plan=CODEX_API_KEY_PLAN)
    if state != "chatgpt":
        return _row("codex", name, "error",
                    error=auth.get("detail")
                    or "`codex login status` answered in a shape this build "
                       "does not recognise.")
    try:
        import codex_models
        plan = (codex_models.plan_cached() if not refresh
                else codex_models.refresh_plan_if_stale("chatgpt"))
    except Exception as e:
        return _row("codex", name, "error", plan=None,
                    error="the plan read failed (%s)" % type(e).__name__)
    if not plan:
        return _row("codex", name, "ok",
                    error="codex did not report a plan allowance for this "
                          "account.")
    return _row("codex", name, "ok",
                plan=_codex_plan_label(plan.get("plan_type")),
                windows=_codex_windows(plan), balance=_codex_balance(plan))


def _deepseek_row(name):
    import providers
    try:
        auth = providers.deepseek_auth_state()
    except Exception as e:
        return _row("deepseek", name, "error",
                    error="the sign-in state could not be read (%s)"
                          % type(e).__name__)
    if not auth.get("signed_in"):
        return _row("deepseek", name, "signed_out",
                    error=auth.get("reason") or "no DeepSeek key on this Mac.")
    import deepseek_usage
    snap = deepseek_usage.snapshot()
    if not snap.get("available"):
        return _row("deepseek", name, "error", plan=DEEPSEEK_PLAN,
                    error=snap.get("reason") or "the balance is unavailable.")
    # NO WINDOWS, measured: DeepSeek publishes no five-hour or weekly window,
    # only a balance (deepseek_usage's header). An empty list here is the fact,
    # not a gap.
    return _row("deepseek", name, "ok", plan=DEEPSEEK_PLAN,
                # The masked key, never the key. `mask` is what
                # deepseek_auth.marker() stores for display.
                account=auth.get("mask"),
                balance=_deepseek_balance(snap))


def _unsupported_row(pid, name):
    return _row(pid, name, "unsupported",
                error="Sutra has no adapter for %s, so nothing about it is "
                      "metered here." % name)


def all_providers(refresh=True):
    """Every provider's usage in one shape. Never raises.

        {"providers": [ {id, name, state, account, plan,
                         windows: [{label, percent, resets_at, resets_epoch,
                                    kind, active}],
                         balance, error} ],
         "fetched_at": epoch, "source": "live" | "cache"}

    `refresh=False` answers from whatever is already cached and spawns nothing,
    for a caller that must not pay for a probe.
    """
    now = time.time()
    if _ALL_CACHE["report"] is not None and (now - _ALL_CACHE["at"]) < ALL_TTL:
        out = dict(_ALL_CACHE["report"])
        out["source"] = "cache"
        return out
    if not refresh and _ALL_CACHE["report"] is not None:
        out = dict(_ALL_CACHE["report"])
        out["source"] = "cache"
        return out

    import providers
    rows = []
    for spec in providers._CATALOG:
        pid, name = spec["id"], spec["name"]
        try:
            if pid == "claude":
                rows.append(_claude_row(name))
            elif pid == "codex":
                rows.append(_codex_row(name, refresh=refresh))
            elif pid == "deepseek":
                rows.append(_deepseek_row(name))
            else:
                rows.append(_unsupported_row(pid, name))
        except Exception as e:
            # One provider's probe must never take the screen down. The row
            # says which one failed and how, and the other three still render.
            rows.append(_row(pid, name, "error",
                             error="the usage read failed (%s)"
                                   % type(e).__name__))
    report = {"providers": rows, "fetched_at": now, "source": "live"}
    _ALL_CACHE.update({"at": now, "report": report})
    return dict(report)
