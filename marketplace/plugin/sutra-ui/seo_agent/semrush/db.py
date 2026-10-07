"""db.py — the one queryable store in this plugin.

Every other engine in seo_agent keeps its state in flat JSON/JSONL (see store.py's
own docstring: "the run folder is the truth"). This is the one deliberate exception,
because the requirement is cohort math over time -- "average position for SEO Writer
blogs at 30 days old, grouped by keyword-difficulty tier" -- which is a join and a
group-by, not a file read. SQLite is stdlib: no new dependency, and it lives at
data_dir()/semrush.db, so it follows the same per-company folder every other file in
this app follows (company switch just points at a different file, like everything
else under data_dir()).

Every write here is an upsert keyed on a natural key (blog.url, or
(blog_id, date, source) for a snapshot), so a sync that runs twice in one day, or
that dies and re-runs, produces the same rows, not duplicates.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

from .. import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS blog (
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  title TEXT,
  published_at TEXT,
  author TEXT,
  generated_by_seo_writer INTEGER NOT NULL DEFAULT 0,
  seo_writer_version TEXT,
  target_keyword TEXT,
  target_keyword_volume INTEGER,
  target_keyword_difficulty REAL,
  category TEXT,
  word_count INTEGER,
  last_updated_at TEXT,
  library_item_id TEXT,
  pt_project_id TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blog_performance_snapshot (
  id INTEGER PRIMARY KEY,
  blog_id INTEGER NOT NULL REFERENCES blog(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  source TEXT NOT NULL,
  organic_keywords INTEGER,
  top3_keywords INTEGER,
  top10_keywords INTEGER,
  top20_keywords INTEGER,
  average_position REAL,
  estimated_traffic INTEGER,
  traffic_change REAL,
  visibility REAL,
  backlinks INTEGER,
  referring_domains INTEGER,
  created_at TEXT NOT NULL,
  UNIQUE(blog_id, date, source)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_blog_date
  ON blog_performance_snapshot(blog_id, date);
CREATE INDEX IF NOT EXISTS idx_blog_classification
  ON blog(generated_by_seo_writer, status);
"""


def db_path():
    return os.path.join(store.data_dir(), "semrush.db")


@contextmanager
def _conn():
    """One connection per call, WAL mode so a sync writing does not block a dashboard
    read. Resolved against store.data_dir() on every call (not cached), for the same
    reason store.py resolves every path live: a company switch must not leave a
    connection open on the WRONG company's file."""
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.executescript(SCHEMA)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- blog ---------------------------------------------------------------------------

BLOG_FIELDS = (
    "url", "title", "published_at", "author", "generated_by_seo_writer",
    "seo_writer_version", "target_keyword", "target_keyword_volume",
    "target_keyword_difficulty", "category", "word_count", "last_updated_at",
    "library_item_id", "pt_project_id", "status",
)


def upsert_blog(fields):
    """Insert or update by url (the natural key). Returns the blog id.

    A field the caller did not pass is left as it was on an existing row -- same
    "never blank what you did not mention" rule store.save_connections() follows --
    so a weekly sweep that only refreshes target_keyword never has to first read the
    row back to preserve its title.
    """
    url = (fields.get("url") or "").strip()
    if not url:
        raise ValueError("a blog needs a url")
    with _conn() as c:
        row = c.execute("SELECT id FROM blog WHERE url = ?", (url,)).fetchone()
        ts = now()
        if row:
            sets, vals = [], []
            for k in BLOG_FIELDS:
                if k in fields and k != "url":
                    sets.append(k + " = ?")
                    vals.append(fields[k])
            if sets:
                sets.append("updated_at = ?")
                vals.append(ts)
                vals.append(row["id"])
                c.execute("UPDATE blog SET %s WHERE id = ?" % ", ".join(sets), vals)
            return row["id"]
        cols = ["url", "created_at", "updated_at"]
        vals = [url, ts, ts]
        for k in BLOG_FIELDS:
            if k != "url" and k in fields:
                cols.append(k)
                vals.append(fields[k])
        placeholders = ",".join("?" for _ in cols)
        cur = c.execute("INSERT INTO blog (%s) VALUES (%s)" % (",".join(cols), placeholders), vals)
        return cur.lastrowid


