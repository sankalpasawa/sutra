"""Loading a sheet the workflow already produced, and the two things it must never invent."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("SEO_AGENT_NO_CLI", "1")
from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent.assets import _common as acm, import_sheet  # noqa: E402

P, F = 0, []


def ok(name, cond, detail=""):
    global P
    if cond:
        P += 1
        print("  PASS  %s" % name)
    else:
        F.append(name)
        print("  FAIL  %s %s" % (name, ("— %s" % (detail,))[:220]))


SHEET = ("Sources,Brand fit,Asset,Format,Tool escalation,Distinct angle,What it'd be,# pages,"
         "# words,Total domains,# comps,# posts,Beatability,Effort,Proof URLs,RAG candidates,"
         "Topic pages we own,Reference links,Reuse verdict,Chosen links,Why\n"
         'M1,CORE,The Real Cost of Recruitment,News article,,Refreshes a stale figure,,2,1133,1789,1,,,,'
         'https://shrm.org/a ; https://shrm.org/b,,,,Build from parts,https://x.com/one,Spread across three\n'
         'M3,ADJACENT,What recruiters argue about,Definitional explainer,,The five tensions,,,,,,42,,,'
         ',,,,Brand new,,Nothing covers it\n'
         'M2 + M1,TRANSPLANT,The screening calculator,Quiz / assessment,needs a real test built,'
         'Hours lost per role,a working scored test,,,,,,2,M,,,,,Improve existing,,Close to one we have\n'
         ',,,,,,,,,,,,,,,,,,,,\n')

rows, rep = import_sheet.parse(SHEET)
print("\nreading the sheet")
ok("every row with a title becomes an idea", rep["read"] == 3, rep)
ok("a blank row is counted and said, not silently skipped", rep["dropped"] == 1, rep)
ok("the columns are read by NAME, so their order does not matter",
   rows[0]["title"] == "The Real Cost of Recruitment")

print("\nthe method shorthand")
ok("M1 is the competitor study", rows[0]["method"] == ["competitor-study"], rows[0]["method"])
ok("M3 is the trends method", rows[1]["method"] == ["study-trends"])
ok("an idea two methods found keeps BOTH, in the sheet's order",
   rows[2]["method"] == ["model-other-niches", "competitor-study"], rows[2]["method"])

print("\nids stay in their bands, so a built sheet could never collide with an imported one")
ok("the competitor idea is banded", rows[0]["id"].startswith("a1"), rows[0]["id"])
ok("the trends idea is banded", rows[1]["id"].startswith("a3"), rows[1]["id"])
ok("every id is unique", len({r["id"] for r in rows}) == len(rows))

print("\nwhat it will NOT invent")
ok("no linkability score exists in the sheet, so none is shown",
   rows[0]["linkability"]["score"] is None and rows[0]["linkability"]["judged"] is False,
   rows[0]["linkability"])
ok("...and it is not a zero, which would read as a real rejection",
   rows[0]["linkability"]["verdict"] is None)
ok("it says why there is no score", "no linkability score" in rows[0]["linkability"]["why"])
ok("ownability is taken from the fit, because that IS what the test decided",
   rows[0]["ownability"]["verdict"] is True and "CORE" in rows[0]["ownability"]["why"])

print("\nthe fields that carry the evidence")
ok("the proof urls come through", [p["url"] for p in rows[0]["proof"]] == ["https://shrm.org/a", "https://shrm.org/b"])
ok("the linking-domain count rides on the proof", rows[0]["proof"][0]["domains"] == 1789)
ok("and says what it counted", "2 pages" in rows[0]["proof"][0]["what"], rows[0]["proof"][0]["what"])
ok("the reuse verdict is lower-cased to the one the app knows",
   rows[0]["reuse"]["verdict"] == "build from parts" and rows[0]["reuse"]["verdict"] in acm.REUSE_VERDICTS)
ok("the chosen links come through", rows[0]["reuse"]["links"] == ["https://x.com/one"])
ok("an idea needing a build is flagged, never hidden",
   rows[2]["tool_escalation"] is True and rows[2]["what_it_would_be"])
ok("an idea needing no build is not flagged", rows[0]["tool_escalation"] is False)
ok("the sheet arrives ranked and keeps its order", [r["rank"] for r in rows] == [1, 2, 3])

print("\nthe screen's own sentence")
import tempfile  # noqa: E402
p = os.path.join(tempfile.mkdtemp(), "clubbed-ideas.csv")
open(p, "w").write(SHEET)
rep2 = import_sheet.apply(p)
line = (acm.read("_work/merge/methods.json") or {}).get("line", "")
ok("the summary names the methods in English, never their folder names",
   "the competitor study" in line and "study-trends" not in line, line)
ok("an import replaces the sheet rather than doubling it", len(acm.ideas()) == 3)
ok("the ideas are on disk and the chip can find one", acm.next_open()["id"] == rows[0]["id"])

print("\nrefusing a file that is not a sheet")
try:
    import_sheet.parse("name,email\nbob,bob@x.com\n")
    ok("a file with no Asset column is refused", False)
except ValueError as e:
    ok("a file with no Asset column is refused, and says which column it wanted",
       "Asset" in str(e) and "name" in str(e))

print("\n%d passed, %d failed" % (P, len(F)))
for n in F:
    print("  FAILED: %s" % n)
sys.exit(1 if F else 0)
