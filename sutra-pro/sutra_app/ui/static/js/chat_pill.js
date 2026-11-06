/* chat_pill.js - the provider pill, the streaming indicator and the switch notice of a chat (work package ABS-9; absorb design 2.3, D111).

   Strings in, strings out, like chat_view.js: nothing touches the DOM and every word from the wire is escaped.

     pill(providers, chosen)    the round pill: one button per provider that CAN run (the chosen one pressed), and a plain, unclickable label with its
                                reason for one that cannot. A provider that cannot run is never offered (the old app's rule). Selecting calls
                                PUT /api/chats/{sid}/choice; there is no text detector (one mechanism, D111). A button carries its fullest usage
                                window ("5-hour 62%") when the provider sent a quota (GAP-providers; a third argument `nowMs` is for a test).
     selectable(providers)      the names the pill offers
     choiceRequest(sid, name)   {method, path, body} for the PUT; name null clears the choice (the policy decides again)
     partial(state, event)      the streaming state after a `chat.partial` event of this chat: {active, text}
     settle(state)              the state once the stored message arrived: nothing is shown
     indicator(state)           the streaming row ("Claude is writing" plus the text so far), or "" when nothing streams
     switchNotice(event)        "Switched Claude to Codex; carried 40 messages" from a `switched` event {from, to, plan}

   Buttons carry data-act="choose-provider" and data-provider; the panel that shows the pill listens for them.
   A classic script with ONE global, ChatPill; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const NAMES = Object.freeze({claude: "Claude", codex: "Codex"});
  const label = name => (hasOwn(NAMES, name) ? NAMES[name] : clean(name));
  const MAX_SHOWN = 4000;      // a streaming reply is shown to this many characters; the stored message has all of it

  const list = providers => (Array.isArray(providers) ? providers.filter(p => isObj(p) && hasOwn(NAMES, p.name)) : []);
  const selectable = providers => list(providers).filter(p => p.ready === true).map(p => p.name);

  // The fullest usage window of a ready provider as a small figure on its button ("5-hour 62%"), from `quota` (GAP-providers, plan_meter.js, looked
  // up when drawn). A window whose reset has passed or that has no figure is left out; "" when nothing is left or plan_meter.js is not loaded.
  function planMeter() {
    if (root.PlanMeter) return root.PlanMeter;
    if (typeof module === "object" && module !== null && module.exports && typeof require === "function") return require("./plan_meter.js");
    return null;
  }
  function quotaWord(p, nowMs) {
    const pm = planMeter();
    if (!pm || !isObj(p.quota)) return "";
    const now = Number.isFinite(nowMs) ? nowMs : Date.now();
    const live = pm.windowsOf(p.quota).filter(w => pm.severity(w.used) !== "unknown" && pm.resetText(w.resets_at, now) !== "reset");
    if (live.length === 0) return "";
    const top = live.reduce((a, b) => (b.used > a.used ? b : a));
    const words = (clean(top.label) || "Plan") + " " + Math.round(top.used * 100) + "%";
    const reset = pm.resetText(top.resets_at, now);
    return ' <small class="cpill-q" data-sev="' + pm.severity(top.used) + '" title="' + esc(words + (reset ? ", " + reset : "")) + '">' + esc(words) + "</small>";
  }

  function pill(providers, chosen, nowMs) {
    const items = list(providers);
    if (items.length === 0) return "";
    const picked = hasOwn(NAMES, chosen) ? chosen : "";
    const parts = items.map(p => {
      if (p.ready !== true) {
        const why = clean(p.why_not) || "cannot run";
        return '<span class="cpill-opt off" title="' + esc(why) + '">' + esc(label(p.name)) + ' <small>' + esc(why) + "</small></span>";
      }
      const on = p.name === picked;
      return '<button type="button" class="cpill-opt' + (on ? " on" : "") + '" data-act="choose-provider" data-provider="' + esc(p.name) +
        '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(label(p.name)) + quotaWord(p, nowMs) + "</button>";
    });
    const auto = picked === "" ? '<span class="cpill-note">chosen by the app</span>' :
      '<button type="button" class="cpill-opt auto" data-act="choose-provider" data-provider="" aria-pressed="false">Let the app choose</button>';
    return '<div class="cpill" role="group" aria-label="Which model answers this chat">' + parts.join("") + auto + "</div>";
  }

  function choiceRequest(sid, name) {
    const provider = hasOwn(NAMES, name) ? name : null;
    return {method: "PUT", path: "/api/chats/" + encodeURIComponent(clean(sid)) + "/choice", body: {provider: provider}};
  }

  const idle = () => ({active: false, text: ""});

  function partial(state, event) {
    const prev = isObj(state) && state.active ? state.text : "";
    const d = isObj(event) && isObj(event.data) ? event.data : (isObj(event) ? event : {});
    const next = (prev + text(d.delta)).slice(-MAX_SHOWN);
    return {active: true, text: next};
  }

  const settle = () => idle();

  function indicator(state, provider) {
    if (!isObj(state) || state.active !== true) return "";
    const who = clean(provider) ? label(clean(provider)) : "The model";
    const shown = text(state.text);
    return '<div class="cstream" role="status" aria-live="polite"><small>' + esc(who) + " is writing…</small>" +
      (shown === "" ? "" : '<div class="cstream-text">' + esc(shown).replace(/\r\n|\r|\n/g, "<br/>") + "</div>") + "</div>";
  }

  function switchNotice(event) {
    const d = isObj(event) && isObj(event.data) ? event.data : event;
    if (!isObj(d) || !clean(d.to)) return "";
    const plan = isObj(d.plan) ? d.plan : {};
    const kept = Number.isFinite(plan.kept_messages) ? plan.kept_messages : 0;
    const omitted = Number.isFinite(plan.omitted) ? plan.omitted : 0;
    const from = clean(d.from) ? "Switched " + label(clean(d.from)) + " to " + label(clean(d.to)) : "Switched to " + label(clean(d.to));
    const carried = kept === 0 ? "nothing to carry" : "carried " + kept + " message" + (kept === 1 ? "" : "s");
    return from + "; " + carried + (omitted > 0 ? ", " + omitted + " earlier shortened" : "");
  }

  const ChatPill = {pill, selectable, choiceRequest, partial, settle, indicator, switchNotice, idle, NAMES};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChatPill;
  else root.ChatPill = ChatPill;
})(globalThis);
