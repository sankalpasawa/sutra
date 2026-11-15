"""The fake backend carries what a turn produced exactly as the real route does (D157): `body.produced` is a list of the library's `OutputItem` and
`body.reply` is the library's `AtomReply`, and for each atom that has them the reply is the text the layer prints for that object and the words
are the words the layer's own `turn_output` gives for it. A fixture that is only written to look right would let the page and the server drift
apart; this one is checked against the code that writes the real thing."""
import json
from pathlib import Path

import pytest
from fake_backend import FakeClient, make_app, run_in_thread

from sutra_app.engine.fnodes.checks import TurnBuffer
from sutra_app.engine.fnodes.output import reply_record, turn_output
from sutra_app.engine.hooks import CallInfo, TurnInfo
from sutra_app.library.atom import REPLY_TEXT_MAX, AtomReply, OutputItem

FIXTURES = Path(__file__).resolve().parent / "fixtures"
IDENTITY = json.loads((FIXTURES / "node-identity.json").read_text(encoding="utf-8"))
BY_ID = {atom["id"]: atom for atom in IDENTITY["atoms"]}
CLOSED, FAILED, OPEN, OLD, REFUSED = ("a-a810960e61-02", "a-a810960e61-03", "a-a810960e61-05", "a-a810960e61-04", "a-a810960e61-01")


def buffer_for(kind, reply, posted=(), saved=()):
    """The turn buffer of an Identity turn as the hooks would have filled it."""
    turn = TurnInfo(run_id="j2-20261104-100004-7f3a", dept_id="web", task_id="t", turn_no=1, function="identity", kind=kind, step=1, step_label="s", cycle=1, task="t", context=[])
    buf = TurnBuffer(turn=turn)
    buf.add_call(CallInfo(call_no=1, function="identity", step=1, purpose="agent_turn", seconds=0.1, inputs=[], reply=reply))
    for message in posted:
        buf.add_message(message)
    for name in saved:
        buf.add_record(name, {})
    return buf


def every_atom(client: FakeClient):
    """Every atom the fake serves: the drawer of each function node of each stage, and the list route."""
    found = {}
    for stage in ("1", "2", "3", "full"):
        client.stage(stage)
        for fn in ("identity", "adaptation", "priority", "coordination", "audit"):
            for dept in ("web", "content"):
                status, detail = client.request("GET", f"/api/graph/nodes/{dept}.{fn}")
                if status == 200:
                    found.update({(stage, a["id"]): a for a in detail["atoms"]})
    return found


@pytest.fixture(scope="module")
def client():
    app = make_app()
    running = run_in_thread(app)
    try:
        yield FakeClient(running.url, app.state.fake.token)
    finally:
        running.stop()


def test_every_atom_the_fake_serves_carries_the_two_keys_only_in_the_librarys_shape(client):
    atoms = every_atom(client)
    assert len(atoms) >= 5
    with_output = 0
    for (stage, atom_id), atom in atoms.items():
        body = atom["body"]
        for item in body.get("produced", []):
            assert set(item) == {"verb", "name", "form", "ref"} and OutputItem.model_validate(item), (stage, atom_id)
        if "reply" in body:
            assert set(body["reply"]) == {"text", "clipped"} and len(body["reply"]["text"]) <= REPLY_TEXT_MAX and AtomReply.model_validate(body["reply"]), (stage, atom_id)
        with_output += bool(body.get("produced"))
    assert with_output >= 3


def test_the_identity_fixture_has_every_case_of_the_card(client):
    assert {k for k in ("produced", "reply") if k in BY_ID[CLOSED]["body"]} == {"produced", "reply"}
    assert {k for k in ("produced", "reply") if k in BY_ID[FAILED]["body"]} == {"produced", "reply"}
    assert {k for k in ("produced", "reply") if k in BY_ID[OPEN]["body"]} == {"produced", "reply"}
    assert not {"produced", "reply"} & set(BY_ID[OLD]["body"])                       # stored before the layer recorded anything: the card says "not recorded"
    assert not {"produced", "reply"} & set(BY_ID[REFUSED]["body"])                   # a refused atom never ran


@pytest.mark.parametrize("atom_id,kind,posted,saved", [
    (CLOSED, "requester_answered", [{"who": "identity", "next": "user"}], []),
    (FAILED, "intake", [{"who": "identity", "next": "adaptation"}], []),
    (OPEN, "intake", [], []),
])
def test_the_fixtures_reply_and_words_are_what_the_layers_own_functions_give_for_that_reply(atom_id, kind, posted, saved):
    body = BY_ID[atom_id]["body"]
    reply = json.loads(body["reply"]["text"])
    buf = buffer_for(kind, reply, posted, saved)
    assert reply_record(buf).model_dump() == body["reply"]                          # the text is the reply object printed the way the layer prints it
    items, _ = turn_output(buf)
    assert [item.model_dump() for item in items] == body["produced"]                # and the words are the ones turn_output says for it


def test_when_the_open_atom_closes_at_stage_3_its_last_try_replaces_the_failed_ones_output_and_the_words_are_the_layers(client):
    client.stage("3")
    closed = next(a for a in client.request("GET", "/api/atoms", )[1] if a["id"] == OPEN)
    assert closed["state"] == "closed"
    body = closed["body"]
    reply = json.loads(body["reply"]["text"])
    assert len(reply["goal"]["done_when"]) == 4 and body["reply"]["clipped"] is False
    buf = buffer_for("intake", reply, [{"who": "identity", "next": "adaptation"}], ["goal.json"])
    assert reply_record(buf).model_dump() == body["reply"] and [i.model_dump() for i in turn_output(buf)[0]] == body["produced"]


def test_the_drawers_route_and_the_list_route_serve_the_same_bodies(client):
    for stage in ("2", "3"):
        client.stage(stage)
        drawer = client.request("GET", "/api/graph/nodes/web.identity")[1]["atoms"]
        listed = client.request("GET", "/api/atoms", )[1]
        served = {a["id"]: a["body"] for a in listed}
        assert drawer and all(served[a["id"]] == a["body"] for a in drawer)
