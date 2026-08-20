"""json_store.py — atomic, permission-safe JSON read/write for the small
on-disk stores under ~/.sutra-ui.

EXTRACTED, NOT REWRITTEN. These two functions lived in composio_store.py and
were imported from there by teamsutra.py. Removing the connector layer took
composio_store.py with it, and the helpers are not connector code at all: they
are the store I/O convention every small record file here follows. Rewriting
them from memory would have quietly dropped two properties that were each
earned by a real failure, so they are moved verbatim:

  - 0600 is forced with fchmod AFTER open, because O_CREAT's mode argument is
    ignored when the temp file already exists and O_TRUNC clears contents but
    not permission bits. Without it os.replace can carry a world-readable inode
    onto a file holding a secret.
  - the temp name is UNIQUE PER WRITER (pid + thread). A fixed suffix let two
    concurrent writers of the same record interleave into one tmp inode and
    os.replace then promoted torn JSON as the durable file — caught as a 1-in-6
    flake by test_teamsutra's concurrency test.

Anything that needs a durable small JSON record should use these rather than
open().write(), including the connector layer when it is rebuilt.
"""
import json
import os
import threading


def read_json(path, default):
    """Parse one JSON file, or `default` on any missing/corrupt/wrong-shape
    read. Never raises — every caller is on a path where a broken file must
    degrade, not 500."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def write_json(path, obj):
    """Atomically write one JSON file (tmp + os.replace), matching org_api's
    convention: a crash mid-write cannot leave a truncated file. The mode is
    forced to 0600 and that mode survives the replace — see the module header
    for why each half of this is load-bearing."""
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = "%s.sutra-tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)  # load-bearing when tmp pre-existed at a laxer mode
    except (OSError, AttributeError):
        pass  # a platform without fchmod still gets O_CREAT's 0600 on a fresh file
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)
