"""tests/test_workspace_core.py — the workspace core, offline.

WHAT THIS SUITE IS FOR. seo_agent/workspace/ is the only part of Sutra that puts a team's
knowledge in somebody else's database, and three of its properties are the kind that are
invisible until the day they are wrong: a personal access token must never touch the disk, a
share link must never be able to create or drop a table, and nothing may report success it
has not verified. None of the three shows up in a screenshot, so all three are asserted here.

STUB-PROVED VERSUS LIVE-PROVED, AND WHICH IS WHICH. Every check below runs offline against a
fake httpx, like every other suite in this folder. Some of them stand in for something that
HAS been measured against the owner's real Supabase project (2026-09-10) and some stand in
for something that has NOT, because creating tables needs a Supabase personal access token
and no such token existed on the machine when this was written. Each check that is only
stub-proved says so on its own line, because a label somebody can read beats an assumption
somebody makes. See design/HANDOFF-W1.md for the live proof still to run.

The fake httpx records every request, so the checks assert what WENT OUT — the method, the
path, the headers, the number of attempts — rather than reading a return value that a bug
could have produced for the wrong reason.
"""
import json
import os
import re
import sys

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import store
from seo_agent.workspace import _common, client, link, schema
from seo_agent.workspace._common import NotConfigured, TableMissing, WorkspaceError

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def raises(label, fn, contains=None, kind=WorkspaceError):
    try:
        fn()
    except kind as e:
        if contains and contains.lower() not in str(e).lower():
            return ok(label, False, "message was: " + str(e))
        return ok(label, True)
    except Exception as e:                      # noqa: BLE001 - a wrong class is a real failure
        return ok(label, False, "raised %s instead: %s" % (type(e).__name__, e))
    return ok(label, False, "did not raise")


# ---- the fake wire -------------------------------------------------------------------------
#
# _common calls httpx.request() and nothing else, which is the whole reason that indirection
# exists: one function to replace and the entire package is offline.

class FakeResponse:
    def __init__(self, status_code, payload=None, content=b"", text=None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHttpx:
    """Stands in for the httpx module inside _common. Answers come from a queue or a router."""

    class TimeoutException(Exception):
        pass

    class TransportError(Exception):
        pass

    def __init__(self):
        self.calls = []
        self.queue = []
        self.router = None

    def request(self, method, url, headers=None, params=None, json=None, content=None,
                timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {},
                           "params": params or {}, "json": json, "content": content,
                           "timeout": timeout})
        if self.queue:
            answer = self.queue.pop(0)
        elif self.router:
            answer = self.router(method, url, params or {}, json)
        else:
            answer = FakeResponse(200, [])
        if isinstance(answer, Exception):
            raise answer
        return answer


class NoSleep:
    """The retry backoff is 0.5s then 1.5s. A suite must not spend two seconds proving it."""
    slept = []

    def sleep(self, seconds):
        NoSleep.slept.append(seconds)


WIRE = FakeHttpx()
_common.httpx = WIRE
_common.time = NoSleep()


def wire(*answers):
    """Queue the answers the next calls will get, and clear the record of previous ones."""
    WIRE.calls = []
    WIRE.queue = list(answers)
    WIRE.router = None
    return WIRE


def route(fn):
    WIRE.calls = []
    WIRE.queue = []
    WIRE.router = fn
    return WIRE


URL = "https://vxhxlgtmbuajgwlvhecu.supabase.co"
KEY = "sb_publishable_MvT8QkGwBGaQRjxA-kFT5g_Jg0YlTrn"


def connect(**extra):
    fields = {"workspace_url": URL, "workspace_key": KEY, "workspace_id": "ws-abc",
              "member_name": "Ravi"}
    fields.update(extra)
    client.save_settings(**fields)


# ---- 1. the share link ------------------------------------------------------------------------
print("\n1. the share link — and that nothing in it can create or drop a table")

made = link.make_link(URL, KEY, "ws-abc")
ok("a link is one opaque token with a readable prefix",
   made.startswith("sutra1_") and " " not in made, made)
ok("it round-trips to exactly the three things that went in",
   link.read_link(made) == (URL, KEY, "ws-abc"))
ok("the same three inputs always make the same link",
   link.make_link(URL, KEY, "ws-abc") == made)

# THE SECURITY ASSERTION. The link is the one thing in this system that gets pasted into
# WhatsApp. What it cannot carry matters more than what it can.
decoded = link._b64decode(made[len("sutra1_"):]).decode("utf-8")
lowered = decoded.lower()
ok("the link carries no SQL at all",
   not any(word in lowered for word in ("create ", "drop ", "table", "insert ", "delete ",
                                        "alter ", "grant ", "select ", ";")), decoded)
ok("the link carries no personal access token and no secret key",
   "sbp_" not in lowered and "sb_secret_" not in lowered and "service_role" not in lowered)
ok("the link carries exactly four fields: version, url, key, workspace id",
   sorted(json.loads(decoded).keys()) == ["k", "u", "v", "w"], sorted(json.loads(decoded).keys()))

raises("making a link with a secret key is refused before it can be sent",
       lambda: link.make_link(URL, "sb_secret_abcdefghij", "ws-abc"), "secret key")
raises("making a link with a personal access token is refused",
       lambda: link.make_link(URL, "sbp_abcdefghijklmnop", "ws-abc"), "secret key")
raises("reading a hand-edited link carrying a secret key is refused too",
       lambda: link.read_link("sutra1_" + link._b64encode(json.dumps(
           {"v": 1, "u": URL, "k": "sb_secret_sneaky", "w": "ws-abc"}).encode())), "secret key")
raises("a link pointing somewhere that is not Supabase is refused",
       lambda: link.read_link("sutra1_" + link._b64encode(json.dumps(
           {"v": 1, "u": "https://evil.example.com", "k": KEY, "w": "ws"}).encode())),
       "supabase project")

ok("a link that arrived with a line break through it still reads",
   link.read_link(made[:20] + "\n  " + made[20:]) == (URL, KEY, "ws-abc"))
raises("an empty box says paste the link", lambda: link.read_link("   "), "paste the link")
raises("a plain URL pasted instead of a link is named as such",
       lambda: link.read_link(URL), "not a Sutra workspace link")
raises("a truncated link says it is cut short",
       lambda: link.read_link("sutra1_"), "cut short")
raises("a damaged link says it is damaged, not 'invalid base64'",
       lambda: link.read_link("sutra1_!!!!not-base64!!!!"), "damaged")
raises("a link from a newer Sutra asks the person to update",
       lambda: link.read_link("sutra1_" + link._b64encode(json.dumps(
           {"v": 99, "u": URL, "k": KEY, "w": "ws"}).encode())), "newer Sutra")


# ---- 2. schema.sql, read as a file ---------------------------------------------------------------
print("\n2. schema.sql — one transaction, idempotent, triggers, RLS")

SQL = schema.sql()
low = SQL.lower()
# The structural counts below must not see the comments. schema.sql explains ITSELF at
# length -- it says the words "create policy if not exists" in a comment about why that
# syntax does not exist -- and counting that as a statement made the first version of this
# suite report 16 policies created and 15 dropped. So: comments stripped, whitespace
# collapsed, then count.
CODE = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", SQL)).lower()
# And the mirror image, for the prose checks: comment markers dropped, wrapped lines rejoined,
# so a sentence that runs across three comment lines is still one searchable sentence. Written
# without this, "for either half" failed only because the line broke between "for" and "either".
PROSE = re.sub(r"\s+", " ", re.sub(r"\s*--\s*", " ", SQL)).lower()

ok("it is one transaction: begin at the top, commit at the bottom",
   CODE.count(" begin; ") == 1 and CODE.count(" commit; ") == 1
   and CODE.index(" begin; ") < CODE.index(" commit; "),
   "%d begin, %d commit" % (CODE.count(" begin; "), CODE.count(" commit; ")))

for table in schema.TABLES:
    ok("creates %s, and with `if not exists` so a retry is harmless" % table,
       ("create table if not exists public.%s (" % table) in CODE)