def get_blog(blog_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM blog WHERE id = ?", (blog_id,)).fetchone()
        return dict(row) if row else None


def get_blog_by_url(url):
    with _conn() as c:
        row = c.execute("SELECT * FROM blog WHERE url = ?", (url.strip(),)).fetchone()
        return dict(row) if row else None


def list_blogs(classification=None, status="active", limit=500, offset=0):
    """classification: None (all), "SEO_WRITER", or "NON_SEO_WRITER"."""
    q = "SELECT * FROM blog"
    where, args = [], []
    if status:
        where.append("status = ?")
        args.append(status)
    if classification == "SEO_WRITER":
        where.append("generated_by_seo_writer = 1")
    elif classification == "NON_SEO_WRITER":
        where.append("generated_by_seo_writer = 0")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY published_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


# ---- snapshots ------------------------------------------------------------------------

SNAPSHOT_FIELDS = (
    "organic_keywords", "top3_keywords", "top10_keywords", "top20_keywords",
    "average_position", "estimated_traffic", "traffic_change", "visibility",
    "backlinks", "referring_domains",
)


def insert_snapshot(blog_id, date, source, **metrics):
    """Idempotent: the same (blog_id, date, source) overwrites, never duplicates, so a
    sync that reruns for a day it already pulled does not skew any average."""
    cols = ["blog_id", "date", "source", "created_at"] + [k for k in SNAPSHOT_FIELDS if k in metrics]
    vals = [blog_id, date, source, now()] + [metrics[k] for k in SNAPSHOT_FIELDS if k in metrics]
    placeholders = ",".join("?" for _ in cols)
    with _conn() as c:
        c.execute(
            "INSERT INTO blog_performance_snapshot (%s) VALUES (%s) "
            "ON CONFLICT(blog_id, date, source) DO UPDATE SET %s"
            % (",".join(cols), placeholders,
               # created_at is a first-insert timestamp, not a last-write one -- excluded from the
               # UPDATE half so a re-run correcting today's numbers does not disturb it.
               ",".join("%s = excluded.%s" % (k, k) for k in cols
                        if k not in ("blog_id", "date", "source", "created_at"))),
            vals,
        )


def blog_history(blog_id, source=None, since=None):
    q = "SELECT * FROM blog_performance_snapshot WHERE blog_id = ?"
    args = [blog_id]
    if source:
        q += " AND source = ?"
        args.append(source)
    if since:
        q += " AND date >= ?"
        args.append(since)
    q += " ORDER BY date ASC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def latest_snapshot(blog_id, source=None):
    q = "SELECT * FROM blog_performance_snapshot WHERE blog_id = ?"
    args = [blog_id]
    if source:
        q += " AND source = ?"
        args.append(source)
    q += " ORDER BY date DESC LIMIT 1"
    with _conn() as c:
        row = c.execute(q, args).fetchone()
        return dict(row) if row else None


# ---- cohort / overview queries ---------------------------------------------------------
# AGE-NORMALIZED ON PURPOSE (see the design conversation this ships from): a raw average
# across every blog conflates a post published yesterday with one published two years
# ago. Every aggregate here is either "as of the blog's own latest snapshot" (overview)
# or explicitly bucketed by days-since-publish (cohort_at_age), never a blind average
# across ages.
#
# ONE BLOG, THREE SOURCES, NEVER ONE "LATEST" ROW ACROSS THEM. Each of the three pulls
# (position_tracking, url_organic, backlinks) writes its OWN row for the same
# (blog_id, date), and each row only carries the columns that source can answer --
# a backlinks-source row has organic_keywords = NULL, not 0. Caught live in this
# integration's own smoke test: picking "the latest snapshot" with no source filter
# non-deterministically returned whichever source's row SQLite scanned last on a tied
# date, and when that was the backlinks row every keyword figure silently read as
# zero. _merge_sources fixes this by reading each source's row independently and
# combining named fields, so a missing source contributes nothing rather than nulling
# out what another source already answered.

def _merge_sources(pt=None, uo=None, bl=None):
    """Keyword/position/traffic/visibility prefer position_tracking (the scheduled,
    authoritative rollup) and fall back to url_organic (the ad-hoc sweep, which never
    carries traffic or visibility). Backlinks/referring_domains come from the
    backlinks source alone, independent of which of the other two is present."""
    primary = pt or uo or {}
    return {
        "organic_keywords": primary.get("organic_keywords") or 0,
        "top3_keywords": primary.get("top3_keywords") or 0,
        "top10_keywords": primary.get("top10_keywords") or 0,
        "top20_keywords": primary.get("top20_keywords") or 0,
        "average_position": primary.get("average_position"),
        "estimated_traffic": (pt or {}).get("estimated_traffic") or 0,
        "visibility": (pt or {}).get("visibility"),
        "backlinks": (bl or {}).get("backlinks") or 0,
        "referring_domains": (bl or {}).get("referring_domains") or 0,
    }


def merged_latest(blog_id):
    """This blog's latest known value per metric family, none of them from the same
    calendar date necessarily -- see _merge_sources. None only when NO source has
    ever reported on this blog."""
    pt = latest_snapshot(blog_id, source="position_tracking")
    uo = latest_snapshot(blog_id, source="url_organic")
    bl = latest_snapshot(blog_id, source="backlinks")
    if not (pt or uo or bl):
        return None
    return _merge_sources(pt, uo, bl)


def overview(classification=None):
    """One row: count, avg/median organic keywords, avg position, top3/10/20 rate,
    avg traffic -- each blog's OWN latest snapshot, not a fixed calendar date, so a
    blog whose sync lagged a day is not scored as zero."""
    blogs = list_blogs(classification=classification, limit=100000)
    rows = []
    for b in blogs:
        snap = merged_latest(b["id"])
        if snap:
            rows.append(snap)
    if not rows:
        return {"count": len(blogs), "with_data": 0}
    n = len(rows)
    ok = [r.get("organic_keywords") or 0 for r in rows]
    ok_sorted = sorted(ok)
    positions = [r["average_position"] for r in rows if r.get("average_position")]
    traffic = [r.get("estimated_traffic") or 0 for r in rows]
    top3 = sum(r.get("top3_keywords") or 0 for r in rows)
    top10 = sum(r.get("top10_keywords") or 0 for r in rows)
    top20 = sum(r.get("top20_keywords") or 0 for r in rows)
    total_kw = sum(ok) or 1
    return {
        "count": len(blogs), "with_data": n,
        "avg_organic_keywords": round(sum(ok) / n, 1),
        "median_organic_keywords": ok_sorted[n // 2],
        "avg_position": round(sum(positions) / len(positions), 1) if positions else None,
        "avg_estimated_traffic": round(sum(traffic) / n, 1),
        "top3_pct": round(100.0 * top3 / total_kw, 1),
        "top10_pct": round(100.0 * top10 / total_kw, 1),
        "top20_pct": round(100.0 * top20 / total_kw, 1),
    }


def _age_days(published_at, as_of_ts):
    if not published_at:
        return None
    try:
        pub = time.strptime(published_at[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return int((as_of_ts - time.mktime(pub)) / 86400)


def _closest_by_age(history, published_at, age_days, tolerance_days):
    """The row in one source's history closest to `age_days` old, within tolerance.
    None when this source has nothing in range -- a blog with no backlinks pull yet
    contributes no backlinks figure to the cohort, rather than a borrowed one from a
    different source's row on a nearby date (the same mixing bug _merge_sources
    exists to avoid, one level up)."""
    best, best_diff = None, None
    for snap in history:
        try:
            snap_ts = time.mktime(time.strptime(snap["date"][:10], "%Y-%m-%d"))
        except ValueError:
            continue
        snap_age = _age_days(published_at, snap_ts)
        if snap_age is None:
            continue
        diff = abs(snap_age - age_days)
        if diff <= tolerance_days and (best is None or diff < best_diff):
            best, best_diff = snap, diff
    return best


def cohort_at_age(classification, age_days, tolerance_days=3):
    """Every blog's merged snapshot closest to `age_days` old, within tolerance --
    each metric family (keywords/position, backlinks) matched to its OWN nearest
    date per source, then combined the same way overview()'s merged_latest is. This
    is the age-normalized comparison the design calls for: "performance after 30
    days", not "performance right now regardless of age"."""
    blogs = list_blogs(classification=classification, limit=100000)
    matched = []
    for b in blogs:
        pt_hist = blog_history(b["id"], source="position_tracking")
        uo_hist = blog_history(b["id"], source="url_organic")
        bl_hist = blog_history(b["id"], source="backlinks")
        pt = _closest_by_age(pt_hist, b["published_at"], age_days, tolerance_days)
        uo = _closest_by_age(uo_hist, b["published_at"], age_days, tolerance_days)
        bl = _closest_by_age(bl_hist, b["published_at"], age_days, tolerance_days)
        if pt or uo or bl:
            matched.append(_merge_sources(pt, uo, bl))
    if not matched:
        return {"age_days": age_days, "n": 0}
    n = len(matched)
    ok = [m.get("organic_keywords") or 0 for m in matched]
    positions = [m["average_position"] for m in matched if m.get("average_position")]
    top10 = sum(m.get("top10_keywords") or 0 for m in matched)
    total_kw = sum(ok) or 1
    return {
        "age_days": age_days, "n": n,
        "avg_organic_keywords": round(sum(ok) / n, 1),
        "avg_position": round(sum(positions) / len(positions), 1) if positions else None,
        "top10_pct": round(100.0 * top10 / total_kw, 1),
    }


# A POSITION OR A VISIBILITY INDEX IS NEVER SUMMED ACROSS BLOGS -- "average position 45" for a
# 3-blog cohort (10 + 15 + 20) is not a number anyone can read. Everything else here (keyword
# counts, traffic, backlinks) is a per-blog measure where a cohort TOTAL is the meaningful trend
# line ("total estimated traffic across every SEO Writer blog"). These two are the only fields
# for which the average is the right aggregate instead.
_MEAN_METRICS = {"average_position", "visibility"}


def timeseries(classification, metric="estimated_traffic", since=None, source=None):
    """Per date: the cohort TOTAL of `metric` across every blog that has a value that day, or
    the cohort MEAN for the two metrics in _MEAN_METRICS. Returns [{date, value}] -- the trend
    line the dashboard's "Performance over time" chart draws."""
    blogs = list_blogs(classification=classification, limit=100000)
    is_mean = metric in _MEAN_METRICS
    totals, counts = {}, {}
    for b in blogs:
        for snap in blog_history(b["id"], source=source, since=since):
            v = snap.get(metric)
            if v is None:
                continue
            d = snap["date"]
            totals[d] = totals.get(d, 0) + v
            counts[d] = counts.get(d, 0) + 1
    if is_mean:
        return [{"date": d, "value": round(totals[d] / counts[d], 1)} for d in sorted(totals)]
    return [{"date": d, "value": totals[d]} for d in sorted(totals)]
