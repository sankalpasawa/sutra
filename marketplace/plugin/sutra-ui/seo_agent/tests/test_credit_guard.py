"""tests/test_credit_guard.py — the credit pre-flight at the top of run_research.

What this proves, and why each check is here rather than left to a live run.

Found 2026-09-09. The account was at minus seven cents. A research run started, did the free
keyword steps, reached the paid steps, could not pay, quietly swapped demo figures in for the real
numbers, and carried on for another twenty minutes to hand back an article built on estimates. The
owner: "why should it even go further if there is no DataForSEO? It is pointless, a very bad
experience." So the run now refuses at the top, before a single step starts.

Two rules the guard must not break, and both are checked here:

  * it FAILS OPEN. A balance that cannot be read, or a balance check that raises, lets the run
    proceed. The owner's connection drops several times a day and a blip must never be the reason
    he cannot write. The paid steps report their own failure loudly.
  * it is read ONCE per run, never per step, because reading the balance is itself an API call.

And one check that exists because of an older incident: an earlier version of the same guard, the
one in front of serp_advanced, named a constant that did not exist. The check threw, the throw was
swallowed, and the guard failed open with nobody the wiser until someone ran it. So the floor
constant is asserted to be real, and the refusal is proved by asserting NO CALL WENT OUT, not by
reading the returned message.
"""
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.tools import _index, _shared as sh, dfs, run_research
from seo_agent.research import _common as _c

llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text
_fixture.stub_voyage()
_fixture.stub_web()

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


# ---- the same ground test_research stands on: the fixture's pages, pinned and put back ----------
rec = store.knowledge("brand/company.json") or {}
rec.setdefault("brand", "Example")
rec.setdefault("domain", "example.com")
rec.setdefault("brand_oneliner", "Example — practitioner-led business programmes for founders and senior operators")
rec.setdefault("niche_definition", "executive education — programmes for operators, cohort learning, leadership practice")
rec.setdefault("about", "Practitioner-led programmes for people who already run things.")
store.save_knowledge("brand/company.json", rec)
if not sh.brand_file("persona.md"):
    store.save_knowledge("brand/persona.md",
        "# Personas\n\n| Persona | Who | Reads |\n|---|---|---|\n"
        "| **Founder / CEO** | runs a 50-500 person company | strategy pieces |\n"
        "| **Senior Operator** | COO / VP running a function | how-to and cases |\n\n"
        "## How to pick one per article\nStrategy -> Founder; role how-to -> Operator.\n")
_saved_index = store.knowledge("site_index.json")
store.save_knowledge("site_index.json", _fixture.SITE_INDEX)
_fixture.plant_content_database()
_index.build(sh.pages_with_bodies(), say=lambda *a, **k: None, reindex=True)

chat = store.new_chat("credit guard test")
events = []
def ctx_for(run):
    return {"chat_id": chat, "run_id": run, "step_id": "step-1", "emit": lambda **kw: events.append(kw)}

TOPIC = "Operator education (a buyer's guide)"
SAY = lambda *a, **k: None


def counting_balance(value):
    """dfs.balance replaced by a counter. box["n"] is how many times the balance was read."""
    box = {"n": 0}
    def bal():
        box["n"] += 1
        if isinstance(value, Exception):
            raise value
        return value
    dfs.balance = bal
    return box


def fresh_run(name):
    dfs._PAY.update({"at": 0.0, "ok": None})       # the process-wide can-pay cache, per test
    _fixture.DFS_CALLS.clear()
    return store.new_run(chat, name)


def paid_calls():
    return [c for c in _fixture.DFS_CALLS if "labs" in c[0] or "serp" in c[0]]


# ---- 1. the floor constant is real -------------------------------------------------------------
# The whole reason this check exists: the serp_advanced guard once named a constant that was not
# there, so the guard threw, the throw was swallowed, and it failed open silently.
print("\nthe floor constant")
ok("research/_common.py defines MIN_CREDITS", hasattr(_c, "MIN_CREDITS"))
ok("run_research resolves it at import, so a missing name breaks loudly",
   hasattr(run_research, "MIN_CREDITS"))
ok("it is one value, not two", run_research.MIN_CREDITS == _c.MIN_CREDITS)
ok("and it is a real dollar floor above zero",
   isinstance(run_research.MIN_CREDITS, (int, float)) and run_research.MIN_CREDITS > 0,
   run_research.MIN_CREDITS)
