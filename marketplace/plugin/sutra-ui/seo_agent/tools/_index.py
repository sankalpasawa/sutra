"""_index.py — the two-vector page index: one vector per page TITLE, many per page BODY.

Not a tool (the underscore says so). build_page_index.py is the tool; links_pass.py is
the main consumer. Ported from the SEO workflow's reuse-check `step_1_retrieve.py`, which
proved the design on a 49-asset ground truth (recall@15 0.644) and then fed the write
phase's internal-link pass.

Why two vectors. v1 embedded only the body, so titles drowned; the fix was a separate
TITLE vector blended with the best BODY chunk. A 4,000-word page covering six subjects
should match on the one passage that is genuinely about the query, and averaging buries
exactly that. So: score = alpha * cos(query, title) + (1 - alpha) * max over chunks of
cos(query, chunk). Best chunk, never mean chunk.

Layout on disk, under knowledge/content-index/ (the same shape the workflow used, so the
retrieval code is a port rather than a rewrite):
    title/vectors.npy          one row per page
    title/meta.jsonl           {"url", "title"} per line, same order as the rows
    body/parts/part_00000.npy  one file per flush, in write order
    body/meta.jsonl            {"url", "title", "chunk"} per line, append-only, row order
    body/state.json            {"done": [urls], "part": n}   resume at page granularity
    index.json                 the stamp: pages, chunks, built_at, model

The body index resumes: a page is listed in state.json only after its part file and
its meta lines are on disk, so a crash mid-build costs one batch, never the index.
Every .npy save is temp-in-the-same-dir then rename, so a file that exists is complete.
"""
import json
import os
import tempfile

import numpy as np

from .. import store

INDEX_DIRNAME = "content-index"
CHUNK_CHARS = 4800           # body chunk size, in characters
OVERLAP = 600                # so a sentence straddling a cut is whole in one chunk
INDEX_BATCH_CHUNKS = 64      # flush a part file every ~64 chunks (overshoots by the last page)
ALPHA = 0.5                  # title weight; 1 - ALPHA is the best-body-chunk weight


def index_dir():
    return os.path.join(store.knowledge_dir(), INDEX_DIRNAME)


def _title_dir():
    return os.path.join(index_dir(), "title")


def _body_dir():
    return os.path.join(index_dir(), "body")


