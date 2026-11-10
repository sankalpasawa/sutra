"""The seed library sync (D144): an install's library gains what a newer seed has (templates, versions of templates it has, the provenance of
the versions it has, the seed's runs) and nothing it already has is changed. Offline; real files in a temp folder. The library "before sync 4"
is derived from the seed the app ships (`seedlib.previous_library`); the branches the shipped seed cannot reach use a seed made by hand."""
import hashlib
import json
import logging
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from seedlib import (
    NEW_TEMPLATE_NAMES, NEW_TEMPLATES, NEW_VERSION_NAMES, NEW_VERSIONS, PROBLEM, PROVENANCE_KEYS, REQUIREMENTS, entry_of, key_of, make_library,
    name_of, previous_library, read, row_of, run_row, seed_index, sha_of, snapshot, folders, version_row, write, write_version,
)

from sutra_app import oslayer
from sutra_app.config import Settings
from sutra_app.main import create_app
from sutra_app.ops import doctor
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

ALL = NEW_TEMPLATE_NAMES + NEW_VERSION_NAMES
RISKS = ("hld", "risks", "still-point-yoga-risks")
GOALS = ("prd", "goals", "still-point-yoga-goals")
DATA_FLOW = ("hld", "data-flow", "still-point-yoga-data-flow")


def old_versions() -> list[str]:
    """`artifact/section/slug@vN` of every version of the seed that an install before sync 4 already had."""
    gone = {(k, n) for k, n in NEW_VERSIONS}
    return sorted(f"{name_of(key_of(e))}@v{v['version']}" for e in seed_index()["templates"] if key_of(e) not in set(NEW_TEMPLATES)
                  for v in e["versions"] if (key_of(e), v["version"]) not in gone)


def index_of(library: Path) -> dict:
    return read(library / "index.json")


