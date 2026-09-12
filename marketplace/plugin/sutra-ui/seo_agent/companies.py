"""companies.py -- one person, several companies.

Owner, 2026-09-11: "one person can do the content for more than one company... when he opens the
agent, an option to choose a company he has already worked on... add another company... and in
the Agent Marketplace tab I should not see any company name."

A COMPANY IS A FOLDER. Every file the agent keeps -- knowledge, chats, library, memory, prompts,
the team workspace -- already lives under one folder, store.data_dir(). So switching company is
switching that folder, and nothing else in the engine has to know companies exist.

NOTHING OF THE FIRST COMPANY MOVES. It stays exactly where every install has always kept its
data, the root; each company added after it gets companies/<id>/ beside it. Moving somebody's
live knowledge (4 GB on the owner's Mac) to introduce a feature is the one way to lose it, so it
is never moved, renamed or copied.

WHAT IS SHARED. The DataForSEO login and the Voyage key are the PERSON's, and every company reads
them from the root (store.connections). The registry, companies.json, is the person's too, and it
is only written once there is something to record: a person with one company never gets one.
"""
import os
import re
import uuid

from . import store

REGISTRY = "companies.json"
FIRST = "c1"
NAME_MAX = 80
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")


def registry_file():
    return os.path.join(store.root_dir(), REGISTRY)


def path_of(cid):
    """A company's folder. The id is checked before it is joined, so nothing can climb out."""
    cid = str(cid or "")
    if cid == FIRST:
        return store.root_dir()
    if not _ID.match(cid):
        raise ValueError("That is not a company.")
    return os.path.join(store.root_dir(), "companies", cid)


def clean_name(name):
    n = " ".join(str(name or "").split())[:NAME_MAX]
    if not n:
        raise ValueError("Type the company's name.")
    return n


def _read(path):
    try:
        return store.read_json(path, {}) or {}
    except Exception:  # noqa: BLE001
        return {}


def _brand_of(cid):
    """What a company's own brand record says, read straight off ITS folder -- never through
    store, which points at the active company, while this has to answer for every one."""
    co = _read(os.path.join(path_of(cid), "knowledge", "brand", "company.json"))
    name = str(co.get("brand") or "").strip()
    return ("" if name.lower() == "this company" else name), str(co.get("domain") or "").strip()


def load():
    """The registry as it is, or as it would be: one company, the root, named from its brand."""
    reg = _read(registry_file())
    rows = [r for r in (reg.get("companies") or []) if isinstance(r, dict)
            and (r.get("id") == FIRST or _ID.match(str(r.get("id") or "")))]
    # FIRST is implicit: it is the root, which exists on every install, so it is put back unless
    # the person deleted it (remove() records that). Without the flag a deleted first company
    # would return on the next read, pointing at a root whose data has gone.
    if not any(r.get("id") == FIRST for r in rows) and not reg.get("first_deleted"):
        rows.insert(0, {"id": FIRST, "name": "", "created_at": ""})
    for r in rows:
        if r["id"] == FIRST and not str(r.get("name") or "").strip():
            r["name"] = _brand_of(FIRST)[0]
    active = reg.get("active")
    if not any(r["id"] == active for r in rows):
        active = rows[0]["id"] if rows else FIRST
    return {"active": active, "companies": rows,
            "first_deleted": bool(reg.get("first_deleted"))}


def _save(reg):
    # first_deleted travels with every write. It used to be set by remove() alone, and the next
    # ordinary save -- a switch, a rename, deleting some other company -- wrote a registry without
    # it, so the deleted first company came back pointing at a root whose data had gone.
    out = {"active": reg["active"], "companies": reg["companies"]}
    if reg.get("first_deleted"):
        out["first_deleted"] = True
    store.write_json(registry_file(), out)


def _chats(cid):
    d = os.path.join(path_of(cid), "chats")
    try:
        return len([n for n in os.listdir(d) if not n.startswith(".")])
    except OSError:
        return 0


def listing():
    """Every company, with what the chooser shows: a name, the site, how many chats."""
    reg = load()
    out = []
    for r in reg["companies"]:
        try:
            brand, domain = _brand_of(r["id"])
        except Exception:  # noqa: BLE001
            brand, domain = "", ""
        out.append({"id": r["id"], "name": str(r.get("name") or "").strip() or brand,
                    "domain": domain, "chats": _chats(r["id"]), "active": r["id"] == reg["active"]})
    return {"active": reg["active"], "companies": out}