def _save_npy(path, arr):
    """Atomic .npy save: write a temp in the SAME dir, then rename over the target."""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".npy.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.save(f, arr)          # a file object, so np.save never appends an extension
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def chunks(text):
    """Overlapping character chunks. A body at or under CHUNK_CHARS is one chunk."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= CHUNK_CHARS:
        return [text]
    out, s = [], 0
    while s < len(text):
        out.append(text[s:s + CHUNK_CHARS])
        s += CHUNK_CHARS - OVERLAP
    return out


def status():
    """What is on disk, without loading a vector. {built, pages, chunks, built_at, model}."""
    stamp = store.read_json(os.path.join(index_dir(), "index.json"), default=None)
    tmeta = os.path.join(_title_dir(), "meta.jsonl")
    tvec = os.path.join(_title_dir(), "vectors.npy")
    if not (os.path.exists(tmeta) and os.path.exists(tvec)):
        return {"built": False, "pages": 0, "chunks": 0, "built_at": None, "model": None}
    pages = sum(1 for _ in open(tmeta, encoding="utf-8"))
    bmeta = os.path.join(_body_dir(), "meta.jsonl")
    n_chunks = sum(1 for _ in open(bmeta, encoding="utf-8")) if os.path.exists(bmeta) else 0
    return {"built": True, "pages": pages, "chunks": n_chunks,
            "built_at": (stamp or {}).get("built_at"), "model": (stamp or {}).get("model"),
            "complete": bool(stamp)}


# ---- build ---------------------------------------------------------------------------------

def build(pages, say=None, reindex=False):
    """pages: [(url, title, body)]. Rows with an empty body are skipped: there is nothing
    to embed and Voyage refuses an empty string anyway. Returns the stamp."""
    from . import voyage
    say = say or (lambda *a, **k: None)
    pages = [(u, t or "", b or "") for u, t, b in pages if u and (b or "").strip()]
    if not pages:
        raise RuntimeError("No pages with body text to index. Run index_site first, and "
                           "check that the crawl was allowed to read the pages.")
    idx = index_dir()
    os.makedirs(idx, exist_ok=True)
    if reindex and os.path.isdir(idx):
        for sub in ("title", "body"):
            p = os.path.join(idx, sub)
            if os.path.isdir(p):
                for root, _dirs, files in os.walk(p, topdown=False):
                    for f in files:
                        os.remove(os.path.join(root, f))
        try:
            os.remove(os.path.join(idx, "index.json"))
        except OSError:
            pass

    # --- TITLE index: one vector per page, one shot ---
    tdir = _title_dir()
    tvec_path = os.path.join(tdir, "vectors.npy")
    have_titles = 0
    if os.path.exists(tvec_path):
        try:
            have_titles = sum(1 for _ in open(os.path.join(tdir, "meta.jsonl")))
        except OSError:
            have_titles = 0
    # The body index embeds only what is new, but the TITLE index is one shot over every page, so
    # "the file exists" is not enough: it must cover the pages we have now. Found live 2026-09-04,
    # when the catalogue went 400 -> 11,703 and the title index quietly stayed at 400, so an
    # internal link could only ever match one of the first 400 titles.
    if have_titles == len(pages) and not reindex:
        say("Title index already built", "%d pages, kept" % have_titles)
    else:
        os.makedirs(tdir, exist_ok=True)
        tvecs = voyage.embed([t if t else u for u, t, b in pages], "document")
        _save_npy(tvec_path, tvecs)
        tmp = os.path.join(tdir, "meta.jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for u, t, b in pages:
                f.write(json.dumps({"url": u, "title": t}, ensure_ascii=False) + "\n")
        os.replace(tmp, os.path.join(tdir, "meta.jsonl"))
        say("Embedded the titles", "%d pages" % len(pages))

    # --- BODY index: chunked, resumable per page ---
    bdir = _body_dir()
    os.makedirs(os.path.join(bdir, "parts"), exist_ok=True)
    state_p = os.path.join(bdir, "state.json")
    meta_p = os.path.join(bdir, "meta.jsonl")
    state = store.read_json(state_p, default=None) or {"done": [], "part": 0}
    done = set(state["done"])
    todo = [p for p in pages if p[0] not in done]
    total_chunks = sum(len(chunks(b)) for _u, _t, b in todo)
    say("Embedding the page text", "%d pages to go (%d done), about %d passages"
        % (len(todo), len(done), total_chunks))

    buf, buf_chunks, flushed = [], 0, 0

    def flush():
        nonlocal buf, buf_chunks, flushed
        if not buf:
            return
        texts, metas = [], []
        for u, t, b in buf:
            for ci, ch in enumerate(chunks(b)):
                texts.append(ch)
                metas.append({"url": u, "title": t, "chunk": ci})
        vecs = voyage.embed(texts, "document")
        _save_npy(os.path.join(bdir, "parts", "part_%05d.npy" % state["part"]), vecs)
        with open(meta_p, "a", encoding="utf-8") as mf:
            for m in metas:
                mf.write(json.dumps(m, ensure_ascii=False) + "\n")
        state["part"] += 1
        state["done"].extend(u for u, _t, _b in buf)
        store.write_json(state_p, state)          # marked done only after the rows are on disk
        flushed += len(texts)
        if flushed % (INDEX_BATCH_CHUNKS * 4) < len(texts):
            say("Embedding the page text", "%d of %d passages" % (flushed, total_chunks))
        buf, buf_chunks = [], 0

    for p in todo:
        buf.append(p)
        buf_chunks += len(chunks(p[2]))
        if buf_chunks >= INDEX_BATCH_CHUNKS:
            flush()
    flush()

    stamp = {"pages": len(pages), "chunks": sum(1 for _ in open(meta_p, encoding="utf-8")),
             "built_at": store.now(), "model": voyage.EMB_MODEL,
             "chunk_chars": CHUNK_CHARS, "overlap": OVERLAP}
    store.write_json(os.path.join(idx, "index.json"), stamp)
    return stamp


# ---- load + retrieve -------------------------------------------------------------------------

def load_title():
    """(V, meta, order) for the title index, V L2-normalised; None when there is no index.
    order[i] is the url of row i; meta maps url -> title."""
    tdir = _title_dir()
    vp, mp = os.path.join(tdir, "vectors.npy"), os.path.join(tdir, "meta.jsonl")
    if not (os.path.exists(vp) and os.path.exists(mp)):
        return None
    V = np.nan_to_num(np.load(vp).astype(np.float32))
    V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    meta, order = {}, []
    with open(mp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            meta[d["url"]] = d.get("title") or ""
            order.append(d["url"])
    if len(order) != V.shape[0]:
        raise RuntimeError("title index is inconsistent: %d rows, %d meta lines. Rebuild it."
                           % (V.shape[0], len(order)))
    return V, meta, order


def body_best(Q, order):
    """Best body-chunk cosine per page, per query row. (n_queries, n_pages), or None.

    Walked ONE part file at a time and reduced into a running per-page maximum, so
    nothing larger than a single part is ever resident. Relies on body/meta.jsonl line
    order == concatenated part order, which the zero-padded part names guarantee.
    """
    bdir = _body_dir()
    pdir, mpath = os.path.join(bdir, "parts"), os.path.join(bdir, "meta.jsonl")
    if not (os.path.isdir(pdir) and os.path.exists(mpath)):
        return None
    pos = {u: i for i, u in enumerate(order)}
    best = np.zeros((Q.shape[0], len(order)), dtype=np.float32)
    seen = 0
    with open(mpath, encoding="utf-8") as mf:
        rows = (json.loads(line) for line in mf)
        for part in sorted(p for p in os.listdir(pdir) if p.endswith(".npy")):
            V = np.load(os.path.join(pdir, part), mmap_mode="r")
            cols = [pos.get((next(rows, None) or {}).get("url", ""), -1) for _ in range(V.shape[0])]
            Vn = np.nan_to_num(np.asarray(V, dtype=np.float32), posinf=0.0, neginf=0.0)
            Vn /= (np.linalg.norm(Vn, axis=1, keepdims=True) + 1e-9)
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):   # macOS BLAS artifact
                sims = np.nan_to_num(Q @ Vn.T)
            for j, p in enumerate(cols):
                if p >= 0:
                    np.maximum(best[:, p], sims[:, j], out=best[:, p])
            seen += V.shape[0]
    return best if seen else None


def score(Q, alpha=ALPHA):
    """Blend title and best-body scores for query rows Q (already normalised).
    Returns (blend, T, B, meta, order); B is None when there is no body index."""
    loaded = load_title()
    if loaded is None:
        raise RuntimeError("There is no page index. Run build_page_index first.")
    V, meta, order = loaded
    Q = np.nan_to_num(np.asarray(Q, dtype=np.float32))
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        T = np.nan_to_num(Q @ V.T)
    B = body_best(Q, order)
    blend = T if B is None else alpha * T + (1 - alpha) * B
    return blend, T, B, meta, order


# ---- the embedding map (for the Knowledge screen) ------------------------------------------

def embedding_map(types=None, traffic=None, cache=True):
    """Every page as a point in two dimensions, from a PCA of the title vectors.

    Cached at knowledge/embedding-map.json next to the index stamp; rebuilt when the
    index is newer. Points carry the url, title, type and traffic so the screen can colour
    and label them. Pure numpy: an SVD of the centred title matrix, first two components.
    """
    idx = index_dir()
    cache_p = os.path.join(idx, "embedding-map.json")
    stamp_p = os.path.join(idx, "index.json")
    if cache and os.path.exists(cache_p) and os.path.exists(stamp_p) \
            and os.path.getmtime(cache_p) >= os.path.getmtime(stamp_p):
        return store.read_json(cache_p, default=None)
    loaded = load_title()
    if loaded is None:
        return None
    V, meta, order = loaded
    if V.shape[0] < 3:
        return None
    X = V - V.mean(axis=0, keepdims=True)
    # SVD on the (n, d) matrix; the first two right-singular vectors are the axes.
    try:
        _u, _s, vt = np.linalg.svd(X, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    P = X @ vt[:2].T
    span = float(np.max(np.abs(P))) or 1.0
    P = P / span
    types = types or {}
    traffic = traffic or {}
    pts = []
    for i, u in enumerate(order):
        pts.append({"u": u, "t": meta.get(u, ""), "x": round(float(P[i, 0]), 4),
                    "y": round(float(P[i, 1]), 4), "k": types.get(u, ""), "v": traffic.get(u, 0)})
    out = {"points": pts, "n": len(pts), "built_at": store.now()}
    store.write_json(cache_p, out)
    return out
