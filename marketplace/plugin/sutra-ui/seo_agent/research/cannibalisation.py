"""cannibalisation.py — Step 1a: do we ALREADY rank for this keyword?

Ported from 14-research-conductor/scripts/cannibalization.py. The footprint here is the site index
(knowledge/site_index.json), which carries each page's ranking keywords from the same DataForSEO
ranked_keywords pull the original read. A top-CANNIB_RANK_MAX (page 1) position is real
cannibalisation, because that is where a second page splits our own traffic; a #40 nobody sees is
not. Never blocks: we still build, the flag rides into the brief.

Reads: the primary keyword, the site index. Returns {keyword, rank, url} or None.
"""
import re

from ..tools import _shared as sh
from . import _common as _c


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def check(keyword, index=None):
    want = _norm(keyword)
    if not want:
        return None
    index = sh.site_index() if index is None else index
    best = None
    for page in index.get("pages", []):
        for term, pos in sh._page_keywords(page):
            if _norm(term) != want:
                continue
            try:
                rank = int(pos)
            except (TypeError, ValueError):
                continue
            if rank <= 0 or rank > _c.CANNIB_RANK_MAX:          # 0 is "not known", not a #1 spot
                continue
            if best is None or rank < best["rank"]:              # keep our BEST position
                best = {"keyword": keyword, "rank": rank, "url": sh.page_url(page)}
    return best
