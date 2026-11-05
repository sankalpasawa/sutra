/* console_view.js - the owner console at /console: usage and cost, the Atom log, health and the diagnostics download (work package GAP-CONSOLE,
   gaps G11 and G12; docs/design/gaps.md).

   Two layers in one file, because the page has no other script of its own:

   1. Pure functions (strings in, strings out, no DOM, no timer), so `node --test` runs them: money(), tokens(), untilText(), periodBar(), usageHtml(),
      connectorsHtml(), filterRows(), pageRows(), logHtml(), cardHtml(), healthHtml(), bytesText(), durationText(). Every word from the wire goes through
      esc(); a link is a link only when it is a path on this origin.
   2. create(opts) -> the controller: it fetches from the routes below, repaints a panel when its markup changed, follows the event stream
      (usage.recorded, coalesced to 1 s; atom.updated, connector.*, task.*) and falls back to polling every 2 s like the other views. `opts` carries
      everything it touches (doc, api, events, fetch, token, save, now, fnode), so a test drives it with fakes.

   Routes read:  GET /api/ops/usage?period=today|7d|30d|all&include_stub=0|1   GET /api/connectors/status   GET /api/ops/info   GET /api/ops/doctor[?refresh=1]
                 GET /api/atoms/log?node_id=&after=&limit=   GET /api/atoms/{id}   GET /api/ops/diagnostics (the token goes in the header; the answer is a zip)

   The Atom log is read forward (the route pages by `seq`), so the console loads the newest WINDOW seqs, shows them newest first, filters them in the page
   (state, check, UTC date) and loads WINDOW older ones on request. A node filter goes to the server (`node_id`), because it must cover the whole log.

   A classic script with ONE global, ConsoleView; in node it is module.exports. In a page that holds #console-root it starts itself. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const clean = v => (typeof v === "string" ? v : (finite(v) ? String(v) : "")).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const arr = v => (Array.isArray(v) ? v : []);
  const num = v => (finite(v) ? v : null);
  const group = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  /* ---------------------------------------------------------------- words */
  const PERIODS = freeze([["today", "Today"], ["7d", "7 days"], ["30d", "30 days"], ["all", "All"]]);
  const DEFAULT_PERIOD = "7d";
  const STATES = freeze([["closed", "Closed"], ["verify_failed", "Verify failed"], ["abandoned", "Abandoned"], ["refused", "Refused"]]);
  const HEALTH_WORDS = freeze({ok: "Ready", cooldown: "Cooling down", quota: "Quota reached", breaker: "Paused after failures", signed_out: "Not signed in", missing: "Not installed"});
  const QUOTA_WORDS = freeze({ok: "Quota fine", warning: "Quota running low", exhausted: "Quota used up", unknown: "Quota unknown"});
  const BASIS_WORDS = freeze({reported: "reported", rate_card: "rate card", unknown: "no price", none: "none"});
  const PROVIDER_NAMES = freeze({claude: "Claude", codex: "Codex", stub: "Stub"});
  const CHECK_WORDS = freeze({ok: "ok", warn: "warning", fail: "failed", skip: "skipped"});
  const WINDOW = 1000;          // log rows (seqs) loaded at first and per "older" request
  const LOG_PAGE_SIZE = 25;     // rows on one page of the table
  const LOG_FETCH = 500;        // the route's limit
  const MAX_FILTERED_ROWS = 5000;
  const POLL_MS = 2000;
  const USAGE_COALESCE_MS = 1000;
  const DOCTOR_POLL_MS = 30000;
  const providerName = key => (hasOwn(PROVIDER_NAMES, key) ? PROVIDER_NAMES[key] : clean(key));

  /* ---------------------------------------------------------------- numbers */
  // 12.5 -> "$12.50", 0.0031 -> "$0.0031", null -> "no figure"
  function money(usd) {
    if (!finite(usd)) return "no figure";
    return "$" + (usd >= 0.01 || usd === 0 ? usd.toFixed(2) : usd.toFixed(4));
  }
  const tokens = n => (finite(n) ? group(n) : "none");
  const sumTokens = (a, b) => (finite(a) || finite(b) ? (finite(a) ? a : 0) + (finite(b) ? b : 0) : null);
  function bytesText(n) {
    if (!finite(n)) return "unknown";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = n;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? String(Math.round(v)) : v.toFixed(v >= 100 ? 0 : 1)) + " " + units[i];
  }
  function durationText(seconds) {
    if (!finite(seconds) || seconds < 0) return "unknown";
    const s = Math.floor(seconds);
    if (s < 60) return s + " s";
    const m = Math.floor(s / 60);
    if (m < 60) return m + " min";
    const h = Math.floor(m / 60);
    if (h < 48) return h + " h" + (m % 60 ? " " + (m % 60) + " min" : "");
    return Math.floor(h / 24) + " days";
  }
  // "in 35 min", "in 2 h 10 min", "in 3 days", "now" for a moment that has passed.
  function untilText(epochSeconds, nowMs) {
    if (!finite(epochSeconds) || !finite(nowMs)) return "";
    const diff = epochSeconds * 1000 - nowMs;
    if (diff <= 0) return "now";
    const minutes = Math.ceil(diff / 60000);
    if (minutes < 60) return "in " + minutes + " min";
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return "in " + hours + " h" + (minutes % 60 ? " " + (minutes % 60) + " min" : "");
    return "in " + Math.floor(hours / 24) + " days";
  }
  function localTime(epochSeconds) {
    try {
      return new Date(epochSeconds * 1000).toLocaleString([], {weekday: "short", hour: "2-digit", minute: "2-digit"});
    } catch (e) {
      return new Date(epochSeconds * 1000).toISOString();
    }
  }
  const whenText = iso => clean(iso).replace("T", " ").replace(/Z$/, "");
  // A path on this origin, or "" (the server sends only such paths; a link built from anything else is dropped).
  const safePath = p => (typeof p === "string" && /^\/(?![\/\\])[^\u0000-\u001f"'<>`]*$/.test(p) ? p : "");

  /* ---------------------------------------------------------------- usage and cost */
  function periodBar(state) {
    const s = isObj(state) ? state : {};
    const period = s.period || DEFAULT_PERIOD;
    return '<div class="cbar" role="group" aria-label="Period">' + PERIODS.map(p =>
      '<button type="button" data-act="period" data-period="' + p[0] + '" aria-pressed="' + String(p[0] === period) + '">' + p[1] + "</button>").join("") +
      '</div><label class="cstub"><input type="checkbox" data-act="stub"' + (s.stub ? " checked" : "") + "> Include stub rows (test runs)</label>";
  }

  function providerOf(report, key) {
    return arr(report.providers).find(p => isObj(p) && p.key === key) || null;
  }

  function tile(label, value, note) {
    return '<div class="ctile"><span class="clabel">' + esc(label) + '</span><b class="cvalue">' + value + "</b>" +
      (note ? '<span class="cnote">' + esc(note) + "</span>" : "") + "</div>";
  }

  // "notional, subscription" when the rows say the money was not billed (a subscription), else the basis word of the figure.
  function usdNote(provider) {
    if (!provider) return "no calls in this period";
    if (provider.notional === true) return "notional, subscription";
    const basis = arr(provider.usd_basis).map(b => (hasOwn(BASIS_WORDS, b) ? BASIS_WORDS[b] : clean(b))).filter(Boolean);
    return basis.length ? basis.join(", ") : "";
  }

  function totalsHtml(report) {
    const totals = isObj(report.totals) ? report.totals : {};
    const claude = providerOf(report, "claude");
    const codex = providerOf(report, "codex");
    const codexTokens = codex ? sumTokens(codex.tokens_in, codex.tokens_out) : null;
    const codexNote = codex ? (finite(codex.tokens_in) || finite(codex.tokens_out) ? "in " + tokens(codex.tokens_in) + ", out " + tokens(codex.tokens_out) : "no token counts") +
      (finite(codex.usd) ? "; " + money(codex.usd) + " (" + usdNote(codex) + ")" : "") : "no calls in this period";
    return '<div class="ctiles">' +
      tile("Calls", esc(tokens(totals.calls || 0)), report.include_stub ? "stub rows included" : "") +
      tile("Claude, usd", esc(claude ? money(claude.usd) : "none"), usdNote(claude)) +
      tile("Codex, tokens", esc(codex ? tokens(codexTokens) : "none"), codexNote) + "</div>";
  }

  // One bar per day. The bar is the day's dollars when any day has them, else its tokens, else its calls.
  function daysHtml(report) {
    const days = arr(report.days).filter(isObj);
    if (!days.length) return '<p class="cempty">No calls in this period.</p>';
    const metric = days.some(d => finite(d.usd) && d.usd > 0) ? "usd" : days.some(d => finite(d.tokens_in) || finite(d.tokens_out)) ? "tokens" : "calls";
    const value = d => (metric === "usd" ? (finite(d.usd) ? d.usd : 0) : metric === "tokens" ? (sumTokens(d.tokens_in, d.tokens_out) || 0) : d.calls || 0);
    const top = Math.max.apply(null, days.map(value).concat([0]));
    const label = {usd: "dollars (Claude's are notional)", tokens: "tokens", calls: "calls"}[metric];
    return '<div class="cdays" role="list" aria-label="Per day: ' + esc(label) + '">' + days.map(d => {
      const v = value(d);
      const width = top > 0 ? Math.max(v > 0 ? 2 : 0, Math.round(v / top * 100)) : 0;
      return '<div class="cday" role="listitem" data-day="' + esc(d.key) + '"><span class="cdate">' + esc(d.key) + '</span><span class="ctrack"><span class="cfill" style="width:' + width +
        '%"></span></span><span class="cdval">' + esc(metric === "usd" ? money(d.usd) : metric === "tokens" ? tokens(v) : group(v)) + " &middot; " + esc(group(d.calls || 0)) + " calls</span></div>";
    }).join("") + '</div><p class="cnote">Bars show ' + esc(label) + " per UTC day.</p>";
  }

  function teamsHtml(report) {
    const teams = arr(report.teams).filter(isObj);
    if (!teams.length) return "";
    const cells = r => "<td>" + esc(group(r.calls || 0)) + "</td><td>" + esc(finite(r.usd) ? money(r.usd) : "") + "</td><td>" + esc(finite(r.tokens_in) ? tokens(r.tokens_in) : "") +
      "</td><td>" + esc(finite(r.tokens_out) ? tokens(r.tokens_out) : "") + "</td>";
    const fns = arr(report.functions).filter(isObj);
    const rows = teams.map(t => '<tr class="cteam"><th scope="row">' + esc(t.name || t.key) + "</th>" + cells(t) + "</tr>" +
      fns.filter(f => f.dept === t.key).map(f => '<tr class="cfn"><th scope="row">' + esc(f.fn) + "</th>" + cells(f) + "</tr>").join("")).join("");
    return '<table class="ctable"><caption>By team and function</caption><thead><tr><th scope="col">Team / function</th><th scope="col">Calls</th><th scope="col">USD</th>' +
      '<th scope="col">Tokens in</th><th scope="col">Tokens out</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  function atomsHtml(report) {
    const atoms = arr(report.atoms).filter(isObj);
    if (!atoms.length) return "";
    const rows = atoms.map(a => {
      const team = safePath(a.team_href);
      const node = safePath(a.node_href);
      return '<tr><th scope="row"><code>' + esc(a.atom_id) + "</code></th><td>" + esc([a.dept, a.fn].filter(Boolean).join(" / ")) + "</td><td>" + esc(group(a.calls || 0)) + "</td><td>" +
        esc(money(a.usd)) + "</td><td>" + esc(tokens(sumTokens(a.tokens_in, a.tokens_out))) + "</td><td>" +
        (team ? '<a href="' + esc(team) + '">Team tab</a>' : "") + (team && node ? " &middot; " : "") + (node ? '<a href="' + esc(node) + '">Node</a>' : "") + "</td></tr>";
    }).join("");
    return '<table class="ctable catoms"><caption>Top ten atoms by cost</caption><thead><tr><th scope="col">Atom</th><th scope="col">Team / function</th><th scope="col">Calls</th>' +
      '<th scope="col">USD</th><th scope="col">Tokens</th><th scope="col">Open</th></tr></thead><tbody>' + rows + "</tbody></table>";
  }

  // The Usage and cost panel: the picker, the totals, a bar per day, the team and function table, the ten dearest atoms.
  function usageHtml(report, state, error) {
    const head = "<h2>Usage and cost</h2>" + periodBar(state);
    if (!isObj(report)) return head + (error ? '<p class="cerr" role="alert">' + esc(error) + "</p>" : '<p class="cempty">Loading&hellip;</p>');
    return head + (error ? '<p class="cerr" role="alert">' + esc(error) + "</p>" : "") + totalsHtml(report) + daysHtml(report) + teamsHtml(report) + atomsHtml(report);
  }

  /* ---------------------------------------------------------------- connectors and the next quota reset */
  function nextReset(status, nowMs) {
    let best = null;
    arr(isObj(status) ? status.providers : []).filter(isObj).forEach(p => {
      const at = isObj(p.quota) ? p.quota.resets_at : null;
      if (finite(at) && at * 1000 > nowMs && (best === null || at < best.at)) best = {at: at, provider: p.name};
    });
    return best;
  }

  // The connectors' health and quota, from GET /api/connectors/status. `format(epochSeconds)` writes a clock time (a test passes its own).
  function connectorsHtml(status, nowMs, format) {
    const fmt = typeof format === "function" ? format : localTime;
    if (!isObj(status)) return '<div class="cconn"><h3>Connectors</h3><p class="cempty">Not loaded yet.</p></div>';
    const rows = arr(status.providers).filter(isObj).map(p => {
      const state = isObj(p.health) ? clean(p.health.state) : "";
      const word = p.installed === false ? HEALTH_WORDS.missing : (hasOwn(HEALTH_WORDS, state) ? HEALTH_WORDS[state] : (state || "unknown"));
      const q = isObj(p.quota) ? p.quota : null;
      const quota = q ? (hasOwn(QUOTA_WORDS, q.status) ? QUOTA_WORDS[q.status] : "Quota unknown") + (q.window ? " (" + clean(q.window) + ")" : "") +
        (finite(q.used) ? ", " + Math.round(q.used * 100) + "% used" : "") +
        (finite(q.resets_at) ? ", resets " + fmt(q.resets_at) + " (" + untilText(q.resets_at, nowMs) + ")" : "") : "No quota signal yet";
      const today = isObj(p.today) ? p.today : {};
      return '<div class="crow" data-provider="' + esc(p.name) + '"><b>' + esc(providerName(p.name)) + '</b><span class="cchip st-' + esc(state || "unknown") + '">' + esc(word) + "</span>" +
        '<span class="cnote">' + esc(quota) + "</span><span class=\"cnote\">Today: " + esc(group(today.calls || 0)) + " calls, " + esc(tokens(today.tokens || 0)) + " tokens</span></div>";
    }).join("");
    const next = nextReset(status, nowMs);
    return '<div class="cconn"><h3>Connectors</h3>' + (rows || '<p class="cempty">No connector is configured.</p>') +
      '<p class="creset" data-next-reset="' + (next ? esc(next.at) : "") + '">' + (next ? "Next quota reset: " + esc(fmt(next.at)) + " (" + esc(untilText(next.at, nowMs)) + ", " + esc(providerName(next.provider)) + ")" :
        "No quota reset is pending.") + "</p></div>";
  }

  /* ---------------------------------------------------------------- the Atom log */
  const bodyOf = row => (isObj(row) && isObj(row.body) ? row.body : {});
  const checkOf = row => { const v = bodyOf(row).verify; return isObj(v) && typeof v.template === "string" ? v.template : ""; };

  // filterRows(rows, {state, check, from, to}) -> the rows that match every filter that is set. `check` "(none)" means a row with no check; the dates are
  // YYYY-MM-DD and compare with the UTC date of the row's ts, both ends included.
  function filterRows(rows, f) {
    const o = isObj(f) ? f : {};
    return arr(rows).filter(r => isObj(r) &&
      (!o.state || r.status === o.state) &&
      (!o.check || (o.check === "(none)" ? checkOf(r) === "" : checkOf(r) === o.check)) &&
      (!o.from || clean(r.ts).slice(0, 10) >= o.from) &&
      (!o.to || clean(r.ts).slice(0, 10) <= o.to));
  }

  // pageRows(rows, page, size) -> {rows, page, pages}: `rows` are in seq order, the page shows the newest first; page 0 is the newest.
  function pageRows(rows, page, size) {
    const per = size > 0 ? size : LOG_PAGE_SIZE;
    const newest = arr(rows).slice().sort((a, b) => b.seq - a.seq);
    const pages = Math.max(1, Math.ceil(newest.length / per));
    const at = Math.min(Math.max(0, page | 0), pages - 1);
    return {rows: newest.slice(at * per, (at + 1) * per), page: at, pages: pages};
  }

  const distinct = values => Array.from(new Set(values.filter(Boolean))).sort();
  function select(name, label, options, value, any) {
    return '<label class="cfilter">' + esc(label) + ' <select data-filter="' + name + '" id="f-' + name + '"><option value="">' + esc(any) + "</option>" +
      options.map(o => '<option value="' + esc(o[0]) + '"' + (o[0] === value ? " selected" : "") + ">" + esc(o[1]) + "</option>").join("") + "</select></label>";
  }

  // The Atom log panel. `log` = {rows, nodes, node, state, check, from, to, page, selected, card, cardHtml, canLoadOlder, capped, error}.
  function logHtml(log) {
    const l = isObj(log) ? log : {};
    const rows = arr(l.rows);
    const shown = filterRows(rows, l);
    const paged = pageRows(shown, l.page, LOG_PAGE_SIZE);
    const filters = '<div class="cfilters">' +
      select("node", "Node", distinct(arr(l.nodes).concat(l.node || "")).map(n => [n, n]), l.node || "", "All nodes") +
      select("state", "State", STATES, l.state || "", "Any state") +
      select("check", "Check", distinct(rows.map(checkOf)).concat(rows.some(r => checkOf(r) === "") ? ["(none)"] : []).map(c => [c, c]), l.check || "", "Any check") +
      '<label class="cfilter">From <input type="date" data-filter="from" id="f-from" value="' + esc(l.from || "") + '"></label>' +
      '<label class="cfilter">To <input type="date" data-filter="to" id="f-to" value="' + esc(l.to || "") + '"></label>' +
      '<button type="button" class="ghost" data-act="clear-filters">Clear filters</button></div><p class="cnote">Dates are UTC.</p>';
    const body = paged.rows.map(r => {
      const b = bodyOf(r);
      const v = isObj(b.verify) ? b.verify : null;
      const checkText = v ? clean(v.template) + (finite(v.exit_code) ? " (exit " + v.exit_code + ")" : "") : "none";
      return '<tr class="lrow st-' + esc(r.status) + '" data-seq="' + esc(r.seq) + '"' + (l.selected === r.seq ? ' aria-selected="true"' : "") + '><th scope="row"><button type="button" class="linkbtn" data-act="open-card" data-seq="' + esc(r.seq) +
        '" aria-expanded="' + String(l.selected === r.seq) + '">' + esc(r.seq) + '</button></th><td title="' + esc(r.ts) + '">' + esc(whenText(r.ts)) + "</td><td><code>" + esc(r.atom_id) + "</code></td><td>" + esc(r.node_id) +
        '</td><td><span class="cchip st-' + esc(r.status) + '">' + esc(clean(r.status).replace("_", " ")) + "</span></td><td>" + esc(checkText) + "</td><td>" + esc(finite(b.attempt) ? b.attempt : "") + "</td><td>" +
        esc(clean(b.model)) + '</td><td class="cgoal">' + esc(clean(b.goal).slice(0, 120)) + "</td></tr>";
    }).join("");
    const table = shown.length ? '<table class="ctable clog"><caption>Atom log, newest first (' + esc(group(shown.length)) + " of " + esc(group(rows.length)) + ' loaded)</caption><thead><tr><th scope="col">Seq</th>' +
      '<th scope="col">When (UTC)</th><th scope="col">Atom</th><th scope="col">Node</th><th scope="col">State</th><th scope="col">Check</th><th scope="col">Try</th><th scope="col">Model</th>' +
      '<th scope="col">Goal</th></tr></thead><tbody>' + body + "</tbody></table>" : '<p class="cempty">' + (rows.length ? "No row matches these filters." : "The Atom log is empty.") + "</p>";
    const pager = '<div class="cpager"><button type="button" class="ghost" data-act="log-page" data-dir="newer"' + (paged.page <= 0 ? " disabled" : "") + '>Newer</button><span>Page ' +
      (paged.page + 1) + " of " + paged.pages + '</span><button type="button" class="ghost" data-act="log-page" data-dir="older"' + (paged.page >= paged.pages - 1 ? " disabled" : "") + ">Older</button>" +
      (l.canLoadOlder ? '<button type="button" class="ghost" data-act="log-older">Load ' + WINDOW + " older rows</button>" : "") + "</div>" +
      (l.capped ? '<p class="cnote">Only the first ' + MAX_FILTERED_ROWS + " rows of this node are loaded.</p>" : "");
    return "<h2>Atom log</h2>" + (l.error ? '<p class="cerr" role="alert">' + esc(l.error) + "</p>" : "") + filters + table + pager + '<div class="ccard" id="c-card" aria-live="polite">' + (l.cardHtml || "") + "</div>";
  }

  // The card text of one log row: the full atom card when the atom could be read (FnodeView.atomHtml), else the card the ledger row itself can give.
  function cardHtml(row, atom, atomHtml) {
    if (!isObj(row)) return "";
    const b = bodyOf(row);
    const word = clean(row.status).replace("_", " ");
    const line = '<p class="cnote">Log row ' + esc(row.seq) + " &middot; " + esc(whenText(row.ts)) + " UTC &middot; " + esc(word) + " &middot; " + esc(row.node_id) + "</p>";
    if (isObj(atom) && typeof atomHtml === "function") return line + atomHtml(atom, {open: true});
    const v = isObj(b.verify) ? b.verify : null;
    const rowsOut = [["Goal", clean(b.goal)], ["Check", v ? clean(v.template) + (finite(v.exit_code) ? ", exit code " + v.exit_code : "") : "none"],
      ["Try", finite(b.attempt) ? b.attempt + " of 3" : ""], ["Model", clean(b.model)], ["Touches", arr(b.touches).map(clean).filter(Boolean).join(", ")], ["Reason", clean(b.reason)]]
      .filter(r => r[1] !== "");
    return line + '<div class="atomcard ledgercard" data-state="' + esc(row.status) + '"><b>' + esc(word.toUpperCase()) + "</b>" +
      rowsOut.map(r => '<div class="ablock"><b>' + esc(r[0]) + "</b> <div>" + esc(r[1]) + "</div></div>").join("") + "</div>";
  }

  /* ---------------------------------------------------------------- health */
  function engineSourceText(e) {
    if (!isObj(e)) return "unknown";
    return clean(e.source) + (e.fields && e.fields.length ? " (" + e.fields.map(clean).join(", ") + ")" : "") + (e.env && e.env.length ? " [" + e.env.map(clean).join(", ") + "]" : "") +
      (e.problem ? " - unreadable: " + clean(e.problem) : "");
  }

  // The Health panel: the facts of GET /api/ops/info, the doctor's checks, "Check again" and "Download diagnostics".
  function healthHtml(info, doctor, state) {
    const s = isObj(state) ? state : {};
    const facts = isObj(info) ? [
      ["Version", info.version], ["Schema", info.schema + (info.schema !== info.schema_expected ? " (this build expects " + info.schema_expected + ")" : "")],
      ["Data folder", info.data_dir], ["Log file", info.log_path], ["Database size", bytesText(info.db_bytes)], ["Free space", bytesText(info.free_bytes)],
      ["Uptime", durationText(info.uptime_s)], ["Live tasks", info.live_tasks], ["Engine settings from", engineSourceText(info.engine_settings)],
      ["Atom log", group(isObj(info.atom_log) ? info.atom_log.rows : 0) + " rows"], ["Usage ledger", group(info.usage_rows || 0) + " rows"],
    ] : [];
    const dl = facts.length ? '<dl class="cfacts">' + facts.map(f => "<div><dt>" + esc(f[0]) + "</dt><dd>" + esc(f[1]) + "</dd></div>").join("") + "</dl>" : '<p class="cempty">' + (s.infoError ? "" : "Loading&hellip;") + "</p>";
    let checks = "";
    if (isObj(doctor)) {
      const c = isObj(doctor.summary) ? doctor.summary : {};
      checks = '<h3>Doctor</h3><p class="cnote" data-doctor="' + (doctor.ok ? "ok" : "fail") + '">' + (doctor.ok ? "Nothing failed. " : "Something failed. ") + esc(c.ok || 0) + " ok, " + esc(c.warn || 0) + " warning(s), " +
        esc(c.fail || 0) + " failed, " + esc(c.skip || 0) + " skipped. " + (doctor.cached ? "Checked " + esc(durationText(doctor.age_s)) + " ago." : "Checked just now.") + "</p><ul class=\"cchecks\">" +
        arr(doctor.checks).filter(isObj).map(k => '<li class="cchk st-' + esc(k.status) + '" data-check="' + esc(k.id) + '"><span class="cchip st-' + esc(k.status) + '">' +
          esc(hasOwn(CHECK_WORDS, k.status) ? CHECK_WORDS[k.status] : k.status) + "</span> <b>" + esc(k.title) + "</b> " + esc(k.detail) +
          (k.fix && (k.status === "warn" || k.status === "fail") ? '<span class="cfix"> Fix: ' + esc(k.fix) + "</span>" : "") + "</li>").join("") + "</ul>";
    }
    const errors = ["infoError", "doctorError", "downloadError"].map(k => (s[k] ? '<p class="cerr" role="alert">' + esc(s[k]) + "</p>" : "")).join("");
    return "<h2>Health</h2>" + errors + dl + checks + '<div class="cacts"><button type="button" class="ghost" data-act="doctor-refresh">Check again</button>' +
      '<button type="button" class="ghost" data-act="download"' + (s.downloading ? " disabled" : "") + ">" + (s.downloading ? "Preparing&hellip;" : "Download diagnostics") + "</button></div>" +
      '<p class="cnote">The diagnostics zip holds the version, the doctor result, the last 2 000 log lines, the settings and the team folder sizes. It holds no chat, prompt, site file or secret.</p>';
  }

  /* ---------------------------------------------------------------- the controller */
  function messageOf(e) {
    return clean(e && e.message) || "The app did not answer.";
  }

  function create(opts) {
    const o = isObj(opts) ? opts : {};
    const doc = o.doc;
    const api = o.api;
    const now = typeof o.now === "function" ? o.now : () => Date.now();
    const el = id => (doc && doc.getElementById ? doc.getElementById(id) : null);
    const S = {
      period: DEFAULT_PERIOD, stub: false, usage: null, usageError: "", status: null, info: null, doctor: null, doctorAt: 0, infoError: "", doctorError: "", downloadError: "", downloading: false, live: "offline",
      log: {rows: [], nodes: [], node: "", state: "", check: "", from: "", to: "", page: 0, selected: null, cardHtml: "", canLoadOlder: false, capped: false, error: "", after: 0, last: 0, loaded: false},
    };
    let stream = null;
    let stopped = false;

    function paint(id, html) {
      const node = el(id);
      if (!node || node.__html === html) return;
      const active = doc && doc.activeElement && doc.activeElement.id && node.contains && node.contains(doc.activeElement) ? doc.activeElement.id : "";
      node.innerHTML = html;
      node.__html = html;
      if (active) { const back = el(active); if (back && typeof back.focus === "function") back.focus(); }
    }

    function renderUsage() { paint("c-usage", usageHtml(S.usage, S, S.usageError) + connectorsHtml(S.status, now(), o.format)); }
    function renderLog() { paint("c-log", logHtml(S.log)); }
    function renderHealth() { paint("c-health", healthHtml(S.info, S.doctor, S)); }
    function renderState() {
      const node = el("cstate");
      if (node) node.textContent = S.live === "live" ? "Live" : (S.live === "polling" ? "Updating every 2 s" : "Not connected");
    }
    function renderAll() { renderUsage(); renderLog(); renderHealth(); renderState(); }

    /* ---- loads */
    async function loadUsage() {
      try {
        S.usage = await api.get("/api/ops/usage", {period: S.period, include_stub: S.stub ? 1 : 0});
        S.usageError = "";
      } catch (e) { S.usageError = messageOf(e); }
      renderUsage();
    }
    async function loadStatus() {
      try { S.status = await api.get("/api/connectors/status"); } catch (e) { /* the panel keeps what it had; usage has its own error line */ }
      renderUsage();
    }
    async function loadInfo() {
      try { S.info = await api.get("/api/ops/info"); S.infoError = ""; } catch (e) { S.infoError = messageOf(e); }
      renderHealth();
    }
    async function loadDoctor(refresh) {
      try {
        S.doctor = await api.get("/api/ops/doctor", refresh ? {refresh: 1} : undefined);
        S.doctorError = "";
        S.doctorAt = now();
      } catch (e) { S.doctorError = messageOf(e); }
      renderHealth();
    }

    // Read rows forward from `after` until a short page (or `until`, a seq that is already loaded, or the cap). Returns the rows in seq order.
    async function readLog(after, node, until) {
      const out = [];
      let cursor = after;
      for (;;) {
        const query = {after: cursor, limit: LOG_FETCH};
        if (node) query.node_id = node;
        const page = arr(await api.get("/api/atoms/log", query)).filter(r => isObj(r) && finite(r.seq));
        page.forEach(r => { if (until === undefined || r.seq <= until) out.push(r); });
        if (page.length < LOG_FETCH || out.length >= MAX_FILTERED_ROWS) break;
        cursor = page[page.length - 1].seq;
        if (until !== undefined && cursor >= until) break;
      }
      return out;
    }

    function setRows(rows) {
      const l = S.log;
      l.rows = rows;
      l.last = rows.length ? rows[rows.length - 1].seq : l.last;
      if (!l.node) l.nodes = distinct(l.nodes.concat(rows.map(r => r.node_id)));
    }

    async function loadLog() {
      const l = S.log;
      try {
        if (l.node) {
          const rows = await readLog(0, l.node);
          l.after = 0;
          l.capped = rows.length >= MAX_FILTERED_ROWS;
          setRows(rows);
          l.canLoadOlder = false;
        } else {
          const info = S.info || await api.get("/api/ops/info");
          if (!S.info) S.info = info;
          const lastSeq = isObj(info.atom_log) && finite(info.atom_log.last_seq) ? info.atom_log.last_seq : 0;
          l.after = Math.max(0, lastSeq - WINDOW);
          l.capped = false;
          setRows(await readLog(l.after, ""));
          l.canLoadOlder = l.after > 0;
        }
        l.error = "";
        l.loaded = true;
      } catch (e) { l.error = messageOf(e); }
      renderLog();
    }

    async function loadMoreLog() {                   // rows newer than the newest one loaded
      const l = S.log;
      if (!l.loaded) return loadLog();
      try {
        const fresh = await readLog(l.last, l.node);
        if (fresh.length) setRows(l.rows.concat(fresh.filter(r => r.seq > l.last)));
        l.error = "";
      } catch (e) { l.error = messageOf(e); }
      renderLog();
    }

    async function loadOlder() {
      const l = S.log;
      if (l.node || l.after <= 0) return;
      const from = Math.max(0, l.after - WINDOW);
      try {
        const older = await readLog(from, "", l.after);
        const have = new Set(l.rows.map(r => r.seq));
        l.rows = older.filter(r => !have.has(r.seq)).concat(l.rows);
        l.nodes = distinct(l.nodes.concat(l.rows.map(r => r.node_id)));
        l.after = from;
        l.canLoadOlder = from > 0;
        l.error = "";
      } catch (e) { l.error = messageOf(e); }
      renderLog();
    }

    async function openCard(seq) {
      const l = S.log;
      const row = l.rows.find(r => r.seq === seq);
      if (!row) return;
      if (l.selected === seq) { l.selected = null; l.cardHtml = ""; renderLog(); return; }
      l.selected = seq;
      let atom = null;
      try { atom = await api.get("/api/atoms/" + encodeURIComponent(row.atom_id)); } catch (e) { atom = null; }
      if (l.selected !== seq) return;                 // another row was opened while this one loaded
      const fn = o.fnode && typeof o.fnode.atomHtml === "function" ? o.fnode.atomHtml : null;
      l.cardHtml = cardHtml(row, atom, fn);
      renderLog();
    }

    function refreshAll() { return Promise.all([loadUsage(), loadStatus(), loadInfo(), loadMoreLog(), now() - S.doctorAt >= DOCTOR_POLL_MS ? loadDoctor(false) : null]); }

    /* ---- the diagnostics download */
    async function download() {
      if (S.downloading) return;
      S.downloading = true;
      S.downloadError = "";
      renderHealth();
      try {
        const res = await o.fetch("/api/ops/diagnostics", {headers: {"X-Sutra-Token": o.token || ""}, cache: "no-store"});
        if (!res.ok) {
          let words = "The app answered " + res.status + ".";
          try { const body = await res.json(); if (body && body.error && body.error.message) words = clean(body.error.message); } catch (e) { /* not JSON */ }
          throw new Error(words);
        }
        const blob = await res.blob();
        const header = res.headers && typeof res.headers.get === "function" ? res.headers.get("content-disposition") || "" : "";
        const named = /filename="([^"]+)"/.exec(header);
        o.save(blob, named ? named[1] : "sutra-pro-diagnostics.zip");
      } catch (e) { S.downloadError = "Could not prepare the diagnostics: " + messageOf(e); }
      S.downloading = false;
      renderHealth();
    }

    /* ---- events */
    function coalesce(fn, ms) {
      if (o.events && typeof o.events.coalesce === "function") return o.events.coalesce(fn, ms);
      return fn;
    }
    const usageSoon = coalesce(() => { loadUsage(); loadStatus(); loadInfo(); }, USAGE_COALESCE_MS);
    const logSoon = coalesce(() => { loadMoreLog(); loadInfo(); }, USAGE_COALESCE_MS);
    const statusSoon = coalesce(() => { loadStatus(); loadInfo(); }, USAGE_COALESCE_MS);

    function onEvent(type) {
      if (type === "usage.recorded") usageSoon();
      else if (type === "atom.updated") logSoon();
      else if (type === "connector.health" || type === "connector.switch" || type === "connector.mode" || type === "task.updated") statusSoon();
      else if (type === "server.resync") refreshAll();
    }

    /* ---- clicks and filters */
    function onClick(e) {
      const target = e.target && e.target.closest ? e.target.closest("[data-act]") : null;
      if (!target) {
        const row = e.target && e.target.closest ? e.target.closest("tr[data-seq]") : null;
        if (row) openCard(Number(row.dataset.seq));
        return;
      }
      const act = target.dataset.act;
      if (act === "period") { S.period = hasOwn({today: 1, "7d": 1, "30d": 1, all: 1}, target.dataset.period) ? target.dataset.period : DEFAULT_PERIOD; loadUsage(); }
      else if (act === "stub") { S.stub = !!target.checked; loadUsage(); }
      else if (act === "log-page") { S.log.page += target.dataset.dir === "older" ? 1 : -1; renderLog(); }
      else if (act === "log-older") loadOlder();
      else if (act === "open-card") openCard(Number(target.dataset.seq));
      else if (act === "clear-filters") {
        const hadNode = !!S.log.node;
        Object.assign(S.log, {node: "", state: "", check: "", from: "", to: "", page: 0});
        if (hadNode) loadLog(); else renderLog();
      } else if (act === "doctor-refresh") loadDoctor(true);
      else if (act === "download") download();
    }

    function onChange(e) {
      const t = e.target;
      if (!t || !t.dataset || !t.dataset.filter) return;
      const name = t.dataset.filter;
      if (!["node", "state", "check", "from", "to"].includes(name)) return;
      const before = S.log.node;
      S.log[name] = clean(t.value);
      S.log.page = 0;
      S.log.selected = null;
      S.log.cardHtml = "";
      if (name === "node" && S.log.node !== before) loadLog(); else renderLog();
    }

    /* ---- start and stop */
    function start() {
      const rootEl = el("console-root");
      if (rootEl) {
        rootEl.addEventListener("click", onClick);
        rootEl.addEventListener("change", onChange);
      }
      renderAll();
      if (o.events && typeof o.events.connect === "function") {
        stream = o.events.connect({url: "/api/events", topics: ["usage", "atom", "connector", "task"], onEvent: onEvent,
          onState: st => { S.live = st; renderState(); }, pollFn: refreshAll, pollMs: POLL_MS});
      }
      return Promise.all([loadUsage(), loadStatus(), loadInfo(), loadDoctor(false)]).then(loadLog);
    }

    function stop() {
      if (stream && typeof stream.close === "function") stream.close();
      stopped = true;
      stream = null;
      [usageSoon, logSoon, statusSoon].forEach(f => { if (f && typeof f.cancel === "function") f.cancel(); });
    }

    return {start, stop, state: () => S, loadUsage, loadStatus, loadInfo, loadDoctor, loadLog, loadMoreLog, loadOlder, openCard, download, onEvent, onClick, onChange, refreshAll, isStopped: () => stopped};
  }

  /* ---------------------------------------------------------------- the page */
  function saveBlob(blob, name) {
    const url = root.URL.createObjectURL(blob);
    const a = root.document.createElement("a");
    a.href = url;
    a.download = name;
    root.document.body.appendChild(a);
    a.click();
    a.remove();
    root.setTimeout(() => root.URL.revokeObjectURL(url), 10000);
  }

  function boot() {
    const ctx = root.SutraCtx;
    if (!ctx || !ctx.api) return null;
    const page = create({doc: root.document, api: ctx.api, events: root.SutraEvents, fnode: root.FnodeView, fetch: root.fetch.bind(root),
      token: ctx.boot && ctx.boot.token, save: saveBlob});
    root.ConsolePage = page;
    page.start().catch(e => { if (root.console) root.console.error("ConsoleView: start failed", e); });
    return page;
  }

  const ConsoleView = {
    PERIODS, STATES, WINDOW, LOG_PAGE_SIZE, POLL_MS, USAGE_COALESCE_MS, DEFAULT_PERIOD, esc, money, tokens, bytesText, durationText, untilText, safePath, periodBar, usageHtml, connectorsHtml,
    nextReset, filterRows, pageRows, logHtml, cardHtml, healthHtml, create, boot,
  };
  if (typeof module === "object" && module !== null && module.exports) module.exports = ConsoleView;
  else {
    root.ConsoleView = ConsoleView;
    const start = () => { if (root.document && root.document.getElementById("console-root")) boot(); };
    if (root.document && root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(globalThis);
