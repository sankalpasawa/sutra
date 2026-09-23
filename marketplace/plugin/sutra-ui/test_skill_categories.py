"""Every skill lands in exactly one category, and a guess reads as a guess.

Run: python3 test_skill_categories.py

The framework is holding/plans/skills-program/FRAMEWORK.md. What this asserts:
the seven are closed, every named skill we ship is categorised by hand, the
rules are readable and ordered, an unknown falls back to Know rather than to a
claim, and the real catalogue on this box comes out fully categorised.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import skill_categories as SC  # noqa: E402

FAIL = []
N = 0


def check(name, cond, detail=""):
    global N
    N += 1
    if not cond:
        FAIL.append("%s%s" % (name, (" -- " + detail) if detail else ""))


# ── 1. the closed lists ─────────────────────────────────────────────────────

check("seven categories", len(SC.CATEGORIES) == 7, str(SC.CATEGORIES))
check("the seven are the framework's seven",
      set(SC.CATEGORIES) == {"Judge", "Shape", "Make", "Say", "Run", "Know", "Mend"})
check("five moments", len(SC.MOMENTS) == 5, str(SC.MOMENTS))
check("every category has a test a person can run",
      all(SC.CATEGORY_TEST.get(c) for c in SC.CATEGORIES))
check("every test is a question", all(t.strip().endswith("?") for t in SC.CATEGORY_TEST.values()))

# ── 2. the named list is well formed ────────────────────────────────────────

for name, pair in SC.NAMED.items():
    cat, moment = pair
    check("named %s: category is one of the seven" % name, cat in SC.CATEGORIES, cat)
    check("named %s: moment is one of the five" % name, moment in SC.MOMENTS, moment)
    check("named %s: key is lower case" % name, name == name.lower())

check("the governance floor is named, not ruled",
      all(k in SC.NAMED for k in ("input-routing", "depth-estimation", "blueprint",
                                  "human-sutra", "writing-style", "flow", "lens")))
check("the per-turn floor judges or says, never makes",
      all(SC.NAMED[k][0] in ("Judge", "Say", "Shape")
          for k in ("input-routing", "depth-estimation", "blueprint", "human-sutra",
                    "writing-style")))
check("every per-turn skill carries the every-turn moment",
      SC.NAMED["input-routing"][1] == "every-turn"
      and SC.NAMED["human-sutra"][1] == "every-turn")
check("the review lanes judge", SC.NAMED["codex-sutra"][0] == "Judge"
      and SC.NAMED["deepseek"][0] == "Judge")
check("debugging mends", SC.NAMED["systematic-debugging"][0] == "Mend")

# ── 3. the rules ────────────────────────────────────────────────────────────

check("rules are ordered strongest effect first",
      [c for c, _m, _p in SC._RULES][:3] == ["Mend", "Run", "Judge"],
      str([c for c, _m, _p in SC._RULES]))
check("every rule names a category from the seven",
      all(c in SC.CATEGORIES for c, _m, _p in SC._RULES))
check("every rule names a moment from the five",
      all(m in SC.MOMENTS for _c, m, _p in SC._RULES))
check("no rule is longer than three lines",
      all(len(p.splitlines()) <= 3 for _c, _m, p in SC._RULES))

RULED = [
    ("runs the incident from triage to the all-clear", "Mend"),
    # a deployment that can roll back still STARTS from a deployment, so the
    # credential is what makes it different: Run, not Mend. Mend is for work
    # that begins at the failure.
    ("deploy the project and roll back if the smoke fails", "Run"),
    ("recover the database after the failed migration", "Mend"),
    ("open a browser and check the flow with playwright", "Run"),
    ("review the diff and refuse anything that breaks the contract", "Judge"),
    ("create a slide deck from the outline", "Make"),
    ("plan the migration in phases before any code moves", "Shape"),
    ("rewrite the update in the company's tone", "Say"),
]
for desc, want in RULED:
    cat, moment, how = SC.classify({"name": "unlisted-" + want, "description": desc})
    check("ruled: %r -> %s" % (desc[:34], want), cat == want, "got %s (%s)" % (cat, how))
    check("ruled: %r carries a moment" % desc[:20], moment in SC.MOMENTS)
    check("ruled: %r says it was ruled" % desc[:20], how == "ruled", how)

# ── 4. the fallback is the weakest claim ────────────────────────────────────

cat, moment, how = SC.classify({"name": "nothing-declared", "description": "A thing."})
check("an undeclared skill falls back to Know", cat == "Know", cat)
check("the fallback says so", how == "fallback", how)
check("the fallback moment is on-ask", moment == "on-ask", moment)
check("an empty entry does not crash", SC.classify({})[0] in SC.CATEGORIES)
check("a None entry does not crash", SC.classify(None)[0] in SC.CATEGORIES)
check("a named skill beats its description",
      SC.classify({"name": "blueprint", "description": "create a deck"})[0] == "Judge")

# ── 5. annotate, and the real catalogue on this box ─────────────────────────

rows = [{"name": "blueprint", "description": ""},
        {"name": "unlisted", "description": "deploy to production"},
        {"name": "mystery", "description": "A thing."}]
facets = SC.annotate(rows)
check("annotate writes the category on every row",
      all(r.get("category") in SC.CATEGORIES for r in rows))
check("annotate writes the moment on every row",
      all(r.get("moment") in SC.MOMENTS for r in rows))
check("annotate writes how it decided", all(r.get("category_how") for r in rows))
check("counts add up to the rows",
      sum(facets["by_category"].values()) == len(rows))
check("by_how separates decisions from guesses",
      facets["by_how"].get("named") == 1 and facets["by_how"].get("fallback") == 1)

try:
    import skills_catalog
    items = skills_catalog.discover_all(project_dir=None)["items"]
except Exception as exc:  # a box with no catalogue still runs the rest
    items = []
    print("note: the live catalogue could not be read (%s)" % str(exc)[:80])

if items:
    f = SC.annotate(items)
    check("every skill on this box has a category",
          all(e.get("category") in SC.CATEGORIES for e in items))
    check("every skill on this box has a moment",
          all(e.get("moment") in SC.MOMENTS for e in items))
    check("each skill has exactly one category",
          all(isinstance(e.get("category"), str) for e in items))
    check("the counts cover every skill", sum(f["by_category"].values()) == len(items))
    named = f["by_how"].get("named", 0)
    check("most of our own skills are named, not guessed", named >= 40,
          "named=%d of %d" % (named, len(items)))
    fallback = f["by_how"].get("fallback", 0)
    check("the fallback is a minority", fallback <= len(items) // 3,
          "fallback=%d of %d" % (fallback, len(items)))
    print("live catalogue: %d skills, by category %s, by how %s"
          % (len(items), f["by_category"], f["by_how"]))

print("%d checks, %d failed" % (N, len(FAIL)))
for f_ in FAIL:
    print("  FAIL " + f_)
sys.exit(1 if FAIL else 0)
