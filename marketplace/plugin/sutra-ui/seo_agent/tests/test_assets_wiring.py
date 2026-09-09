"""The asset engine's wiring: the gates, the id that travels beside a message, and the tick.

Not the methods themselves, which have their own suites. This is the plumbing between them and
the rest of the app, which is the part no single builder owns and so the part nothing else tests.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("SEO_AGENT_NO_CLI", "1")

from seo_agent.tests import _fixture
_fixture.setup()
_fixture.plant_brand_files()
from seo_agent import loop, registry, store  # noqa: E402
from seo_agent.assets import _common as acm  # noqa: E402
from seo_agent.tools import build_assets  # noqa: E402

P, F = 0, []


def ok(name, cond, detail=""):
    global P
    if cond:
        P += 1
        print("  PASS  %s" % name)
    else:
        F.append(name)
        print("  FAIL  %s %s" % (name, ("— %s" % (detail,))[:220]))



print("\nthe two shared tests live in ONE place")
import inspect  # noqa: E402
from seo_agent.assets import formats as _fm  # noqa: E402
src = inspect.getsource(_fm)
ok("a method calls the shared ownability test rather than writing its own",
   "ownability" in src and "def ownability" not in src)
ok("and the shared linkability test the same way",
   "linkability" in src and "def linkability" not in src)
ok("the keep-or-drop line is derived in code, never asked of the model",
   "verdict" in inspect.getsource(acm.linkability) and "LINKABILITY_FLOOR" in inspect.getsource(acm.linkability))

print("\nthe gate answer")
proposed = [{"domain": "adaface.com", "kind": "direct", "why": "same product"},
            {"domain": "vervoe.com", "kind": "direct", "why": "same product"}]
ok("accepting the list as proposed keeps its evidence",
   acm.parse_gate_answer("competitors", "Use this list", proposed) == proposed)
ok("a blank answer is an acceptance, not an empty list",
   acm.parse_gate_answer("competitors", "", proposed) == proposed)
edited = acm.parse_gate_answer("competitors", "- adaface.com\n- testgorilla.com", proposed)
ok("a rewritten list WINS over the proposal", [r.get("domain") for r in edited] == ["adaface.com", "testgorilla.com"], edited)
ok("a name the proposal already had keeps the evidence behind it",
   edited[0].get("why") == "same product", edited[0])
ok("a name the person added is taken at face value", edited[1] == {"domain": "testgorilla.com"}, edited[1])
ok("nobody asked and nobody kept anything are DIFFERENT", acm.gate_approved("competitors") is None)
acm.save_gate("competitors", [])
ok("...and once asked, keeping nothing reads as an empty list, not as unasked",
   acm.gate_approved("competitors") == [])

print("\nthe idea row")
rows = [dict(acm.blank_idea("a0001", "formats"), title="One", rank=2, status="open"),
        dict(acm.blank_idea("a0002", "trends"), title="Two", rank=1, status="open"),
        dict(acm.blank_idea("a0003", "trends"), title="Three", rank=None, status="open"),
        dict(acm.blank_idea("a0004", "trends"), title="Done one", rank=0, status="done")]
acm.save_ideas(rows)
ok("the chip offers the best-ranked idea that is still open", acm.next_open()["id"] == "a0002", acm.next_open())
ok("an idea that has been written is never offered again",
   all(r["id"] != "a0004" for r in [acm.next_open()]))
ok("an unranked idea sorts LAST, so it never jumps the queue",
   [r["id"] for r in sorted([r for r in rows if r["status"] == "open"],
                            key=lambda r: (r.get("rank") is None, r.get("rank") or 0))][-1] == "a0003")
ok("the counts are per status", acm.counts()["open"] == 3 and acm.counts()["done"] == 1, acm.counts())

print("\nticking: provenance only, never a guess")
chat = store.new_chat("t")
run = store.new_run(chat, "t")
store.save_artifact(chat, run, "draft.md", "# A title\n\nsome body text here\n")
store.patch_state(chat, run, idea_id="a0002", topic="A title")
out = loop.save_to_library(chat, run)
ok("the article saved", bool(out and out.get("item_id")), out)
ok("the run carried the idea id through to the library item",
   (store.library_get(out["item_id"]) or {}).get("idea_id") == "a0002")
ok("the idea it came from is ticked", acm.by_id("a0002")["status"] == "done")
ok("and the tick says WHICH article did it",
   acm.by_id("a0002")["built"]["library_id"] == out["item_id"])
ok("no other idea was touched", acm.by_id("a0001")["status"] == "open")

run2 = store.new_run(chat, "t2")
store.save_artifact(chat, run2, "draft.md", "# Typed by hand\n\nbody\n")
store.patch_state(chat, run2, topic="Typed by hand")     # no idea_id: the user typed his own
before = acm.counts()
loop.save_to_library(chat, run2)
ok("an article the user typed himself ticks NOTHING", acm.counts() == before, acm.counts())

print("\nthe registry and the driver")
tools = {t["name"]: t for t in registry.WORK_TOOLS}
ok("the engine is a work tool", "build_assets" in tools)
ok("it declares that it pauses, because it stops twice for a person", tools["build_assets"]["pauses"] is True)
ok("it costs no credits up front; the paid step guards itself", not tools["build_assets"].get("cost_credits"))
ok("its description tells the model when NOT to call it",
   "never" in tools["build_assets"]["description"].lower())
ok("the driver runs the three finders apart and merges once",
   build_assets.KEYS == ["scope", "competitors", "formats", "trends", "merge", "reuse"])
ok("status is cheap: it reads the sheet and calls no model",
   build_assets.status()["total"] == 4 and build_assets.status()["next"]["id"] == "a0001")

print("\nrefusing honestly")
os.remove(os.path.join(store.knowledge_dir(), "brand", "features.md"))
out = build_assets.run({"chat_id": chat, "run_id": run})
ok("with no brand pack it refuses rather than judging blind", bool(out.get("error")), out.get("summary"))
ok("and names both what is missing and what to do", "brand pack" in (out.get("error") or "").lower())


# ---- the gate, driven the whole way round ------------------------------------------------------
# A builder stops. The loop asks. The person answers. The engine picks up where it stopped. This is
# the path the owner cares about most and it crosses three files, so nothing else tests it.

print("\nthe gate, all the way round")
from seo_agent import registry as _reg  # noqa: E402
from seo_agent.tools import build_assets as _ba  # noqa: E402

_fixture.plant_brand_files()          # put features.md back; the refusal test above removed it
# ...and un-answer the gate: an earlier check saved an empty approval, which would make the
# builder below sail straight past the very thing this section exists to prove.
_gp = acm.path(acm.gate_path("competitors"))
if os.path.exists(_gp):
    os.remove(_gp)
ASKED = {"n": 0}


def _fake_run(co, say, redo=False):
    """A builder that wants the competitor list, then finishes once it has one."""
    approved = acm.gate_approved("competitors")
    if approved is None:
        ASKED["n"] += 1
        return {"gate": {"kind": "competitors", "builder": "competitors",
                         "question": "These are the fifteen I would study. Agree, or give me your own list.",
                         "why": "Studying the wrong companies costs fifteen paid pulls and a week.",
                         "proposed": [{"domain": "adaface.com", "kind": "direct", "why": "same product"}]}}
    acm.save("competitors.json", [dict(acm.blank_idea("a9001", "competitors"), title="From the study")])
    return {"files": ["competitors.json"], "needs_review": []}


_real_module = _ba._module
_ba._module = lambda name: (type("M", (), {"run": staticmethod(_fake_run)})
                            if name == "competitors" else _real_module(name))

chat2 = store.new_chat("gate")
run3 = store.new_run(chat2, "gate")
store.save_messages(chat2, [{"role": "user", "content": "work out what to write about"}])
out = _ba.run({"chat_id": chat2, "run_id": run3}, only="competitors")
ok("a builder that needs a person returns a gate and writes nothing", bool(out.get("gate")), out.get("summary"))
ok("the gate names which builder is waiting", out["gate"].get("builder") == "competitors")
ok("and says WHY it is worth stopping for", "costs" in out["gate"].get("why", ""))

loop._ask_asset_gate(chat2, run3, "call-1", out["gate"])
st = store.get_state(chat2, run3)
w = st.get("waiting_on") or {}
ok("the run is genuinely stopped, not running", st.get("status") == "waiting", st.get("status"))
ok("it waits as an ordinary question, so the screen already knows how to draw it",
   w.get("kind") == "question", w.get("kind"))
ok("what marks it as a gate is its own field, not the kind", w.get("asset_gate") == "competitors")
ok("the proposal is on the checkpoint, so a person can see it before answering",
   len(w.get("proposed") or []) == 1, w.get("proposed"))
ok("there is an option to decline", any("Not now" in (o.get("label") or "")
                                        for o in (w.get("options") or [])), w.get("options"))

before = ASKED["n"]
loop._resume_asset_gate(chat2, run3, w, store.get_messages(chat2), {"text": "Use this list"})
ok("answering files the approval where the builder will look", acm.gate_approved("competitors") is not None)
ok("the approved list kept the evidence behind the name",
   (acm.gate_approved("competitors") or [{}])[0].get("why") == "same product")
ok("the engine picked up where it stopped and did NOT ask again", ASKED["n"] == before, ASKED["n"])
ok("and it produced its file this time", acm.exists("competitors.json"))

_ba._module = _real_module

print("\n%d passed, %d failed" % (P, len(F)))
for n in F:
    print("  FAILED: %s" % n)
sys.exit(1 if F else 0)
