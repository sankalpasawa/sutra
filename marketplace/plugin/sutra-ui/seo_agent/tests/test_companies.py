"""One person, several companies (owner, 2026-09-11).

"One person can do the content for more than one company... choose a company he has already
worked on... add another company... and he will still be able to see the earlier one."

What this suite holds on to, because each is how the feature would hurt somebody:
  * a person with ONE company sees nothing change and gets nothing written
  * the first company's data never moves
  * a company never sees another's knowledge, chats or team workspace
  * the person's paid keys follow them into every company, and are never lost by omission
  * a switch is refused while anything is still running for the company being left
"""
import os
import shutil
import sys
import threading

from seo_agent.tests import _fixture   # noqa: F401  (throwaway SEO_AGENT_DATA)

from seo_agent import companies, store

FAILS = []


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("  -> %s" % (extra,)) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(label)


def refused(label, fn, needle=""):
    try:
        fn()
        ok(label, False, "it was allowed")
    except ValueError as e:
        ok(label, needle.lower() in str(e).lower(), str(e))


store.set_data_dir(None)
ROOT = store.root_dir()
for n in ("companies", "companies.json", "connections.json"):
    p = os.path.join(ROOT, n)
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)
PERSON = os.path.join(ROOT, "connections.json")

# ==========================================================================================
print("\nONE COMPANY: nothing changes for a person who never adds a second")
lst = companies.listing()
ok("a fresh install has exactly one company, and it is the open one",
   len(lst["companies"]) == 1 and lst["companies"][0]["active"], lst)
ok("...and it lives at the root, where every install has always kept its data",
   companies.path_of(companies.FIRST) == ROOT and store.data_dir() == ROOT)
ok("nothing is written until there is a reason: no registry for one company",
   not os.path.exists(companies.registry_file()))
store.save_knowledge("brand/company.json", {"brand": "Testlify", "domain": "testlify.com"})
ok("the first company is named from its own brand record",
   companies.listing()["companies"][0]["name"] == "Testlify")

# ==========================================================================================
print("\nADD, SWITCH, AND KEEP THEM APART")
store.save_connections(dict(store.connections(), dataforseo_login="me@example.com",
                            dataforseo_password="pw", voyage_key="vk",
                            workspace_url="https://one.supabase.co"))
acme = companies.add("Acme Hiring")
ok("adding a company makes its own folder",
   os.path.isdir(os.path.join(companies.path_of(acme["id"]), "knowledge")))
ok("...beside the first, never inside its knowledge",
   os.path.dirname(companies.path_of(acme["id"])) == os.path.join(ROOT, "companies"))
ok("...and does not switch on its own", store.data_dir() == ROOT)

companies.switch(acme["id"])
ok("switching moves every path the agent uses",
   store.knowledge_dir() == os.path.join(companies.path_of(acme["id"]), "knowledge")
   and store.chats_dir() == os.path.join(companies.path_of(acme["id"]), "chats"))
ok("the new company knows nothing of the first one's brand",
   not os.path.exists(os.path.join(store.knowledge_dir(), "brand", "company.json")))
store.save_knowledge("brand/company.json", {"brand": "Acme", "domain": "acme.com"})

c = store.connections()
ok("the person's DataForSEO login follows them into the new company",
   c.get("dataforseo_login") == "me@example.com" and c.get("dataforseo_password") == "pw")
ok("...and so does the Voyage key", c.get("voyage_key") == "vk")
ok("the first company's team workspace does NOT follow: it is that company's team",
   not c.get("workspace_url"), c)

store.save_connections(dict(store.connections(), workspace_url="https://two.supabase.co",
                            voyage_key="vk2"))
own = store.read_json(store.connections_file(), {})
person = store.read_json(PERSON, {})
ok("a workspace joined here is written to this company's own file",
   own.get("workspace_url") == "https://two.supabase.co")
ok("...and a key changed here goes to the person's file, never copied into the company's",
   "voyage_key" not in own and person.get("voyage_key") == "vk2", (own, person))
ok("the company's own file holds no key at all",
   not any(k in own for k in store.PERSON_KEYS), own)

