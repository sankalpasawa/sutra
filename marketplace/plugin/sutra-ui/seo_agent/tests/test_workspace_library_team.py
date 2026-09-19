"""The team Library: shared once there is a draft, deleted only by whoever made it (2026-09-18).

What happened: one teammate updated, the Library backfill sent every row on her Mac, and nine rows
that held nothing ("continue", "Write a1007", every one titled "Writing…" and 0 words long) landed
in everybody's Library with a spinner that never stopped. Devansh asked for three things:
  * an article reaches the team the moment its draft exists, whether or not anyone marks it ready
  * nothing reaches the team before it has words
  * only the person who created an article can delete it, and then it goes for everyone
This suite proves each, through the real push -> queue -> drain chain with only the team's
project replaced by a fake in memory.
"""
import os
import shutil
import sys

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

from seo_agent import store, library_edit, loop
from seo_agent.workspace import outbox, sync

FAILS = []


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


class Team(object):
    """The team's project, as far as the Library goes, for one member."""

    def __init__(self, member_id="m-dev", name="Devansh"):
        self.library, self.deleted, self.member_id, self.name = {}, [], member_id, name

    def configured(self):
        return True

    def actor(self):
        return self.name

    def settings(self):
        return {"member_id": self.member_id, "member_name": self.name}

    def select(self, table, where=None, order=None, limit=None, columns="*", offset=None):
        return [{"item_id": k} for k in self.library]

    def one(self, table, where=None, columns="*"):
        return self.library.get(str((where or {}).get("item_id")), {})

    def upsert(self, table, rows, on_conflict=None):
        for r in rows:
            self.library[str(r["item_id"])] = dict(r)

    def delete(self, table, where):
        key = str((where or {}).get("item_id"))
        self.deleted.append(key)
        self.library.pop(key, None)


TEAM = Team()
sync._client = lambda client=None: client if client is not None else TEAM


def reset():
    # belt and braces on top of _fixture: this function deletes folders, so it checks where first
    live = os.path.realpath(os.path.expanduser("~/.sutra-ui"))
    assert not os.path.realpath(store.data_dir()).startswith(live), "refusing to reset a real install"
    TEAM.library.clear()
    TEAM.deleted[:] = []
    for item in outbox.pending():
        try:
            os.remove(item["_path"])
        except OSError:
            pass
    for d in (store.library_dir(), store.chats_dir()):
        if os.path.isdir(d):
            shutil.rmtree(d)


def run_with_draft(chat, run, draft="# The title\n\nThe first draft, with words in it."):
    os.makedirs(os.path.join(store.chats_dir(), chat), exist_ok=True)
    store.save_artifact(chat, run, "draft.md", draft)
    return store.library_item_id(chat, run)


# ---- nothing reaches the team before it has words ---------------------------------------------------
print("an empty row never reaches the team")
reset()
empty = store.library_start("c1", "r1", "continue", owner="Devansh", owner_id="m-dev")
got = sync.push("library", empty, store.library_get(empty), client=TEAM)
ok("the push refuses a row with no draft", got is None, got)
ok("and nothing was queued for it", outbox.count() == 0, outbox.count())
ok("so the team never sees it", empty not in TEAM.library, list(TEAM.library))
sync.backfill_library(client=TEAM, now=10_000.0)
ok("the backfill, which goes through the same door, cannot send it either", empty not in TEAM.library,
   list(TEAM.library))

# ---- the draft is shared the moment it exists --------------------------------------------------------
print("\nthe first draft is shared as a draft, without anyone marking it ready")
reset()
item = run_with_draft("c2", "r2")
store.library_start("c2", "r2", "write about cost per hire", owner="Devansh", owner_id="m-dev")
real_client = library_edit._client
library_edit._client = lambda client=None: client if client is not None else TEAM
try:
    loop._share_first_draft("c2", "r2")
finally:
    library_edit._client = real_client
