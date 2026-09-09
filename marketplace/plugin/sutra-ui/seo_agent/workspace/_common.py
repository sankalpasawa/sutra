"""_common.py — one HTTP call, one retry rule, one place a Supabase error becomes English.

Everything in this package that touches the network comes through request(). That is the
same discipline as tools/dfs.py: one door, so a timeout, a retry rule or a header change is
a one-line fix instead of a hunt through six call sites.

THE RETRY RULE, AND WHY IT IS THIS NARROW. We retry a dropped connection and a 5xx, because
both mean "Supabase did not get to an answer" and the same request will work a second later.
We never retry a 4xx. A 4xx means we sent something wrong, and sending it again wrongly three
times only makes the person wait three times as long for the same refusal. It is also the
difference between a harmless retry and a duplicate insert.

THE ERROR RULE. Supabase answers a refusal with a JSON body carrying `message` and often
`hint`, and those two sentences are usually the whole diagnosis. A caller that only sees
"401" has to guess. So explain() reads the body and hands back a sentence a person can act
on, and the raw status is kept on the exception for the log.

Measured against the owner's real project, 2026-09-10, so the strings below are the ones
Supabase actually sends and not what the docs imply:

  * a wrong key            -> 401 {"message":"Invalid API key","hint":"Double check your API key."}
  * a publishable key on
    an admin-only endpoint -> 401 {"message":"Secret API key required", "hint":"Only secret ..."}
  * a table that is not
    created yet            -> 404 {"code":"PGRST205","message":"Could not find the table
                                   'public.workspace' in the schema cache"}
  * a bad management token -> 401 {"message":"Unauthorized"}
  * a bucket that is not
    created yet            -> HTTP 400, body {"statusCode":"404","error":"Bucket not found",
                                   "code":"NoSuchBucket"}

THE STORAGE QUIRK, AND WHY status() EXISTS. That last one is not a typo. Supabase Storage
answers a missing bucket with HTTP 400 and puts the REAL code, 404, in the body as a string.
Found 2026-09-10 while writing verify(): bucket_exists() asked for allow_404 and never got a
404, so a perfectly ordinary "not created yet" arrived as a hard failure and would have made
verify() crash on exactly the workspace it exists to diagnose. So the status we act on is the
body's statusCode when it has one, and the HTTP code otherwise.

NOTHING IN HERE EVER PUTS A KEY IN A MESSAGE. The headers are built here and never echoed,
because an error string ends up in a log file, a screenshot and a bug report.
"""
import json
import time

import httpx

# The workspace endpoints are small reads and writes, not the minute-long jobs DataForSEO
# runs, so the timeout is short enough that a person notices a hang. The upload timeout is
# separate because the knowledge pack is ~100 MB.
TIMEOUT = 30.0
UPLOAD_TIMEOUT = 600.0
# A free project sleeps after 7 days idle and the first call after that can take about a
# minute to wake it (WORKSPACE-PLAN section 9). That is a slow answer, not an error, so the
# wake-up call gets its own longer timeout rather than a retry.
WAKE_TIMEOUT = 120.0

RETRIES = 2                  # extra attempts after the first, so 3 tries at worst
BACKOFF = (0.5, 1.5)         # seconds before attempt 2 and attempt 3


