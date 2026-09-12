"""Which models the Codex CLI will actually run, asked of Codex.

THE MISTAKE THIS CORRECTS
-------------------------
providers._CODEX_MODELS declared exactly one entry -- "CLI default" -- on the
finding that codex-cli publishes no model roster. That finding was tested four
ways and every one of them agreed:

    codex models …              no such subcommand
    codex exec --help           `-m, --model <MODEL>`, no enumeration
    codex doctor                reports `model  <default> · openai`
    app-server JSON schema      39 files, 1.79 MB, ZERO concrete model ids

All four are still true, and all four were the wrong question. The roster is not
a compiled-in list and not a subcommand: it is an RPC. The app-server protocol
declares **model/list**, and its params type says what it is for in OpenAI's own
words -- `includeHidden`: "When true, include models that are hidden from the
default picker list." Codex has a notion of "the default picker list" and will
hand it over on request.

Measured against 0.153.2 on 2026-09-08, driving `codex app-server` over stdio:

    initialize -> model/list {}                     -> 3 models
    initialize -> model/list {includeHidden:true}   -> 5 models

WHY THIS IS THE ONLY ACCEPTABLE SOURCE
--------------------------------------
Three sources exist and they DISAGREE, which is the whole argument for using
the live one:

    model/list (this module)     3 visible   account-scoped, server-fresh
    ~/.codex/models_cache.json   the same 5  the CLI's own cache of the above
    the 210 MB Rust binary       11          a compiled-in FALLBACK superset

The binary's manifest carries `gpt-6-astra` and `gpt-5.6-sol`. Both are real,
both are documented, both are live in the OpenAI API -- and NEITHER is
selectable on the account this was measured on. OpenAI's own docs explain it:
Codex model access is plan-scoped (Free/Go get Terra; Plus/Pro/Business/
Enterprise get Sol/Terra/Luna; Astra reached Pro/Enterprise/Business Premium
first), and openai/codex#42853 is people reporting Astra missing from the
picker on accounts that should have it. A picker built from the binary would
offer six models that do not work, and each one fails SILENTLY: measured, an
unknown `-m` is accepted with a "Model metadata not found" warning and then
runs on degraded fallback metadata.

So: no hardcoded ids, no binary scraping, and models_cache.json only as a
last-resort read (it is an internal file, not an interface).

NOTHING HERE IS ON THE RENDER PATH, AND THAT IS ENFORCED BY SHAPE
-----------------------------------------------------------------
providers.models_for() is reached by load_settings(), and every fs/tree, fs/read
and settings GET goes through that. A subprocess there would tax requests that
never asked about Codex -- the same rule that keeps codex_auth() off
_describe().

So this module is split in two, and the split is the guard:

    cached()            pure. Returns what was last discovered. NEVER spawns.
                        This is what providers.models_for() calls.
    refresh_if_stale()  spawns. Called ONLY from the route that already spawns
                        for Codex (GET /providers/codex/auth, which is paying
                        for `codex login status` anyway).

There is deliberately no function that does both.

WHEN IT REFRESHES
-----------------
Keyed on the AUTH STATE plus a TTL, because those are the two things that can
change the answer:

  - the state changed (logged_out -> chatgpt, chatgpt -> api_key) -> refresh NOW.
    This is what makes the picker correct for BOTH credentials without assuming
    they offer the same models. A ChatGPT plan and an API key are scoped by
    different things, and this module never guesses which; it re-asks.
  - otherwise, at most once per TTL.

That combination is what keeps the 2-second sign-in poll from spawning an
app-server on every tick while still being right the instant a sign-in lands.

Reads: the `codex` binary (through providers.provider_bin) and, as a last
       resort, $CODEX_HOME/models_cache.json.
Writes: nothing. No settings, no credential, no file, ever.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import providers

#: How long a discovered list is trusted before it is re-asked. Short enough
#: that a plan change or a rollout (Astra was rolling out account-by-account
#: while this was written) is picked up within one settings visit; long enough
#: that opening the screen repeatedly costs one spawn, not one per open.
TTL_SECONDS = 300

#: The measured cost of one call is ~1.0-1.3s: app-server boots, answers from
#: its cached catalog, and exits. This cap is generous against a cold start and
#: a slow disk, and is deliberately well under the 10s that route already
#: budgets for `codex login status`.
TIMEOUT_SECONDS = 8

#: The RPC. `initialize` first -- measured: model/list before it returns
#: nothing. Both are one line of JSON on stdin, answered on stdout.
_METHOD = "model/list"

#: What Sutra tells Codex it is. Codex echoes this into its own user-agent, so
#: it is a real identifier rather than a placeholder.
_CLIENT = {"name": "sutra-ui", "title": "Sutra", "version": "1"}

#: Guards the cache against two requests arriving together -- the sign-in poll
#: and a settings open can overlap. The loser waits and then reads the cache.
_LOCK = threading.Lock()

#: (models, auth_state, fetched_at). `models` is () for "asked and got nothing
#: usable", which is DIFFERENT from None for "never asked" -- the first must
#: not be retried on every call and the second must not be cached.
_CACHE = {"models": None, "state": None, "at": 0.0}


def _reset_for_tests():
    with _LOCK:
        _CACHE.update({"models": None, "state": None, "at": 0.0})


# ------------------------------------------------------------------ mapping --

def _entry(raw, note_from_default=False):
    """One model/list item as a Sutra catalogue entry, or None.

    Sutra's shape is {id, name, note} (providers._CLAUDE_MODELS). Mapping:

        id / model  -> id     the EXACT string that reaches `-m`
        displayName -> name   "GPT-5.6-Terra"
        description -> note   "Balanced agentic coding model for everyday work."

    HIDDEN ENTRIES NEVER GET HERE. `gpt-reserve` and `codex-auto-review` are
    internal -- an approval-review model and a reserve pool -- and Codex marks
    them hidden precisely so a picker does not offer them.

    `supportedReasoningEfforts` IS consumed now (see `efforts` below) -- it is
    what makes a Reasoning-effort control possible without guessing, because
    the value set is per model. `defaultReasoningEffort` is still not read: the
    picker's "default" option means "emit no override and let codex decide",
    which needs no knowledge of what codex would have chosen.
    """
    if not isinstance(raw, dict):
        return None
    if raw.get("hidden") is True:
        return None
    mid = raw.get("id") or raw.get("model")
    if not isinstance(mid, str) or not mid.strip():
        return None
    mid = mid.strip()
    name = raw.get("displayName")
    if not isinstance(name, str) or not name.strip():
        name = mid                      # the id is a worse label and a true one
    note = raw.get("description")
    if not isinstance(note, str) or not note.strip():
        note = "offered by codex for this account"
    if note_from_default and raw.get("isDefault") is True:
        note = "%s · what `codex` uses by default" % note
    return {"id": mid, "name": name.strip(), "note": note.strip(),
            # PER MODEL, and that is the whole reason this is carried rather
            # than declared as a constant somewhere: the sets genuinely differ
            # between models on one account (measured -- terra offers `ultra`,
            # luna does not, 5.5 stops at `xhigh`). A fixed list would offer
            # every model the union and silently degrade on the ones that do
            # not have it, because `-c model_reasoning_effort` accepts an
            # unknown value without complaint (measured: "__bogus__" sailed
            # through, which is why this feature waited for model/list).
            "efforts": _efforts(raw),
            # Private (underscore keys are stripped before the client sees the
            # entry -- providers._codex_discovered). budget.window_for reads
            # it: the effective window is PER MODEL on one account as of
            # 2026-09-12 (gpt-5.5 258,400; gpt-5.3-codex-spark 121,600).
            "_window": _effective_window(raw)}


def _efforts(raw):
    """`supportedReasoningEfforts` as a tuple of plain strings.

    The measured shape is [{"reasoningEffort": "low", "description": …}, …];
    a bare list of strings is accepted too, because the cheaper shape is the
    one a future build is more likely to move to and mis-reading it would
    silently empty the picker rather than fail.
    """
    out = []
    for item in (raw.get("supportedReasoningEfforts") or ()):
        v = item.get("reasoningEffort") if isinstance(item, dict) else item
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return tuple(out)


def _effective_window(raw):
    """The effective context window codex declares for one model, or None.

    context_window x effective_context_window_percent / 100 -- the two fields
    codex's own models_cache.json carries (measured 2026-09-09: 272000 x 95
    -> 258,400 for every visible model; 2026-09-12: gpt-5.3-codex-spark
    appeared at 128000 x 95 -> 121,600, and one default stopped being honest).
    The camelCase spellings are the RPC's convention for the same fields per
    the cache-file note below ("same field names as the RPC in snake_case")
    and are NOT independently measured: a model/list answer without them
    simply carries no window, and budget.window_for keeps the provider
    default it always had.
    """
    cw = raw.get("contextWindow", raw.get("context_window"))
    pct = raw.get("effectiveContextWindowPercent",
                  raw.get("effective_context_window_percent"))
    if isinstance(cw, bool) or isinstance(pct, bool):
        return None
    if isinstance(cw, int) and isinstance(pct, int) \
            and cw > 0 and 0 < pct <= 100:
        return int(cw * pct / 100)
    return None


def default_id(models=None):
    """The id codex would choose on its own, or None.

    Carried so the picker's FIRST option can name what "CLI default" actually
    resolves to instead of leaving it abstract. It is metadata about the
    default, never a selection: choosing "CLI default" still emits no -m, which
    is the behaviour that must not change.
    """
    for m in (models if models is not None else (cached() or ())):
        if m.get("_default"):
            return m["id"]
    return None


def efforts_for(model_id=None):
    """The reasoning efforts `model_id` supports, or ().

    A FALSY model_id means the picker is on "CLI default", and that resolves to
    whatever codex marked isDefault -- so the efforts offered there are that
    model's. Server and client resolve it the same way, which is what keeps the
    control from offering a value the validator would then drop.

    () when nothing was discovered, when the id is unknown, or when the model
    published no efforts. Every one of those ends the same way for the caller:
    only "default" is offered, and no override is emitted.

    PURE. Reads the cache; never spawns.
    """
    models = cached() or ()
    if not model_id:
        model_id = default_id(models)
    if not model_id:
        return ()
    for m in models:
        if m.get("id") == model_id:
            return tuple(m.get("efforts") or ())
    return ()


def _map(data):
    """model/list's `data` array -> a tuple of Sutra entries. () on junk."""
    if not isinstance(data, list):
        return ()
    out, seen = [], set()
    for raw in data:
        e = _entry(raw)
        if not e or e["id"] in seen:
            continue
        seen.add(e["id"])
        # Kept on the entry rather than returned separately so the ordering
        # and the default cannot drift apart. Stripped before it reaches the
        # client by providers.models_for -- see the note there.
        e["_default"] = bool(isinstance(raw, dict) and raw.get("isDefault") is True)
        out.append(e)
    return tuple(out)


