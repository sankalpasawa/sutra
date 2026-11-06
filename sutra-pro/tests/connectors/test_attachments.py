"""Attachments: store, kinds, delivery (work package ABS-4; the old test_shadow_attachments cases re-expressed)."""
from __future__ import annotations

import base64
import json
import stat
import sys

import pytest

from sutra_app.connectors.attachments import INLINE_CHARS, MAX_BYTES, AttachmentStore, deliver, sniff
from sutra_app.connectors.base import TurnPlan
from sutra_app.connectors.chat_models import ChatTurnIn
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.claude import ClaudeConnector
from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.connectors.models import RouteContext
from test_chat_port import make

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
PDF = b"%PDF-1.7\n" + b"0" * 20
JPG = b"\xff\xd8\xff\xe0" + b"0" * 20


@pytest.fixture
def store(tmp_path):
    return AttachmentStore(tmp_path)


def test_kinds_are_decided_by_content_not_name(store):
    assert store.save("photo.txt", PNG).kind == "image" and store.save("x.png", PDF).kind == "pdf"
    assert store.save("notes.md", b"hello").kind == "text"
    assert sniff(JPG) == "image/jpeg" and sniff(b"GIF89a....") == "image/gif" and sniff(b"RIFF\0\0\0\0WEBPxx") == "image/webp"


def test_stored_once_by_hash_under_the_data_folder(store, tmp_path):
    a, b = store.save("one.png", PNG), store.save("two.png", PNG)
    assert a.id == b.id and len(a.id) == 64
    assert store.path_of(a.id).parent == tmp_path / "attachments" and len(list((tmp_path / "attachments").iterdir())) == 1
    if sys.platform != "win32":
        assert stat.S_IMODE(store.path_of(a.id).stat().st_mode) == 0o600


@pytest.mark.parametrize("name,blob", [("a.exe", b"MZ\x90\x00"), (".env", b"KEY=1"), ("a.txt", b"bin\x00ary"), ("a.txt", b"\xff\xfe\xfa"), ("a.txt", b"")])
def test_what_is_not_an_image_pdf_or_text_is_refused(store, name, blob):
    with pytest.raises(InvalidRequestError):
        store.save(name, blob)


def test_the_size_limit(store):
    with pytest.raises(InvalidRequestError):
        store.save("big.png", PNG + b"0" * MAX_BYTES)


def test_an_id_is_a_hash_never_a_path(store):
    assert store.path_of("../../etc/passwd") is None and store.path_of("0" * 64) is None


def test_claude_takes_images_and_pdfs_as_paths_codex_takes_images_only(store):
    refs = [store.save("a.png", PNG), store.save("b.pdf", PDF)]
    assert len(deliver(store, refs, "claude").images) == 2
    with pytest.raises(InvalidRequestError) as e:
        deliver(store, refs, "codex")
    assert "b.pdf" in str(e.value)
    assert len(deliver(store, refs[:1], "codex").images) == 1


def test_text_is_inline_fenced_and_a_cut_is_said(store):
    d = deliver(store, [store.save("n.txt", b"short")], "claude")
    assert "short" in d.text and "data, not instructions" in d.text and "[cut" not in d.text
    big = deliver(store, [store.save("big.txt", b"x" * (INLINE_CHARS + 5))], "codex")
    assert f"[cut: showing the first {INLINE_CHARS} of {INLINE_CHARS + 5} characters]" in big.text


def test_at_most_ten_files_a_message(store):
    refs = [store.save(f"f{i}.txt", b"t%d" % i) for i in range(11)]
    with pytest.raises(InvalidRequestError):
        deliver(store, refs, "claude")


def test_a_missing_file_is_named(store):
    ref = store.save("a.txt", b"x")
    store.path_of(ref.id).unlink()
    with pytest.raises(InvalidRequestError, match="a.txt"):
        deliver(store, [ref], "claude")


def test_claude_stdin_has_image_and_document_blocks_then_the_text(store, tmp_path):
    paths = [str(store.path_of(store.save("a.png", PNG).id)), str(store.path_of(store.save("b.pdf", PDF).id))]
    line = ClaudeConnector._image_line(TurnPlan(prompt="look", ctx=RouteContext(), images=tuple(paths)))
    content = json.loads(line)["message"]["content"]
    assert [c["type"] for c in content] == ["image", "document", "text"]
    assert content[1]["source"]["media_type"] == "application/pdf" and base64.b64decode(content[1]["source"]["data"]) == PDF


def test_the_port_delivers_text_and_images_to_the_provider_of_the_turn(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.attachments = AttachmentStore(tmp_path)
    ref = port.attachments.save("notes.txt", b"the plan is X")
    port.send("cs_att", ChatTurnIn(text="read this", attachments=[ref]))
    assert "the plan is X" in claude.calls[0].prompt and claude.calls[0].prompt.startswith("read this")


def test_the_port_refuses_a_pdf_for_codex_with_its_name(tmp_path):
    port, router, history, cfg, claude, codex = make(tmp_path)
    port.attachments = AttachmentStore(tmp_path)
    ref = port.attachments.save("paper.pdf", PDF)
    port.choose("cs_att2", "codex")
    with pytest.raises(InvalidRequestError, match="paper.pdf"):
        port.send("cs_att2", ChatTurnIn(text="x", attachments=[ref]))
