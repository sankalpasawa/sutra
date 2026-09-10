"""client.py — the one place Supabase is spoken to.

Same shape as tools/dfs.py: every call goes through this module, so the credentials live in
exactly one place and a header change is a one-line fix instead of a hunt through five call
sites. Nothing outside this file may build an httpx request to Supabase.

TWO HTTP SURFACES, ONE KEY.

  * PostgREST, at <project>/rest/v1/<table>, is the rows. Filters are query parameters in
    PostgREST's own `column=op.value` shape, which is why where= takes a dict and turns it
    into that rather than inventing a query language of its own.
  * Storage, at <project>/storage/v1/object/<bucket>/<path>, is the knowledge pack.

Both are authenticated with the SAME publishable key, in both the `apikey` header and the
`Authorization: Bearer` header. That duplication is not a mistake: PostgREST reads `apikey`,
the Storage service reads `Authorization`, and sending only one of them fails on whichever
service was not sent its own.

WHAT THIS FILE WILL NEVER DO. It will never ask for, hold, or send a secret key
(`sb_secret_`, a service_role JWT) or a personal access token. Those bypass Row Level
Security or can drop tables, and WORKSPACE-PLAN section 5 rules them out by name. The one
place a personal access token appears in this package is schema.create(), as an argument
that is used once and never written down.

Measured against the owner's real project, 2026-09-10:

  * a publishable key can read and write rows, and can read Storage
  * a publishable key CANNOT create a storage bucket -- 400 "new row violates row-level
    security policy" -- which is why the bucket is created by schema.sql instead
  * the OpenAPI root (GET /rest/v1/) is refused to a publishable key with "Secret API key
    required", so nothing here may use it to discover tables
"""
import json
import os
import time
import uuid

from .. import store
from ._common import (NotConfigured, TIMEOUT, UPLOAD_TIMEOUT, TableMissing,
                      WorkspaceError, request)

# The six things a connected workspace remembers, all inside connections.json, which
# store.save_connections already keeps at 0600.
#
#   workspace_url   the project address, public, and inside the share link
#   workspace_key   the sb_publishable_ key, bounded by RLS, and inside the share link
#   workspace_id    which workspace these rows belong to
#   workspace_name  what to call it on screen while nothing is being fetched
#   member_id       this person's id, stamped on their writes
#   member_name     this person's name, what the Library shows next to their articles
#   last_seen_id    the highest `changes.id` already applied locally; the whole sync protocol
#
# workspace_name is here because the Connections tab shows the workspace by name in its
# RESTING state, when no call is in flight (2026-09-10). Without a local copy the screen
# either shows a blank where the name goes or fetches on every render. It is a cache of
# `workspace.name`, and the database is the truth: register_member() refreshes it from the
# row it reads, so a rename by a teammate lands on the next join or heartbeat.
SETTINGS = ("workspace_url", "workspace_key", "workspace_id", "workspace_name",
            "member_id", "member_name", "last_seen_id")

# NO TOKEN IS STORED, and it is not a security compromise we are making — it is that nobody
# should ever be asked for one twice. See schema.MIGRATIONS: a workspace created by this build is
# born current, so the only workspaces a migration can apply to are ones made before the change
# that needs it. That is a population that shrinks to nothing, and it was never worth a stored
# admin credential. (2026-09-10, the owner: "I don't think the token being saved is a point, the
# question is do we even let the user update this.")


# How often heartbeat() is allowed to actually write. The Connections tab polls about once a
# second; a write per poll would be 3,600 pointless updates an hour per person. A minute is
# fine because the only question it answers is "who is around", and "around" is not a
# question with second-level resolution.
HEARTBEAT_SECONDS = 60.0
# How recently a member must have been seen to count as here now. Three heartbeats, so one
# missed poll or a laptop lid closed for a moment does not make somebody vanish from the list.
ACTIVE_SECONDS = 180.0

# The knowledge pack's bucket. One bucket, one object per pack version.
BUCKET = "knowledge"


# ---- the connection ----------------------------------------------------------------------

def settings():
    """The six workspace fields out of connections.json, as strings, missing ones blank."""
    conn = store.connections()
    return {k: (conn.get(k) if conn.get(k) is not None else "") for k in SETTINGS}


