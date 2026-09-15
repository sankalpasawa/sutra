"""org2_apply.py -- apply an APPROVED Org request (rename, move, new sub-department).

WHY THIS EXISTS
The new Org screen (19-org2.js) never edits the registry directly. The pencil's
Rename, Move and New sub-department each file a PROPOSAL (POST /api/org2/request
-> proposals.create) that waits in Approvals; approving it calls this module
through org_api._apply_proposal, exactly as a routine or a pull request is
applied. Nothing here runs without that approval (BUILD-PLAN.md phase 8).

WHY IT IS ITS OWN MODULE
org_api.py and org2_api.py are read-only by test (test_forbidden_calls.py fails
the build if either names `restructure` or `mint_domain`), and org_apply.py
guarantees STRUCTURALLY that it applies moves and nothing else (the founder's
drag-and-drop constraint of 2026-09-13). A rename and a mint are neither, so
they live apart, the way project_import.py lives apart to call mint_domain.

REGISTRY ONLY. Every write lands under SUTRA_NATIVE_HOME through the engine's
own locked writers: a rename changes one domain record's `name` and appends an
audit line; a move is delegated to org_apply.apply_moves (validated against a
fresh read, refused on any block); a new sub-department is one mint_domain
under a live parent. No project directory, transcript, git repo or workdir
file is touched.
"""
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import placement_engine as E  # noqa: E402
import org_apply              # noqa: E402  (the one validated move path)

KINDS = ("org.rename", "org.move", "org.create")
NAME_MAX = 80


def _name(raw):
    s = " ".join(str(raw or "").split())
    if not s:
        raise ValueError("a name is required")
    if len(s) > NAME_MAX:
        raise ValueError("the name is longer than %d characters" % NAME_MAX)
    return s


def _live(ref, domains, what="department"):
    d = domains.get(ref)
    if not d:
        raise ValueError("no %s %s" % (what, ref))
    if d.get("status") == "retired":
        raise ValueError("%s is retired" % (d.get("name") or ref))
    return d


def _no_live_sibling_named(ref, parent_ref, name, domains):
    """ValueError when another live child of `parent_ref` already carries
    `name` (case-insensitive). Shared by rename and create."""
    want = name.lower()
    for r, x in E.live_refs(domains).items():
        if r != ref and x.get("parent_ref") == parent_ref and (x.get("name") or "").lower() == want:
            parent = (domains.get(parent_ref) or {}).get("name") or "the root"
            raise ValueError("%s already has a department named %s" % (parent, name))


def apply_request(kind, args):
    """Apply one approved request. Raises ValueError (nothing written) when the
    request no longer fits the tree; org_apply.ApplyRefused rides through for
    a move that stopped validating."""
    args = dict(args or {})
    if kind == "org.rename":
        domains = E.load_domains()
        d = _live(args.get("ref"), domains)
        name = _name(args.get("name"))
        if name == d.get("name"):
            raise ValueError("%s already has that name" % name)
        # restructure("rename") does not look at siblings (DeepSeek review P1-7);
        # two live siblings with one name would defeat mint_domain's dedupe.
        _no_live_sibling_named(args["ref"], d.get("parent_ref"), name, domains)
        E.restructure("rename", args["ref"], name=name)
        return {"applied": True, "ref": args["ref"], "name_before": d.get("name"), "name_after": name}
    if kind == "org.move":
        return org_apply.apply_moves([{"op": "move", "ref": args.get("ref"), "target": args.get("target")}],
                                     base=args.get("base"))
    if kind == "org.create":
        domains = E.load_domains()
        parent = _live(args.get("parent"), domains, "parent")
        name = _name(args.get("name"))
        _no_live_sibling_named(None, args["parent"], name, domains)
        ref, created = E.mint_domain(args["parent"], name, [name], parent.get("tenant_id") or "T-local",
                                     origin="operator-request")
        return {"applied": True, "ref": ref, "created": bool(created), "parent": args["parent"], "name": name}
    raise ValueError("no way to apply %r" % kind)
