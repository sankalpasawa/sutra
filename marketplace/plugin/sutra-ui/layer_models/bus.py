"""The revision counter a model edit bumps and the stream reads (A4.7.4): one integer, and the last keys that moved.
Reading it costs a lock and an integer, so a stream producer may ask for it on every frame."""
import threading

_LOCK = threading.Lock()
_REV = 0
_LOG = []            # [(revision, key)], the last KEEP bumps
KEEP = 200


def revision():
    """The current revision: 0 until the first bump."""
    with _LOCK:
        return _REV


def bump(keys=()):
    """Count one change; `keys` names what moved ('x.client'). Returns the new revision."""
    global _REV
    with _LOCK:
        _REV += 1
        for k in (keys or ()):
            _LOG.append((_REV, k))
        del _LOG[:-KEEP]
        return _REV


def changed_since(rev):
    """The keys bumped after revision `rev`, oldest first, each once. Only the last KEEP bumps are remembered."""
    with _LOCK:
        out = []
        for r, k in _LOG:
            if r > rev and k not in out:
                out.append(k)
        return out
