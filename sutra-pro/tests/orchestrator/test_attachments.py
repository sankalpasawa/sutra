"""The orchestrator's attachment service (work package ABS-4)."""
import pytest

from sutra_app.connectors.errors import InvalidRequestError
from sutra_app.orchestrator.attachments import Attachments


def test_upload_returns_a_reference_and_get_finds_the_file(tmp_path):
    a = Attachments(tmp_path)
    ref = a.upload("note.txt", b"hello")
    assert ref.kind == "text" and a.get(ref.id).read_bytes() == b"hello"


def test_ten_files_a_message_at_most(tmp_path):
    a = Attachments(tmp_path)
    assert len(a.upload_many([(f"{i}.txt", b"x%d" % i) for i in range(10)])) == 10
    with pytest.raises(InvalidRequestError):
        a.upload_many([(f"{i}.txt", b"y%d" % i) for i in range(11)])


def test_a_refused_file_is_a_sentence(tmp_path):
    with pytest.raises(InvalidRequestError, match="images, PDFs and text"):
        Attachments(tmp_path).upload("a.exe", b"MZ")