ok("all ten tables and no eleventh",
   CODE.count("create table if not exists public.") == len(schema.TABLES),
   CODE.count("create table if not exists public."))

# THE TRIGGER IS THE POINT (WORKSPACE-PLAN section 3). One function, attached to every domain
# table, so a client that crashes between the row and the log cannot lose a change.
ok("one trigger function, written once", CODE.count("function public.log_change() returns trigger") == 1)
ok("it is security definer, so it can write a log the caller may not write",
   "security definer" in CODE.split("log_change() returns trigger")[1][:200])
for table in schema.TABLES:
    if table == "changes":
        continue
    ok("an after insert/update/delete trigger on %s" % table,
       re.search(r"create or replace trigger \w+ after insert or update or delete on public\.%s\b"
                 % table, CODE) is not None)
ok("no trigger on `changes` itself — logging the log would recurse for ever",
   re.search(r"trigger \w+ after insert or update or delete on public\.changes", CODE) is None)

# THE LOST-CHANGE RACE, found 2026-09-10. bigserial allocates at INSERT, not at COMMIT, so a
# writer holding id 7 can commit AFTER a writer holding id 8. A poller that read 8 and moved
# its cursor would never read 7. The reader guards against it by consuming only rows older
# than a lag window, and that guard is powered entirely by this column's clock.
# \b matters here. Written without it, "at timestamptz ... default now()" also matches
# `joined_at`, `changed_at` and `updated_at`, and the check passed on tables it was not about.
ok("changes.at is clock_timestamp() — the real wall clock at the insert",
   re.search(r"\bat timestamptz not null default clock_timestamp\(\)", CODE) is not None)
ok("and it is NOT now(), which is transaction START time and would stamp a slow writer EARLY",
   re.search(r"\bat timestamptz not null default (now\(\)|current_timestamp)", CODE) is None)
ok("the index that makes the reader's window query cheap is (at, id)",
   "create index if not exists changes_at_id_idx on public.changes (at, id)" in CODE)
ok("the reasoning is written where the next person will find it, not rediscovered",
   "bigserial" in PROSE and "will never read it" in PROSE)
ok("and the lag window in the comment is the same 3 seconds the reader filters on",
   "interval '3 seconds'" in low)
ok("and the residual is stated: a transaction open longer than the window can still be skipped",
   "stays open for longer than the lag window can still be skipped" in PROSE)
ok("only the log's clock is load-bearing — the other tables keep now(), and that is said so",
   "default now()" in CODE and "ordinary record-keeping" in PROSE)

# The sync side (mirror.py) depends on all three of these. Reconciled 2026-09-10.
ok("the trigger writes op for every operation, from tg_op",
   "values (tg_table_name, lower(tg_op), row_key, row_data," in CODE)
ok("a delete logs the whole old row, so the payload of a deletion is a real row",
   "if (tg_op = 'delete') then row_data := to_jsonb(old);" in CODE)
ok("pages carries its own op column, so a page GOING AWAY is an update to 'gone' ...",
   "op text not null default 'changed'" in CODE and "changed | gone" in low)
ok("... and a real delete on pages means the delta is being TRIMMED, never that a page is gone",
   "carries only what changed since that pack was built, and is trimmed" in low)

for table in schema.TABLES:
    ok("row level security is on for %s" % table,
       ("alter table public.%s enable row level security" % table) in CODE)

ok("every policy is preceded by a drop-if-exists, since Postgres has no create policy if not exists",
   CODE.count("create policy ") == CODE.count("drop policy if exists "),
   "%d create vs %d drop" % (CODE.count("create policy "), CODE.count("drop policy if exists ")))
ok("every domain policy is scoped to this workspace, both reading and writing",
   CODE.count("using (workspace_id = public.current_workspace_id())") >= 8
   and CODE.count("with check (workspace_id = public.current_workspace_id())") >= 8)
ok("the changes log has a read policy and no write policy — append-only to everyone but the trigger",
   "create policy changes_read on public.changes for select" in CODE
   and "on public.changes for all" not in CODE
   and "on public.changes for insert" not in CODE)
ok("the log is granted select only, never insert",
   "grant select on public.changes to anon, authenticated" in CODE)

# The bucket. Measured 2026-09-10: a publishable key cannot create one, so this is the only
# moment it can be made.
ok("it creates the knowledge bucket", "insert into storage.buckets" in CODE
   and "'knowledge'" in CODE)
ok("bucket creation is idempotent", "on conflict (id) do update" in CODE)

# THE OBJECT SIZE LIMIT. Measured 2026-09-10: the owner's real pack is 205 MB zipped and
# Supabase Free caps ONE object at 50 MB, so the pack goes up in parts and the part size must
# be decided here rather than discovered from whatever plan the bucket happened to be made on.
PINNED = 47185920                       # 45 MiB
ok("the bucket's object limit is pinned at creation, not left to the plan default",
   "file_size_limit" in CODE and str(PINNED) in CODE)
ok("and it is under the SMALLER reading of '50 MB', so it is safe either way it is meant",
   PINNED < 50_000_000)

# The number has to clear a window at BOTH ends, and the lower end is the one that bites: an
# obvious 40 MiB pin would have cut pack.py's parts to 36 MiB, making the pin the thing that
# changed the split it was added to stop.
# This reaches into pack.py ON PURPOSE. The two numbers have to agree and they live in two
# files, so if PART_BYTES or PART_HEADROOM ever move, THIS SUITE SHOULD GO RED. That is the
# check, not an accidental coupling to somebody else's module.
from seo_agent.workspace import pack as _pack           # noqa: E402
ok("and it is high enough that pack.py's own formula still yields its full part size",
   max(1 << 20, min(_pack.PART_BYTES, PINNED - _pack.PART_HEADROOM)) == _pack.PART_BYTES,
   "part would be %d, PART_BYTES is %d"
   % (max(1 << 20, min(_pack.PART_BYTES, PINNED - _pack.PART_HEADROOM)), _pack.PART_BYTES))

# Raising is safe; lowering strands parts already stored. So the conflict clause may only ever
# raise -- which also leaves a bucket somebody deliberately set higher by hand alone.
ok("re-running the script can only ever RAISE an existing bucket's limit, never lower it",
   "greatest(coalesce(storage.buckets.file_size_limit, 0)" in CODE)
ok("the reasoning is in the file: the cap, the parts, and which direction is safe to change",
   "caps a single stored object at 50 mb" in PROSE
   and "stored as numbered parts" in PROSE and "raising this later is safe" in PROSE)
ok("and so is why two generations are kept, so nobody tidies it down to one",
   "two generations of each half are kept at once, deliberately" in PROSE
   and "reintroduces the torn-download race" in PROSE)
for op in ("select", "insert", "update", "delete"):
    ok("a storage policy for %s on the knowledge bucket" % op,
       re.search(r"create policy knowledge_\w+ on storage\.objects for %s\b" % op, CODE) is not None)
ok("the storage block cannot abort the tables — it catches insufficient_privilege",
   "exception when insufficient_privilege" in CODE)

# The cheap-mode fact, and the heartbeat that must not fill the log.
ok("workspace carries bucket_ready, which is what makes a one-call readiness check possible",
   "bucket_ready boolean not null default false" in CODE)
ok("and the storage block sets it LAST, so a failed policy leaves it false",
   "update public.workspace set bucket_ready = true;" in CODE
   and CODE.index("create policy knowledge_remove") < CODE.index("set bucket_ready = true"))
ok("the trigger skips an update that changed nothing but last_seen_at",
   "tg_op = 'update' and tg_table_name = 'members'" in CODE
   and "(to_jsonb(new) - 'last_seen_at') = (to_jsonb(old) - 'last_seen_at')" in CODE)
ok("and says why: a heartbeat a minute per person would fill an append-only log for ever",
   "a heartbeat is not a change" in PROSE)

ok("nothing in the script drops a table",
   "drop table" not in CODE and "drop schema" not in CODE)
