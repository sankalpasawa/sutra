# Manual test plan — DeepSeek provider (key handling, sign-in, install, chat)

Covers everything shipped in 2.243.0 → 2.245.0. Written to be run by hand, top to
bottom, on a Mac. Each case is: **Setup → Steps → Expect → Verify**.

Source of truth for behaviour: `deepseek_auth.py`, `deepseek_session.py`,
`deepseek_install.py`, `providers.py` (§DeepSeek), `org_api.py:1057-1290`,
`app.py:1976-2345`, `acp_runtime.py`, `static/js/07-loaders.js:255-900`.

---

## 0. Environment reference — memorise these five paths

| Thing | Where | Command to inspect |
|---|---|---|
| The key itself | login keychain, service `com.sutra.provider`, account `deepseek:api-key` | `security find-generic-password -s com.sutra.provider -a deepseek:api-key` |
| Non-secret marker | `~/.sutra-ui/settings.json` → `deepseek_key: {mask, saved_at}` | `python3 -c "import json;print(json.load(open(__import__('os').path.expanduser('~/.sutra-ui/settings.json'))).get('deepseek_key'))"` |
| Env overrides (win over keychain) | `SUTRA_UI_DEEPSEEK_API_KEY`, then `DEEPSEEK_API_KEY` | `env \| grep -i deepseek` |
| CLI install prefix | `~/.sutra-ui/providers/deepseek` | `ls -la ~/.sutra-ui/providers/deepseek/bin 2>/dev/null` |
| Browser write token | tab `sessionStorage`, key `sutra.deepseek.session` | DevTools → Application → Session Storage |

**Reset-to-zero procedure** (run before any block marked *from clean*):

```
# 1. sign out of DeepSeek in the UI, OR nuke by hand:
security delete-generic-password -s com.sutra.provider -a deepseek:api-key 2>/dev/null
# 2. drop the marker
python3 - <<'PY'
import json,os
p=os.path.expanduser('~/.sutra-ui/settings.json')
d=json.load(open(p)); d.pop('deepseek_key',None)
json.dump(d,open(p,'w'),indent=2)
PY
# 3. unset overrides in the shell that will start the server
unset DEEPSEEK_API_KEY SUTRA_UI_DEEPSEEK_API_KEY
# 4. (only for install tests) remove the CLI
rm -rf ~/.sutra-ui/providers/deepseek
```

---

## 1. Storage & non-global-context proof (the security claim)

| # | Case | Expect |
|---|---|---|
| 1.1 | Key is in the keychain, not settings.json | plaintext file holds only `sk-****XXXX` |
| 1.2 | Key never in argv | `ps` shows no key |
| 1.3 | Key never in the server's own env | `os.environ` of the backend has no DeepSeek var |
| 1.4 | Key crosses only into the child CLI's env | child has it, parent does not |
| 1.5 | Key never in an API response | no route echoes it |
| 1.6 | No iCloud sync | keychain item is `ThisDeviceOnly` |

**1.1 — steps**
1. Sign in with a valid key (see 3 or 4).
2. `cat ~/.sutra-ui/settings.json | grep -A3 deepseek_key`
3. **Expect** `{"mask": "sk-****<last4>", "saved_at": <epoch float>}` and nothing else.
4. **Verify the negative:** `grep -c "<your full key>" ~/.sutra-ui/settings.json` → `0`.
5. `security find-generic-password -s com.sutra.provider -a deepseek:api-key` → item found,
   `svce` = `com.sutra.provider`, `acct` = `deepseek:api-key`.

**1.2 — steps**
1. With the key saved and a DeepSeek pane open, run `ps -Ewww | grep -i deepseek`.
2. **Expect** the `deepseek --acp` command line with **no** `sk-` string anywhere in it.
3. (Contrast case, to prove the test can fail: `security add-generic-password -w sk-test`
   would appear in `ps`; Sutra deliberately does not shell out that way.)

**1.3 — steps**
1. Find the backend pid: `pgrep -fl "sutra-ui\|app.py\|uvicorn"`.
2. `ps -Ewww -p <pid> | tr ' ' '\n' | grep -i deepseek`
3. **Expect** empty (unless *you* exported an override — that is case 5).

