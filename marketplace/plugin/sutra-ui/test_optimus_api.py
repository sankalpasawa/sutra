"""test_optimus_api -- Optimus is a window: reads honest, mutations gated.

Isolated root via SUTRA_UI_DAEMON_ROOT (never the live ~/.sutra-native).
Desktop token set BEFORE org_api import (module reads it at import time).
No TestClient (venv has no httpx): endpoint functions are called directly
with a stub Request -- same objects FastAPI would call.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="optimus-test-")
os.environ["SUTRA_UI_DAEMON_ROOT"] = TMP
os.environ["SUTRA_DESKTOP_TOKEN"] = "test-token-123"
os.environ.setdefault("SUTRA_NATIVE_HOME", os.path.join(TMP, "user-kit"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import org_api  # noqa: E402  (token bound at import)
importlib.reload(org_api)
import optimus_api  # noqa: E402
importlib.reload(optimus_api)

from fastapi import HTTPException  # noqa: E402


class Req:
    def __init__(self, token=None):
        self.headers = {"x-sutra-desktop-token": token} if token else {}


OK = Req("test-token-123")
NO = Req()


def seed():
    d = os.path.join(TMP, "daemon")
    os.makedirs(os.path.join(d, "outputs"), exist_ok=True)
    os.makedirs(os.path.join(TMP, "ledger"), exist_ok=True)
    os.makedirs(os.path.join(TMP, "outbox"), exist_ok=True)
    json.dump([{"route_id": "r-test1234", "status": "proposed",
                "pattern": "^write ", "workflow": "W-md-authoring@0.1.0",
                "host": "claude-bare", "prompt_template": "x {text}",
                "verify_template_id": "file-exists", "verify_version": "1",
                "verify_args": [], "timeout_s": 300,
                "department": "Finance Ops", "charter": "EMI Reconciliation"}],
              open(os.path.join(d, "routes.json"), "w"))
    json.dump({"in-done1": {"state": "passed", "ts": "x"}},
              open(os.path.join(d, "state.json"), "w"))
    with open(os.path.join(d, "inbox.jsonl"), "w") as fh:
        fh.write(json.dumps({"input_id": "in-done1", "ts": "x", "text": "write a"}) + "\n")
        fh.write(json.dumps({"input_id": "in-pend1", "ts": "x", "text": "write b"}) + "\n")
        fh.write("{torn")  # incomplete tail must not break the snapshot


def http_status(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return 200
    except HTTPException as e:
        return e.status_code


class OptimusApi(unittest.TestCase):

    def test_01_snapshot_honest_empty(self):
        j = optimus_api.optimus_snapshot()
        self.assertIn("present", j)

    def test_02_snapshot_reads_seeded_stores(self):
        seed()
        j = optimus_api.optimus_snapshot()
        self.assertTrue(j["present"])
        self.assertEqual(j["routes"][0]["route_id"], "r-test1234")
        self.assertEqual(j["routes"][0]["department"], "Finance Ops")
        self.assertEqual(j["pending_inputs"], ["in-pend1"])
        self.assertEqual(j["state_summary"], {"passed": 1})
        self.assertFalse(j["daemon"]["running"])

    def test_03_mutations_refuse_without_token(self):
        seed()
        self.assertEqual(http_status(optimus_api.optimus_ask, NO, {"text": "x"}), 403)
        self.assertEqual(http_status(optimus_api.optimus_route_approve, NO,
                                     {"route_id": "r", "operator": "o", "confirm": "r"}), 403)
        self.assertEqual(http_status(optimus_api.optimus_daemon_start, NO), 403)

    def test_04_approve_requires_typed_confirmation(self):
        seed()
        try:
            optimus_api.optimus_route_approve(OK, {"route_id": "r-test1234",
                                                   "operator": "operator-one",
                                                   "confirm": "wrong"})
            self.fail("expected 400")
        except HTTPException as e:
            self.assertEqual(e.status_code, 400)
            self.assertIn("confirmation mismatch", e.detail)

    def test_05_approve_with_confirmation_reaches_the_cli_gate(self):
        seed()
        j = optimus_api.optimus_route_approve(OK, {"route_id": "r-test1234",
                                                   "operator": "operator-one",
                                                   "confirm": "r-test1234"})
        self.assertTrue(j["ok"], j)          # the daemon CLI approved it
        self.assertEqual(j["exit_code"], 0)
        routes = json.load(open(os.path.join(TMP, "daemon", "routes.json")))
        self.assertEqual(routes[0]["status"], "approved")
        self.assertIn("approved_hash", routes[0])

    def test_06_ask_appends_via_cli(self):
        j = optimus_api.optimus_ask(OK, {"text": "write a note on kyc"})
        self.assertIn("queued in-", j["out"])

    def test_07_stop_honest_when_not_running(self):
        j = optimus_api.optimus_daemon_stop(OK, {"pid_confirm": 99999})
        self.assertIn("not running", j["out"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
