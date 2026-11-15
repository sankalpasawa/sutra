"""What the seed the app ships (J2 1adb8ecd, sync 6) does to an install that has the sync 5 library (D185, D144): the install gains the new
families, versions and run templates and loses nothing it had; nothing the owner changed is overwritten, renamed or moved; a second sync
changes nothing. The install's library is the real seed of J2 sync 5 (`fixtures/seed-sync5`, 157 files), here with the owner's own changes on
top of it. The numbers 81, 107 and 4 are what the shipped seed holds today; a newer seed changes them on purpose, in the same commit."""
import json
import shutil
from pathlib import Path

import pytest
from seedlib import key_of, read, snapshot, write

from sutra_app.ops import doctor

SYNC5 = Path(__file__).parent / "fixtures" / "seed-sync5"
FAMILIES, VERSIONS, RUN_TEMPLATES = 81, 107, 4


def install(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    shutil.copytree(SYNC5, data / "library")
    return data, data / "library"


def counts(library: Path) -> tuple[int, int, int]:
    doc = read(library / "index.json")
    return len(doc["templates"]), sum(len(e["versions"]) for e in doc["templates"]), len(doc.get("run_templates") or [])


def shas(library: Path) -> dict[tuple, str]:
    return {(*key_of(e), v["version"]): v["sha"] for e in read(library / "index.json")["templates"] for v in e["versions"]}


def test_the_sync_5_library_is_what_these_tests_assume():
    doc = read(SYNC5 / "index.json")
    assert counts(SYNC5) == (32, 39, 0) and "run_templates" not in doc and len(doc["runs"]) == 8 and not (SYNC5 / "run-templates").exists()


def test_the_shipped_seed_holds_what_sync_6_added():
    seed = doctor.seed_dir()
    assert counts(seed) == (FAMILIES, VERSIONS, RUN_TEMPLATES)
    assert sorted(p.parent.name for p in (seed / "run-templates").glob("*/template.json")) == sorted(r["id"] for r in read(seed / "index.json")["run_templates"])
    assert sum(1 for e in read(seed / "index.json")["templates"] for v in e["versions"] if "renamed_from" in v or "adapted_from" in v) == 67


def test_a_sync_5_library_gains_81_families_107_versions_and_4_run_templates_and_loses_nothing(tmp_path):
    data, library = install(tmp_path)
    before, had = snapshot(library), shas(library)
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    assert counts(library) == (FAMILIES, VERSIONS, RUN_TEMPLATES)
    after = snapshot(library)
    assert [name for name in before if name not in after] == []                                  # no file is gone
    assert {name for name in before if after[name] != before[name]} == {"index.json"}            # the index only gained rows (below); no folder file changed
    assert {key: sha for key, sha in shas(library).items() if key in had} == had                 # every old row is there, at its number, with its sha
    assert sorted(report["run_templates"]) == sorted(r["id"] for r in read(library / "index.json")["run_templates"])
    assert len(report["renamed"]) == 67 and report["skipped"] == []
    for row in read(library / "index.json")["run_templates"]:
        for file in ("template.json", "schema.json"):
            assert (library / "run-templates" / row["id"] / file).is_file()


def test_the_old_families_stay_where_they_are_and_a_renamed_family_is_added_beside_them(tmp_path):
    data, library = install(tmp_path)
    old_dirs = {p.relative_to(library).as_posix() for p in library.glob("*/*/*") if p.is_dir()}
    doctor.sync_seed_library(data)
    now = {p.relative_to(library).as_posix() for p in library.glob("*/*/*") if p.is_dir() and p.parent.parent.name != "run-templates"}
    assert old_dirs <= now and len(now) == FAMILIES                                              # every old family folder is still there
    # each added version that J2 says was renamed has its own folder under the new family and the old family still holds its number
    seed = read(doctor.seed_dir() / "index.json")
    renamed = [(e, v) for e in seed["templates"] for v in e["versions"] if v.get("renamed_from")]
    assert renamed
    for entry, row in renamed:
        assert (library.joinpath(*key_of(entry), f"v{row['version']}") / "meta.json").is_file()


def test_what_the_owner_changed_is_not_overwritten_renamed_or_moved(tmp_path):
    data, library = install(tmp_path)
    doc = read(library / "index.json")
    mine = doc["templates"][0]
    mine["description"] = "owner's own description"
    mine["versions"][0]["description"] = "owner's own version note"
    doc["runs"]["j2-20270101-000000"] = {"run": "j2-20270101-000000", "business": "the owner's own run"}
    write(library / "index.json", doc)
    folder = library.joinpath(*key_of(mine), f"v{mine['versions'][0]['version']}")
    note = folder / "owner-note.txt"
    note.write_text("kept\n", encoding="utf-8")
    meta = read(folder / "meta.json")
    meta["used_by"].append({"run": "j2-20270101-000000", "workflow": "W-1", "atom": "W-1.a1", "action": "reused"})
    write(folder / "meta.json", meta)
    own = {"id": "owner-made", "name": "A", "description": "mine", "business_type": "shop", "stages": ["prd"], "workflows": 1, "mock": False,
           "made_from_run": "j2-20270101-000000", "created": "2027-01-01T00:00:00", "used_by": 5}
    doc = read(library / "index.json")
    doc["run_templates"] = [own]
    write(library / "index.json", doc)
    (library / "run-templates" / "owner-made").mkdir(parents=True)
    write(library / "run-templates" / "owner-made" / "template.json", {"id": "owner-made", "made_from_run": "j2-20270101-000000"})
    write(library / "run-templates" / "owner-made" / "schema.json", {})
    doctor.sync_seed_library(data)
    after = read(library / "index.json")
    entry = next(e for e in after["templates"] if key_of(e) == key_of(mine))
    assert entry["description"] == "owner's own description" and entry["versions"][0]["description"] == "owner's own version note"
    assert after["runs"]["j2-20270101-000000"]["business"] == "the owner's own run"
    assert note.read_text() == "kept\n" and read(folder / "meta.json")["used_by"][-1]["run"] == "j2-20270101-000000"
    rows = {r["id"]: r for r in after["run_templates"]}
    assert rows["owner-made"] == own and len(rows) == RUN_TEMPLATES + 1
    assert (library / "run-templates" / "owner-made" / "template.json").is_file()


def test_a_second_sync_changes_nothing_and_the_start_up_sync_does_it_once(tmp_path):
    data, library = install(tmp_path)
    first = doctor.sync_seed_once(data)
    assert first and len(first["run_templates"]) == RUN_TEMPLATES
    done, dirs = snapshot(library), sorted(p.relative_to(library).as_posix() for p in library.rglob("*") if p.is_dir())
    assert doctor.sync_seed_once(data) is None                                                  # the marker holds
    report: dict = {}
    assert doctor.sync_seed_library(data, report=report) == []
    assert report == {"templates": [], "versions": [], "filled": {}, "skipped": [], "runs": [], "run_templates": [], "renamed": {}}
    assert snapshot(library) == done and sorted(p.relative_to(library).as_posix() for p in library.rglob("*") if p.is_dir()) == dirs
    assert doctor.missing_seed_templates(data) == [] and doctor.missing_seed_versions(data) == [] and doctor.missing_seed_run_templates(data) == []


def test_before_the_sync_the_doctor_check_names_the_run_templates_and_after_it_is_ok(tmp_path):
    data, library = install(tmp_path)
    assert len(doctor.missing_seed_run_templates(data)) == RUN_TEMPLATES
    check = doctor._check_library(data, None)
    assert check.status == "warn" and f"{RUN_TEMPLATES} seed run template(s)" in check.detail
    doctor.sync_seed_library(data)
    assert doctor._check_library(data, None).status == "ok"


def test_a_new_install_gets_the_whole_seed_with_its_run_templates(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    report: dict = {}
    doctor.sync_seed_library(data, report=report)
    assert counts(data / "library") == (FAMILIES, VERSIONS, RUN_TEMPLATES) and len(report["run_templates"]) == RUN_TEMPLATES
    assert json.loads((data / "library" / "index.json").read_text())["run_templates"][0]["id"]
    assert snapshot(data / "library") == snapshot(doctor.seed_dir())