ok("the script ends by reporting what actually landed, for the person who pasted it",
   CODE.rstrip().endswith("as verdict;") and "workspace ready." in CODE)
ok("the verdict is read OUTSIDE the transaction, so it reports what landed not what was asked",
   CODE.index("commit;") < CODE.index("as verdict;"))
ok("schema_version is written at creation",
   "insert into public.workspace (name, schema_version)" in CODE)

# ONE NUMBER, TWO FILES THAT CANNOT IMPORT EACH OTHER. A fresh workspace must be born at the
# version the code expects, or every fresh workspace would immediately want a migration it does
# not need.
ok("the version schema.sql writes is the version schema.py expects",
   ("select 'team workspace', %d where not exists" % schema.SCHEMA_VERSION) in CODE,
   re.search(r"select 'team workspace', (\d+)", CODE).group(1) if
   re.search(r"select 'team workspace', (\d+)", CODE) else "not found")
ok("and so is the column default", 
   ("schema_version integer not null default %d" % schema.SCHEMA_VERSION) in CODE)

# THE TORN-DOWNLOAD FIX. The pack is a 33.6 MB core plus a 171.5 MB index; the core was counted
# and the index was not, so the index was overwritten in place and a teammate 171 MB into a
# download could get half the old bytes and half the new.
ok("the index has its own version counter, separate from the core's",
   "pack_version integer not null default 0" in CODE
   and "index_version integer not null default 0" in CODE)
ok("and the file says why two counters and not one: the halves publish on different terms",
   "two counters, not one" in PROSE
   and "republished only when its content hash moves" in PROSE)
ok("and the two-generation note covers BOTH halves now, not just the core",
   "do not \"tidy up\" to one generation, for either half" in PROSE)
ok("the verdict row reports both counters, so a paste-route run shows them",
   "as pack_version" in CODE and "as index_version" in CODE)
ok("the workspace id is generated by the database, so the script has no placeholders",
   "gen_random_uuid()" in CODE and "{{" not in SQL and "%s" not in SQL)


# ---- 3. the client: what actually goes out on the wire -----------------------------------------
print("\n3. client.py — one door, and the right thing goes through it")

store.save_connections({})
ok("configured() is false with nothing connected", client.configured() is False)
raises("a call with nothing connected says so in words, not a KeyError",
       lambda: client.select("ideas"), "no team workspace is connected", NotConfigured)

connect()
ok("configured() is true once a url and key are saved", client.configured() is True)
ok("saving workspace settings did not disturb the other connections",
   "workspace_url" in store.connections())

store.save_connections(dict(store.connections(), dataforseo_login="someone"))
client.save_settings(member_name="Ravi")
ok("save_settings merges, it never replaces connections.json",
   store.connections().get("dataforseo_login") == "someone")
raises("save_settings refuses a field that is not a workspace setting",
       lambda: client.save_settings(nonsense="x"), "not a workspace setting")

ok("workspace_name has a home, so the Connections tab has something to show at rest",
   "workspace_name" in client.SETTINGS)
client.save_settings(workspace_name="Testlify")
ok("and it round-trips through connections.json",
   client.settings()["workspace_name"] == "Testlify")

wire(FakeResponse(200, [{"idea_id": "a"}]))
rows = client.select("ideas", where={"ticked": True}, order="updated_at.desc", limit=50)
call = WIRE.calls[0]
ok("select is a GET on /rest/v1/<table>",
   call["method"] == "GET" and call["url"].endswith("/rest/v1/ideas"), call["url"])
ok("a bare where value becomes PostgREST's eq., and a bool becomes true/false",
   call["params"].get("ticked") == "eq.true", call["params"])
ok("order and limit go through as PostgREST expects them",
   call["params"].get("order") == "updated_at.desc" and call["params"].get("limit") == 50)
ok("both auth headers are sent — PostgREST reads apikey, Storage reads Authorization",
   call["headers"].get("apikey") == KEY and call["headers"].get("Authorization") == "Bearer " + KEY)
ok("the actor header is sent, because the log_change trigger reads it",
   call["headers"].get("x-sutra-actor") == "Ravi")
ok("every call carries a timeout", call["timeout"] is not None)
ok("select hands back the rows", rows == [{"idea_id": "a"}])

wire(FakeResponse(200, []))
client.select("changes", where={"id": ("gt", 41)}, order="id.asc", limit=500)
ok("an (op, value) pair becomes that operator", WIRE.calls[0]["params"].get("id") == "gt.41")

wire(FakeResponse(200, []))
client.select("ideas", where={"kind": ("in", ["a", "b"])})
ok("an in-list becomes in.(a,b)", WIRE.calls[0]["params"].get("kind") == "in.(a,b)")

wire(FakeResponse(200, []))
client.since(41)
ok("since() is the whole sync protocol: id greater than last seen, oldest first",
   WIRE.calls[0]["params"].get("id") == "gt.41" and WIRE.calls[0]["params"].get("order") == "id.asc")

wire(FakeResponse(201, [{"idea_id": "a"}]))
client.insert("ideas", {"idea_id": "a"})
ok("insert is a POST that asks for the stored row back",
   WIRE.calls[0]["method"] == "POST"
   and WIRE.calls[0]["headers"].get("Prefer") == "return=representation")
ok("insert sends a list even when handed one row", WIRE.calls[0]["json"] == [{"idea_id": "a"}])

wire()
ok("inserting nothing makes no call at all", client.insert("ideas", []) == [] and not WIRE.calls)

wire(FakeResponse(200, [{"name": "close"}]))
client.upsert("prompts", {"name": "close", "body": "x"}, on_conflict="name")
ok("upsert asks for merge-duplicates, which is 'last save wins' decided by the database",
   "resolution=merge-duplicates" in WIRE.calls[0]["headers"].get("Prefer", ""))
ok("on_conflict goes through as a parameter", WIRE.calls[0]["params"].get("on_conflict") == "name")

wire(FakeResponse(200, []))
client.update("ideas", {"idea_id": "a"}, {"ticked": True})
ok("update is a PATCH filtered to the named rows",
   WIRE.calls[0]["method"] == "PATCH" and WIRE.calls[0]["params"].get("idea_id") == "eq.a")

wire()
raises("update with an empty where is refused — it would have rewritten every row",
       lambda: client.update("ideas", {}, {"ticked": True}), "every row in it")
ok("and it never reached the wire", not WIRE.calls)
wire()
raises("delete with an empty where is refused — it would have emptied the table",
       lambda: client.delete("ideas", {}), "emptied it")
ok("and that never reached the wire either", not WIRE.calls)

wire(FakeResponse(200, {"Key": "knowledge/pack/7.zip"}))
client.upload("knowledge", "pack/7.zip", b"zipbytes")
call = WIRE.calls[0]
ok("upload POSTs the bytes to /storage/v1/object/<bucket>/<path>",
   call["method"] == "POST" and call["url"].endswith("/storage/v1/object/knowledge/pack/7.zip")
   and call["content"] == b"zipbytes", call["url"])
ok("upload overwrites, because the pack is rebuilt on every click",
   call["headers"].get("x-upsert") == "true")
ok("upload gets the long timeout — the pack is about 100 MB",
   call["timeout"] == _common.UPLOAD_TIMEOUT)

wire(FakeResponse(200, None, content=b"zipbytes"))
ok("download hands back the raw bytes", client.download("knowledge", "pack/7.zip") == b"zipbytes")
wire(FakeResponse(200, {}))
client.remove("knowledge", "pack/6.zip")
ok("remove is a DELETE on the object", WIRE.calls[0]["method"] == "DELETE")


# ---- 3b. the members row, which the engine owns -----------------------------------------------
print("\n3b. members — one writer, idempotent on member_id")

connect()
store.save_connections({k: v for k, v in store.connections().items() if k != "member_id"})
wire()
first = client.member_id()
ok("a member id is minted on first use", bool(first) and len(first) == 36)
ok("and it never changes afterwards — a rejoin lands on the same seat", client.member_id() == first)
ok("minting it costs no network call", not WIRE.calls)

