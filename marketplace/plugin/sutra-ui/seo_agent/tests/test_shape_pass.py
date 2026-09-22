"""tests/test_shape_pass.py — the one step that sees the finished shape may finally fix it.

THE TWO BAD ARTICLES (real output, 2026-09-22, both spotted by Devansh reading the drafts).

BAD 1, the basics arrive last. "Pre-Employment Tests", as planned and as published:

    1. Cognitive ability tests
    2. Personality tests
    3. Skills tests
    4. Situational judgment tests
    5. Emotional intelligence tests
    6. What pre-employment testing is, and why employers use it     <- LAST

Five sections lean on a term the sixth finally explains. The architect's own prompt forbids exactly
this in capitals, and lost: the archetype was `listicle`, whose format rule says the body is "the N
parallel items". A definition is not an item, so it was pushed out to a closer. An advisory rule
lost to a structural one.

BAD 2, the sections walk off in different directions:

    Cognitive Ability Tests: What Score Counts as a Pass
    Pre-Employment Personality Tests and What 'Failing' Means
    Skills Tests: What Counts as a Passing Score
    What Is a Situational Judgment Test, and What Scores Mean
    EQ Tests: Best for Leadership and People-Facing Roles          <- a different question

Four say one thing four ways; the fifth changes the subject. A reader cannot compare cognitive
against EQ, which is the only reason anyone opens a "types of" article. Devansh: "we are talking
about different things for everything."

WHY NOTHING CAUGHT IT. `pass_all` already existed, its prompt already opened "Nobody has yet read
the headings as a set. That is your job", and it already received every heading AND every job. Then:

    "You may not add, remove or reorder sections -- same headings, same count, same order,
     in and out."

The one step that could see the whole shape was forbidden from changing it. Worse, it was told to
"BREAK THE TEMPLATE" when four headings share a construction -- so with four headings about pass
scores it varied the fifth by changing its AXIS. BAD 2 is that instruction working as written.

What this pins:

  1. IT CAN REORDER, and the basics-last article is the fixture.
  2. THE ORDER IS VALIDATED AS A PERMUTATION. A list that adds, drops or repeats a section is
     thrown away WHOLE and the original order stands. A reorder that loses a section is a deletion
     wearing a different hat, and this pass holds no cards to justify one.
  3. SECTIONS TRAVEL WITH THEIR HEADINGS. They are zipped positionally downstream, so a reorder
     that moved one list and not the other would silently put every heading on the wrong prose.
  4. IT CAN REWRITE THE JOBS, because the job is the brief the writer works from. Fixing only the
     headings would have left the five divergent briefs exactly as they were.
  5. IT STILL MAY NOT ADD OR DELETE, and every move is named in the log.

Run: SEO_AGENT_DATA=$(mktemp -d) bash seo_agent/tests/run_all.sh
"""
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm
from seo_agent.write import headings as H

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


STAKES = ["What is pre-employment testing? (definition)",
          "Why employers use pre-employment tests",
          "X types of pre-employment tests"]


def _fixture_article():
    """The real bad article: five type sections, the definition last."""
    secs = [{"job": "settle what score passes", "covers": None},
            {"job": "settle what managers misread", "covers": None},
            {"job": "how it differs from cognitive", "covers": None},
            {"job": "what to read into a score", "covers": None},
            {"job": "who they suit", "covers": None},
            {"job": "close by defining the subject", "covers": STAKES[0]}]
    recs = [{"n": 1, "heading": "Cognitive Ability Tests: What Score Counts as a Pass"},
            {"n": 2, "heading": "Personality Tests and What 'Failing' Means"},
            {"n": 3, "heading": "Skills Tests: What Counts as a Passing Score"},
            {"n": 4, "heading": "What Is a Situational Judgment Test"},
            {"n": 5, "heading": "EQ Tests: Best for Leadership and People-Facing Roles"},
            {"n": 6, "heading": "What Pre-Employment Testing Is"}]
    return secs, recs


def _run(reply):
    secs, recs = _fixture_article()
    seen = {}
    _orig = llm.json_call

    def fake(p, **k):
        seen["p"] = p
        return reply

    llm.json_call = fake
    try:
        n, notes, log = H.pass_all({"title": "T", "angle": "A", "spine": "S", "persona": "P"},
                                   {"primary": "pre employment tests"}, secs, recs, {},
                                   lambda *a: None, table_stakes=STAKES)
    finally:
        llm.json_call = _orig
    return secs, recs, log, seen.get("p", "")


