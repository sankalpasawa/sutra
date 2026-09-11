"""The face pack: the list a person picks their avatar from, and the rules for picking.

Owner asked for it on 2026-09-10: "give users one of the emojis to choose from... pick any
unique pack, should be super cool, not vulgar, but super specific."

The four rules the pack was chosen by are asserted here, not just written in a comment, because
the easy way to break this is to append a face without reading why the others were chosen.
"""
import sys

from seo_agent.tests import _fixture   # noqa: F401

from seo_agent.workspace import faces
F=[]
def ok(l,c):
    print(("  PASS  " if c else "  FAIL  ")+l)
    if not c: F.append(l)

ok("32 faces, no duplicates", len(faces.FACES) == 32 and len(set(faces.FACES)) == 32)
ok("every face has a name", all(f in faces.NAMES for f in faces.FACES))
ok("no name is blank", all(faces.NAMES[f].strip() for f in faces.FACES))
# the four rules the pack was chosen by
ok("no faces, no body parts, no skin tones",
   not any(any(ord(ch) in range(0x1F3FB, 0x1F400) for ch in f) for f in faces.FACES))
ok("no flags", not any("\U0001F1E6" <= ch <= "\U0001F1FF" for f in faces.FACES for ch in f))

ok("free() excludes what is taken", "🦊" not in faces.free(["🦊"]))
ok("free() ignores junk in the taken list", len(faces.free(["not-an-emoji", ""])) == 32)
ok("suggest is stable for the same name",
   faces.suggest([], "Devansh") == faces.suggest([], "Devansh"))
ok("suggest prefers a face nobody has",
   faces.suggest([f for f in faces.FACES if f != "🐫"], "anyone") == "🐫")
ok("a full workspace still gets a suggestion rather than nothing",
   faces.suggest(list(faces.FACES), "the 33rd person") in faces.FACES)
ok("is_known rejects anything off-pack", not faces.is_known("💩") and faces.is_known("🐙"))
ok("name_of an unknown face is blank, not a crash", faces.name_of("💩") == "")

# two people, different names, should mostly differ -- the point of the hash
picks = {faces.suggest([], n) for n in ["Devansh", "Sankalp", "Vinit", "Joy", "Tishant"]}
ok("five different names get %d different faces" % len(picks), len(picks) >= 4)
# THE MIGRATION HAS TO EXIST, or a workspace created before today has no column to write into.
from seo_agent.workspace import schema   # noqa: E402
ok("SCHEMA_VERSION moved with the migration",
   schema.SCHEMA_VERSION == 4 and any(m[0] == 4 for m in schema.MIGRATIONS))
_m4 = [m for m in schema.MIGRATIONS if m[0] == 4][0]
ok("the step adds the column idempotently, so re-running it is harmless",
   "add column if not exists emoji" in _m4[2])
ok("and it tells PostgREST to reload, or the column reads as missing until its cache turns",
   "notify pgrst" in _m4[2])
ok("a workspace on 3 is offered exactly the one step",
   [m[0] for m in schema.pending(3)] == [4])
ok("a workspace already on 4 is offered none", schema.pending(4) == [])
ok("a workspace on 2 gets both steps, in order", [m[0] for m in schema.pending(2)] == [3, 4])

print()
if F:
    print("%d FAILED: %s" % (len(F), ", ".join(F)))
    sys.exit(1)
print("all face checks passed")