# A NEW member: read finds nothing, so it inserts, and joined_at is set.
wire(FakeResponse(200, []), FakeResponse(201, [{"member_id": first, "name": "Ravi"}]))
row = client.register_member("Ravi")
ok("a new member is read for first, then inserted",
   [c["method"] for c in WIRE.calls] == ["GET", "POST"], [c["method"] for c in WIRE.calls])
ok("the insert carries member_id, name, joined_at and last_seen_at",
   sorted(WIRE.calls[1]["json"][0]) == ["joined_at", "last_seen_at", "member_id", "name"],
   sorted(WIRE.calls[1]["json"][0]))
ok("and the name is remembered locally", client.settings()["member_name"] == "Ravi")
ok("and it comes back as the stored row", row.get("member_id") == first)

# THE IDEMPOTENCE REQUIREMENT. A rejoin must not make a second row, and -- the part a blind
# upsert gets wrong -- must not reset joined_at either.
wire(FakeResponse(200, [{"member_id": first, "name": "Ravi", "joined_at": "2026-01-01T00:00:00Z"}]),
     FakeResponse(200, [{"member_id": first, "name": "Ravi"}]))
client.register_member("Ravi")
ok("registering again UPDATES, it never inserts a second row",
   [c["method"] for c in WIRE.calls] == ["GET", "PATCH"], [c["method"] for c in WIRE.calls])
ok("and it does not touch joined_at — a joined_at that moves is a second last_seen_at",
   "joined_at" not in WIRE.calls[1]["json"], WIRE.calls[1]["json"])
ok("and the update is filtered to this member only",
   WIRE.calls[1]["params"].get("member_id") == "eq." + first)

# The row appearing between the read and the write.
wire(FakeResponse(200, []),
     FakeResponse(409, {"message": "duplicate key value violates unique constraint"}),
     FakeResponse(200, [{"member_id": first}]))
client.register_member("Ravi")
ok("a 409 between the read and the insert falls back to an update, not a crash",
   [c["method"] for c in WIRE.calls] == ["GET", "POST", "PATCH"],
   [c["method"] for c in WIRE.calls])

# A rename is a change and SHOULD reach the log; only the heartbeat is exempt.
wire(FakeResponse(200, [{"member_id": first, "name": "Ravi"}]), FakeResponse(200, [{}]))
client.register_member("Ravi Kumar")
ok("a rename goes through as an ordinary update", WIRE.calls[1]["json"].get("name") == "Ravi Kumar")

client._HEARTBEAT["at"] = 0
wire(FakeResponse(200, [{}]))
ok("a heartbeat writes last_seen_at and nothing else",
   client.heartbeat() is True and list(WIRE.calls[0]["json"]) == ["last_seen_at"])

wire(FakeResponse(200, [{}]))
ok("a second heartbeat inside the window does not write at all",
   client.heartbeat() is False and not WIRE.calls)
ok("the rate limit is a named constant, and it is about a minute",
   30 <= client.HEARTBEAT_SECONDS <= 300, client.HEARTBEAT_SECONDS)
wire(FakeResponse(200, [{}]))
ok("force=True writes anyway", client.heartbeat(force=True) is True)

client._HEARTBEAT["at"] = 0
wire(FakeResponse(500, {}), FakeResponse(500, {}), FakeResponse(500, {}))
ok("a heartbeat that fails returns False rather than interrupting what somebody was doing",
   client.heartbeat() is False)
client._HEARTBEAT["at"] = 0
wire(FakeResponse(200, [{}]))
ok("and the failure did not spin — the next attempt is still rate-limited normally",
   client.heartbeat() is True)

NOW = client._stamp()
OLD = client._stamp(__import__("time").time() - 3600)
wire(FakeResponse(200, [{"member_id": "a", "last_seen_at": NOW},
                        {"member_id": "b", "last_seen_at": OLD}]))
ok("members() returns everybody who ever joined, most recently seen first",
   [m["member_id"] for m in client.members()] == ["a", "b"])
ok("and it asks the database for that order rather than sorting after",
   WIRE.calls[0]["params"].get("order") == "last_seen_at.desc")
wire(FakeResponse(200, [{"member_id": "a", "last_seen_at": NOW},
                        {"member_id": "b", "last_seen_at": OLD}]))
ok("active_within narrows it to who is actually around",
   [m["member_id"] for m in client.members(active_within=client.ACTIVE_SECONDS)] == ["a"])
ok("and 'around' allows a few missed heartbeats, so a closed lid is not a departure",
   client.ACTIVE_SECONDS >= client.HEARTBEAT_SECONDS * 2)


# ---- 4. errors, in English, and the retry rule ------------------------------------------------
print("\n4. _common.py — plain English, and a retry rule that is exactly this narrow")

wire(FakeResponse(401, {"message": "Invalid API key", "hint": "Double check your API key."}))
try:
    client.select("ideas")
    ok("a 401 raises", False)
except WorkspaceError as e:
    text = str(e)
    ok("a 401 says the key is not for this project, in words",
       "that key is not for this project" in text.lower(), text)
    ok("and tells the person exactly where to get the right one",
       "sb_publishable_" in text and "api keys" in text.lower())
    ok("and quotes Supabase's own message and hint", "Invalid API key" in text and "Double check" in text)
    ok("and NEVER contains the key itself", KEY not in text)
    ok("the raw status is kept on the exception for the log, not in the sentence", e.status == 401)
ok("a 401 is not retried — the same wrong thing sent three times is still wrong",
   len(WIRE.calls) == 1, len(WIRE.calls))

# Measured on the real project 2026-09-10: this exact body comes back from an admin-only
# endpoint. It means Sutra called the wrong endpoint, not that the person's key is wrong,
# and telling them to re-paste a perfectly good key would send them on a wild goose chase.
wire(FakeResponse(401, {"message": "Secret API key required",
                        "hint": "Only secret API keys can be used for this endpoint."}))
raises("the other 401 — 'secret API key required' — is named as a bug in Sutra",
       lambda: client.select("ideas"), "bug in Sutra")

wire(FakeResponse(404, {"code": "PGRST205", "message":
                        "Could not find the table 'public.workspace' in the schema cache"}))
raises("a missing table is its own class, so verify can tell it from a refusal",
       lambda: client.select("workspace"), "not been created yet", TableMissing)

wire(FakeResponse(403, {"message": "new row violates row-level security policy"}))
raises("a 403 is explained as the workspace's own security rule",
       lambda: client.select("ideas"), "belongs to a different workspace")

wire(FakeResponse(429, {"message": "Too many requests"}))
raises("a 429 says wait a minute", lambda: client.select("ideas"), "slow down")
ok("a 429 is not retried either", len(WIRE.calls) == 1)

wire(FakeResponse(500, {"message": "boom"}), FakeResponse(500, {"message": "boom"}),
     FakeResponse(500, {"message": "boom"}))
raises("a 5xx that never recovers says it is Supabase's problem, not the person's",
       lambda: client.select("ideas"), "supabase itself had a problem")
ok("a 5xx is retried, exactly RETRIES times more", len(WIRE.calls) == _common.RETRIES + 1,
   len(WIRE.calls))

wire(FakeResponse(503, {}), FakeResponse(200, [{"idea_id": "a"}]))
ok("a 5xx that recovers on the retry returns the rows, and the caller never knew",
   client.select("ideas") == [{"idea_id": "a"}] and len(WIRE.calls) == 2)

wire(FakeHttpx.TransportError("connection reset"),
     FakeHttpx.TransportError("connection reset"),
     FakeHttpx.TransportError("connection reset"))
try:
    client.select("ideas")
    ok("a dropped connection raises", False)
except WorkspaceError as e:
    ok("a dropped connection says check you are online and that nothing was lost",
       "could not reach supabase" in str(e).lower() and "nothing was lost" in str(e).lower(), str(e))