row = store.library_get(item) or {}
ok("the row now holds the draft", "first draft" in (row.get("draft") or ""), row.get("draft"))
ok("as a draft, not ready", row.get("status") == "draft", row.get("status"))
ok("and the team has it", item in TEAM.library and "first draft" in TEAM.library[item]["body_md"],
   list(TEAM.library))
ok("with its owner on it", (TEAM.library.get(item, {}).get("meta") or {}).get("owner_id") == "m-dev",
   TEAM.library.get(item))
store.library_set_status(item, "ready")
store.save_artifact("c2", "r2", "draft.md", "# The title\n\nA later run draft.")
loop._share_first_draft("c2", "r2")
ok("a second share never overwrites a row that already has words",
   "first draft" in (store.library_get(item) or {}).get("draft", ""), store.library_get(item))
ok("nor moves it back from ready", (store.library_get(item) or {}).get("status") == "ready")

# ---- the owner is stamped once --------------------------------------------------------------------
print("\nthe owner is set once and never renamed")
reset()
item = store.library_start("c3", "r3", "x", owner="Aparna", owner_id="m-apa")
store.library_finish(item, "T", "words here", {"owner": "Devansh", "owner_id": "m-dev"}, chat_id="c3", run_id="r3")
m = store.library_get(item)
ok("a later save cannot change who made it", m.get("owner_id") == "m-apa" and m.get("owner") == "Aparna", m)

# ---- who may delete --------------------------------------------------------------------------------
print("\nonly the person who created an article may delete it")
reset()
mine = store.library_finish("run-cA-rA", "Mine", "words", {"owner": "Devansh", "owner_id": "m-dev"},
                            chat_id="cA", run_id="rA")["id"]
theirs = store.library_finish("run-cB-rB", "Theirs", "words", {"owner": "Aparna", "owner_id": "m-apa"},
                              chat_id="cB", run_id="rB")["id"]
legacy_here = store.library_finish("run-cC-rC", "Old, made here", "words", {}, chat_id="cC", run_id="rC")["id"]
os.makedirs(os.path.join(store.chats_dir(), "cC"), exist_ok=True)
legacy_away = store.library_finish("run-cD-rD", "Old, made elsewhere", "words", {}, chat_id="cD", run_id="rD")["id"]
g = store.library_get
ok("my own row is mine", store.library_is_mine(g(mine), "m-dev"))
ok("a teammate's row is not", not store.library_is_mine(g(theirs), "m-dev"))
ok("an old row whose chat is on this Mac is mine", store.library_is_mine(g(legacy_here), "m-dev"))
ok("an old row whose chat is elsewhere is not", not store.library_is_mine(g(legacy_away), "m-dev"))
ok("with no workspace, every row is mine", store.library_is_mine(g(theirs), ""))

TEAM.library.update({theirs: {"item_id": theirs}, mine: {"item_id": mine}})
out = library_edit.delete(theirs, client=TEAM)
ok("deleting a teammate's article is refused", out.get("ok") is False, out)
ok("with their name in the reason", "Aparna" in (out.get("error") or ""), out)
ok("and it is still here and still on the team", g(theirs) is not None and theirs in TEAM.library)
out = library_edit.delete(mine, client=TEAM)
ok("deleting my own works", out.get("ok") is True, out)
ok("it is gone from this Mac", g(mine) is None)
ok("and from the team, for everyone", mine in TEAM.deleted and mine not in TEAM.library, TEAM.deleted)

# ---- stalled rows ----------------------------------------------------------------------------------
print("\na writing row whose run is dead says so")
reset()
live = store.library_start("cL", "rL", "live one")
store.patch_state("cL", "rL", status="running")
dead = store.library_start("cF", "rF", "failed one")
store.patch_state("cF", "rF", status="failed")
gone = store.library_start("cG", "rG", "chat deleted")
rows = {r["id"]: r for r in store.library_list()}
ok("a running run is not stalled", rows[live]["stalled"] is False, rows[live])
ok("a failed run is", rows[dead]["stalled"] is True, rows[dead])
ok("a run with no state left is", rows[gone]["stalled"] is True, rows[gone])

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all team-library checks passed")
