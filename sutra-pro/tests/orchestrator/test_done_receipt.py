"""The receipt on a done card (GAP-model-quality): what a finished task cost and took, evidence only, written once by the Projector when the
task ends. `TEnv` (test_tasks) runs the real Projector over a fake launcher; usage arrives as run events, atoms are rows written by hand."""
import json

from orchestrator.test_tasks import TEnv, ev, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.orchestrator.models import ChatMessageOut, DoneCard, DoneReceipt


def usage(n: int, provider: str, usd, tokens_in, tokens_out):
    return ev("usage", fn="priority", step="J2.c", atom=None, provider=provider, model="m", purpose="agent_turn", usd=usd, tokens_in=tokens_in,
              tokens_out=tokens_out, seconds=1.0, ok=True, how="text", call_ref=f"r:{n}")


def atom(t: TEnv, task_id: str, n: int, display: str) -> None:
    t.sql("INSERT INTO atoms(id, schema, node_id, task_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?, 'atom/1', 'web.identity', ?, ?, ?, 1, 'g', '{}', 'x', ?)",
          f"run:W-{n}.a1", task_id, display, display, 5000 + n)


def done_cards(t: TEnv) -> list:
    return [m for m in t.chats.messages("cs_org") if m.card is not None and m.card.type == "done"]


def finish(t: TEnv, task_id: str, *events, status="done", outcome="Done: the page is up."):
    t.write_events(task_id, *events, ev("run.ended", status=status, outcome=outcome, at="2026-11-04T10:07:00Z"))
    t.drain(task_id)
    return done_cards(t)[-1].card


def test_the_done_card_carries_cost_tokens_time_and_the_atoms_by_final_state(tenv):
    task = tenv.started()
    for n, display in enumerate(["closed", "closed", "verify_failed"], 1):
        atom(tenv, task, n, display)
    card = finish(tenv, task, usage(1, "claude", 0.31, 1000, 200), usage(2, "claude", 0.11, 500, 100), usage(3, "stub", 9.0, 1, 1))
    row = tenv.row(task)
    assert card.receipt == DoneReceipt(usd=0.42, tokens=1800, seconds=row.ended_at - row.started_at, checks_passed=2, checks_total=3)
    assert card.receipt.seconds > 0                                                           # the stub row is left out of the sums


def test_a_codex_only_task_has_tokens_and_no_dollars(tenv):
    task = tenv.started()
    card = finish(tenv, task, usage(1, "codex", None, 4000, 900))
    assert (card.receipt.usd, card.receipt.tokens) == (None, 4900)


def test_a_task_with_no_atoms_claims_no_check(tenv):
    task = tenv.started()
    card = finish(tenv, task, status="done_with_open_items", outcome="Done with open items: x")
    assert (card.receipt.checks_passed, card.receipt.checks_total, card.receipt.usd, card.receipt.tokens) == (0, 0, None, None)


def test_replaying_the_drain_changes_nothing(tenv):
    task = tenv.started()
    atom(tenv, task, 1, "closed")
    first = finish(tenv, task, usage(1, "claude", 0.2, 10, 10))
    tenv.sql("UPDATE tasks SET events_offset = 0 WHERE id = ?", task)
    tenv.drain(task)
    assert len(done_cards(tenv)) == 1 and done_cards(tenv)[0].card == first


def test_a_retry_card_names_its_attempt(tenv):
    first = tenv.started()
    tenv.projector.mark_ended(first, "crashed", "boom")
    assert done_cards(tenv)[-1].card.receipt.attempt is None
    second = tenv.run(tenv.service.retry(first)).id
    tenv.projector.mark_ended(second, "crashed", "boom again")
    assert done_cards(tenv)[-1].card.receipt.attempt == 2


def test_a_card_stored_before_the_receipt_existed_keeps_its_wire_shape():
    old = {"type": "done", "task_id": "tsk_b7c8d9e0f1a2", "dept_name": "Content", "title": "Menu page copy", "status": "done", "outcome": "Done."}
    assert DoneCard.model_validate(old).model_dump(mode="json") == old
    message = {"id": 17, "session_id": "cs_org", "role": "agent", "who": "sutra", "kind": "card", "text": "", "card": old, "pause": None,
               "answered_by": None, "task_id": None, "state": "ok", "at": "2026-11-04T10:00:00Z"}
    assert ChatMessageOut.model_validate(message).model_dump(mode="json") == message
    with_receipt = {**old, "receipt": {"usd": 0.42, "tokens": None, "seconds": 360, "checks_passed": 7, "checks_total": 8, "attempt": None}}
    assert json.loads(DoneCard.model_validate(with_receipt).model_dump_json()) == with_receipt
