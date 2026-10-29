/* 25-j2view.js -- the department as the J2 prototype's own page (UI-port package j2ui-shell).

   Owner, 2026-10-26: "Take latest pull from J2 prototype and implement UI in the exact same fashion, no change."
   Every department on the engine runtime whose kind is in the Library opens on that page (A5.1: website, default, organic, root
   and any Library kind; the page's words are kind-neutral, j2ui_words.py), served by j2ui_page.py at /j2ui/<ref>/ and fed by the
   adapter (j2ui_api.py), in ONE same-origin iframe under a slim bar of this app's own: the department's On/Off switch and
   `Settings and records`. The page is never edited here; this file only holds the frame and the bar.

   Hooks (each guarded by typeof where it is called, so a test that does not load this file is untouched):
     19-org2.js  o2ScreenHtml   the body is j2vHtml(n) and there is no list column while j2vOn(ref)
                 wireOrg2       j2vAfterPaint lays the frame over its placeholder after every paint
     22-website.js wbTab        j2vTab(ref) folds Chat, Map, All five, Board, Agent activity and System status into the
                                page, so every link that used to open one of them lands on it, and answers `records`
                 wbViewer       the records tab: j2vRecordsHtml
                 wbList         in records mode the first group is one `Department view` row (j2vTop)

   Settings and records is the classic list and its panes (a function's Settings with its instructions, an engine, filed
   work, People, Human Sutra), so nothing the page has no screen for is lost. Only a department of the first build, a ref the map
   does not know, or one on its Settings and records tab (the stored tab `records`, the escape hatch) keeps the classic screens. The
   organisation row keeps Root's classic chat (J2_ROOT_DEFAULT = false); Root's page is one click away from it.
   `?j2view=off` in the address turns the page off everywhere (kept in localStorage through lsSet); `?j2view=on` back on.

   Copy discipline is 20-dept.js's: names, no counts at rest, no colour literal (every colour a panel.css token). */

const J2V_KEY = "sutra.j2view";
const J2V_TABS = ["j2", "chat", "map", "five", "board", "activity", "status"];
const J2V_FRAME = { key: null, el: null, host: null, observed: false };
/* Root's page is not the default of the organisation row until a real Setup conversation has been walked in the page
   (A5.1.7); flipping this one constant makes it so. Until then Root's page opens from its chat (tab `j2`). */
const J2_ROOT_DEFAULT = false;

function j2vS(){
  if (!S.j2v) S.j2v = { on: undefined };
  return S.j2v;
}
/* On unless the address says `j2view=off` or an earlier visit did. Read once; the one writer is lsSet (01-state.js), which
   the chat-only frame refuses (test_embed.js). */
function j2vEnabled(){
  const st = j2vS();
  if (st.on !== undefined) return st.on;
  st.on = true;
  try {
    const q = (typeof location !== "undefined" && location.search) || "";
    const m = /[?&]j2view=(on|off)\b/.exec(q);
    if (m){ st.on = m[1] === "on"; if (typeof lsSet === "function") lsSet(J2V_KEY, m[1]); }
    else if (typeof localStorage !== "undefined" && JSON.parse(localStorage.getItem(J2V_KEY) || "null") === "off") st.on = false;
  } catch (e) { st.on = true; }
  return st.on;
}
/* The scope: the server's word. /api/native/<ref>/map says `j2: true` for a department of the engine runtime whose kind is in the
   Library (j2ui_common.need); this file holds no kind list. */
function j2vEligible(ref){
  const m = (typeof wbS === "function" && ref) ? wbS().map[ref] : null;
  return !!(m && m.j2 === true);
}
/* Does the stored tab leave the department on the page? Nothing chosen yet, or one of the six that the page folds. A Root keeps its
   own chat unless it was sent to the page (tab `j2`) or J2_ROOT_DEFAULT says the page is its default. */
function j2vWants(ref){
  const t = wbS().tab[ref], m = wbS().map[ref];
  if (m && m.kind === "root") return t === "j2" || (t === undefined && J2_ROOT_DEFAULT);
  return t === undefined || J2V_TABS.indexOf(t) >= 0;
}
function j2vOn(ref){
  return j2vEnabled() && j2vEligible(ref) && j2vWants(ref);
}
/* What wbTab answers for this department: `j2` for the page, `records` for Settings and records, null to let wbTab answer
   as it always did (any other tab is the classic screen's own: an engine, a filed work, Human Sutra, a function's pane). */
function j2vTab(ref){
  if (!j2vEnabled() || !j2vEligible(ref)) return null;
  if (j2vWants(ref)) return "j2";
  return wbS().tab[ref] === "records" ? "records" : null;
}

