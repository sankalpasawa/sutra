/* project_store.js - the state of the project page (MAN-13, D326; docs/design/multi-agent-nodes/architecture.md section 6).

   The first of the page's three layers (store, view, page glue), a pure state machine: no DOM, no timer, no fetch, so `node --test` runs it.

     snapshot   `GET /api/projects/{id}`: the project, its nodes, edges, spend, open questions and cards. It is replaced whole on every refetch (events are invalidations).
     messages   `GET /api/projects/{id}/messages?after=k`: numbered 1, 2, 3 ... with no gap (D297). A batch that does not start at the next number is NOT applied: the page asks again
                from its last whole number ("gap"). A number seen twice is ignored, so a replay is harmless.
     audit      `GET /api/projects/{id}/audit?after=k`: rows by `seq`, appended once.

   Nothing here trusts the wire: a wrong shape is an `error` in the state, never an exception, and the last good snapshot stays on the screen.

   A classic script with ONE global, ProjectStore; in node it is module.exports. */
(function (root) {
  "use strict";

  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const arr = v => (Array.isArray(v) ? v : []);
  const whole = v => Number.isInteger(v) && v >= 0;
  const DECIDED_BY = "decided_by rule:decide_for_me";       // the start of the reason of an audit row the rule table answered (gatekeeper.DECIDE_FOR_ME)
  const KEEP = 500;                                        // the most rows of audit and messages the page keeps (the newest)

  /* ---------------------------------------------------------------- selectors (pure) */
  // The rows Sutra answered for the owner (Decide for me): which question, the answer and the rule's own words. Oldest first, as the audit is.
  function decidedList(rows) {
    return arr(rows).filter(r => isObj(r) && r.action === "gate.decided" && typeof r.reason === "string" && r.reason.startsWith(DECIDED_BY))
      .map(r => ({seq: r.seq, at: r.at, node_id: r.node_id || "", decision: r.decision === "deny" ? "no" : "yes", why: r.reason.slice(DECIDED_BY.length).replace(/^[:\s]+/, "").replace(/^[a-z0-9_]+:\s*/, "")}));        // the rule's own name is not for the owner: only what it said
  }

  // The depth of each node: 0 when nothing comes before it, else one more than its deepest earlier node. Edges of both kinds count (a delay is still "after"). A cycle cannot be drawn:
  // the walk stops at the node it is already on, so it never loops.
  function depths(nodes, edges) {
    const ids = arr(nodes).map(n => n.id);
    const before = {};
    ids.forEach(id => { before[id] = []; });
    arr(edges).forEach(e => { if (isObj(e) && before[e.to] && before[e.from]) before[e.to].push(e.from); });
    const out = {};
    const walking = {};
    const go = id => {
      if (id in out) return out[id];
      if (walking[id]) return 0;
      walking[id] = true;
      out[id] = before[id].length ? 1 + Math.max.apply(null, before[id].map(go)) : 0;
      walking[id] = false;
      return out[id];
    };
    ids.forEach(go);
    return out;
  }

  // A step's name in the owner's words: "Step a1", "The reviewer", "The planner".
  function nodeName(node) {
    if (!isObj(node)) return "A step";
    if (node.role === "reviewer") return "The reviewer";
    if (node.role === "planner") return "The planner";
    const ref = typeof node.plan_ref === "string" ? node.plan_ref.trim() : "";
    return ref ? "Step " + ref : "A step";
  }

  function create() {
    const S = {snapshot: null, messages: [], seq: 0, audit: [], auditAfter: 0, live: "offline", error: "", loaded: false};

    // Replace the snapshot. A body that is not a project (no project object, nodes not a list) is refused and the last good one stays.
    function setSnapshot(snap) {
      if (!isObj(snap) || !isObj(snap.project) || typeof snap.project.id !== "string" || !Array.isArray(snap.nodes)) {
        S.error = "That project could not be read.";
        return false;
      }
      S.snapshot = snap;
      S.error = "";
      S.loaded = true;
      return true;
    }

    // Take the next messages. Applied only when they continue the numbering; returns {applied, gap}. Rows already seen are skipped, so the same batch twice changes nothing.
    function addMessages(rows) {
      const list = arr(rows).filter(r => isObj(r) && whole(r.seq)).sort((a, b) => a.seq - b.seq);
      const fresh = list.filter(r => r.seq > S.seq);
      if (fresh.length === 0) return {applied: 0, gap: false};
      if (fresh[0].seq !== S.seq + 1) return {applied: 0, gap: true};
      let applied = 0;
      fresh.forEach(r => {
        if (r.seq === S.seq + 1) { S.messages.push(r); S.seq = r.seq; applied += 1; }
      });
      if (S.messages.length > KEEP) S.messages.splice(0, S.messages.length - KEEP);
      return {applied, gap: applied < fresh.length};
    }

    function addAudit(rows) {
      let n = 0;
      arr(rows).filter(r => isObj(r) && whole(r.seq) && r.seq > S.auditAfter).sort((a, b) => a.seq - b.seq).forEach(r => {
        S.audit.push(r);
        S.auditAfter = r.seq;
        n += 1;
      });
      if (S.audit.length > KEEP) S.audit.splice(0, S.audit.length - KEEP);
      return n;
    }

    return {
      state: () => S,
      setSnapshot, addMessages, addAudit,
      setLive: v => { S.live = v === "live" || v === "polling" ? v : "offline"; },
      setError: text => { S.error = typeof text === "string" ? text : ""; },
      // Is there a message the snapshot knows and the page has not read yet?
      behind: () => !!(S.snapshot && whole(S.snapshot.last_message_seq) && S.snapshot.last_message_seq > S.seq),
      decided: () => decidedList(S.audit),
    };
  }

  const ProjectStore = {create, decidedList, depths, nodeName, DECIDED_BY, KEEP};
  if (typeof module === "object" && module !== null && module.exports) module.exports = ProjectStore;
  else root.ProjectStore = ProjectStore;
})(globalThis);
