"""tests/test_assets_formats.py — method 2 of the asset engine, with the model stubbed.

Proves the plumbing and the rules the original enforces in code, not whether the model's judgment
is any good. Only a real run shows that.

What it holds the builder to:
  - the proven-format table is read from disk, all 19 rows, never recalled by a model
  - a format the pre-screen drops is logged with its reason and never reaches step B
  - the pre-screen matches its answers back BY FORMAT NAME, so a short reply cannot shift them
  - brand_fit on a row comes from step C's Ownability test and from nowhere else, even when the
    pre-screen said something different
  - linkability's keep-or-drop line is the shared one, applied in code at the shared floor
  - an idea the judge never returned a row for is neither kept nor dropped on a default
  - the sort is brand fit, then evidence x beatability, then effort
  - every step is resumable, and a redo really redoes
  - no prompt reaches the model with an unfilled {{TOKEN}}

The stubs live in this file rather than in _fixture.py because four other asset builders are being
written at the same time and _fixture.py belongs to none of us.
"""
import os
import re
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import llm, store

FAILS = []
CALLS = {"json": 0, "text": 0}
UNFILLED = []
SEEN = []                    # every prompt the model was handed, for the "did it see X" checks


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def calls():
    return CALLS["json"] + CALLS["text"]


# --- the stub model -------------------------------------------------------------------------
# Keyed on the literal output keys each prompt asks for, the way _fixture does it: prompts share
# vocabulary but never share their output shape. Where a prompt hands the model ids, the stub reads
# them back out of the prompt, so a test can prove the matching is done by id and not by position.

DROP_FORMAT = "Controversy / opinion"          # the pre-screen refuses exactly this one
NOT_OWNABLE = "Glossary / terms"               # ownability fails exactly this one
THIN_LINKS = "Facts listicle"                  # linkability scores this one below the floor
NO_VERDICT = "Quiz / typology"                 # the judges return no row at all for this one
LIED_FIT = "Calculator"                        # pre-screen says ADJACENT, ownability says CORE

_IDS = re.compile(r"^### (a\d+)$", re.M)


def _ids(prompt):
    return _IDS.findall(prompt)


def _title(prompt, idea_id):
    """The title line that follows '### <id>' in a judged batch."""
    m = re.search(r"^### %s\n(.*)$" % idea_id, prompt, re.M)
    return m.group(1) if m else ""