ok("the guard's other two names are real too",
   callable(getattr(dfs, "balance", None)) and callable(getattr(dfs, "demo_mode", None)))


# run_research now STOPS ONCE and asks how long the article should be, between the brief and the
# research conversation. Outside the loop there is nobody to answer, so this answers it the way
# loop._resume_words does and calls the tool straight back with the number.
def research(ctx, **kw):
    out = run_research.run(ctx, **kw)
    if isinstance(out, dict) and out.get("ask_words"):
        out = run_research.run(ctx, word_target=out["ask_words"]["suggested"])
    return out


# ---- 2. a healthy balance runs, and the balance is read exactly once ----------------------------
print("\na healthy balance runs, and is read once for the whole run")
_fixture.stub_dfs(balance=12.5)
run1 = fresh_run("healthy")
box = counting_balance(12.5)
_real_can_pay = dfs._can_pay
dfs._can_pay = lambda ttl=300.0: True     # dfs has its own per-call can-pay cache; silence it so
                                          # the count below is the pre-flight's read and nothing else
out1 = research(ctx_for(run1), topic=TOPIC, angle="what changes after")
dfs._can_pay = _real_can_pay
ok("the run finishes with no error", bool(out1.get("summary")) and not out1.get("error"), out1.get("error"))
ok("it wrote the brief", bool(store.load_artifact(chat, run1, "research.json")))
ok("it bought real numbers", len(paid_calls()) > 0, len(paid_calls()))
ok("the balance was read ONCE for the whole run, not once per step", box["n"] == 1, box["n"])
rs1 = store.load_artifact(chat, run1, "research.json") or {}
ok("and the run is not marked as demo data", rs1.get("demo_data") is False, rs1.get("demo_data"))


# ---- 3. below the floor refuses BEFORE anything is bought --------------------------------------
print("\nbelow the floor, the run refuses before it starts")
_fixture.stub_dfs(balance=-0.07)
run2 = fresh_run("broke")
out2 = run_research.run(ctx_for(run2), topic=TOPIC)
ok("nothing was bought: not one call went out", paid_calls() == [], _fixture.DFS_CALLS)
ok("nothing was bought at all, paid or free", _fixture.DFS_CALLS == [], _fixture.DFS_CALLS)
ok("not even the first step ran", store.load_artifact(chat, run2, "_work/world.json") is None)
ok("no brief was written", store.load_artifact(chat, run2, "research.json") is None)
ok("it comes back as a refusal", bool(out2.get("error")), out2)

err2 = out2.get("error") or ""
sum2 = out2.get("summary") or ""
print("\nthe refusal names what is missing and both ways out")
ok("it names what is missing: DataForSEO", "DataForSEO" in err2)
ok("it names the balance", "$-0.07" in err2 and "$-0.07" in sum2, (sum2, err2))
ok("it names the floor the run needs", "$%.2f" % run_research.MIN_CREDITS in err2)
ok("way out one: top up the account", "top up" in err2.lower())
ok("way out two: ask for it anyway, on placeholder numbers", "placeholder_numbers" in err2)
ok("it says the placeholder numbers would be marked as not real", "not real" in err2)
# owner, 2026-09-11: "it could simply have been 'not enough DataForSEO credits'". The refusal used to
# be a 70-word lecture ending "I will not guess at this", and the agent read it back paragraph and all.
ok("it leads with the owner's own words", err2.startswith("Not enough DataForSEO credits"), err2)
ok("and stays short: one line, not a lecture", len(err2.split()) <= 45, len(err2.split()))
ok("no em dashes on screen", "—" not in err2 and "—" not in sum2)


# ---- 4. the way out is explicit, never the default ----------------------------------------------
print("\nplaceholder_numbers is the only way past it")
run3 = fresh_run("placeholders on purpose")
out3 = research(ctx_for(run3), topic=TOPIC, angle="what changes after", placeholder_numbers=True)
ok("asked for explicitly, the run goes ahead", bool(out3.get("summary")) and not out3.get("error"), out3.get("error"))
rs3 = store.load_artifact(chat, run3, "research.json") or {}
ok("and every number in it is flagged as demo", rs3.get("demo_data") is True, rs3.get("demo_data"))
ok("the brief says why, naming the balance",
   any("balance at $-0.07" in n for n in (rs3.get("notes") or [])), rs3.get("notes"))
