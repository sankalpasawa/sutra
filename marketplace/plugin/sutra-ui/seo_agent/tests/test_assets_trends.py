"""tests/test_assets_trends.py — method 3 (study trends), with the model and Reddit stubbed.

Proves the plumbing and the rules the original enforces in code: the subreddit approval really is a
gate (nothing is scraped before it), the merge check is written before the tensions it gates, every
scraped post is placed exactly once, the closed vocabularies hold, the two judgments are the shared
ones from `_common`, the self-audit gate stops a bad sort before it is filtered, and the final gate
decides whether the pool is handed on at all. It also proves the honest-failure paths: a Reddit that
refuses everything produces an empty pool with a written reason and never an invented post.

What this does NOT prove is whether the tensions or the ideas are any good. Only a real run does that.
"""
import os
import re
import sys
import tempfile

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store
from seo_agent.assets import _common as cm
from seo_agent.assets import trends
from seo_agent.brand import _common as bcm
from seo_agent.brand import field_sources as fs

trends.THROTTLE = 0
fs.THROTTLE = 0

FAILS = []
CALLS = {"json": 0, "text": 0}
FETCHED = []
UNFILLED = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


def say(label, note=""):
    pass


# --- the fake niche ------------------------------------------------------------------------------
# Four groups of posts. Three become tensions; the fourth is the one that lands in misc and has to be
# re-mined into a tension of its own, because the original makes that step required, not optional.
GROUPS = {
    "remote": ["fake remote listings", "secretly onsite", "remote then rto"],
    "ghosted": ["ghosted after interview", "no reply ever", "silence for weeks"],
    "rounds": ["endless interview rounds", "five rounds deep"],
    "odd": ["unpaid take home", "week long task"],
}
SENTENCE = {
    "remote": "Candidates apply for roles advertised as remote that turn out to be onsite.",
    "ghosted": "Candidates hear nothing back after being ghosted following hours of interviews.",
    "rounds": "Candidates are dragged through five or more interview rounds for one role.",
    "odd": "Candidates are handed an unpaid take-home task that costs them a week.",
}
PHRASE_GROUP = {ph: g for g, phs in GROUPS.items() for ph in phs}

SUBS = ["recruiting", "AskHR", "humanresources"]
POSTS = []          # (post_id, subreddit, group, score, comments)
_n = 0
for _sub, _plan in (("recruiting", ["remote"] * 3 + ["ghosted"] * 2 + ["odd"] * 1),
                    ("AskHR", ["remote"] * 3 + ["rounds"] * 2 + ["odd"] * 1),
                    ("humanresources", ["ghosted"] * 3 + ["rounds"] * 3 + ["odd"] * 1)):
    for _g in _plan:
        _n += 1
        POSTS.append(("p%02d" % _n, _sub, _g, 100 + _n, 20 + _n))
BY_ID = {p[0]: p for p in POSTS}


def _listing(sub):
    out = []
    for pid, s, g, score, ncom in POSTS:
        if s != sub:
            continue
        out.append('<div class="thing" data-fullname="t3_%s" data-subreddit="%s" data-score="%d" '
                   'data-comments-count="%d" data-author="someone" data-timestamp="2026-01-01" '
                   'data-permalink="/r/%s/comments/%s/t/" data-url="">'
                   '<a class="title may-blank " href="#">A post about %s hiring</a></div>'
                   % (pid, s, score, ncom, s, pid, g))
    return "<html><body>" + "".join(out) + "</body></html>"


def _post_page(pid):
    g = BY_ID[pid][2]
    return ("<html><body><div class=\"thing\"><div class=\"md\"><p>This happened to me, %s.</p></div>"
            "</div>class=\"commentarea\"<div class=\"md\"><p>Same here, %s again.</p></div>"
            "<div class=\"md\"><p>It is always %s.</p></div><div class=\"side\">sidebar</div>"
            "</body></html>" % (g, g, g))


LOGIN = '<html><head><title>Welcome to Reddit</title></head><body>log in</body></html>'
BLOCK_ALL = {"on": False}