def synced(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    previous_library(data)
    doctor.sync_seed_library(data)
    return data, data / "library"


# ---- the shipped seed is what the fixtures assume ---------------------------------------------------------------------------------

def test_the_shipped_seed_holds_what_sync_4_added(tmp_path):
    doc = seed_index()
    for key in NEW_TEMPLATES:
        assert entry_of(doc, key)["versions"]
    for key, n in NEW_VERSIONS:
        assert row_of(doc, key, n)["sha"]
    assert len(doc["templates"]) - len(NEW_TEMPLATES) == len(old_versions()) == 26 and len(doc["runs"]) == 8
    library = previous_library(tmp_path / "data")
    assert len(index_of(library)["templates"]) == 26 and "runs" not in index_of(library)


# ---- a library before sync 4 gains templates, versions, provenance and runs -------------------------------------------------------

def test_a_library_at_the_previous_seed_gains_the_templates_versions_provenance_and_runs(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    seed = doctor.seed_dir()
    assert doctor.missing_seed_templates(data) == NEW_TEMPLATE_NAMES
    assert doctor.missing_seed_versions(data) == NEW_VERSION_NAMES
    before = snapshot(library)
    report: dict = {}
    added = doctor.sync_seed_library(data, report=report)
    assert added == ALL
    assert report["templates"] == NEW_TEMPLATE_NAMES and report["versions"] == NEW_VERSION_NAMES and report["skipped"] == []
    assert sorted(report["filled"]) == old_versions()                          # the provenance of its 26 old versions
    assert all(keys == ["business", "made_by.date", "mock"] for keys in report["filled"].values())
    assert len(report["runs"]) == 8
    assert index_of(library) == read(seed / "index.json")                      # with no runs of its own the library is the seed, as data
    assert (library / "index.json").read_bytes() == (seed / "index.json").read_bytes()
    for entry in seed_index()["templates"]:
        for row in entry["versions"]:
            folder = Path(*key_of(entry), f"v{row['version']}")
            for name in ("spec.json", "schema.json", "model.py"):
                assert (library / folder / name).read_bytes() == (seed / folder / name).read_bytes()
            assert read(library / folder / "meta.json") == read(seed / folder / "meta.json")
    after = snapshot(library)
    assert before.keys() <= after.keys()                                       # nothing it had is gone
    assert sorted(n for n in before if after[n] != before[n]) == sorted(["index.json"] + [f"{n.split('@v')[0]}/v{n.split('@v')[1]}/meta.json" for n in old_versions()])
    assert doctor.missing_seed_templates(data) == [] and doctor.missing_seed_versions(data) == []
    assert not [p for p in [*after, *folders(library)] if ".tmp-" in p or ".sync-" in p]          # no temp file or folder is left behind


def test_nothing_the_install_has_is_overwritten(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    own = ("prd", "problem", "acme-own")                                       # a template of the owner's own, which the seed does not have
    row = version_row(own, 1, sha_of("own"), provenance=False)
    write_version(library, own, row)
    doc = index_of(library)
    doc["templates"].append({"artifact": "prd", "section": "Problem", "section_slug": "problem", "slug": "acme-own", "name": "Acme Own", "kind": "specialised",
                             "extends": "prd/problem@generic/1", "versions": [row], "description": "mine"})
    entry_of(doc, GOALS)["description"] = "the owner's words"                    # the seed has other words for it: not provenance, so not touched
    taken = row_of(doc, GOALS, 1)
    taken["used_by"] = [*taken["used_by"], {"run": "j2-20270101-000000", "workflow": "W-1", "atom": "W-1.a1", "action": "reused"}]
    meta_path = library.joinpath(*GOALS, "v1", "meta.json")
    meta = read(meta_path)
    meta["used_by"] = taken["used_by"]
    write(meta_path, meta)
    doc["runs"] = {"j2-20270101-000000": run_row("j2-20270101-000000", "The owner's own run"), "j2-20261103-154028": {"run": "j2-20261103-154028", "mine": True}}
    write(library / "index.json", doc)
    own_files = snapshot(library.joinpath(*own))
    doctor.sync_seed_library(data)
    after = index_of(library)
    assert snapshot(library.joinpath(*own)) == own_files and entry_of(after, own)["versions"] == [row]
    assert entry_of(after, GOALS)["description"] == "the owner's words" and row_of(after, GOALS, 1)["used_by"] == taken["used_by"]
    assert read(meta_path)["used_by"] == taken["used_by"]
    assert row_of(after, GOALS, 1)["business"] == row_of(seed_index(), GOALS, 1)["business"]          # and the provenance it lacked is there
    assert after["runs"]["j2-20270101-000000"]["business"] == "The owner's own run"
    assert after["runs"]["j2-20261103-154028"] == {"run": "j2-20261103-154028", "mine": True}            # a run id it has is never replaced
    assert len(after["runs"]) == 9                                                                      # the owner's two, the seed's other seven


def test_provenance_is_added_only_where_it_is_absent(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    seed_rows = seed_index()
    doc = index_of(library)
    row = row_of(doc, RISKS, 1)                                                # the owner's version says its own business and date
    row["business"] = {"name": "Mine", "type": "mine"}
    row["made_by"]["date"] = "2020-01-01 00:00:00"
    meta_path = library.joinpath(*RISKS, "v1", "meta.json")
    meta = read(meta_path)
    meta["business"] = {"name": "Mine", "type": "mine"}
    meta["made_by"] = dict(row["made_by"])
    write(meta_path, meta)
    other = read(library.joinpath(*GOALS, "v1", "meta.json"))                   # a made_by without a date gets the date, and no other key of it changes
    other["made_by"] = {**row_of(doc, GOALS, 1)["made_by"], "agent": "the owner's agent"}
    write(library.joinpath(*GOALS, "v1", "meta.json"), other)
    write(library / "index.json", doc)
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    after = index_of(library)
    assert row_of(after, RISKS, 1)["business"] == {"name": "Mine", "type": "mine"} and row_of(after, RISKS, 1)["made_by"]["date"] == "2020-01-01 00:00:00"
    assert row_of(after, RISKS, 1)["mock"] == row_of(seed_rows, RISKS, 1)["mock"]
    assert report["filled"][f"{name_of(RISKS)}@v1"] == ["mock"]
    kept = read(meta_path)
    assert kept["business"] == {"name": "Mine", "type": "mine"} and kept["made_by"]["date"] == "2020-01-01 00:00:00" and kept["mock"] == row_of(seed_rows, RISKS, 1)["mock"]
    dated = read(library.joinpath(*GOALS, "v1", "meta.json"))["made_by"]
    assert dated["agent"] == "the owner's agent" and dated["date"] == row_of(seed_rows, GOALS, 1)["made_by"]["date"]


# ---- a number is never renumbered -------------------------------------------------------------------------------------------------

def test_a_version_number_the_owner_took_is_kept_and_the_seeds_is_skipped_not_renumbered(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    own = version_row(PROBLEM, 2, sha_of("the owner's own spec"), provenance=False)       # the seed's v2 of this template has another spec
    write_version(library, PROBLEM, own)
    doc = index_of(library)
    entry_of(doc, PROBLEM)["versions"].append(own)
    write(library / "index.json", doc)
    folder = library.joinpath(*PROBLEM, "v2")
    mine = snapshot(folder)
    wanted = [n for n in NEW_VERSION_NAMES if not n.endswith("still-point-yoga-problem@v2")]
    assert doctor.missing_seed_versions(data) == wanted                       # the sync cannot give that one, so it is not "missing"
    report: dict = {}
    added = doctor.sync_seed_library(data, report=report)
    assert added == NEW_TEMPLATE_NAMES + wanted
    assert [(s["template"], s["version"]) for s in report["skipped"]] == [(name_of(PROBLEM), 2)]
    assert "taken" in report["skipped"][0]["why"] and "not renumbered" in report["skipped"][0]["why"]
    assert snapshot(folder) == mine and row_of(index_of(library), PROBLEM, 2) == own
    assert not library.joinpath(*PROBLEM, "v3").exists()                      # the seed's v2 did not move to a free number
    assert doctor.missing_seed_versions(data) == []


def test_the_same_spec_at_another_number_counts_as_present(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    seed = doctor.seed_dir()
    shutil.copytree(seed.joinpath(*REQUIREMENTS, "v2"), library.joinpath(*REQUIREMENTS, "v5"))        # the seed's v2 spec, as the owner's own v5
    row = json.loads(json.dumps(row_of(seed_index(), REQUIREMENTS, 2)))
    for name in PROVENANCE_KEYS:
        row.pop(name, None)
    row["made_by"].pop("date")
    row["version"] = 5
    meta_path = library.joinpath(*REQUIREMENTS, "v5", "meta.json")
    meta = read(meta_path)
    for name in (*PROVENANCE_KEYS, "made_by"):
        meta.pop(name, None)
    write(meta_path, meta)
    doc = index_of(library)
    entry_of(doc, REQUIREMENTS)["versions"].append(row)
    write(library / "index.json", doc)
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    assert report["versions"] == [n for n in NEW_VERSION_NAMES if not n.endswith("still-point-yoga-requirements@v2")]
    assert not library.joinpath(*REQUIREMENTS, "v2").exists() and library.joinpath(*REQUIREMENTS, "v3").is_dir()
    seed_row = row_of(seed_index(), REQUIREMENTS, 2)
    got = row_of(index_of(library), REQUIREMENTS, 5)
    assert got["business"] == seed_row["business"] and got["made_by"]["date"] == seed_row["made_by"]["date"] and got["mock"] == seed_row["mock"]
    assert got["collected_from"] == seed_row["collected_from"] and sorted(report["filled"][f"{name_of(REQUIREMENTS)}@v5"]) == ["business", "collected_from", "made_by.date", "mock"]
    assert read(meta_path)["collected_from"] == seed_row["collected_from"]


# ---- idempotent, locked, marked ---------------------------------------------------------------------------------------------------

def test_a_second_sync_changes_nothing_byte_for_byte(tmp_path):
    data, library = synced(tmp_path)
    files, dirs, stamp = snapshot(library), folders(library), (library / "index.json").stat().st_mtime_ns
    report: dict = {}
    assert doctor.sync_seed_library(data, report=report) == []
    assert report == {"templates": [], "versions": [], "filled": {}, "skipped": [], "runs": []}
    assert snapshot(library) == files and folders(library) == dirs and (library / "index.json").stat().st_mtime_ns == stamp       # not even rewritten


def test_a_held_lock_makes_the_sync_give_up_and_leave_every_file_as_it_was(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(doctor, "LOCK_WAIT_S", 0.2)
    data = tmp_path / "data"
    library = previous_library(data)
    fd = os.open(library / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)       # another process: a run that is storing a template
    assert oslayer.try_lock(fd)
    before, dirs = snapshot(library), folders(library)
    try:
        with pytest.raises(doctor.LibraryBusy) as busy:
            doctor.sync_seed_library(data)
        assert isinstance(busy.value, OSError) and "locked by another process" in str(busy.value)
        with caplog.at_level(logging.WARNING, logger="sutra_app.ops.doctor"):
            assert doctor.sync_seed_once(data) is None                          # the start goes on: a line in the log, and no marker
        assert "not synced" in caplog.text and "locked by another process" in caplog.text and "tries again" in caplog.text
        assert not (library / doctor.SEED_MARKER).exists()
        assert snapshot(library) == before and folders(library) == dirs
    finally:
        oslayer.unlock(fd)
        os.close(fd)
    assert doctor.sync_seed_library(data) == ALL                                # the lock is free: the sync runs


def test_the_sync_holds_the_lock_that_a_runs_store_takes(tmp_path, monkeypatch):
    from sutra_app.engine import j2_template_lib as lib
    data = tmp_path / "data"
    library = previous_library(data)
    monkeypatch.setenv("J2_LIBRARY_DIR", str(library))
    monkeypatch.setattr(lib, "LOCK_WAIT_S", 0.2)
    real, seen = doctor._apply_seed, []

    def probe(*args, **kwargs):
        with pytest.raises(lib.LibraryBusy):                                    # inside the sync, `store` and `mark_used` wait: it is their file and their calls
            with lib._library_lock():
                pass
        seen.append("busy")
        return real(*args, **kwargs)
    monkeypatch.setattr(doctor, "_apply_seed", probe)
    doctor.sync_seed_library(data)
    assert seen == ["busy"]
    with lib._library_lock():                                                   # and it is free afterwards
        pass


def test_the_start_up_sync_runs_once_per_seed(tmp_path, caplog):
    data = tmp_path / "data"
    library = previous_library(data)
    seed = doctor.seed_dir()
    with caplog.at_level(logging.INFO, logger="sutra_app.ops.doctor"):
        report = doctor.sync_seed_once(data)
    assert report["templates"] == NEW_TEMPLATE_NAMES and report["versions"] == NEW_VERSION_NAMES and len(report["filled"]) == 26 and len(report["runs"]) == 8
    assert "6 template(s), 5 version(s), provenance on 26 version(s), 8 run(s)" in caplog.text
    marker = library / doctor.SEED_MARKER
    assert marker.read_text(encoding="utf-8") == hashlib.sha256((seed / "index.json").read_bytes()).hexdigest() + "\n"
    gone = library.joinpath(*REQUIREMENTS, "v3")
    shutil.rmtree(gone)                                                          # the marker stops a second start: it does not look again
    assert doctor.sync_seed_once(data) is None and not gone.exists()
    other = tmp_path / "other-seed"                                              # a newer app ships another seed: the marker no longer matches, so it syncs
    shutil.copytree(seed, other)
    doc = read(other / "index.json")
    doc["runs"]["j2-20261109-000000"] = run_row("j2-20261109-000000")
    write(other / "index.json", doc)
    again = doctor.sync_seed_once(data, other)
    assert again["runs"] == ["j2-20261109-000000"] and again["versions"] == [f"{name_of(REQUIREMENTS)}@v3"] and gone.is_dir()
    assert marker.read_text(encoding="utf-8").strip() == hashlib.sha256((other / "index.json").read_bytes()).hexdigest()
    assert doctor.sync_seed_once(data, other) is None


def test_a_data_folder_without_a_library_is_left_to_the_engine_at_start_and_gets_the_whole_seed_by_command(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    assert doctor.sync_seed_once(data) is None and not (data / "library").exists()    # the engine seeds it whole at the first run (host/loop.py)
    report: dict = {}
    added = doctor.sync_seed_library(data, report=report)
    seed = doctor.seed_dir()
    assert added == sorted(name_of(key_of(e)) for e in seed_index()["templates"]) and report["versions"] == [] and len(report["runs"]) == 8
    assert snapshot(data / "library") == snapshot(seed)                           # the seed, byte for byte
    assert [p.name for p in data.iterdir()] == ["library"]                        # and no temp folder beside it
    assert doctor.sync_seed_library(data) == []


# ---- an index that is not an index ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["{not json", "", "[]", '{"schema": "template-library/1"}', '{"templates": {}}', '"index"'])
def test_an_index_that_is_not_json_is_left_alone_and_reported(tmp_path, caplog, text):
    data = tmp_path / "data"
    library = previous_library(data)
    (library / "index.json").write_text(text, encoding="utf-8")
    before, dirs = snapshot(library), folders(library)
    with pytest.raises(doctor.LibraryUnreadable) as problem:
        doctor.sync_seed_library(data)
    assert isinstance(problem.value, doctor.SeedSyncError) and isinstance(problem.value, OSError) and "index.json" in str(problem.value)
    assert snapshot(library) == before and folders(library) == dirs
    with caplog.at_level(logging.WARNING, logger="sutra_app.ops.doctor"):
        assert doctor.sync_seed_once(data) is None
    assert "not synced" in caplog.text and "index.json" in caplog.text and not (library / doctor.SEED_MARKER).exists()
    assert snapshot(library) == before
    assert doctor.missing_seed_versions(data) == []                               # nothing to say about versions of an index it cannot read


def test_an_empty_index_or_none_at_all_is_read_as_an_empty_one_as_j2_reads_it(tmp_path):
    for text in ("{}", None):
        data = tmp_path / ("a" if text else "b")
        library = previous_library(data)
        if text is None:
            (library / "index.json").unlink()
        else:
            (library / "index.json").write_text(text, encoding="utf-8")
        report: dict = {}
        doctor.sync_seed_library(data, report=report)
        assert len(report["templates"]) == 32 and report["versions"] == [] and report["skipped"] == []        # the folders it has are adopted by their sha
        assert index_of(library) == read(doctor.seed_dir() / "index.json")


# ---- repair: what the library lost ------------------------------------------------------------------------------------------------

def test_a_library_that_lost_index_entries_or_folders_is_repaired_from_the_seed_and_a_folder_with_another_spec_is_not(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    doc = index_of(library)
    doc["templates"] = [e for e in doc["templates"] if key_of(e) not in (RISKS, DATA_FLOW)]                  # the index lost two entries, the folders stay
    write(library / "index.json", doc)
    meta_path = library.joinpath(*DATA_FLOW, "v1", "meta.json")                                              # and one of those folders was changed by hand
    meta = read(meta_path)
    meta["sha"] = sha_of("changed by hand")
    write(meta_path, meta)
    shutil.rmtree(library.joinpath(*GOALS))                                                                  # a template folder is gone, its entry stays
    pages = ("lld", "pages-and-sections", "still-point-yoga-pages-and-sections")
    shutil.rmtree(library.joinpath(*pages, "v1"))                                                            # and a version folder of a template that stays
    changed = meta_path.read_bytes()
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    assert report["templates"] == sorted([*NEW_TEMPLATE_NAMES, name_of(RISKS), name_of(GOALS)])             # adopted by sha; restored from the seed
    assert report["versions"] == sorted([*NEW_VERSION_NAMES, f"{name_of(pages)}@v1"])
    assert [(s["template"], s["version"]) for s in report["skipped"]] == [(name_of(DATA_FLOW), 1)] and "another spec" in report["skipped"][0]["why"]
    assert meta_path.read_bytes() == changed and not any(key_of(e) == DATA_FLOW for e in index_of(library)["templates"])
    seed = doctor.seed_dir()
    assert library.joinpath(*GOALS, "v1", "model.py").read_bytes() == seed.joinpath(*GOALS, "v1", "model.py").read_bytes()
    assert library.joinpath(*pages, "v1", "spec.json").read_bytes() == seed.joinpath(*pages, "v1", "spec.json").read_bytes()
    assert entry_of(index_of(library), RISKS) == entry_of(read(seed / "index.json"), RISKS)


def test_missing_seed_versions_is_what_the_sync_adds_and_it_writes_nothing(tmp_path):
    data = tmp_path / "data"
    library = previous_library(data)
    shutil.rmtree(library.joinpath(*PROBLEM, "v1"))                                                          # a lost folder is a version the library lacks too
    before = snapshot(library)
    listed = doctor.missing_seed_versions(data)
    assert listed == sorted([*NEW_VERSION_NAMES, f"{name_of(PROBLEM)}@v1"])
    assert snapshot(library) == before and not (library / ".lock").exists()                                  # read only: no write, no lock file
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    assert report["versions"] == listed
    assert doctor.missing_seed_versions(data) == [] and doctor.missing_seed_versions(tmp_path / "nowhere") == []


# ---- seeds made by hand: the branches the shipped seed does not reach -----------------------------------------------------------------

def test_a_seed_entry_with_an_unsafe_name_or_a_missing_folder_is_not_followed(tmp_path):
    seed = make_library(tmp_path / "seed", {("prd", "problem", "acme-problem"): {1: sha_of("a"), 2: sha_of("b")}, ("prd", "goals", "acme-goals"): {1: sha_of("c")}})
    doc = read(seed / "index.json")
    doc["templates"].append({**doc["templates"][0], "slug": "..", "versions": [version_row(("prd", "problem", ".."), 1, sha_of("evil"))]})
    write(seed / "index.json", doc)
    shutil.rmtree(seed.joinpath("prd", "problem", "acme-problem", "v2"))                                    # the seed lists a version it has no folder for
    library = make_library(tmp_path / "data" / "library", {("prd", "problem", "acme-problem"): {1: sha_of("a")}}, provenance=False)
    report: dict = {}
    added = doctor.sync_seed_library(tmp_path / "data", seed, report=report)
    assert added == ["prd/goals/acme-goals"] and [(s["template"], s["version"], s["why"]) for s in report["skipped"]] == [
        ("prd/problem/acme-problem", 2, "the seed has no folder for it")]
    assert sorted(p.name for p in library.joinpath("prd").iterdir()) == ["goals", "problem"] and not library.joinpath("prd", "v1").exists()      # `..` was not followed
    assert [key_of(e) for e in index_of(library)["templates"]] == [("prd", "goals", "acme-goals"), ("prd", "problem", "acme-problem")]
    assert row_of(index_of(library), ("prd", "problem", "acme-problem"), 1)["business"] == {"name": "Acme", "type": "shop"}        # filled from the seed


def test_a_damaged_entry_or_runs_value_is_reported_and_the_rest_still_syncs(tmp_path):
    seed = make_library(tmp_path / "seed", {("prd", "problem", "acme-problem"): {1: sha_of("a")}, ("prd", "goals", "acme-goals"): {1: sha_of("c")}},
                        runs={"j2-20261103-100000": run_row("j2-20261103-100000")})
    library = make_library(tmp_path / "data" / "library", {("prd", "problem", "acme-problem"): {1: sha_of("a")}}, provenance=False, runs={})
    doc = index_of(library)
    doc["templates"][0]["versions"] = "none"                                                                  # an entry whose versions are not a list
    doc["runs"] = ["a list"]                                                                                  # and runs that are not an object
    write(library / "index.json", doc)
    report: dict = {}
    added = doctor.sync_seed_library(tmp_path / "data", seed, report=report)
    assert added == ["prd/goals/acme-goals"]
    assert {(s["template"], s["version"]) for s in report["skipped"]} == {("prd/problem/acme-problem", None), ("index.json", None)}
    after = index_of(library)
    assert after["runs"] == ["a list"] and entry_of(after, ("prd", "problem", "acme-problem"))["versions"] == "none"


def test_a_new_template_gets_the_seeds_entry_in_the_seeds_key_order_and_the_index_stays_sorted(tmp_path):
    seed = make_library(tmp_path / "seed", {("prd", "users", "acme-users"): {1: sha_of("u"), 2: sha_of("v")}, ("hld", "risks", "acme-risks"): {1: sha_of("r")}})
    library = make_library(tmp_path / "data" / "library", {("lld", "pages", "acme-pages"): {1: sha_of("p")}, ("prd", "goals", "acme-goals"): {1: sha_of("g")}}, provenance=False)
    doctor.sync_seed_library(tmp_path / "data", seed)
    doc = index_of(library)
    assert [key_of(e) for e in doc["templates"]] == sorted(key_of(e) for e in doc["templates"]) and len(doc["templates"]) == 4
    assert list(entry_of(doc, ("prd", "users", "acme-users"))) == list(entry_of(read(seed / "index.json"), ("prd", "users", "acme-users")))
    assert [v["version"] for v in entry_of(doc, ("prd", "users", "acme-users"))["versions"]] == [1, 2] and "runs" not in doc


# ---- the server's start ------------------------------------------------------------------------------------------------------------

def started(tmp_path: Path, data: Path) -> None:
    """The app's lifespan on `data`, up and down (`start_services` runs in it)."""
    settings = Settings.load({}, data_dir=data, token="t" * 20, env_file=tmp_path / "none.env", engine="fake")
    with TestClient(create_app(settings, connector=ScriptedConnector()), base_url="http://127.0.0.1:8780"):
        pass


def test_the_server_start_syncs_an_existing_library_once_and_never_creates_one(tmp_path, monkeypatch, caplog):
    data = tmp_path / "data"
    library = previous_library(data)
    started(tmp_path, data)
    assert index_of(library) == read(doctor.seed_dir() / "index.json") and (library / doctor.SEED_MARKER).is_file()
    gone = library.joinpath(*REQUIREMENTS, "v3")
    shutil.rmtree(gone)
    started(tmp_path, data)                                                                                    # a second start: the marker says it was done
    assert not gone.exists()
    fresh = tmp_path / "fresh" / "data"
    started(tmp_path, fresh)                                                                                   # a data folder with no library: the engine's first run seeds it
    assert not (fresh / "library").exists()
    monkeypatch.setattr(doctor, "LOCK_WAIT_S", 0.2)
    (library / doctor.SEED_MARKER).unlink()
    fd = os.open(library / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    assert oslayer.try_lock(fd)
    try:
        with caplog.at_level(logging.WARNING, logger="sutra_app.ops.doctor"):
            started(tmp_path, data)                                                                            # a held lock never stops the app from starting
    finally:
        oslayer.unlock(fd)
        os.close(fd)
    assert "not synced" in caplog.text and not gone.exists()