ok("the summary itself says none of the numbers are real",
   "no number here is real" in (out3.get("summary") or ""), out3.get("summary"))


# ---- 5. it fails OPEN, in both directions ------------------------------------------------------
print("\nfail open: an unreadable balance never stops a run")
_fixture.stub_dfs(balance=12.5)
run4 = fresh_run("balance check raises")
counting_balance(RuntimeError("api.dataforseo.com: connection reset"))
out4 = research(ctx_for(run4), topic=TOPIC, angle="what changes after")
ok("a balance check that RAISES lets the run proceed",
   bool(out4.get("summary")) and not out4.get("error"), out4.get("error"))
ok("and it proceeds LIVE, not on placeholders",
   (store.load_artifact(chat, run4, "research.json") or {}).get("demo_data") is False)
ok("real calls went out", len(paid_calls()) > 0, len(paid_calls()))

# the same matrix at the guard itself, so each answer is pinned on its own
run5 = fresh_run("preflight matrix")
ctx5 = ctx_for(run5)
def preflight(bal, placeholder=False):
    counting_balance(bal)
    return run_research._preflight(ctx5, False, placeholder, SAY)

ok("a balance of None proceeds", preflight(None)[0] is None)
ok("a balance that is not a number proceeds", preflight("no idea")[0] is None)
ok("a balance check that raises proceeds", preflight(ValueError("timeout"))[0] is None)
ok("exactly at the floor proceeds", preflight(run_research.MIN_CREDITS)[0] is None)
ok("a hair under the floor refuses", preflight(run_research.MIN_CREDITS - 0.01)[0] is not None)
ok("proceeding on a readable, healthy balance is not a demo run", preflight(12.5)[1] is False)
ok("refusing is the default, with no request to proceed", preflight(-0.07)[0] is not None)
ok("asked for it, the same balance proceeds as a demo run",
   preflight(-0.07, True)[0] is None and preflight(-0.07, True)[1] is True)


# ---- 6. no login at all refuses too, unless placeholders were asked for ------------------------
# Found live, 2026-09-17 (Devansh): a run said "no DataForSEO login" once, researched three times
# over 26 minutes on placeholder numbers, failed the thin-material guard each time with no further
# mention of DataForSEO, then sat waiting 17 hours. This used to be the demo path with no refusal
# at all -- the exact thing _preflight's own docstring says must not happen ("why should it even go
# further if there is no DataForSEO?"). Only the empty-balance branch ever acted on those words.
print("\nno DataForSEO login refuses too, before anything is bought")
_real_auth = dfs._auth
dfs._auth = lambda: None
box6 = counting_balance(12.5)
r6, demo6, note6 = run_research._preflight(ctx_for(fresh_run("no login")), False, False, SAY)
ok("it refuses", r6 is not None, r6)
ok("it names what is missing: DataForSEO login", "DataForSEO login" in (r6 or {}).get("error", ""), r6)
ok("it says none of the numbers would be real", "none of these numbers would be real" in (r6 or {}).get("error", ""), r6)
ok("way out one: connect it", "connect DataForSEO" in (r6 or {}).get("error", ""), r6)
ok("way out two: placeholder numbers, on purpose", "placeholder_numbers" in (r6 or {}).get("error", ""), r6)
ok("no credential value is anywhere in the refusal", "fixture-login" not in str(r6) and "fixture-password" not in str(r6), r6)
ok("it is not marked demo (it never ran)", demo6 is False, demo6)
ok("and it never spends an API call reading a balance there is no account for", box6["n"] == 0, box6["n"])

print("\n...and refuses before a single step runs, end to end")
run6 = fresh_run("no login, end to end")
out6 = research(ctx_for(run6), topic=TOPIC)
dfs._auth = _real_auth
ok("it comes back as a refusal", bool(out6.get("error")), out6)
ok("nothing was bought, paid or free", _fixture.DFS_CALLS == [], _fixture.DFS_CALLS)
ok("no brief was written", store.load_artifact(chat, run6, "research.json") is None)