/* ── the viewer: the bar, and the place the page's frame is laid over ─────────────────────────────────────────────── */
function j2vHtml(n){
  const m = wbS().map[n.ref];
  wbTick();
  /* the list column is not painted, so the department is opened here, as wbOrgHtml does for Root */
  if (typeof dpSelect === "function" && dpS().sel !== n.ref) dpSelect(n.ref);
  const root = !!(m && m.kind === "root");           /* a Root has its chat to go back to; its records are the classic Root pane */
  return `<div class="o2viewer j2v wb"><div class="j2vbar">${m ? wbOnOff(m) : ""}` +
    (root ? wbBtn("Back to the chat", `data-wbtab="chat"`) : wbBtn("Settings and records", `data-wbtab="records"`)) + `</div>` +
    `<div class="j2frame" data-j2frame="${wbEsc(n.ref)}"></div></div>`;
}
function j2vRecordsHtml(n){
  return dpCard("Settings and records", dpQuiet("Open a function to change its instructions, or an engine or filed work from the list.") +
    `<div class="dpoffer">${wbBtn("Back to the department", `data-wbtab="j2"`)}</div>`);
}
/* The list's first group in records mode: one row back to the page where Chat, Map, Board and Agent activity were. */
function j2vTop(ref, m){
  if (!j2vEnabled() || !j2vEligible(ref) || j2vOn(ref)) return null;
  return `<div class="o2g dpg wb">` + dpRow("Department view", `data-wbtab="j2"`, false) + `</div>`;
}

/* ── the frame: one iframe on a host of <body>, laid over the placeholder ─────────────────────────────────────────── */
/* The mount-once rule of the chat frame (20-dept.js DP_FRAME): re-inserting an iframe reloads it, so it lives on a host
   element OUT of the region render() rebuilds, is laid over the placeholder each paint, is hidden -- never emptied -- when
   no placeholder is on screen, and is dropped only when the department changes. It has NO sandbox attribute: a sandbox
   without allow-same-origin could not fetch, keep its view in localStorage or send the panel token. */
function j2vFrameDrop(){
  if (J2V_FRAME.el && J2V_FRAME.el.parentNode) J2V_FRAME.el.parentNode.removeChild(J2V_FRAME.el);
  J2V_FRAME.el = null; J2V_FRAME.key = null;
  if (J2V_FRAME.host) J2V_FRAME.host.hidden = true;
}
function j2vFrameHost(){
  if (J2V_FRAME.host && J2V_FRAME.host.isConnected) return J2V_FRAME.host;
  if (typeof document === "undefined" || !document.createElement || !document.body) return null;
  const h = document.createElement("div");
  h.className = "j2vhost";
  h.hidden = true;
  document.body.appendChild(h);
  J2V_FRAME.host = h;
  return h;
}
function j2vFramePlace(){
  const h = J2V_FRAME.host;
  if (!h) return;
  const ph = (J2V_FRAME.key && typeof document !== "undefined" && document.querySelector)
    ? document.querySelector('[data-j2frame="' + String(J2V_FRAME.key).replace(/"/g, "") + '"]') : null;
  if (!ph || S.screen !== "org2" || !ph.getBoundingClientRect){ h.hidden = true; return; }
  const r = ph.getBoundingClientRect();
  h.style.left = r.left + "px"; h.style.top = r.top + "px";
  h.style.width = r.width + "px"; h.style.height = r.height + "px";
  h.hidden = !(r.width > 0 && r.height > 0);
}
/* Called after every paint of the Org screen (wireOrg2) and on every rebuild of #panes (the observer below, so leaving
   the screen hides the frame too). */
function j2vAfterPaint(scBody){
  const root = (scBody && scBody.querySelector) ? scBody
             : (typeof document !== "undefined" && document.querySelector ? document : null);
  const ph = (root && S.screen === "org2") ? root.querySelector("[data-j2frame]") : null;
  if (!ph){ if (J2V_FRAME.host) J2V_FRAME.host.hidden = true; return; }
  const ref = ph.getAttribute("data-j2frame") || "";
  if (J2V_FRAME.key !== ref){
    j2vFrameDrop();
    const host = j2vFrameHost();
    if (!host) return;
    const fr = document.createElement("iframe");
    fr.className = "j2v-if";
    fr.title = "Department";
    fr.src = "/j2ui/" + encodeURIComponent(ref) + "/";
    host.appendChild(fr);
    J2V_FRAME.el = fr; J2V_FRAME.key = ref;
  }
  j2vFrameWatch();
  j2vFramePlace();
}
function j2vFrameWatch(){
  if (J2V_FRAME.observed || typeof window === "undefined" || !window.addEventListener) return;
  J2V_FRAME.observed = true;
  window.addEventListener("resize", j2vFramePlace);
  window.addEventListener("scroll", j2vFramePlace, true);
  const panes = document.getElementById && document.getElementById("panes");
  if (panes && typeof MutationObserver !== "undefined"){
    new MutationObserver(() => {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => j2vAfterPaint(null));
      else j2vAfterPaint(null);
    }).observe(panes, { childList: true });
  }
}