def fake_fetch(url):
    FETCHED.append(url)
    if BLOCK_ALL["on"]:
        return LOGIN
    if "/search?q=" in url:
        return LOGIN                                   # the activity probe: unknown, never empty
    m = re.search(r"/r/([A-Za-z0-9_]+)/comments/(\w+)/", url)
    if m:
        return _post_page(m.group(2))
    m = re.search(r"/r/([A-Za-z0-9_]+)/top/", url)
    if m:
        return _listing(m.group(1))
    return None


fs.fetch = fake_fetch

# The scrape moved off old.reddit HTML and onto research/reddit.py on 2026-09-09, because old.reddit
# login-walls even a real browser and this builder was coming back empty every single time while
# reporting it as "nobody talks about this". So the stub moves with it: same fixture data, new
# transport. BLOCK_ALL still makes every call unknown, which is what the refusal checks below need.
from seo_agent.research import reddit as _reddit          # noqa: E402


def _fake_top(sub, limit=25, period="year", fetch_fn=None):
    FETCHED.append("top:" + sub)
    if BLOCK_ALL["on"]:
        return {"state": "unknown", "posts": [], "reason": "Reddit served a login page"}
    rows = [{"id": pid, "subreddit": s_, "title": "A post about %s hiring" % g,
             "text": "This happened to me, %s." % g,
             "author": "someone", "score": score, "num_comments": ncom, "created_utc": 0.0,
             "url": "https://www.reddit.com/r/%s/comments/%s/t/" % (s_, pid), "permalink": ""}
            for pid, s_, g, score, ncom in POSTS if s_ == sub][:limit]
    return {"state": "ok" if rows else "empty", "posts": rows, "reason": ""}


def _fake_comments(post_id, limit=20, sort="top", fetch_fn=None):
    FETCHED.append("comments:" + post_id)
    if BLOCK_ALL["on"]:
        return {"state": "unknown", "comments": [], "reason": "Reddit served a login page"}
    g = BY_ID[post_id][2]
    return {"state": "ok", "reason": "", "comments": [
        {"text": "This happened to me, %s." % g}, {"text": "Same here, %s again." % g},
        {"text": "It is always %s." % g}]}


_reddit.top = _fake_top
_reddit.comments = _fake_comments


# --- the model stub ------------------------------------------------------------------------------

def _ids_in_cards(p):
    return re.findall(r"^### (\S+) \| r/", p, re.M)


def _tension_codes(p):
    return re.findall(r"^(T\d+) \| (.+)$", p, re.M)


def _group_of_sentence(s):
    for g, sent in SENTENCE.items():
        if sent == s.strip() or g in s.lower():
            return g
    return ""


