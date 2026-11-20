"""D255: scripts/usd_basis.py, the read-only measurement behind the dollar budget. Per recorded run it sums the API price each AI call reported,
counts the calls with and without one (by provider and basis), and divides by the run's credits spent; then the median and spread of dollars
per credit, the fallback dollars per million tokens for calls with no price, and the proposed default (1000 credits, rounded to a clean amount)."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "usd_basis.py"
spec = importlib.util.spec_from_file_location("usd_basis", SCRIPT)
ub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ub)

LEDGER = """CREATE TABLE usage_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, task_id TEXT, usd REAL,
  tokens_in INTEGER, tokens_out INTEGER, detail_json TEXT)"""
A, B, C = "tsk_00000000000a", "tsk_00000000000b", "tsk_00000000000c"


def call(conn, provider, task, usd, tin, tout, basis):
    conn.execute("INSERT INTO usage_ledger (provider, task_id, usd, tokens_in, tokens_out, detail_json) VALUES (?, ?, ?, ?, ?, ?)",
                 (provider, task, usd, tin, tout, json.dumps({"usd_basis": basis})))


def run_folder(data, dept, run, task, spent):
    folder = data / "departments" / dept / "runs" / run
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({"run_id": run, "task_id": task}))
    (folder / "report.json").write_text(json.dumps({"metrics": {"budget": {"total": 100, "spent": spent}}}))


@pytest.fixture
def data(tmp_path):
    data = tmp_path / "beta"
    data.mkdir()
    conn = sqlite3.connect(data / "db.sqlite3")
    conn.execute(LEDGER)
    call(conn, "claude", A, 1.00, 200_000, 50_000, "reported")      # $4 per million tokens
    call(conn, "claude", A, 0.50, 100_000, 25_000, "reported")
    call(conn, "stub", A, 0.0, 0, 0, "none")                          # stub rows never count
    call(conn, "claude", B, 2.00, 400_000, 100_000, "reported")
    call(conn, "codex", B, None, 30_000, 10_000, "unknown")           # Codex reports no price
    call(conn, "claude", C, 0.40, 50_000, 50_000, "reported")         # a task with no run folder
    call(conn, "claude", C, 1.00, 25_000, 0, "reported")              # $40 per million: the median per call would stay $4, the pooled rate moves
    conn.commit()
    conn.close()
    run_folder(data, "web", "j2-1", A, 100)
    run_folder(data, "web", "j2-2", B, 50)
    run_folder(data, "ops", "j2-3", "tsk_00000000000d", 0)            # a run with no calls
    return data


def test_per_run_cost_and_priced_counts(data):
    rows = {r["task_id"]: r for r in ub.measure(data)["runs"]}
    assert set(rows) == {A, B, "tsk_00000000000d"}
    a, b = rows[A], rows[B]
    assert (a["usd"], a["priced"], a["unpriced"], a["tokens"], a["spent"]) == (1.5, 2, 0, 375_000, 100)
    assert a["usd_per_credit"] == pytest.approx(0.015)
    assert (b["usd"], b["priced"], b["unpriced"], b["tokens"], b["spent"]) == (2.0, 1, 1, 540_000, 50)
    assert b["usd_per_credit"] == pytest.approx(0.04)
    assert rows["tsk_00000000000d"]["usd_per_credit"] is None
    calls = ub.measure(data)["calls"]
    assert calls == {("claude", "reported"): {"priced": 5, "unpriced": 0}, ("codex", "unknown"): {"priced": 0, "unpriced": 1}}


def test_median_spread_and_default(data):
    m = ub.measure(data)
    s = m["per_credit"]
    assert (s["runs"], s["min"], s["max"]) == (2, pytest.approx(0.015), pytest.approx(0.04))
    assert s["median"] == pytest.approx(0.0275)
    assert m["fallback_usd_per_mtok"] == pytest.approx(4.9)      # pooled: $4.90 over 1.0M priced tokens (the median per call would be $4)
    spread = ub.spread([0.01, 0.02, 0.03, 0.04, 0.05])
    assert (spread["p25"], spread["median"], spread["p75"]) == (pytest.approx(0.02), pytest.approx(0.03), pytest.approx(0.04))


@pytest.mark.parametrize("dollars, clean", [(18.72, 20), (27.5, 30), (12.4, 10), (47.0, 45), (52.0, 50), (86.0, 90), (1.2, 5)])
def test_the_default_is_rounded_to_a_clean_amount(dollars, clean):
    assert ub.clean_amount(dollars) == clean


def test_presets_are_half_and_double():
    assert ub.presets(20) == (10, 20, 40)


def test_opens_read_only_and_refuses_the_stable_folder(data, tmp_path, monkeypatch, capsys):
    conn = ub.open_ro(data / "db.sqlite3")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO usage_ledger (provider) VALUES ('claude')")
    conn.close()
    home = tmp_path / "home"
    (home / ".sutra-pro").mkdir(parents=True)
    (home / "link").symlink_to(home / ".sutra-pro")
    monkeypatch.setenv("HOME", str(home))
    for refused in (home / ".sutra-pro", home / "link", home / ".sutra-pro" / "departments"):
        assert ub.main(["--data", str(refused)]) == 2
        assert "~/.sutra-pro" in capsys.readouterr().err
    assert ub.main(["--data", str(tmp_path / "nothing")]) == 2                 # no db.sqlite3 there


def test_main_prints_numbers_and_the_proposal(data, capsys):
    assert ub.main(["--data", str(data)]) == 0
    out = capsys.readouterr().out
    assert "tsk_00000000000a" in out and "median" in out and "fallback" in out
    assert "default $30 (presets $15 / $30 / $60)" in out                       # 1000 x $0.0275 = $27.50 -> $30
