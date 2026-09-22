"""tests/test_key_preflight.py — a missing key is said UP FRONT, on every path, not just research.

THE INCIDENT (owner, 2026-09-22). A friend onboarded a new company with neither DataForSEO nor
Voyage connected. Nothing told him. Setup ran a long time. The asset engine, which needs Voyage to
tell that two differently-worded complaints are the same complaint, fell back to matching literal
words and turned 200 Reddit posts into 151 fragments. The idea sheet came out empty. The only two
signals in the whole app were a "!" badge on a sidebar item he had no reason to click and one line
buried mid-log, after the damage.

The lesson had already been learned. `run_research._refuse`, 2026-09-09, quoting the owner:

    "why should it even go further if there is no DataForSEO? It never misfires. It is pointless,
     a very bad experience."

That guard was written for one tool and applied to no other. Measured on 2026-09-22: run_research
checked; build_assets, onboard, learn_brand and suggest_topics did not. So the whole first-run
path still failed in exactly the way that note describes.

What this suite pins:

  1. THE TWO KEYS FAIL DIFFERENTLY, and the difference is the design.
     DataForSEO is money: where it is genuinely required (run_research) its absence is a REFUSAL.
     Voyage is meaning: the engine still works without it, just cruder, so it is a WARNING.
  2. A WARNING IS NOT A REFUSAL, AND build_assets ONLY WARNS. The first version of this guard
     refused build_assets on a missing DataForSEO, copying run_research. test_assets_wiring caught
     it: this engine does not need DataForSEO. Two of its three finders never touch it, and the
     third already degrades one step and says so. Refusing would block somebody who could still
     get a good sheet, which is a worse bug than the one being fixed. Pinned here so nobody
     "tidies" the guard back into a refusal.
  3. THE REFUSAL SAYS BOTH WAYS OUT. A wall that does not say how to get past it is not a guard.
  4. IT FAILS OPEN. A check that cannot run is not a reason to refuse: the paid calls fail loudly
     on their own, and the owner's connection drops several times a day.
  5. A KEY THAT ARRIVES UNDOES THE SKIP. build_assets skips a builder whose files exist, which is
     right for a re-run and exactly wrong once a missing key is connected: the work being skipped
     is the work the key would have fixed. Without this the friend adds his Voyage key, runs it
     again, is told "Already built", gets the same 151 fragments, and concludes the key did
     nothing. Only ever upwards: losing a key never throws away good work.
  6. ONBOARD WARNS AND NEVER REFUSES. The interview needs neither key, so blocking it would be
     absurd; but it is the first thing anyone does, so it is the first chance to say.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.tools import _shared as sh

llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


BOTH_GONE = {"dataforseo": True, "voyage": True}
DFS_GONE = {"dataforseo": True, "voyage": False}
VOYAGE_GONE = {"dataforseo": False, "voyage": True}
BOTH_HERE = {"dataforseo": False, "voyage": False}


# ---- 1. the two keys are treated differently ---------------------------------------------------
print("the two keys fail differently, and that is the design")

ok("no DataForSEO is a refusal",
   sh.refuse_missing_keys(("dataforseo",), DFS_GONE) is not None)
ok("no Voyage is NOT a refusal, because the engine still works without it",
   sh.refuse_missing_keys(("dataforseo",), VOYAGE_GONE) is None)
ok("with both connected nothing is refused",
   sh.refuse_missing_keys(("dataforseo",), BOTH_HERE) is None)


# ---- 2. the refusal names the problem AND both ways out ----------------------------------------
print("\nthe refusal says how to get past it")

ref = sh.refuse_missing_keys(("dataforseo",), DFS_GONE) or {}
said = (ref.get("summary", "") + " " + ref.get("error", "")).lower()
ok("it is the shape loop.py already draws: a summary and an error",
   set(ref) >= {"summary", "error"}, sorted(ref))
ok("it names the thing that is missing", "dataforseo" in said)
ok("it says where to put it", "connections" in said)
ok("and it offers the other way out, rather than being a wall",
   "placeholder" in said or "demo" in said, said[:200])


# ---- 3. the warning says what it will cost, before the work ------------------------------------
print("\nthe warning says what it costs, in words a person can act on")

lines = []
warned = sh.warn_missing_keys(lambda a, b="": lines.append((a, b)), ("voyage",), VOYAGE_GONE)
ok("a missing Voyage key is warned about", warned == ["voyage"], warned)
ok("the warning says what goes wrong, not just the key's name",
   any("group" in a.lower() or "mean" in a.lower() for a, _b in lines), lines)
ok("and says it is free, so nobody assumes it is a paid blocker",
   any("free" in b.lower() for _a, b in lines), lines)
lines = []
sh.warn_missing_keys(lambda a, b="": lines.append((a, b)), ("voyage",), BOTH_HERE)
ok("nothing is said when the key is there", lines == [], lines)

# A warning must never be the thing that breaks a run. The reporter is the chat's own, and a chat
# write can fail for reasons that have nothing to do with keys.
def _boom(*_a, **_k):
    raise RuntimeError("the chat write failed")
try:
    sh.warn_missing_keys(_boom, ("voyage",), VOYAGE_GONE)
    survived = True
except Exception:                          # noqa: BLE001
    survived = False
ok("a warning that cannot be printed does not take the run down with it", survived)


# ---- 4. it fails open --------------------------------------------------------------------------
print("\nit fails open: a check that cannot run is not a refusal")

import seo_agent.tools.dfs as dfs_mod
_avail = dfs_mod.available
dfs_mod.available = lambda: (_ for _ in ()).throw(RuntimeError("the wire is down"))
try:
    got = sh.keys_missing()
finally:
    dfs_mod.available = _avail
ok("an unreadable DataForSEO check reports NOT missing, so the run proceeds",
   got.get("dataforseo") is False, got)


# ---- 5. build_assets WARNS, and does not refuse ------------------------------------------------
print("\nbuild_assets warns about both keys and refuses on neither")

from seo_agent import store
from seo_agent.tools import build_assets

# GET PAST THE TWO GATES THAT COME FIRST, or this proves nothing. build_assets already refuses
# without a site index and without a brand pack, and both fire before the key check. A first draft
# of this test "passed" on the brand-pack refusal and would have gone on passing with the key
# guard deleted entirely.
store.save_knowledge("site_index.json", {"pages": [{"url": "https://example.com/a", "title": "A"}]})
store.save_knowledge("brand/features.md", "# Features\n\n- A thing this company genuinely does.\n")

_ran, said_lines = [], []
_orig_module = build_assets._module
def _spy(name):
    _ran.append(name)
    return _orig_module(name)

_orig_keys = sh.keys_missing
_orig_reporter = sh.reporter
sh.keys_missing = lambda: BOTH_GONE
sh.reporter = lambda ctx, tool="": (lambda a, b="": said_lines.append(a))
build_assets._module = _spy
try:
    out = build_assets.run({"chat_id": "c-x", "run_id": "r-x"}) or {}
except Exception as e:                     # noqa: BLE001 -- the builders themselves are not under test
    out = {"summary": "raised", "error": str(e)}
finally:
    sh.keys_missing = _orig_keys
    sh.reporter = _orig_reporter
    build_assets._module = _orig_module

why = (str(out.get("summary", "")) + " " + str(out.get("error", ""))).lower()
ok("THE ENGINE STILL RUNS with neither key: two of its three finders never needed DataForSEO, "
   "and the third degrades one step on its own",
   _ran != [], (_ran, why[:120]))
ok("it is not refused for a missing key",
   "not connected" not in why and "not started" not in why, why[:200])
ok("but both missing keys were SAID, up front, before the work",
   sum(1 for line in said_lines if "DataForSEO" in line or "Voyage" in line) >= 2, said_lines[:4])

# ---- 6. a key that arrives undoes the skip -----------------------------------------------------
print("\na key that arrives since undoes 'Already built'")

ok("Voyage absent then, present now: rebuild",
   sh.keys_improved({"dataforseo": True, "voyage": False}, {"dataforseo": True, "voyage": True}))
ok("nothing changed: keep the skip",
   not sh.keys_improved({"dataforseo": True, "voyage": True}, {"dataforseo": True, "voyage": True}))
ok("a key LOST since does not throw away work that was built properly",
   not sh.keys_improved({"dataforseo": True, "voyage": True}, {"dataforseo": True, "voyage": False}))
ok("no record at all cannot prove an improvement, so the ordinary skip stands",
   not sh.keys_improved(None, {"dataforseo": True, "voyage": True}))
ok("and a corrupted record is treated the same way, never as a reason to rebuild everything",
   not sh.keys_improved("not a dict", {"dataforseo": True, "voyage": True}))

stamp = sh.keys_stamp(BOTH_GONE)
ok("the stamp records what was CONNECTED, not what was missing",
   stamp == {"dataforseo": False, "voyage": False}, stamp)


# ---- 7. onboard warns, and never refuses -------------------------------------------------------
print("\nonboard warns and never refuses: the interview needs neither key")

from seo_agent.tools import onboard

said_lines = []
_orig_reporter = sh.reporter
sh.reporter = lambda ctx, tool="": (lambda a, b="": said_lines.append(a))
sh.keys_missing = lambda: BOTH_GONE
try:
    got = onboard.run({"chat_id": "c-y", "run_id": "r-y"}) or {}
finally:
    sh.reporter = _orig_reporter
    sh.keys_missing = _orig_keys

ok("the interview still runs: it is never refused for a missing key",
   not (isinstance(got, dict) and got.get("error") and "connected" in str(got.get("summary", ""))),
   got.get("summary"))
ok("and both missing keys were said, at the start, in the chat",
   sum(1 for line in said_lines if "DataForSEO" in line or "Voyage" in line) >= 2, said_lines)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all key pre-flight checks passed")
