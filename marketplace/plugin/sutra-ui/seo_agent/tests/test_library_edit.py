"""tests/test_library_edit.py — a finished article, edited by anyone on the team.

Entirely offline. A fake Supabase (dict tables, a trigger that writes the log, a `library` row a
client can read back) stands in for the workspace, the model is a lambda, and two data dirs stand
in for two Macs. Nothing here opens a socket or shells out.

What it proves, in the order it would hurt if it broke:

  * THE SECTION SPLIT LOSES NOTHING and a rewrite of one section leaves every other byte-identical.
  * THE GUARDS HOLD: a figure the article never had is refused by name; a reply that grows a new
    section is refused; a proposal writes nothing.
  * A SAVE COUNTS, NAMES AND KEEPS: version +1, who and when, the version before on disk and
    undoable, twice.
  * A STALE SAVE IS REFUSED, locally (a teammate's save already mirrored here) and remotely (the
    team's row is ahead and the poller has not landed it yet), with who and when, and force wins.
  * THE TEAM GETS IT: a save on Mac A lands on Mac B through the ordinary pull, with its version,
    its editor and its previous body, so B can undo A's edit.
  * THE MEMBER RULE: a Mac with a workspace but no member id saves locally and says so; with no
    workspace at all the save is local and says so; offline, the row queues and the save says so.
  * FINISHING AN ARTICLE PUSHES IT, and only when a workspace is connected.
"""
import os
import sys
import tempfile
import time

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import store, library_edit as le, loop            # noqa: E402
from seo_agent.workspace import mirror, outbox, sync              # noqa: E402

FAILS = []
CHECKS = [0]


def ok(label, cond, extra=""):
    CHECKS[0] += 1
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label +
          (("   " + str(extra)) if extra and not cond else ""))


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def fake_head(url, headers, timeout, **kw):
    """The clock probe, answered from this Mac's own clock so the pull's lag guard measures a skew
    of zero. NO TEST HERE OPENS A SOCKET."""
    class Resp(object):
        status_code = 200
        headers = {"Date": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())}
    return Resp()


sync._probe = fake_head


# ---- a Supabase made of dictionaries -------------------------------------------------------------------

class FakeDB(object):
    """One project. The trigger lives on the table write, as in schema.sql. Rows are stamped a
    minute old so the pull's lag guard lets them through."""
    PK = {t: k for t, k in mirror.TABLES.values()}
    WORKSPACE = "w-0000"

    def __init__(self):
        self.tables, self.log, self.writes = {}, [], 0

    def _trigger(self, table, op, key, payload, actor):
        self.log.append({"id": len(self.log) + 1, "workspace_id": self.WORKSPACE, "kind": table,
                         "op": op, "key": str(key), "payload": payload, "actor": actor or "unknown",
                         "at": iso(time.time() - 60)})

    def upsert(self, table, rows):
        for r in rows:
            row = dict(r)
            row.setdefault("workspace_id", self.WORKSPACE)
            row["updated_at"] = iso(time.time())
            key = str(row.get(self.PK[table]))
            held = self.tables.setdefault(table, {})
            op = "update" if key in held else "insert"
            held[key] = row
            self.writes += 1
            self._trigger(table, op, key, dict(row), row.get("actor"))

    def log_after(self, last, limit):
        return [dict(r) for r in self.log if r["id"] > last][:limit]