def active():
    reg = load()
    return next(r for r in reg["companies"] if r["id"] == reg["active"])


def add(name):
    """A new company: its own folder, beside the first. Does NOT switch to it -- the caller does,
    once it has checked that nothing is running for the company being left."""
    n = clean_name(name)
    reg = load()
    if any(str(r.get("name") or "").strip().lower() == n.lower() for r in reg["companies"]):
        raise ValueError("You already have a company called %s." % n)
    slug = re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")[:30] or "company"
    cid = "%s-%s" % (slug, uuid.uuid4().hex[:4])
    root = path_of(cid)
    for sub in ("chats", "knowledge", "library"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    reg["companies"].append({"id": cid, "name": n, "created_at": store.now()})
    _save(reg)
    return {"id": cid, "name": n}


def switch(cid):
    reg = load()
    if not any(r["id"] == cid for r in reg["companies"]):
        raise ValueError("There is no such company.")
    store.set_data_dir(path_of(cid))
    reg["active"] = cid
    _save(reg)
    return cid


def rename(cid, name):
    n = clean_name(name)
    reg = load()
    for r in reg["companies"]:
        if r["id"] == cid:
            if any(o is not r and str(o.get("name") or "").strip().lower() == n.lower()
                   for o in reg["companies"]):
                raise ValueError("You already have a company called %s." % n)
            r["name"] = n
            _save(reg)
            return {"id": cid, "name": n}
    raise ValueError("There is no such company.")


                                        # everything one company owns, and nothing the person does
OWNED = ("chats", "knowledge", "library", "workspace", "prompts", "memory.jsonl")


def remove(cid):
    """Delete a company: its knowledge, chats, library, memory and team workspace.

    Owner, 2026-09-12: "there should be a 3 dot option... delete everything about that particular
    brand completely, so it goes away."

    THE FIRST COMPANY IS NOT A FOLDER OF ITS OWN. It lives at the root, where the person's own
    things also live: the DataForSEO login, the Voyage key, the list of companies, and the
    folders of every other company. So deleting it removes what it OWNS, one name at a time,
    and never the root itself. Any other company is one folder and goes whole.

    The caller stops whatever is running first; this does not kill threads.
    """
    reg = load()
    if not any(r["id"] == cid for r in reg["companies"]):
        raise ValueError("There is no such company.")
    if len(reg["companies"]) < 2:
        raise ValueError("This is your only company, so there is nothing to switch to. "
                         "Add another one first, then delete this.")

    import shutil
    root = path_of(cid)
    if cid == FIRST:
        # knowledge-backup-<n> is a copy of this company's knowledge that index_site leaves
        # behind, and it is as much "everything about that brand" as the folder it came from.
        # 146 MB of one survived the first pass on the owner's own install.
        owned = list(OWNED) + sorted(n for n in os.listdir(root)
                                     if n.startswith("knowledge-backup"))
        for name in owned:
            p = os.path.join(root, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        conn = store.read_json(os.path.join(root, "connections.json"), {}) or {}
        kept = {k: v for k, v in conn.items() if k in store.PERSON_KEYS}
        if kept != conn:
            store.write_json(os.path.join(root, "connections.json"), kept)
    else:
        shutil.rmtree(root, ignore_errors=True)

    rows = [r for r in reg["companies"] if r["id"] != cid]
    # FIRST is implicit -- load() puts it back unless the registry says it was deleted, and
    # without this the row would reappear on the next read pointing at an empty root. The flag is
    # carried by _save, so deleting a SECOND company later cannot quietly drop it.
    reg2 = {"active": reg["active"], "companies": rows,
            "first_deleted": bool(reg.get("first_deleted")) or cid == FIRST}
    if reg["active"] == cid:
        reg2["active"] = rows[0]["id"]
        store.set_data_dir(path_of(rows[0]["id"]))
    _save(reg2)
    return {"deleted": cid, "active": reg2["active"]}


def activate_saved():
    """At start-up, open the company that was open last time. No registry means one company, at
    the root, which is where store already points -- so there is nothing to do."""
    if not os.path.exists(registry_file()):
        return None
    reg = load()
    store.set_data_dir(path_of(reg["active"]))
    return reg["active"]