# ---- 1. it sees what it needs -------------------------------------------------------------------
print("the pass finally sees the whole shape")

_s, _r, _l, prompt = _run({"headings": []})
ok("it is shown what every ranking page covers, in page order", STAKES[0] in prompt)
ok("and each section's own 'covers' label, which nobody read before",
   "covers the expected topic" in prompt)
ok("the jobs are shown, because the job is what steers the writing", "job:" in prompt)
ok("the real bad article is in the prompt as the example", "LAST" in prompt)
ok("and the second bad article too", "a different question" in prompt)
ok("every token was filled", "{{" not in prompt, prompt[:160])


# ---- 2. the basics-last article is fixed ---------------------------------------------------------
print("\nthe basics-last article is reordered")

secs, recs, log, _p = _run({"order": [6, 1, 2, 3, 4, 5], "why_order": "the definition comes first",
                            "headings": []})
ok("the definition is now the first section", recs[0]["n"] == 6, [r["n"] for r in recs])
ok("SECTIONS travelled with their headings, or every heading would sit on the wrong prose",
   secs[0]["job"] == "close by defining the subject", secs[0]["job"])
ok("nothing was added or lost", sorted(r["n"] for r in recs) == [1, 2, 3, 4, 5, 6])
ok("and the move is on the record, never silent",
   any(x.get("reordered") for x in log), log)


# ---- 3. a broken order is thrown away WHOLE ------------------------------------------------------
print("\na broken order is refused entirely, not partly applied")

for name, bad in [("one section dropped", [6, 1, 2, 3, 4]),
                  ("a section repeated", [6, 6, 1, 2, 3, 4]),
                  ("a section invented", [6, 1, 2, 3, 4, 99]),
                  ("not numbers at all", ["six", "one"])]:
    secs, recs, log, _p = _run({"order": bad, "headings": []})
    ok("%s: the original order stands" % name,
       [r["n"] for r in recs] == [1, 2, 3, 4, 5, 6], [r["n"] for r in recs])

secs, recs, log, _p = _run({"order": [6, 1, 2, 3, 4], "headings": []})
ok("and the refusal is logged, so a lost fix is not invisible",
   any("order refused" in str(x.get("why", "")) for x in log), log)

secs, recs, log, _p = _run({"headings": []})
ok("no order at all is fine: the article keeps the order it came in with",
   [r["n"] for r in recs] == [1, 2, 3, 4, 5, 6])


# ---- 4. the jobs can be rewritten ----------------------------------------------------------------
print("\nthe jobs can be rewritten, because the job is the brief")

secs, recs, log, _p = _run({"headings": [
    {"n": 5, "heading": "EQ Tests: What Score Counts as a Pass", "job": "settle what score passes",
     "changed": True, "why": "same question as the rest", "why_job": "it had drifted to fit"}]})
ok("the divergent section's job is brought back onto the shared question",
   secs[4]["job"] == "settle what score passes", secs[4]["job"])
ok("and its heading moved with it",
   recs[4]["heading"] == "EQ Tests: What Score Counts as a Pass", recs[4]["heading"])
ok("the job change is logged with its reason",
   any(x.get("job") for x in log), log)

secs, recs, log, _p = _run({"headings": [{"n": 1, "heading": recs and "Cognitive Ability Tests: What Score Counts as a Pass",
                                          "changed": False}]})
ok("a job nobody rewrote is left exactly alone",
   secs[0]["job"] == "settle what score passes", secs[0]["job"])


# ---- 5. it still may not add or delete ------------------------------------------------------------
print("\nit still may not add or delete a section")

secs, recs, log, _p = _run({"headings": [{"n": 99, "heading": "A section nobody planned", "changed": True}]})
ok("a heading for a section that does not exist is ignored",
   len(recs) == 6 and all(r["n"] != 99 for r in recs), [r["n"] for r in recs])
ok("the prompt says outright that adding or removing is not allowed",
   "may not add or remove" in prompt.lower())
ok("and that a set of parallel sections keeps one question",
   "never vary the question" in prompt.lower())


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all shape-pass checks passed")
