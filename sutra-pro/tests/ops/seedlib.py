"""Helpers of the seed-library tests (D144): a library as an install had it before sync 4, derived from the seed the app ships; a small seed
made by hand; a snapshot of a folder. Shared by `test_seed_sync.py`, `test_doctor.py` and `test_cli.py`; nothing here is a test."""
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from sutra_app.ops import doctor

PROVENANCE_KEYS = ("business", "mock", "collected_from")

# What sync 4 put into the seed: six templates (`still-point-yoga-prd-*` and the second PRD problem template) and five versions of four
# templates the earlier seed already had. `test_the_shipped_seed_holds_what_sync_4_added` checks these lists against the committed seed.
NEW_TEMPLATES = (
    ("prd", "goals", "still-point-yoga-prd-goals"),
    ("prd", "out-of-scope", "still-point-yoga-prd-out-of-scope"),
    ("prd", "problem", "still-point-yoga-problem-users-and-goals"),
    ("prd", "success-metrics", "still-point-yoga-prd-success-metrics"),
    ("prd", "success-metrics", "still-point-yoga-prd-success-metrics-and-out-of-scope"),
    ("prd", "users", "still-point-yoga-prd-users"),
)
NEW_VERSIONS = (
    (("hld", "components", "still-point-yoga-components"), 2),
    (("lld", "pages-and-sections", "still-point-yoga-pages-and-sections"), 2),
    (("prd", "problem", "still-point-yoga-problem"), 2),
    (("prd", "requirements", "still-point-yoga-requirements"), 2),
    (("prd", "requirements", "still-point-yoga-requirements"), 3),
)
PROBLEM = ("prd", "problem", "still-point-yoga-problem")
REQUIREMENTS = ("prd", "requirements", "still-point-yoga-requirements")


def name_of(key: tuple[str, str, str]) -> str:
    return "/".join(key)


NEW_TEMPLATE_NAMES = sorted(name_of(k) for k in NEW_TEMPLATES)
NEW_VERSION_NAMES = sorted(f"{name_of(k)}@v{n}" for k, n in NEW_VERSIONS)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def key_of(entry: dict) -> tuple[str, str, str]:
    return (entry["artifact"], entry["section_slug"], entry["slug"])


def seed_index() -> dict:
    return read(doctor.seed_dir() / "index.json")


def entry_of(doc: dict, key: tuple[str, str, str]) -> dict:
    return next(e for e in doc["templates"] if key_of(e) == key)


def row_of(doc: dict, key: tuple[str, str, str], version: int) -> dict:
    return next(v for v in entry_of(doc, key)["versions"] if v["version"] == version)


def snapshot(root: Path) -> dict[str, bytes]:
    """Every file under `root` (relative path -> bytes), but `.lock`: an empty file that any first use of the library creates (J2's own
    `store` too), which says nothing about what the library holds."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".lock"}


def folders(root: Path) -> list[str]:
    """Every folder under `root`, relative: a copy that was not renamed into place would show up here."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir())


def previous_library(data_dir: Path) -> Path:
    """`<data_dir>/library` as an install had it before sync 4: the shipped seed without its six new templates and five new versions,
    without the provenance keys of the versions that remain (their rows and their meta.json) and without `runs`. Returns the library."""
    library = data_dir / "library"
    shutil.copytree(doctor.seed_dir(), library)
    doc = read(library / "index.json")
    drop = {key for key in NEW_TEMPLATES}
    for key in drop:
        shutil.rmtree(library.joinpath(*key))
    doc["templates"] = [e for e in doc["templates"] if key_of(e) not in drop]
    for key, n in NEW_VERSIONS:
        shutil.rmtree(library.joinpath(*key, f"v{n}"))
        entry = entry_of(doc, key)
        entry["versions"] = [v for v in entry["versions"] if v["version"] != n]
    for entry in doc["templates"]:
        for row in entry["versions"]:
            for name in PROVENANCE_KEYS:
                row.pop(name, None)
            row["made_by"].pop("date", None)
            meta_path = library.joinpath(*key_of(entry), f"v{row['version']}", "meta.json")
            meta = read(meta_path)
            for name in (*PROVENANCE_KEYS, "made_by"):
                meta.pop(name, None)
            write(meta_path, meta)
    doc.pop("runs")
    write(library / "index.json", doc)
    return library


