"""tests/test_semrush.py — the blog performance analytics pipeline (seo_agent/semrush/).

What this proves, with the wire faked (no real Semrush account is used):

  * client.py's demo data is stable (same input -> same output) and always flagged _demo,
    so a screenshot from a demo run can never be mistaken for a real number;
  * db.py's snapshot writes are idempotent -- a sync that reruns for a day it already
    covered corrects that row rather than duplicating it, and its created_at survives a
    correction;
  * db.py's overview()/cohort_at_age() merge the three sources (position_tracking,
    url_organic, backlinks) per blog rather than picking "whichever row is latest" --
    the bug this integration's own smoke test caught, where a backlinks-only row could
    zero out a keyword figure another source had already answered;
  * db.py's timeseries() sums count-like metrics across a cohort but AVERAGES
    average_position/visibility, because summing a position across blogs is not a number;
  * sync.discover_blogs classifies a blog SEO_WRITER only when its slug matches a finished
    Library item, and leaves an existing classification alone on a second run.
"""
import os
import sys

from seo_agent.tests import _fixture
_fixture.setup()

from seo_agent import store
from seo_agent.semrush import client, db, sync

FAILS = []


def ok(label, cond, extra=""):
    if not cond:
        FAILS.append(label)
    print(("  PASS  " if cond else "  FAIL  ") + label + ((" — " + str(extra)) if extra and not cond else ""))
    return cond


# ---- isolate this suite's own semrush.db from anything else in the throwaway data dir -----------
db_path_before = db.db_path()
if os.path.exists(db_path_before):
    os.remove(db_path_before)
db.init_db()


# ---- client.py: demo mode is stable and flagged --------------------------------------------------
print("\nclient: demo mode is stable and flagged")
ok("Semrush is not connected in the test fixture", client.demo_mode())
a1 = client.url_organic("https://testlify.com/blog/example-post")
a2 = client.url_organic("https://testlify.com/blog/example-post")
ok("the same url gives the same demo rows twice", a1 == a2, (a1, a2))
ok("every demo row is flagged _demo", a1 and all(r.get("_demo") for r in a1), a1)
b1 = client.url_organic("https://testlify.com/blog/a-different-post")
ok("a different url gives different demo rows", a1 != b1, (a1, b1))
bl = client.backlinks_for_url("https://testlify.com/blog/example-post")
ok("demo backlinks are flagged too", bl.get("_demo") is True, bl)


# ---- db.py: idempotent snapshot writes -----------------------------------------------------------
print("\ndb: snapshot writes are idempotent")
blog_id = db.upsert_blog({"url": "https://testlify.com/blog/idempotency-check", "title": "Idempotency check",
                          "published_at": "2026-01-01", "generated_by_seo_writer": 1})
db.insert_snapshot(blog_id, "2026-06-01", "url_organic", organic_keywords=5, average_position=12.0)
first = db.blog_history(blog_id, source="url_organic")
ok("one row after the first write", len(first) == 1, first)
created_at_1 = first[0]["created_at"]
db.insert_snapshot(blog_id, "2026-06-01", "url_organic", organic_keywords=9, average_position=8.0)
second = db.blog_history(blog_id, source="url_organic")
ok("still one row after a same-day rerun (no duplicate)", len(second) == 1, second)
ok("the corrected value won, not the first one", second[0]["organic_keywords"] == 9, second)
ok("created_at is untouched by the correction", second[0]["created_at"] == created_at_1,
   (second[0]["created_at"], created_at_1))


# ---- db.py: merging three sources instead of "whichever is latest" --------------------------------
print("\ndb: overview()/merged_latest() merge sources rather than picking one row")
mix_id = db.upsert_blog({"url": "https://testlify.com/blog/source-mix", "title": "Source mix",
                         "published_at": "2026-01-01", "generated_by_seo_writer": 1})
# Same date, two different sources: url_organic carries the keyword figures, backlinks does not.
db.insert_snapshot(mix_id, "2026-06-01", "url_organic", organic_keywords=14, top10_keywords=3,
                   average_position=9.5)
db.insert_snapshot(mix_id, "2026-06-01", "backlinks", backlinks=22, referring_domains=6)
merged = db.merged_latest(mix_id)
ok("organic_keywords comes from url_organic, not zeroed by the backlinks-only row",
   merged["organic_keywords"] == 14, merged)
ok("backlinks comes from the backlinks row", merged["backlinks"] == 22, merged)
ov = db.overview("SEO_WRITER")
ok("overview reflects the merged figure, not a source-mixing zero",
   ov["avg_organic_keywords"] > 0, ov)


# ---- db.py: cohort_at_age is age-normalized, not "whatever is on disk today" ----------------------
print("\ndb: cohort_at_age matches each source to its own nearest date")
age_id = db.upsert_blog({"url": "https://testlify.com/blog/age-check", "title": "Age check",
                         "published_at": "2026-01-01", "generated_by_seo_writer": 0})
