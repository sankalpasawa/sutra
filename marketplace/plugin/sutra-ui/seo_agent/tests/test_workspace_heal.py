"""The pack heal: a workspace with no pack, and a teammate who joined before it had one.

THE INCIDENT, 2026-09-11. The owner's workspace never received a knowledge pack: every publish
was refused at its last step. A teammate joined anyway. The join put him on the team -- his name
appeared on the owner's screen -- and then stopped, because there was nothing to download. Nothing
ever tried again, so his Knowledge tab stayed empty for good. The message he saw even promised
the pack "uploads by itself", which nothing did.

agents_api._ws_pack_heal makes that true from both ends, and this suite pins down when it acts
and, just as much, when it must NOT: a teammate must never become the team's source of truth,
a failing upload must not repeat every minute, and it must never race a create or a join.
"""
import os
import sys
import types

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

import agents_api as api                            # noqa: E402
from seo_agent.workspace import pack as real_pack   # noqa: E402
from seo_agent.workspace import sync as real_sync   # noqa: E402

FAILS = []
REAL_GET_JOB = api._ws_get_job


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


class Client:
    def __init__(self, version=0, boom=False):
        self.version, self.boom = version, boom

    def one(self, table, columns="*", **kw):
        if self.boom:
            raise RuntimeError("the network is down")
        return {"pack_version": self.version}


class Rebuilder:
    def __init__(self):
        self.asked, self.running, self.pending = [], False, False

    def request(self, reason=""):
        self.asked.append(reason)
        return "started"


def fresh(version=0, have=True, me="m1", first="m1", joined=None, job=None, boom=False):
    """One scenario: wipe the heal's memory and put a fake behind every door it knocks on."""
    api._ws_heal.update({"at": 0.0, "sent_at": 0.0, "fetched_at": 0.0, "busy": False, "last": ""})
    api._ws_rebuilder_ref[0] = None
    rb = Rebuilder()
    calls = {"join": 0, "catch_up": 0}

    def join(client, **kw):
        calls["join"] += 1
        if joined == "fail":
            raise RuntimeError("the download stopped half way")
        return {"replay_from": 7}

    def catch_up(client, replay_from=None):
        calls["catch_up"] += 1

    real_sync.catch_up = catch_up
    api._ws_rebuilder = lambda mods: rb
    api._ws_settings = lambda mods: {"member_id": me}
    api._ws_member_rows = lambda mods: [
        {"member_id": first, "joined_at": "2026-09-10T07:49:31+00:00"},
        {"member_id": "someone-else" if first == me else me, "joined_at": "2026-09-11T06:08:00+00:00"}]
    api._ws_get_job = lambda: job
    fake_pack = types.SimpleNamespace(core_ready=lambda kroot=None: have, join=join,
                                      PackIncomplete=real_pack.PackIncomplete)
    return {"pack": fake_pack, "client": Client(version, boom)}, rb, calls


def settle():
    t = api._workers.get("workspace-heal")
    if t is not None:
        t.join(3)


# ==========================================================================================
print("\nSEND: the Mac that made the workspace holds the knowledge, and the workspace has none")
mods, rb, calls = fresh(version=0, have=True, me="m1", first="m1")
ok("it asks for a pack", api._ws_pack_heal(mods, now=1000.0) == "send")
ok("through the rebuilder -- the same path Check for changes takes, not a second one",
   len(rb.asked) == 1, rb.asked)
ok("and downloads nothing", calls["join"] == 0)
ok("a second look inside the minute does nothing", api._ws_pack_heal(mods, now=1030.0) == "")
ok("after the minute but inside fifteen it does not send again: a failing send is 33 MB up "
   "and back, not a once-a-minute habit",
   api._ws_pack_heal(mods, now=1100.0) == "" and len(rb.asked) == 1, rb.asked)
ok("after fifteen minutes it tries again",
   api._ws_pack_heal(mods, now=1000.0 + 901) == "send" and len(rb.asked) == 2, rb.asked)

# ==========================================================================================
print("\nNOT SEND: a teammate never becomes the team's source of truth")
mods, rb, calls = fresh(version=0, have=True, me="m2", first="m1")
ok("a member who did not make the workspace sends nothing, however much they hold",
   api._ws_pack_heal(mods, now=1000.0) == "" and rb.asked == [])
mods, rb, calls = fresh(version=0, have=False, me="m1", first="m1")
ok("a creator with no knowledge has nothing to send",
   api._ws_pack_heal(mods, now=1000.0) == "" and rb.asked == [])

