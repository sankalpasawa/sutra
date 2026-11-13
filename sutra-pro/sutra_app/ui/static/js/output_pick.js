/* output_pick.js - "What should we make?" on the start page of a team (J2 sync 4; docs/design/j2-sync-4.md D139 and 4.4; J2 sync 5, D166).

   The J2 start page no longer has a way to choose what a run makes, so the choice moved to a placeholder the port puts in the landing (page edit E19,
   `<div class="soutpick" id="soutpick"></div>`, before the chips) and this module fills it. The landing hides itself once the team has a run, and the
   placeholder with it, so the choice is only ever shown before the first message.

     typesOf(settings)      the types the owner may pin, from `output_types` of GET /api/engine/settings: [{name, label, form, pin}] in the data's order
                            (`types.json`, the user's own types, the types a capability registers). The page names no type: the choices ARE the data.
     optionsFor(current, types)   [[value, label]]: Let the team decide (auto) first, then every type of `types` that can be pinned, with the data's own label;
                            a value that is not among them (a type the data no longer lists) is added after them, so the choice in force is shown, not lost.
     outputOf(settings)     what the team's next run would make: `next_run.output` of GET /api/engine/settings?dept= (the start page's own pick included, so
                            a reload shows it), else the team's default `effective.output`, else "auto".
     html(state)            the markup: <label for="outsel">What should we make?</label> <select id="outsel" class="outsel"> and a status line for a refusal.
                            state {output, locked, note}.
     mount(host, {api, dept})   reads the settings, paints `host`, and sends a change as POST /api/output {type} (token and team: SutraCtx.api and ?dept=,
                            the request the page's own wrapper would make). A 409 (a run exists, so the choice is closed) puts the old choice back, locks
                            the select and says "The team has started; choose before the first message."; any other refusal puts the old choice back and
                            says what went wrong. -> {state(), refresh(), destroy()}
     start()                on a team page whose boot block does not call the team archived and that has #soutpick; an archived team gets nothing built
                            (and sutra-panel.css hides the placeholder anyway). Self-starting in a page; in node nothing starts by itself.

   Settings, Engine keeps the team's default (D129: `auto`; with no default type the planner chooses, D165); this is the per-request choice. A classic script with ONE global, OutputPick (see sutra_ctx.js
   for why); in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const enc = encodeURIComponent;

  const QUESTION = "What should we make?";
  const AUTO = Object.freeze(["auto", "Let the team decide"]);
  const STARTED = "The team has started; choose before the first message.";
  const FAILED = "That did not work. Try again.";

  // The types the settings answer lists, cleaned: a row without a name is dropped, a missing label is the name, and `pin` must be true to be offered.
  function typesOf(settings) {
    const list = isObj(settings) && Array.isArray(settings.output_types) ? settings.output_types : [];
    return list.filter(t => isObj(t) && clean(t.name) !== "").map(t => ({name: clean(t.name), label: clean(t.label) || clean(t.name), form: clean(t.form), pin: t.pin === true}));
  }

  const labelOf = (value, types) => {
    if (value === AUTO[0]) return AUTO[1];
    const found = (Array.isArray(types) ? types : []).find(t => isObj(t) && t.name === value);
    return found ? (clean(found.label) || value) : value;
  };

  function optionsFor(current, types) {
    const now = clean(current);
    const list = [AUTO.slice()];
    (Array.isArray(types) ? types : []).forEach(t => {
      if (isObj(t) && t.pin === true && clean(t.name) !== "" && !list.some(o => o[0] === clean(t.name))) list.push([clean(t.name), clean(t.label) || clean(t.name)]);
    });
    if (now !== "" && !list.some(o => o[0] === now)) list.push([now, labelOf(now, types)]);
    return list;
  }

  function outputOf(settings) {
    const s = isObj(settings) ? settings : {};
    const next = isObj(s.next_run) ? clean(s.next_run.output) : "";
    if (next !== "") return next;
    const fallback = isObj(s.effective) ? clean(s.effective.output) : "";
    return fallback !== "" ? fallback : "auto";
  }

  function html(state) {
    const s = isObj(state) ? state : {};
    const types = Array.isArray(s.types) ? s.types : [];
    const now = clean(s.output) || "auto";
    const note = clean(s.note);
    return '<label for="outsel">' + esc(QUESTION) + '</label><select id="outsel" class="outsel" aria-describedby="soutnote"' + (s.locked === true ? " disabled" : "") + ">" +
      optionsFor(now, types).map(o => '<option value="' + esc(o[0]) + '"' + (o[0] === now ? " selected" : "") + ">" + esc(o[1]) + "</option>").join("") + "</select>" +
      '<span class="soutnote" id="soutnote" role="status"' + (note === "" ? " hidden" : "") + ">" + esc(note) + "</span>";
  }

  function report(where, error) {
    if (typeof console !== "undefined" && console && typeof console.error === "function") console.error("OutputPick: " + where + " failed", error);
  }

  /* ---------------------------------------------------------------- the placeholder */
  function mount(host, options) {
    const o = isObj(options) ? options : {};
    const api = o.api;
    const dept = clean(o.dept);
    const S = {output: "auto", types: [], locked: false, note: "", busy: false, loaded: false, destroyed: false};

    const view = () => ({output: S.output, types: S.types, locked: S.locked || S.busy, note: S.note});

    // The first paint writes the markup; after that the elements are changed in place, so the select keeps the keyboard's focus.
    function paint() {
      if (S.destroyed) return;
      const select = typeof host.querySelector === "function" ? host.querySelector("#outsel") : null;
      if (!S.loaded || !select) {
        host.innerHTML = html(view());
        return;
      }
      select.disabled = S.locked || S.busy;
      select.value = S.output;
      if (clean(select.value) !== S.output) {          // a value the list does not hold (the engine answered with another output): the markup is made again
        host.innerHTML = html(view());
        return;
      }
      const note = host.querySelector("#soutnote");
      if (note) {
        note.textContent = S.note;
        note.hidden = clean(S.note) === "";
      }
    }

    async function refresh() {
      if (!api || typeof api.get !== "function" || S.destroyed) return false;
      let got;
      try {
        got = await api.get("/api/engine/settings", {dept});
      } catch (e) {
        report("the settings could not be read", e);
        return false;
      }
      if (S.destroyed) return false;
      S.output = outputOf(got);
      S.types = typesOf(got);
      S.loaded = true;
      paint();
      return true;
    }

    async function choose(type) {
      const wanted = clean(type);
      if (!api || typeof api.post !== "function" || S.busy || S.locked || wanted === "" || wanted === S.output) return false;
      const before = S.output;
      S.busy = true;
      S.note = "";
      S.output = wanted;
      paint();
      let ok = false;
      try {
        const reply = await api.post("/api/output?dept=" + enc(dept), {type: wanted});
        S.output = isObj(reply) && clean(reply.output) !== "" ? clean(reply.output) : wanted;
        ok = true;
      } catch (e) {
        S.output = before;
        if (e && e.status === 409) {
          S.locked = true;
          S.note = STARTED;
        } else {
          S.note = clean(e && e.message) || FAILED;
        }
      }
      S.busy = false;
      paint();
      return ok;
    }

    host.addEventListener("change", e => {
      const t = e && e.target;
      if (t && t.id === "outsel") choose(t.value);
    });
    const first = refresh();

    return {refresh, choose, first, state: () => ({output: S.output, locked: S.locked, note: S.note, busy: S.busy, loaded: S.loaded}), destroy: () => { S.destroyed = true; }};
  }

  let started = null;
  function start() {
    if (started !== null) return started;
    const doc = root.document;
    const ctx = root.SutraCtx;
    if (!doc || !ctx || !ctx.api || !isObj(ctx.boot) || ctx.boot.page !== "dept" || ctx.boot.archived === true) return null;
    const host = doc.getElementById("soutpick");
    if (!host) return null;
    started = mount(host, {api: ctx.api, dept: ctx.dept});
    return started;
  }

  const OutputPick = {AUTO, QUESTION, STARTED, typesOf, optionsFor, labelOf, outputOf, html, mount, start};
  if (typeof module === "object" && module !== null && module.exports) {
    module.exports = OutputPick;
  } else {
    root.OutputPick = OutputPick;
    const page = root.SutraCtx && isObj(root.SutraCtx.boot) ? root.SutraCtx.boot.page : "";
    if (page === "dept" && root.document) {
      if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
      else start();
    }
  }
})(globalThis);