# ---- 7. placeholder_numbers=True still runs with no login, exactly as before -------------------
print("\nasked for explicitly, no login still runs on placeholders")
dfs._auth = lambda: None
box7 = counting_balance(12.5)
run7a = fresh_run("no login, asked for placeholders")
r7, demo7, note7 = run_research._preflight(ctx_for(run7a), False, True, SAY)
ok("it does not refuse", r7 is None, r7)
ok("it says the numbers are demo", demo7 is True and "no number here is real" in note7, note7)
ok("still no balance call: there is no account to read one from", box7["n"] == 0, box7["n"])
run7b = fresh_run("no login, asked, end to end")
out7 = research(ctx_for(run7b), topic=TOPIC, placeholder_numbers=True)
dfs._auth = _real_auth
ok("the run goes ahead", bool(out7.get("summary")) and not out7.get("error"), out7.get("error"))
rs7 = store.load_artifact(chat, run7b, "research.json") or {}
ok("and it is on record as demo", rs7.get("demo_data") is True, rs7.get("demo_data"))

# ---- 8. a connected login is unaffected ---------------------------------------------------------
print("\na connected login runs exactly as before")
_fixture.stub_dfs(balance=12.5)          # restores a real dfs._auth (fixture-login/fixture-password)
run8 = fresh_run("connected")
out8 = research(ctx_for(run8), topic=TOPIC, angle="what changes after")
ok("no error", bool(out8.get("summary")) and not out8.get("error"), out8.get("error"))
ok("it bought real numbers", len(paid_calls()) > 0, len(paid_calls()))
rs8 = store.load_artifact(chat, run8, "research.json") or {}
ok("and it is not demo data", rs8.get("demo_data") is False, rs8.get("demo_data"))

# ---- 9. the thin-material message names placeholders when the run was on demo data -------------
# Chained to the live bug: a person on placeholder numbers who then hits the thin-material guard
# used to be told only "the write-up came back thin", with nothing connecting the two.
print("\nthe thin-material refusal names placeholders as the likely cause")
_fixture.stub_dfs(balance=12.5)
dfs._auth = lambda: None
_c.DOSSIER_MIN_WORDS = 10 ** 6            # forces the guard, the same way test_research.py does
run9 = fresh_run("thin on placeholders")
out9 = research(ctx_for(run9), topic=TOPIC, angle="what changes after", placeholder_numbers=True)
_c.DOSSIER_MIN_WORDS = 1500
dfs._auth = _real_auth
err9 = out9.get("error") or ""
ok("it still stops on thin material", "did not produce enough material" in (out9.get("summary") or ""), out9)
ok("and now names the cause: no DataForSEO login",
   "no DataForSEO login is connected" in err9, err9)


# ---- 7. a resume with everything already bought is never refused --------------------------------
# The guard asks "is there paid work left", not "is the balance healthy". A run whose paid steps are
# all on disk spends nothing, so refusing it would only stand between a person and the brief he has
# already paid for.
print("\na resume with nothing left to buy is not refused")
run7 = fresh_run("all bought already")
ctx7 = ctx_for(run7)
for name in run_research.PAID_STEPS:
    _c.save_work(ctx7, name, {"bought": True})
_c.save_work(ctx7, "curate", {"turns": [1]})
box7 = counting_balance(-0.07)
r7, demo7, _n7 = run_research._preflight(ctx7, False, False, SAY)
ok("nothing left to buy, so no refusal even at minus seven cents", r7 is None and demo7 is False)
ok("and the balance was not read at all", box7["n"] == 0, box7["n"])

missing = fresh_run("one step missing")
ctx8 = ctx_for(missing)
for name in run_research.PAID_STEPS:
    if name != "serp":
        _c.save_work(ctx8, name, {"bought": True})
_c.save_work(ctx8, "curate", {"turns": [1]})
counting_balance(-0.07)
ok("one paid step still to run brings the refusal straight back",
   run_research._preflight(ctx8, False, False, SAY)[0] is not None)
counting_balance(-0.07)
ok("redo always means paid work is ahead",
   run_research._preflight(ctx7, True, False, SAY)[0] is not None)


# ---- tidy up ------------------------------------------------------------------------------------
if not os.environ.get("KEEP_RUN"):
    shutil.rmtree(store.chat_dir(chat), ignore_errors=True)
if _saved_index is not None:
    store.save_knowledge("site_index.json", _saved_index)
print("\nStubbed model, wire and web. Proves the guard refuses before it spends, fails open, and reads once.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all credit guard checks passed")