# -------------------------------------------------------------------- the RPC --

def _rpc(binary, method=None, params=None):
    """Drive initialize + one request and return its `result`, or None.

    ONE TRANSPORT, TWO READS. `method`/`params` were added when the account
    rate-limit read landed (2026-09-09): both it and model/list are
    `initialize` + one request over the same `codex app-server` stdio pipe, so
    they share this function rather than getting a second, near-identical
    mechanism to keep in step. `method=None` keeps the model/list call site
    unchanged.

    Returns the whole `result` object; each caller's own mapper takes the piece
    it wants (`data` for model/list, the rate-limit fields for the account
    read).

    None means "could not ask" -- no binary, spawn refused, timeout, non-JSON,
    a JSON-RPC error, or a shape this build does not recognise. Every one of
    those is the same answer as far as the caller is concerned: fall back.

    NO MODEL TURN IS CONSUMED. This starts the app-server, which answers from
    the catalog it already holds, and exits. Nothing is sent to a model.

    The child is killed in a finally, always. An app-server left running would
    hold a daemon socket and outlive the request that started it.
    """
    p = None
    try:
        p = subprocess.Popen(
            [binary, "app-server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            # Unbuffered-ish: the answers are line-delimited JSON and a block
            # buffer would make a fast reply look like a timeout.
            bufsize=1,
        )
        req = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"clientInfo": _CLIENT}}) + "\n"
               + json.dumps({"jsonrpc": "2.0", "id": 2,
                             "method": method or _METHOD,
                             # includeHidden FALSE, EXPLICITLY, for model/list.
                             # The default is the picker list already, but
                             # naming it is what stops a later protocol default
                             # from quietly putting internal models in front of
                             # an operator. The account read passes {}.
                             "params": (params if params is not None
                                        else {"includeHidden": False})}) + "\n")
        p.stdin.write(req)
        p.stdin.flush()

        # THE READ HAPPENS ON ITS OWN THREAD, and that is not decoration.
        #
        # The first version of this loop was `while time.time() < deadline:
        # p.stdout.readline()`, which checks the clock BETWEEN reads and never
        # during one. `readline()` on a pipe blocks with no timeout, so a child
        # that starts and then says nothing -- holding stdout open while it
        # waits on something of its own -- parks the caller FOREVER and
        # TIMEOUT_SECONDS is a comment rather than a bound. That is not
        # hypothetical: it hung this module's own test suite, on a stub that
        # read stdin and never wrote a line.
        #
        # It matters far more in production than in a test. This runs inside
        # GET /providers/codex/auth, so an app-server that never answers would
        # hang the provider screen's request with nothing to cancel it.
        #
        # join(timeout) is the bound. Killing the child in the `finally` then
        # unblocks the reader, and the thread is a daemon so a wedged one can
        # never hold the process open.
        answer = {}

        def _read():
            try:
                for line in p.stdout:
                    try:
                        msg = json.loads(line)
                    except (ValueError, TypeError):
                        continue          # notifications, banners, noise
                    if not isinstance(msg, dict) or msg.get("id") != 2:
                        continue          # not our answer yet
                    answer["msg"] = msg
                    return
            except (OSError, ValueError):
                pass

        reader = threading.Thread(target=_read, name="codex-model-list",
                                  daemon=True)
        reader.start()
        reader.join(TIMEOUT_SECONDS)

        msg = answer.get("msg")
        if not isinstance(msg, dict) or "error" in msg:
            return None                   # timed out, closed on us, or refused
        result = msg.get("result")
        if not isinstance(result, dict):
            return None
        return result
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    finally:
        if p is not None:
            try:
                p.kill()
            except OSError:
                pass
            try:
                p.wait(timeout=2)
            except Exception:                    # noqa: BLE001
                pass