def save_settings(**fields):
    """Merge fields into connections.json and hand back the new settings.

    A merge, not a replace, because connections.json also holds the DataForSEO login and the
    Voyage key and this module must never be the reason those disappear.
    """
    unknown = [k for k in fields if k not in SETTINGS]
    if unknown:
        raise WorkspaceError("Not a workspace setting: %s" % ", ".join(sorted(unknown)))
    conn = store.connections()
    for key, value in fields.items():
        conn[key] = "" if value is None else str(value)
    store.save_connections(conn)
    return settings()


def forget():
    """Disconnect. Clears the six fields and leaves every other connection alone."""
    conn = store.connections()
    for key in SETTINGS:
        conn.pop(key, None)
    store.save_connections(conn)


def configured():
    """True when there is somewhere to talk to and a key to talk with.

    Deliberately does not check that the tables exist: that is verify()'s job and it costs a
    network call. This one is asked on every render.
    """
    current = settings()
    return bool(current["workspace_url"].strip() and current["workspace_key"].strip())


def _conn():
    current = settings()
    url = current["workspace_url"].strip().rstrip("/")
    key = current["workspace_key"].strip()
    if not url or not key:
        raise NotConfigured(
            "No team workspace is connected yet. Open the Connections tab and either create "
            "a workspace or paste the link a teammate sent you.")
    return url, key, current


def actor():
    """The name stamped on this person's writes. The trigger reads it from a header.

    Falls back to the member id, then to the machine's user name, then to 'unknown' -- never
    to a blank, because a blank in the Library reads as a bug rather than as "we do not know".
    """
    current = settings()
    return (current["member_name"].strip() or current["member_id"].strip()
            or os.environ.get("USER", "").strip() or "unknown")


def headers(url=None, key=None, extra=None):
    """The headers every call sends. Built here and never logged: an error string ends up in
    a bug report, and a key in a bug report is a key that has to be rotated."""
    if key is None:
        _, key, _ = _conn()
    out = {
        "apikey": key,                      # PostgREST reads this one
        "Authorization": "Bearer " + key,   # Storage reads this one
        "x-sutra-actor": actor(),           # the log_change trigger reads this one
    }
    if extra:
        out.update(extra)
    return out


# ---- PostgREST -------------------------------------------------------------------------

# The filters PostgREST understands that we let a caller ask for. The list is closed on
# purpose: an unknown operator would be sent to Supabase as a literal and come back as a
# confusing 400 instead of a mistake caught here, next to the code that made it.
OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is", "in", "cs", "not.is")


def _filter(value):
    """A where= value turned into PostgREST's `op.value`.

    A bare value means equals, which is what nine calls in ten want. A (op, value) pair asks
    for anything else. A list under `in` becomes in.(a,b,c).
    """
    if isinstance(value, (tuple, list)) and len(value) == 2 and value[0] in OPERATORS:
        op, val = value
    else:
        op, val = "eq", value
    if op == "in":
        items = val if isinstance(val, (list, tuple, set)) else [val]
        return "in.(%s)" % ",".join(str(i) for i in items)
    if val is None:
        return "is.null"
    if isinstance(val, bool):
        return "%s.%s" % (op, "true" if val else "false")
    return "%s.%s" % (op, val)


def _params(where=None, order=None, limit=None, columns="*", offset=None):
    params = {"select": columns}
    for column, value in (where or {}).items():
        params[column] = _filter(value)
    if order:
        params["order"] = order if isinstance(order, str) else ".".join(str(p) for p in order)
    if limit is not None:
        params["limit"] = int(limit)
    if offset is not None:
        params["offset"] = int(offset)
    return params


def _rest(table, url=None, key=None):
    if url is None or key is None:
        url, key, _ = _conn()
    return url.rstrip("/") + "/rest/v1/" + table, key


def select(table, where=None, order=None, limit=None, columns="*", offset=None,
           url=None, key=None):
    """Rows out of one table. Returns a list, empty when nothing matches.

        select("ideas", where={"ticked": True}, order="updated_at.desc", limit=50)
        select("changes", where={"id": ("gt", last_seen)}, order="id.asc", limit=500)
    """
    endpoint, key = _rest(table, url, key)
    resp = request("GET", endpoint, "read the %s table" % table,
                   headers=headers(key=key),
                   params=_params(where, order, limit, columns, offset))
    return resp.json() or []


def one(table, where=None, columns="*", url=None, key=None):
    """The first matching row, or None. For the tables that hold exactly one row."""
    rows = select(table, where=where, columns=columns, limit=1, url=url, key=key)
    return rows[0] if rows else None