**1.4 — steps**
1. Open a DeepSeek pane and send one message so the CLI spawns.
2. `pgrep -fl "deepseek"` → note the child pid.
3. `ps -Ewww -p <child pid> | tr ' ' '\n' | grep DEEPSEEK_API_KEY`
4. **Expect** present on the **child**, absent on the **parent** from 1.3.
   This is `acp_runtime.py:515` — `env=dict(os.environ, **env)` builds a copy per spawn.

**1.5 — steps**
1. `curl -s localhost:<port>/api/settings | python3 -m json.tool | grep -i -A12 '"auth"'`
2. **Expect** `state`, `signed_in`, `env_var`, `env_vars`, `mask`, `saved_at`,
   `stored_mask`, `store_available`, `store_reason`, `browser_session`, `reason`.
3. **Expect NOT present:** the key, and the pairing **code** (`browser_session` is three
   booleans + a sentence).
4. `curl -s localhost:<port>/api/settings | grep -c "sk-[A-Za-z0-9]\{10,\}"` → `0`.

**1.6 — steps**
1. `security find-generic-password -s com.sutra.provider -a deepseek:api-key -g 2>&1 | grep -i accessible`
   (or dump attrs) — the item was written with
   `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`.
2. **Expect** the key does **not** appear on a second Mac signed into the same iCloud.
   (Practical check: Keychain Access → the item is under **login**, not **iCloud**.)

---

## 2. Env-override precedence (the one real "global context" path)

*From clean, plus a saved key for 2.3.*

| # | Setup | Steps | Expect |
|---|---|---|---|
| 2.1 | `export DEEPSEEK_API_KEY=sk-valid…` then start server | open Settings → AI Provider | row reads signed-in via **env**, names `DEEPSEEK_API_KEY`, shows its mask, **no** key field |
| 2.2 | both vars exported, different values | same | row names `SUTRA_UI_DEEPSEEK_API_KEY` (it wins) |
| 2.3 | env var set **and** a key already saved in keychain | try to save a new key | refusal `ENV_OVERRIDE`: "*<VAR> is set in this server's environment and wins over anything saved here … Unset it and restart the server first.*" Nothing written |
| 2.4 | `export DEEPSEEK_API_KEY="   "` (whitespace only) | start server, open row | treated as **absent** — falls through to keychain |
| 2.5 | `export DEEPSEEK_API_KEY="sk-x\n"` (trailing newline) | start server, send a message | key is `.strip()`ped and works — no unexplained 401 |
| 2.6 | env var set, then CLI install attempted | click Install | install refuses with `ENV_OVERRIDE` too |

**2.1 detailed**
1. `unset` both, run the reset. `export DEEPSEEK_API_KEY=<real key>`.
2. Start the server from that same shell.
3. Panel → Settings → AI Provider → DeepSeek row.
4. **Expect** "signed in" state = `env`, `env_var: "DEEPSEEK_API_KEY"`, mask computed
   from the value **without storing it** (`stored_mask` stays `null` if nothing was ever saved).
5. `cat ~/.sutra-ui/settings.json | grep deepseek_key` → absent. An env key writes no marker.

---

## 3. Sign-in lane 1 — desktop app (Electron bridge)

*Run in `/Applications/Sutra.app`, from clean.*

| # | Case | Expect |
|---|---|---|
| 3.1 | Valid key | saved; message `SAVED` or `SAVED_NO_CLI`; field clears |
| 3.2 | Key never crosses HTTP | main process attaches `x-sutra-desktop-token`; renderer never holds it |
| 3.3 | 20s cap | a hung validate returns a timeout message, not a spinner forever |
| 3.4 | Browser cannot use this lane | a plain browser on the same backend gets the code field / env text, not a dead key field |

**3.1 detailed**
1. Launch Sutra.app. Settings → AI Provider → DeepSeek.
2. **Expect** an API-key field is drawn (bridge present ⇒ `deepseekBridge()` non-null).
3. Paste a valid `sk-…` key. Click Save.
4. **Expect within ~8s** a green message, one of:
   - CLI already installed → "*DeepSeek accepted the key and it is saved on this Mac
     (sk-****xxxx). DeepSeek is selectable above now — no restart.*"
   - CLI missing → the same first sentence + "*DeepSeek is still not selectable above: …*"
     and then the install starts automatically (see 6).