def _from_cache_file():
    """$CODEX_HOME/models_cache.json's models, or (). LAST RESORT ONLY.

    This is the CLI's own cache of the same server answer, so it is the right
    data -- but it is an internal file with no compatibility promise, which is
    why model/list is asked first and this is only read when the RPC could not
    be made at all. Same field names as the RPC in snake_case, so the visible
    set is derived the same way rather than by a second rule.
    """
    home = Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex"))
    try:
        blob = json.loads((home / "models_cache.json").read_text(
            encoding="utf-8", errors="replace")[:2 ** 20])
    except (OSError, ValueError, TypeError):
        return ()
    if not isinstance(blob, dict):
        return ()
    models = blob.get("models")
    if not isinstance(models, list):
        return ()
    out = []
    for raw in models:
        if not isinstance(raw, dict):
            continue
        # The file spells the gate as `visibility`, not `hidden`.
        if raw.get("visibility") != "list":
            continue
        out.append({"id": raw.get("slug"), "model": raw.get("slug"),
                    "displayName": raw.get("display_name"),
                    "description": raw.get("description"),
                    # the window pair, under the file's own names (_window)
                    "context_window": raw.get("context_window"),
                    "effective_context_window_percent":
                        raw.get("effective_context_window_percent"),
                    "hidden": False,
                    "isDefault": False})
    return _map(out)


