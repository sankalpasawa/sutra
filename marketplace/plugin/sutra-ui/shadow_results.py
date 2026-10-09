"""What a task made (founder, 2026-10-09, from Paperclip's per-task results
tab): the files, where they are, and a way to open each one.

WHERE THE LIST COMES FROM -- never a guess:

  own copy, not yet kept   the files the task changed in its copy since its
                           starting point (shadow_workspace.changes)
  own copy, kept           the files that were added to the founder's folder
  no copy                  the files the task's own checks named, or recorded
                           as its artifacts (shadow_paths.owned_artifacts)

OPENING ONE. Only a file on that list, and only inside the task's folder: a
text file is served as plain text (an .html is words to read, never a page
that runs in the app), an image or a PDF as itself, anything else as a
download. Capped at OPEN_MAX_BYTES.
"""
import os

OPEN_MAX_BYTES = 5 * 1024 * 1024


def _kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
        return "image"
    if ext == ".pdf":
        return "pdf"
    try:
        import shadow_attachments
        if ext in shadow_attachments.TEXT_EXT:
            return "text"
    except Exception:                    # noqa: BLE001
        pass
    return "file"


def _where(mission):
    """(root, files, where, note) for this task, before sizes are read."""
    ws = (mission or {}).get("workspace") or {}
    state = ws.get("state")
    if state in ("active", "pending", "clash"):
        import shadow_workspace
        files, _patch = shadow_workspace.changes(ws)
        return ws.get("path"), files, "copy", ""
    if state == "kept":
        return ws.get("repo"), list(ws.get("files") or []), "project", ""
    if state in ("discarded", "empty"):
        return None, [], "none", ("Thrown away -- nothing was added to your "
                                  "project." if state == "discarded"
                                  else "This task didn't change any files.")
    import shadow_paths
    root = shadow_paths.mission_artifact_root(mission)
    return root, shadow_paths.owned_artifacts(mission), "project", ""


def results(mission):
    """{"where", "files": [{"path", "name", "folder", "bytes", "kind",
    "exists"}], "note"}. Never raises."""
    try:
        root, files, where, note = _where(mission)
    except Exception as exc:              # noqa: BLE001
        return {"where": "none", "files": [], "note": "couldn't read the "
                "files (%s)" % str(exc)[:120]}
    out = []
    for rel in files[:200]:
        rel = str(rel).replace("\\", "/").lstrip("/")
        full = _resolve(root, rel)
        exists = bool(full and os.path.isfile(full))
        out.append({"path": rel, "name": os.path.basename(rel),
                    "folder": os.path.dirname(rel),
                    "bytes": os.path.getsize(full) if exists else None,
                    "kind": _kind(rel), "exists": exists})
    if not out and not note:
        note = ("No files yet." if (mission or {}).get("state") not in
                ("done", "failed", "stopped") else
                "This task didn't leave any files Shadow knows about.")
    return {"where": where, "files": out, "note": note}


def _resolve(root, rel):
    """The real path of `rel` inside `root`, or None when it would leave it."""
    if not root or not rel:
        return None
    base = os.path.realpath(root)
    full = os.path.realpath(os.path.join(base, rel))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


def open_file(mission, rel):
    """(media_type, bytes, download_name or None) for one listed file.
    Raises LookupError when it is not on the list or not there,
    ValueError when it is too big."""
    rel = str(rel or "").replace("\\", "/").lstrip("/")
    root, files, _where_, _note = _where(mission)
    listed = {str(f).replace("\\", "/").lstrip("/") for f in files}
    if rel not in listed:
        raise LookupError("that file is not one this task made")
    full = _resolve(root, rel)
    if not full or not os.path.isfile(full):
        raise LookupError("that file isn't there any more")
    if os.path.getsize(full) > OPEN_MAX_BYTES:
        raise ValueError("too big to open here (over %d MB)"
                         % (OPEN_MAX_BYTES // 1048576))
    with open(full, "rb") as fh:
        blob = fh.read()
    import shadow_attachments
    media = shadow_attachments.media_type_of(blob)
    if media:
        return media, blob, None
    if b"\x00" not in blob:
        try:
            blob.decode("utf-8")
            return "text/plain; charset=utf-8", blob, None
        except UnicodeDecodeError:
            pass
    return "application/octet-stream", blob, os.path.basename(rel)