store.save_connections({"workspace_name": "Acme team"})
ok("a save that does not mention the keys never deletes them",
   store.read_json(PERSON, {}).get("dataforseo_login") == "me@example.com")
store.save_connections(dict(store.connections(), voyage_key=""))
ok("a key sent blank is cleared for the person, from whichever company",
   "voyage_key" not in store.read_json(PERSON, {}))
ok("both files stay owner-only",
   (os.stat(PERSON).st_mode & 0o777) == 0o600
   and (os.stat(store.connections_file()).st_mode & 0o777) == 0o600)

companies.switch(companies.FIRST)
ok("switching back puts every path back at the root", store.data_dir() == ROOT)
ok("...where the first company's brand is untouched",
   (store.knowledge("brand/company.json") or {}).get("brand") == "Testlify")
ok("...and its own team workspace is still its own",
   store.connections().get("workspace_url") == "https://one.supabase.co")
ok("...and the key cleared from the other company is gone here too: it is one person's key",
   not store.connections().get("voyage_key"))

# ==========================================================================================
print("\nTHE LIST, AND COMING BACK TO IT")
lst = companies.listing()
ok("two companies, in the order they were made, the first one open",
   [x["name"] for x in lst["companies"]] == ["Testlify", "Acme Hiring"]
   and lst["active"] == companies.FIRST, lst)
ok("each shows its own site, read from its own folder",
   [x["domain"] for x in lst["companies"]] == ["testlify.com", "acme.com"], lst)
companies.switch(acme["id"])
store.set_data_dir(None)                                   # the app restarts
ok("after a restart, the company that was open last is the one that opens",
   companies.activate_saved() == acme["id"] and store.data_dir() == companies.path_of(acme["id"]))
companies.switch(companies.FIRST)

refused("a blank name is refused", lambda: companies.add("   "), "name")
refused("a second company with the same name is refused", lambda: companies.add("acme hiring"),
        "already")
for bad in ("../../etc", "c1/../x", "UPPER", "a/b"):
    refused("an id that could reach outside the folder is refused: %r" % bad,
            lambda b=bad: companies.path_of(b))
refused("switching to a company that does not exist is refused",
        lambda: companies.switch("nope-0000"), "no such")
companies.rename(companies.FIRST, "Testlify Inc")
ok("a company can be renamed", companies.listing()["companies"][0]["name"] == "Testlify Inc")
refused("renaming onto another company's name is refused",
        lambda: companies.rename(acme["id"], "testlify inc"), "already")

# ==========================================================================================
print("\nTHE DOOR: the API switches only when nothing is running")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agents_api as api   # noqa: E402

out = api.api_companies()
ok("GET /companies lists both", len(out["companies"]) == 2, out)

gate = threading.Event()
t = threading.Thread(target=gate.wait, daemon=True)
t.start()
api._workers["run-in-flight"] = t
res = api.api_company_switch({"id": acme["id"]})
ok("a switch while a run is still going is refused", getattr(res, "status_code", 200) == 409, res)
ok("...and nothing moved", store.data_dir() == ROOT)
gate.set()
t.join(2)
api._workers.pop("run-in-flight", None)

res = api.api_company_switch({"id": acme["id"]})
ok("once it has finished, the switch goes through",
   store.data_dir() == companies.path_of(acme["id"]), res)
h = api.api_health()
ok("health says which company is open and how many there are",
   h["company"]["id"] == acme["id"] and h["company"]["name"] == "Acme Hiring"
   and h["companies"] == 2, (h.get("company"), h.get("companies")))

res = api.api_company_add({"name": "Third Co"})
added = (res or {}).get("added") or {}
ok("adding through the door switches straight to the new company",
   added.get("name") == "Third Co" and store.data_dir() == companies.path_of(added.get("id")), res)
res = api.api_company_add({"name": ""})
ok("...and a blank name comes back as a sentence, not a crash",
   getattr(res, "status_code", 200) == 400)
res = api.api_company_switch({"id": "../../"})
ok("a switch to nonsense is refused, not obeyed", getattr(res, "status_code", 200) >= 400)
companies.switch(companies.FIRST)
store.set_data_dir(None)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all company checks passed")
