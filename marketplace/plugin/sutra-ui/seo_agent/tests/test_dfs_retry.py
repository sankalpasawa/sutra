"""tests/test_dfs_retry.py — a bad moment at DataForSEO must not throw the research away.

Found 2026-09-15. Three research runs died within ten minutes on "DataForSEO task failed (40101):
Internal SE Server Error." The research conversation makes ~48 live searches; one of them hitting a
bad moment raised straight through pool.map, and everything the other researchers had found was
lost, because curate is only saved when the whole round finishes. A retry paid for it all again.

What this proves, with the wire faked (httpx) and the model and the web stubbed, never a real call:

  * dfs retries the codes DataForSEO calls temporary (40101 and friends, HTTP 5xx, timeouts) and
    never retries a real refusal (bad login, no money, bad parameters, HTTP 402);
  * a many-task call is never re-sent over one task's code, because that buys the rest twice;
  * in curate, one search that still fails is skipped and counted, not fatal;
  * if EVERY search fails, the round still fails loudly;
  * the conversation is kept turn by turn, and a resume does not buy the same searches again.
"""
import os
import shutil
import sys

import httpx

# THE SUITES SHARE ONE DATA FOLDER, so this one leaves it as it found it. _fixture.setup() plants a
# company record (domain example.com), a site index, traffic and a content database; left behind,
# the company record told test_workspace_ideas "this Mac's company is example.com" in the check that
# needs there to be no catalogue at all. Whatever setup plants that was not there before is removed
# at the end.
_PLANTED = ("site_index.json", "top-pages.json", "brand/company.json", "content-database.jsonl")
_DATA = os.environ.get("SEO_AGENT_DATA", "").strip()
_HAD = {n for n in _PLANTED if _DATA and os.path.exists(os.path.join(_DATA, "knowledge", n))}

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.tools import dfs, run_research
from seo_agent.research import curate

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


# ---- the wire, faked ----------------------------------------------------------------------------
_real = {"post": dfs.post, "get": dfs.get, "auth": dfs._auth, "balance": dfs.balance,
         "serp_advanced": dfs.serp_advanced, "sleeps": dfs.RETRY_SLEEPS,
         "httpx_post": httpx.post, "httpx_get": httpx.get}
dfs.RETRY_SLEEPS = (0, 0, 0)
dfs._auth = lambda: ("fixture-login", "fixture-password")
SLEPT = []
_real_sleep = dfs.time.sleep


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "https://api.dataforseo.com/v3/x")
            raise httpx.HTTPStatusError("HTTP %d" % self.status_code, request=req,
                                        response=httpx.Response(self.status_code, request=req))

    def json(self):
        return self._body


def body(task_code=20000, top=20000, n_tasks=1, msg="ok"):
    tasks = [{"status_code": task_code, "status_message": msg,
              "result": [{"items": [{"type": "organic", "url": "https://a.example/x"}]}]}]
    tasks += [{"status_code": 20000, "result": []} for _ in range(n_tasks - 1)]
    return {"status_code": top, "status_message": msg, "cost": 0.002, "tasks": tasks}


def wire(*answers):
    """httpx.post answering in turn from `answers` (a _Resp or an exception); returns the call log."""
    calls = []
    seq = list(answers)

    def fake(url, **kw):
        calls.append(url)
        a = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(a, BaseException):
            raise a
        return a
    httpx.post = fake
    httpx.get = fake
    return calls


print("\ndfs: temporary trouble is retried")
calls = wire(_Resp(200, body(40101, msg="Internal SE Server Error.")),
             _Resp(200, body(40101, msg="Internal SE Server Error.")), _Resp(200, body()))
items = dfs._items(dfs.post("/serp/google/organic/live/advanced", [{"keyword": "x"}]))
ok("a 40101 task twice, then fine: the answer comes back", len(items) == 1 and len(calls) == 3, (items, len(calls)))

calls = wire(_Resp(200, body(40101, msg="Internal SE Server Error.")))
try:
    dfs._items(dfs.post("/serp/google/organic/live/advanced", [{"keyword": "x"}]))
    raised = ""
except RuntimeError as e:
    raised = str(e)
ok("still 40101 after every wait: raises with their message, after 1 + %d tries" % len(dfs.RETRY_SLEEPS),
   "40101" in raised and len(calls) == 1 + len(dfs.RETRY_SLEEPS), (raised, len(calls)))