5. **Expect** the key field is now **empty**.
6. **Verify** keychain item exists (0.reference) and settings.json holds only the mask.
7. **Verify** the provider dropdown above now offers DeepSeek **without a restart**.

**3.2 detailed**
1. DevTools on the renderer → Console → `window.sutra.deepseekKeySave` is a function.
2. Console → `Object.keys(window.sutra)` — **expect no token value** of any kind.
3. Network tab during a save → **expect zero** requests carrying the key from the renderer
   (the write goes over IPC → main → loopback).

**3.4 detailed**
1. With the desktop app running, open `http://127.0.0.1:<port>/panel` in Safari/Chrome.
2. **Expect** the DeepSeek row says saving is a desktop-app action, and **no pairing code
   was minted** (`deepseek_session.arm()` mints nothing when `SUTRA_DESKTOP_TOKEN` is set).
3. `curl -s localhost:<port>/api/settings | grep -A4 browser_session`
   → `available: false`, with a reason naming the desktop app.

---

## 4. Sign-in lane 2 — browser pairing code (CLI-started server)

*From clean. Start the backend from a terminal, not the app.*

| # | Case | Expect |
|---|---|---|
| 4.1 | Banner on stdout | ASCII box with the code, once, at startup |
| 4.2 | Correct code | `PAIRED`; key field opens; token in sessionStorage |
| 4.3 | Wrong code | 200 with `ok:false`, "That code was not accepted." — **not** a thrown fetch error |
| 4.4 | Empty code | client-side "Paste the code from the server's terminal output first." |
| 4.5 | Code reuse | second exchange refused; message says only a restart mints another |
| 4.6 | Second browser | cannot pair after the code is burned |
| 4.7 | Panel reload | pairing survives (sessionStorage) |
| 4.8 | New tab | does **not** inherit the token → code field again |
| 4.9 | Private window / storage blocked | "The code was accepted but this browser will not keep the token (private window?)…" |
| 4.10 | Server restart with a stale token | key save returns 403 → token dropped, message "this browser's sign-in has expired — the server was restarted. Paste its new code below." |
| 4.11 | Code never leaks | `/api/settings` reports existence only |
| 4.12 | Case/format tolerance | code accepted as displayed (grouped form) and canonicalised |

**4.1 detailed**
1. `unset` overrides, run reset, start the backend in a terminal.
2. **Expect** on stdout:
```
  +-- Sutra: DeepSeek sign-in code -------------------------------+
  |    XXXX-XXXX-XXXX                                            |
  |  Paste it into the DeepSeek row under                         |
  |  Settings -> AI Provider …  Single use. …                     |
  +--------------------------------------------------------------+
```
3. **Verify** `grep -r "<the code>" ~/.sutra-ui/ 2>/dev/null` → **no hits**. Never on disk.

**4.2 detailed**
1. Browser → panel → Settings → AI Provider → DeepSeek row.
2. **Expect** a **code** field (not a key field) plus the env-var text.
3. Paste the code, click the pair button.
4. **Expect** green: "*This browser can now save a DeepSeek key. The code is used up —
   restart the server if you need another.*"
5. **Expect** the code field cleared, and an API-key field now drawn.
6. DevTools → Session Storage → `sutra.deepseek.session` holds a token string.
7. Now do 3.1 steps 3-7 through this lane; **Verify** the request carries header
   `X-Sutra-Session-Token` and the body carries `key` (this is the one hop the key makes,
   over loopback).

**4.5 detailed**
1. After 4.2 succeeded, in a second tab clear storage and paste the **same** code.
2. **Expect** `ok:false`, a message distinguishing "already used, restart for another"
   from "wrong code". `browser_session.claimed` is `true`, `available` `false`.

**4.10 detailed**
1. Pair (4.2). Restart the backend. Do **not** reload the panel.
2. Click Save with a key.
3. **Expect** the expiry sentence above, the token removed from sessionStorage, and the
   row re-rendered with the **code** field (not a key field that could only 403).

**4.11 detailed**
1. `curl -s localhost:<port>/api/settings | python3 -m json.tool | grep -A5 browser_session`
2. **Expect** `{available, claimed, reason}` only. `grep` the whole response for the code
   string → `0` hits.

---

## 5. Key validation & refusals (`deepseek_auth.clean` + `validate`)

