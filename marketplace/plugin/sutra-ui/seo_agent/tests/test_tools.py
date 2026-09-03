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
    rs = art("research.json")
    ok("writes research.json", bool(rs))
    ok("has a primary keyword", bool((rs or {}).get("primary_keyword")))
    ok("has People Also Ask", isinstance((rs or {}).get("people_also_ask"), list))
    ok("has top results", len((rs or {}).get("top_results", [])) > 0)
    ok("has the gap", bool((rs or {}).get("the_gap")))
    ok("emitted several substeps", len(events) - n0 >= 3, len(events) - n0)
except Exception as e:
    ok("runs", False, e)

print("\nbuild_blueprint")
from seo_agent.tools import build_blueprint
try:
    out = build_blueprint.run(ctx, target_words=1500)
    bp = art("blueprint.json")
    ok("writes blueprint.json", bool(bp))
    ok("has sections", len((bp or {}).get("sections", [])) > 0)
    ok("has a title", bool((bp or {}).get("title")))
    secs = (bp or {}).get("sections", [])
    ok("every section has a brief", all(s.get("covers") for s in secs))
except Exception as e:
    ok("runs", False, e)

print("\nwrite_article")
from seo_agent.tools import write_article
try:
    n0 = len(events)
    out = write_article.run(ctx)
    d = art("draft.md")
    ok("writes draft.md", bool(d))
    ok("draft has an H1", bool(d) and d.strip().startswith("#"))
    ok("draft has real length", bool(d) and len(d.split()) > 50, len((d or "").split()))
    ok("emitted a substep per section", len(events) - n0 >= 3, len(events) - n0)
except Exception as e:
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
