/* graph_layout.js - the pure core of the Workflow graph and Org chart views, part 1 of 3 (work package UI-4; docs/design/ui.md
   sections 6.1, 7 and 10; S3-web-13).

   It turns the orchestrator's GraphView into a tree plus cross links (validate), puts the tree on a page (layout) and says what changed
   between two versions of it (diff). Nothing here touches the DOM, the clock or a random number, so the same input gives the same
   bytes and a live update never reshuffles the picture. Bad data never throws: a node or link that cannot be drawn is dropped (or
   moved to the top level) and a sentence in `warnings` says why. The one exception is a value that is not a graph at all
   (validate throws a TypeError), so a view can keep its last good picture (X5).

   Part of the shape of the answer, since several files read it:
     graph    {nodes, links, cross}      nodes[]: id kind label status detail parent (id or null) chat_session_id org_node_id dept_id
                                         task_id fn step_ref version meta; sibling order is the array order
              links[]  {from, to, kind}  the tree: parent to child, kind contains, has_function or has_step (derived from `parent`)
              cross[]  {from, to, kind, label}   handoff, depends_on, speaks_to, step and any other kind
     layout   {nodes, links, edges, width, height, warnings}   the nodes of the graph in depth-first order plus x y w h depth;
              links[] {from, to, d, x1, y1, x2, y2}  edges[] {id, from, to, kind, label, d, loop, lx, ly, x1, y1, x2, y2}
   Warnings are plain sentences, not HTML: escape them before they reach a page.

   A classic script with ONE global, GraphLayout (see sutra_ctx.js for why); in node it is module.exports. graph_render.js reads the
   vocabulary and forest() from here, so load this file first. */