# ------------------------------------------------------------------ the API --

def cached():
    """What was last discovered: a tuple, or None if nothing ever was.

    PURE. NEVER SPAWNS. This is the function providers.models_for() is allowed
    to call, and the reason the render path stays subprocess-free.
    """
    with _LOCK:
        return _CACHE["models"]


def window_for(model_id):
    """The effective context window codex declares for `model_id`, or None.

    PURE, NEVER SPAWNS: the discovered roster first, then codex's own cache
    file as the last resort -- refresh_if_stale's order minus the RPC, and a
    capped 1 MB read when discovery has not run in this process. None for "",
    for an id the roster does not list, and for a roster that published no
    window; budget.window_for turns None into the provider default, which
    over-sizes a smaller model only on a machine where neither source exists.
    """
    if not model_id:
        return None
    for m in (cached() or _from_cache_file()):
        if m.get("id") == model_id:
            return m.get("_window") or None
    return None


def refresh_if_stale(auth_state=None, force=False):
    """Re-ask Codex when the answer could have changed. Returns the tuple.

    SPAWNS A SUBPROCESS. Call only from a path that already accepts that cost
    -- today exactly one: GET /providers/codex/auth, which is paying for
    `codex login status` on the same request.

    THE STATE IS PART OF THE CACHE KEY, and it is what makes this correct for
    both credentials. A ChatGPT plan and an API key are scoped by different
    things and may offer different models; rather than assuming anything about
    either, a change in `auth_state` invalidates the list immediately. The TTL
    covers the slower case -- a plan upgrade, or a staged rollout reaching this
    account -- without polling for it.
    """
    with _LOCK:
        fresh = (_CACHE["models"] is not None
                 and _CACHE["state"] == auth_state
                 and (time.time() - _CACHE["at"]) < TTL_SECONDS)
        if fresh and not force:
            return _CACHE["models"]

    # OUTSIDE THE LOCK. The spawn is up to TIMEOUT_SECONDS and holding the lock
    # across it would make cached() -- a render-path call -- block on it.
    binary = providers.provider_bin("codex")
    models = ()
    if binary:
        result = _rpc(binary)
        models = (_map(result.get("data")) if isinstance(result, dict)
                  else _from_cache_file())

    with _LOCK:
        _CACHE.update({"models": models, "state": auth_state, "at": time.time()})
        return models


