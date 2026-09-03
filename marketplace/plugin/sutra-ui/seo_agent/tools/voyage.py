"""voyage.py — the one Voyage client: embeddings and reranking.

Ported from the SEO workflow's `02-asset-engine/_shared/voyage.py`, the single client
every embedding job there ran on: the page index, the reuse check, the dedup, and the
internal-link pass. One client, one key, so every "is this page about that?" question
in the agent is answered on the same stack and the same numbers.

THE KEY is never in the repo and never printed. In order:
    1. the agent's Connections store (`voyage_key`, saved owner-only by the app)
    2. the VOYAGE_API_KEY environment variable
    3. the first `pa-...` token in ~/.testlify-access.md (the workflow's own fallback,
       kept so a developer who already has that file needs nothing else)

Free tier (as of 2026-07): voyage-4-large ~200M tokens/mo, rerank-2.5 ~200M/mo.

Two contracts every caller relies on:
    embed()  returns float32, L2-normalised rows, so a dot product IS the cosine.
    rerank() returns [(index_into_docs, relevance_score), ...] best first.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import store

EMB_MODEL = os.environ.get("VOYAGE_EMB_MODEL", "voyage-4-large")     # best general embedder on the free tier
RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2.5")   # best reranker on the free tier
MAX_ITEMS = 64            # Voyage caps items per embed call
MAX_CHARS = 90000         # ...and total chars per call
EMB_WORKERS = int(os.environ.get("VOYAGE_EMB_WORKERS", "8"))  # parallel embed POSTs; _post backs off on 429
ATTEMPTS = 6
TIMEOUT = 180

EMBED_URL = "https://api.voyageai.com/v1/embeddings"
RERANK_URL = "https://api.voyageai.com/v1/rerank"


class NoVoyageKey(Exception):
    pass


def get_key():
    """The key, from the three places above. Raises NoVoyageKey rather than exiting:
    inside the app a missing key is something to tell the user, not a reason to die."""
    try:
        k = (store.connections().get("voyage_key") or "").strip()
        if k:
            return k
    except Exception:
        pass
    k = (os.environ.get("VOYAGE_API_KEY") or "").strip()
    if k:
        return k
    p = os.path.expanduser("~/.testlify-access.md")
    if os.path.exists(p):
        try:
            m = re.search(r"pa-[A-Za-z0-9_\-]{20,}", open(p, encoding="utf-8", errors="ignore").read())
        except OSError:
            m = None
        if m:
            return m.group(0)
    raise NoVoyageKey("No Voyage key. Add one in Connections (it is free at voyageai.com), "
                      "or set VOYAGE_API_KEY.")


def available():
    try:
        get_key()
        return True
    except NoVoyageKey:
        return False


def _post(url, body):
    key = get_key()          # read per call, never cached: the user can paste a key mid-session
    last = None
    for attempt in range(ATTEMPTS):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                         headers={"Authorization": "Bearer " + key,
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read()[:160].decode("utf-8", "ignore")
            except Exception:
                pass
            if e.code in (401, 403):
                raise NoVoyageKey("Voyage refused the key (HTTP %d). Check it in Connections." % e.code)
            w = 2 ** attempt
            if e.code == 429:                       # rate limited: back off harder
                w = max(w, 15)
            last = "HTTP %d %s" % (e.code, detail)
            print("   voyage %s, retry in %ds" % (last, w), file=sys.stderr)
            time.sleep(w)
        except Exception as ex:                     # noqa: BLE001 -- network weather of every kind
            last = str(ex)[:160]
            print("   voyage err %s, retry" % last, file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError("Voyage call failed after %d attempts: %s" % (ATTEMPTS, last))


def embed(texts, input_type="document"):
    """(N, dim) float32 array of L2-normalised embeddings, in the order given.

    Batches are POSTED IN PARALLEL: the calls are I/O-bound and sequential was ~8x too
    slow on a 10,000-page site. Order is preserved twice over: the batches are built in
    order and `ex.map` returns them in order; inside a batch, rows are re-sorted by the
    index Voyage echoes back.
    """
    texts = [t if (t and str(t).strip()) else "untitled" for t in texts]   # Voyage 400s on ""
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    batches, i = [], 0
    while i < len(texts):
        batch, chars = [], 0
        while i < len(texts) and len(batch) < MAX_ITEMS and chars + len(texts[i]) <= MAX_CHARS:
            batch.append(texts[i]); chars += len(texts[i]); i += 1
        if not batch:                                # one text alone is over the cap: truncate it
            batch = [texts[i][:MAX_CHARS]]; i += 1
        batches.append(batch)

    def _do(b):
        d = _post(EMBED_URL, {"input": b, "model": EMB_MODEL, "input_type": input_type})
        return [e["embedding"] for e in sorted(d["data"], key=lambda x: x["index"])]

    out = []
    with ThreadPoolExecutor(max_workers=min(EMB_WORKERS, len(batches)) or 1) as ex:
        for res in ex.map(_do, batches):
            out.extend(res)
    v = np.asarray(out, dtype=np.float32)
    v /= (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)          # normalise: dot == cosine
    return v


def rerank(query, docs, top_k):
    """Cross-encoder scores: it reads the query and each document together, which is
    what makes it so much better than cosine at telling 'same topic' from 'same thing'."""
    if not docs:
        return []
    d = _post(RERANK_URL, {"query": query, "documents": list(docs), "model": RERANK_MODEL,
                           "top_k": int(top_k), "return_documents": False})
    return [(r["index"], float(r["relevance_score"])) for r in d["data"]]