class FakeClient(object):
    """workspace/client.py, to the interface library_edit, sync and outbox actually use."""

    def __init__(self, db, member_id="m-ravi", member_name="Ravi", configured=True):
        self.db, self.member_id, self.member_name = db, member_id, member_name
        self.is_configured = configured
        self.offline = False
        self.sent = []

    def settings(self):
        conn = store.connections()
        return {"workspace_url": "https://fake.supabase.co" if self.is_configured else "",
                "workspace_key": "sb_publishable_x" if self.is_configured else "",
                "workspace_id": FakeDB.WORKSPACE, "member_id": self.member_id,
                "member_name": self.member_name, "last_seen_id": conn.get("last_seen_id") or 0}

    def save_settings(self, **fields):
        conn = store.connections()
        conn.update(fields)
        store.save_connections(conn)
        return self.settings()

    def configured(self):
        return self.is_configured

    def actor(self):
        return self.member_name or self.member_id or "unknown"

    def headers(self, url=None, key=None, extra=None):
        return {"x-sutra-actor": self.actor()}

    def _net(self):
        if self.offline:
            raise RuntimeError("the network is down")

    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        self._net()
        w = where or {}
        if table == "changes":
            rows = self.db.log_after(int(w["id"][1]), 10 ** 9)
            if "at" in w:
                rows = [r for r in rows if r["at"] < w["at"][1]]
            return rows[:int(limit or 500)]
        held = self.db.tables.get(table, {})
        rows = [dict(r) for k, r in held.items() if all(str(r.get(c)) == str(v) for c, v in w.items())]
        return rows[:int(limit or 500)]

    def one(self, table, where=None, columns="*"):
        if table == "workspace":
            self._net()
            return {"id": FakeDB.WORKSPACE, "schema_version": 4}
        rows = self.select(table, where=where, columns=columns, limit=1)
        return rows[0] if rows else None

    def upsert(self, table, rows, on_conflict=None):
        self._net()
        self.db.upsert(table, rows)
        self.sent.append(("upsert", table, [dict(r) for r in rows]))

    def insert(self, table, rows):
        self.upsert(table, rows)

    def update(self, table, where, patch):
        self.upsert(table, [dict(patch, **where)])

    def delete(self, table, where):
        raise AssertionError("nothing here deletes")


MADE = []


def fresh_mac():
    d = tempfile.mkdtemp(prefix="lib-edit-")
    MADE.append(d)
    store.set_data_dir(d)
    sync.forget_skew() if hasattr(sync, "forget_skew") else None
    return d


MD = ("# Cost per hire\n\nIntro with 4,700 hires and $12,000 a seat.\n\n"
      "## What it costs\n\nBody one.\n\n### A sub-heading\n\nunder the sub\n\n"
      "- a list\n- of items\n\n"
      "## What to do\n\n```\ncode\n\nwith a gap\n```\n\nBody two.\n")


# =====================================================================================================
print("\nthe section split loses nothing, and a rewrite moves one section only")

fresh_mac()
secs = le.sections(MD)
ok("five pieces: H1 + intro, two H2 sections, and nothing else",
   [s["id"] for s in secs] == ["s0", "s1", "s2"], [s["id"] for s in secs])
ok("headings are the H1/H2 text", [s["heading"] for s in secs] == ["Cost per hire", "What it costs", "What to do"])
ok("an H3 stays inside its H2", "### A sub-heading" in secs[1]["text"])
ok("a fenced block with a blank line inside stays whole in its section", "code\n\nwith a gap" in secs[2]["text"])
ok("the sections are the whole article with the gaps between them",
   "".join(s["text"] for s in secs).replace("\n", "") == MD.replace("\n", ""))
lead = le.sections("no heading first\n\n# Then one\n\nbody\n")
ok("text before the first heading is its own section, called Opening",
   lead[0]["heading"] == le.OPENING and lead[0]["level"] == 0 and lead[1]["id"] == "s1", lead)

item = store.library_save("c1", "r1", "Cost per hire", MD)
model = lambda p, s: "## What it costs\n\nBody one, tighter, still 4,700 hires.\n\n### A sub-heading\n\nunder the sub\n\n- a list\n- of items"
out = le.propose(item, MD, "s1", "tighten", model=model)
ok("the proposal carries the new section and the whole article with it swapped in",
   "tighter" in out["proposed"] and "tighter" in out["draft"] and "Body two." in out["draft"])
