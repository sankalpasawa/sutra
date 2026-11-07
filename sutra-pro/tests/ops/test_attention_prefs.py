"""Quiet hours and the hourly cap (gap package routines-limits): the shared case table, junk refused, the file, and the routes."""
import json
import os
import stat
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.config import Settings
from sutra_app.ops import attention_api
from sutra_app.ops.attention_prefs import (
    DEFAULT_NUDGES_PER_HOUR, MAX_NUDGES_PER_HOUR, AttentionPrefs, clamp_nudges, clean_quiet_hours, window_active,
)
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.testing import FakeClock

REPO = Path(__file__).resolve().parents[2]
CASES = json.loads((REPO / "tests" / "fixtures" / "quiet_hours_cases.json").read_text(encoding="utf-8"))
TOKEN = "X-Sutra-Token"


@pytest.fixture
def prefs(tmp_path):
    return AttentionPrefs(tmp_path / "attention.json")


# ---- the shared table (the JS lane runs the same one) ------------------------------------------------------------------------------------

@pytest.mark.parametrize("case", CASES["active"], ids=lambda c: f"{c['window']}-{c['at']}")
def test_window_active_runs_the_shared_table(case):
    assert window_active(CASES["windows"][case["window"]], case["at"]) is case["quiet"], case["why"]


@pytest.mark.parametrize("case", CASES["invalid"], ids=lambda c: c["why"][:40])
def test_every_invalid_window_of_the_shared_table_is_refused(case):
    with pytest.raises(ValueError):
        clean_quiet_hours(case["value"])


def test_a_valid_window_is_cleaned_to_exactly_its_two_ends():
    assert clean_quiet_hours({"start": "21:00", "end": "08:00"}) == {"start": "21:00", "end": "08:00"}
    assert window_active({"start": "21:00", "end": "08:00"}, 23 * 60) is True and window_active({"start": "21:00", "end": "08:00"}, datetime(2026, 1, 1, 12, 0)) is False


# ---- the rate ---------------------------------------------------------------------------------------------------------------------------

def test_the_rate_clamps_numbers_and_refuses_junk_and_zero_stays_zero():
    assert (DEFAULT_NUDGES_PER_HOUR, MAX_NUDGES_PER_HOUR) == (3, 10)
    assert [clamp_nudges(n) for n in (0, 1, 3, 10, 11, 99, -4)] == [0, 1, 3, 10, 10, 10, 0]
    assert clamp_nudges("5") == 5 and clamp_nudges(7.0) == 7
    for junk in (True, False, "three", None, 2.5, [3], {"n": 3}, float("nan")):
        with pytest.raises(ValueError):
            clamp_nudges(junk)


# ---- the file ---------------------------------------------------------------------------------------------------------------------------

def test_an_absent_file_is_the_defaults(prefs):
    assert prefs.read() == {"quiet_hours": None, "nudges_per_hour": 3}
    assert not prefs.path.exists()


def test_a_write_keeps_what_it_is_not_given_and_clearing_deletes_the_key(prefs):
    prefs.write(quiet_hours={"start": "21:00", "end": "08:00"})
    prefs.write(nudges_per_hour=0)
    assert prefs.read() == {"quiet_hours": {"start": "21:00", "end": "08:00"}, "nudges_per_hour": 0}      # 0 stays 0: never unasked
    prefs.write(quiet_hours=None)
    assert prefs.read()["quiet_hours"] is None and "quiet_hours" not in json.loads(prefs.path.read_text())
    assert prefs.read()["nudges_per_hour"] == 0


def test_junk_is_refused_before_the_file_is_touched(prefs):
    prefs.write(nudges_per_hour=2)
    before = prefs.path.read_text()
    for window in ({"start": "10:00", "end": "10:00"}, {"start": "9:00", "end": "17:00"}, "21:00-08:00", True):
        with pytest.raises(ValueError):
            prefs.write(quiet_hours=window)
    with pytest.raises(ValueError):
        prefs.write(nudges_per_hour=True)
    assert prefs.path.read_text() == before


def test_the_file_is_private_atomic_and_keeps_keys_it_does_not_know(prefs):
    prefs.path.write_text(json.dumps({"version": 1, "from_a_newer_app": {"x": 1}}))
    prefs.write(nudges_per_hour=4)
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(prefs.path).st_mode) == 0o600
    assert json.loads(prefs.path.read_text())["from_a_newer_app"] == {"x": 1} and not list(prefs.path.parent.glob(".attention.json.*"))


def test_a_file_that_does_not_read_degrades_toward_speaking_and_never_raises(prefs):
    for body in ("{not json", "[1, 2]", '"text"', json.dumps({"quiet_hours": "21:00-08:00", "nudges_per_hour": "lots"}),
                 json.dumps({"quiet_hours": {"start": "10:00", "end": "10:00"}, "nudges_per_hour": True})):
        prefs.path.write_text(body)
        assert prefs.read() == {"quiet_hours": None, "nudges_per_hour": 3}, body
    prefs.path.write_text(json.dumps({"nudges_per_hour": 99}))
    assert prefs.read()["nudges_per_hour"] == 10                                      # a hand-edited number is clamped, not dropped
    prefs.write(nudges_per_hour=1)                                                    # the next save replaces what did not read
    assert prefs.read()["nudges_per_hour"] == 1