Run each through whichever lane you have. Every one is a **200 with `ok:false`** and a
plain-English sentence — never a 422, never the key echoed back.

| # | Input / condition | Code | Expected message (substring) | Post-state |
|---|---|---|---|---|
| 5.1 | empty / whitespace | `NO_KEY` | "no API key was given." | nothing stored |
| 5.2 | key with a space or newline **inside** | `BAD_PASTE` | "that does not look like one key — it has a space or a line break inside it." | nothing stored; **field keeps the text** |
| 5.3 | key longer than the cap | `TOO_LONG` | "that is too long to be an API key (N characters)." | nothing stored |
| 5.4 | trailing newline only | — | success | trimmed before storing |
| 5.5 | wrong/revoked key (401) | `KEY_REJECTED` | "DeepSeek rejected that key." | nothing stored |
| 5.6 | valid key, endpoint refused (403) | `KEY_REJECTED` | "…may be disabled or scoped away from this endpoint." | nothing stored |
| 5.7 | account out of credit (402) | `BILLING` | "reported a billing problem on that account. Top it up…" | nothing stored |
| 5.8 | rate-limited (429) | `RATE_LIMITED` | "rate-limited the check, so the key could not be confirmed." | nothing stored |
| 5.9 | network down | `NETWORK` | "could not reach api.deepseek.com to check the key (<ExcType>). Nothing was saved" | nothing stored |
| 5.10 | probe 404 | `PROBE_UNRECOGNISED` | "That is a Sutra problem, not a problem with your key." | nothing stored |
| 5.11 | any other HTTP | `HTTP` | "answered HTTP N, which this build does not know how to read." | nothing stored |

**How to force each**
- 5.2: paste `sk-abc def` or paste two keys at once.
- 5.5: mutate the last char of a real key.
- 5.9: turn Wi-Fi off, then Save. **Expect** the refusal names the exception *type* only —
  `grep` the message for your key → `0` hits.
- 5.7/5.8/5.10/5.11: block/redirect `api.deepseek.com` via `/etc/hosts` to a local stub
  returning the status, or use a key on a zero-balance account for 402.

**After every refusal, verify all three:**
```
security find-generic-password -s com.sutra.provider -a deepseek:api-key   # must NOT exist
grep deepseek_key ~/.sutra-ui/settings.json                                 # must be absent
```
and the provider row must still read *not signed in*. A refused key must never leave a
"signed in" row.

**5.12 — order of operations (important, easy to regress)**
1. Turn Wi-Fi **off** and lock/deny the keychain so `_store()` fails.
2. Save a key.
3. **Expect** the **keychain** refusal (`NO_KEYCHAIN`), *not* the network one — the store
   check runs **before** the network call, so a Mac that cannot store a key never sends it
   anywhere to find that out.

---

## 6. Keychain-unavailable and store-failure paths

| # | Setup | Expect |
|---|---|---|
| 6.1 | No keychain available (`store_status()` false) | Save is **refused** with why. No in-memory fallback — the row must never claim "signed in" with nothing behind it |
| 6.2 | Keychain write throws | `STORE_FAILED` "DeepSeek accepted the key but the login keychain would not store it (<ExcType>). Nothing was saved." Marker absent |
| 6.3 | Keychain delete throws on sign-out | `STORE_FAILED` "…so it is still there. Nothing was changed." Marker **kept** (item goes first, marker second) |
| 6.4 | Row rendering cost | drawing the row performs **zero** keychain reads |

**6.4 detailed**
1. Open Keychain Access → set the item to prompt on access (or watch for auth dialogs).
2. Reload the panel, browse the file tree, open a chat — anything that hits
   `load_settings()` / `fs/tree` / `fs/read` / `ws_chat` connect.
3. **Expect no keychain prompt.** The row renders from the settings **marker**
   (`providers._deepseek_key_present()`).
4. **Contrast:** actually sending a message *does* read the keychain
   (`deepseek_key_for_request()`), so a prompt there is correct.

---

## 7. Stale marker / keychain divergence (self-healing)

**7.1 — key deleted straight out of Keychain Access**
1. Sign in successfully. Confirm the row says signed in.
2. Keychain Access → delete the `com.sutra.provider` / `deepseek:api-key` item.
3. Reload the panel. **Expect** the row *still* says signed in — the marker is trusted for
   rendering. This is documented, not a bug.