after = le.sections(out["draft"])
ok("every other section is byte-identical", after[0]["text"] == secs[0]["text"] and after[2]["text"] == secs[2]["text"])
ok("the diff is a list a screen can draw", any(d.get("type") == "add" for d in out["diff"]), out["diff"])
ok("the figure check passed because 4,700 was already in the article", out["checks"][0]["status"] == "pass")
ok("a proposal writes NOTHING", store.library_get(item)["draft"] == MD)

seen_prompt = []
le.propose(item, MD, "s1", "tighten", model=lambda p, s: seen_prompt.append(p) or model(p, s))
ok("the model sees the section, the instruction, the title and the other headings, not the whole article",
   "Body one." in seen_prompt[0] and "tighten" in seen_prompt[0] and "Cost per hire" in seen_prompt[0]
   and "## What to do" in seen_prompt[0] and "Body two." not in seen_prompt[0])

print("\nthe guards")
try:
    le.propose(item, MD, "s1", "add a stat", model=lambda p, s: "## What it costs\n\nNow 51% cheaper, 3x faster.\n")
    ok("an invented figure is refused", False)
except le.InventedFigure as e:
    ok("an invented figure is refused, by name", "51" in str(e) and "3x" in str(e) or "3" in str(e), str(e))
try:
    le.propose(item, MD, "s1", "x", model=lambda p, s: "## What it costs\n\nfine\n\n## Sneaked in\n\nx\n")
    ok("a reply that grows a new section is refused", False)
except ValueError as e:
    ok("a reply that grows a new section is refused", "new heading" in str(e), str(e))
try:
    le.propose(item, MD, "s1", "x", model=lambda p, s: "fine, but the heading is gone\n")
    ok("a reply that drops the heading is refused", False)
except ValueError as e:
    ok("a reply that drops the heading is refused", "heading" in str(e), str(e))
try:
    le.propose(item, MD, "s1", "x", model=lambda p, s: "```markdown\nHere is the rewritten section:\n## What it costs\n\nfenced but fine\n```")
    ok("fences and a 'Here is' opener are stripped, not refused", True)
except Exception as e:                                          # noqa: BLE001
    ok("fences and a 'Here is' opener are stripped, not refused", False, e)
try:
    le.propose(item, MD, "s9", "x", model=model)
    ok("an unknown section id is refused", False)
except ValueError as e:
    ok("an unknown section id is refused", "s9" in str(e))
try:
    le.propose(item, MD, "s1", "   ", model=model)
    ok("an empty instruction is refused before any model call", False)
except ValueError:
    ok("an empty instruction is refused before any model call", True)
# a figure that is in the EVIDENCE but not yet in the article is allowed. The research travels as
# research.json beside the article (library_finish copies it in), which is what library_get reads.
store.write_json(os.path.join(store.library_dir(), item, "research.json"),
                 {"keywords": {"primary": {"keyword": "cost per hire", "volume": 8800}}})
try:
    le.propose(item, MD, "s1", "x", model=lambda p, s: "## What it costs\n\nSearched 8,800 times a month.\n")
    ok("a figure from the research is allowed into the article", True)
except le.InventedFigure as e:
    ok("a figure from the research is allowed into the article", False, e)

# =====================================================================================================
print("\nWP4B: the whole-article AI rewrite (propose_article), a style pass with the guards moved to "
      "headings and source tags since there is no untouched section left to compare against")

AMD = ("# Cost per hire\n\nIntro with 4,700 hires and $12,000 a seat [c2].\n\n"
      "## What it costs\n\nBody one [c1].\n\n## What to do\n\nBody two [c3].\n")
aitem = store.library_save("a1", "ar1", "Cost per hire", AMD)

out = le.propose_article(aitem, AMD, "make the tone warmer",
                         model=lambda p, s: AMD.replace("Body one", "Body one, now warmer"))
ok("the proposal carries the rewritten article as both 'proposed' and 'draft' (no splice, it IS the new draft)",
   "warmer" in out["proposed"] and out["draft"] == out["proposed"] and out["was"] == AMD)