ok("a dropped connection is retried — the owner's wifi drops several times a day",
   len(WIRE.calls) == _common.RETRIES + 1)

wire(FakeHttpx.TransportError("reset"), FakeResponse(200, [{"idea_id": "a"}]))
ok("and a connection that comes back mid-retry just works",
   client.select("ideas") == [{"idea_id": "a"}])

wire(FakeHttpx.TimeoutException("slow"), FakeHttpx.TimeoutException("slow"),
     FakeHttpx.TimeoutException("slow"))
raises("a timeout names the timeout, in seconds", lambda: client.select("ideas"), "timed out after")

# THE STORAGE QUIRK, measured 2026-09-10 on the real project: Storage answers a missing
# bucket with HTTP 400 and puts the real code, 404, in the body as a string. Before this was
# handled, bucket_exists() asked for allow_404 and never got one, so an ordinary "not created
# yet" arrived as a hard failure on exactly the workspace verify() exists to diagnose.
wire(FakeResponse(400, {"statusCode": "404", "error": "Bucket not found",
                        "message": "Bucket not found", "code": "NoSuchBucket"}))
ok("a missing bucket reads as absent, not as a crash — Storage sends 400 with 404 in the body",
   client.bucket_exists("knowledge") is False)

# Live 2026-09-10: uploading into the missing bucket said "Supabase has no such address,
# check the project URL in the Connections tab" -- which sends a person to check the one
# thing that was right. The bucket is made by schema.sql and by nothing else.
wire(FakeResponse(400, {"statusCode": "404", "error": "Bucket not found",
                        "message": "Bucket not found", "code": "NoSuchBucket"}))
raises("uploading into a missing bucket blames the missing bucket, not the project URL",
       lambda: client.upload("knowledge", "pack/7.zip", b"x"), "no file cupboard yet", TableMissing)

# Live 2026-09-10, the same mistake in the other direction: a rejected personal access token
# was answered with "copy the key that starts with sb_publishable_", sending the person off to
# re-paste a key that was never the problem. There are two credentials; one message cannot
# serve both.
wire(FakeResponse(401, {"message": "Unauthorized"}))
try:
    schema.run_sql("someref", "sbp_wrong", "select 1")
    ok("a rejected access token raises", False)
except WorkspaceError as e:
    ok("a rejected ACCESS TOKEN points at the tokens page, not at the API keys page",
       "account/tokens" in str(e) and "sb_publishable_" not in str(e), str(e))
wire(FakeResponse(200, {"id": "knowledge"}))
ok("a bucket that is there reads as present", client.bucket_exists("knowledge") is True)


# ---- 5. verify(): the only function allowed to say it worked -----------------------------------
print("\n5. verify() — the single most important function in the package")


def project(tables=schema.TABLES, bucket=True, workspace_row=True, refuse=()):
    """A fake Supabase project: which tables exist, whether the bucket does, what refuses."""
    def answer(method, url, params, body):
        # THE CUPBOARD IS PROVED BY A ROUND TRIP, NOT BY READING THE BUCKET'S RECORD, so the fake
        # answers object endpoints. A publishable key cannot read storage.buckets even when the
        # bucket is fine, which is the bug this shape exists because of (2026-09-09).
        if "/storage/v1/object/" in url:
            if not bucket:
                return FakeResponse(400, {"statusCode": "403", "message":
                                          "new row violates row-level security policy"})
            return FakeResponse(200, {"Key": url.rsplit("/storage/v1/object/", 1)[-1]})
        if "/storage/v1/bucket" in url:
            # The old door. Left answering "not found" on purpose: nothing may depend on it again.
            return FakeResponse(400, {"statusCode": "404", "message": "Bucket not found"})
        name = url.rsplit("/rest/v1/", 1)[-1]
        if name in refuse:
            return FakeResponse(403, {"message": "new row violates row-level security policy"})
        if name not in tables:
            return FakeResponse(404, {"code": "PGRST205", "message":
                                      "Could not find the table 'public.%s' in the schema cache" % name})
        if name == "workspace" and params.get("limit") == 1:
            return FakeResponse(200, [{"id": "ws-abc", "schema_version": schema.SCHEMA_VERSION,
                                       "name": "Team workspace", "pack_version": 0,
                                       "index_version": 0, "bucket_ready": bucket}]
                                if workspace_row else [])
        return FakeResponse(200, [])
    return answer


route(project())
seen = schema.verify(URL, KEY)
ok("a complete workspace verifies", seen["ok"] is True, seen["reason"])
ok("it names every table it saw", sorted(seen["present"]) == sorted(schema.TABLES))
ok("it reads the workspace id back out of the database, never invents one",
   seen["workspace_id"] == "ws-abc")
ok("it reads the schema version back too", seen["schema_version"] == schema.SCHEMA_VERSION)
probed = [c["url"].rsplit("/rest/v1/", 1)[-1] for c in WIRE.calls if "/rest/v1/" in c["url"]]
ok("it probed every expected table by name, one at a time",
   all(t in probed for t in schema.TABLES), probed)
ok("it probed with the publishable key, which is the point of probing this way",
   all(c["headers"].get("apikey") == KEY for c in WIRE.calls))
ok("it never touched the OpenAPI root, which is admin-only and would prove the wrong thing",
   not any(c["url"].rstrip("/").endswith("/rest/v1") for c in WIRE.calls))
ok("the table probes cost nothing — limit=0 asks for no rows",
   all(c["params"].get("limit") == 0 for c in WIRE.calls
       if "/rest/v1/" in c["url"] and c["params"].get("limit") is not None
       and not c["params"].get("select", "").startswith("id,")))

route(project(tables=()))
seen = schema.verify(URL, KEY)
ok("an empty project is not ready, and says nothing has been created yet",
   seen["ok"] is False and "nothing has been created" in seen["reason"].lower(), seen["reason"])
ok("and it does not raise — an un-built workspace is a finding, not a crash",
   sorted(seen["missing"]) == sorted(schema.TABLES))

route(project(tables=[t for t in schema.TABLES if t != "changes"]))
seen = schema.verify(URL, KEY)
ok("one missing table means not ready, and the message names it",
   seen["ok"] is False and "changes" in seen["reason"], seen["reason"])
ok("and it says running the script again is safe", "again is safe" in seen["reason"])

# THE BUCKET COUNTS. A workspace with ten tables and no bucket is one nobody can ever join.
route(project(bucket=False))
seen = schema.verify(URL, KEY)
ok("ten tables and no knowledge bucket is NOT ready",
   seen["ok"] is False and seen["bucket"] is False)
ok("and the reason says why it matters: no teammate could download the pack",
   "no teammate could download" in seen["reason"].lower(), seen["reason"])

route(project(refuse=("ideas",)))
seen = schema.verify(URL, KEY)
ok("a table that exists but refuses this key is NOT counted as present",
   seen["ok"] is False and "ideas" not in seen["present"] and "ideas" in seen["unreadable"])

route(project(workspace_row=False))
seen = schema.verify(URL, KEY)
ok("tables but no workspace row is not ready either",
   seen["ok"] is False and "workspace row is missing" in seen["reason"], seen["reason"])

store.save_connections({})
seen = schema.verify()
ok("verify with nothing connected reports it plainly instead of raising",
   seen["ok"] is False and "nothing to check" in seen["reason"])
connect()

# ---- ready(): the same question, one call instead of eleven ------------------------------------
#
# The Connections tab polls about once a second. verify() is eleven calls, so a poll cannot use
# it. ready() can, because schema.sql creates the tables in ONE TRANSACTION -- a readable
# workspace row proves the other nine exist -- and records the one piece that is allowed to fail
# on its own, the bucket, in workspace.bucket_ready.
route(project())
quick = schema.ready(URL, KEY)
ok("ready() answers the resting-state question in ONE round trip",
   quick["ok"] is True and len(WIRE.calls) == 1, len(WIRE.calls))
ok("and it is that one call, on the workspace table",
   WIRE.calls[0]["url"].endswith("/rest/v1/workspace"))
