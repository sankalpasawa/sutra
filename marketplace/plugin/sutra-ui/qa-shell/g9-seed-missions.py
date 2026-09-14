"""qa-shell/g9-seed-missions.py -- the four G9 missions, as REAL records.

Companion to g9-live-card-check.mjs. These go through the app's own
MissionStore.create() / .save(), land as real mission files, and are served
by the real /api/shadow/missions to the real renderer. Nothing about them is
a fixture except WHICH missions exist.

SUTRA_SHADOW_HOME IS MANDATORY and must not be the default home. The store
resolver honours it for every Shadow file (shadow_ledger.shadow_home), so
pointing it at a throwaway directory keeps the operator's live Shadow state
-- missions, ledgers, watch lists -- untouched. Refusing to run without it
is the same guard shadow_home() applies under pytest, for the same reason:
on 2026-09-08..12 test runs wrote dozens of fixture missions into the live
home because the override was assumed rather than required.

Usage:
  SUTRA_UI_REPO=$PWD SUTRA_SHADOW_HOME=/tmp/g9-shadow-home \\
    .venv/bin/python qa-shell/g9-seed-missions.py
"""
import json
import os
import sys

HOME = os.environ.get("SUTRA_SHADOW_HOME")
if not HOME:
    sys.exit("refusing to seed: set SUTRA_SHADOW_HOME to a throwaway dir")
if os.path.realpath(os.path.expanduser(HOME)) == \
        os.path.realpath(os.path.expanduser("~/.sutra-ui/shadow")):
    sys.exit("refusing to seed into the live Shadow home")

os.makedirs(HOME, exist_ok=True)
sys.path.insert(0, os.environ.get("SUTRA_UI_REPO") or os.getcwd())

import mission_engine  # noqa: E402  (path must be set first)

# (name, objective, turns_used, max_turns) -- max_turns None means the key is
# REMOVED, not set to zero. A record written before the field existed is the
# real-world shape the no-bar fallback has to survive.
SEEDS = [
    ("low",   "Refactor the CSV importer",      3,  20),
    ("high",  "Chase the flaky overlay test",   19, 20),
    ("over",  "Rebuild the settings migration", 26, 20),
    ("nomax", "Watch the deploy",               4,  None),
]

store = mission_engine.MissionStore()
ids = {}
for name, objective, used, mx in SEEDS:
    m = store.create(
        objective=objective,
        template="fix",
        target_mode="existing",
        target_session=None,
        done_when=[{"check": "the suite is green"}],
    )
    m["state"] = "running"
    m["turns_used"] = used
    if mx is None:
        m.pop("max_turns", None)
    else:
        m["max_turns"] = mx
    store.save(m)
    ids[name] = m["id"]
    print("seeded %-6s %s  turns_used=%s max_turns=%s"
          % (name, m["id"], used, "ABSENT" if mx is None else mx))

out = os.path.join(HOME, "g9-ids.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(ids, fh, indent=1)
print("ids -> " + out)