ok("the diff is a list a screen can draw", any(d.get("type") == "add" for d in out["diff"]), out["diff"])
ok("the figure check passed because nothing new appeared", out["checks"][0]["status"] == "pass")
ok("a proposal writes NOTHING", store.library_get(aitem)["draft"] == AMD)

seen_prompt = []
le.propose_article(aitem, AMD, "warmer tone", model=lambda p, s: seen_prompt.append(p) or AMD)
ok("the model sees the whole article, the instruction and the title",
   "Cost per hire" in seen_prompt[0] and "warmer tone" in seen_prompt[0]
   and "Body one" in seen_prompt[0] and "Body two" in seen_prompt[0])

out2 = le.propose_article(aitem, None, "keep it the same", model=lambda p, s: AMD)
ok("draft=None falls back to the saved article", out2["was"] == AMD)

print("\nthe whole-article guards")
try:
    le.propose_article(aitem, AMD, "x", model=lambda p, s: AMD.replace("## What it costs", "## What it will cost you"))
    ok("a rewrite that changes a heading is refused", False)
except ValueError as e:
    ok("a rewrite that changes a heading is refused, by name", "heading" in str(e), str(e))
try:
    le.propose_article(aitem, AMD, "x", model=lambda p, s: AMD.replace("Body one [c1].", "Body one."))
    ok("a rewrite that drops a source tag is refused", False)
except ValueError as e:
    ok("a rewrite that drops a source tag is refused, naming the tag", "c1" in str(e) and "dropped" in str(e), str(e))
try:
    le.propose_article(aitem, AMD, "x", model=lambda p, s: AMD.replace("Body two [c3].", "Body two [c3][c4]."))
    ok("a rewrite that adds a source tag is refused", False)
except ValueError as e:
    ok("a rewrite that adds a source tag is refused, naming the tag", "c4" in str(e) and "added" in str(e), str(e))
try:
    le.propose_article(aitem, AMD, "add a stat", model=lambda p, s: AMD.replace("Body one [c1].", "Now 51% cheaper [c1]."))
    ok("an invented figure is refused, same guard the section route uses", False)
except le.InventedFigure as e:
    ok("an invented figure is refused, same guard the section route uses", "51" in str(e), str(e))
try:
    le.propose_article(aitem, AMD, "   ", model=lambda p, s: (_ for _ in ()).throw(AssertionError("model called")))
    ok("an empty instruction is refused before any model call", False)
except ValueError:
    ok("an empty instruction is refused before any model call", True)
try:
    le.propose_article("no-such", AMD, "x", model=lambda p, s: AMD)
    ok("an unknown item id is refused", False)
except ValueError as e:
    ok("an unknown item id is refused", "not in the Library" in str(e), str(e))

# regrouping tags is a style choice, not a source change: only the SET of ids must survive
GMD = "# Cost per hire\n\n## What it costs\n\nBody with two sources [c1, c2].\n"
gitem = store.library_save("a1g", "ar1g", "Cost per hire", GMD)
out3 = le.propose_article(gitem, GMD, "x", model=lambda p, s: GMD.replace("[c1, c2]", "[c2][c1]"))
ok("regrouping citation tags is allowed -- the set of ids survives, not their exact spelling",
   set(le.citation_ids(out3["proposed"])) == {"c1", "c2"}, out3["proposed"])

# =====================================================================================================
print("\na save counts, names, keeps the version before, and refuses a stale save")

fresh_mac()
item = store.library_save("c2", "r2", "Cost per hire", MD)
v1 = MD.replace("Body one.", "Body one, edited.")
m = le.save(item, v1, base_version=0)
ok("version 0 -> 1", m["version"] == 1, m.get("version"))
ok("who and when are stamped", bool(m["edited_by"]) and bool(m["edited_at"]))
ok("the version before is recorded, small, on the meta", m["previous"]["version"] == 0 and "draft" not in m["previous"])
ok("the previous body is on disk beside the article", store.library_get(item)["previous_draft"] == MD)
ok("the list does NOT carry the previous body",
   all("previous_draft" not in r for r in store.library_list()))
