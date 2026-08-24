"""workspace_corpus.py -- builds the five Workspace test corpora (PLAN-100 S53).

Each builder writes a complete corpus into a caller-supplied base directory:

    base/
      home/                 registry root (domains/ charters/ placements/)
      work/                 the workdir -- the .md document universe
      settings.json         panel settings with flags.workspace on

and returns a dict {"home", "workdir", "settings", ...corpus-specific ids...}.

Follows fixture_seed.py's rule: NO placement_engine import and NO engine
mutators -- the on-disk JSON shapes are written directly so ids and timestamps
are exactly reproducible across runs, and building a corpus can never depend
on (or corrupt) whatever registry the environment points at. Callers are
responsible for pointing the reader (placement_engine via workspace_api) at
`home` -- test_workspace_api.py does that by patching the E.* path constants.

The five corpora (PLAN-100 S53):
  corpus_empty            fresh install -- empty registry, empty workdir
  corpus_large            5k synthetic docs -- trips the 4000-row tree cap
  corpus_orphaned         a placement whose file is absent on disk (F2)
  corpus_duplicate_titles two docs sharing one H1 title (resolve collision)
  corpus_corrupted        broken registry rows that must be skipped, not fatal

stdlib only.
"""
import json
import os


# Deterministic clock base, fixture_seed.py precedent: derived mtimes/ts are
# reproducible run-to-run. Placement ts_ms is fixed; file mtimes are set with
# os.utime so "sorted mtime desc" assertions never race the wall clock.
DAY = 86400
NOW = 1756000000  # 2026-08-24T02:26:40Z, unix seconds


# ----------------------------------------------------------- low-level IO ---

def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True, indent=2)


def _mkdirs(base):
    home = os.path.join(base, "home")
    work = os.path.join(base, "work")
    for sub in ("domains", "charters", "placements"):
        os.makedirs(os.path.join(home, sub), exist_ok=True)
    os.makedirs(work, exist_ok=True)
    return home, work


def _write_settings(base, work, flag_on=True):
    """The panel settings file the flag gate reads (FLAG.md: flags.workspace
    in ~/.sutra-ui/settings.json). Tests point providers.SETTINGS_PATH here."""
    settings = {"workdir": work}
    if flag_on:
        settings["flags"] = {"workspace": True}
    path = os.path.join(base, "settings.json")
    _write_json(path, settings)
    return path


def write_domain(home, ref, name, parent_ref=None, status="active",
                 ts_minted_ms=None, description=None):
    """Minimal real on-disk domain shape (fixture_seed.py DOMAINS rows)."""
    row = {
        "ref": ref, "parent_ref": parent_ref, "name": name,
        "tenant_id": "T-local", "status": status, "origin": "operator",
        "touched_by_operator": True, "accountable": "tenant_owner",
        "authority": {}, "principles": [],
        "mint_evidence": [w.lower() for w in name.split()],
        "ts_minted_ms": ts_minted_ms if ts_minted_ms is not None else NOW * 1000,
        "successor_refs": [], "disposition_event_id": None,
        "retired_at_ms": None, "retire_reason_code": None, "retire_note": None,
    }
    if description is not None:
        row["description"] = description
    _write_json(os.path.join(home, "domains", ref + ".json"), row)
    return ref


def write_charter(home, cid, title, domain_ref, purpose="", scope_in=(),
                  status="active"):
    """Body + sidecar pair. The id is caller-fixed (C-<hex> shape, matching
    the naming resolve validates) rather than content-addressed --
    determinism beats hash fidelity for corpus assertions, and charter_view()
    loads by filename, not by re-hashing."""
    body = {
        "id": cid, "schema": 2, "title": title, "domain_ref": domain_ref,
        "purpose": purpose, "scope_in": list(scope_in), "scope_out": [],
        "kind": "standing", "linked_domain_refs": [], "supersedes": None,
        "tenant_id": "T-local", "ts_ms": NOW * 1000,
    }
    _write_json(os.path.join(home, "charters", cid + ".json"), body)
    _write_json(os.path.join(home, "charters", cid + ".page.json"),
                {"id": cid, "status": status, "artifacts": []})
    return cid


_PL_SEQ = [0]