# ==========================================================================================
print("\nFETCH: a teammate who joined before there was a pack -- the incident itself")
mods, rb, calls = fresh(version=1, have=False, me="m2", first="m1")
ok("it fetches", api._ws_pack_heal(mods, now=1000.0) == "fetch")
settle()
ok("the pack is downloaded exactly once", calls["join"] == 1, calls)
ok("and the log is caught up after it, from where the pack stops", calls["catch_up"] == 1, calls)
ok("the screen can say it arrived", "arrived" in api._ws_heal["last"], api._ws_heal["last"])
ok("and the heal is free again", api._ws_heal["busy"] is False)
ok("nothing is sent from a Mac that is receiving", rb.asked == [])

mods, rb, calls = fresh(version=1, have=False, joined="fail")
api._ws_pack_heal(mods, now=1000.0)
settle()
ok("a download that fails says so in words, and never raises into the poll",
   "did not come down" in api._ws_heal["last"] and api._ws_heal["busy"] is False,
   api._ws_heal["last"])
ok("...then waits five minutes rather than hammering", api._ws_pack_heal(mods, now=1120.0) == "")
ok("...then tries again", api._ws_pack_heal(mods, now=1000.0 + 301) == "fetch")
settle()

# ==========================================================================================
print("\nNOTHING TO DO")
mods, rb, calls = fresh(version=1, have=True)
ok("a Mac with the pack, on a workspace with one: nothing happens",
   api._ws_pack_heal(mods, now=1000.0) == "" and rb.asked == [] and calls["join"] == 0)

# ==========================================================================================
print("\nNEVER RACES THE THING IT IS HEALING")
mods, rb, calls = fresh(version=1, have=False, job={"kind": "join", "phase": "download"})
ok("a join in progress is left alone",
   api._ws_pack_heal(mods, now=1000.0) == "" and calls["join"] == 0)
mods, rb, calls = fresh(version=0, have=True, job={"kind": "create", "phase": "pack"})
ok("a create that is uploading is left alone",
   api._ws_pack_heal(mods, now=1000.0) == "" and rb.asked == [])
mods, rb, calls = fresh(version=0, have=True, job={"kind": "join", "phase": "failed"})
ok("a job that has FINISHED does not block it", api._ws_pack_heal(mods, now=1000.0) == "send")
mods, rb, calls = fresh(version=0, have=True)
busy = Rebuilder()
busy.running = True
api._ws_rebuilder_ref[0] = busy
ok("a rebuild already running is left alone",
   api._ws_pack_heal(mods, now=1000.0) == "" and rb.asked == [])
mods, rb, calls = fresh(version=0, have=True, boom=True)
ok("a network that is down is a quiet nothing, never an exception",
   api._ws_pack_heal(mods, now=1000.0) == "")

# ==========================================================================================
print("\nJOINING BEFORE THERE IS A PACK FINISHES ON THE TEAM, NOT AS A FAILURE")


class JoinClient:
    def save_settings(self, **kw):
        pass

    def one(self, table, columns="*", **kw):
        return {"name": "Team workspace"}

    def register_member(self, name, emoji=None, **kw):
        return {}


def refuse(client, **kw):
    raise real_pack.PackIncomplete("This workspace has not shared its knowledge yet. Nothing to "
                                   "do: it arrives on this Mac by itself.")


api._ws = lambda: {"schema": types.SimpleNamespace(verify=lambda url, key: {"ok": True,
                                                                           "workspace_id": "w1"}),
                   "pack": types.SimpleNamespace(join=refuse, PackIncomplete=real_pack.PackIncomplete),
                   "client": JoinClient(), "sync": types.SimpleNamespace()}
api._ws_get_job = REAL_GET_JOB
api._ws_heal.update({"at": 55.0, "fetched_at": 55.0})
api._ws_start_job("join")
api._ws_join_worker("https://x.supabase.co", "sb_publishable_x", "w1", "J", "m2", "")
job = api._ws_get_job() or {}
err = job.get("error") or {}
ok("the join finishes as DONE, not as 'Joining did not finish'", job.get("phase") == "done", job)
ok("...saying the person is on the team", "on the team" in (err.get("what") or ""), err)
ok("...and that there is nothing to press", "Nothing to do" in (err.get("do") or ""), err)
ok("and the heal is told to look straight away rather than waiting its turn",
   api._ws_heal["fetched_at"] == 0.0 and api._ws_heal["at"] == 0.0)

# ==========================================================================================
print("\nWIRED IN")
src = open(os.path.join(_ROOT, "agents_api.py"), encoding="utf-8").read()
i = src.index("def api_workspace(check")
route = src[i:src.index("@router.", i)]
ok("the workspace poll runs the heal", "_ws_pack_heal(mods)" in route)
ok("...inside a try, so the poll can never fail over it",
   route.index("try:\n        _ws_pack_heal(mods)") >= 0 if "try:\n        _ws_pack_heal(mods)" in route else False)
ok("and the poll reports what the heal is doing, so the screen is never silent about it",
   '"pack_heal": _ws_heal.get("last")' in route)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all heal checks passed")
