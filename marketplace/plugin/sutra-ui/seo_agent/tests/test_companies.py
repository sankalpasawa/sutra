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

# ==========================================================================================
# THE PIN MUST NEVER OUTRANK A LATER SEO_AGENT_DATA. agents_api calls activate_saved() at
# import and pins the data dir to whichever company the person had open. Every test module
# sets SEO_AGENT_DATA at ITS import, and pytest imports modules in alphabetical order, so a
# module importing agents_api first (test_activity.py) pinned the dir to the owner's LIVE
# company and every later module wrote there: on 2026-09-12 a whole-suite run put four chats
# and two never-finished runs into his real Dharmik data. Nothing in the app changes the
# variable mid-process, so this costs production nothing.
# ==========================================================================================
# DELETING A COMPANY. Owner, 2026-09-12: "delete everything about that particular brand
# completely, so it goes away." The first company is the root, which also holds the person's
# keys, the registry and every other company's folder, so it is the dangerous one.
print("\nDELETING A COMPANY takes its data and nothing of the person's")
store.set_data_dir(None)
companies.switch(companies.FIRST)
gone = companies.add("Doomed Co")
companies.switch(gone["id"])
store.new_chat("will not survive")
gone_dir = companies.path_of(gone["id"])
ok("it has a folder of its own", os.path.isdir(gone_dir))

res = api.api_company_delete(gone["id"])
ok("the API deletes it", (res or {}).get("deleted") == gone["id"], res)
ok("the folder is gone", not os.path.isdir(gone_dir))
ok("it is out of the list", all(c["id"] != gone["id"] for c in companies.listing()["companies"]))
ok("and the open company moved to a real one", os.path.isdir(store.data_dir()))
res = api.api_company_delete("no-such-co")
ok("deleting a company that does not exist is a 404, not a crash",
   getattr(res, "status_code", 200) == 404)

# the first company: its data goes, the person's keys and the registry stay
companies.switch(companies.FIRST)
store.save_connections({"dataforseo_login": "keep-me", "supabase_url": "company-only"})
store.new_chat("first company chat")
os.makedirs(store.knowledge_dir(), exist_ok=True)
with open(os.path.join(store.knowledge_dir(), "site_index.json"), "w") as f:
    f.write("{}")
other = companies.add("Survivor Co")
# index_site leaves knowledge-backup-<n> beside the knowledge folder, and it is as much "this
# brand's data" as the folder it was copied from: 146 MB of one sat in the owner's root while
# the first pass of this delete removed only the names it knew. (verification run, 2026-09-12)
os.makedirs(os.path.join(ROOT, "knowledge-backup-400"), exist_ok=True)
with open(os.path.join(ROOT, "knowledge-backup-400", "site_index.json"), "w") as f:
    f.write("{}")
res = api.api_company_delete(companies.FIRST)
ok("the first company can be deleted too", (res or {}).get("deleted") == companies.FIRST, res)
ok("its knowledge is gone", not os.path.isdir(os.path.join(ROOT, "knowledge")))
ok("and the knowledge backup beside it went too",
   not os.path.isdir(os.path.join(ROOT, "knowledge-backup-400")))
ok("its chats are gone", not os.path.isdir(os.path.join(ROOT, "chats")))
ok("the root itself survives, because everything else lives in it", os.path.isdir(ROOT))
ok("the person's DataForSEO login survives",
   (store.read_json(os.path.join(ROOT, "connections.json"), {}) or {}).get("dataforseo_login")
   == "keep-me")
ok("the company's own key went with it",
   "supabase_url" not in (store.read_json(os.path.join(ROOT, "connections.json"), {}) or {}))
ok("the other company's folder is untouched", os.path.isdir(companies.path_of(other["id"])))
ok("the deleted first company does not come back on the next read",
   all(c["id"] != companies.FIRST for c in companies.listing()["companies"]),
   companies.listing())
# down to one, whatever the sections above left behind: deleting the last one would leave the
# person with no company to switch to, so it is refused rather than emptying everything.
for row in list(companies.listing()["companies"])[1:]:
    companies.remove(row["id"])
last = companies.listing()["companies"]
ok("...and the deletes above leave exactly one company standing", len(last) == 1, last)
refused("the last company standing cannot be deleted",
        lambda: companies.remove(last[0]["id"]), "only company")

print("\nA LATER SEO_AGENT_DATA BEATS AN EARLIER PIN (tests never write to live data)")
_env_before = os.environ.get("SEO_AGENT_DATA", "")
_pinned = companies.path_of(companies.FIRST)
store.set_data_dir(_pinned)
ok("the pin holds while the environment is unchanged", store.data_dir() == _pinned)
_later = os.path.join(ROOT, "a-later-temp-home")
os.environ["SEO_AGENT_DATA"] = _later
ok("a test repointing SEO_AGENT_DATA wins over the pin",
   store.data_dir() == os.path.abspath(_later), store.data_dir())
ok("...and the root follows it too", store.root_dir() == os.path.abspath(_later))
os.environ["SEO_AGENT_DATA"] = _env_before
store.set_data_dir(None)
ok("putting the environment back restores the old root", store.data_dir() == ROOT)

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all company checks passed")