ok("it never probes the other tables, and never touches Storage",
   not any("/storage/" in c["url"] for c in WIRE.calls))
ok("it hands back the id, the name, the schema version and the pack version",
   quick["workspace_id"] == "ws-abc" and quick["workspace_name"] == "Team workspace"
   and quick["schema_version"] == schema.SCHEMA_VERSION and "pack_version" in quick)
ok("and it LABELS ITSELF shallow, so nobody mistakes it for a verification",
   quick["checked"] == "shallow")
ok("while verify() labels itself full", schema.verify(URL, KEY)["checked"] == "full")

route(project(tables=()))
quick = schema.ready(URL, KEY)
ok("ready() on an un-built project says so, in one call and without raising",
   quick["ok"] is False and "has not been created yet" in quick["reason"]
   and len(WIRE.calls) == 1)

route(project(bucket=False))
quick = schema.ready(URL, KEY)
ok("ready() catches the bucket, because schema.sql RECORDS it rather than leaving it inferred",
   quick["ok"] is False and quick["bucket"] is False
   and "knowledge bucket is not" in quick["reason"], quick["reason"])

route(project(workspace_row=False))
ok("ready() on tables with no workspace row is not ready",
   schema.ready(URL, KEY)["ok"] is False)

store.save_connections({})
ok("ready() with nothing connected reports it rather than raising",
   schema.ready()["ok"] is False)
connect()

# THE RULE THAT MAKES IT SOUND, asserted rather than assumed: if the tables were NOT created
# atomically, a readable workspace row would prove nothing about the other nine and this whole
# function would be a lie. Section 2 asserts the one-transaction property; this ties the two
# together so that removing the transaction breaks this too.
ok("ready() is only sound because the tables are created in one transaction",
   CODE.count(" begin; ") == 1 and CODE.count(" commit; ") == 1)
# THE CONTRACT: ready() may never be how a workspace is reported ready for the FIRST time,
# because bucket_ready is a record of what happened at creation and not an observation of what
# is true now. So the three first-time paths must call verify() and must not call ready().
_SCHEMA_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "workspace", "schema.py"), encoding="utf-8").read()
for _fn in ("create", "confirm", "join"):
    _body = _SCHEMA_SRC.split("\ndef %s(" % _fn, 1)[1].split("\ndef ", 1)[0]
    ok("%s() decides with verify(), never with the shallow check" % _fn,
       "verify(" in _body and "ready(" not in _body)


# ---- 6. create(): two routes, and a token that never touches the disk ---------------------------
print("\n6. create() — two routes, and where the token does NOT go")

ok("project_ref reads the ref out of the project URL",
   schema.project_ref(URL) == "vxhxlgtmbuajgwlvhecu")
ok("and accepts a bare ref pasted on its own",
   schema.project_ref("vxhxlgtmbuajgwlvhecu") == "vxhxlgtmbuajgwlvhecu")
raises("and refuses something that is not a project URL",
       lambda: schema.project_ref("my project"), "supabase project url")
ok("the SQL Editor link points at this project's new-query page",
   schema.editor_url("vxhxlgtmbuajgwlvhecu")
   == "https://supabase.com/dashboard/project/vxhxlgtmbuajgwlvhecu/sql/new")

raises("create refuses a secret key outright, before any call goes out",
       lambda: schema.create(URL, "sb_secret_abcdefghij"), "only ever uses the publishable key")
raises("create refuses a personal access token pasted into the key box",
       lambda: schema.create(URL, "sbp_abcdefghijklmnop"), "only ever uses the publishable key")

# No token: straight to route 2, with the reason and the whole script.
route(project(tables=()))
result = schema.create(URL, KEY)
ok("with no token, create offers the paste route rather than failing",
   result["route"] == "paste" and result["ok"] is False)
ok("the paste route carries the reason", "no access token" in result["reason"].lower())
ok("the paste route carries the script itself, as a person reads it and not as the repo keeps it",
   result["sql"] == schema.paste_sql() and "begin;" in result["sql"])
ok("and the SQL Editor link for this exact project",
   result["editor_url"].endswith("/vxhxlgtmbuajgwlvhecu/sql/new"))
ok("and tells the person what to do next", "paste" in result["next"].lower())

# Route 1's failure. LIVE-PROVED, 2026-09-10: POSTing to the real management API with a bad
# token answers 401 {"message":"Unauthorized"}, which is the body used here.
FAKE_TOKEN = "sbp_thisisafaketokenusedonlybythissuite000000"


def management(fail_with=None, tables_after=schema.TABLES, bucket_after=True):
    """A project that starts EMPTY and becomes whatever tables_after says once the script runs.

    Starting empty matters: create() verifies before it does anything, so a fake that was
    already complete would take the "already set up" branch and the happy path would never be
    exercised at all. That is exactly what happened the first time this was written.
    """
    state = {"ran": False}
    before, after = project(()), project(tables_after, bucket_after)

    def answer(method, url, params, body):
        if "api.supabase.com" in url:
            if fail_with is not None:
                return fail_with
            state["ran"] = True
            return FakeResponse(201, [{"verdict": "Workspace ready. Copy the workspace id above into Sutra."}])
        return (after if state["ran"] else before)(method, url, params, body)
    return answer


route(management(fail_with=FakeResponse(401, {"message": "Unauthorized"}),
                 tables_after=()))
result = schema.create(URL, KEY, token=FAKE_TOKEN)
ok("a rejected token falls back to the paste route automatically",
   result["route"] == "paste" and result["ok"] is False)
ok("and the fallback shows WHY route 1 could not be used",
   "could not run the setup" in result["reason"].lower(), result["reason"])
ok("and still carries the script, so the person is never stuck",
   result["sql"] == schema.paste_sql() and "commit;" in result["sql"])

# THE HAPPY PATH. STUB-PROVED, NOT LIVE-PROVED: no Supabase personal access token existed on
# this machine when this was written, so the management API's 2xx has never been seen for real.
# See design/HANDOFF-W1.md for the live proof still to run.
route(management())
result = schema.create(URL, KEY, token=FAKE_TOKEN)
ok("[STUB-PROVED, NOT LIVE-PROVED] a token that works creates the workspace",
   result["ok"] is True and result["route"] == "seamless", result.get("reason"))
sent = [c for c in WIRE.calls if "api.supabase.com" in c["url"]]
ok("the script is POSTed to the management API for this project",
   len(sent) == 1 and sent[0]["url"].endswith("/projects/vxhxlgtmbuajgwlvhecu/database/query"))
ok("the whole script goes, verbatim, as the query", sent[0]["json"] == {"query": schema.sql()})
ok("the token is sent as a bearer header and nowhere else",
   sent[0]["headers"].get("Authorization") == "Bearer " + FAKE_TOKEN
   and FAKE_TOKEN not in json.dumps(sent[0]["json"]))
ok("success is reported only after verify read the tables back",
   any("/rest/v1/workspace" in c["url"] for c in WIRE.calls))
ok("the workspace id came from the database, not from the app", result["workspace_id"] == "ws-abc")
ok("and it was remembered", store.connections().get("workspace_id") == "ws-abc")

# THE MOST IMPORTANT CHECK IN THIS FILE. WORKSPACE-PLAN section 4: the token is used once and
# never written to disk. Not connections.json, not a cache, not a log. Search everything.
hits = []
for root, _dirs, files in os.walk(store.data_dir()):
    for name in files:
        path = os.path.join(root, name)
        try:
            with open(path, "rb") as f:
                if FAKE_TOKEN.encode() in f.read():
                    hits.append(path)
        except OSError:
            pass
ok("the personal access token is nowhere in the data directory afterwards", not hits, hits)
ok("and nowhere in connections.json in particular",
   FAKE_TOKEN not in json.dumps(store.connections()))
ok("connections.json holds only the three public things",
   all(k in store.connections() for k in ("workspace_url", "workspace_key", "workspace_id"))
   and not any(str(v).startswith("sbp_") for v in store.connections().values()))