4. Now **send a DeepSeek message** (or open the balance card).
5. **Expect** a refusal naming the divergence:
   "*a saved key was on record (sk-****xxxx) but the login keychain no longer holds it —
   the item at service 'com.sutra.provider', account 'deepseek:api-key' is gone or could
   not be read. That record has been cleared; sign in again to replace it.*"
6. **Expect** the marker is now **dropped**: `grep deepseek_key ~/.sutra-ui/settings.json`
   → absent, and the next paint of the row reads *not signed in*.
7. **Verify** it self-heals: sign in again → row correct.

**7.2 — marker hand-edited to garbage**
1. Set `"deepseek_key": {"mask": ""}` / `"deepseek_key": "nonsense"` in settings.json.
2. Reload. **Expect** treated as **no marker** (validated shape: dict with non-empty
   string `mask`), no crash, row reads not signed in.

---

## 8. Sign-out / remove

| # | Case | Expect |
|---|---|---|
| 8.1 | Remove with a key saved | confirm dialog first; then "The saved key is gone from the login keychain." |
| 8.2 | Remove with nothing saved | idempotent success: "There was no saved key on this Mac to remove." |
| 8.3 | Cancel the confirm | nothing happens, no request fired |
| 8.4 | Sign out **while DeepSeek is the active provider** | settings come back with `provider_ignored` and a fallback provider already chosen |
| 8.5 | Both artefacts gone | keychain item **and** marker removed |

**8.1 detailed**
1. Click Remove. **Expect** a `window.confirm` reading: "*Remove the saved DeepSeek key?
   It is deleted from your login keychain and Sutra keeps no copy, so you will need the key
   itself to sign in again. DeepSeek stops being selectable until you do.*"
2. Confirm. **Verify** both:
   `security find-generic-password -s com.sutra.provider -a deepseek:api-key` → not found;
   `grep deepseek_key ~/.sutra-ui/settings.json` → absent.
3. **Expect** the provider list above re-renders in the **same paint** — no reload.

**8.4 detailed**
1. Select DeepSeek as the provider. Confirm a pane answers.
2. Sign out.
3. **Expect** the provider selector has already fallen back (Claude), and the response
   carried `settings.provider_ignored` explaining DeepSeek stopped being runnable.
4. Open a new pane. **Expect** it boots on the fallback, **not** a dead DeepSeek spawn.

---

## 9. CLI install — the other half of a usable DeepSeek

*From clean, with `rm -rf ~/.sutra-ui/providers/deepseek`.*

| # | Case | Expect |
|---|---|---|
| 9.1 | Save a valid key on a Mac with no CLI | `SAVED_NO_CLI`, then the install starts **automatically** |
| 9.2 | The message is honest | it does **not** say "selectable now — no restart"; it quotes the row's own reason |
| 9.3 | Install button (key saved weeks ago) | same install, no second key write |
| 9.4 | Progress + lockout | field and both buttons disabled for the whole download |
| 9.5 | Double-fire | second call **waits**, then answers `ALREADY` — npm is not unpacked twice |
| 9.6 | Client dies mid-save | install still completes (server-side daemon thread) |
| 9.7 | Old app binary | "Update the Sutra app to install the DeepSeek CLI from here." — and **no** npm command, package name, or `node_modules` in any user-facing string |
| 9.8 | No npm | `NO_NPM` with its reason |
| 9.9 | Prefix not writable | `NO_DIRECTORY` |
| 9.10 | Timeout (>300s) | `TIMEOUT`; row still reads not installed; button still there |
| 9.11 | npm fails | `NPM_FAILED` with the real cause |
| 9.12 | Binary missing after install | `NO_BINARY` |
| 9.13 | Register step fails | `REGISTER_FAILED` |
| 9.14 | Bundled Node | works on a Mac with **no** Node of its own |

**9.1 detailed**
1. `rm -rf ~/.sutra-ui/providers/deepseek`; ensure `which deepseek` is empty.
2. Save a valid key.
3. **Expect** the key message first, then it is **replaced** by:
   "*Installing the DeepSeek CLI — this takes a minute. It goes into Sutra's own folder;
   nothing else on your Mac changes.*"
