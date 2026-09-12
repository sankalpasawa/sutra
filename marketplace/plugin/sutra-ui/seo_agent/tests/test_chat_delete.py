"""Deleting a chat: it goes, nothing else does.

Owner asked for it on 2026-09-10 ("3 dots and delete the chat"). The two things that make a
delete dangerous are both checked here: a chat id that climbs out of the chats folder, and the
Library, which holds finished articles and must survive the conversation they were written in.
"""
import os
import shutil
import sys

from seo_agent.tests import _fixture   # noqa: F401  (points SEO_AGENT_DATA at a temp dir)

from seo_agent import store

FAILS = []


def ok(label, cond):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAILS.append(label)


c = store.new_chat("throwaway")
r = store.new_run(c, "cost per hire")
store.save_artifact(c, r, "draft.md", "# hello")
d = store.chat_dir(c)
ok("the chat and its run are on disk", os.path.isdir(os.path.join(d, "runs", r)))

store.library_save(c, r, "An article worth keeping", "# body")

ok("delete_chat reports that it removed it", store.delete_chat(c) is True)
ok("the folder is gone", not os.path.isdir(d))
ok("and it is out of the chat list", all(x["id"] != c for x in store.list_chats()))
ok("deleting the same chat twice is a quiet False, never a crash", store.delete_chat(c) is False)
ok("a chat that never existed is False", store.delete_chat("c-nope1234") is False)

# THE GUARD THAT MATTERS. `chat_dir` is chats/<id>, so an id of ".." resolves to the data dir
# itself and an rmtree there takes Knowledge, the Library and every other chat with it.
victim = os.path.join(store.knowledge_dir())
os.makedirs(victim, exist_ok=True)
keep = os.path.join(victim, "site_index.json")
with open(keep, "w") as f:
    f.write("{}")
for bad in ("..", "../knowledge", "../../", "a/../../knowledge", "./.."):
    store.delete_chat(bad)
ok("a chat id that climbs out of the chats folder deletes nothing at all", os.path.isfile(keep))

rows = store.library_list()
ok("the article it wrote is still in the Library",
   any(x.get("title") == "An article worth keeping" for x in rows))

# A CHAT WHOSE RUN SAYS "running" MUST STILL BE DELETABLE. The API used to refuse one, which is
# right while a thread really is writing, and a trap once the thread has gone: the state file
# still says "running" and nothing will ever change it. Three chats a test left in the owner's
# live data were undeletable for exactly this reason (2026-09-12). The route now stops the run,
# waits for any worker of that chat, and deletes.
print("\na chat left stuck on 'running' can still be deleted")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agents_api as api   # noqa: E402

stuck = store.new_chat("left running by a dead process")
sr = store.new_run(stuck, "bp")
ok("its run says running", store.get_state(stuck, sr).get("status") == "running")
res = api.api_delete_chat(stuck)
if (res or {}).get("ok") is not True:
    print("    (the route answered: %r)" % (res,))
ok("the delete goes through instead of being refused", (res or {}).get("ok") is True)
ok("the folder is gone", not os.path.isdir(store.chat_dir(stuck)))
ok("and the run was recorded as stopped, not left hanging",
   all(x["id"] != stuck for x in store.list_chats()))

print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all chat-delete checks passed")