def insert(table, rows, url=None, key=None):
    """Add rows. Returns them as the database stored them, defaults filled in.

    return=representation costs nothing extra and hands back the generated ids and
    timestamps, so a caller never has to guess what landed.
    """
    rows = rows if isinstance(rows, list) else [rows]
    if not rows:
        return []
    endpoint, key = _rest(table, url, key)
    resp = request("POST", endpoint, "add to the %s table" % table,
                   headers=headers(key=key, extra={"content-type": "application/json",
                                                   "Prefer": "return=representation"}),
                   json_body=rows)
    return resp.json() or []


def upsert(table, rows, on_conflict=None, url=None, key=None):
    """Add rows, replacing any that are already there.

    This is the one every sync path wants. WORKSPACE-PLAN section 8: two people editing one
    prompt means last save wins, and merge-duplicates IS last save wins, decided by the
    database rather than by whoever's client happened to check first.
    """
    rows = rows if isinstance(rows, list) else [rows]
    if not rows:
        return []
    endpoint, key = _rest(table, url, key)
    params = {"on_conflict": on_conflict} if on_conflict else None
    resp = request("POST", endpoint, "save to the %s table" % table,
                   headers=headers(key=key, extra={
                       "content-type": "application/json",
                       "Prefer": "resolution=merge-duplicates,return=representation"}),
                   params=params, json_body=rows)
    return resp.json() or []


def update(table, where, patch, url=None, key=None):
    """Change the matching rows. where is required and may not be empty.

    An empty where in PostgREST means EVERY ROW, and a caller that meant "this one" and
    passed an empty dict by accident would silently rewrite the whole table. So it is
    refused here, loudly, rather than obeyed.
    """
    if not where:
        raise WorkspaceError(
            "Sutra refused to update the %s table without saying which rows. That would have "
            "changed every row in it." % table)
    endpoint, key = _rest(table, url, key)
    resp = request("PATCH", endpoint, "update the %s table" % table,
                   headers=headers(key=key, extra={"content-type": "application/json",
                                                   "Prefer": "return=representation"}),
                   params=_params(where), json_body=patch)
    return resp.json() or []


def delete(table, where, url=None, key=None):
    """Remove the matching rows. where is required, for the same reason as update()."""
    if not where:
        raise WorkspaceError(
            "Sutra refused to delete from the %s table without saying which rows. That would "
            "have emptied it." % table)
    endpoint, key = _rest(table, url, key)
    resp = request("DELETE", endpoint, "delete from the %s table" % table,
                   headers=headers(key=key, extra={"Prefer": "return=representation"}),
                   params=_params(where))
    try:
        return resp.json() or []
    except (ValueError, json.JSONDecodeError):
        return []


# ---- who is in it ---------------------------------------------------------------------------
#
# THE ENGINE OWNS THE MEMBERS ROW. Nothing outside this package may insert into `members`. The
# Connections panel was writing it directly as a stopgap (2026-09-10) and that is a second
# writer: two places deciding what a member row looks like drift, and the one that drifts is
# always the one nobody re-reads. The panel calls register_member() and heartbeat() instead.
#
# `member_id` is minted once per install and kept in connections.json for good. It is a plain
# uuid4 and it identifies a SEAT, not a person: it is what makes rejoining idempotent, what
# stamps `actor` on the log, and what a rename updates rather than replaces.

def member_id():
    """This install's member id, minted on first use and never changed afterwards.

    Minted here rather than at join time so that every write has an actor even if a join was
    interrupted halfway, and so a person who leaves and rejoins the same workspace lands back
    on their own row instead of appearing twice in the list.
    """
    current = settings()["member_id"].strip()
    if current:
        return current
    minted = str(uuid.uuid4())
    save_settings(member_id=minted)
    return minted


