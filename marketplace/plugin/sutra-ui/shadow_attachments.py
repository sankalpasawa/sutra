"""Files the founder gives Shadow: images, PDFs and text files (founder,
2026-10-08: "we should be able to add a photo to the question/task ... so
Shadow can understand it, and decide whether to pass it on to the worker
chat"; then "add pdfs and text files too ... we want similar functionality").

WHAT THIS IS. A small store for files attached in Shadow's own boxes -- the
Now box, + Delegate, a task's chat, an answer to Shadow's question. Each file
is saved once under the shadow home and named by an id, and Shadow gets the
CONTENT, not a file name:

  image  shown as an image block      (session_runtime.send_user_frame)
  pdf    sent as a PDF document block (measured 2026-10-08: the Claude Code
         CLI reads a base64 PDF document block in stream-json input with no
         tool call)
  text   its text put in the message, cut at INLINE_CHARS with the cut said

A task keeps the list of its files (`attachments` on the mission), so the
brief writer and the decider can decide whether the worker needs one -- and
pass it on by its path, which the worker opens with its Read tool (Read
handles images, PDFs and text alike).

WHY NOT the Chats screen's /api/org/attach. That writes into the configured
WORKDIR -- the founder's repository on this machine. A file the founder shows
Shadow is not part of the project and must not land in it.

CHECKED BY CONTENT, NOT BY NAME. An image or a PDF is recognised by its own
signature; a text file must have an allowed extension AND decode as UTF-8
with no NUL byte. Anything else is refused. `.env` and other secret-bearing
names are not on the list on purpose.
"""
import base64
import binascii
import os
import re
import time
import uuid

import shadow_ledger

#: Per file. Images and PDFs ride as base64 in one message; text is smaller
#: by nature and only its first INLINE_CHARS go in the message anyway.
MAX_BYTES = 10 * 1024 * 1024
TEXT_MAX_BYTES = 1024 * 1024
#: How much of one text file goes into the message. The worker can Read the
#: whole file at its path; Shadow is told when it got only the start.
INLINE_CHARS = 40000
#: Files per message, and per task in total -- past this the founder is told
#: why, never silently cut.
MAX_PER_MESSAGE = 6
MAX_PER_TASK = 30

_ID_RE = re.compile(r"^(img|att)-[0-9a-f]{16}$")

_BINARY_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
               "image/webp": ".webp", "application/pdf": ".pdf"}
#: Text files by extension -> media type. Code and data Shadow can read as
#: words; nothing that usually carries secrets (.env, .pem, .key).
TEXT_EXT = {
    ".txt": "text/plain", ".md": "text/markdown", ".markdown": "text/markdown",
    ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".json": "application/json", ".log": "text/plain",
    ".yaml": "text/yaml", ".yml": "text/yaml", ".toml": "text/plain",
    ".ini": "text/plain", ".xml": "application/xml",
    ".html": "text/html", ".htm": "text/html", ".css": "text/css",
    ".js": "text/javascript", ".jsx": "text/javascript",
    ".ts": "text/plain", ".tsx": "text/plain", ".py": "text/x-python",
    ".sql": "text/plain", ".sh": "text/plain", ".rb": "text/plain",
    ".go": "text/plain", ".java": "text/plain", ".rs": "text/plain",
}
ALL_EXT = list(_BINARY_EXT.values()) + list(TEXT_EXT)


class Refused(ValueError):
    """Said no, in a sentence the founder can read."""


def media_type_of(blob):
    """An image's or a PDF's type from its bytes, or None."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    if blob[:5] == b"%PDF-":
        return "application/pdf"
    return None


def kind_of(media_type):
    """image | pdf | text"""
    if str(media_type or "").startswith("image/"):
        return "image"
    if media_type == "application/pdf":
        return "pdf"
    return "text"


def _dir():
    d = os.path.join(os.path.realpath(shadow_ledger.shadow_home()),
                     "attachments")
    os.makedirs(d, exist_ok=True)
    return d


def _clean_name(name):
    safe = os.path.basename(str(name or "")).strip()
    safe = re.sub(r"[^A-Za-z0-9 ._()-]", "_", safe)[:80]
    return safe or "file"


def path_of(aid):
    """The file's absolute path, or None for an unknown or malformed id."""
    if not _ID_RE.match(str(aid or "")):
        return None
    d = _dir()
    for ext in ALL_EXT:
        p = os.path.join(d, aid + ext)
        if os.path.exists(p):
            return p
    return None


def _media_of_path(path):
    ext = os.path.splitext(path)[1].lower()
    for media, e in _BINARY_EXT.items():
        if e == ext:
            return media
    return TEXT_EXT.get(ext)