def stub_json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    SEEN.append(prompt)
    if "{{" in prompt:
        UNFILLED.append(prompt[:90])

    if '"headline_template"' in prompt and '"formats"' in prompt:          # A2, extra formats
        return {"formats": [
            {"format": "Branded index", "example": "Big Mac Index — https://economist.com/big-mac-index",
             "headline_template": "The [TOPIC] Index", "why_links": "Data"},
            {"format": "Benchmark grader", "example": "HubSpot Website Grader — https://website.grader.com",
             "headline_template": "How does your [TOPIC] compare?", "why_links": "Utility"},
            {"format": "Salary transparency report", "example": "Buffer Open Salaries — https://buffer.com/salaries",
             "headline_template": "The [TOPIC] Report", "why_links": "Data"},
            {"format": "Salary transparency report", "example": "the same one again",
             "headline_template": "x", "why_links": "Data"},
            {"format": "A format I cannot name", "example": "",
             "headline_template": "x", "why_links": "Data"}]}

    if '"in_scope_subject"' in prompt:                                     # A3, the pre-screen
        out = []
        for line in prompt.splitlines():
            m = re.match(r"- (.+?) — earns links through ", line)
            if not m:
                continue
            fmt = m.group(1)
            if fmt == DROP_FORMAT:
                out.append({"format": fmt, "keep": False,
                            "drop_reason": "no in-scope subject; picking a public fight is not ours"})
            elif fmt == NO_VERDICT:
                continue                        # the pre-screen forgets this one entirely
            else:
                out.append({"format": fmt, "keep": True,
                            "in_scope_subject": "Cost of a bad hire",
                            "brand_fit": "ADJACENT" if fmt == LIED_FIT else "CORE",
                            "transplant_from": "cost-of-living" if fmt == LIED_FIT else ""})
        return {"screened": out}

    if '"what_it_would_be"' in prompt:                                     # B, one adaptation
        fmt = re.search(r"link-bait format: \*\*(.+?)\*\* \(headline", prompt).group(1)
        return {"our_topic": "Cost of a mis-hire, per role",
                "distinct_angle": "Built on our own aggregate hire-cost data, per role, which no "
                                  "consultancy publishes",
                "asset": ("What a Bad Hire Really Costs, Per Role — %s" % fmt) if fmt != LIED_FIT
                         else "Bad-Hire Cost Calculator, per role",
                "tool_escalation": "interactive calculator" if fmt == LIED_FIT else "",
                "headline": "What does a bad hire actually cost you?",
                "what_it_would_be": "A four-input form, a sourced formula and a sharable PDF.",
                "source_niche": "finance"}

    if '"brand_fit": "CORE"' in prompt:                                    # the shared ownability test
        out = []
        for i in _ids(prompt):
            t = _title(prompt, i)
            if NOT_OWNABLE in t:
                out.append({"id": i, "verdict": False, "brand_fit": "", "why": "no standing here"})
            elif NO_VERDICT in t:
                continue                        # judged blind: no row comes back for this idea
            elif LIED_FIT in t or "Calculator" in t:
                out.append({"id": i, "verdict": True, "brand_fit": "CORE", "transplant_from": "",
                            "why": "we hold the hire-cost data"})
            else:
                out.append({"id": i, "verdict": True, "brand_fit": "TRANSPLANT",
                            "transplant_from": "cost-of-living", "why": "the shape travels"})
        return out

    if '"score": 3' in prompt:                                             # the shared linkability test
        out = []
        for i in _ids(prompt):
            t = _title(prompt, i)
            if NO_VERDICT in t:
                continue
            out.append({"id": i, "score": 1 if THIN_LINKS in t else 4, "why": "stubbed"})
        return out

    if '"beatability": 3' in prompt:                                       # D, the scores
        out = []
        for n, i in enumerate(_ids(prompt)):
            out.append({"id": i, "beatability": 3 if n % 2 == 0 else 1,
                        "effort": "S" if n % 2 == 0 else "L"})
        return out

    return _fixture.stub_json(prompt, system, retries)


def stub_text(prompt, system=None, **kw):
    CALLS["text"] += 1
    SEEN.append(prompt)
    if "{{" in prompt:
        UNFILLED.append(prompt[:90])
    return _fixture.stub_text(prompt, system)


llm.json_call = stub_json
llm.text = stub_text

from seo_agent.assets import _common as cm, formats            # noqa: E402


# --- the inputs -------------------------------------------------------------------------------

SCOPE = """# Brand scope — Example

## What we are
We run skills assessments for hiring teams.

## Subjects we own
- Cost of a bad hire, because we hold aggregate per-role hiring data.
- Skills testing, because it is the product.

## Subjects we do NOT own
- Payroll. We do not touch it.

## What we have that others do not
- Aggregate pass-rate data across 1,500 hiring teams.
"""

CO = {"brand": "Example", "domain": "example.com",
      "niche_definition": "skills assessment for hiring teams"}
SAID = []


def say(label, note=""):
    SAID.append((label, note))


def plant():
    kd = store.knowledge_dir()
    shutil.rmtree(os.path.join(kd, "assets"), ignore_errors=True)
    cm.save("scope.md", SCOPE)
    store.save_knowledge("brand/brand-voice.md", "# Voice\nDirect. A number before an adjective.\n")
    store.save_knowledge("brand/features.md", "# Features\n- Skills tests, 1,500 of them.\n")
    store.save_knowledge("brand/stats.md", "# Stats\n- 1,500 hiring teams.\n- 55% faster time-to-hire.\n")