def write_placement(home, work_path, domain_ref, charter_id, ts_ms=None,
                    kind="file", confidence=0.8):
    """One placements/PL-*.json row in write_placement()'s stored shape.
    CURRENT.jsonl is deliberately NOT appended -- the workspace projection
    reads placement bodies only, and a torn/absent CURRENT must not matter."""
    _PL_SEQ[0] += 1
    pid = "PL-%016x" % _PL_SEQ[0]
    body = {
        "id": pid, "work_ref": {"kind": kind, "id": work_path},
        "domain_ref": domain_ref, "charter_id": charter_id,
        "origin": "hook", "confidence": confidence, "created": "corpus",
        "supersedes": None, "phase": "open", "tenant_id": "T-local",
        "ts_ms": ts_ms if ts_ms is not None else NOW * 1000,
        "seq": _PL_SEQ[0], "pid": 1,
    }
    _write_json(os.path.join(home, "placements", pid + ".json"), body)
    return pid


def write_doc(work, rel, title=None, body="", mtime=None):
    """A .md file under the workdir with a pinned mtime. `title=None` writes
    no H1, exercising the filename-stem fallback."""
    full = os.path.join(work, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(full) or work, exist_ok=True)
    text = ""
    if title is not None:
        text += "# %s\n\n" % title
    text += body
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text)
    if mtime is not None:
        os.utime(full, (mtime, mtime))
    return rel


# ---------------------------------------------------------------- corpora ---

def corpus_empty(base):
    """Fresh install: registry dirs exist but hold nothing; workdir empty.
    tree must answer 200 with empty arrays (ERROR-MODEL F4); charter/resolve
    must answer 404 registry_empty."""
    home, work = _mkdirs(base)
    return {"home": home, "workdir": work,
            "settings": _write_settings(base, work)}


def corpus_small(base):
    """Not one of the five -- the shared small registry the defect corpora
    build on, and the default subject for join/search/charter/doc/resolve
    tests. Two departments, two charters, filed + unfiled docs with pinned
    mtimes."""
    home, work = _mkdirs(base)
    d_root = write_domain(home, "dref-root0000000001", "Sutra Labs",
                          ts_minted_ms=(NOW - 400 * DAY) * 1000)
    d_eng = write_domain(home, "dref-eng00000000001", "Sutra OS",
                         parent_ref=d_root,
                         ts_minted_ms=(NOW - 300 * DAY) * 1000,
                         description="Engines and the desktop panel")
    d_res = write_domain(home, "dref-res00000000001", "Research",
                         parent_ref=d_root,
                         ts_minted_ms=(NOW - 200 * DAY) * 1000,
                         description="Market and product research")
    c_eng = write_charter(home, "C-9be2f1aa11223344", "Engine Library", d_eng,
                          purpose="Deterministic, testable primitives.",
                          scope_in=["placement engine", "workspace viewer"])
    c_res = write_charter(home, "C-77c1d2bb55667788", "Research Briefs", d_res,
                          purpose="Turn raw intel into briefs.",
                          scope_in=["competitor analysis", "weekly brief"])

    write_doc(work, "research/2026-08-21-obsidian-viewer.md",
              title="Obsidian-like file viewer",
              body="the reuse path -- Obsidian is not open source\n"
                   "workspace joins registry and files\n",
              mtime=NOW - 2 * DAY)
    write_doc(work, "engine/notes.md", title="Engine notes",
              body="placement engine calibration notes\n",
              mtime=NOW - 5 * DAY)
    write_doc(work, "research/brief-31.md", title="Weekly brief 31",
              body="competitor pricing moved again\n",
              mtime=NOW - 1 * DAY)
    # Unfiled: no placement points at it. No H1 -> stem title "TODO".
    write_doc(work, "TODO.md", title=None, body="unfiled scratch list\n",
              mtime=NOW - 3 * DAY)

    p_eng = write_placement(home, "engine/notes.md", d_eng, c_eng,
                            ts_ms=(NOW - 5 * DAY) * 1000)
    p_obs = write_placement(home, "research/2026-08-21-obsidian-viewer.md",
                            d_eng, c_eng, ts_ms=(NOW - 2 * DAY) * 1000)
    p_brief = write_placement(home, "research/brief-31.md", d_res, c_res,
                              ts_ms=(NOW - 1 * DAY) * 1000)
    return {"home": home, "workdir": work,
            "settings": _write_settings(base, work),
            "d_root": d_root, "d_eng": d_eng, "d_res": d_res,
            "c_eng": c_eng, "c_res": c_res,
            "p_eng": p_eng, "p_obs": p_obs, "p_brief": p_brief}


