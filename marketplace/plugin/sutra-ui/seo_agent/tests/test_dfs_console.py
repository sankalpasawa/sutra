"""The DataForSEO console's two routes: the allowlisted call, and the balance button.

Owner, 2026-09-12: "beside DataForSEO we could add two buttons: one is check balance... another
where you use DataForSEO separately". His own page called api.dataforseo.com from the browser
with Basic auth out of localStorage; inside Sutra that would be blocked by the origin and would
put his API password in a page, so the console asks the backend and the backend asks DataForSEO.

What this holds on to, because each is how it would hurt somebody:
  * an endpoint nobody chose is refused BEFORE any paid call is made
  * the allowlist is the eight the console offers, and nothing else
  * the credentials never appear in what comes back
  * "check balance" reads NOW, and writes the fresh figure into the cache the rest of the app
    reads, so two parts of the screen cannot disagree about the same number
"""
import os
import sys

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

from seo_agent import loop, store

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agents_api as api          # noqa: E402
from seo_agent.tools import dfs   # noqa: E402

FAILS = []


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


def status_of(res):
    return getattr(res, "status_code", 200)


# ---- the allowlist -------------------------------------------------------------------------
print("the console can call eight endpoints and no others")

CALLED = []
dfs.post = lambda path, payload: (CALLED.append(("post", path, payload)) or
                                  {"status_code": 20000, "cost": 0.003, "tasks": []})
dfs.get = lambda path: (CALLED.append(("get", path, None)) or
                        {"status_code": 20000, "tasks": []})

ok("the allowlist is exactly eight endpoints", len(api.DFS_CONSOLE_PATHS) == 8,
   sorted(api.DFS_CONSOLE_PATHS))
ok("and every one of them is a real /v3 path",
   all(p.startswith("/v3/") for p in api.DFS_CONSOLE_PATHS), sorted(api.DFS_CONSOLE_PATHS))

for bad in ("/v3/dataforseo_labs/google/keyword_ideas/live",   # real, but not offered
            "/v3/appendix/user_data/../../etc",                # climbing
            "https://evil.example/v3/appendix/user_data",      # a whole other host
            "", "/v3/serp/google/organic/task_post"):          # empty, and a paid queue call
    CALLED[:] = []
    res = api.api_dfs_call({"endpoint": bad, "payload": [{}]})
    ok("refused: %r" % (bad[:48] or "(empty)"), status_of(res) == 400, res)
    ok("...and nothing was spent finding out", CALLED == [], CALLED)

# ---- an allowed call -----------------------------------------------------------------------
print("\nan allowed endpoint reaches dfs.py, with the /v3 stripped and the body wrapped")

CALLED[:] = []
res = api.api_dfs_call({"endpoint": "/v3/dataforseo_labs/google/keyword_overview/live",
                        "payload": {"keywords": ["skills assessment"]}})
ok("it answers ok", (res or {}).get("ok") is True, res)
ok("dfs.post was called once", len(CALLED) == 1, CALLED)
ok("...with the path dfs.BASE expects (no second /v3)",
   CALLED and CALLED[0][1] == "/dataforseo_labs/google/keyword_overview/live", CALLED)
ok("...and a bare object wrapped into the list their API wants",
   CALLED and CALLED[0][2] == [{"keywords": ["skills assessment"]}], CALLED)
ok("the cost comes back, so the console can show what it spent",
   (res or {}).get("cost") == 0.003, res)

CALLED[:] = []
res = api.api_dfs_call({"endpoint": "/v3/dataforseo_labs/google/keyword_overview/live",
                        "payload": [{"keywords": ["a"]}, {"keywords": ["b"]}]})
ok("a list is passed through untouched, never re-wrapped",
   CALLED and CALLED[0][2] == [{"keywords": ["a"]}, {"keywords": ["b"]}], CALLED)

CALLED[:] = []
res = api.api_dfs_call({"endpoint": "/v3/appendix/user_data"})
ok("the free account endpoint goes through GET, as their API requires",
   CALLED and CALLED[0][0] == "get" and CALLED[0][1] == "/appendix/user_data", CALLED)

# ---- what comes back -----------------------------------------------------------------------
print("\nthe reply carries their JSON and none of his credentials")

store.save_connections({"dataforseo_login": "him@example.com", "dataforseo_password": "SECRET-PW"})
dfs.post = lambda path, payload: {"status_code": 20000, "tasks": [{"result": [{"x": 1}]}]}
res = api.api_dfs_call({"endpoint": "/v3/dataforseo_labs/google/ranked_keywords/live",
                        "payload": {"target": "testlify.com"}})
flat = repr(res)
ok("the raw reply is returned, because the console shows it",
   (res or {}).get("data", {}).get("tasks") == [{"result": [{"x": 1}]}], res)
ok("the password is nowhere in it", "SECRET-PW" not in flat)
ok("nor is the login", "him@example.com" not in flat)

# ---- refusals ------------------------------------------------------------------------------
print("\na refusal from DataForSEO is reported, not swallowed")


def _boom(path, payload):
    raise RuntimeError("DataForSEO refused the call (40501): invalid field")


dfs.post = _boom
res = api.api_dfs_call({"endpoint": "/v3/backlinks/domain_pages/live", "payload": {}})
ok("their own words come back", status_of(res) == 502, res)


class NoCredentials(Exception):
    pass


dfs.NoCredentials = NoCredentials


def _nocreds(path, payload):
    raise NoCredentials("nope")


dfs.post = _nocreds
res = api.api_dfs_call({"endpoint": "/v3/backlinks/domain_pages/live", "payload": {}})
ok("and a missing credential says what to do about it, in one line",
   status_of(res) == 400 and "not connected" in str(getattr(res, "body", b"")).lower(), res)

# ---- the balance button --------------------------------------------------------------------
print("\ncheck balance reads NOW, and the rest of the app agrees with it afterwards")

dfs.available = lambda: True
dfs.balance = lambda: 12.34
loop._BAL.update({"at": 0.0, "v": None})
res = api.api_dfs_balance()
ok("it answers with the balance it just read", (res or {}).get("balance") == 12.34, res)
ok("it names the floor a run needs, from run_research and never a literal",
   isinstance((res or {}).get("floor"), (int, float)), res)
ok("12.34 is above that floor, so it says so", (res or {}).get("enough") is True, res)
ok("the cached figure the rest of the app reads was refreshed too",
   loop._BAL.get("v") == 12.34, loop._BAL)

dfs.balance = lambda: 0.07
res = api.api_dfs_balance()
ok("a balance under the floor is reported as not enough", (res or {}).get("enough") is False, res)

dfs.available = lambda: False
res = api.api_dfs_balance()
ok("with nothing connected it asks for the login instead of guessing",
   status_of(res) == 400, res)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all DataForSEO console checks passed")
