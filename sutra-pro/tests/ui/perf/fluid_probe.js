/* fluid_probe.js - the frame-time probe of the "fluid" package (docs/notes/GAP3-fluid.md). NOT a test and not shipped: paste it into the console of a page served
   by the fake backend (`scripts/py tests/ui/fake_backend.py --port 8791 --stage full`, then open http://127.0.0.1:8791/), or run it with the browser pane's
   javascript tool. It installs window.__probe (a requestAnimationFrame frame-time probe) and the helpers the measurements of the note use:

     __probe.measure(ms, fn)     frames, frames over 20 ms and 33 ms, the longest frame, the mean frame, long tasks, for `fn` plus `ms` of quiet
     __probe.lag(ms, fn)         the same for a pane that is NOT on screen (the browser pane hides itself and the page then gets no animation frames): a 4 ms
                                 timer that reads the layout each tick, so the style and layout work of the page lands inside the gaps it measures:
                                 {ticks, over16, over20, longest gap in ms}. This is the probe the note's numbers come from.
     __probe.work()              {render: calls, ms and characters of ChatMarkdown.render, mutations: records, nodes added/removed and elements created in #sstream, #smsgs, #nodepanel, #pane-graph, #pane-chart}
     __setupDirect()             a fake model behind the chats (providers, PUT choice, POST /direct) and "Ask directly" with a turn running in the org chat
     __stream(sid, total, per, ms)  emits `total` characters as chat.partial events of `sid`, `per` characters every `ms` (through /__fake/emit: the real SSE path)
     __seed(n)                   n more messages in the org chat (stored by the fake backend), so a transcript is long enough to cost something to draw
     __append(text)              one new agent message, as the live stream delivers it
*/
(() => {
  if (window.__probe) return "already installed";
  const P = window.__probe = {f: [], long: [], run: false, last: 0, renders: {calls: 0, ms: 0, chars: 0}, muts: {records: 0, added: 0, removed: 0, created: 0}};
  try { new PerformanceObserver(l => l.getEntries().forEach(e => P.long.push(Math.round(e.duration)))).observe({entryTypes: ["longtask"]}); } catch (e) { /* no long tasks */ }
  P.start = () => {
    P.f = []; P.long = []; P.run = true; P.last = performance.now();
    P.renders = {calls: 0, ms: 0, chars: 0}; P.muts = {records: 0, added: 0, removed: 0, created: 0};
    const mine = P.gen = (P.gen || 0) + 1;                                // one loop at a time: an older measure's loop ends
    const tick = t => { if (!P.run || mine !== P.gen) return; P.f.push(t - P.last); P.last = t; requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  };
  P.stop = () => {
    P.run = false;
    const f = P.f.slice(1);
    const sum = f.reduce((a, b) => a + b, 0);
    return {frames: f.length, ms: Math.round(sum), over20: f.filter(x => x > 20).length, over33: f.filter(x => x > 33).length, longest: Math.round(Math.max(0, ...f)),
      mean: +(sum / Math.max(1, f.length)).toFixed(1), longTasks: P.long.length, longestTask: Math.max(0, ...P.long)};
  };
  P.sleep = ms => new Promise(r => setTimeout(r, ms));
  P.measure = async (ms, fn) => { P.start(); if (fn) await fn(); await P.sleep(ms); return P.stop(); };
  P.lag = async (ms, fn) => {
    const gaps = [];
    let last = performance.now();
    const id = setInterval(() => { const t = performance.now(); gaps.push(t - last - 4); last = t; void document.body.offsetHeight; }, 4);
    if (fn) await fn();
    await P.sleep(ms);
    clearInterval(id);
    const g = gaps.slice(1).map(x => Math.max(0, x));
    return {ticks: g.length, over16: g.filter(x => x > 16).length, over20: g.filter(x => x > 20).length, longest: Math.round(Math.max(0, ...g)), total: Math.round(g.reduce((a, b) => a + b, 0))};
  };
  P.work = () => ({render: {calls: P.renders.calls, ms: +P.renders.ms.toFixed(1), chars: P.renders.chars}, mutations: Object.assign({}, P.muts)});

  // time ChatMarkdown.render (the work a streamed chunk causes) and count the DOM mutations of the chat areas
  const md = window.ChatMarkdown;
  if (md && typeof md.render === "function") {
    const render = md.render;
    md.render = function (text, opts) {
      const t0 = performance.now();
      const out = render.apply(this, arguments);
      P.renders.calls += 1; P.renders.ms += performance.now() - t0; P.renders.chars += String(text).length;
      return out;
    };
  }
  // created: every element that was put into the page (an added node and all it holds), the honest size of the work the browser had to do
  const size = node => (node.nodeType === 1 ? 1 + node.querySelectorAll("*").length : 1);
  const watch = new MutationObserver(list => list.forEach(r => {
    P.muts.records += 1; P.muts.added += r.addedNodes.length; P.muts.removed += r.removedNodes.length;
    r.addedNodes.forEach(n => { P.muts.created += size(n); });
  }));
  ["sstream", "smsgs", "nodepanel", "pane-graph", "pane-chart"].forEach(id => { const el = document.getElementById(id); if (el) watch.observe(el, {childList: true, subtree: true, characterData: true}); });

  window.__setupDirect = async () => {
    if (!window.__fetch0) {
      window.__fetch0 = window.fetch;
      window.fetch = function (url, init) {
        const u = String(url), m = ((init && init.method) || "GET").toUpperCase();
        const j = body => Promise.resolve(new Response(JSON.stringify(body), {status: 200, headers: {"content-type": "application/json"}}));
        if (/\/api\/chats\/[^/]+\/providers$/.test(u) && m === "GET") return j({providers: [{name: "claude", ready: true}, {name: "codex", ready: true}], chosen: "claude"});
        if (/\/api\/chats\/[^/]+\/choice$/.test(u) && m === "PUT") return j({});
        if (/\/api\/chats\/[^/]+\/direct$/.test(u) && m === "POST") return j({message_id: 7777});
        return window.__fetch0.apply(this, arguments);
      };
    }
    const pill = document.querySelector("#spill");
    const b = document.createElement("button"); b.dataset.act = "choose-provider"; b.dataset.provider = "claude"; pill.appendChild(b); b.click();   // reads the providers again
    await P.sleep(400);
    const direct = document.querySelector('#sbar [data-mode="direct"]'); if (direct) direct.click();
    await P.sleep(200);
    const box = document.querySelector("#sbox"); box.value = "Tell me a long story"; box.dispatchEvent(new Event("input", {bubbles: true}));
    document.querySelector("#ssend").click();
    await P.sleep(500);
    return !document.querySelector("#sstream").hidden || "turn running";
  };

  // a reply made of paragraphs, lists, headings and code, emitted as chat.partial events
  window.__reply = total => {
    const para = "This is a **long** reply with `code` and some words that keep going so the line wraps over the width of the column. ";
    let text = "";
    for (let i = 0; text.length < total; i += 1) {
      text += i % 9 === 8 ? "\n\n- item " + i + " with more words\n- item " + (i + 1) + "\n\n```js\nconst a = " + i + ";\n```\n\n" : (i % 5 === 4 ? "\n\n## Heading " + i + "\n\n" : para);
    }
    return text;
  };
  window.__stream = async (sid, total, per, every) => {
    const text = window.__reply(total);
    const t0 = performance.now();
    for (let i = 0; i < text.length; i += per) {
      const body = JSON.stringify({event: "chat.partial", data: {session_id: sid, message_id: 7777, delta: text.slice(i, i + per)}});
      await (window.__fetch0 || window.fetch)("/__fake/emit", {method: "POST", headers: {"content-type": "application/json"}, body});
      await new Promise(r => setTimeout(r, every));
    }
    return {chars: text.length, ms: Math.round(performance.now() - t0)};
  };
  let nextId = 5000;
  const post = (event, data) => (window.__fetch0 || window.fetch)("/__fake/emit", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({event, data})});
  window.__post = post;                                                   // __post("graph.updated", {...}): any event, through the fake backend
  window.__append = async text => {
    nextId += 1;
    await post("chat.message", {session_id: "cs_org", message: {id: nextId, session_id: "cs_org", role: "agent", who: "sutra", kind: "text", text, card: null, pause: null,
      answered_by: null, task_id: null, state: "ok", at: "2026-11-04T10:00:03Z"}});
  };
  window.__seed = async n => {
    for (let i = 0; i < n; i += 1) await window.__append("Message " + i + " of a long conversation, with **bold** words and `code`, so the bubble is not empty. ".repeat(1 + (i % 3)));
    await P.sleep(800);
    return document.querySelectorAll("#smsgs .nmsg").length;
  };

  // the scenarios of the note: the same code before and after the change. Each returns the frame probe's numbers (and the work counters where they matter).
  const railButton = test => Array.from(document.querySelectorAll(".rail.tabs button")).find(b => test(b));
  const clickNode = id => {
    const t = document.querySelector('g.wnode[data-id="' + id + '"]');
    const r = t.getBoundingClientRect();
    for (const type of ["pointerdown", "pointerup"]) t.dispatchEvent(new PointerEvent(type, {bubbles: true, clientX: r.x + 5, clientY: r.y + 5, pointerId: 1, button: 0}));
    t.dispatchEvent(new MouseEvent("click", {bubbles: true, clientX: r.x + 5, clientY: r.y + 5}));
  };
  window.__run = {
    // 20 messages arriving, 150 ms apart, in an org chat that already holds a long conversation (run __seed(300) once, first)
    append: async () => { const r = await P.measure(300, async () => { for (let i = 0; i < 20; i += 1) { await window.__append("A new reply number " + i + " with some words in it."); await P.sleep(150); } }); return Object.assign({messages: document.querySelectorAll("#smsgs .nmsg").length}, r, P.work()); },
    // a 6500 character reply as 470 chat.partial events, ~80 a second (needs __setupDirect() first)
    stream: async () => { P.start(); const s = await window.__stream("cs_org", 6500, 14, 8); await P.sleep(300); return Object.assign(s, P.stop(), P.work()); },
    // Home's panes: Org chart, Settings, Workflow graph, four rounds
    panes: async () => {
      const seq = [railButton(b => b.dataset.pane === "chart" || b.dataset.tab === "chart"), railButton(b => /Appearance/.test(b.textContent)), railButton(b => b.dataset.pane === "graph" || b.dataset.tab === "graph"),
        railButton(b => b.dataset.pane === "chart" || b.dataset.tab === "chart"), railButton(b => b.dataset.pane === "graph" || b.dataset.tab === "graph")];
      return Object.assign(await P.measure(300, async () => { for (let k = 0; k < 4; k += 1) for (const b of seq) { b.click(); await P.sleep(250); } }), P.work());
    },
    // the node panel opened (a click on the Web node) and closed, six times
    panel: async () => {
      const opened = [];
      const r = await P.measure(300, async () => { for (let i = 0; i < 6; i += 1) { clickNode("web"); await P.sleep(700); opened.push(!document.querySelector("#nodepanel").hidden); const c = document.querySelector("[data-npclose]"); if (c) c.click(); await P.sleep(400); } });
      return Object.assign({opened: opened.join(",")}, r, P.work());
    },
    // the graph drawn again: the fake backend swaps its graph between two versions and tells the page, 20 times (the picture really changes each time),
    // then 20 events that change nothing (the data is the same as the page has)
    graph: async () => {
      const swap = version => (window.__fetch0 || window.fetch)("/__fake/fixture", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({name: "graph", version})});
      const changing = await P.measure(300, async () => { for (let i = 0; i < 20; i += 1) { await swap(i % 2 ? "3" : "full"); await window.__post("graph.updated", {version: 100 + i, nodes: [], edges_added: [], edges_removed: []}); await P.sleep(200); } });
      const same = await P.measure(300, async () => { for (let i = 0; i < 20; i += 1) { await window.__post("graph.updated", {version: 200 + i, nodes: [], edges_added: [], edges_removed: []}); await P.sleep(150); } });
      return {changing, same, work: P.work()};
    },
  };
  return "installed";
})();
