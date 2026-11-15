"""What a turn produced, across sections (D157): the engine's recorded run, replayed through the real projector and store, reaches the page's
two doors for atoms (the drawer's `GET /api/graph/nodes/{id}` and `GET /api/atoms`) with the words and the reply every atom of the run
recorded, in the one shape the page reads: `body.produced` is a list of `{verb, name, form, ref}` and `body.reply` is `{text, clipped}` or null."""
import json

from sutra_app.library.atom import REPLY_TEXT_MAX
from sutra_app.library.types import FUNCTIONS, function_node_id

from .test_contract_fnodes import replayed  # noqa: F401  (a fixture)
from .test_contract_world import World, clock, db, events, ids, settings, tenv, world  # noqa: F401  (fixtures used by name)

ITEM = {"verb", "name", "form", "ref"}


def atoms_of(world: World, fn: str) -> list[dict]:
    node = function_node_id("web", fn)
    detail = world.client.get(f"/api/graph/nodes/{node}").json()["atoms"]
    listed = world.client.get("/api/atoms", params={"node_id": node, "limit": 100}).json()
    assert {a["id"]: a["body"] for a in listed} == {a["id"]: a["body"] for a in detail}, fn          # the two doors serve the same bodies
    return detail


def test_every_atom_of_the_recorded_run_reaches_the_page_with_its_words_and_its_reply(replayed):
    world, _ = replayed
    seen = 0
    for fn in FUNCTIONS:
        for atom in atoms_of(world, fn):
            body, seen = atom["body"], seen + 1
            assert body["produced"] and all(set(item) == ITEM and item["verb"] in ("make", "do") and item["name"] and item["ref"] for item in body["produced"]), atom["id"]
            assert body["reply"] is None or (set(body["reply"]) == {"text", "clipped"} and len(body["reply"]["text"]) <= REPLY_TEXT_MAX), atom["id"]
            assert (body["reply"] is not None) == (body["work"]["dispatch_kind"] == "llm"), atom["id"]      # an AI call gave a reply; code and the owner gave none
    assert seen == 31                                                                                  # the 31 function atoms of the recorded run


def test_a_reply_that_reached_the_page_is_the_object_the_model_sent_and_says_when_it_was_cut(replayed):
    world, _ = replayed
    audit = [a for a in atoms_of(world, "audit") if a["body"]["reply"] is not None][0]["body"]
    reply = audit["reply"]
    assert reply["clipped"] is False and json.loads(reply["text"])["findings"], "the Audit report's findings are in the reply"
    proposals = [a["body"]["reply"] for a in atoms_of(world, "adaptation") if a["body"]["reply"] is not None]
    cut = [r for r in proposals if r["clipped"]]
    assert cut and all(len(r["text"]) == REPLY_TEXT_MAX and r["text"].endswith("…") for r in cut)      # the long proposals of the mock run are cut, and say so
    assert all(r["text"].startswith("{") for r in proposals)


def test_the_words_of_the_recorded_run_say_what_each_function_made(replayed):
    world, _ = replayed
    said = {fn: [item["name"] for atom in atoms_of(world, fn) for item in atom["body"]["produced"]] for fn in FUNCTIONS}
    assert "the charter: Brew Lab, 7 done-when items" in said["identity"] and any(n.startswith("asked you 3 questions:") for n in said["identity"])
    assert any(n.startswith("you answered:") for n in said["identity"])                                # the manual atom of the question
    assert any(n.startswith("a proposal of") for n in said["adaptation"]) and any(n.startswith(("GRANT", "COUNTER")) for n in said["priority"])
    assert any(n.startswith("scheduled 3 workflows in this order: W-1, W-2, W-3") for n in said["coordination"])
    assert any(n.startswith("code posted 1 message: Queue empty") for n in said["coordination"])      # a turn that was only a hand-off by code
    assert any("findings and rubric rows:" in n for n in said["audit"]) and any(n.startswith("finding F-7: needs revision") for n in said["audit"])
    assert all(any(n.startswith("posted ") for n in names) for names in said.values())                  # every function posted a message in the run