class WorkspaceError(Exception):
    """A failure a person can read. str(e) is safe to show in the UI as-is.

    `status` is the HTTP code (0 when the request never got an answer) and `body` is the
    parsed error body, both for the log. Never put a credential on either.
    """

    def __init__(self, message, status=0, body=None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


class TableMissing(WorkspaceError):
    """The table is not there yet — PGRST205 from PostgREST, 42P01 from Postgres.

    This is its own class because it is the one 4xx that is not a bug: it is exactly what an
    un-created workspace looks like, and verify() must be able to tell it apart from a real
    refusal. If verify treated it as a generic error it could not report WHICH table is
    missing, and "something went wrong" is the kind of message this plan forbids.
    """


class NotConfigured(WorkspaceError):
    """No workspace is connected yet."""


def _body(resp):
    """The error body as a dict. Supabase always sends JSON here, but a proxy or a gateway
    in front of it may send HTML, so a body that will not parse becomes a text field rather
    than an exception raised while handling an exception."""
    try:
        parsed = resp.json()
    except (ValueError, json.JSONDecodeError):
        return {"text": (resp.text or "")[:400]}
    if isinstance(parsed, dict):
        return parsed
    return {"text": str(parsed)[:400]}


def status(resp, body=None):
    """The status to act on: Supabase Storage's body statusCode when present, else the HTTP
    code. See THE STORAGE QUIRK at the top -- Storage sends 400 on the wire and "404" in the
    body, and every decision below is about what actually happened, not what the wire said."""
    body = _body(resp) if body is None else body
    claimed = body.get("statusCode")
    if isinstance(claimed, int):
        return claimed
    if isinstance(claimed, str) and claimed.strip().isdigit():
        return int(claimed.strip())
    return resp.status_code


def _sentence(body):
    """message + hint, joined, from whichever of the four shapes this endpoint uses.

    PostgREST says `message`/`hint`. GoTrue says `msg` or `error_description`. The
    management API says `message`. Storage says `message` or `error`. One reader for all
    four beats four call sites each guessing."""
    msg = ""
    for field in ("message", "msg", "error_description", "error", "text"):
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            msg = value.strip()
            break
    hint = body.get("hint")
    details = body.get("details")
    parts = [p for p in (msg, hint if isinstance(hint, str) else None,
                         details if isinstance(details, str) else None) if p]
    return " ".join(parts)


# What a 401 should tell the person to go and fix. There are two credentials in this system
# and they are obtained from different pages, so one message cannot serve both. Found
# 2026-09-10 while proving route 1 against the real management API: a rejected personal
# access token was answered with "copy the key that starts with sb_publishable_", which would
# have sent the person to re-paste a key that was never the problem.
KEY_ADVICE = ("Open your project in Supabase, go to Project Settings then API Keys, and copy "
              "the key that starts with sb_publishable_.")
TOKEN_ADVICE = ("Supabase did not accept that access token. Generate a fresh one at "
                "supabase.com/dashboard/account/tokens, and check it is for the account that "
                "owns this project.")


def explain(resp, what, advice_401=KEY_ADVICE):
    """Turn a refused response into a WorkspaceError whose text says what to do next.

    `what` is the thing we were doing, in plain words ("read the ideas table"), so the
    sentence reads as one thought rather than a status code with a noun bolted on.
    `advice_401` is which credential to blame; see KEY_ADVICE above for why it is a parameter.
    """
    body = _body(resp)
    code = status(resp, body)
    said = _sentence(body)
    tail = (" Supabase said: " + said) if said else ""

    if code == 401:
        # The two 401s mean opposite things and the fix is different for each, so they must
        # not collapse into one message. "Secret API key required" means the endpoint is
        # admin-only and we should not have called it with the publishable key at all --
        # that is our bug, not the person's, and saying "check your key" would send them
        # off to re-paste a key that was perfectly correct.
        if "secret" in said.lower():
            raise WorkspaceError(
                "Sutra tried to %s using an endpoint that only accepts a secret admin key. "
                "Sutra never asks for one, so this is a bug in Sutra, not a problem with "
                "your project.%s" % (what, tail), code, body)
        if advice_401 is TOKEN_ADVICE:
            raise WorkspaceError(
                "Sutra could not %s. %s%s" % (what, advice_401, tail), code, body)
        raise WorkspaceError(
            "That key is not for this project. Sutra could not %s because Supabase rejected "
            "the key. %s%s" % (what, advice_401, tail), code, body)

    if code == 403:
        raise WorkspaceError(
            "Supabase allowed the key but refused the row. Sutra could not %s. This is the "
            "workspace's own security rule saying the row belongs to a different workspace."
            "%s" % (what, tail), code, body)

    if code == 404:
        target = body.get("code") or ""
        # Storage, live 2026-09-10: a missing bucket came back as "Supabase has no such
        # address, check the project URL", which sends a person to check the one thing that
        # was right. The bucket is made by schema.sql and by nothing else, so say that.
        if target == "NoSuchBucket" or "bucket not found" in said.lower():
            raise TableMissing(
                "This workspace has no file cupboard yet, so Sutra could not %s. The setup "
                "script creates it — run it again from the Connections tab, or create a "
                "private bucket named 'knowledge' under Storage.%s" % (what, tail), code, body)
        if target in ("PGRST205", "PGRST202", "42P01") or "schema cache" in said:
            raise TableMissing(
                "That part of the workspace has not been created yet, so Sutra could not %s."
                "%s" % (what, tail), code, body)
        raise WorkspaceError(
            "Sutra could not %s because Supabase has no such address. Check the project URL "
            "in the Connections tab.%s" % (what, tail), code, body)

    if code == 409:
        raise WorkspaceError(
            "Sutra could not %s because a row with that id is already there.%s"
            % (what, tail), code, body)

    if code == 413:
        raise WorkspaceError(
            "Sutra could not %s because the file is larger than this project accepts.%s"
            % (what, tail), code, body)

    if code == 429:
        raise WorkspaceError(
            "Supabase is asking Sutra to slow down, so it could not %s. Wait a minute and "
            "try again.%s" % (what, tail), code, body)

    if code >= 500:
        raise WorkspaceError(
            "Supabase itself had a problem, so Sutra could not %s. It already tried again "
            "%d times. This is on Supabase's side; wait a few minutes.%s"
            % (what, RETRIES, tail), code, body)

    raise WorkspaceError(
        "Sutra could not %s (Supabase answered %d).%s" % (what, code, tail), code, body)


def request(method, url, what, headers=None, params=None, json_body=None, content=None,
            timeout=TIMEOUT, allow_404=False, advice_401=KEY_ADVICE):
    """The one call. Returns the httpx response on 2xx, raises WorkspaceError otherwise.

    allow_404 hands a 404 back to the caller instead of raising, which verify() wants: to it,
    a missing table is a finding to report, not a crash.
    """
    last_transport = None
    for attempt in range(RETRIES + 1):
        try:
            resp = httpx.request(method, url, headers=headers, params=params, json=json_body,
                                 content=content, timeout=timeout)
        except httpx.TimeoutException as e:
            last_transport = ("timed out after %ds" % int(timeout), e)
            resp = None
        except httpx.TransportError as e:
            # Connect errors, DNS failures, a dropped wifi. The owner's connection drops
            # several times a day (recorded in tests/test_credit_guard.py), which is the
            # whole reason a retry exists here at all.
            last_transport = ("could not reach Supabase", e)
            resp = None

        if resp is not None:
            if resp.status_code < 300:
                return resp
            code = status(resp)              # not resp.status_code: see THE STORAGE QUIRK
            if code == 404 and allow_404:
                return resp
            if code < 500:
                explain(resp, what, advice_401)   # a 4xx is our mistake: never retried
            if attempt == RETRIES:
                explain(resp, what, advice_401)
        elif attempt == RETRIES:
            reason, exc = last_transport
            raise WorkspaceError(
                "Sutra could not %s: %s. Check that you are online, then try again — "
                "nothing was lost, the change is still queued locally."
                % (what, reason), 0, {"transport": type(exc).__name__})

        time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])

    # Unreachable: every path above either returns or raises on the last attempt.
    raise WorkspaceError("Sutra could not %s." % what)
