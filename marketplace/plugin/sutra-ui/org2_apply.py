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

KINDS = ("org.rename", "org.move", "org.create", "org.charter")
NAME_MAX = 80
TITLE_MAX = 60           # mint_charter_stub cuts titles here
PURPOSE_MAX = 4000


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
    if kind == "org.charter":
        return _apply_charter(args)
    raise ValueError("no way to apply %r" % kind)


def _kind(raw):
    """The charter kind a request asked for, checked against the engine's own
    closed set (DS-2). Absent means `standing`, the kind every charter this
    path wrote before role existed."""
    kind = str(raw or "standing").strip().lower()
    if kind not in E.CHARTER_KINDS:
        raise ValueError("a charter kind is one of: %s" % ", ".join(E.CHARTER_KINDS))
    return kind


def _person(args):
    """Whose role this is (DS-2). A role charter always names someone, and
    `unfilled` is a name for nobody -- it says the role exists and is open,
    which is a different fact from a charter that names no person at all."""
    name = " ".join(str(args.get("person") or "").split())[:NAME_MAX]
    return name or E.ROLE_UNFILLED


def _extras(prior, done_when, rules, person, kind):
    """The sidecar keys this request carries onto the charter it mints. `None`
    means the request said nothing about that field, so the prior value rides
    through; a list or a string means the request DID, including when it is
    empty. `person` is written for a role charter only."""
    out = {k: prior[k] for k in ("goals", "metrics", "milestones", "todos") if prior.get(k)}
    dw = list(prior.get("done_when") or []) if done_when is None else done_when
    rl = E.normalize_rules(prior.get("rules")) if rules is None else rules
    if dw:
        out["done_when"] = dw
    if rl:
        out["rules"] = rl
    who = (prior.get("person") or "") if person is None else person
    if kind == "role":
        out["person"] = who or E.ROLE_UNFILLED
    elif who:
        out["person"] = who
    return out


def _apply_charter(args):
    """Write or amend a department's charter (BUILD-PLAN S82-S83; founder
    ruling D-O3, 2026-09-15: charters change by SUCCESSION, never in place).

    Bodies are content-addressed and immutable, so an edit mints a NEW body
    with `supersedes` set to the old id -- the shape charter_reassign uses to
    re-home a charter -- carries the old sidecar's status, artifacts, links,
    goals, metrics, milestones and todos, marks the old sidecar
    `lifecycle: superseded` (never the status enum), and re-points every
    current placement that cited the old id (phase post-close), so filed work
    follows the amended charter. A department with no charter gets a fresh
    standing one. Nothing outside the registry is touched.

    DS-1 (2026-09-21): `done_when` and `rules` ride the same request and land
    on the successor's SIDECAR, which is what the department screen's Identity
    card reads. DS-2: `kind` may be `role`, and a role charter's sidecar names
    the `person` who holds it (or `unfilled`). Passing a field ABSENT keeps the
    prior value; passing it empty clears it -- so an edit that only touches the
    title never silently drops the rules, and an operator who deletes every
    rule actually deletes them. This is still the ONLY writer."""
    domains = E.load_domains()
    d = _live(args.get("ref"), domains)
    purpose = " ".join(str(args.get("purpose") or "").split())
    if not purpose:
        raise ValueError("a purpose is required")
    if len(purpose) > PURPOSE_MAX:
        raise ValueError("the purpose is longer than %d characters" % PURPOSE_MAX)
    title = (" ".join(str(args.get("title") or "").split()) or ("%s Charter" % d.get("name")))[:TITLE_MAX]
    tenant = d.get("tenant_id") or "T-local"
    old_id = str(args.get("charter_id") or "").strip() or None
    done_when = E.normalize_done_when(args["done_when"]) if "done_when" in args else None
    rules = E.normalize_rules(args["rules"]) if "rules" in args else None
    person = _person(args) if "person" in args else None
    if not old_id:
        kind = _kind(args.get("kind"))
        extras = _extras({}, done_when, rules, person, kind)
        cid = E.mint_charter_stub(args["ref"], title, purpose, [], [], tenant, kind=kind, extras=extras)
        E._append_jsonl(E.CHARTER_INDEX, {"event": "charter_written", "id": cid, "domain_ref": args["ref"],
                                           "kind": kind, "source": "org2-request", "ts_ms": E._now_ms()})
        return {"applied": True, "charter_id": cid, "supersedes": None, "ref": args["ref"], "repointed": 0}
    old = E.load_charter(old_id)
    if old is None:
        raise ValueError("no charter %s" % old_id)
    if old.get("domain_ref") != args["ref"]:
        raise ValueError("charter %s belongs to another department" % old_id)
    if E.superseded_by(old_id):
        raise ValueError("charter %s was already amended; edit the current one" % old_id)
    prior = E.load_sidecar(old_id)
    kind = _kind(args.get("kind")) if args.get("kind") else (old.get("kind") or prior.get("kind") or "standing")
    if (old.get("title") == title
            and " ".join(str(old.get("purpose") or "").split()) == purpose
            and kind == (old.get("kind") or prior.get("kind") or "standing")
            and (done_when is None or done_when == list(prior.get("done_when") or []))
            and (rules is None or rules == E.normalize_rules(prior.get("rules")))
            and (person is None or person == (prior.get("person") or ""))):
        raise ValueError("nothing changed")
    cid = E.mint_charter_stub(args["ref"], title, purpose, list(old.get("scope_in") or []), list(old.get("scope_out") or []),
                              old.get("tenant_id") or tenant, kind=kind,
                              supersedes=old_id, status=prior.get("status", "active"),
                              artifacts=prior.get("artifacts") or [], linked_domain_refs=prior.get("linked_domain_refs") or [],
                              extras=_extras(prior, done_when, rules, person, kind))
    citing = [p for p in E._current_placements() if p.get("charter_id") == old_id]
    for p in citing:
        E.write_placement(p["work_ref"], args["ref"], cid, "matched", p.get("confidence", 0.5),
                          {"domains": [], "charters": []}, old.get("tenant_id") or tenant,
                          supersedes=p["id"], phase="post-close")
    sc = E.load_sidecar(old_id)
    sc["lifecycle"] = "superseded"
    E.save_sidecar(old_id, sc)
    E._append_jsonl(E.CHARTER_INDEX, {"event": "charter_amended", "id": old_id, "successor_id": cid,
                                       "domain_ref": args["ref"], "placements_repointed": len(citing),
                                       "kind": kind, "source": "org2-request", "ts_ms": E._now_ms()})
    return {"applied": True, "charter_id": cid, "supersedes": old_id, "ref": args["ref"], "repointed": len(citing)}