# ---- a small seed made by hand ----------------------------------------------------------------------------------------------------

def sha_of(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def version_row(key: tuple[str, str, str], n: int, sha: str, *, provenance: bool = True, mock: bool = True, run: str = "j2-20261103-100000") -> dict:
    row: dict[str, Any] = {"version": n, "sha": sha, "schema_sha": sha_of("schema", sha), "description": f"{name_of(key)} v{n}", "fingerprints": [sha_of("fp", sha)],
                           "business_type": key[0], "facts": [], "fields": ["a"], "enums": {},
                           "made_by": {"run": run, "workflow": "W-1", "atom": "W-1.a1", "agent": "template generator (mock)"},
                           "used_by": [{"run": run, "workflow": "W-1", "atom": "W-1.a1", "action": "created"}]}
    if provenance:
        row["made_by"]["date"] = "2026-11-03 10:00:00"
        row["business"] = {"name": "Acme", "type": "shop"}
        row["mock"] = mock
        row["collected_from"] = {"run": run, "where": "the run's copy"}
    return row


def write_version(root: Path, key: tuple[str, str, str], row: dict) -> None:
    """The four files of one version folder for `row`; its meta.json carries the row's provenance as the seed's own do."""
    folder = root.joinpath(*key, f"v{row['version']}")
    folder.mkdir(parents=True)
    meta = {"schema": "template-library/1", "name": name_of(key), "version": row["version"], "sha": row["sha"], "schema_sha": row["schema_sha"],
            "model_sha": sha_of("model", row["sha"]), "class": "Acme", "created": "2026-11-03T10:00:00", "fingerprints": row["fingerprints"],
            **{k: copy.deepcopy(row[k]) for k in ("made_by", "business", "mock", "collected_from") if k in row}, "used_by": row["used_by"]}
    write(folder / "meta.json", meta)
    write(folder / "spec.json", {"name": name_of(key), "version": row["version"], "sha": row["sha"]})
    write(folder / "schema.json", {"title": name_of(key), "sha": row["schema_sha"]})
    (folder / "model.py").write_text(f"# {name_of(key)} v{row['version']}\nclass Acme:\n    pass\n", encoding="utf-8")


def make_library(root: Path, templates: dict[tuple[str, str, str], dict[int, str]], *, provenance: bool = True, runs: dict | None = None) -> Path:
    """A small library (a seed, or an install's) at `root`: `templates` maps a key (artifact, section_slug, slug) to {version: spec sha}."""
    root.mkdir(parents=True)
    entries = []
    for key, versions in templates.items():
        rows = [version_row(key, n, sha, provenance=provenance) for n, sha in sorted(versions.items())]
        for row in rows:
            write_version(root, key, row)
        entries.append({"artifact": key[0], "section": key[1].capitalize(), "section_slug": key[1], "slug": key[2], "name": name_of(key), "kind": "specialised",
                        "extends": f"{key[0]}/{key[1]}@generic/1", "versions": rows, "description": f"{name_of(key)} template"})
    doc: dict[str, Any] = {"schema": "template-library/1", "templates": entries}
    if runs is not None:
        doc["runs"] = runs
    write(root / "index.json", doc)
    return root


def run_row(run: str, business: str = "Acme") -> dict:
    return {"run": run, "date": "2026-11-03 10:00:00", "business": business, "business_type": "shop", "mock": True, "provider": "not recorded",
            "model": "not recorded", "library": "not recorded", "decisions": [], "counts": {"created": 0, "extended": 0, "reused": 0, "generic": 0}}
