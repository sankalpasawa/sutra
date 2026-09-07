/* qa-shell/deepseek-cli-check.mjs — LANE 1 (L3) for "a key installs the CLI".
 *
 * THE BUG THIS LANE WATCHES (founder screenshot, 2026-09-07). Entering a
 * DeepSeek key produced "saved on this Mac" directly beneath a row reading
 * "Not installed on this Mac", with no control anywhere on the screen that
 * could fix it. L1/L2 (test_provider_switch.js, test_deepseek_install.py)
 * assert the logic and the markup; this asserts the same behaviour is REACHABLE
 * IN THE SHIPPED SHELL -- the bridge verb exists on the real preload, the route
 * answers through the real desktop gate, and the real renderer draws the
 * control when the real row says the CLI is missing.
 *
 * DEPENDENCY-FREE, like nav-check.mjs: raw CDP over Node's built-in WebSocket.
 * shell-check.mjs's playwright is not installed on every machine that has to
 * run this gate, and installing a browser stack to assert four strings would
 * be a worse trade than writing the twenty lines of protocol.
 *
 * IT DOWNLOADS NOTHING ON THE FOUNDER'S MAC. The install verb IS invoked --
 * that is the point, it proves the route and its gate -- but this machine
 * already has `deepseek` on PATH, so the backend answers ALREADY and fetches
 * nothing. That is itself the assertion: an install must never re-download
 * over a working CLI. The DOWNLOAD path is proven separately against a
 * deliberately CLI-less backend on a side port, because faking "no CLI" inside
 * the founder's live app would mean writing to their real settings.
 *
 * THE RENDERER IS EXERCISED BY ASKING THE APP, NOT BY LOOKING AT IT. PROVIDERS
 * and SETTINGS are swapped for the screenshot's state, the app's OWN
 * deepseekAuthHtml() is called, and the originals are restored in the same
 * evaluate() -- so nothing persists and no state the founder can see moves.
 *
 * Run through run.sh, which owns the debug-mode relaunch and the restore.
 */
const PORT = process.env.SHELL_DEBUG_PORT || "9223";

/* The CDP port answers before the shell's PAGE target exists (nav-check.mjs
   lost that race on 2026-08-24). Poll for the target. */
let page = null;
for (let i = 0; i < 40 && !page; i++){
  try {
    const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = targets.find(t => t.type === "page" && /127\.0\.0\.1:8330/.test(t.url || ""));
  } catch {}
  if (!page) await new Promise(r => setTimeout(r, 500));
}
if (!page){ console.error("no shell page target on CDP after 20s"); process.exit(1); }
console.log("attached to shell page: " + page.url);

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let seq = 0; const pend = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); } };
const cdp = (method, params={}) => new Promise((res, rej) => {
  const id = ++seq; pend.set(id, m => m.error ? rej(new Error(method+": "+JSON.stringify(m.error))) : res(m.result));
  ws.send(JSON.stringify({ id, method, params }));
});
async function evql(expr){
  const r = await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval failed");
  return r.result.value;
}

let passed = 0, failed = 0;
const check = (name, ok, detail = "") => {
  if (ok){ passed++; console.log("ok   - " + name); }
  else   { failed++; console.log("FAIL - " + name + (detail ? "\n       " + detail : "")); }
};

console.log("\nLANE 1 · state (the app testifies about itself)");

/* boot() fills PROVIDERS only after /api/settings answers. */
for (let i = 0; i < 40; i++){
  if (await evql(`typeof PROVIDERS !== "undefined" && !!PROVIDERS && PROVIDERS.length > 0`)) break;
  await new Promise(r => setTimeout(r, 250));
}

/* ── the surface exists in the REAL shell ─────────────────────────────────── */
const surface = await evql(`(() => ({
  hasBridge:  !!(window.sutra && window.sutra.deepseekKeySave),
  hasInstall: !!(window.sutra && window.sutra.deepseekCliInstall),
  renderer:   typeof deepseekAuthHtml === "function",
  row:        (typeof PROVIDERS !== "undefined" && PROVIDERS || []).find(p => p.id === "deepseek") || null,
  auth:       (typeof SETTINGS !== "undefined" && SETTINGS) ? (SETTINGS.deepseek_auth || {}).state : null,
}))()`);

/* THE BUNDLE IS FROZEN AND THE PANEL IS NOT. Since 2.117.0 the installed app
   runs its own payload for main.js/preload.js and never reads the staged copy
   (PUBLISH-CHECK "Bundled builds"), while the PANEL is served by whichever
   backend is on 8330 -- so under QA_BACKEND=repo the renderer under test is
   repo code and the bridge under test is whatever the last DMG shipped. This
   lane therefore has two legitimate outcomes, and asserts BOTH rather than
   failing on a machine whose app predates the verb. */
const rebuilt = surface.hasInstall;
console.log(rebuilt
  ? "       shell: carries deepseekCliInstall (rebuilt bundle)"
  : "       shell: bundle predates deepseekCliInstall — asserting the "
    + "degradation path instead (rebuild the DMG to exercise the bridge)");

