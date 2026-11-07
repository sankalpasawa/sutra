/* model_pick.js - the model list and the effort of a chat, under the provider buttons of its pill (gap package welcome-settings, item 4).

   Strings in, strings out, like chat_pill.js (which calls pickHtml): nothing touches the DOM and every word from the wire is escaped.

     pickHtml(pill) -> html          for the provider the chat is pinned to: a model select (the main rows with a short note each, then a "More models"
                                     group with the pinned snapshots and the 1M-context spellings; for Codex the models Codex itself lists) and an effort
                                     select (only the values that model accepts). `pill` is one provider of GET /api/chats/{sid}/providers
                                     ({name, ready, model, chat_model, chat_effort, can_pick, model_options: [{slug, label, note, group, efforts}]}).
                                     When the chat's session still runs on the other provider the model waits for the switch, and the pill says so.
     choiceRequest(sid, provider, change) -> {method, path, body}   PUT /api/chats/{sid}/choice; `change` is {model} or {effort} (one at a time: a model
                                     change never re-sends the effort, the server keeps the stored one)
     selectRequest(sid, providers, act, provider, value) -> request|null   the request for a change of a select: act is "choose-model" or "choose-effort"
                                     and `provider` is the name on the select; null when the value is not one the list offers (nothing is sent)
     modelOf(pill) -> slug           the model shown as chosen: this chat's own, else the policy's

   The selects carry data-act="choose-model" | "choose-effort" and data-provider; the panel that shows the pill listens for `change`.
   A classic script with ONE global, ModelPick; in node it is module.exports. */
(function (root) {
  "use strict";

  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" ? v : (Number.isFinite(v) ? String(v) : ""));
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const NAMES = Object.freeze({claude: "Claude", codex: "Codex"});
  const EFFORTS = Object.freeze(["low", "medium", "high", "xhigh", "max"]);
  const label = name => (hasOwn(NAMES, name) ? NAMES[name] : clean(name));

  const optionsOf = pill => (isObj(pill) && Array.isArray(pill.model_options) ? pill.model_options.filter(o => isObj(o) && clean(o.slug) !== "") : []);
  const modelOf = pill => (isObj(pill) ? clean(pill.chat_model) || clean(pill.model) : "");
  const effortsOf = (options, slug) => {
    const found = options.find(o => clean(o.slug) === slug);
    const list = found && Array.isArray(found.efforts) ? found.efforts.filter(e => EFFORTS.includes(e)) : [];
    return list.length ? list : EFFORTS.slice();
  };

  function optionHtml(o, chosen) {
    const slug = clean(o.slug);
    const name = clean(o.label) || slug;
    const note = clean(o.note);
    return '<option value="' + esc(slug) + '"' + (slug === chosen ? " selected" : "") + (note ? ' title="' + esc(note) + '"' : "") + ">" +
      esc(name) + (note ? " - " + esc(note) : "") + "</option>";
  }

  function modelSelect(pill, options, chosen) {
    const main = options.filter(o => clean(o.group) !== "more");
    const more = options.filter(o => clean(o.group) === "more");
    const known = options.some(o => clean(o.slug) === chosen);
    // the model the chat runs on is shown even when the list does not name it (a policy model the CLI no longer lists): the select never lies
    const extra = chosen !== "" && !known ? '<option value="' + esc(chosen) + '" selected>' + esc(chosen) + "</option>" : "";
    return '<select class="cpick-model" data-act="choose-model" data-provider="' + esc(pill.name) + '" aria-label="Model for ' + esc(label(pill.name)) + '">' +
      extra + main.map(o => optionHtml(o, chosen)).join("") +
      (more.length ? '<optgroup label="More models">' + more.map(o => optionHtml(o, chosen)).join("") + "</optgroup>" : "") + "</select>";
  }

  function effortSelect(pill, options, chosen) {
    const allowed = effortsOf(options, chosen);
    const now = clean(pill.chat_effort);
    const blank = now === "" ? '<option value="" selected>Default</option>' : "";
    const stale = now !== "" && !allowed.includes(now) ? '<option value="' + esc(now) + '" selected>' + esc(now) + " (the nearest this model accepts is used)</option>" : "";
    return '<select class="cpick-effort" data-act="choose-effort" data-provider="' + esc(pill.name) + '" aria-label="Effort for ' + esc(label(pill.name)) + '">' +
      blank + stale + allowed.map(e => '<option value="' + esc(e) + '"' + (e === now ? " selected" : "") + ">" + esc(e) + "</option>").join("") + "</select>";
  }

  function pickHtml(pill) {
    if (!isObj(pill) || clean(pill.name) === "" || pill.ready !== true) return "";
    const options = optionsOf(pill);
    if (options.length === 0) return "";
    const who = esc(label(pill.name));
    if (pill.can_pick === false) {
      return '<div class="cpick" data-provider="' + esc(pill.name) + '"><span class="cpick-note">The model and effort of ' + who +
        " can be chosen after your next message: this chat still runs on the other model.</span></div>";
    }
    const chosen = modelOf(pill);
    const found = options.find(o => clean(o.slug) === chosen);
    const note = found && clean(found.note) ? '<span class="cpick-note">' + esc(clean(found.note)) + "</span>" : "";
    return '<div class="cpick" data-provider="' + esc(pill.name) + '"><label class="cpick-l">Model ' + modelSelect(pill, options, chosen) + "</label>" +
      '<label class="cpick-l">Effort ' + effortSelect(pill, options, chosen) + "</label>" + note + "</div>";
  }

  function choiceRequest(sid, provider, change) {
    const name = hasOwn(NAMES, provider) ? provider : null;
    const body = {provider: name};
    const c = isObj(change) ? change : {};
    if (name !== null && typeof c.model === "string" && clean(c.model) !== "") body.model = clean(c.model);
    else if (name !== null && typeof c.effort === "string" && EFFORTS.includes(c.effort)) body.effort = c.effort;
    return {method: "PUT", path: "/api/chats/" + encodeURIComponent(clean(sid)) + "/choice", body};
  }

  function selectRequest(sid, providers, act, provider, value) {
    const pill = (Array.isArray(providers) ? providers : []).find(p => isObj(p) && p.name === provider);
    if (!pill || pill.ready !== true) return null;
    const options = optionsOf(pill);
    const picked = clean(value);
    if (act === "choose-model") {
      return options.some(o => clean(o.slug) === picked) ? choiceRequest(sid, provider, {model: picked}) : null;
    }
    if (act === "choose-effort") return effortsOf(options, modelOf(pill)).includes(picked) ? choiceRequest(sid, provider, {effort: picked}) : null;
    return null;
  }

  const ModelPick = {pickHtml, choiceRequest, selectRequest, modelOf, EFFORTS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ModelPick;
  else root.ModelPick = ModelPick;
})(globalThis);