4. **Expect** within ~1-5 min: "The DeepSeek CLI is installed." (or a named failure).
5. **Verify** `ls ~/.sutra-ui/providers/deepseek/bin` → a `deepseek` executable.
6. **Verify** the provider row above flips to installed/selectable **without a restart**.

**9.6 detailed**
1. Save a valid key on a CLI-less Mac and **immediately close the window / reload the page**.
2. Wait 2 minutes. Reopen the panel.
3. **Expect** the CLI is installed anyway (`_deepseek_kick_install()` runs server-side).

**9.14 detailed**
1. On a Mac with no Node on PATH (`which node` empty), or temporarily
   `PATH=/usr/bin:/bin` for the server.
2. Save a key, let the install run, then open a DeepSeek pane and send a message.
3. **Expect** it answers. **Expect NOT** `env: node: No such file or directory`
   (`providers.ensure_bundled_node_path()` runs before every spawn).

---

## 10. Chat path — ACP auth, the Gemini-error regression, spawn

| # | Case | Expect |
|---|---|---|
| 10.1 | DeepSeek selected, no key | connect-time refusal naming all three key sources — **not** a dead socket |
| 10.2 | DeepSeek selected, key + CLI | pane answers |
| 10.3 | **Regression 2.244.1** — machine that never ran the fork interactively | **no** "Gemini API key is missing or not configured." |
| 10.4 | Rejected key at ACP `authenticate` | RuntimeError surfaced as itself; must **not** fall through to `session/new` |
| 10.5 | Session resume | `session/load` with a live id resumes |
| 10.6 | Dead session id | falls back to a fresh session, turn does not fail |
| 10.7 | Permission mode | set via `session/new` mode, not a flag |
| 10.8 | Shadow / delegate spawns | do **not** run `deepseek -p --input-format stream-json` |

**10.1 detailed**
1. From clean (no key, no env var), select DeepSeek, open a pane, send a message.
2. **Expect** a refusal at **connect** time, in text, naming: `SUTRA_UI_DEEPSEEK_API_KEY`,
   `DEEPSEEK_API_KEY`, and the login keychain, and what was found at each.
3. **Expect NOT** a spinner, a closed WebSocket with no message, or a raw traceback.

**10.3 detailed**
1. Fresh Mac (or `rm -rf ~/.gemini`) so no `security.auth.selectedType` was ever written.
2. Save a valid DeepSeek key, install the CLI, select DeepSeek, send a message.
3. **Expect** a normal answer.
4. **Expect NOT** `session/new failed: {'code': -32000, 'message': 'Gemini API key is
   missing or not configured.'}` — the fix is the `authenticate` call with
   `methodId: "deepseek-api-key"` before `session/new`.
5. **Verify** `~/.gemini` was **not** relocated (`GEMINI_CLI_HOME` untouched) — old
   transcripts under `~/.gemini/tmp/<project>/chats` still resolve, so `session/load`
   of an older session still works.

**10.4 detailed**
1. Put a syntactically valid but revoked key in `DEEPSEEK_API_KEY` (bypasses save-time
   validation), restart the server, send a message.
2. **Expect** an ACP authenticate failure surfaced with its own text.
3. **Expect NOT** the Gemini sentence from 10.3.

---

## 11. Balance / usage card

| # | Case | Expect |
|---|---|---|
| 11.1 | Signed in, funded account | balance renders |
| 11.2 | No key | the **same sentence** the chat refusal shows (one resolver, one message) |
| 11.3 | Stale marker | the divergence sentence from 7.1, and the marker is cleared |
| 11.4 | Cache | repeated opens do not re-hit the API within the cache window |
| 11.5 | Key never in the payload | `grep` the response for `sk-` → `0` |

**11.2 detailed** — open the balance card and the chat refusal side by side; the sentence
must be **identical**. Divergence here means someone re-implemented the resolver.

---

## 12. Leak sweep (run last, once, with a key saved and a pane used)