plant()

print("\nstep A — the swipe library")
table = formats.swipe_table()
ok("the proven table is read off disk, all 19 rows", len(table) == 19, len(table))
ok("every row carries the four columns, none empty",
   all(r["format"] and r["example"] and r["headline_template"] and r["why_links"] for r in table),
   [r for r in table if not all((r["format"], r["example"], r["headline_template"], r["why_links"]))][:1])
ok("bold and the (agent knowledge) marker come off the format name only",
   "Calculator" in [r["format"] for r in table]
   and "Branded index" in [r["format"] for r in table]
   and not any("*" in r["format"] for r in table),
   [r["format"] for r in table][:4])
ok("the example cells are left verbatim, markdown and all",
   any("*" in r["example"] for r in table))
ok("the table rows are tagged as the proven half", all(r["source"] == "table" for r in table))

print("\nthe whole builder")
out = formats.run(CO, say, redo=True)
rows = cm.read("formats.json")
swipe = cm.read(formats.WORK + "swipe.json")
adapt = cm.read(formats.WORK + "adaptations.json")
filt = cm.read(formats.WORK + "filtered.json")

ok("it writes assets/formats.json and says so", out["files"] == ["formats.json"] and isinstance(rows, list))
ok("every working file a person can open is there",
   all(cm.exists(formats.WORK + n) for n in
       ("swipe.json", "format-swipe.md", "adaptations.json", "filtered.json", "scored.json", "run-log.md")),
   os.listdir(os.path.join(store.knowledge_dir(), "assets", "_work", "formats")))

print("\nA2 — the model's own knowledge, added and checked")
added = [f for f in swipe["kept"] if f["source"] == "model"]
ok("model formats are added on top of the table", len(added) == 2, [f["format"] for f in added])
ok("a format the model could not name an example for is refused",
   not any(f["format"] == "A format I cannot name" for f in swipe["kept"]))
ok("a format the proven table already has is not added a second time",
   [f["format"] for f in swipe["kept"]].count("Branded index") == 1
   and [f for f in swipe["kept"] if f["format"] == "Branded index"][0]["source"] == "table",
   [f["format"] for f in swipe["kept"] if f["format"] == "Branded index"])
ok("a format the model returned twice in one reply is added once",
   [f["format"] for f in swipe["kept"]].count("Salary transparency report") == 1)
ok("model rows are marked as model knowledge, not as proven",
   all(f["source"] == "model" for f in added) and len([f for f in swipe["kept"] if f["source"] == "table"]) >= 17)

print("\nA3 — the pre-screen")
ok("the format with no in-scope subject is dropped",
   [d["format"] for d in swipe["dropped"]] == [DROP_FORMAT], swipe["dropped"])
ok("the drop carries the reason, so the cut is auditable",
   "not ours" in swipe["dropped"][0]["why"], swipe["dropped"])
ok("a dropped format never reaches step B",
   not any(a["format"] == DROP_FORMAT for a in adapt))
ok("a format the pre-screen forgot is kept, not silently dropped",
   any(f["format"] == NO_VERDICT for f in swipe["kept"])
   and [f for f in swipe["kept"] if f["format"] == NO_VERDICT][0]["prescreen_note"],
   [f["format"] for f in swipe["kept"]])
ok("answers are matched back by format name, so a short reply cannot shift them",
   all(f["in_scope_subject"] == "Cost of a bad hire"
       for f in swipe["kept"] if f["format"] != NO_VERDICT))
ok("format-swipe.md is one row per surviving format, marked rough",
   cm.read(formats.WORK + "format-swipe.md").count("\n| ") == len(swipe["kept"]) + 1
   and "ROUGH pre-screen" in cm.read(formats.WORK + "format-swipe.md"))