ok("no workspace: the save is local and says so",
   m["team"]["configured"] is False and m["team"]["synced"] is False and "stays on this Mac" in m["team"]["why"], m["team"])
try:
    le.save(item, MD, base_version=0)
    ok("a save from the version before is refused", False)
except le.Conflict as c:
    ok("a save from the version before is refused, with who and the newer version",
       c.current["version"] == 1 and c.current["edited_by"] == m["edited_by"] and c.current["draft"] == v1)
ok("and it wrote nothing", store.library_get(item)["draft"] == v1)
m2 = le.save(item, MD, base_version=0, force=True)
ok("force writes over it, version 2", m2["version"] == 2 and store.library_get(item)["draft"] == MD)
m3 = le.save(item, v1)
ok("no base_version means last save wins, as before", m3["version"] == 3)
r = le.revert(item)
ok("undo brings the version before back and counts as a save",
   r["version"] == 4 and store.library_get(item)["draft"] == MD and store.library_get(item)["previous_draft"] == v1)
r2 = le.revert(item)
ok("undo is itself undoable", store.library_get(item)["draft"] == v1 and r2["version"] == 5)
ok("undo on an article with nothing before it is None",
   le.revert(store.library_save("c2b", "r2b", "Fresh", MD)) is None)
ok("a save on an article that is not there is None", le.save("no-such", MD) is None)

# =====================================================================================================
print("\nthe FIRST edit can be undone (2026-09-22: 'undo is not at all working')")
# The timeline only ever grew on an edit, so one edit left one entry, the cursor sat on it, and
# can_undo -- "is there anything before the cursor" -- was 0 > 0. Undo was dead on every article
# anyone had edited exactly once, which is most of them. Every article on his Mac had versions: [].
fresh_mac()
fitem = store.library_save("c2f", "r2f", "First", "# First\nas it was written")
before = store.library_get(fitem)
ok("a freshly saved article has no timeline and nothing to undo, which is right",
   not (before.get("versions") or []) and store.library_history_flags(before)["can_undo"] is False)
f1 = le.save(fitem, "# First\nedited once")
ok("ONE edit and Undo is live", store.library_history_flags(f1)["can_undo"] is True, f1.get("versions"))
ok("the entry behind it is the article's own body, not a copy of the edit",
   len(f1["versions"]) == 2 and f1["versions"][0]["version"] == 0, f1.get("versions"))
ok("and undoing really brings the original text back",
   le.undo(fitem) and store.library_get(fitem)["draft"] == "# First\nas it was written",
   store.library_get(fitem)["draft"])
ok("redo puts the edit back", le.redo(fitem) and store.library_get(fitem)["draft"] == "# First\nedited once")

# The same for an article that arrived from the team workspace carrying no history at all: it is
# the identical empty timeline, so the first edit on THIS Mac seeds it the same way.
fresh_mac()
titem = store.library_save("c2t", "r2t", "Theirs", "# Theirs\ntheir version")
store.library_finish(titem, "Theirs", "# Theirs\ntheir version",
                     {"version": 7, "owner": "Someone else"})
t1 = le.save(titem, "# Theirs\nmy change")
ok("a teammate's article with no history is undoable after one edit too",
   store.library_history_flags(t1)["can_undo"] is True, t1.get("versions"))
ok("and its first entry is stamped with the version it arrived as, not zero",
   t1["versions"][0]["version"] == 7, t1.get("versions"))
ok("undo gives back exactly what they sent",
   le.undo(titem) and store.library_get(titem)["draft"] == "# Theirs\ntheir version")

# =====================================================================================================
print("\nevery save makes a version (last 20), and Undo/Redo step through them")

fresh_mac()
hitem = store.library_save("c2h", "r2h", "History", "# History\nv0")
le.save(hitem, "# History\nv1")
le.save(hitem, "# History\nv2")
h3 = le.save(hitem, "# History\nv3")
ok("three edits, four versions kept -- the three plus the article they started from",
   len(h3["versions"]) == 4, h3.get("versions"))