def stub_json(prompt, system=None, retries=1, **kw):
    CALLS["json"] += 1
    p = prompt
    if "{{" in p:
        UNFILLED.append(p[:90])

    if '"post_id": "<the id, verbatim>"' in p:                       # 2a phrases
        out = []
        for pid in _ids_in_cards(p):
            out.append({"post_id": pid, "phrases": list(GROUPS[BY_ID[pid][2]])})
        return {"posts": out}

    if "## The phrases, each with the post ids it came from" in p:   # 2b consolidate
        seen = {}
        for line in re.findall(r"^- (.+?)  \[(.*?)\]$", p, re.M):
            ph, ids = line[0].strip(), [x.strip() for x in line[1].split(",") if x.strip()]
            g = PHRASE_GROUP.get(ph)
            if g:
                seen.setdefault(g, []).append({"phrase": ph, "post_ids": ids})
        # The odd group does not surface on the first pass: its phrases sit in a long list and no
        # shared pain comes out of them, so they land in orphans and their posts land in misc. Only
        # when misc is re-mined on its own do they group. That is the path stage 2c has to walk.
        alone = list(seen) == ["odd"]
        want = ["odd"] if alone else [g for g in ("remote", "ghosted", "rounds") if g in seen]
        return {"tensions": [{"tension": SENTENCE[g], "phrases": seen[g]} for g in want],
                "orphans": [] if alone else [{"phrase": x["phrase"], "post_ids": x["post_ids"]}
                                             for x in seen.get("odd", [])]}

    if '"per_phrase"' in p:                                          # 2b merge check
        checked = []
        for sent, phrases in re.findall(r"^- (.+)\n  phrases: (.+)$", p, re.M):
            phs = [x.strip() for x in phrases.split(";") if x.strip()]
            checked.append({"original": sent, "verdict": "PASS", "shared_pain": sent,
                            "per_phrase": [{"phrase": x, "fits": True} for x in phs],
                            "result_tensions": [{"tension": sent,
                                                 "phrases": [{"phrase": x, "post_ids": []} for x in phs]}]})
        return {"checked": checked, "orphans": []}

    if '"assignments"' in p:                                          # 2c assign
        codes = _tension_codes(p)
        out = []
        for pid in _ids_in_cards(p):
            g = BY_ID[pid][2]
            tid = next((c for c, s in codes if _group_of_sentence(s) == g), "misc")
            out.append({"post_id": pid, "tension_id": tid, "secondary_id": ""})
        return {"assignments": out}

    if '"records"' in p:                                              # 2d records
        out = []
        for i, (code, sent) in enumerate(_tension_codes(p)):
            g = _group_of_sentence(sent)
            subq = ["Who should pay for the time this costs?", "How long is too long?"]
            if i == 0:
                subq.append("Should Example publish its own numbers on this?")   # a product leak
            out.append({"tension_id": code, "core_pain": "People lose time they cannot get back.",
                        "audience": "candidate",
                        "emotion": "frustration" if i == 0 else "anger",       # outside the closed set
                        "best_example": "", "representative_quotes": ["It happened to me twice."],
                        "sub_questions": subq,
                        "implied_data_point": "the share of %s postings that end this way" % g})
        return {"records": out}

    if '"asset_title"' in p:                                          # 4 idea
        m = re.search(r"^- Tension: (.+)$", p, re.M)
        g = _group_of_sentence(m.group(1) if m else "")
        return {"asset_title": "The %s Index: what the numbers actually say" % g.title(),
                "what_it_would_be": "A yearly count, published with the method.",
                "unfair_advantage": "our own hiring data",
                "tool_escalation": "a live index anyone can query" if g == "remote" else ""}

    if '"brand_fit": "CORE"' in p:                                    # _common.ownability
        out = []
        for iid, title in re.findall(r"^### (a\d+)\n(.*)$", p, re.M):
            g = _group_of_sentence(title)
            fit = "ADJACENT" if g == "rounds" else "CORE"
            out.append({"id": iid, "verdict": True, "brand_fit": fit, "transplant_from": "",
                        "why": "it is our own data"})
        return out

    if "no half marks" in p:                                          # _common.linkability
        score = {"remote": 4, "ghosted": 2, "rounds": 3, "odd": 4}
        out = []
        for iid, title in re.findall(r"^### (a\d+)\n(.*)$", p, re.M):
            out.append({"id": iid, "score": score.get(_group_of_sentence(title), 4),
                        "why": "a real number sits under it"})
        return out

    return _fixture.stub_json(prompt, system, retries)


def stub_text(prompt, system=None, **kw):
    CALLS["text"] += 1
    return _fixture.stub_text(prompt, system)


llm.json_call = stub_json
llm.text = stub_text


# --- a data dir with a brand pack the builder can read --------------------------------------------

def fresh(label):
    store.set_data_dir(tempfile.mkdtemp(prefix="trends-%s-" % label))
    store.save_knowledge("site_index.json", _fixture.SITE_INDEX)
    store.save_knowledge("brand/company.json",
                         {"brand": "Example", "domain": "example.com",
                          "niche_definition": "hiring software", "brand_oneliner": "Example hires better"})
    bcm.save("brand-voice.md", "# Voice\nDirect and concrete.\n")
    bcm.save("features.md", "# Features\nA hiring platform with its own funnel data.\n")
    bcm.save("_work/field-sources/candidates.json", {"candidates": [
        {"name": "recruiting", "who": "in-house recruiters", "covers": "the job", "posts": 9,
         "comments": 400, "verdict": "keep", "why": ""},
        {"name": "AskHR", "who": "HR", "covers": "the job", "posts": 8, "comments": 300,
         "verdict": "keep", "why": ""},
        {"name": "humanresources", "who": "HR", "covers": "the adjacent trade", "posts": 7,
         "comments": 250, "verdict": "keep", "why": ""},
        {"name": "walledsub", "who": "nobody could tell", "covers": "the tier below", "posts": 0,
         "comments": 0, "verdict": "unknown",
         "why": "unverified — Reddit could not be checked (blocked or unreachable); no paid fallback"},
        {"name": "deadsub", "who": "nobody", "covers": "the job", "posts": 1, "comments": 2,
         "verdict": "drop", "why": "only 1 posts / 2 comments in a year"}]})
    cm.save("scope.md", "# Scope\nExample sells hiring software. It is NOT a job board.\n")
    return store.data_dir()