print("\nB — one adaptation per format, substance before the label")
ok("one adaptation per surviving format, never five", len(adapt) == len(swipe["kept"]), (len(adapt), len(swipe["kept"])))
ok("the adaptation carries the swipe row forward, so nothing is re-decided",
   all(a["example"] and a["headline_template"] and a["source_niche"] for a in adapt))
ok("the rough tag is carried in the working file only, never as brand_fit",
   all("prescreen_fit" in a for a in adapt) and not any("brand_fit" in a for a in adapt))
adapt_prompt = [p for p in SEEN if "Return these fields in THIS order" in p][0]
returns = adapt_prompt.split("Return these fields in THIS order", 1)[1]
ok("the adapt prompt asks for the topic, then the angle, then the name",
   returns.index("`our_topic`") < returns.index("`distinct_angle`") < returns.index("`asset`"))
ok("the adapt prompt is handed the scope, the voice, the product and the numbers",
   "1,500 hiring teams" in adapt_prompt and "Direct. A number" in adapt_prompt
   and "Skills tests" in adapt_prompt and "Payroll" in adapt_prompt)
ok("the adapt prompt refuses to ask for a brand fit", "Do NOT return a brand fit" in adapt_prompt)

print("\nC — the real gate, and the one place brand_fit is decided")
kept_ids = {r["id"] for r in rows}
ok("the idea that fails ownability is dropped",
   not any(NOT_OWNABLE in r["title"] for r in rows)
   and any(NOT_OWNABLE in d["title"] for d in filt["dropped"]),
   [d["title"] for d in filt["dropped"]])
ok("the idea nobody would cite is dropped at the shared floor",
   not any(THIN_LINKS in r["title"] for r in rows)
   and any("linkability: 1 of 4, needs 3" in d["why"] for d in filt["dropped"]),
   [d["why"] for d in filt["dropped"]])
ok("a drop names which test failed", all(d["why"] for d in filt["dropped"]))
ok("the idea no judge returned a row for is kept and flagged, not defaulted either way",
   any(NO_VERDICT in r["title"] for r in rows) and len(filt["unjudged"]) == 1
   and [r for r in rows if NO_VERDICT in r["title"]][0]["ownability"]["verdict"] is None,
   filt["unjudged"])
lied = [r for r in rows if r["format"] == LIED_FIT]
ok("brand_fit comes from step C's ownability, overruling the rough pre-screen",
   lied and lied[0]["brand_fit"] == "CORE"
   and [f for f in swipe["kept"] if f["format"] == LIED_FIT][0]["prescreen_fit"] == "ADJACENT",
   lied and lied[0]["brand_fit"])
ok("transplant_from is filled where the tag says TRANSPLANT",
   all(r["transplant_from"] for r in rows if r["brand_fit"] == "TRANSPLANT"))
ok("linkability keeps the score, the of, and the code-derived verdict",
   all(r["linkability"]["of"] == 4 and r["linkability"]["verdict"] is True
       for r in rows if r["linkability"]["score"] >= cm.LINKABILITY_FLOOR),
   [r["linkability"] for r in rows][:2])
own_prompt = [p for p in SEEN if "OWNABLE when a reader" in p][0]
ok("the ownability judge is shown the scope, so it is not judging blind", "Payroll" in own_prompt)
ok("the competitor set is deliberately not passed, as the original says",
   "(no competitor set on file yet)" in own_prompt)

print("\nD — the scores")
ok("beatability is 1 to 3 and effort is S/M/L on every row",
   all(r["beatability"] in (1, 2, 3) and r["effort"] in ("S", "M", "L") for r in rows),
   [(r["beatability"], r["effort"]) for r in rows][:4])

print("\nE — the pool, assembled and sorted")
ok("every row is a full idea row, no half shapes",
   all(set(r) == set(cm.blank_idea("x", "y")) for r in rows),
   [set(rows[0]) ^ set(cm.blank_idea("x", "y"))] if rows else "")