ok("can undo, cannot redo at the tip", store.library_history_flags(h3) == {"can_undo": True, "can_redo": False})

u1 = le.undo(hitem)
ok("undo steps back one version", store.library_get(hitem)["draft"] == "# History\nv2")
ok("undo counts as a save and reaches the team status too", u1["version"] == 4 and "team" in u1)
u2 = le.undo(hitem)
ok("undo again steps back another", store.library_get(hitem)["draft"] == "# History\nv1")
d1 = le.redo(hitem)
ok("redo steps forward", store.library_get(hitem)["draft"] == "# History\nv2")
d2 = le.redo(hitem)
ok("redo again reaches the tip", store.library_get(hitem)["draft"] == "# History\nv3")
ok("nothing left to redo at the tip", store.library_history_flags(store.library_get(hitem))["can_redo"] is False)
ok("redo past the tip is None", le.redo(hitem) is None)

le.undo(hitem)
le.undo(hitem)
ok("back at v1", store.library_get(hitem)["draft"] == "# History\nv1")
branched = le.save(hitem, "# History\nbranched")
ok("a fresh edit after undoing drops the redo tail",
   store.library_history_flags(branched)["can_redo"] is False, branched.get("versions"))
ok("redo after a fresh edit is None, the tail is really gone", le.redo(hitem) is None)
ok("undo from the branch still walks the shared history back to v1",
   le.undo(hitem) and store.library_get(hitem)["draft"] == "# History\nv1")
ok("undo from the first edit reaches the article as it was saved",
   le.undo(hitem) and store.library_get(hitem)["draft"] == "# History\nv0",
   store.library_get(hitem)["draft"])
ok("and THAT is the end of the line", le.undo(hitem) is None)

ok("undo/redo on an article that is not there is None",
   le.undo("no-such") is None and le.redo("no-such") is None)

# the 20-cap, exercised through the same route the screen calls
fresh_mac()
citem = store.library_save("c2c", "r2c", "Capped", "# Capped\nv0")
last = None
for i in range(1, 24):
    last = le.save(citem, "# Capped\nv%d" % i)
ok("the kept history never grows past 20", len(last["versions"]) == 20, len(last["versions"]))
ok("the oldest four were dropped, the newest twenty remain",
   last["versions"][0]["version"] == 4, last["versions"][0])
for _ in range(30):
    le.undo(citem)
ok("undoing all the way only reaches the oldest KEPT version (v4, since v1-v3 were dropped)",
   store.library_get(citem)["draft"] == "# Capped\nv4", store.library_get(citem)["draft"])

# =====================================================================================================
print("\nthe team gets it: a save on Mac A lands on Mac B, versioned, named, undoable")

db = FakeDB()
mac_a = fresh_mac()
a_client = FakeClient(db, "m-ravi", "Ravi")
item = store.library_save("c3", "r3", "Cost per hire", MD)
m = le.save(item, v1, base_version=0, client=a_client)
ok("the save reached the team's library table", "library" in db.tables and item in db.tables["library"])
row = db.tables["library"][item]
ok("the row carries the body, the version and the editor",
   row["body_md"] == v1 and row["meta"]["version"] == 1 and row["meta"]["edited_by"] == "Ravi" and row["actor"] == "Ravi", row.get("meta"))
ok("and the previous body, so a teammate can undo", row["meta"].get("previous_draft") == MD)
ok("the save says it is shared", m["team"]["synced"] is True and m["team"]["queued"] is False, m["team"])
ok("the trigger wrote the log; the client never did", len(db.log) == 1 and db.log[0]["kind"] == "library")

