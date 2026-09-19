#!/usr/bin/env node
/* throwaway probe: drive the REAL panel in headless Chrome and watch what
   happens to the + Delegate textarea while a person types at human speed and
   the app's OWN background traffic (polls, SSE frames, tickers) drives the
   renders. Zero deps -- Node 22+ has a global WebSocket, and CDP is the only
   thing this needs.

   MODE=forced  -- render() called by the probe every few keystrokes
   MODE=live    -- nothing forced; real elapsed time, real background renders
*/
"use strict";
const { spawn } = require("child_process");
const os = require("os");
const path = require("path");
const fs = require("fs");

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const ORIGIN = process.env.PANEL || "http://127.0.0.1:7681/";
const MODE = process.env.MODE || "live";
const GAP = Number(process.env.GAP || 450);
const N = Number(process.env.N || 40);

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const http = async (p) => (await fetch(`http://127.0.0.1:${PORT}${p}`)).json();

class CDP {
  constructor(ws){ this.ws = ws; this.id = 0; this.waits = new Map();
    ws.addEventListener("message", (e) => {
      const m = JSON.parse(e.data);
      if (m.id && this.waits.has(m.id)){ this.waits.get(m.id)(m); this.waits.delete(m.id); }
    });
  }
  send(method, params){
    const id = ++this.id;
    return new Promise((res) => { this.waits.set(id, res);
      this.ws.send(JSON.stringify({ id, method, params: params || {} })); });
  }
  async evaluate(expr){
    const m = await this.send("Runtime.evaluate",
      { expression: expr, awaitPromise: true, returnByValue: true });
    if (m.error) throw new Error(JSON.stringify(m.error));
    const r = m.result;
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 900));
    return r.result && r.result.value;
  }
}

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cdp-"));
  const proc = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${dir}`, "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", "--window-size=1400,900", ORIGIN,
  ], { stdio: "ignore" });

  let targets = null;
  for (let i = 0; i < 60; i++){
    try { targets = await http("/json/list"); if (targets.length) break; } catch (e) {}
    await sleep(250);
  }
  if (!targets || !targets.length){ proc.kill(); throw new Error("chrome never came up"); }
  const page = targets.find(t => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  const cdp = new CDP(ws);
  await cdp.send("Runtime.enable");
  await cdp.send("Page.enable");
  const done = async () => { try { ws.close(); } catch (e) {} proc.kill(); };

  try {
    for (let i = 0; i < 120; i++){
      if (await cdp.evaluate(`typeof render === "function" && typeof S !== "undefined"
        && !!S.screen && Array.isArray(S.sessions) && Array.isArray(S.openPanes)`)) break;
      await sleep(250);
    }
    await sleep(1500);
    console.log("mode:", MODE, "| booted:", await cdp.evaluate(`S.screen`));

    await cdp.evaluate(`(() => {
      if (typeof goDest === "function") goDest("focus");
      if (typeof openScreen === "function") openScreen("shadow");
      render(); return S.screen; })()`);
    /* the founder's real screen has a live delegate session streaming beside
       the workspace -- that is what rewrites panesHtml on every frame */
    if (process.env.PANE)
      console.log("opened pane:", await cdp.evaluate(`(() => {
        const live = (S.sessions || []).filter(s => s.real);
        const s = live[0]; if (!s) return "none";
        if (S.openPanes.indexOf(s.id) < 0) S.openPanes.push(s.id);
        render(); return s.id; })()`));
    if (process.env.CARD)
      console.log("card open:", await cdp.evaluate(`(() => { S.shadowCardOpen = true;
        if (typeof renderShadowCard === "function") renderShadowCard();
        return !!document.querySelector("[data-shcardwrap]"); })()`));
    for (let i = 0; i < 40; i++){
      if (await cdp.evaluate(`!!document.querySelector("[data-shdelegate]")`)) break;
      await cdp.evaluate(`render()`); await sleep(250);
    }
    await cdp.evaluate(`(() => { const b = document.querySelector("[data-shdelegate]");
      if (b) b.click(); else { S.shadowNewOpen = true; render(); } return true; })()`);
    await sleep(400);
    await cdp.evaluate(`render()`);

    if (!(await cdp.evaluate(`!!document.querySelector("[data-shnewtalk]")`))){
      console.log("box never mounted"); await done(); return;
    }

    /* instrument: count renders, log every blur of the box, and record any
       removal of the host's subtree, with a stack */
    await cdp.evaluate(`(() => {
      window.__box = document.querySelector("[data-shnewtalk]");
      window.__log = [];
      window.__renders = 0;
      const r = window.render;
      window.render = function(){ window.__renders++; return r.apply(this, arguments); };
      window.__box.addEventListener("blur", () => {
        window.__log.push({ t: Date.now(), ev: "blur",
          connected: window.__box.isConnected, renders: window.__renders,
          stack: (new Error()).stack.split("\\n").slice(1, 6).join(" | ") });
      });
      const host = document.querySelector("[data-shnewhost]");
      window.__hostGone = false;
      const mo = new MutationObserver((recs) => {
        recs.forEach(rec => {
          for (const n of rec.removedNodes){
            if (n === window.__box || (n.contains && n.contains(window.__box)))
              window.__log.push({ t: Date.now(), ev: "removed",
                from: rec.target.tagName + "." + rec.target.className,
                renders: window.__renders });
          }
        });
      });
      mo.observe(document.body, { childList: true, subtree: true });
      window.__box.focus();
      return document.activeElement === window.__box; })()`);

    const chars = ("ship the referral flow end to end and open a PR").split("").slice(0, N);
    const report = [];
    for (let i = 0; i < chars.length; i++){
      await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", text: chars[i] });
      await cdp.send("Input.dispatchKeyEvent", { type: "keyUp" });
      if (MODE === "forced" && i % 4 === 3)
        await cdp.evaluate(`(() => { if (typeof invalidatePanesHtml === "function") invalidatePanesHtml(); render(); })()`);
      if (MODE === "stress"){
        /* everything live traffic does to this screen while a person types */
        await cdp.evaluate(`(() => {
          const n = ${i};
          if (n % 5 === 0){                      /* a task list that changes */
            S.shadowMissions = (S.shadowMissions || []).slice();
            S.shadowMissions.unshift({ id: "m-probe-" + n, objective: "probe " + n,
              state: "running", turns_used: n, max_turns: 25, target_mode: "new" });
          }
          if (n % 5 === 2 && (S.shadowMissions || []).length)
            S.shadowMissions = S.shadowMissions.slice(1);
          if (n % 3 === 0) S.needsYou = [{ item_id: "probe-" + n, kind: "needs_decision",
            state: "new", title: "probe " + n }];
          if (n % 3 === 1) S.needsYou = [];
          if (n % 7 === 0) S.shadowHomeErr = "probe";
          if (n % 7 === 3) S.shadowHomeErr = null;
          if (n % 4 === 0 && typeof invalidatePanesHtml === "function") invalidatePanesHtml();
          if (n % 6 === 0 && typeof renderShadowCard === "function"){
            S.shadowCardOpen = !S.shadowCardOpen; renderShadowCard(); }
          render(); return true; })()`);
      }
      await sleep(GAP);
      const st = await cdp.evaluate(`(() => {
        const live = document.querySelector("[data-shnewtalk]");
        const a = document.activeElement;
        return { i: ${i}, renders: window.__renders,
          same: live === window.__box, conn: !!(window.__box && window.__box.isConnected),
          foc: a === live,
          active: a ? (a.tagName + (a.dataset && a.dataset.shnewtalk ? "[box]" : "")) : "none",
          v: live ? live.value : null, caret: live ? live.selectionStart : null }; })()`);
      if (!st.same || !st.foc || st.caret !== st.v.length) report.push(st);
    }

    const tail = await cdp.evaluate(`(() => {
      const live = document.querySelector("[data-shnewtalk]");
      return { renders: window.__renders, log: window.__log,
        same: live === window.__box, foc: document.activeElement === live,
        value: live ? live.value : null,
        store: (typeof shadowNewChat === "function") ? shadowNewChat().text : null }; })()`);

    /* the caret must survive editing in the MIDDLE, not just appending */
    await cdp.evaluate(`(() => { window.__box.setSelectionRange(4, 4); return true; })()`);
    await cdp.send("Input.dispatchKeyEvent", { type: "keyDown", text: "X" });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp" });
    await cdp.evaluate(`(() => { if (typeof invalidatePanesHtml === "function") invalidatePanesHtml(); render(); render(); })()`);
    console.log("mid-text edit:", JSON.stringify(await cdp.evaluate(`(() => {
      const live = document.querySelector("[data-shnewtalk]");
      return { same: live === window.__box, foc: document.activeElement === live,
        caret: live.selectionStart, head: live.value.slice(0, 8) }; })()`)));

    /* SUBMIT, without creating anything on the server: the create writer is
       stubbed, so this exercises the Enter path and nothing else */
    console.log("submit:", JSON.stringify(await cdp.evaluate(`(async () => {
      window.shadowCreateTask = async () => ({ id: "m-probe", objective: "probe",
        state: "running", turns_used: 0, max_turns: 25, target_mode: "new" });
      const box = document.querySelector("[data-shnewtalk]");
      box.focus();
      box.dispatchEvent(new KeyboardEvent("keydown",
        { key: "Enter", bubbles: true, cancelable: true }));
      await new Promise(r => setTimeout(r, 300));
      render();
      return { boxCleared: box.value === "", chatReset: S.shadowNewChat === null,
        panelOpen: !!S.shadowNewOpen,
        boxesOnScreen: document.querySelectorAll("[data-shnewtalk]").length }; })()`)));

    /* and closing + Delegate must still tear the panel down */
    console.log("close:", JSON.stringify(await cdp.evaluate(`(() => {
      S.shadowNewOpen = true; render();
      const b = document.querySelector("[data-shdelegate]"); if (b) b.click();
      render(); render();
      return { open: !!S.shadowNewOpen,
        boxes: document.querySelectorAll("[data-shnewtalk]").length,
        hosts: document.querySelectorAll("[data-shnewhost]").length }; })()`)));

    console.log("renders during typing:", tail.renders);
    console.log("anomalous samples:", report.length);
    report.slice(0, 12).forEach(r => console.log("  " + JSON.stringify(r)));
    console.log("events:", JSON.stringify(tail.log, null, 1).slice(0, 2500));
    console.log("final:", JSON.stringify({ same: tail.same, foc: tail.foc,
      value: tail.value, store: tail.store }));
  } catch (e){
    console.error("PROBE ERROR:", e.message);
  }
  await done();
})();