check("the DeepSeek key bridge is still there", surface.hasBridge);
check("the sign-in renderer is a real global", surface.renderer);
check("the backend still sends a deepseek row", !!surface.row);
console.log("       row: installed=" + (surface.row && surface.row.installed)
            + " runnable=" + (surface.row && surface.row.runnable)
            + "  ·  key state: " + surface.auth);

/* ── the renderer draws the control exactly when the CLI is missing ───────── */
const rendered = await evql(`(() => {
  const realP = PROVIDERS, realS = SETTINGS;
  const swap = (installed) => {
    PROVIDERS = (realP || []).map(p => p.id === "deepseek"
      ? Object.assign({}, p, { installed: installed,
          bin_path: installed ? "/usr/local/bin/deepseek" : null,
          runnable: installed && p.configured })
      : p);
    /* The install block lives in the SIGNED-IN state -- the state the
       screenshot was taken in. Force it for the call, then restore. */
    const st = (realS && realS.deepseek_auth) || {};
    SETTINGS = Object.assign({}, realS, { deepseek_auth: Object.assign({}, st,
      { state: "stored", signed_in: true, mask: "sk-****0f2b" }) });
    return deepseekAuthHtml();
  };
  let missing = "", present = "";
  try { missing = swap(false); present = swap(true); }
  finally { PROVIDERS = realP; SETTINGS = realS; }
  return {
    missingHasButton: /data-deepseek="install"/.test(missing),
    presentHasButton: /data-deepseek="install"/.test(present),
    missingSaysNotHere: /not on this Mac yet/.test(missing),
    stillSaysSaved: /saved on this Mac/.test(missing),
    leaks: ["npm", "node_modules", "sluisr", "--prefix"].filter(w => missing.indexOf(w) >= 0),
  };
})()`);

check("a missing CLI draws the install control", rendered.missingHasButton,
      "the signed-in block renders no install button — that is the screenshot "
      + "state with no way forward, exactly as reported");
check("the block says what is missing, in a user's words", rendered.missingSaysNotHere);
check("the saved key is still reported as saved", rendered.stillSaysSaved,
      "burying the successful key write would send the operator back to re-paste "
      + "a key that is already in the keychain");
check("an installed CLI draws no install control", !rendered.presentHasButton,
      "the block offers to install over a working CLI");
check("the install copy names no internals", rendered.leaks.length === 0,
      "leaked: " + rendered.leaks.join(", "));

/* ── the route, or the honest refusal when the bundle predates it ─────────── */
const installed = await evql(`(async () => {
  try {
    if (!(window.sutra && window.sutra.deepseekCliInstall)) return { absent:true };
    return await window.sutra.deepseekCliInstall();
  } catch (e) { return { ok:false, threw: String((e && e.message) || e) }; }
})()`);

if (rebuilt) {
  console.log("       install verb: ok=" + installed.ok + " code=" + installed.code
              + (installed.threw ? " threw=" + installed.threw : ""));
  console.log("       message: " + String(installed.message || "").slice(0, 140));
  check("the install verb reaches the backend and is authorised", !!installed.ok,
        "the route refused the desktop bridge: " + (installed.message || installed.threw));
  check("nothing is re-downloaded over a working CLI", installed.code === "ALREADY",
        "expected ALREADY on a Mac that already has the CLI, got " + installed.code);
  check("the answer carries the state the row redraws from",
        Array.isArray(installed.providers) && !!installed.settings,
        "no providers/settings in the response — the panel would need a second "
        + "request and could render a stale row for a paint");
} else {
  /* THE PATH THE FOUNDER'S CURRENT APP TAKES. An older bundle must not produce
     a TypeError rendered as "the install did not come back" -- that sends them
     to their network for a problem that is a stale app. The panel's own
     handler is driven here, not re-implemented. */
  check("an older bundle is detected, not called blindly", !!installed.absent);
  const degraded = await evql(`(async () => {
    const realBusy = S.deepseekBusy, realMsg = S.deepseekMsg, realOk = S.deepseekMsgOk;
    let out = null;
    try { await deepseekInstallCli(); out = { msg: S.deepseekMsg, ok: S.deepseekMsgOk, busy: S.deepseekBusy }; }
    catch (e) { out = { threw: String((e && e.message) || e) }; }
    finally { S.deepseekBusy = realBusy; S.deepseekMsg = realMsg; S.deepseekMsgOk = realOk; }
    return out;
  })()`);
  console.log("       degraded message: " + String(degraded.msg || degraded.threw || "").slice(0, 160));
  check("the panel degrades instead of throwing", !degraded.threw, degraded.threw || "");
  check("it names the real fix, in one sentence, with no internals",
        /update the sutra app/i.test(degraded.msg || "")
        && !/npm|sluisr|node_modules/.test(degraded.msg || "")
        && ((degraded.msg || "").match(/\./g) || []).length === 1,
        "got: " + (degraded.msg || ""));
  check("it does not claim a success", degraded.ok === false);
  check("it leaves nothing stuck in a busy state", !degraded.busy);
}

/* ── DETACH — the one hard rule ────────────────────────────────────────────── */
/* No close() of the target. Dropping the socket is a normal CDP event. */
try { ws.close(); } catch {}

console.log("\n" + passed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