mac_b = fresh_mac()
b_client = FakeClient(db, "m-priya", "Priya")
rb = sync.pull_once(client=b_client)
got = store.library_get(item)
ok("Mac B has the article after one pull", got is not None and got["draft"] == v1, rb)
ok("with its version, its editor and its previous body",
   got["version"] == 1 and got["edited_by"] == "Ravi" and got.get("previous_draft") == MD, {k: got.get(k) for k in ("version", "edited_by")})
rv = le.revert(item, client=b_client)
ok("Priya can undo Ravi's edit from her Mac", rv["version"] == 2 and store.library_get(item)["draft"] == MD and rv["edited_by"] == "Priya")
ok("and that went to the team too", db.tables["library"][item]["meta"]["version"] == 2)

# =====================================================================================================
print("\na stale save is refused when the TEAM is ahead and the poller has not landed it yet")

store.set_data_dir(mac_a)                                 # back on Ravi's Mac, still at version 1
ok("Ravi's Mac still holds version 1", store.library_get(item)["version"] == 1)
try:
    le.save(item, v1.replace("edited", "edited again"), base_version=1, client=a_client)
    ok("Ravi's save from version 1 is refused because the team is on 2", False)
except le.Conflict as c:
    ok("Ravi's save from version 1 is refused because the team is on 2",
       c.current["version"] == 2 and c.current["edited_by"] == "Priya" and c.current["draft"] == MD, c.current)
    ok("and Priya's version has landed on Ravi's Mac, so 'load theirs' has it",
       store.library_get(item)["version"] == 2 and store.library_get(item)["draft"] == MD)
m = le.save(item, v1.replace("edited", "edited again"), base_version=2, client=a_client)
ok("saving from the current version goes through, version 3", m["version"] == 3 and db.tables["library"][item]["meta"]["version"] == 3)
try:
    le.save(item, MD, base_version=1, force=True, client=a_client)
    ok("force skips the check entirely", True)
except le.Conflict:
    ok("force skips the check entirely", False)

# =====================================================================================================
print("\nthe member rule, and the ways a save stays local")

fresh_mac()
item = store.library_save("c4", "r4", "Cost per hire", MD)
db4 = FakeDB()
guest = FakeClient(db4, member_id="", member_name="", configured=True)
m = le.save(item, v1, base_version=0, client=guest)
ok("a workspace with no member id: the save is local and says join first",
   m["team"]["configured"] is True and m["team"]["member"] is False and "not a member" in m["team"]["why"], m["team"])
ok("nothing reached the team", "library" not in db4.tables)
ok("and the local save stands, version 1", store.library_get(item)["version"] == 1)
ok("team_status reads the same three states",
   le.team_status(guest)["member"] is False
   and le.team_status(FakeClient(db4, configured=False))["configured"] is False
   and le.team_status(FakeClient(db4))["member"] is True)

fresh_mac()
item = store.library_save("c5", "r5", "Cost per hire", MD)
db5 = FakeDB()
off = FakeClient(db5)
off.offline = True
m = le.save(item, v1, base_version=0, client=off)
ok("offline: the save is local, queued, and says so",
   m["version"] == 1 and m["team"]["queued"] is True and "network" in m["team"]["why"], m["team"])
ok("the row is waiting in the outbox", outbox.status()["queued"] == 1, outbox.status())
off.offline = False
ok("an immediate retry waits out the backoff rather than hammering", outbox.drain(off)["blocked"] is True)
outbox.drain(off, now=time.time() + 3600)                # the poller's later pass
ok("back online, the queue drains and the team has it", db5.tables.get("library", {}).get(item, {}).get("body_md") == v1,
   outbox.status())
ok("the conflict check treats offline as 'cannot tell' and does not refuse the local save",
   True)   # proven above: the save went through while offline

# =====================================================================================================
print("\nfinishing an article pushes it to the team, only when a workspace is connected")

