"""Live checks of the transport schemas against the REAL claude and codex CLIs (library design 3.5, 14 and 17, risk 2;
S2-models-04; work package L8).

They run only with SUTRA_LIVE=1 (`tests/conftest.py` skips `live`, and the default gate never calls a model):

    SUTRA_LIVE=1 scripts/py -m pytest tests/library/test_lib_live_transport.py -q

A CLI that is not installed or not signed in with a subscription login skips its tests. What they settle:

    test_a_corrected_schema_is_accepted_and_the_reply_parses
        `claude -p --json-schema` (and Codex's strict form) takes `transport_schema("priority", kind="price")`, where a
        one-value `Literal` is an `enum` (J2 dropped `const`), and `ReplyParser` reads the reply. [U] until run.
    test_chart_change_request_native
        5 trials per CLI through `call_json` with `transport_schema(ChartChangeRequest)` (ops as `anyOf` of five closed
        objects), a six-node chart and the request "merge Leads into Quotes and add a Support team". It passes when
        `how == "native"` and the reply validates in at least 4 of 5 trials. A failure settles union against flat (risk 2):
        set `CHART_OPS_TRANSPORT = "flat"` in org_chart.py and add `ChartOpFlat`.
"""
from __future__ import annotations

import json
import shutil

import pytest
from factories_org import six_node_chart

from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.codex import CodexConnector
from sutra_app.connectors.errors import ConnectorError
from sutra_app.connectors.models import ConnectorConfig
import sutra_app.library.all  # noqa: F401  (registers every family: run alone, the file would see only three)
from sutra_app.library.org_chart import ChartChangeRequest
from sutra_app.library.registry import REGISTRY, transport_schema
from sutra_app.library.replies import ReplyInvalid, ReplyParser

pytestmark = pytest.mark.live

CALL_TIMEOUT_S = 240.0
TRIALS, NEEDED = 5, 4


@pytest.fixture(scope="module", params=["claude", "codex"])
def live(request, tmp_path_factory):
    name = request.param
    if shutil.which(name) is None:
        pytest.skip(f"{name} is not installed")
    root = tmp_path_factory.mktemp(f"live-{name}")
    cfg = ConnectorConfig(data_dir=root / "data", work_root=root / "work")
    connector = ClaudeConnector(cfg) if name == "claude" else CodexConnector(cfg)
    try:
        auth = connector.probe_auth()
    except ConnectorError as err:
        pytest.skip(f"{name} status could not be read: {err.user_message()}")
    if auth.signed_in is not True or auth.billing == "api_key":
        pytest.skip(f"{name} is not signed in with a subscription login")
    yield connector
    connector.runner.stop_all()


def test_a_corrected_schema_is_accepted_and_the_reply_parses(live):
    schema = REGISTRY.transport_schema("priority", kind="price")
    prompt = ("You are Priority. Price this proposal for a one-page website for a small cafe: one workflow named 'Build the page' "
              "that covers done-when item 1, with one step ('Write the page') and one output ('index.html'). GRANT it with an envelope "
              "of money_limit 15, model_call_limit 2, time_limit_minutes 10 and retry_limit 1, and send it on to Adaptation. "
              "Reply with the JSON object only.")
    result = live.call_json_result(prompt, schema=schema, timeout=CALL_TIMEOUT_S, effort="low")
    assert result.how == "native"
    parsed = ReplyParser().parse("priority", json.dumps(result.value), kind="price")
    assert parsed.model.kind == "price" and parsed.model.decision in ("GRANT", "COUNTER", "REFUSE")


def chart_prompt() -> str:
    chart = six_node_chart()
    nodes = [{"id": n.id, "kind": n.kind, "name": n.name} for n in chart.nodes]
    return ("You change an organisation chart. Existing nodes: " + json.dumps(nodes) + ". Request: merge Leads into Quotes and add "
            "a Support team. Reply with one JSON object: reason, reuses and ops. Use a $ref such as $support for a node you add.")


def test_chart_change_request_native(live):
    schema = transport_schema(ChartChangeRequest)
    prompt, parser, native, valid = chart_prompt(), ReplyParser(), 0, 0
    for _ in range(TRIALS):
        result = live.call_json_result(prompt, schema=schema, timeout=CALL_TIMEOUT_S, effort="low")
        native += result.how == "native"
        try:
            parser.parse("chart_change_request", json.dumps(result.value))
            valid += 1
        except ReplyInvalid:
            pass
    assert native >= NEEDED and valid >= NEEDED, (
        f"{live.name}: native {native}/{TRIALS}, valid {valid}/{TRIALS}: the union form is not safe, switch CHART_OPS_TRANSPORT to flat")