CO = {"brand": "Example", "domain": "example.com", "niche_definition": "hiring software"}


# --- 1. the gate ---------------------------------------------------------------------------------
print("\nthe subreddit gate")
fresh("gate")
out = trends.run(CO, say)
g = out.get("gate") or {}
ok("run() returns a gate instead of waiting", g.get("kind") == "subreddits", out)
ok("the gate carries the proposal and a reason a person can read",
   bool(g.get("proposed")) and len(g.get("why") or "") > 40)
ok("nothing was scraped before the approval", not cm.exists(trends._w("posts.json")) and not cm.exists("trends.json"))
names = [r["name"] for r in g["proposed"]]
ok("the proposal reuses field-sources.md rather than proposing a fresh list",
   set(names) >= {"recruiting", "AskHR", "humanresources"}, names)
ok("a subreddit builder 11 checked and dropped stays dropped", "deadsub" not in names, names)
ok("a subreddit Reddit refused is carried as unverified, not dropped", "walledsub" in names, names)
ok("the gate says out loud which ones could not be checked", "walledsub" in (g.get("why") or ""), g.get("why"))
ok("an unverified candidate is not passed off as checked",
   [r["checked"] for r in g["proposed"] if r["name"] == "walledsub"] == [False])
ok("a second call still gates rather than guessing an answer",
   (trends.run(CO, say).get("gate") or {}).get("kind") == "subreddits")

# --- 2. the full run ------------------------------------------------------------------------------
print("\nthe run, once the subreddits are approved")
cm.save(trends.APPROVED, {"subreddits": SUBS, "at": store.now()})
out = trends.run(CO, say)
ok("the run finishes and writes the pool", out.get("files") == ["trends.json"], out)
pool = cm.read("trends.json") or []
rows = cm.read(trends._w("tensions.json")) or []
amap = {}
for line in (cm.read(trends._w("post-tension-map.tsv")) or "").splitlines()[1:]:
    pid, tid = line.split("\t")[:2]
    amap[pid] = tid

print("\nphase A — the scrape")
posts = (cm.read(trends._w("posts.json")) or {}).get("posts") or []
ok("every approved subreddit was read", len(posts) == len(POSTS), len(posts))
ok("the post body and its comments were read, not just the title",
   all(p["body"] and p["top_comments"] for p in posts[:trends.COMMENT_POSTS]))
ok("a login page served with a success code is blocked, never empty", trends._blocked(LOGIN))
ok("a real listing is not read as blocked", not trends._blocked(_listing("recruiting")))

print("\nstage 2 — phrases into tensions")
ph = cm.read(trends._w("phrases.json")) or {}
ok("every post has a phrase row, even a thin one", set(ph) == {p[0] for p in POSTS}, len(ph))
pm = (cm.read(trends._w("phrase-map.csv")) or "").splitlines()[1:]
ok("the phrase map is one row per distinct phrase",
   len(pm) == len({ln.split(",")[0] for ln in pm if ln.strip()}), len(pm))
mc = cm.read(trends._w("merge-check.md")) or ""
ok("merge-check.md exists and names every tension", all(r["tension_id"] in mc for r in rows), rows and mc[:200])
ok("it records the per-phrase evidence, not just a claim", "fits" in mc and "shared pain written first" in mc)
ok("THE ORDER: the gate was written before the tensions it gates",
   os.path.getmtime(trends._path("merge-check.md")) <= os.path.getmtime(trends._path("tensions.json")))

print("\nstage 2c — every post placed once, and misc re-mined")
ok("every scraped post is placed exactly once", set(amap) == {p[0] for p in POSTS} and len(amap) == len(POSTS))
ok("misc was re-mined, and the count is written down", cm.exists(trends._w("misc-remine.md")))
ok("a 3-post group sitting in misc was promoted to a real tension",
   any(r.get("from_misc") for r in rows), [r["tension_id"] for r in rows])
ok("misc is empty once the promotion happened",
   sum(1 for t in amap.values() if t == "misc") == 0, amap)
