"""Page boot: what a page is told when it loads, and the Content-Security-Policy that goes with it.

Three small pure pieces live here, all used by `routes.py`:

* `render_page` is the ONE boot injector. It replaces the marker `<!--SUTRA-BOOT-->` of a page file with a JSON block
  (the per-launch token, the department, the version). The token reaches a page only this way and is sent back only in
  the `X-Sutra-Token` header; no cookie exists anywhere (D81).
* `inline_script_hashes` and `csp_header` build the `script-src` allow-list from the page's own inline scripts, so the
  policy needs no `'unsafe-inline'` for scripts (D82, S3-web-09).
* `DeptLike` is the row shape the UI reads from `Services.department`; the UI never imports the orchestrator (D72).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Literal, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

BOOT_MARKER = "<!--SUTRA-BOOT-->"
BOOT_BLOCK_ID = "sutra-boot"
TOKEN_MIN_LENGTH = 16  # Settings.token has the same minimum, also when it comes from SUTRA_TOKEN

URL_ID_PATTERN = r"[A-Za-z0-9_.:-]{1,120}"
URL_ID_RE = re.compile(URL_ID_PATTERN)


def is_url_id(value: object) -> bool:
    """The generic URL-id rule for `/d/{dept}/` (S3-web-13). The UI treats ids as opaque; the strict department rule
    stays with the engine and the orchestrator. `fullmatch`, never `$`: `$` also accepts a trailing newline.
    `.` and `..` pass the character set but are path segments, never a team, so they are refused here."""
    return isinstance(value, str) and value not in (".", "..") and URL_ID_RE.fullmatch(value) is not None


class DeptLike(Protocol):
    """The row of `Services.department(dept_id)`. Only `id` and `name` are required; a row that also carries
    `archived` and `merged_into_name` (none does in v1: a department is never archived) gets the banner (UI-D10)."""

    id: str
    name: str


class BootMarkerError(ValueError):
    """The page file does not hold the boot marker exactly once."""


class BootContext(BaseModel):
    """What `render_page` writes into the boot block. Closed and checked: a bad token or id fails loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    page: Literal["home", "dept", "console"]
    token: str = Field(min_length=TOKEN_MIN_LENGTH)
    dept: str = ""
    dept_label: str = ""  # the department's name (row.name); the Simple view's title
    archived: bool = False
    note: str = ""  # the archived banner text, empty otherwise
    version: str

    @model_validator(mode="after")
    def _check_page(self) -> "BootContext":
        if self.page in ("home", "console"):
            if self.dept:
                raise ValueError(f"the {self.page} page belongs to no department: dept must be empty")
        else:
            if not is_url_id(self.dept):
                raise ValueError(f"a department page needs a dept matching {URL_ID_PATTERN}")
            if not self.dept_label:
                raise ValueError("a department page needs a dept_label")
        return self


def archived_note(merged_into_name: str) -> str:
    """The banner of a merged (archived) team's page. No v1 row is archived; the text is the contract of S3-web-02."""
    target = merged_into_name.strip() or "another team"
    return f"This team was merged into {target}. Its history stays available."


def dept_boot(row: DeptLike, *, token: str, version: str) -> BootContext:
    """The boot context of a department page, from the row `Services.department` returned."""
    archived = bool(getattr(row, "archived", False))
    merged_into = str(getattr(row, "merged_into_name", "") or "")
    return BootContext(
        page="dept",
        token=token,
        dept=row.id,
        dept_label=row.name,
        archived=archived,
        note=archived_note(merged_into) if archived else "",
        version=version,
    )


def render_page(html: str, boot: BootContext) -> str:
    """Replace the single boot marker of `html` with the boot block. Raises `BootMarkerError` unless the marker occurs
    exactly once. The block is `<script type="application/json">`, so it is not executable and not hashed; every `<` in
    it is the JSON escape `\\u003c`, so no label or name can close the script element, and `ensure_ascii` keeps the
    line separators U+2028 and U+2029 out of it."""
    found = html.count(BOOT_MARKER)
    if found != 1:
        raise BootMarkerError(f"a page must hold {BOOT_MARKER} exactly once, found {found}")
    payload = json.dumps(boot.model_dump(), separators=(",", ":")).replace("<", "\\u003c")
    return html.replace(BOOT_MARKER, f'<script type="application/json" id="{BOOT_BLOCK_ID}">{payload}</script>')


# An inline script that the policy can name by hash: a start tag with NO attributes (a `src`, `type` or `nonce` makes it
# something else: external, data, or already named). Found by scanning, not by one backtracking pattern, so a document
# with many unclosed tags stays linear. The end tag is `</script` followed by a space, `/` or `>`, as the HTML tokenizer
# reads it.
_SCRIPT_OPEN = re.compile(r"<script[\t\n\f\r ]*>", re.IGNORECASE)
_SCRIPT_CLOSE = re.compile(r"</script(?=[\t\n\f\r />])", re.IGNORECASE)
_HASH_SOURCE = re.compile(r"'sha256-[A-Za-z0-9+/]{43}='")


def inline_script_hashes(html: str) -> list[str]:
    """The CSP source `'sha256-<base64>'` of each attribute-less inline script of `html`, in document order.
    A browser hashes the script text after the HTML parser has turned CRLF and a lone CR into LF, so the text is
    normalised the same way; every other character, whitespace included, counts."""
    hashes: list[str] = []
    pos = 0
    while True:
        start = _SCRIPT_OPEN.search(html, pos)
        if start is None:
            break
        end = _SCRIPT_CLOSE.search(html, start.end())
        if end is None:
            break
        text = html[start.end() : end.start()].replace("\r\n", "\n").replace("\r", "\n")
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode("ascii") + "'")
        pos = end.end()
    return hashes


def csp_header(hashes: Sequence[str]) -> str:
    """The Content-Security-Policy value of every page. Scripts: this origin plus the given hashes, never
    'unsafe-inline'. Styles keep 'unsafe-inline' because J2 builds 43 style attributes and generated SVG carries a
    `<style>` (S3-web-09). A source that is not a `'sha256-...'` token is refused, so no caller can add a directive."""
    sources: list[str] = []
    for source in hashes:
        if not _HASH_SOURCE.fullmatch(source):
            raise ValueError(f"not a CSP sha256 source: {source!r}")
        if source not in sources:
            sources.append(source)
    return "; ".join(
        [
            "default-src 'self'",
            "script-src " + " ".join(["'self'", *sources]),
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "frame-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
        ]
    )
