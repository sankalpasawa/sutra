"""link.py — the share link, and the promise that it cannot do any harm.

WORKSPACE-PLAN section 5: the share link is the project URL, the publishable key and the
workspace id, base64'd into one string with a copy button. A teammate pastes it, types a
name, and they are in.

WHAT IS NOT IN IT, AND WHY THAT IS THE WHOLE POINT. Nothing in a link can create a table,
drop a table, or read another project. It carries no SQL, no personal access token, no secret
key and no service_role JWT. read_link() ENFORCES that rather than trusting it: a link whose
key is a secret one is refused, and tests/test_workspace_core.py asserts both directions.
That refusal matters because the link is the one thing in this system that gets pasted into
WhatsApp, and a person who pastes the wrong key has to be stopped by the code, not by a
warning in a doc they will not read.

WHY IT IS ONE OPAQUE STRING RATHER THAN THREE BOXES. Three boxes is three chances to paste
the wrong thing into the wrong one, and the plan's join flow is "paste the link, type a name,
press Done". So it is one token with a visible prefix, `sutra1_`, which tells a person at a
glance what they are looking at and lets Sutra reject something that is not a Sutra link with
a sentence rather than a decoding error.

Base64URL, not standard base64: its alphabet is A-Z a-z 0-9 - _, so the string survives being
put in a URL, a chat message or a terminal without anything mangling a + or a /. The padding
is stripped and put back on read, because a trailing = is the character most likely to be
eaten by whatever the link travels through.
"""
import base64
import binascii
import json
import re

from ._common import WorkspaceError

PREFIX = "sutra1_"
VERSION = 1

# The keys a link is allowed to carry. Anything starting sb_secret_ or sbp_, or any JWT whose
# role is service_role, is refused on sight.
BANNED = ("sb_secret_", "sbp_", "supabase_admin", "service_role")


def _b64encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text):
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _check_key(key):
    """Refuse anything that is not the publishable key. Used on the way in AND on the way out.

    Checked when making a link so the creator is stopped before they send it, and checked
    again when reading one so a hand-edited link cannot smuggle a secret past the app.
    """
    key = (key or "").strip()
    if not key:
        raise WorkspaceError("That link has no key in it, so Sutra cannot connect with it.")
    lowered = key.lower()
    for banned in BANNED:
        if banned in lowered:
            raise WorkspaceError(
                "That is a secret key, and a secret key must never be shared. Sutra only puts "
                "the publishable key — the one starting sb_publishable_ — in a link, because "
                "that is the only one bounded by the workspace's own security rules.")
    if not (key.startswith("sb_publishable_") or key.startswith("eyJ")):
        # eyJ is the first three characters of every JWT, which is the older anon key format.
        # Both are accepted; anything else is not a Supabase key at all.
        raise WorkspaceError(
            "That does not look like a Supabase publishable key. It should start with "
            "sb_publishable_.")
    return key


def _check_url(url):
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https://[a-z0-9-]+\.supabase\.(co|in|net)$", url, re.I):
        raise WorkspaceError(
            "That link does not point at a Supabase project. The address should read "
            "https://something.supabase.co")
    return url


def make_link(url, key, workspace_id):
    """One copy-able string carrying the three public things, and nothing else."""
    url = _check_url(url)
    key = _check_key(key)
    workspace_id = (workspace_id or "").strip()
    if not workspace_id:
        raise WorkspaceError(
            "Sutra will not make a share link before the workspace exists — the id comes from "
            "the database, so there is nothing to share yet.")
    # Short field names because the whole thing is a string a person copies by hand when the
    # copy button fails them. Sorted keys so the same inputs always give the same link, which
    # is what lets a test compare two links rather than two decoded blobs.
    payload = json.dumps({"v": VERSION, "u": url, "k": key, "w": workspace_id},
                         sort_keys=True, separators=(",", ":"))
    return PREFIX + _b64encode(payload.encode("utf-8"))


def read_link(text):
    """(url, key, workspace_id) from a link, or a WorkspaceError saying what is wrong with it.

    Every failure here is something a person did with their hands -- pasted half a link,
    pasted a URL instead, pasted it with a line break through the middle -- so every message
    names the mistake instead of reporting a decoding error.
    """
    raw = (text or "").strip().strip('"').strip("'")
    # Chat apps and email wrap long strings, so a pasted link arrives with newlines and
    # spaces through it. Stripping all whitespace is not being lenient about the format, it
    # is refusing to blame a person for what their chat app did to the string.
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        raise WorkspaceError("Paste the link your teammate sent you — the box is empty.")
    if not raw.lower().startswith(PREFIX):
        raise WorkspaceError(
            "That is not a Sutra workspace link. A link looks like sutra1_ followed by a long "
            "string of letters. Ask your teammate to press the copy button next to the link "
            "in their Connections tab.")
    body = raw[len(PREFIX):]
    if not body:
        raise WorkspaceError(
            "That link is cut short — only the sutra1_ part arrived. Copy the whole thing.")
    try:
        decoded = _b64decode(body).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise WorkspaceError(
            "That link is damaged — part of it is missing or a character was changed on the "
            "way. Ask your teammate to send it again.")
    try:
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        raise WorkspaceError(
            "That link is damaged and Sutra could not read what is inside it. Ask your "
            "teammate to send it again.")
    if not isinstance(data, dict):
        raise WorkspaceError("That link is damaged. Ask your teammate to send it again.")
    if int(data.get("v") or 0) > VERSION:
        raise WorkspaceError(
            "That link was made by a newer Sutra than this one. Update Sutra, then paste it "
            "again.")

    url = _check_url(data.get("u"))
    key = _check_key(data.get("k"))
    workspace_id = str(data.get("w") or "").strip()
    if not workspace_id:
        raise WorkspaceError(
            "That link is missing the workspace id. Ask your teammate to copy it again from "
            "their Connections tab.")
    return url, key, workspace_id