ok("a promoted tension went through the same gate",
   all(r["tension_id"] in mc for r in rows if r.get("from_misc")))

print("\nstage 2d — the record, and the closed vocabularies")
ok("the counts are summed from the posts, never asked of the model",
   all(r["n_posts"] == sum(1 for t in amap.values() if t == r["tension_id"]) for r in rows))
ok("upvotes are the real sum",
   all(r["upvotes"] == sum(BY_ID[p][3] for p in r["posts"]) for r in rows))
ok("an emotion outside the closed set is corrected in code",
   all(r["emotion"] in trends.EMOTIONS for r in rows), [r["emotion"] for r in rows])
ok("audience stays inside its closed set", all(r["audience"] in trends.AUDIENCES for r in rows))
ok("a sub-question naming the company is dropped as evidence leaking backwards",
   not any("example" in q.lower() for r in rows for q in r["sub_questions"]),
   [r["sub_questions"] for r in rows])
# www.reddit.com, not old.reddit.com: the scrape moved on 2026-09-09 because old.reddit login-walls
# even a real browser, and this builder was blind.
ok("the best example is a real post URL from that tension's own pile",
   all(r["best_example"].startswith("https://www.reddit.com") for r in rows if r["n_posts"]))

print("\nstage 2.5 — the self-audit gate")
sa = cm.read(trends._w("self-audit.md")) or ""
ok("the audit is written down, box by box", sa.count("- [") == 5, sa)
ok("it passed on this run", "PASS" in sa)

print("\nstage 3 — the two shared tests")
ok("linkability carries the score out of four", all(r["linkability"]["of"] == 4 for r in rows))
ok("the keep-or-drop line is drawn in code at the shared floor",
   all((r["linkability"]["verdict"] is True) == (r["linkability"]["score"] >= cm.LINKABILITY_FLOOR)
       for r in rows))
verdicts = {r["tension_id"]: r["verdict"] for r in rows}
ok("a tension with a low linkability score is dropped however loud it was",
   any(v == "DROP" for v in verdicts.values()), verdicts)
ok("an ADJACENT fit is a maybe, not a keep", any(v == "MAYBE" for v in verdicts.values()), verdicts)
ok("a CORE fit that clears the floor is kept", any(v == "KEEP" for v in verdicts.values()), verdicts)
ok("every tension carries a written reason", all(r["why"] for r in rows))

print("\nstage 4 — the ideas")
ok("one idea per surviving tension",
   len(pool) == sum(1 for r in rows if r["verdict"] in trends.KEPT), (len(pool), verdicts))
ok("an idea row is the shared shape, nothing missing",
   all(set(r) == set(cm.blank_idea("a0001", "study-trends")) for r in pool), pool[:1])
ok("every idea is tagged with this method", all(r["method"] == ["study-trends"] for r in pool))
ok("the ids sit in this method's own band, so the merge can never confuse them with another finder's",
   all(3001 <= int(r["id"][1:]) < 4001 for r in pool), [r["id"] for r in pool])
ok("the angle is the tension itself, which is this method's whole edge",
   all(r["angle"] in SENTENCE.values() for r in pool), [r["angle"] for r in pool])
ok("what it would be is its own field, not folded into the angle",
   all(r["what_it_would_be"] for r in pool))
ok("an asset that needs software built says so on the row, and the reason travels with it",
   any(r["tool_escalation"] and any("Needs a build" in x["what"] for x in r["proof"]) for r in pool),
   [(r["title"], r["tool_escalation"]) for r in pool])
ok("an asset a writer could ship is not flagged as a build",
   any(not r["tool_escalation"] for r in pool))
ok("the title is a real title, not a format label", all(len(r["title"]) > 10 for r in pool))
ok("the judgments are carried across, not re-decided",
   all(r["linkability"]["score"] >= cm.LINKABILITY_FLOOR and r["ownability"]["verdict"] for r in pool))
ok("the Reddit signal travels with the idea as its proof",
   all("upvotes" in (r["proof"][0]["what"] or "") and r["proof"][0]["url"] for r in pool), pool[:1])
ok("the unfair advantage is kept somewhere a person can see it",
   all(any("Unfair advantage" in p["what"] for p in r["proof"]) for r in pool))