(function (root) {
  "use strict";

  const freeze = Object.freeze;

  /* ---------------------------------------------------------------- vocabulary (graph_render.js uses the same lists) */
  // J2's nine map words (docs/map-schema.md "Statuses"). A function node uses the first five. `archived` is a word the server never
  // sends (a merged-away node is deleted); a node that carries it is not drawn.
  const STATUSES = freeze(["idle", "running", "waiting", "waiting_on_you", "fault", "filed", "done_unchecked", "left_open", "not_made"]);
  const ARCHIVED = "archived";
  const KINDS = freeze(["root", "department", "division", "function", "step"]);
  const TREE_KINDS = freeze(["contains", "has_function", "has_step"]);       // the edges that build the tree (derived on read)
  const CROSS_KINDS = freeze(["handoff", "depends_on", "speaks_to", "step"]); // the stored links; any other kind is drawn as `step`
  // The size of a box by kind (section 6.1; a function chip is 168 wide so that "Identity . 1 open . 5 closed" fits).
  const SIZES = freeze({
    root: freeze({w: 96, h: 34}),
    department: freeze({w: 168, h: 54}),
    division: freeze({w: 150, h: 46}),
    function: freeze({w: 168, h: 50}),
    step: freeze({w: 140, h: 40}),
  });
  // pad: the margin round the picture; slot: the width one leaf takes; rowGap: the space between the tallest box of one row and the top
  // of the next; maxRise: how high a link between two boxes of one row may arc.
  const DEFAULTS = freeze({pad: 40, slot: 178, rowGap: 78, maxRise: 60});
  const PORT_GAP = 12;           // spacing of the points where cross links meet a box edge (the tree links own the middle)
  const PORT_MARGIN = 10;        // and how far from a corner they stay
  const ARC_FLOOR = 2;           // an arc never rises above this y

  const STATUS_SET = new Set(STATUSES);
  const KIND_SET = new Set(KINDS);
  const TREE_SET = new Set(TREE_KINDS);

  /* ---------------------------------------------------------------- small helpers */
  const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
  const finite = Number.isFinite;                 // true only for a number that is not NaN or infinite (it does not convert)
  const text = v => (typeof v === "string" ? v : (finite(v) ? String(v) : ""));
  const idOrNull = v => (typeof v === "string" && v !== "" ? v : null);
  const positive = v => finite(v) && v > 0;
  const nonNegative = v => finite(v) && v >= 0;
  const round1 = n => Math.round(n * 10) / 10;
  const num = n => String(round1(n));
  const point = (x, y) => num(x) + "," + num(y);
  const quote = s => '"' + s + '"';
  const linkKey = (kind, from, to) => JSON.stringify([kind, from, to]);       // one key for one link, whatever the words are
  // The largest and the smallest number of a list (undefined for an empty one). Math.max(...list) would overflow the stack on a long list.
  const largest = list => list.reduce((a, b) => Math.max(a, b), list[0]);
  const smallest = list => list.reduce((a, b) => Math.min(a, b), list[0]);

  // "M x,y C x,y x,y x,y": one cubic from P to Q.
  const cubic = (px, py, c1x, c1y, c2x, c2y, qx, qy) =>
    "M" + point(px, py) + " C" + point(c1x, c1y) + " " + point(c2x, c2y) + " " + point(qx, qy);

  /* ---------------------------------------------------------------- the tree */
  // Keeps the first node of each id. A node without a string id, or whose id was seen, is dropped with a warning.
  function indexNodes(list, warnings) {
    const seen = new Set();
    const kept = [];
    list.forEach((n, i) => {
      const id = isObj(n) && typeof n.id === "string" ? n.id : "";
      if (id === "") {
        warnings.push("node " + (i + 1) + " has no id and is not drawn");
        return;
      }
      if (seen.has(id)) {
        warnings.push("node " + quote(id) + " appears twice; the later one is not drawn");
        return;
      }
      seen.add(id);
      kept.push(n);
    });
    return kept;
  }

  // Breaks every loop of parents at its lowest id (that node becomes a root), so the walk up from any node ends.
  function cutLoops(list, parent, warnings) {
    const settled = new Set();                    // nodes whose walk up has ended
    list.forEach(n => {
      const walk = [];
      const onWalk = new Set();
      let cur = n.id;
      while (cur !== null && !settled.has(cur) && !onWalk.has(cur)) {
        onWalk.add(cur);
        walk.push(cur);
        cur = parent.get(cur);
      }
      if (onWalk.has(cur)) {                      // the walk came back to a node of its own: a loop (cur is null when it reached a root)
        const from = walk.indexOf(cur);
        const ring = walk.filter((id, i) => i >= from);
        const lowest = ring.slice().sort()[0];    // the default sort compares as strings, so this is the lowest id
        parent.set(lowest, null);
        warnings.push("nodes " + ring.map(quote).join(", ") + " are each other's parents; " + quote(lowest) + " is drawn as a root");
      }
      walk.forEach(id => settled.add(id));
    });
  }

  // forest(nodes): the tree in the `parent` fields of `nodes` (an id or null), made safe. A node without an id or with a repeated id is
  // dropped; a missing, own or looping parent makes the node a root. Returns
  //   nodes     the kept nodes in their order, as copies with the parent that stands
  //   roots     ids with no parent, in order          children  Map id -> ids, in order
  //   order     all ids, depth first (a parent, then each child's subtree)           depth  Map id -> 0 for a root, 1 below it, ...
  //   warnings  one sentence per repair
  // Iterative, so a very deep chain cannot overflow the stack.
  function forest(items) {
    const warnings = [];
    const list = indexNodes(Array.isArray(items) ? items : [], warnings);
    const ids = new Set(list.map(n => n.id));
    const parent = new Map();
    list.forEach(n => {
      let p = idOrNull(n.parent);
      if (p === n.id) {
        warnings.push("node " + quote(n.id) + " is its own parent; it is drawn as a root");
        p = null;
      } else if (p !== null && !ids.has(p)) {
        warnings.push("node " + quote(n.id) + " names parent " + quote(p) + ", which is not drawn; it is drawn as a root");
        p = null;
      }
      parent.set(n.id, p);
    });
    cutLoops(list, parent, warnings);
    const children = new Map(list.map(n => [n.id, []]));
    const roots = [];
    list.forEach(n => {
      const p = parent.get(n.id);
      if (p === null) roots.push(n.id);
      else children.get(p).push(n.id);
    });
    const order = [];
    const depth = new Map();
    const stack = roots.slice().reverse().map(id => [id, 0]);
    while (stack.length) {
      const [id, level] = stack.pop();
      order.push(id);
      depth.set(id, level);
      const kids = children.get(id);
      for (let i = kids.length - 1; i >= 0; i--) stack.push([kids[i], level + 1]);
    }
    return {nodes: list.map(n => Object.assign({}, n, {parent: parent.get(n.id)})), roots, children, order, depth, warnings};
  }

  /* ---------------------------------------------------------------- validate */
  // validate(graphView) -> {graph: {nodes, links, cross}, warnings}
  //
  // graphView is ORCH's GraphView {version, chart_version, nodes: [GraphNodeOut], edges: [{src, dst, kind, label}]}. The parent of a node
  // is the `src` of its incoming contains, has_function or has_step edge; every other edge is a cross link. Nodes keep the order they
  // came in (the server sends a depth-first order, so that is the sibling order). Not changed: the argument.
  //   - `archived` nodes are not drawn, and neither are the links to them (no warning: the server never sends the word).
  //   - An unknown status is idle and an unknown kind is a step, each with a warning; an empty label falls back to the id.
  //   - A repeated id, an id-less node, a link to a node that is not there, a second parent, a link from a node to itself, a repeated
  //     cross link and a loop of parents each give a warning and are repaired, never thrown.
  function validate(view) {
    if (!isObj(view) || !Array.isArray(view.nodes)) throw new TypeError("GraphLayout.validate: the graph must be an object with a nodes array");
    if (view.edges !== undefined && view.edges !== null && !Array.isArray(view.edges)) throw new TypeError("GraphLayout.validate: edges must be an array");
    const warnings = [];

    const archived = new Set();
    const nodes = [];
    indexNodes(view.nodes, warnings).forEach(n => {
      if (n.status === ARCHIVED) {
        archived.add(n.id);
        return;
      }
      let status = n.status;
      if (!STATUS_SET.has(status)) {
        warnings.push("node " + quote(n.id) + " has status " + quote(text(status)) + "; it is drawn as idle");
        status = "idle";
      }
      let kind = n.kind;
      if (!KIND_SET.has(kind)) {
        warnings.push("node " + quote(n.id) + " has kind " + quote(text(kind)) + "; it is drawn as a step");
        kind = "step";
      }
      nodes.push({
        id: n.id, kind, label: text(n.label).trim() === "" ? n.id : text(n.label), status, detail: text(n.detail),
        chat_session_id: idOrNull(n.chat_session_id), org_node_id: idOrNull(n.org_node_id), dept_id: idOrNull(n.dept_id),
        task_id: idOrNull(n.task_id), fn: idOrNull(n.fn), step_ref: idOrNull(n.step_ref),
        version: finite(n.version) ? n.version : null,
        meta: isObj(n.meta) ? n.meta : {},
      });
    });

    const byId = new Map(nodes.map(n => [n.id, n]));
    const treeKind = new Map();                   // child id -> the edge kind that made its parent
    const cross = [];
    const seenCross = new Set();
    (view.edges || []).forEach((e, i) => {
      const src = isObj(e) && typeof e.src === "string" ? e.src : "";
      const dst = isObj(e) && typeof e.dst === "string" ? e.dst : "";
      if (src === "" || dst === "") {
        warnings.push("link " + (i + 1) + " has no source or no target and is not drawn");
        return;
      }
      if (archived.has(src) || archived.has(dst)) return;
      let kind = typeof e.kind === "string" ? e.kind : "";
      if (kind === "") {
        warnings.push("link " + quote(src) + " -> " + quote(dst) + " has no kind; it is drawn as a plain link");
        kind = "step";
      }
      const label = "link " + quote(src) + " -> " + quote(dst) + " (" + kind + ")";
      if (!byId.has(src) || !byId.has(dst)) {
        warnings.push(label + " names a node that is not in the graph and is not drawn");
        return;
      }
      if (src === dst) {
        warnings.push(label + " joins a node to itself and is not drawn");
        return;
      }
      if (TREE_SET.has(kind)) {
        if (treeKind.has(dst)) {
          warnings.push(label + " gives " + quote(dst) + " a second parent; " + quote(byId.get(dst).parent) + " stays");
          return;
        }
        byId.get(dst).parent = src;
        treeKind.set(dst, kind);
        return;
      }
      const key = linkKey(kind, src, dst);
      if (seenCross.has(key)) {
        warnings.push(label + " appears twice; the later one is not drawn");
        return;
      }
      seenCross.add(key);
      cross.push({from: src, to: dst, kind, label: text(e.label)});
    });

    const tree = forest(nodes);
    const links = tree.nodes.filter(n => n.parent !== null).map(n => ({from: n.parent, to: n.id, kind: treeKind.get(n.id)}));
    return {graph: {nodes: tree.nodes, links, cross}, warnings: warnings.concat(tree.warnings)};
  }

  /* ---------------------------------------------------------------- layout */
  function settings(opts) {
    const o = isObj(opts) ? opts : {};
    const sizes = {};
    KINDS.forEach(kind => {
      const given = isObj(o.sizes) && isObj(o.sizes[kind]) ? o.sizes[kind] : {};
      sizes[kind] = {w: positive(given.w) ? given.w : SIZES[kind].w, h: positive(given.h) ? given.h : SIZES[kind].h};
    });
    return {
      pad: nonNegative(o.pad) ? o.pad : DEFAULTS.pad,
      slot: positive(o.slot) ? o.slot : DEFAULTS.slot,
      rowGap: nonNegative(o.rowGap) ? o.rowGap : DEFAULTS.rowGap,
      maxRise: nonNegative(o.maxRise) ? o.maxRise : DEFAULTS.maxRise,
      sizes,
    };
  }

  // The offset along a box edge of each cross-link end that meets it. The ends on one side of one box go left of the middle when their
  // other end is left of it, right otherwise, nearest the middle first; the middle stays free for the tree links. Same-row arcs are
  // ordered the other way round (the longest arc innermost) so that arcs from one box nest instead of crossing.
  function assignPorts(ports) {
    ports.forEach(({node, list}) => {
      [[list.filter(p => p.other >= node.cx), false], [list.filter(p => p.other < node.cx), true]].forEach(([group, left]) => {
        const reach = p => Math.abs(p.other - node.cx);
        const order = p => (p.arc ? -reach(p) : reach(p));        // an arc: the farthest first; any other link: the nearest first
        // Two ends at the very same place (two links between one pair of boxes) keep the order the links came in (the sort is stable),
        // except in the left-hand group of S-curves, where it is reversed, so that the links run side by side instead of crossing.
        group.sort((p, q) => order(p) - order(q) || (!p.arc && left ? q.index - p.index : 0));
        const gap = Math.min(PORT_GAP, Math.max(0, node.n.w / 2 - PORT_MARGIN) / group.length);
        group.forEach((p, rank) => {
          p.join[p.source ? "fromOffset" : "toOffset"] = (left ? -1 : 1) * (rank + 1) * gap;
        });
      });
    });
  }

  // layout(graph, opts) -> {nodes, links, edges, width, height, warnings}
  //
  // graph is validate's `graph` (or any {nodes, cross} with the same fields, such as ChartMarks.toGraph's). opts {pad, slot, rowGap,
  // maxRise, sizes: {kind: {w, h}}} replace the defaults; a value that is not a usable number is ignored.
  //   y = pad + depth * (tallest box + rowGap); x by post-order: a leaf takes one slot (its box is centred in it), a parent is centred
  //   over its first and last child, trees sit side by side with one empty slot between. The whole picture is then moved so that its
  //   leftmost box starts at x = pad, as its top row starts at y = pad; width and height add one more pad on the far side.
  //   Tree links are S-curves from the bottom of a parent to the top of a child. A cross link between two rows is an S-curve between
  //   the facing edges; between two boxes of one row it is an arc rising min(maxRise, 0.3 * the distance) above both tops (never above
  //   y 2). `loop` is true for a link that has a reverse twin of the same kind.
  function layout(graph, opts) {
    const o = settings(opts);
    const g = isObj(graph) ? graph : {};
    const tree = forest(g.nodes);
    const warnings = tree.warnings.slice();
    const byId = new Map(tree.nodes.map(n => [n.id, n]));
    const sizeOf = kind => (hasOwn(o.sizes, kind) ? o.sizes[kind] : o.sizes.step);

    const pitch = largest(tree.nodes.map(n => sizeOf(n.kind).h)) + o.rowGap;        // NaN for no nodes, which have no rows

    // leaves take slots left to right (depth-first order meets them in that order); a parent sits between its first and last child
    const slotOf = new Map();
    let next = 0;
    tree.order.forEach(id => {
      if (tree.depth.get(id) === 0) next += 1;                             // one empty slot before each tree (the shift below undoes the first)
      if (tree.children.get(id).length === 0) slotOf.set(id, next++);
    });
    tree.order.slice().reverse().forEach(id => {                           // children before their parent
      const kids = tree.children.get(id);
      if (kids.length > 0) slotOf.set(id, (slotOf.get(kids[0]) + slotOf.get(kids[kids.length - 1])) / 2);
    });

    // the middle of each box on the slot grid, then the whole picture moved so that its leftmost box edge sits at x = pad
    const middle = id => slotOf.get(id) * o.slot;
    const shift = o.pad - smallest(tree.order.map(id => middle(id) - sizeOf(byId.get(id).kind).w / 2));      // NaN for no nodes, which have no use for it

    const placed = new Map();                     // id -> {n: the laid out node, cx: the middle of its box}
    const nodes = tree.order.map(id => {
      const size = sizeOf(byId.get(id).kind);
      const depth = tree.depth.get(id);
      const cx = middle(id) + shift;
      const n = Object.assign({}, byId.get(id), {depth, x: round1(cx - size.w / 2), y: round1(o.pad + depth * pitch), w: size.w, h: size.h});
      placed.set(id, {n, cx});
      return n;
    });
    const width = nodes.length === 0 ? 2 * o.pad : largest(nodes.map(n => n.x + n.w)) + o.pad;
    const height = nodes.length === 0 ? 2 * o.pad : largest(nodes.map(n => n.y + n.h)) + o.pad;

    const links = nodes.filter(n => n.parent !== null).map(n => {
      const a = placed.get(n.parent);
      const b = placed.get(n.id);
      const x1 = a.cx, y1 = a.n.y + a.n.h, x2 = b.cx, y2 = b.n.y, mid = (y1 + y2) / 2;
      return {from: n.parent, to: n.id, d: cubic(x1, y1, x1, mid, x2, mid, x2, y2), x1: round1(x1), y1: round1(y1), x2: round1(x2), y2: round1(y2)};
    });

    // cross links: which links stand, where they meet the boxes, then their paths
    const joins = [];
    const seen = new Set();
    (Array.isArray(g.cross) ? g.cross : []).forEach(e => {
      const from = isObj(e) && typeof e.from === "string" ? e.from : "";
      const to = isObj(e) && typeof e.to === "string" ? e.to : "";
      const kind = isObj(e) && typeof e.kind === "string" && e.kind !== "" ? e.kind : "step";
      const label = "link " + quote(from) + " -> " + quote(to) + " (" + kind + ")";
      const a = placed.get(from);
      const b = placed.get(to);
      if (!a || !b) {
        warnings.push(label + " names a node that is not drawn and is skipped");
        return;
      }
      if (a === b) {
        warnings.push(label + " joins a node to itself and is skipped");
        return;
      }
      const key = linkKey(kind, from, to);
      if (seen.has(key)) {
        warnings.push(label + " appears twice; the later one is skipped");
        return;
      }
      seen.add(key);
      const rows = Math.sign(b.n.depth - a.n.depth);                      // 1: b is a row below a, -1: above it, 0: in the same row (an arc)
      joins.push({from, to, kind, label: text(e.label), a, b, arc: rows === 0, fromSide: rows > 0 ? "bottom" : "top", toSide: rows < 0 ? "bottom" : "top"});
    });

    const ports = new Map();
    const addPort = (box, side, port) => {
      const key = JSON.stringify([box.n.id, side]);
      if (!ports.has(key)) ports.set(key, {node: box, list: []});
      ports.get(key).list.push(port);
    };
    joins.forEach((join, index) => {
      addPort(join.a, join.fromSide, {join, index, source: true, other: join.b.cx, arc: join.arc});
      addPort(join.b, join.toSide, {join, index, source: false, other: join.a.cx, arc: join.arc});
    });
    assignPorts(ports);

    const edges = joins.map(join => {
      const x1 = join.a.cx + join.fromOffset, y1 = join.fromSide === "top" ? join.a.n.y : join.a.n.y + join.a.n.h;
      const x2 = join.b.cx + join.toOffset, y2 = join.toSide === "top" ? join.b.n.y : join.b.n.y + join.b.n.h;
      let d;
      let ly;
      if (join.arc) {
        const rise = Math.max(0, Math.min(o.maxRise, 0.3 * Math.abs(x2 - x1), y1 - ARC_FLOOR));
        const lift = rise * 4 / 3;              // control points this high make the top of the curve exactly `rise` above the tops
        d = cubic(x1, y1, x1, y1 - lift, x2, y2 - lift, x2, y2);
        ly = y1 - rise;
      } else {
        const mid = (y1 + y2) / 2;
        d = cubic(x1, y1, x1, mid, x2, mid, x2, y2);
        ly = mid;
      }
      return {id: join.kind + ":" + join.from + ">" + join.to, from: join.from, to: join.to, kind: join.kind, label: join.label, d,
        loop: seen.has(linkKey(join.kind, join.to, join.from)),
        lx: round1((x1 + x2) / 2), ly: round1(ly), x1: round1(x1), y1: round1(y1), x2: round1(x2), y2: round1(y2)};
    });

    return {nodes, links, edges, width: round1(width), height: round1(height), warnings};
  }

  /* ---------------------------------------------------------------- diff */
  // diff(prev, next) -> {added: [id], removed: [id], status: [{id, from, to}]}
  // prev and next are graphs (or layouts: anything with a nodes array of {id, status}); prev may be missing, which means "nothing yet", so
  // every node of next is added. added follows the order of next, removed the order of prev, status the order of next.
  function diff(prev, next) {
    const byId = graph => {
      const map = new Map();
      (isObj(graph) && Array.isArray(graph.nodes) ? graph.nodes : []).forEach(n => {
        if (isObj(n) && typeof n.id === "string" && !map.has(n.id)) map.set(n.id, n);
      });
      return map;
    };
    const before = byId(prev);
    const after = byId(next);
    const added = [];
    const removed = [];
    const status = [];
    after.forEach((n, id) => {
      if (!before.has(id)) added.push(id);
      else if (before.get(id).status !== n.status) status.push({id, from: before.get(id).status, to: n.status});
    });
    before.forEach((n, id) => {
      if (!after.has(id)) removed.push(id);
    });
    return {added, removed, status};
  }

  const GraphLayout = {validate, layout, diff, forest, STATUSES, KINDS, TREE_KINDS, CROSS_KINDS, SIZES, DEFAULTS};
  if (typeof module === "object" && module !== null && module.exports) module.exports = GraphLayout;
  else root.GraphLayout = GraphLayout;
})(globalThis);