# ============================================ the account's plan usage ======
# WHAT THIS IS. `account/rateLimits/read`, the second read over the transport
# above -- Codex's own supported method for "how much of this account's
# allowance is spent". Measured live on 2026-09-09, it answered in under a
# second and CONSUMED NO MODEL TURN.
#
# CHATGPT ONLY, AND THAT IS NOT A POLICY CHOICE. A rate-limit window is a
# property of a ChatGPT PLAN. The protocol's own PlanType enum is seventeen
# ChatGPT/workspace values (free, go, plus, pro, team, business, enterprise,
# edu…) with no "api key" among them, and RateLimitReachedType is entirely
# workspace-scoped. An API key has no plan to have an allowance of, so this is
# never asked in that mode -- see refresh_plan_if_stale.
#
# NOTHING ABOUT DOLLARS. Spend for an API key lives behind OpenAI's Admin API
# (/v1/organization/costs), which needs a SEPARATE, more privileged credential
# than the one Sutra holds. Deliberately not pursued: a second org-wide
# credential to render a number is a worse trade than the number is worth.
#
# >>> WINDOW DURATIONS ARE DATA, NEVER CONSTANTS <<<
# The measured account is planType "go" and returns ONE window of
# windowDurationMins=43200 (30 days) with NO `secondary` at all. The
# five-hour/weekly pair people describe is what other plans return. So this
# module maps whatever windows arrive and never names a duration: the label is
# derived client-side from windowDurationMins. Hardcoding "5-hour" here would
# have described this very account wrongly.

#: The method. Named like _METHOD so the two reads read alike.
_PLAN_METHOD = "account/rateLimits/read"

#: The auth state a plan read is meaningful in. One value, and it is the whole
#: gate: anything else clears the cache instead of asking.
_PLAN_STATE = "chatgpt"

#: Its own cache, separate from the model cache: the two reads answer different
#: questions, go stale for different reasons, and a plan refresh must not
#: invalidate a model list. Same shape and same discipline.
_PLAN_CACHE = {"plan": None, "state": None, "at": 0.0}

#: Shorter than the model TTL. A model roster changes when a plan changes; a
#: percentage changes as the operator works, and this figure rides on
#: loadUsage(), which the client already calls after every completed turn.
PLAN_TTL_SECONDS = 60


def _reset_plan_for_tests():
    with _LOCK:
        _PLAN_CACHE.update({"plan": None, "state": None, "at": 0.0})


def _window(raw, key):
    """One RateLimitWindow as {key, used_percent, duration_mins, resets_at}.

    None when there is no usable percentage. `usedPercent` is the only required
    field: a window with no duration and no reset is still a real "you have
    spent N% of something" and the client can label it generically, whereas a
    window with no percentage is nothing to draw.

    resets_at is Unix SECONDS, passed through untouched -- the client turns it
    into a countdown, which is where the clock is.
    """
    if not isinstance(raw, dict):
        return None
    pct = raw.get("usedPercent")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    def _int(v):
        return v if (isinstance(v, int) and not isinstance(v, bool)) else None
    return {"key": key,
            "used_percent": float(pct),
            "duration_mins": _int(raw.get("windowDurationMins")),
            "resets_at": _int(raw.get("resetsAt"))}


def _credits(raw):
    """The credits snapshot, or None when OpenAI reports no credits at all.

    THE null RULE. The measured account answers {hasCredits: false, unlimited:
    false, balance: null}. That is "there are no credits here", NOT "your
    balance is zero" -- and rendering it as 0 would read as an exhausted
    balance, which is a different and alarming claim. So a snapshot is returned
    ONLY when `unlimited` is true or `balance` is actually present; otherwise
    None, and the client draws nothing.
    """
    if not isinstance(raw, dict):
        return None
    unlimited = raw.get("unlimited") is True
    balance = raw.get("balance")
    has_balance = isinstance(balance, (str, int, float)) and not isinstance(balance, bool)
    if not unlimited and not has_balance:
        return None
    return {"unlimited": unlimited,
            "balance": str(balance) if has_balance else None,
            "has_credits": raw.get("hasCredits") is True}