calls = wire(_Resp(502, {}), _Resp(200, body()))
dfs.post("/serp/google/organic/live/advanced", [{"keyword": "x"}])
ok("an HTTP 5xx is retried", len(calls) == 2, len(calls))

calls = wire(httpx.ConnectTimeout("timed out"), httpx.ConnectError("reset"), _Resp(200, body()))
dfs.post("/serp/google/organic/live/advanced", [{"keyword": "x"}])
ok("a timeout and a dropped connection are retried", len(calls) == 3, len(calls))

calls = wire(_Resp(200, body(top=50303)), _Resp(200, body()))
dfs.get("/serp/google/organic/tasks_ready")
ok("a top-level temporary code on a GET is retried too", len(calls) == 2, len(calls))

print("\ndfs: a real refusal is never retried")
for label, resp in (("bad login (40100)", _Resp(200, body(top=40100, msg="You are not authorized"))),
                    ("no money on the task (40200)", _Resp(200, body(40200, msg="Payment Required"))),
                    ("bad parameters (40501)", _Resp(200, body(40501, msg="Invalid Field"))),
                    ("HTTP 402", _Resp(402, {}))):
    calls = wire(resp)
    try:
        dfs._items(dfs.post("/serp/google/organic/live/advanced", [{"keyword": "x"}]))
        raised = False
    except (RuntimeError, httpx.HTTPStatusError):
        raised = True
    ok("%s: raised after exactly one call" % label, raised and len(calls) == 1, (raised, len(calls)))

calls = wire(_Resp(200, body(40101, n_tasks=3)))
dfs.post("/serp/google/organic/task_post", [{"keyword": "a"}, {"keyword": "b"}, {"keyword": "c"}])
ok("a many-task post is not re-sent over one task's temporary code", len(calls) == 1, len(calls))

httpx.post, httpx.get = _real["httpx_post"], _real["httpx_get"]
ok("the waits are the model's waits", _real["sleeps"] == (5, 15, 40), _real["sleeps"])
ok("the refusals are not in the retry list",
   not ({40100, 40200, 40210, 40501, 40102} & dfs.RETRY_CODES), dfs.RETRY_CODES)


# ---- curate: a failed search is skipped, not fatal ----------------------------------------------
COMPANY = {"brand": "Example", "domain": "example.com", "location_name": "United States", "language_code": "en"}
SPINE = {"spine": "s", "about": "a", "not_about": "n"}
SEARCHES = []


def searches(fail=lambda q: False):
    SEARCHES.clear()

    def fake(query, **kw):
        SEARCHES.append(query)
        if fail(query):
            raise RuntimeError("DataForSEO task failed (40101): Internal SE Server Error.")
        slug = query.replace(" ", "-")
        return {"extract": {"top_organic": [{"url": "https://site%d.example/%s" % (i, slug)} for i in range(3)]},
                "cost": 0.002}
    dfs.serp_advanced = fake


print("\ncurate: one search that fails is skipped and counted")
searches(fail=lambda q: q == "agency fee percentage")
said = []
out = curate.run("Cost per hire", "the angle", SPINE, COMPANY, say=lambda a, b="": said.append((a, b)))
ok("the round finishes with its turns", len(out["turns"]) > 0, len(out["turns"]))
ok("the failures are counted", out["failed_searches"] > 0 and out["failed_searches"] < out["searches"],
   (out["failed_searches"], out["searches"]))
ok("and said on screen", any("failed and were skipped" in b for a, b in said), said[-1:])

print("\ncurate: every search failing still fails loudly")
searches(fail=lambda q: True)
try:
    curate.run("Cost per hire", "the angle", SPINE, COMPANY)
    raised = ""
except RuntimeError as e:
    raised = str(e)
ok("no research at all is an error, not an empty round", "Every research search failed" in raised, raised)
ok("and it stopped asking soon, rather than running every turn against a dead service",
   len(SEARCHES) <= curate.FAIL_FAST + len(curate.RESEARCHERS * [0]) * curate.QUERIES_PER_TURN, len(SEARCHES))