def register_member(name=None, url=None, key=None, workspace_id=None):
    """Put this person in the members table, and remember who they are locally.

    Called on CREATE (for the creator) and on JOIN (for the joiner). Both go through here, so
    there is one definition of what a member row looks like instead of two that drift.

    IDEMPOTENT ON member_id, which is the whole requirement: a retried create, a rejoin, or a
    person pasting the link twice must never make a second row. It reads first and updates
    what is there rather than upserting, because a blind upsert would reset `joined_at` to now
    on every rejoin -- and "joined_at" that changes every time is not a joined_at, it is a
    second last_seen_at. The 409 fallback covers the case where the row appeared between the
    read and the write.
    """
    mid = member_id()
    who = (name or "").strip() or settings()["member_name"].strip() or actor()
    now = _stamp()

    existing = None
    try:
        existing = one("members", where={"member_id": mid}, url=url, key=key)
    except TableMissing:
        raise
    except WorkspaceError:
        # A read that failed for some other reason should not stop a person joining; the write
        # below will raise on its own if the table is genuinely unusable.
        existing = None

    if existing:
        rows = update("members", {"member_id": mid},
                      {"name": who, "last_seen_at": now}, url=url, key=key)
    else:
        row = {"member_id": mid, "name": who, "joined_at": now, "last_seen_at": now}
        if workspace_id:
            # Normally the column default fills this in. Passed explicitly only when the
            # caller already knows it, so a join does not depend on the default resolving.
            row["workspace_id"] = workspace_id
        try:
            rows = insert("members", row, url=url, key=key)
        except WorkspaceError as e:
            if e.status != 409:
                raise
            rows = update("members", {"member_id": mid},
                          {"name": who, "last_seen_at": now}, url=url, key=key)

    save_settings(member_name=who)
    _HEARTBEAT["at"] = time.time()      # the write above already counts as one
    return (rows or [{}])[0]


_HEARTBEAT = {"at": 0.0}


def heartbeat(url=None, key=None, force=False):
    """Say this person is still here. Returns True when it actually wrote.

    Rate-limited to HEARTBEAT_SECONDS in memory, so a screen polling once a second can call it
    on every poll without thinking about it -- which is the only way a heartbeat ever gets
    called correctly. The database side is guarded too: schema.sql's trigger skips an update
    that changed nothing but last_seen_at, so a heartbeat never reaches the change log.

    Never raises for a network failure. A missed heartbeat means somebody looks idle for a
    minute; it is not worth interrupting what the person was doing.
    """
    if not configured() or not settings()["member_id"].strip():
        return False
    now = time.time()
    if not force and (now - _HEARTBEAT["at"]) < HEARTBEAT_SECONDS:
        return False
    _HEARTBEAT["at"] = now              # set BEFORE the call, so a slow failure cannot spin
    try:
        update("members", {"member_id": settings()["member_id"].strip()},
               {"last_seen_at": _stamp()}, url=url, key=key)
        return True
    except WorkspaceError:
        return False


def members(active_within=None, url=None, key=None):
    """Everyone in the workspace, most recently seen first.

    active_within, in seconds, filters to who is actually around -- pass ACTIVE_SECONDS for
    "here now". Left None it returns everybody who ever joined, which is what a member list
    wants and what "who is in it" does not.
    """
    rows = select("members", order="last_seen_at.desc", url=url, key=key)
    if active_within is None:
        return rows
    cutoff = _stamp(time.time() - float(active_within))
    return [r for r in rows if str(r.get("last_seen_at") or "") >= cutoff]


def _stamp(epoch=None):
    """An ISO-8601 UTC timestamp Postgres accepts as a timestamptz.

    Sent explicitly rather than left to the column default because these are ordinary
    record-keeping times, not the log's ordering clock -- see the note on changes.at in
    schema.sql for the one place a clock is load-bearing.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",
                         time.gmtime(time.time() if epoch is None else epoch))


# ---- the change log ----------------------------------------------------------------------

def since(last_seen_id=None, limit=500, url=None, key=None):
    """The change log rows this client has not applied yet, oldest first.

    That single query is the whole sync protocol (WORKSPACE-PLAN section 3). Deletions come
    back as ordinary rows with op='delete', so "40 pages are gone" needs no special path.
    """
    if last_seen_id is None:
        last_seen_id = settings()["last_seen_id"] or 0
    return select("changes", where={"id": ("gt", int(last_seen_id or 0))},
                  order="id.asc", limit=limit, url=url, key=key)


# ---- Storage ------------------------------------------------------------------------------

def _object_url(bucket, path, url=None):
    if url is None:
        url, _, _ = _conn()
    return "%s/storage/v1/object/%s/%s" % (url.rstrip("/"), bucket, path.lstrip("/"))


def upload(bucket, path, data, content_type="application/octet-stream",
           replace=True, url=None, key=None):
    """Put bytes in the cupboard. Returns the stored path.

    replace=True sends x-upsert, because the pack is rebuilt on every click
    (WORKSPACE-PLAN section 2) and a second upload of the same version must overwrite rather
    than fail. The timeout is the long one: the pack is around 100 MB.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    if url is None or key is None:
        url, key, _ = _conn()
    extra = {"content-type": content_type}
    if replace:
        extra["x-upsert"] = "true"
    request("POST", _object_url(bucket, path, url),
            "upload %s to the %s cupboard" % (path, bucket),
            headers=headers(key=key, extra=extra), content=data, timeout=UPLOAD_TIMEOUT)
    return path