```
K='<your full key>'
# 1. nothing on disk under Sutra's own state
grep -rl "$K" ~/.sutra-ui/ 2>/dev/null            # expect: no output
# 2. nothing in the app's logs
grep -rl "$K" ~/Library/Logs/ 2>/dev/null | head  # expect: no output
# 3. nothing in the gemini fork's state / transcripts
grep -rl "$K" ~/.gemini/ 2>/dev/null              # expect: no output
# 4. nothing in any unauthenticated route
for p in /api/settings /api/state /api/balance /api/activity /api/sessions; do
  echo "== $p"; curl -s "localhost:<port>$p" | grep -c "$K"; done   # expect: 0 each
# 5. nothing in the shell history you just typed into (yours to clean)
```
Also check, by eye, the terminal the backend runs in: **expect no `sk-` string** in any
startup line, request log, or traceback, including during the failure cases of §5.

**12.6 — exception text**
1. Force `STORE_FAILED` (deny keychain write) and `NETWORK` (Wi-Fi off).
2. **Expect** each message names an **exception type** (`OSError`, `URLError`) and never
   quotes the key, the request, or the Authorization header.

---

## 13. Persistence & restart

| # | Case | Expect |
|---|---|---|
| 13.1 | Restart the backend with a saved key | still signed in, no re-entry |
| 13.2 | Restart with a pairing token held by a tab | token is dead → 403 → code field (see 4.10) |
| 13.3 | Reboot the Mac | key survives (keychain), pairing does not (by design) |
| 13.4 | Restart the desktop app | signed in; a **new** desktop token is minted and works |
| 13.5 | Delete `~/.sutra-ui/settings.json` entirely | row reads not signed in even though the keychain still holds a key; signing in again overwrites cleanly |

**13.5 note** — this is the inverse of 7.1: marker gone, key present. The row trusts the
marker, so it reads not-signed-in. Saving again rewrites both. Verify no duplicate keychain
items accumulate (`security dump-keychain | grep -c com.sutra.provider` stays at 1 item).

---

## 14. Cross-lane and negative-authorisation cases

| # | Case | Expect |
|---|---|---|
| 14.1 | `curl -X POST /api/providers/deepseek/key` with **no** token | 403, and the refusal says **which lane is even possible** on this server (desktop-started / paired-once / paste-the-code) |
| 14.2 | Same with a **wrong** token | 403; comparison is constant-time (`hmac.compare_digest`) |
| 14.3 | Same for `/key/remove` and `/cli` | **all three** gated identically |
| 14.4 | Cross-origin POST from another page, no `PANEL_TOKEN` | refused by the origin guard |
| 14.5 | `/providers/deepseek/session` is ungated | by design — it hands out the credential; protected by the 80-bit stdout code + origin guard |
| 14.6 | Desktop-started server | mints **no** pairing code; lane 2 unavailable; posture unchanged |
| 14.7 | Update routes | still `_desktop_control()` only — a session token must **not** authorise an app update |

**14.1 command**
```
curl -si -X POST localhost:<port>/api/providers/deepseek/key \
  -H 'Content-Type: application/json' -d '{"key":"sk-whatever"}'
```
**Expect** 403 with a lane-specific sentence. **Expect** nothing written.

**14.7 detailed** — try an update route with `X-Sutra-Session-Token`. **Expect** refused.
Signing a key into your own keychain and replacing `/Applications/Sutra.app` must not share
a gate.

---

## 15. Quick smoke sequence (10 minutes, if you only run one thing)

1. Reset to zero (§0).
2. Start backend from a terminal → **see the code banner** (4.1).
3. Pair in the browser (4.2) → key field opens.
4. Save a **bad** key → refusal, field keeps the text, nothing stored (5.5).
5. Save a **good** key → saved; install chains automatically (9.1).
6. `cat ~/.sutra-ui/settings.json` → **mask only** (1.1).
7. Send a DeepSeek message → answers; **no Gemini error** (10.3).
8. `ps -Ewww` → key on the child, **not** on the backend, **not** in argv (1.2-1.4).
9. `curl /api/settings | grep -c sk-` → `0` (1.5).
10. Sign out → both artefacts gone, provider falls back in the same paint (8.1, 8.4).

---

### Structure note (D55 Clause 2)
New file. Survey: no existing manual-test doc in `sutra-ui/` — the tests here are the
**hand** counterpart to the automated `test_deepseek_auth.py` / `test_deepseek_usage.py` /
`test_deepseek_install.py` / `test_deepseek_session.py` / `test_panel.js`, which cover the
same surface programmatically. Nothing merged or deleted; no other doc duplicated this.