ok("ids sit in method 2's band so three pools cannot collide",
   all(r["id"].startswith("a2") for r in rows), [r["id"] for r in rows][:3])
ok("ids are unique", len({r["id"] for r in rows}) == len(rows))
ok("every row is tagged with this method", all(r["method"] == ["model-other-niches"] for r in rows))
ok("ranking, dedup and the reuse verdict are left to the merge",
   all(r["rank"] is None and r["reuse"]["verdict"] == "" and r["status"] == "open" for r in rows))
ok("proof carries the format's real example, with no invented domain count",
   all(r["proof"] and r["proof"][0]["what"] and r["proof"][0]["domains"] is None for r in rows),
   rows[0]["proof"] if rows else "")
ok("sorted CORE first, then TRANSPLANT, then ADJACENT",
   [formats.FIT_ORDER.get(r["brand_fit"], 3) for r in rows]
   == sorted(formats.FIT_ORDER.get(r["brand_fit"], 3) for r in rows),
   [r["brand_fit"] for r in rows])
ok("within one brand fit, evidence x beatability decides, then effort",
   [formats.sort_key(r) for r in rows] == sorted(formats.sort_key(r) for r in rows))

print("\nthe run log")
log = cm.read(formats.WORK + "run-log.md")
ok("the run log names every format dropped at the pre-screen", DROP_FORMAT in log)
ok("the run log names every idea dropped at the gate",
   all(d["title"][:30] in log for d in filt["dropped"]), log[:400])
ok("the run log names the ideas nobody judged", filt["unjudged"][0] in log)

print("\nwhat a person is asked to look at")
notes = " ".join(out["needs_review"])
ok("the unjudged idea is raised", "no verdict" in notes, out["needs_review"])
ok("a title that still names the shape is raised, not silently rewritten",
   "name the shape" in notes and any("Calculator" in r["title"] for r in rows), out["needs_review"])
ok("an idea that cannot be written from desk research is raised, never hidden",
   "desk research" in notes and "interactive calculator" in notes, out["needs_review"])

print("\nresume")
before = calls()
out2 = formats.run(CO, say, redo=False)
ok("a second run rebuilds nothing and calls no model", calls() == before and out2["files"] == ["formats.json"])
os.remove(cm.path("formats.json"))
before = calls()
formats.run(CO, say, redo=False)
ok("with the pool gone but the working files there, it re-assembles without the model",
   calls() == before and isinstance(cm.read("formats.json"), list))
os.remove(cm.path(formats.WORK + "scored.json"))
os.remove(cm.path("formats.json"))
before = calls()
formats.run(CO, say, redo=False)
ok("a missing step file is the only one redone", 0 < calls() - before <= 3, calls() - before)
before = calls()
formats.run(CO, say, redo=True)
ok("a redo really redoes every step", calls() - before > 10, calls() - before)

print("\nrefusals")
os.remove(cm.path("scope.md"))
os.remove(cm.path("formats.json"))
shutil.rmtree(os.path.join(store.knowledge_dir(), "assets", "_work"), ignore_errors=True)
try:
    formats.run(CO, say, redo=True)
    ok("it refuses to run without the brand scope", False, "it ran anyway")
except RuntimeError as e:
    ok("it refuses to run without the brand scope, in plain words", "scope.md" in str(e), e)
cm.save("scope.md", SCOPE)

print("\nprompts")
ok("no prompt reached the model with an unfilled {{TOKEN}}", not UNFILLED, UNFILLED[:2])
ok("every prompt this builder owns is on disk",
   all(os.path.exists(os.path.join(cm.PROMPTS, n + ".md")) for n in
       ("formats-swipe-library", "formats-extra", "formats-prescreen", "formats-adapt", "formats-score")))

print("\nStubbed model. Proves the plumbing, the code-enforced rules and resume, not judgment quality.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all method 2 checks passed")
