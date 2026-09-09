"""tests/test_find_prompt.py — "this isn't coming out right" finds the prompt, and only proposes.

The owner asked for a way to say a thing is not coming out right and have the agent work out which
step owns it (2026-09-09), with one hard line drawn through the middle of it: the agent proposes,
the person edits. So the two things worth proving are the map and the limit.

The map: every editable prompt is reachable, each carries the station it runs in and what it is
responsible for, and a name that does not exist comes back with the real list rather than an error
the model cannot act on.

The limit: this tool has no write path at all. Not a disabled one, not a guarded one — none. That
is asserted against the module, because "we would never do that" is not a guarantee and the next
person to add a convenience `save()` here should have a test stop them.
"""
import inspect
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent.prompts import store as ps
from seo_agent.tools import find_prompt

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


# ---- the map ---------------------------------------------------------------------------------
all_of_them = find_prompt.run(None)
names = [r["name"] for r in all_of_them["prompts"]]

ok("every editable prompt is on the map, and nothing else is",
   sorted(names) == sorted(ps.EDITABLE), set(names) ^ set(ps.EDITABLE))
ok("the count it reports is the count it returned",
   all_of_them["count"] == len(names), (all_of_them["count"], len(names)))
ok("every row says which station it runs in",
   all(r.get("station") and r.get("station_is_for") for r in all_of_them["prompts"]),
   [r["name"] for r in all_of_them["prompts"] if not r.get("station")])
ok("every row says what that prompt is responsible for",
   all(r.get("owns") for r in all_of_them["prompts"]),
   [r["name"] for r in all_of_them["prompts"] if not r.get("owns")])
ok("the eight format rulebooks are marked as one-per-article, so seven of them are not proposed",
   "one of the eight" in all_of_them["routed_note"].lower(), all_of_them["routed_note"])
ok("the map tells the model what to do next instead of leaving it to guess",
   "find_prompt again" in all_of_them["next"], all_of_them["next"])


# ---- one prompt ------------------------------------------------------------------------------
one = find_prompt.run(None, name="write/wrapper")
ok("a named prompt comes back with its real current text",
   one["text"] == ps.current_text("write/wrapper") and one["words"] > 0, one.get("words"))
ok("and with its plain title, not its path", one["title"] == ps.EDITABLE["write/wrapper"][0], one.get("title"))
ok("the tokens it must not drop are listed",
   one["tokens"] == sorted(ps.tokens(ps.shipped_text("write/wrapper"))) and len(one["tokens"]) > 0,
   one.get("tokens"))
ok("the token rule is stated in the result, not left to the model to remember",
   "refused" in one["token_rule"] and "{{TOKEN}}" in one["token_rule"], one.get("token_rule"))
ok("the result tells the model to propose and send the person to the Prompts tab",
   "You do not edit this" in one["how_to_change_it"] and "Prompts tab" in one["how_to_change_it"],
   one.get("how_to_change_it"))

# A format rulebook is fetched by the same door as a writing prompt. It has no {{TOKEN}} of its
# own, which is correct, and must not be treated as an error.
rule = find_prompt.run(None, name="write/formats/listicle")
ok("a format rulebook is reachable too, and its empty token list is not an error",
   rule.get("text") and "error" not in rule, rule.get("error"))


# ---- a wrong name ----------------------------------------------------------------------------
bad = find_prompt.run(None, name="write/does-not-exist")
ok("a name that does not exist is refused", "error" in bad, bad)
ok("and the refusal hands back the real list, so the model can correct itself in one turn",
   len(bad.get("prompts") or []) == len(ps.EDITABLE), len(bad.get("prompts") or []))
ok("an empty name is the map, not an error", "error" not in find_prompt.run(None, name="   "))


# ---- the limit: the agent proposes, the person edits ------------------------------------------
src = inspect.getsource(find_prompt)
ok("the tool never saves a prompt", "ps.save" not in src and ".save(" not in src, "a write path exists")
ok("the tool never resets a prompt", "reset(" not in src)
ok("the tool makes no model call", "llm" not in src)
ok("the tool writes nothing at all", "open(" not in src and "store.save" not in src)
ok("and the design reason is written down where the next person will read it",
   "the person EDITS" in src or "the agent PROPOSES" in src)

print("\nThe map is complete and the tool has no write path: the agent proposes, the person edits.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all find_prompt checks passed")
