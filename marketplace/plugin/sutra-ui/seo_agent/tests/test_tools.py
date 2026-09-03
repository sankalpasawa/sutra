"""tests/test_tools.py — every tool's plumbing, with the model stubbed.

A model key is not needed to prove a tool reads the right inputs, emits progress and
writes the right artifact shape. Stub the model, drive each tool, assert the shape.
What this does NOT prove is whether the writing is any good. Only a real run does that.
"""
import json
import os
import shutil
import sys

from seo_agent.tests import _fixture
_fixture.setup()
from seo_agent import llm, store

# --- stub the model ------------------------------------------------------------------
llm.json_call = _fixture.stub_json
llm.text = _fixture.stub_text

# --- drive each tool -----------------------------------------------------------------
c = store.new_chat("tool test")
r = store.new_run(c, "executive education")
events = []
ctx = {"chat_id": c, "run_id": r, "emit": lambda **kw: events.append(kw)}

FAILS = []
def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond

def art(name):
    return store.load_artifact(c, r, name)

print("\nlearn_voice")
from seo_agent.tools import learn_voice
try:
    out = learn_voice.run(ctx, sample_pages=4)
    v = store.knowledge("brand_voice.json")
    ok("returns a summary", bool(out.get("summary")))
    ok("saves brand_voice.json", bool(v))
    ok("has a voice summary", bool((v or {}).get("summary")))
    ok("has a words-to-avoid list", isinstance((v or {}).get("avoid"), list))
except Exception as e:
    ok("runs", False, e)

print("\nsuggest_topics")
from seo_agent.tools import suggest_topics
try:
    n0 = len(events)
    out = suggest_topics.run(ctx)
    t = art("topics.json")
    ok("returns a summary", bool(out.get("summary")))
    ok("writes topics.json", bool(t))
    topics = (t or {}).get("topics", t if isinstance(t, list) else [])
    ok("six topics", len(topics) == 6, len(topics))
    ok("each has an angle", all(x.get("angle") for x in topics))
    ok("emitted progress", len(events) > n0)
except Exception as e:
    ok("runs", False, e)

print("\nrun_research")
from seo_agent.tools import run_research
try:
    n0 = len(events)
    out = run_research.run(ctx, topic="executive education for CHROs")
    rs = art("research.json") or {}
    ok("writes research.json", bool(rs), out.get("error"))
    ok("has a primary keyword", bool(((rs.get("keywords") or {}).get("primary") or {}).get("keyword")))
    ok("has the world statement", bool((rs.get("world") or {}).get("not_about")))
    ok("has People Also Ask", isinstance((rs.get("serp") or {}).get("paa"), list))
    ok("has who ranks", len((rs.get("serp") or {}).get("who_ranks") or []) > 0)
    ok("has gaps to own", bool((rs.get("winners") or {}).get("gaps_to_own")))
    ok("says the numbers are demo data", rs.get("demo_data") is True and "demo" in out.get("summary", ""))
    ok("writes cards.json", bool(art("cards.json")))
    ok("emitted several substeps", len(events) - n0 >= 3, len(events) - n0)
except Exception as e:
    ok("runs", False, e)

print("\nbuild_blueprint")
from seo_agent.tools import build_blueprint
try:
    out = build_blueprint.run(ctx, target_words=1500)     # an old caller's extra argument is ignored
    bp = art("blueprint.json") or {}
    ok("writes blueprint.json", bool(bp), out.get("error"))
    ok("has sections", len(bp.get("sections", [])) > 0)
    ok("has an h1", bool(bp.get("h1")))
    secs = bp.get("sections", [])
    ok("every section has a job", all(s.get("job") for s in secs))
    ok("keyword set carries the primary", bool((bp.get("keyword_set") or {}).get("primary")))
    ok("faq is a list", isinstance(bp.get("faq"), list))
except Exception as e:
    ok("runs", False, e)

print("\nwrite_article")
from seo_agent.tools import write_article
# The write phase reads the CONTRACTS-shaped blueprint, research brief and evidence cards. Until the
# research and blueprint tools write that shape, the fixture plants it here.
_fixture.plant_write_inputs(c, r)
_fixture.plant_brand_files()
try:
    n0 = len(events)
    out = write_article.run(ctx)
    d = art("draft.md")
    a = art("article.json") or {}
    ok("returns a summary, no error", bool(out.get("summary")) and not out.get("error"), out.get("error"))
    ok("writes draft.md", bool(d))
    ok("draft has an H1", bool(d) and d.strip().startswith("#"))
    ok("draft has real length", bool(d) and len(d.split()) > 50, len((d or "").split()))
    ok("draft carries the sources list", bool(d) and "## Sources" in d)
    ok("writes article.json with sections and sources", bool(a.get("sections")) and isinstance(a.get("sources"), list))
    ok("writes links-report.json", bool(art("links-report.json")))
    ok("writes write-report.json with every step", len((art("write-report.json") or {}).get("steps", {})) >= 20)
    ok("emitted a substep per step", len(events) - n0 >= 20, len(events) - n0)
except Exception as e:
    import traceback; traceback.print_exc()
    ok("runs", False, e)

print("\nindex_site, when the site refuses the crawl")
from seo_agent.tools import index_site
_saved_index = store.knowledge("site_index.json")
_real_discover = index_site._discover
def _blocked(client, roots, max_pages):
    raise RuntimeError("Could not read %s: Client error '429 Too Many Requests'" % roots[0])
index_site._discover = _blocked
try:
    n0 = len(events)
    out = index_site.run(ctx, domain="blocked.example")
    idx = store.knowledge("site_index.json")
    ok("falls back to search data instead of failing", out.get("crawl_blocked") is True)
    ok("the index says the crawl was blocked", bool((idx or {}).get("crawl_blocked")))
    ok("pages come from ranking URLs", bool((idx or {}).get("pages")) and all(p.get("source") == "search" for p in idx["pages"]))
    ok("every page has a top keyword", all(p.get("top_keyword") for p in idx["pages"]))
    ok("no page carries text it never read", all(not p.get("body") for p in idx["pages"]))
    ok("the summary tells the truth", "crawl refused" in out.get("summary", ""))
    ok("emitted the refusal as a substep", any("refused" in (e.get("label") or "") for e in events[n0:]))
    try:
        learn_voice.run(ctx, sample_pages=3)
        ok("learn_voice refuses to invent a voice from titles", False, "no raise")
    except RuntimeError as e:
        ok("learn_voice refuses to invent a voice from titles", "refused the crawl" in str(e), str(e)[:120])
except Exception as e:
    ok("runs", False, e)
finally:
    index_site._discover = _real_discover
    if _saved_index is not None:
        store.save_knowledge("site_index.json", _saved_index)

shutil.rmtree(store.chat_dir(c))
print("\nStubbed model. Proves plumbing and artifact shapes, not writing quality.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
