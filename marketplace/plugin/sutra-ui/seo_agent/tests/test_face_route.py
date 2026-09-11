"""The face route must not report a save that Supabase refused.

The bug, 2026-09-11: the owner picked a face, was told nothing, and nothing was written. His
workspace is on schema 2; members.emoji arrives in 4, so the write was rejected -- and
_ws_announce caught every exception and moved on, after which the route returned ok:true.
"""
import os
import sys

# agents_api lives at the sutra-ui root, not inside the package, so this suite reaches up for it
# the way the panel does. It imports no network and starts no server.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

import agents_api as api

F = []
def ok(l, c):
    print(("  PASS  " if c else "  FAIL  ") + l)
    if not c: F.append(l)

class Boom:
    """A client whose member write fails the way PostgREST fails on a missing column."""
    def __init__(self, msg): self.msg = msg
    def register_member(self, name, emoji=None):
        raise RuntimeError(self.msg)

class Fine:
    def __init__(self): self.saw = None
    def register_member(self, name, emoji=None): self.saw = (name, emoji); return {}

# _ws_announce now REPORTS instead of swallowing
err = api._ws_announce({"client": Boom("PGRST204 column members.emoji does not exist")}, "m1", "Devansh", "🐙")
ok("a rejected write comes back as a reason, not silence", bool(err))
ok("and the reason names the column", "emoji" in err.lower())

good = Fine()
ok("a write that lands reports no error", api._ws_announce({"client": good}, "m1", "Devansh", "🐙") == "")
ok("and the face reached the client", good.saw == ("Devansh", "🐙"))
ok("no client at all is not an error", api._ws_announce({}, "m1", "D", "🐙") == "")
ok("no member id is not an error", api._ws_announce({"client": good}, "", "D", "🐙") == "")

# the route turns that reason into a sentence a person can act on
src = open("agents_api.py").read()
i = src.index('def api_workspace_face(')   # the singular one; _faces() sorts first
j = src.index('@router.', i)          # the whole function, not a guessed number of characters
route = src[i:j]
ok("the route checks the result instead of returning ok blindly",
   "err = _ws_announce(" in route and "if err:" in route)
ok("a missing column is explained as a workspace that needs updating",
   "has not been updated yet" in route)
ok("and it points at where to do that", "Connections" in route)
ok("any other failure still says what went wrong, never ok",
   "could not be saved" in route)
ok("ok:true is only reachable AFTER the error branch",
   route.index("if err:") < route.index('"ok": True'))

# PICKED ONCE. The rule is enforced on the server, not just by hiding a button.
ok("the route refuses a second pick", "Faces are picked once" in route)
ok("and it decides from the WORKSPACE row, not the local settings copy",
   "_ws_member_rows(mods)" in route)
ok("the refusal comes before any write", route.index("picked once") < route.index("_ws_announce("))

print()
if F:
    print("%d FAILED: %s" % (len(F), ", ".join(F))); sys.exit(1)
print("the face route is honest about what it saved")