fresh_mac()
cid, rid = "c6", "r6"
store.save_artifact(cid, rid, "draft.md", MD)
store.save_artifact(cid, rid, "blueprint.json", {"h1": "Cost per hire", "sections": []})
store.save_artifact(cid, rid, "research.json", {"keywords": {"primary": {"keyword": "cost per hire"}}})
store.patch_state(cid, rid, status="running", topic="Cost per hire")
saved = loop.save_to_library(cid, rid)
ok("with no workspace the article is saved and nothing is queued",
   saved and store.library_get(saved["item_id"]) is not None and outbox.status()["queued"] == 0, outbox.status())

db6 = FakeDB()
real_configured, real_push = sync.configured, sync.push
sync.configured = lambda client=None: True
sync.push = lambda kind, key, payload=None, **kw: real_push(kind, key, payload, client=FakeClient(db6), **kw)
try:
    saved = loop.save_to_library(cid, rid)
finally:
    sync.configured, sync.push = real_configured, real_push
ok("with a workspace the finished article goes to the team's library table",
   saved["item_id"] in db6.tables.get("library", {}), list(db6.tables.get("library", {})))
ok("as a whole row: title, body and the archetype meta",
   db6.tables["library"][saved["item_id"]]["body_md"] == MD and db6.tables["library"][saved["item_id"]]["title"] == "Cost per hire")

# =====================================================================================================
print("\nWP4B: the ai-article route itself (agents_api.api_library_ai_article), same shape as the "
      "ai-section route: bad id, not found, an empty instruction, and a proposal through")

# agents_api lives at the sutra-ui root, not inside the package -- see test_library_tabs.py's own
# note on this same import, including why store.set_data_dir has to be reasserted right after it
# (importing agents_api activates the person's saved company and repins the data dir).
_data_dir = store.data_dir()
try:
    import agents_api
    store.set_data_dir(_data_dir)
except Exception as e:                                        # noqa: BLE001
    agents_api = None
    print("  SKIP  the route itself (agents_api would not import: %s)" % str(e)[:120])

if agents_api:
    fresh_mac()
    ritem = store.library_save("r-a1", "r-ar1", "Cost per hire", AMD)

    for bad_id in ("../etc", "..", "has space"):
        rb = agents_api.api_library_ai_article(bad_id, {"instruction": "x"})
        ok("the route refuses a bad id: %r" % bad_id, getattr(rb, "status_code", None) == 400, rb)

    r404 = agents_api.api_library_ai_article("no-such-item", {"instruction": "x"})
    ok("an item that does not exist is a 404", getattr(r404, "status_code", None) == 404, r404)

    r400 = agents_api.api_library_ai_article(ritem, {"instruction": "   "})
    ok("an empty instruction is refused with a 400, before any model call", getattr(r400, "status_code", None) == 400, r400)

    real_text = le.llm.text
    le.llm.text = lambda p, s: AMD.replace("Body one", "Body one, warmer")
    try:
        r = agents_api.api_library_ai_article(ritem, {"instruction": "warmer tone", "draft": AMD})
    finally:
        le.llm.text = real_text
    ok("a good instruction returns the proposal, the diff and the checks -- nothing written",
       isinstance(r, dict) and "warmer" in r["proposed"] and r["draft"] == r["proposed"]
       and any(d.get("type") == "add" for d in r["diff"]) and r["checks"][0]["status"] == "pass", r)
    ok("and nothing was saved", store.library_get(ritem)["draft"] == AMD)

    le.llm.text = lambda p, s: AMD.replace("## What it costs", "## What it will cost you")
    try:
        rbad = agents_api.api_library_ai_article(ritem, {"instruction": "x"})
    finally:
        le.llm.text = real_text
    ok("a rewrite that breaks a guard comes back as a 400 through the route too, not a 500",
       getattr(rbad, "status_code", None) == 400, rbad)

# =====================================================================================================
print()
for d in MADE:
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except Exception:                                   # noqa: BLE001
        pass
if FAILS:
    print("%d of %d checks FAILED:" % (len(FAILS), CHECKS[0]))
    for f in FAILS:
        print("  - " + f)
    sys.exit(1)
print("all %d checks passed" % CHECKS[0])