def test_two_writes_at_once_through_separate_instances_both_land(tmp_path):
    """The route builds a new AttentionPrefs for every request, so a lock of its own guards nothing: two overlapping PUTs (two tabs) must both land."""
    path = tmp_path / "attention.json"
    window = {"start": "21:00", "end": "08:00"}
    for _ in range(25):
        path.unlink(missing_ok=True)
        gate = threading.Barrier(2)

        def put(**change):
            gate.wait()
            AttentionPrefs(path).write(**change)

        threads = [threading.Thread(target=put, kwargs={"quiet_hours": window}), threading.Thread(target=put, kwargs={"nudges_per_hour": 7})]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert AttentionPrefs(path).read() == {"quiet_hours": window, "nudges_per_hour": 7}


def test_a_restart_in_a_new_process_reads_the_same_choices(prefs):
    prefs.write(quiet_hours={"start": "22:30", "end": "06:15"}, nudges_per_hour=0)
    code = ("import json, sys; from sutra_app.ops.attention_prefs import AttentionPrefs; print(json.dumps(AttentionPrefs(sys.argv[1]).read()))")
    out = subprocess.run([sys.executable, "-c", code, str(prefs.path)], capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONPATH": str(REPO)}, cwd=str(prefs.path.parent))
    assert json.loads(out.stdout) == {"quiet_hours": {"start": "22:30", "end": "06:15"}, "nudges_per_hour": 0}


# ---- the routes -------------------------------------------------------------------------------------------------------------------------

def make_client(tmp_path, *, at=datetime(2026, 11, 4, 2, 0)) -> TestClient:
    settings = Settings.load({}, data_dir=tmp_path / "data", token="test-token-0123456789abcdef", env_file=tmp_path / "none.env")
    app = FastAPI()
    app.state.services = Services(settings=settings, version="test", db=None, redact=Redactor(None, environ={}), clock=FakeClock(start=int(at.timestamp()), step=0))
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(attention_api.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


AUTH = {TOKEN: "test-token-0123456789abcdef"}


def error_of(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    return response.json()["error"]


def test_the_answer_has_the_defaults_and_needs_no_token(client):
    assert client.get("/api/ops/attention").json() == {"quiet_hours": None, "nudges_per_hour": 3, "default_nudges_per_hour": 3, "max_nudges_per_hour": 10, "quiet_now": False}


def test_a_write_needs_the_token(client):
    error_of(client.put("/api/ops/attention", json={"nudges_per_hour": 1}), 401, "bad_token")
    error_of(client.put("/api/ops/attention", json={"nudges_per_hour": 1}, headers={TOKEN: "wrong-token-wrong-token"}), 401, "bad_token")
    assert client.get("/api/ops/attention").json()["nudges_per_hour"] == 3


def test_a_question_at_two_in_the_morning_inside_the_window_reads_as_quiet_now(tmp_path):
    inside = make_client(tmp_path, at=datetime(2026, 11, 4, 2, 0))
    assert inside.put("/api/ops/attention", json={"quiet_hours": {"start": "21:00", "end": "08:00"}}, headers=AUTH).json()["quiet_now"] is True
    outside = make_client(tmp_path, at=datetime(2026, 11, 4, 12, 0))                  # the same file, noon
    assert outside.get("/api/ops/attention").json()["quiet_now"] is False and outside.get("/api/ops/attention").json()["quiet_hours"] == {"start": "21:00", "end": "08:00"}


def test_put_sets_each_choice_alone_and_null_clears_the_window(client):
    one = client.put("/api/ops/attention", json={"nudges_per_hour": 0}, headers=AUTH).json()
    assert one["nudges_per_hour"] == 0 and one["quiet_hours"] is None
    two = client.put("/api/ops/attention", json={"quiet_hours": {"start": "21:00", "end": "08:00"}}, headers=AUTH).json()
    assert two["nudges_per_hour"] == 0 and two["quiet_hours"] == {"start": "21:00", "end": "08:00"}
    assert client.put("/api/ops/attention", json={"quiet_hours": None}, headers=AUTH).json()["quiet_hours"] is None
    assert client.put("/api/ops/attention", json={"nudges_per_hour": 50}, headers=AUTH).json()["nudges_per_hour"] == 10        # stopped at the ceiling


@pytest.mark.parametrize("body", [{"quiet_hours": {"start": "10:00", "end": "10:00"}}, {"quiet_hours": {"start": "9:00", "end": "17:00"}},
                                  {"quiet_hours": {"start": "21:00"}}, {"quiet_hours": {"start": "21:00", "end": None}},
                                  {"nudges_per_hour": True}, {"nudges_per_hour": "three"}, {"nudges_per_hour": 2.5}, {"nudges_per_hour": None}, {}, {"other": 1}])
def test_junk_is_a_422_and_changes_nothing(client, body):
    client.put("/api/ops/attention", json={"nudges_per_hour": 2}, headers=AUTH)
    error_of(client.put("/api/ops/attention", json=body, headers=AUTH), 422, "validation")
    assert client.get("/api/ops/attention").json()["nudges_per_hour"] == 2 and client.get("/api/ops/attention").json()["quiet_hours"] is None


def test_the_refusal_of_equal_ends_says_why(client):
    refused = error_of(client.put("/api/ops/attention", json={"quiet_hours": {"start": "10:00", "end": "10:00"}}, headers=AUTH), 422, "validation")
    assert "all day or no time at all" in refused["message"] and refused["details"]["violations"][0]["path"] == "quiet_hours"