ok("ranking and reuse are left to the merge",
   all(r["rank"] is None and r["reuse"]["verdict"] == "" for r in pool))

print("\nstage 5 — the final gate")
v = cm.read(trends._w("verify.md")) or ""
ok("the gate wrote its own result", "VERIFY: PASS" in v, v)
ok("the run log records the pass and the shortcuts", "VERIFY: PASS" in (cm.read(trends._w("run-log.md")) or ""))
ok("nothing was left unfilled in any prompt", not UNFILLED, UNFILLED[:2])

print("\nresume")
n_calls, n_fetch = CALLS["json"], len(FETCHED)
again = trends.run(CO, say)
ok("a finished pool is not rebuilt", again.get("files") == ["trends.json"])
ok("no model call and no fetch on a resume", CALLS["json"] == n_calls and len(FETCHED) == n_fetch,
   (CALLS["json"] - n_calls, len(FETCHED) - n_fetch))

# --- 3. Reddit refuses everything -----------------------------------------------------------------
print("\nwhen Reddit refuses everything (2026-09-09: it refused every check for this owner)")
fresh("blocked")
BLOCK_ALL["on"] = True
cm.save(trends.APPROVED, {"subreddits": SUBS})
out = trends.run(CO, say)
BLOCK_ALL["on"] = False
ok("the pool is written, empty", out.get("files") == ["trends.json"] and (cm.read("trends.json") == []))
ok("no post was invented", not ((cm.read(trends._w("posts.json")) or {}).get("posts")))
ok("the refusal is said plainly, and as unknown rather than empty",
   any("would not serve" in n or "unknown" in n for n in out["needs_review"]), out["needs_review"])
ok("the reason is written to the run log", "Reddit" in (cm.read(trends._w("run-log.md")) or ""))

# --- 4. the self-audit gate stops a bad sort ------------------------------------------------------
print("\nthe self-audit gate refuses to filter a bad sort")
fresh("audit")
cm.save(trends.APPROVED, {"subreddits": SUBS})
_real_assign = trends._assign_call
trends._assign_call = lambda co, posts_, tensions: {}      # everything falls to misc
try:
    out = trends.run(CO, say)
finally:
    trends._assign_call = _real_assign
sa = cm.read(trends._w("self-audit.md")) or ""
ok("the run stops before any filtering", out.get("files") == [], out)
ok("no pool is written from a sort that failed its own audit", not cm.exists("trends.json"))
ok("the audit file says FAIL and names the box", "FAIL" in sa and "misc" in sa, sa)
ok("the person is told, in plain words", any("audit gate" in n for n in out["needs_review"]),
   out["needs_review"])
ok("no tension was filtered", all(not r["verdict"] for r in (cm.read(trends._w("tensions.json")) or [])))

# --- 5. a test that returns no row for an idea ----------------------------------------------------
print("\nan unjudged tension is held, never dropped by default")
fresh("unjudged")
_rows = [{"idea_id": cm.new_id(1, "trends"), "tension_id": "T01", "tension": SENTENCE["remote"],
          "core_pain": "x", "implied_data": "y", "sub_questions": [], "phrases": [], "posts": [],
          "n_posts": 1, "upvotes": 1, "comments": 1, "subreddits": ["recruiting"], "quotes": [],
          "best_example": "", "audience": "candidate", "emotion": "anger",
          "linkability": {}, "ownability": {}, "brand_fit": "", "transplant_from": "",
          "verdict": "", "why": ""}]
_saved = llm.json_call
llm.json_call = lambda p, **kw: []            # the model returns no row at all
try:
    _out = trends.filter_tensions(_rows, say)
finally:
    llm.json_call = _saved
ok("the verdict is UNJUDGED, not DROP", _out[0]["verdict"] == trends.UNJUDGED, _out[0]["verdict"])
ok("an unjudged score is None, never a zero that reads as a real verdict",
   _out[0]["linkability"]["score"] is None and _out[0]["ownability"]["verdict"] is None,
   _out[0]["linkability"])
ok("nothing is built from an unjudged tension", trends.ideas(CO, _out, say) == [])

print("\nStubbed model and Reddit. Proves the plumbing, the gates and the code-enforced rules, not "
      "whether the tensions or the ideas are any good.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all study-trends checks passed")