# 30 days after publish is 2026-01-31.
db.insert_snapshot(age_id, "2026-01-30", "url_organic", organic_keywords=6, top10_keywords=1)
cohort = db.cohort_at_age("NON_SEO_WRITER", 30, tolerance_days=3)
ok("a snapshot one day off a 30-day mark is matched within tolerance", cohort["n"] == 1, cohort)
far_cohort = db.cohort_at_age("NON_SEO_WRITER", 90, tolerance_days=3)
ok("the same snapshot is NOT matched to a 90-day mark it is nowhere near", far_cohort["n"] == 0, far_cohort)


# ---- db.py: timeseries sums counts, averages positions --------------------------------------------
print("\ndb: timeseries sums count-like metrics, averages position/visibility")
ts_a = db.upsert_blog({"url": "https://testlify.com/blog/ts-a", "generated_by_seo_writer": 1,
                       "published_at": "2026-01-01"})
ts_b = db.upsert_blog({"url": "https://testlify.com/blog/ts-b", "generated_by_seo_writer": 1,
                       "published_at": "2026-01-01"})
db.insert_snapshot(ts_a, "2026-07-01", "position_tracking", organic_keywords=10, average_position=10.0)
db.insert_snapshot(ts_b, "2026-07-01", "position_tracking", organic_keywords=20, average_position=20.0)
kw_series = db.timeseries("SEO_WRITER", metric="organic_keywords", since="2026-07-01")
pos_series = db.timeseries("SEO_WRITER", metric="average_position", since="2026-07-01")
kw_val = next((r["value"] for r in kw_series if r["date"] == "2026-07-01"), None)
pos_val = next((r["value"] for r in pos_series if r["date"] == "2026-07-01"), None)
ok("organic_keywords is the cohort TOTAL (10 + 20)", kw_val == 30, kw_val)
ok("average_position is the cohort MEAN (10 and 20 -> 15), never their sum",
   pos_val == 15.0, pos_val)


# ---- sync.py: discover_blogs classification -------------------------------------------------------
print("\nsync: discover_blogs classifies by Library slug match, and never reclassifies on rerun")
store.save_knowledge("site_index.json", {"pages": [
    {"url": "https://testlify.com/blog/matched-post", "type": "blog", "title": "Matched Post",
     "modified": "2026-05-01", "word_count": 1500},
    {"url": "https://testlify.com/blog/unmatched-post", "type": "blog", "title": "Unmatched Post",
     "modified": "2026-05-02", "word_count": 900},
]})
chat = store.new_chat("semrush test")
run = store.new_run(chat, "matched post")
item_id = store.library_item_id(chat, run)
store.library_start(chat, run, request_text="write matched post")
store.library_finish(item_id, "Matched Post", "# Matched Post\n\nbody", chat_id=chat, run_id=run, status="ready")

result = sync.discover_blogs()
ok("both blog pages are added", result["added"] == 2, result)
matched = db.get_blog_by_url("https://testlify.com/blog/matched-post")
unmatched = db.get_blog_by_url("https://testlify.com/blog/unmatched-post")
ok("the slug-matched post is classified SEO_WRITER", matched["generated_by_seo_writer"] == 1, matched)
ok("and carries its library_item_id", matched["library_item_id"] == item_id, matched)
ok("the unmatched post is classified NON_SEO_WRITER", unmatched["generated_by_seo_writer"] == 0, unmatched)

# A manual override (the door db.upsert_blog gives the API's POST /blogs) must survive a rediscovery.
db.upsert_blog({"url": "https://testlify.com/blog/unmatched-post", "generated_by_seo_writer": 1})
result2 = sync.discover_blogs()
ok("a rerun adds nothing new (both URLs already tracked)", result2["added"] == 0, result2)
reclassified = db.get_blog_by_url("https://testlify.com/blog/unmatched-post")
ok("a manual override is not clobbered by rediscovery", reclassified["generated_by_seo_writer"] == 1,
   reclassified)

# ---- tidy up --------------------------------------------------------------------------------------
import shutil
shutil.rmtree(store.chat_dir(chat), ignore_errors=True)
try:
    os.remove(db.db_path())
    for suffix in ("-wal", "-shm"):
        p = db.db_path() + suffix
        if os.path.exists(p):
            os.remove(p)
except OSError:
    pass

print("\nFaked wire (demo mode only, no real Semrush account touched). Proves demo determinism, "
      "idempotent snapshot writes, source-merging in overview/cohort queries, correct sum-vs-mean "
      "aggregation in timeseries, and slug-based SEO Writer classification that survives rediscovery.")
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all semrush checks passed")