def _as_text(blob):
    """The text of an allowed text file, or None when it is not text."""
    if b"\x00" in blob:
        return None
    try:
        return blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def save(name, content_b64):
    """Store one file. Returns {id, name, path, media_type, kind, bytes}."""
    try:
        blob = base64.b64decode(content_b64 or "", validate=True)
    except (ValueError, binascii.Error):
        raise Refused("that file could not be read")
    if not blob:
        raise Refused("that file is empty")
    clean = _clean_name(name)
    media = media_type_of(blob)
    if media is not None:
        if len(blob) > MAX_BYTES:
            raise Refused("files can be up to %d MB" % (MAX_BYTES // 1048576))
        aid = ("img-" if kind_of(media) == "image" else "att-") \
            + uuid.uuid4().hex[:16]
        ext = _BINARY_EXT[media]
    else:
        ext = os.path.splitext(clean)[1].lower()
        if ext not in TEXT_EXT or _as_text(blob) is None:
            raise Refused("only images, PDFs and text files can be attached")
        if len(blob) > TEXT_MAX_BYTES:
            raise Refused("text files can be up to %d MB"
                          % (TEXT_MAX_BYTES // 1048576))
        media = TEXT_EXT[ext]
        aid = "att-" + uuid.uuid4().hex[:16]
    path = os.path.join(_dir(), aid + ext)
    with open(path, "wb") as fh:
        fh.write(blob)
    return {"id": aid, "name": clean, "path": path, "media_type": media,
            "kind": kind_of(media), "bytes": len(blob)}


def read(aid):
    """(media_type, bytes) for a stored file, or None."""
    p = path_of(aid)
    if p is None:
        return None
    with open(p, "rb") as fh:
        blob = fh.read()
    return _media_of_path(p), blob


def blocks(ids):
    """[(media_type, base64 text)] for the images and PDFs among `ids`, in
    order: what session_runtime.send_user_frame puts in front of the text
    (an image block or a document block). Text files are not here -- their
    words go in the message (note). Unknown ids are skipped: a file that
    cannot be found must not cost the message."""
    out = []
    for aid in ids or []:
        got = read(aid)
        if got and got[0] and kind_of(got[0]) in ("image", "pdf"):
            out.append((got[0], base64.b64encode(got[1]).decode("ascii")))
    return out


def valid_ids(ids):
    """The ids that name a stored file, de-duplicated, in order. Raises
    Refused past MAX_PER_MESSAGE."""
    seen = []
    for aid in ids or []:
        if path_of(aid) and aid not in seen:
            seen.append(aid)
    if len(seen) > MAX_PER_MESSAGE:
        raise Refused("up to %d files per message" % MAX_PER_MESSAGE)
    return seen


def link(mission, ids, source, names=None, shown=False):
    """Add files to a mission record (in memory; the caller saves). Returns
    the rows added. `source` is where they came from: intake | talk | answer.
    `shown` says whether THIS task's Shadow chat has already seen them: a
    file said in the task's own chat has; one from the Now box or an answer
    form has not, and is shown with the next brief or decision."""
    have = mission.setdefault("attachments", [])
    known = {a.get("id") for a in have}
    added = []
    for aid in ids or []:
        if aid in known:
            continue
        if len(have) >= MAX_PER_TASK:
            raise Refused("a task can hold up to %d files" % MAX_PER_TASK)
        path = path_of(aid)
        row = {"id": aid, "path": path,
               "name": (names or {}).get(aid) or aid,
               "kind": kind_of(_media_of_path(path or "")),
               "source": source,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "shown": bool(shown)}
        have.append(row)
        added.append(row)
    return added


def _text_part(aid, name):
    got = read(aid)
    if not got or kind_of(got[0]) != "text":
        return ""
    text = _as_text(got[1]) or ""
    cut = len(text) > INLINE_CHARS
    return ("--- %s (text file%s) ---\n%s\n--- end of %s ---\n"
            % (name, ", only the first %d characters; the whole file is at "
               "its path" % INLINE_CHARS if cut else "",
               text[:INLINE_CHARS], name))


def note(ids, names=None):
    """What goes with files Shadow is given: what each is and where it
    lives -- so it can pass a path on if the worker needs one -- and the
    words of every text file."""
    if not ids:
        return ""
    names = names or {}
    rows, texts = [], []
    for aid in ids:
        path = path_of(aid)
        kind = kind_of(_media_of_path(path or ""))
        name = names.get(aid) or aid
        rows.append("- %s (%s) at %s" % (name, kind, path))
        if kind == "text":
            texts.append(_text_part(aid, name))
    n = len(ids)
    return ("[The founder attached %d file%s: images and PDFs are shown above, "
            "text files are below. Look at %s. If the work needs one, the "
            "worker can open it at its path with its Read tool -- pass a path "
            "on only when the work needs it.]\n%s\n%s\n"
            % (n, "" if n == 1 else "s", "it" if n == 1 else "them",
               "\n".join(rows), "".join(texts)))