# A 200 from the management API is still not success. This is the bar from section 10.
route(management(tables_after=[t for t in schema.TABLES if t != "pages"]))
result = schema.create(URL, KEY, token=FAKE_TOKEN)
ok("a script that ran without error but left a table missing is NOT reported as success",
   result["ok"] is False and result["route"] == "paste")
ok("and the reason says the script ran but the workspace is incomplete",
   "ran but the workspace is not complete" in result["reason"], result["reason"])
ok("and names the table that is missing", "pages" in result["reason"])

route(management(bucket_after=False))
result = schema.create(URL, KEY, token=FAKE_TOKEN)
ok("a script that made the tables but not the bucket is NOT reported as success",
   result["ok"] is False, result.get("reason"))

route(project())
result = schema.create(URL, KEY)
ok("a project that is already set up is connected to, not rebuilt",
   result["ok"] is True and result["route"] == "already")

# ---- join ---------------------------------------------------------------------------------
route(project())
good_link = link.make_link(URL, KEY, "ws-abc")
result = schema.join(good_link, "Priya")
ok("joining a real workspace verifies it, then takes a seat",
   result["ok"] is True and result["route"] == "join", result.get("reason"))
ok("and the joiner is written into members BY THE ENGINE, not by the screen",
   any("/rest/v1/members" in c["url"] and c["method"] in ("POST", "PATCH") for c in WIRE.calls))
ok("and their name is remembered locally", store.connections().get("member_name") == "Priya")
ok("and the workspace name came down with it",
   store.connections().get("workspace_name") == "Team workspace")

route(project(tables=()))
result = schema.join(good_link, "Priya")
ok("joining a workspace that is not built refuses, and does NOT enrol anybody",
   result["ok"] is False
   and not any("/rest/v1/members" in c["url"] and c["method"] == "POST" for c in WIRE.calls))

route(project())
stale = link.make_link(URL, KEY, "ws-someone-elses")
result = schema.join(stale, "Priya")
ok("a link naming a different workspace than the project holds is refused",
   result["ok"] is False and "different workspace" in result["reason"], result.get("reason"))

raises("joining with a damaged link fails on the link, before any call goes out",
       lambda: schema.join("sutra1_!!!", "Priya"), "damaged")

# A members row that cannot be written must not cost somebody a working workspace.
def project_no_members(method, url, params, body):
    if "/rest/v1/members" in url and method in ("POST", "PATCH"):
        return FakeResponse(403, {"message": "new row violates row-level security policy"})
    return project()(method, url, params, body)

route(project_no_members)
result = schema.join(good_link, "Priya")
ok("a members row that will not write leaves the person connected anyway",
   result["ok"] is True and result["member"].get("ok") is False, result.get("member"))
ok("and says what went wrong with it rather than swallowing it",
   "error" in result["member"])

route(project())
result = schema.create(URL, KEY, member_name="Ravi")
ok("create enrols the CREATOR too, so the list is never empty on day one",
   any("/rest/v1/members" in c["url"] for c in WIRE.calls))

route(project())
result = schema.confirm(URL, KEY)
ok("the paste route's 'I've run it' button is judged by the same verify()",
   result["ok"] is True and result["route"] == "paste" and result["workspace_id"] == "ws-abc")
route(project(tables=()))
result = schema.confirm(URL, KEY)
ok("and it says no when the person has not actually run it yet", result["ok"] is False)


# ---- 7. migrations ------------------------------------------------------------------------------
print("\n7. migrations — without these, every future change breaks every existing workspace")

ok("SCHEMA_VERSION and the migration list agree",
   schema.SCHEMA_VERSION == 1 + len(schema.MIGRATIONS),
   "version %d, %d migrations" % (schema.SCHEMA_VERSION, len(schema.MIGRATIONS)))
ok("and the versions run 2, 3, 4 ... with no gap and no repeat",
   [m[0] for m in schema.MIGRATIONS] == list(range(2, schema.SCHEMA_VERSION + 1)),
   [m[0] for m in schema.MIGRATIONS])

# THE FIRST REAL MIGRATION. index_version can ONLY reach an already-created workspace this way:
# `create table if not exists` will not add a column to a table that already exists, so a
# workspace made before today would keep the torn-download race for ever without this.
real = [m for m in schema.MIGRATIONS if m[0] == 2]
ok("there is a migration that adds index_version", len(real) == 1)
if real:
    ok("it is idempotent, so running it against a workspace that already has the column is a no-op",
       "add column if not exists index_version" in real[0][2].lower())
    ok("it says what it does in words, for the person who has to paste it",
       "index" in real[0][1].lower() and len(real[0][1]) > 20, real[0][1])
    ok("it carries no begin/commit of its own — migration_sql wraps it",
       "begin;" not in real[0][2].lower() and "commit;" not in real[0][2].lower())
    ok("and it does not bump the version itself, so the bump can never be in a separate transaction",
       "schema_version" not in real[0][2].lower())
ok("a workspace created from today's schema.sql needs no migration at all",
   schema.pending(schema.SCHEMA_VERSION) == [])
ok("and one created before today gets exactly the missing steps",
   [m[0] for m in schema.pending(1)] == list(range(2, schema.SCHEMA_VERSION + 1)))

REAL_MIGRATIONS, REAL_VERSION = schema.MIGRATIONS, schema.SCHEMA_VERSION
schema.MIGRATIONS = [
    (2, "give library a word count",
     "alter table public.library add column if not exists word_count integer not null default 0;"),
    (3, "index the library by author",
     "create index if not exists library_actor_idx on public.library (actor);"),
]
schema.SCHEMA_VERSION = 3
try:
    ok("pending() returns the steps a workspace has not run, in order",
       [s[0] for s in schema.pending(1)] == [2, 3])
    ok("pending() on an up-to-date workspace returns nothing", schema.pending(3) == [])
    ok("pending() never offers a step this build of Sutra does not know about",
       [s[0] for s in schema.pending(0)] == [2, 3])

    step_sql = schema.migration_sql(schema.MIGRATIONS[0])
    ok("a migration is wrapped in its own transaction",
       step_sql.startswith("begin;") and step_sql.rstrip().endswith("commit;"))
    ok("and the version bump is INSIDE it, so the version can never be ahead of the change",
       "update public.workspace set schema_version = 2;" in step_sql
       and step_sql.index("word_count") < step_sql.index("schema_version = 2"))

    def migrating(version_now, fail_at=None):
        state = {"version": version_now}

        def answer(method, url, params, body):
            if "api.supabase.com" in url:
                query = (body or {}).get("query", "")
                bump = re.search(r"schema_version = (\d+)", query)
                if fail_at is not None and bump and int(bump.group(1)) == fail_at:
                    return FakeResponse(400, {"message": "syntax error"})
                if bump:
                    state["version"] = int(bump.group(1))
                return FakeResponse(201, [])
            if "/storage/v1/object/" in url:
                return FakeResponse(200, {"Key": "knowledge/probe"})
            if "/storage/v1/bucket" in url:
                return FakeResponse(400, {"statusCode": "404", "message": "Bucket not found"})
            name = url.rsplit("/rest/v1/", 1)[-1]
            if name not in schema.TABLES:
                return FakeResponse(404, {"code": "PGRST205", "message": "Could not find the table"})
            if name == "workspace" and params.get("limit") == 1:
                return FakeResponse(200, [{"id": "ws-abc", "schema_version": state["version"]}])
            return FakeResponse(200, [])
        return answer

    route(migrating(1))
    result = schema.migrate(URL, KEY, token=FAKE_TOKEN)
    ok("[STUB-PROVED, NOT LIVE-PROVED] migrate applies the missing steps in order",
       result["ok"] is True and result["applied"] == [2, 3], result.get("reason"))
    order = [re.search(r"schema_version = (\d+)", c["json"]["query"]).group(1)
             for c in WIRE.calls if "api.supabase.com" in c["url"]]
    ok("and sends them oldest first, never in whatever order a dict happened to be in",
       order == ["2", "3"], order)

    route(migrating(1, fail_at=2))
    result = schema.migrate(URL, KEY, token=FAKE_TOKEN)
    ok("a failing step stops the run there and says which one",
       result["ok"] is False and result["applied"] == [] and "step 2" in result["reason"].lower(),
       result.get("reason"))
    ok("and says the later steps were left unapplied", "unapplied" in result["reason"])

    route(migrating(3))
    result = schema.migrate(URL, KEY, token=FAKE_TOKEN)
    ok("an up-to-date workspace is left alone", result["ok"] is True and result["applied"] == [])
    ok("and no SQL was sent at all",
       not any("api.supabase.com" in c["url"] for c in WIRE.calls))

    route(migrating(1))
    result = schema.migrate(URL, KEY)
    ok("without a token, migrate offers the paste route", result["route"] == "paste")
    ok("carrying ONLY the missing steps, never the whole create script",
       "word_count" in result["sql"] and "create table if not exists public.ideas" not in result["sql"])
    ok("and naming the steps so a person knows what they are running",
       result["steps"] == [(2, "give library a word count"), (3, "index the library by author")])

    route(project(tables=()))
    result = schema.migrate(URL, KEY, token=FAKE_TOKEN)
    ok("migrate refuses to touch a workspace that is not complete",
       result["ok"] is False and result["route"] == "blocked", result.get("reason"))