print("\ncurate: the work is kept, and a resume does not buy it twice")
# Pinned to the historical team of 4 for this whole section (through the "round died" block below):
# the stub always offers Builder/Sceptic/Evidence One/Practitioner, in that order (_fixture.stub_json),
# and the two sections compare team sizes against each other, so both must use the same one --
# regardless of curate.RESEARCHERS' own default. Reset once, at the end of the section.
store.save_research_settings(researchers=4)
searches()
kept = []
full = curate.run("Cost per hire", "the angle", SPINE, COMPANY, keep=lambda s: kept.append(s))
bought = len(SEARCHES)
last = kept[-1]
ok("a save after every turn", len(kept) == len(full["turns"]) + len(full["team"]), (len(kept), len(full["turns"])))
ok("the last save has every researcher finished", len(last["done"]) == len(full["team"]), last["done"])

searches()
again = curate.run("Cost per hire", "the angle", SPINE, COMPANY, resume=last)
ok("a finished round resumed buys no search", len(SEARCHES) == 0, len(SEARCHES))
ok("and gives the same conversation back", len(again["turns"]) == len(full["turns"]) and
   len(again["pages"]) == len(full["pages"]), (len(again["turns"]), len(full["turns"])))

# A round that dies part way: one researcher's second question throws. The others finish and are
# saved; the resume runs only what is left. Still under the researchers=4 pin set above.
searches()
_real_ask = curate._ask
def _dies(topic, article, persona, turns):
    if persona["role"] == "The Sceptic" and len(turns) == 1:
        raise RuntimeError("the model went away")
    return _real_ask(topic, article, persona, turns)
curate._ask = _dies
kept = []
try:
    curate.run("Cost per hire", "the angle", SPINE, COMPANY, keep=lambda s: kept.append(s))
    died = False
except RuntimeError:
    died = True
curate._ask = _real_ask
ok("the round died", died)
state = kept[-1]
ok("the three that finished are saved as finished, the one that died is not",
   "The Sceptic" not in state["done"] and len(state["done"]) == 3, state["done"])
ok("its one finished turn is kept", len(state["turns"].get("The Sceptic") or []) == 1,
   len(state["turns"].get("The Sceptic") or []))
searches()
resumed = curate.run("Cost per hire", "the angle", SPINE, COMPANY, resume=state)
ok("the resume searches only for the turns the Sceptic has left",
   len(SEARCHES) == (curate.TURNS - 1) * curate.QUERIES_PER_TURN, (len(SEARCHES), bought))
ok("and the round comes back whole", len(resumed["turns"]) == len(full["turns"]), len(resumed["turns"]))
store.save_research_settings(researchers=None, gap_rounds=None)   # the pin above ends here


print("\nrun_research: the saved round belongs to its topic")
chat = store.new_chat("dfs retry test")
run = store.new_run(chat, "partial")
ctx = {"chat_id": chat, "run_id": run}
seen = []
_real_run = curate.run
curate.run = lambda *a, **k: (seen.append(k.get("resume")), k["keep"]({"team": [1]}), {"turns": []})[-1]
run_research._curate(ctx, False, "Topic A", "angle", SPINE, COMPANY, None)
ok("a first run has nothing to resume, and saves under its topic",
   seen[-1] is None and store.load_artifact(chat, run, "_work/curate-partial.json").get("topic") == "Topic A",
   store.load_artifact(chat, run, "_work/curate-partial.json"))
run_research._curate(ctx, False, "Topic A", "angle", SPINE, COMPANY, None)
ok("the same topic again resumes it", (seen[-1] or {}).get("team") == [1], seen[-1])
run_research._curate(ctx, False, "Topic B", "angle", SPINE, COMPANY, None)
ok("a different topic does not", seen[-1] is None, seen[-1])
run_research._curate(ctx, True, "Topic B", "angle", SPINE, COMPANY, None)
ok("fresh (a redo, the thin dossier's retry) never resumes", seen[-1] is None, seen[-1])
curate.run = _real_run

# ---- tidy up ------------------------------------------------------------------------------------
shutil.rmtree(store.chat_dir(chat), ignore_errors=True)
for _name in _PLANTED:
    if _name not in _HAD:
        try:
            os.remove(os.path.join(store.knowledge_dir(), _name))
        except OSError:
            pass
dfs.post, dfs.get, dfs._auth, dfs.balance = _real["post"], _real["get"], _real["auth"], _real["balance"]
dfs.serp_advanced, dfs.RETRY_SLEEPS = _real["serp_advanced"], _real["sleeps"]
print("\nFaked wire, stubbed model and web. Proves temporary DataForSEO trouble is waited out, one bad "
      "search is skipped, none at all still fails, and a resumed round does not buy its searches twice.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all dfs retry checks passed")