def _map_plan(result):
    """`account/rateLimits/read`'s result as the shape the panel renders.

        {"windows": [ {key, used_percent, duration_mins, resets_at}, … ],
         "plan_type", "reached", "limit_id", "credits", "reset_credits"}

    EVERY WINDOW THE ANSWER CARRIES, from all three places the protocol puts
    them, deduplicated on (duration, reset, percent):

        rateLimits.primary / .secondary     the historical single-bucket view
        rateLimitsByLimitId[<id>].primary   the multi-bucket view, keyed by
                                 /.secondary metered limit_id (e.g. "codex")

    `secondary` is genuinely optional -- the measured account has none -- so
    its absence is a normal answer and not a degraded one.

    None when the answer is unusable. () windows with a plan_type is still a
    real answer: the account has a plan and no metered window right now.
    """
    if not isinstance(result, dict):
        return None
    buckets = []
    base = result.get("rateLimits")
    if isinstance(base, dict):
        buckets.append((base.get("limitId"), base))
    by_id = result.get("rateLimitsByLimitId")
    if isinstance(by_id, dict):
        for lid, snap in by_id.items():
            if isinstance(snap, dict):
                buckets.append((lid, snap))

    windows, seen, plan_type, reached, limit_id, credits = [], set(), None, None, None, None
    for lid, snap in buckets:
        plan_type = plan_type or _str(snap.get("planType"))
        reached = reached or _str(snap.get("rateLimitReachedType"))
        limit_id = limit_id or _str(lid) or _str(snap.get("limitId"))
        credits = credits or _credits(snap.get("credits"))
        for half in ("primary", "secondary"):
            w = _window(snap.get(half), half)
            if not w:
                continue
            # Dedupe: the single-bucket view MIRRORS one of the keyed buckets
            # (protocol's own words: "Backward-compatible single-bucket view"),
            # so the same window arrives twice on a one-limit account and would
            # otherwise be drawn twice.
            sig = (w["duration_mins"], w["resets_at"], w["used_percent"])
            if sig in seen:
                continue
            seen.add(sig)
            windows.append(w)

    if not buckets:
        return None
    resets = result.get("rateLimitResetCredits")
    n = resets.get("availableCount") if isinstance(resets, dict) else None
    return {"windows": windows,
            "plan_type": plan_type,
            "reached": reached,
            "limit_id": limit_id,
            "credits": credits,
            "reset_credits": n if isinstance(n, int) and not isinstance(n, bool) else None}


def _str(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def plan_cached():
    """The last plan read, or None. PURE -- never spawns.

    None covers both "never asked" and "not applicable to this credential",
    and the client renders nothing for either. There is deliberately no way to
    tell them apart here: both mean "do not draw a plan".
    """
    with _LOCK:
        return _PLAN_CACHE["plan"]


def refresh_plan_if_stale(auth_state=None, force=False):
    """Re-read the plan when it could have changed. Returns the plan or None.

    SPAWNS. Same rule as refresh_if_stale: only from a route that already
    accepts that cost.

    NOT CHATGPT -> CLEARED, NOT SKIPPED. Signing out or switching to an API key
    must make the indicator GO AWAY, not go stale: a percentage left on screen
    after a credential change describes an allowance that is no longer being
    metered. So the cache is emptied and nothing is asked -- which is also why
    API-key mode never sends this request at all.
    """
    if auth_state != _PLAN_STATE:
        with _LOCK:
            _PLAN_CACHE.update({"plan": None, "state": auth_state, "at": time.time()})
        return None

    with _LOCK:
        fresh = (_PLAN_CACHE["plan"] is not None
                 and _PLAN_CACHE["state"] == auth_state
                 and (time.time() - _PLAN_CACHE["at"]) < PLAN_TTL_SECONDS)
        if fresh and not force:
            return _PLAN_CACHE["plan"]

    binary = providers.provider_bin("codex")
    plan = _map_plan(_rpc(binary, _PLAN_METHOD, {})) if binary else None

    with _LOCK:
        _PLAN_CACHE.update({"plan": plan, "state": auth_state, "at": time.time()})
        return plan
