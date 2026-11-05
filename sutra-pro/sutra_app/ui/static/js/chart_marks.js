/* chart_marks.js - the pure core of the Org chart view, part 3 of 3 (work package UI-4; docs/design/ui.md sections 6.3, 7 and 10;
   S2-models-01, S3-web-04).

   The org chart is one tree that only the chat agent changes (D67, UI-D7). This file turns the chart into the same graph shape the
   Workflow graph uses (toGraph), says which nodes the selected change touched (marks) and writes the change log (logHtml). The tree is
   drawn by GraphLayout.layout and GraphRender.svg; the marks go to svg() in `view.marks`.

   A change is ChartChangeOut: {seq, id, at, actor, decision, status, summary, reason, task_id, task_title, revision, added, moved,
   archived, reused}. Only a change whose status is `applied` marks the chart; for the others (pending_approval, rejected, stale,
   failed) the node lists hold a plan that was not carried out, so they mark nothing.

   A classic script with ONE global, ChartMarks (see sutra_ctx.js for why); it needs no other script, and in node it is module.exports. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;                 // true only for a number that is not NaN or infinite (it does not convert)
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const idOrNull = v => (typeof v === "string" && v !== "" ? v : null);
  const clean = v => text(v).replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim();
  const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  const esc = s => String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
  const DOT = " \u00b7 ";

  /* ---------------------------------------------------------------- the chart as a graph */
  // toGraph(orgChart) -> {nodes, links, cross}: the shape GraphLayout.validate answers with, so layout() and GraphRender take it as it is.
  // orgChart is ChartView {version, nodes: [{id, kind, name, purpose, parent_id, position}]} (S2-models-01). name becomes the label,
  // purpose the detail, parent_id the parent; siblings come in `position` order (a missing position is 0; equal positions keep their order).
  // Every node is idle and has no cross links. A repeated id or a loop of parents is left for layout() to repair with a warning. Throws a
  // TypeError when the argument is not a chart at all, so a view can keep its last good picture. Not changed: the argument.
  function toGraph(chart) {
    if (!isObj(chart) || !Array.isArray(chart.nodes)) throw new TypeError("ChartMarks.toGraph: the chart must be an object with a nodes array");
    const place = n => (finite(n.position) ? n.position : 0);
    const nodes = chart.nodes
      .filter(isObj)
      .sort((a, b) => place(a) - place(b))        // the sort is stable: equal positions keep the order they were sent in
      .map(n => {
        const id = text(n.id);
        return {
          id, kind: text(n.kind), label: text(n.name).trim() === "" ? id : text(n.name), status: "idle", detail: text(n.purpose),
          parent: idOrNull(n.parent_id), chat_session_id: null, org_node_id: id, dept_id: n.kind === "department" ? id : null,
          task_id: null, fn: null, step_ref: null, version: null, meta: {},
        };
      });
    const ids = new Set(nodes.map(n => n.id));
    const links = nodes.filter(n => n.parent !== n.id && ids.has(n.parent)).map(n => ({from: n.parent, to: n.id, kind: "contains"}));
    return {nodes, links, cross: []};
  }

  /* ---------------------------------------------------------------- the changes */
  // The changes that have a seq, newest first (equal seqs keep their order: the sort is stable).
  function newestFirst(changes) {
    return (Array.isArray(changes) ? changes : []).filter(c => isObj(c) && finite(c.seq)).sort((a, b) => b.seq - a.seq);
  }

  // The selected change: the one with seq `wanted` (a number, or the digits of one), else the newest when none is asked for. A seq that
  // no change has selects nothing (undefined).
  function selectedOf(sorted, wanted) {
    if (wanted === undefined || wanted === null) return sorted[0];
    const seq = typeof wanted === "string" && /^\d+$/.test(wanted) ? Number(wanted) : wanted;
    return sorted.find(c => c.seq === seq);
  }

  const BY_WORDS = freeze({add: "added by ", move: "moved by ", reuse: "reused by "});

  // marks(changes, changeSeq) -> {[orgNodeId]: {mark: "add"|"move"|"reuse", tag}}
  // The nodes the selected change touched (changeSeq, default the newest): its `added` ids are marked "add", `moved` "move" and `reused`
  // "reuse" (a node in two lists takes the first). The tag reads "added by task: Coffee shop landing page", or "added by change 12" when
  // the change has no task title. A change that is not `applied` marks nothing; neither does `archived`, which is no longer in the chart.
  function marks(changes, changeSeq) {
    const change = selectedOf(newestFirst(changes), changeSeq);
    if (change === undefined || change.status !== "applied") return {};
    const title = clean(change.task_title);
    const where = title !== "" ? "task: " + title : "change " + change.seq;
    const entries = [];
    const seen = new Set();
    [["added", "add"], ["moved", "move"], ["reused", "reuse"]].forEach(([key, mark]) => {
      (Array.isArray(change[key]) ? change[key] : []).forEach(id => {
        if (typeof id !== "string" || id === "" || seen.has(id)) return;
        seen.add(id);
        entries.push([id, {mark, tag: BY_WORDS[mark] + where}]);
      });
    });
    return Object.fromEntries(entries);            // fromEntries, so an id such as "__proto__" is a key like any other
  }

  /* ---------------------------------------------------------------- the log */
  const two = n => (n < 10 ? "0" : "") + n;
  // The clock time of an ISO instant in the viewer's own time zone: "09:12" and "2026-11-04 09:12", or null for a value that is no date.
  function clockOf(at) {
    const when = new Date(typeof at === "string" ? at : NaN);
    if (Number.isNaN(when.getTime())) return null;
    const hm = two(when.getHours()) + ":" + two(when.getMinutes());
    return {hm, full: when.getFullYear() + "-" + two(when.getMonth() + 1) + "-" + two(when.getDate()) + " " + hm};
  }

  const DECISIONS = freeze(["reuse", "add", "rearrange"]);
  const STATUSES = freeze(["applied", "pending_approval", "rejected", "stale", "failed"]);
  // The words after a change that did not change the chart.
  const statusNote = status => (status === "applied" ? "" : (status === "pending_approval" ? "waiting for your yes or no" : "not applied"));

  // logHtml(changes, selectedSeq) -> the html of the change log, newest change first:
  //   <div class="chglog"> <div class="chgrow" data-change="12" role="button" tabindex="0" aria-pressed> ...
  // A row reads "Change 12 . Added the Web team . 09:12 . for 'Coffee shop landing page'", then the status word when the change was not
  // applied; the selected row (selectedSeq, default the newest) has .sel and, under it, the change's reason. The rows are the click
  // targets: a click selects a change, and the view paints the log and the marks again.
  function logHtml(changes, selectedSeq) {
    const sorted = newestFirst(changes);
    const selected = selectedOf(sorted, selectedSeq);
    const rows = sorted.map(c => {
      const when = clockOf(c.at);
      const title = clean(c.task_title);
      const summary = clean(c.summary);
      const note = statusNote(c.status);
      const reason = clean(c.reason);
      const isSelected = c === selected;
      const segments = [esc("Change " + c.seq)];
      if (summary !== "") segments.push(esc(summary));
      if (when !== null) segments.push('<time datetime="' + esc(c.at) + '" title="' + esc(when.full) + '">' + when.hm + "</time>");
      if (title !== "") segments.push(esc("for '" + title + "'"));
      if (note !== "") segments.push('<span class="chgstatus">' + note + "</span>");
      const classes = ["chgrow", DECISIONS.includes(c.decision) ? "dec-" + c.decision : "", STATUSES.includes(c.status) ? "st-" + c.status : "st-unknown", isSelected ? "sel" : ""].filter(Boolean).join(" ");
      return '<div class="' + classes + '" data-change="' + c.seq + '" role="button" tabindex="0" aria-pressed="' + isSelected + '">' + segments.join(DOT) +
        (isSelected && reason !== "" ? '<div class="chgreason">' + esc(reason) + "</div>" : "") + "</div>";
    });
    return '<div class="chglog" role="group" aria-label="Changes to the org chart">' + (rows.length ? rows.join("") : '<p class="chgnone">No changes yet.</p>') + "</div>";
  }

  const ChartMarks = {toGraph, marks, logHtml};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ChartMarks;
  else root.ChartMarks = ChartMarks;
})(globalThis);