def corpus_large(base, filed=2600, unfiled=2600):
    """5k+ synthetic docs (default 5200) so the tree MUST hit the 4000-row cap
    and set `truncated: true`. One department, one charter; filed docs join in
    registry order first, so the unfiled block is where truncation lands --
    mirroring 'walk stops at the cap in registry order'."""
    home, work = _mkdirs(base)
    d_root = write_domain(home, "dref-big00000000001", "Bulk")
    cid = write_charter(home, "C-b16b16b16b16b16b", "Bulk charter", d_root,
                        purpose="synthetic volume")
    for i in range(filed):
        rel = "filed/doc-%04d.md" % i
        write_doc(work, rel, title="Filed %04d" % i, body="bulk row\n",
                  mtime=NOW - i)
        write_placement(home, rel, d_root, cid, ts_ms=(NOW - i) * 1000)
    for i in range(unfiled):
        write_doc(work, "loose/doc-%04d.md" % i, title="Loose %04d" % i,
                  body="bulk row\n", mtime=NOW - i)
    return {"home": home, "workdir": work,
            "settings": _write_settings(base, work),
            "d_root": d_root, "charter": cid,
            "filed": filed, "unfiled": unfiled}


def corpus_orphaned(base):
    """corpus_small plus one placement whose work_ref.id has NO file on disk
    (deleted outside the app -- ERROR-MODEL F2). The tree must keep the row
    with missing:true; counts must exclude it; resolve on that path must 409
    mismatch. Also one placement with an ESCAPING path, which must be dropped
    entirely (MIGRATION M5), never crash the tree."""
    c = corpus_small(base)
    c["orphan_path"] = "research/deleted-elsewhere.md"
    c["p_orphan"] = write_placement(c["home"], c["orphan_path"],
                                    c["d_res"], c["c_res"],
                                    ts_ms=(NOW - 4 * DAY) * 1000)
    c["p_escape"] = write_placement(c["home"], "../outside.md",
                                    c["d_res"], c["c_res"],
                                    ts_ms=(NOW - 4 * DAY) * 1000)
    return c


def corpus_duplicate_titles(base):
    """corpus_small plus two docs whose H1 collide ('Quarterly plan') at
    different paths with different mtimes. Titles are display-only (identity
    rule); resolve of the bare title must pick most-recent mtime and return
    the rest under `also`."""
    c = corpus_small(base)
    c["dup_new"] = write_doc(c["workdir"], "plans/q3-plan.md",
                             title="Quarterly plan", body="the newer one\n",
                             mtime=NOW - 1 * DAY)
    c["dup_old"] = write_doc(c["workdir"], "archive/q3-plan-old.md",
                             title="Quarterly plan", body="the older one\n",
                             mtime=NOW - 30 * DAY)
    return c


def corpus_corrupted(base):
    """corpus_small plus deliberately broken registry rows: an invalid-JSON
    domain file, an invalid-JSON placement file, and a torn CURRENT.jsonl tail
    line. Every reader in the chain (load_domains / all_placements /
    _read_jsonl) skips these by contract -- the tree must stay 200 and keep
    the good rows. This is the graceful-skip corpus, NOT the engine_down one
    (that family is an unreadable STORE, exercised by mocking in tests)."""
    c = corpus_small(base)
    with open(os.path.join(c["home"], "domains", "dref-broken000000001.json"),
              "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    with open(os.path.join(c["home"], "placements", "PL-broken.json"),
              "w", encoding="utf-8") as fh:
        fh.write("{ torn placement")
    with open(os.path.join(c["home"], "placements", "CURRENT.jsonl"),
              "w", encoding="utf-8") as fh:
        fh.write('{"work_ref_id": "engine/notes.md"}\n{"torn": ')
    return c


ALL_CORPORA = {
    "empty": corpus_empty,
    "large": corpus_large,
    "orphaned": corpus_orphaned,
    "duplicate_titles": corpus_duplicate_titles,
    "corrupted": corpus_corrupted,
}
