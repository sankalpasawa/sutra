"""tests/test_research_settings.py -- the Prompts tab's two research numbers.

Researchers (how many personas interview an expert, research/curate.pick_team) and Gap rounds
(how many extra evidence rounds a gap check may spend, research/gap_check.triage), saved the way
the model-call slots setting already works: a small JSON at the agent data root
(store.research_settings / save_research_settings), read fresh by the engine on every call.

Proves: the raw store round-trips, including gap_rounds=0 (a real, valid value that must never
collapse to None the way slot_settings' 0 does); the engine's OWN default -- not just what the
screen would show -- is 3 researchers and 1 gap round when nothing has been saved; a saved value
overrides that default; and every value is clamped to its range regardless of what asked for it.
No Claude process is ever started: llm.json_call is stubbed.
"""
import os
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store  # noqa: E402
from seo_agent.research import _common as _c  # noqa: E402
from seo_agent.research import curate, gap_check  # noqa: E402

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("   " + str(extra)) if extra and not cond else ""))


def reset():
    store.save_research_settings(researchers=None, gap_rounds=None)


# =========================================================================================
print("\nthe engine's own defaults -- not the screen's")
ok("curate.RESEARCHERS is 3", curate.RESEARCHERS == 3, curate.RESEARCHERS)
ok("curate.RESEARCHERS_RANGE is 1 to 6", curate.RESEARCHERS_RANGE == (1, 6), curate.RESEARCHERS_RANGE)
ok("_common.GAP_ROUNDS_DEFAULT is 1", _c.GAP_ROUNDS_DEFAULT == 1, _c.GAP_ROUNDS_DEFAULT)
ok("_common.GAP_MAX_QUERIES (the hard cap / range top) is still 3", _c.GAP_MAX_QUERIES == 3, _c.GAP_MAX_QUERIES)

# =========================================================================================
print("\nstore.research_settings / save_research_settings round-trip")
reset()
ok("a fresh install has nothing saved", store.research_settings() == {"researchers": None, "gap_rounds": None},
   store.research_settings())
saved = store.save_research_settings(researchers=5, gap_rounds=2)
ok("save returns the new values", saved == {"researchers": 5, "gap_rounds": 2}, saved)
ok("and research_settings() reads them back", store.research_settings() == {"researchers": 5, "gap_rounds": 2})
saved0 = store.save_research_settings(researchers=5, gap_rounds=0)
ok("gap_rounds=0 is a REAL value, not collapsed to None (unlike slot_settings' int(v) or None)",
   saved0 == {"researchers": 5, "gap_rounds": 0}, saved0)
ok("and it round-trips as 0, not None", store.research_settings()["gap_rounds"] == 0,
   store.research_settings())
reset()
ok("clearing both goes back to None, None", store.research_settings() == {"researchers": None, "gap_rounds": None})

# =========================================================================================
print("\npick_team: how many researchers actually run")
REAL_JSON_CALL = llm.json_call


def fake_team(n_available=10):
    """A json_call stub that always offers MORE researchers than any setting under test would ask
    for, so the team size actually seen is pick_team's own clamp, never the model's."""
    def call(prompt, *a, **kw):
        return {"researchers": [{"role": "role-%d" % i, "focus": "x"} for i in range(n_available)]}
    return call


llm.json_call = fake_team()
try:
    reset()
    team = curate.pick_team("t", "a", {}, {"brand": "Acme"})
    ok("with nothing saved, the engine's own default (3) is what actually runs, not a screen guess",
       len(team) == 3, len(team))

    store.save_research_settings(researchers=5, gap_rounds=None)
    team = curate.pick_team("t", "a", {}, {"brand": "Acme"})
    ok("a saved setting overrides the default", len(team) == 5, len(team))

    store.save_research_settings(researchers=99, gap_rounds=None)
    team = curate.pick_team("t", "a", {}, {"brand": "Acme"})
    ok("an out-of-range saved value is clamped to the top of the range (6), not trusted as-is",
       len(team) == 6, len(team))

    store.save_research_settings(researchers=0, gap_rounds=None)
    team = curate.pick_team("t", "a", {}, {"brand": "Acme"})
    ok("and clamped to the bottom of the range (1) too", len(team) == 1, len(team))

    team = curate.pick_team("t", "a", {}, {"brand": "Acme"}, n=4)
    ok("an explicit n from the caller still wins over the saved setting", len(team) == 4, len(team))
finally:
    llm.json_call = REAL_JSON_CALL
    reset()

# =========================================================================================
print("\ngap_check.triage: how many gap rounds actually run")


def fake_queries(n_available=10):
    def call(prompt, *a, **kw):
        return {"queries": [{"query": "q%d" % i, "fills": [], "source": "flagged", "why": "x"}
                            for i in range(n_available)]}
    return call


META = {"title": "t", "angle": "a", "spine": "s", "about": "", "not_about": ""}
llm.json_call = fake_queries()
try:
    reset()
    qs = gap_check.triage([], META, [])
    ok("with nothing saved, the engine's own default (1) is what actually runs, not the hard cap (3)",
       len(qs) == 1, len(qs))

    store.save_research_settings(researchers=None, gap_rounds=3)
    qs = gap_check.triage([], META, [])
    ok("a saved setting raises it, up to the hard cap", len(qs) == 3, len(qs))

    store.save_research_settings(researchers=None, gap_rounds=0)
    qs = gap_check.triage([], META, [])
    ok("gap_rounds=0 really runs NO gap query, not one slipping through before the cap check",
       qs == [], qs)

    store.save_research_settings(researchers=None, gap_rounds=99)
    qs = gap_check.triage([], META, [])
    ok("an out-of-range saved value is clamped to the hard cap (3), never trusted as-is",
       len(qs) == 3, len(qs))

    qs = gap_check.triage([], META, [], max_queries=2)
    ok("an explicit max_queries from the caller still wins over the saved setting", len(qs) == 2, len(qs))
finally:
    llm.json_call = REAL_JSON_CALL
    reset()

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all research-settings checks passed")
