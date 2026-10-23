"""founding.py -- how an organisation, its Root and its departments come to be.

Founder, 2026-09-28: "I want root to be there, and then root can always spawn off new departments. There will be only
one root in an app. There will be one root for one organizational structure. If there are two different roots created,
then two org structures are operating." And: "I don't want to create the old way. I want it to be organic only."

So: an organisation is founded with its one Root, a department of the kind root, On, and nothing else. Every other
department is Root's to spawn: the owner's words on Root become a Request, Root's engine Setup shapes and makes the
department under Root (its charter, its functions' templates, its record, its goal), and Root's rule holds: a new
department is stamped by the owner. Two organisations are two structures, each with its own Root.

The registry (placement_engine) holds the tree; org2_apply applies the same asks the Org screen files; website_dept
holds each department's record.
"""
import sys
from pathlib import Path

_LIB = str(Path(__file__).resolve().parents[1] / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import placement_engine as E  # noqa: E402
import org2_apply  # noqa: E402
import proposals  # noqa: E402
import website_dept as W  # noqa: E402

TEMPLATE = "product-build"          # the Library's use-case template for a department that builds a product
FUNCTIONS = ("identity", "adaptation", "priority", "coordination", "audit")


def _apply(kind, args, summary):
    """File the request as a proposal and apply it on the owner's command."""
    rec = proposals.create(kind, args, summary)
    rec = proposals.decide(rec["id"], True, apply_fn=org2_apply.apply_request)
    if rec.get("status") != "approved":
        raise ValueError(str((rec.get("result") or {}).get("error") or rec.get("status")))
    return rec["result"]


def _child(domains, parent, name):
    for ref, d in E.live_refs(domains).items():
        if d.get("parent_ref") == parent and (d.get("name") or "").lower() == name.lower():
            return ref
    return None


def ensure(parent, name, summary):
    ref = _child(E.load_domains(), parent, name)
    if ref:
        return ref, False
    out = _apply("org.create", {"parent": parent, "name": name}, summary)
    return out["ref"], True


def charter(ref, purpose, done, rules, summary):
    return _apply("org.charter", {"ref": ref, "purpose": purpose, "done_when": done, "rules": rules}, summary)


def _standing(ref):
    """The registry's charter that speaks for the department, by dept_api's own rule: the first active, unsuperseded
    charter of kind standing, else the first active one that is not a role. None when it has none."""
    views = [v for v in (E.charter_view(c) for c in E.charters_for(ref)) if v]
    sup = E.superseded_ids()
    live = [v for v in views if v.get("status", "active") != "retired" and v.get("id") not in sup and str(v.get("kind") or "") != "role"]
    return next((v for v in live if v.get("kind", "standing") == "standing"), live[0] if live else None)


def mirror(ref):
    """The registry's charter as a one-way mirror of the department's one record (PRD M3.1). dept.json holds the goal,
    the done-when items, the rules, the owner, the budget and the windows; the Org screen still reads the charter, so on
    every identity revision the goal, the done-when lines and the rules are copied onto it, by succession. Every
    registry write goes through a filed proposal (decision C1), so the copy is filed and applied in one move, as _apply
    does: nothing waits for the owner, who stamped the identity itself. Nothing is filed when the charter says the same
    already, or when the department is not in the registry. Returns the applied result, or None."""
    d = W.dept(ref)
    if not d or ref not in E.live_refs(E.load_domains()):
        return None
    purpose = " ".join(str(d.get("goal") or "").split())[:org2_apply.PURPOSE_MAX]
    if not purpose:
        return None
    items = [i.get("text") for i in d.get("done_items") or [] if isinstance(i, dict) and str(i.get("text") or "").strip()]
    done = E.normalize_done_when(items or ([d["done"]] if str(d.get("done") or "").strip() else []))
    rules = E.normalize_rules([{"tag": r.get("tag"), "line": r.get("line")} for r in d.get("rules") or []
                               if isinstance(r, dict) and r.get("tag") in E.CHARTER_RULE_TAGS and str(r.get("line") or "").strip()])
    cur = _standing(ref)
    if cur and " ".join(str(cur.get("purpose") or "").split()) == purpose and list(cur.get("done_when") or []) == done \
            and E.normalize_rules(cur.get("rules")) == rules:
        return None
    args = {"ref": ref, "purpose": purpose, "done_when": done, "rules": rules}
    if cur:
        args["charter_id"] = cur["id"]
    return _apply("org.charter", args, "Copy %s's identity, revision %d, to the Org screen"
                  % (d.get("name") or ref, int(d.get("identity_revision") or 1)))


def roots():
    """Every Root: one for each organisational structure in this app."""
    return [d for d in W.list_depts() if d.get("kind") == "root"]


def found_structure(org_name, owner="the owner"):
    """An organisation and its one Root, On. Departments are Root's to spawn. Founding the same organisation again
    finds its Root and creates nothing."""
    org_name = " ".join(str(org_name or "").split())[:80]
    if not org_name:
        raise ValueError("name the organisation")
    top = E.active_roots(E.load_domains())
    if not top:
        raise ValueError("the registry has no root")
    org, org_new = ensure(top[0], org_name, "Found %s as a new organisation" % org_name)
    if org_new:
        charter(org, "%s, as one organisation run on Sutra" % org_name, [], [], "Write %s's charter" % org_name)
    root, root_new = ensure(org, "Root", "Give %s its root department" % org_name)
    created = False
    if root_new or not W.dept(root):
        k = W.KINDS["root"]
        charter(root, k["goal"].format(name=org_name), [k["done"]], k["rules"], "Write the root department's charter")
        d, _ = W.create(root, "%s Root" % org_name, None, owner=owner, parent=org, kind="root")
        d["org"] = {"ref": org, "name": org_name}
        W.save_dept(root, d)
        created = True
    return {"org": org, "root": root, "created": created}


def spawn(root_ref, name, kind, goal, owner="the owner", goal_context=None, template_ref=None, route="template",
          done_items=None, to_confirm=None):
    """Root sets up a department: the child under Root, its charter, its functions' templates from the Library, its record,
    and its goal, which makes it run. Asking for the same name again finds it and makes nothing.

    `done_items` are the done-when items Root drafted at birth (PRD M3.2), part of what Root stamps: the record keeps
    them, `done` stays as their joined text, and the charter carries them as its done-when lines. With none, the kind's
    own done line is D1. `to_confirm` names the items that rest on a fact nobody gave: [{item, why}]."""
    rd = W.dept(root_ref)
    if not rd or rd.get("kind") != "root":
        raise ValueError("only a Root sets up departments")
    if kind not in W.KINDS or kind == "root":
        raise ValueError("the Library has no department kind named %s" % kind)
    name = " ".join(str(name or "").split())[:80]
    goal = " ".join(str(goal or "").split())[:2000]
    if not name or not goal:
        raise ValueError("a department has a name and a goal")
    ref, new = ensure(root_ref, name, "Root sets up %s" % name)
    existing = W.dept(ref)
    had_record = bool(existing)
    had_goal = bool(W.requests(ref)) if had_record else False
    context = goal_context or {"messages": [{"actor": "user", "text": goal}]}
    operation = "found:%s:%s" % (context.get("id") or ref, context.get("selected_revision") or "latest")
    if not new and not had_record:
        raise ValueError("the registry and department record disagree for %s" % name)
    if had_record:
        if existing.get("kind") != kind:
            raise ValueError("an incompatible department already has the name %s" % name)
        if existing.get("template_ref") and existing.get("template_ref") != template_ref:
            raise ValueError("the existing department uses another template")
        if had_goal:
            prior_operation = (existing.get("founding") or {}).get("operation_id")
            same_operation = prior_operation == operation
            return {"ref": ref, "name": name, "kind": kind, "goal": goal, "created": False,
                    "operation_id": prior_operation, "existing": not same_operation}
    k = W.KINDS[kind]
    items = W.done_items(done_items, kind)
    if new:
        charter(ref, goal, [i["text"] for i in items], k["rules"], "Write %s's charter" % name)
    picks = {}
    tpl = k.get("functions_template") or TEMPLATE
    import function_templates as FT
    for fn in FUNCTIONS:
        tid = "%s/%s" % (fn, tpl)
        if FT.picked(ref).get(fn) != tid:
            _apply("org.template", {"ref": ref, "function": fn, "template": tid}, "%s runs the %s template" % (fn.title(), tpl))
        picks[fn] = tid
    if not had_record:
        # the shaped goal is the owner's words, and it is the record's goal from birth (PRD M3.1)
        d, _ = W.create(ref, name, None, owner=owner, parent=root_ref, kind=kind, goal=goal)
    else:
        d = existing
    checkpoints = ["root", "child", "functions", "rules_limits", "goal_context", "born_engines"]
    d.update({"templates": picks, "org": rd.get("org") or {}, "root": root_ref, "template_ref": template_ref,
              "initial_goal_context": context, "goal": goal,
              "done_items": [{x: i[x] for x in ("id", "text", "how", "level")} for i in items], "done": W.done_line(items),
              "to_be_confirmed": [dict(c) for c in to_confirm or [] if isinstance(c, dict) and c.get("item")],
              "founding": {"operation_id": operation, "checkpoints": checkpoints}})
    W.save_dept(ref, d)
    if not had_goal:
        W.give_goal(ref, goal)
    d = W.dept(ref)
    events = list(d.get("events") or [])
    if not any(e.get("kind") == "j2_ready" for e in events):
        events.append({"kind": "j2_ready", "route": route or ("organic" if kind == "organic" else "template")})
    d["events"] = events
    d["founding"] = {"operation_id": operation,
                     "checkpoints": checkpoints + ["j2_ready"]}
    W.save_dept(ref, d)
    # J1 ends here and J2 is the department's own life: its cycle starts with the hand-over, and nobody presses Start
    import j2_runtime
    if j2_runtime.enabled():
        j2_runtime.begin(ref)
    return {"ref": ref, "name": name, "kind": kind, "goal": goal, "created": bool(new or not had_record or not had_goal),
            "existing": False, "operation_id": operation}
