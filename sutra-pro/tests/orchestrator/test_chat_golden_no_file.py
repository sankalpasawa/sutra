"""D440 NFR-2 and FR-12: a chat with no file is byte-for-byte what it was, and a file's text is never written anywhere but the attachment store."""
from __future__ import annotations

import json

from orchestrator.test_api_chat_v2 import H, _upload, _spy_on_model_input, rig, wait_for, world  # noqa: F401

from sutra_app.connectors.transcript import render_carry_over
from sutra_app.orchestrator.api import chat_v2


def test_a_chat_with_no_file_stores_the_same_line_sends_the_same_prompt_and_answers_the_same_body(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    seen = _spy_on_model_input(services)
    r = client.post(f"/api/chats/{sid}/direct", json={"text": "hello there"}, headers=H)
    assert r.status_code == 202 and set(r.json()) == {"message_id", "turn"}             # no `files` key, as before
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and not chat_v2.direct_running.answering(sid))
    user = chats.messages(sid)[0]
    assert user.text == "hello there" and user.attachments == []
    assert seen[0].text == "hello there" and seen[0].images == []
    row = services.db.conn().execute("SELECT meta_json FROM chat_messages WHERE id = ?", (user.id,)).fetchone()
    assert "attachments" not in json.loads(row["meta_json"])
    assert "attachments" not in client.get(f"/api/chats/{sid}/messages", headers=H).json()["messages"][0]


def test_a_carry_over_of_a_chat_with_no_file_is_unchanged_by_the_store(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    client.post(f"/api/chats/{sid}/direct", json={"text": "one"}, headers=H)
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and not chat_v2.direct_running.answering(sid))
    with_store = services.chat_port.router.transcripts.messages(sid)
    from sutra_app.orchestrator.chats import ChatTranscripts
    without = ChatTranscripts(chats).messages(sid)
    assert [(m.role, m.text) for m in with_store] == [(m.role, m.text) for m in without]
    assert render_carry_over(with_store) == render_carry_over(without)


def test_a_files_text_is_written_only_under_the_attachment_store_never_to_logs_the_chat_store_or_the_work_folder(rig, settings, tmp_path):
    """FR-12: the egress audit row holds sizes only, the usage and call logs hold no prompt, the chat line holds the name; only `<data>/attachments/<sha>` holds the bytes."""
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    secret = b"ZEBRA-QUOKKA-7731 is the content of this file"
    ref = _upload(client, sid, "notes.txt", secret)
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "read", "attachments": [ref], "names": ["notes.txt"]}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and not chat_v2.direct_running.answering(sid))
    stored = services.attachments.store.path_of(ref)
    assert stored is not None and stored.parent.name == "attachments"
    leaks = []
    for root in {settings.data_dir, tmp_path / "work"}:
        for p in root.rglob("*"):
            if p.is_file() and p != stored and b"ZEBRA-QUOKKA-7731" in p.read_bytes():
                leaks.append(str(p))
    assert leaks == [], leaks
    assert "ZEBRA" not in "".join(m.text for m in chats.messages(sid) if m.role == "user")