finally:
    schema.MIGRATIONS, schema.SCHEMA_VERSION = REAL_MIGRATIONS, REAL_VERSION


# ---- 8. nothing in the package reaches for a forbidden route ------------------------------------
print("\n8. the package as a whole")

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")
sources = {}
for name in sorted(os.listdir(PKG)):
    if name.endswith(".py"):
        with open(os.path.join(PKG, name), encoding="utf-8") as f:
            sources[name] = f.read()

ok("no Postgres driver anywhere — the direct database route is IPv6-only and cannot work",
   not any(re.search(r"\b(import|from)\s+(psycopg2?|asyncpg|pg8000|sqlalchemy)\b", s)
           for s in sources.values()))
ok("nothing asks for the database password",
   not any("db_password" in s or "database_password" in s for s in sources.values()))
ok("only _common.py imports httpx — every call goes through the one door",
   [n for n, s in sources.items() if re.search(r"^import httpx", s, re.M)] == ["_common.py"],
   [n for n, s in sources.items() if re.search(r"^import httpx", s, re.M)])
ok("the token is only ever a parameter, never a stored setting",
   "sbp_" not in " ".join(client.SETTINGS) and "token" not in " ".join(client.SETTINGS))
ok("connections.json is the only place settings are kept, and store already keeps it 0600",
   "save_connections" in sources["client.py"])

print("\nthe two bugs the owner's first real run found")
# BOTH OF THESE SHIPPED GREEN AND BOTH WERE WRONG. They are the reason a live run was worth more
# than any number of stubbed ones. (2026-09-09)

# 1. bucket_exists asked whether the bucket's RECORD was readable, not whether a file could be
#    stored. Measured on his project: GET /storage/v1/bucket/knowledge -> 404 NoSuchBucket, while
#    upload, download, replace and delete all returned 200. The bucket was there the whole time;
#    a publishable key simply cannot read storage.buckets. verify() then called a working
#    workspace broken and sent him back to the setup script.
_bsrc = sources["client.py"]
_probe = _bsrc[_bsrc.index("def bucket_exists"):]
_probe = _probe[:_probe.index("\ndef ", 10)] if "\ndef " in _probe[10:] else _probe
# Assert on the CODE, not the docstring: the docstring quotes the old endpoint as evidence of
# what was measured, and it should keep doing so.
_body = _probe.split('"""', 2)[-1]
ok("the cupboard check writes a file rather than reading the bucket's record",
   "/storage/v1/object/" in _body and "/storage/v1/bucket/" not in _body, _body[:200])
ok("and the docstring still carries the measurement that proved it",
   "NoSuchBucket" in _probe and "200" in _probe)
ok("and it reads the file back, because an upload that 200s and cannot be read is not storage",
   _probe.count("request(") >= 3)
ok("and tidies the probe away without letting a failed tidy fail the check",
   "finally:" in _probe)

# 2. verify() believed PostgREST the first time it said a table was missing. His run created all
#    ten and was told five were absent seconds later: PostgREST answers from a cached schema, and
#    PGRST205 for "created a moment ago" is byte-identical to PGRST205 for "never existed".
ok("a missing table is re-asked before it is believed", bool(schema.CACHE_RETRY_WAITS))
ok("and the waits are short, so a healthy workspace is never delayed",
   sum(schema.CACHE_RETRY_WAITS) <= 6, schema.CACHE_RETRY_WAITS)
ok("the setup script tells PostgREST to reload rather than leaving it to chance",
   "notify pgrst" in schema.sql())
ok("and it does so AFTER commit, since a notify inside the transaction fires on commit anyway "
   "but a reader racing it would still see the old cache",
   schema.sql().index("notify pgrst") > schema.sql().index("commit;"))

print("\nthe pasted script is the SQL, not the essay about it")
# The owner opened the paste screen and asked why he was being shown 33,671 characters, most of
# them developer notes about bigserial races and why 45 MiB and not 40. Every word earns its place
# in the repo; none of it earns a place in front of somebody who was told this takes thirty
# seconds. (2026-09-10)
_full, _paste = schema.sql(), schema.paste_sql()
ok("the pasted script is far shorter than the file on disk",
   len(_paste) < len(_full) * 0.6, (len(_full), len(_paste)))
ok("and it is still ONE transaction, so it all works or none of it does",
   _paste.count("begin;") == 1 and _paste.count("commit;") == 1,
   (_paste.count("begin;"), _paste.count("commit;")))
# The stripping must never remove a statement. These are one line from each section of the file,
# so a change that eats a whole block fails here rather than on somebody's project.
for _needed in ("create table if not exists public.workspace", "create table if not exists public.changes",
                "create or replace function public.log_change", "create or replace trigger pages_changed",
                "alter table public.ideas       enable row level security", "create policy changes_read",
                "insert into storage.buckets", "create policy knowledge_replace",
                "as verdict"):
    ok("still there: %s" % _needed[:52], _needed in _paste)
ok("the header tells a person the two things they need to know",
   "Safe to run twice" in _paste and "whether the workspace is ready" in _paste)
ok("the one comment block a person actually reads is kept",
   "WHAT YOU SHOULD SEE WHEN THIS WORKS" in _paste)
# `bigserial` and `clock_timestamp()` are still in there — they are the COLUMN DEFINITION, which
# is SQL and must survive. What must not survive is the essay ABOUT them.
ok("the deep rationale is gone, while the column it describes stays",
   "id           bigserial   primary key" in _paste
   and "at           timestamptz not null default clock_timestamp()" in _paste
   and "THE RACE (found 2026-09-10)" not in _paste
   and "WHY 47185920 (45 MiB) AND NOT A ROUNDER 40" not in _paste,
   [w for w in ("THE RACE (found 2026-09-10)", "WHY 47185920 (45 MiB) AND NOT A ROUNDER 40")
    if w in _paste])
ok("the file on disk is untouched: stripping is a VIEW, never an edit",
   len(schema.sql()) == len(_full) and "bigserial" in schema.sql())
ok("and the paste route hands back the stripped version, not the file",
   schema.fallback("no token", url="https://abcdefghijklmnop.supabase.co")["sql"] == _paste)

print("\nStubbed wire, no network. Proves the link cannot carry a secret or any SQL, the retry "
      "rule is 5xx-and-dropped-connections only, verify() is the one voice that says 'ready', "
      "and a personal access token never reaches the disk.")
print("NOT proved here and NOT proved live: that the management API accepts schema.sql and "
      "that the publishable key can upload, download, update and delete in the knowledge "
      "bucket. Both need a Supabase access token. See design/HANDOFF-W1.md.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all workspace core checks passed")