def download(bucket, path, url=None, key=None):
    """Get bytes back out. Raises rather than returning empty when it is not there, because
    a caller that unzipped b'' would fail two steps later with a useless message."""
    if url is None or key is None:
        url, key, _ = _conn()
    resp = request("GET", _object_url(bucket, path, url),
                   "download %s from the %s cupboard" % (path, bucket),
                   headers=headers(key=key), timeout=UPLOAD_TIMEOUT)
    return resp.content


def remove(bucket, path, url=None, key=None):
    """Delete one object. Used to drop last month's pack once the new one is up."""
    if url is None or key is None:
        url, key, _ = _conn()
    request("DELETE", _object_url(bucket, path, url),
            "remove %s from the %s cupboard" % (path, bucket),
            headers=headers(key=key))
    return True


def objects(bucket, prefix="", limit=100, url=None, key=None):
    """What is in the cupboard. Storage lists through a POST, not a GET, which is the one
    place its API stops looking like the rest."""
    if url is None or key is None:
        url, key, _ = _conn()
    resp = request("POST", "%s/storage/v1/object/list/%s" % (url.rstrip("/"), bucket),
                   "list the %s cupboard" % bucket,
                   headers=headers(key=key, extra={"content-type": "application/json"}),
                   json_body={"prefix": prefix, "limit": int(limit),
                              "sortBy": {"column": "name", "order": "asc"}})
    return resp.json() or []


def bucket_exists(bucket=BUCKET, url=None, key=None):
    """Whether the pack can actually be stored: not whether the bucket RECORD is readable.

    THIS ASKED THE WRONG QUESTION AND TOLD THE OWNER HIS SETUP HAD FAILED WHEN IT HAD NOT
    (2026-09-09, his first real run). It read GET /storage/v1/bucket/<name>, which reads the
    bucket's row in storage.buckets. Measured on his live project:

        GET  /storage/v1/bucket             -> 200 []                    (empty!)
        GET  /storage/v1/bucket/knowledge   -> 400 {"statusCode":"404","code":"NoSuchBucket"}
        POST /storage/v1/object/knowledge/probe/hello.txt   -> 200       (it uploaded)
        GET  /storage/v1/object/knowledge/probe/hello.txt   -> 200 b'one'
        DELETE  the same                                    -> 200

    The bucket was there the whole time and all four operations worked. What a publishable key
    cannot do is READ storage.buckets, because schema.sql grants policies on storage.OBJECTS and
    Supabase ships none on storage.buckets for anon. So "I cannot see the bucket's row" was being
    reported as "there is no bucket", and verify() then called a working workspace broken.

    The question that matters is "can the pack be stored", so that is the question this asks: it
    writes a tiny object, reads it back, and deletes it. That is the same round trip pack.py makes,
    through the same policies, with the same key. A bucket whose record we cannot read but whose
    objects we can write is a perfectly good bucket; one whose record reads fine but rejects an
    upload is useless, and the old check called that one healthy.

    Never raises: a workspace with no working cupboard is a real state verify() must report, not
    an error. The probe key is unique per call so two Sutras checking at once cannot collide, and
    the delete is best-effort — a stray probe file is harmless next to a false failure.
    """
    if url is None or key is None:
        url, key, _ = _conn()
    base = url.rstrip("/")
    path = "%s/storage/v1/object/%s/.sutra-probe/%s" % (base, bucket, uuid.uuid4().hex)
    try:
        wrote = request("POST", path, "check the %s cupboard" % bucket,
                        headers={**headers(key=key), "Content-Type": "application/octet-stream",
                                 "x-upsert": "true"},
                        content=b"sutra", allow_404=True)
        if wrote.status_code >= 300:
            return False
        read = request("GET", path, "check the %s cupboard" % bucket,
                       headers=headers(key=key), allow_404=True)
        return read.status_code < 300
    except WorkspaceError:
        return False
    finally:
        try:
            request("DELETE", path, "tidy the probe", headers=headers(key=key), allow_404=True)
        except Exception:  # noqa: BLE001 — a leftover probe file is not worth a failure
            pass
