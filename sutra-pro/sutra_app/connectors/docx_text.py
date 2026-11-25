"""The text of a Word file (.docx), for an attachment (D440).

Read with python-docx, which is already a dependency of the app: paragraphs in order, a table as tab-separated rows, nothing executed (a .docx holds no macros; a .docm is not
taken) and no external entity is loaded (python-docx's parser does not resolve them). The file is bounded by the 20 MB upload limit; what a zip could expand to is bounded
here too, and the text kept is bounded (the caller cuts it at the 40,000 characters the model reads). Any failure is ONE sentence naming the file, never a stack or a 500.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import BinaryIO

from .errors import InvalidRequestError

__all__ = ["extract", "MAX_EXPANDED", "MAX_CHARS"]

MAX_EXPANDED = 200 * 1024 * 1024          # a .docx that would expand to more than this is a zip bomb, not a document
MAX_CHARS = 1_000_000                      # more text than this is never held; the model is given the first 40,000 of it


def extract(path: "str | Path | BinaryIO", name: str = "the file") -> str:
    """The paragraphs and tables of the .docx at `path` (or in that open binary stream), in order. Raises InvalidRequestError("<name> could not be read as a Word file") for anything that is not one."""
    sentence = f"{name} could not be read as a Word file"
    try:
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_EXPANDED:
                raise InvalidRequestError(sentence)
        import docx                                              # python-docx; imported here so a chat that never carries a Word file never loads it
        from docx.table import Table
        document = docx.Document(path if hasattr(path, "read") else str(path))
        out: list[str] = []
        size = 0
        for block in document.iter_inner_content():
            if isinstance(block, Table):
                lines = ["\t".join(cell.text for cell in row.cells) for row in block.rows]
                piece = "\n".join(lines)
            else:
                piece = block.text
            out.append(piece)
            size += len(piece) + 1
            if size >= MAX_CHARS:
                break
        return "\n".join(out)[:MAX_CHARS]
    except InvalidRequestError:
        raise
    except Exception as exc:                                     # noqa: BLE001  (a bad zip, a missing part, a bad XML: all one sentence)
        raise InvalidRequestError(sentence) from exc
