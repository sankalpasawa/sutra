/* Charters section of the Directory view — asserted against the rules in
   lib/domains_page.py charter_table() / cols_for() / child_of().

   Extracts the REAL functions out of the shipped static/panel.html, so this
   tests what ships, not a copy. Written because the local registry has two
   charters, both `active`, in one department: neither the status filter nor
   the O/L lanes can be exercised by hand on that data.

   Run: node test_charter_filter.js
*/
const fs = require('fs');
const PANEL = __dirname + '/static/panel.html';
const html = fs.readFileSync(PANEL, 'utf8');
/* panel.html was one file with an inline <script>; it is now a shell that pulls an
   ORDERED list of /static/js/*.js modules. Concatenate them in order (the same way
   test_panel.js does) so the extraction below sees the real functions instead of a
   -1 indexOf and a null match. */
/* The src carries a ?v=<token> cache-bust the server substitutes per build, so the
   query is captured separately and dropped -- reading "01-state.js?v=__ASSETVER__"
   off disk is an ENOENT, which is exactly how this broke. test_panel.js's loader
   strips it the same way. */
const refs = [...html.matchAll(/<script src="\/static\/js\/([^"?]+)(?:\?[^"]*)?"><\/script>/g)].map(m => m[1]);
if (!refs.length) throw new Error('panel.html references no /static/js modules -- has the shell changed?');
const script = refs.map(name => fs.readFileSync(__dirname + '/static/js/' + name, 'utf8')).join('\n');

function slice(from, toAnchor) {
  const a = script.indexOf(from);
  if (a < 0) throw new Error('not found in panel.html: ' + from);
  const b = script.indexOf('\n}', script.indexOf(toAnchor, a)) + 2;
  return script.slice(a, b);
}
const escSrc = script.match(/const esc = [\s\S]*?\n/)[0];
const src = escSrc
  + slice('function dirChip', 'return parts.length < 2')
  + slice('function dirChildOf', 'return null;')
  + slice('function dirLanesFor', 'return cols;')
  + slice('function dirCharterSection', 'return `<section class="chsec"><h2 class="chh">Charters</h2>${legend}${fil}');

function render(charters, domains, dirSt) {
  const S = { dirQ: '', dirSt: dirSt || null };
  const CHARTERS = charters;
  const f = new Function('S', 'CHARTERS', src + '; return dirCharterSection;')(S, CHARTERS);
  const byRef = new Map(domains.map(d => [d.ref, d]));
  const kids = new Map();
  domains.forEach(d => {
    if (d.parent_ref) { if (!kids.has(d.parent_ref)) kids.set(d.parent_ref, []); kids.get(d.parent_ref).push(d); }
  });
  const root = domains.find(d => !d.parent_ref);
  return f(byRef, kids, root);
}

/* root -> A, B (top level); A -> A1 (deep, rolls up to A) */
const DOMAINS = [
  { ref: 'r',  name: 'Root',    path: 'D0',   parent_ref: null },
  { ref: 'a',  name: 'Alpha',   path: 'D1',   parent_ref: 'r'  },
  { ref: 'b',  name: 'Bravo',   path: 'D2',   parent_ref: 'r'  },
  { ref: 'a1', name: 'Alpha-1', path: 'D1.1', parent_ref: 'a'  },
];
const ch = (id, owner, status, kind, linked) => ({
  id, title: 'C ' + id, purpose: 'p', domain_ref: owner,
  status, kind: kind || 'standing', linked_domain_refs: linked || [],
});

const rowsIn  = h => (h.match(/<tr class="chtr/g) || []).length;
const btnsIn  = h => [...h.matchAll(/data-chst="([^"]+)"[^>]*aria-pressed="([^"]+)"/g)].map(m => m[1] + ':' + m[2]);
const laneHdr = h => [...h.matchAll(/<th scope="col" class="lane"[^>]*>([^<]*)</g)].map(m => m[1]);
const rowLanes = (h, i) => {
  const rows = h.split('<tr class="chtr').slice(1);
  return [...rows[i].matchAll(/<td class="(lo|ll|ln)"/g)].map(m => m[1]);
};

const checks = [];
const t = (name, ok) => checks.push([name, ok]);

/* ── status filter ─────────────────────────────────────────────────────── */
const oneStatus = [ch('1', 'r', 'active'), ch('2', 'a', 'active')];
let h = render(oneStatus, DOMAINS);
t('filter bar is ALWAYS shown, even with one status (founder direction)', /class="chfil"/.test(h));
t('one status -> buttons are all + active',
  JSON.stringify(btnsIn(h).map(x => x.split(':')[0])) === JSON.stringify(['all', 'active']));
t('both rows render', rowsIn(h) === 2);

const many = [
  ch('1', 'r', 'active'), ch('2', 'a', 'active'),
  ch('3', 'a', 'shipped', 'project'), ch('4', 'b', 'paused', 'project'),
  ch('5', 'b', 'retired', 'project'),
];
h = render(many, DOMAINS);
t('many statuses -> all + each, sorted', JSON.stringify(btnsIn(h).map(x => x.split(':')[0]))
  === JSON.stringify(['all', 'active', 'paused', 'retired', 'shipped']));
t('default selection is "active"', btnsIn(h).includes('active:true'));
t('default shows only the 2 active rows', rowsIn(h) === 2);
t('filter "all" shows every row', rowsIn(render(many, DOMAINS, 'all')) === 5);
t('filter "shipped" shows 1 row', rowsIn(render(many, DOMAINS, 'shipped')) === 1);
t('no active charters -> default falls back to "all"',
  /data-deffil="all"/.test(render(many.filter(c => c.status !== 'active'), DOMAINS)));
t('no charters -> "none yet"', /class="chempty"/.test(render([], DOMAINS)));

/* ── O / L lanes ───────────────────────────────────────────────────────── */
h = render(many, DOMAINS, 'all');
t('lane header is one column per TOP-LEVEL department',
  JSON.stringify(laneHdr(h)) === JSON.stringify(['D1', 'D2']));
t('legend renders', /O owner &middot; L linked/.test(h));

const owned = render([ch('x', 'a', 'active')], DOMAINS, 'all');
t('charter owned by a top-level dept -> O in its lane, blank elsewhere',
  JSON.stringify(rowLanes(owned, 0)) === JSON.stringify(['lo', 'ln']));

const deep = render([ch('x', 'a1', 'active')], DOMAINS, 'all');
t('DEEP owner rolls UP to its top-level lane (child_of)',
  JSON.stringify(rowLanes(deep, 0)) === JSON.stringify(['lo', 'ln']));

const linked = render([ch('x', 'a', 'active', 'standing', ['b'])], DOMAINS, 'all');
t('linked_domain_refs produce L in the linked lane',
  JSON.stringify(rowLanes(linked, 0)) === JSON.stringify(['lo', 'll']));

const both = render([ch('x', 'a', 'active', 'standing', ['a1'])], DOMAINS, 'all');
t('O outranks L when a charter owns AND links into the same lane',
  JSON.stringify(rowLanes(both, 0)) === JSON.stringify(['lo', 'ln']));

/* A charter owned by the PAGE ITSELF has no lane: cols_for() skips
   `r === page_ref`. Asserted alongside a lane-occupying charter, because with
   ONLY the root-owned one nothing lands in a lane and show_cols drops the
   columns altogether (the next case covers that). Rows sort by owner name:
   Alpha before Root. */
const rootOwned = render([ch('x', 'r', 'active'), ch('y', 'a', 'active')], DOMAINS, 'all');
t('charter owned by the page itself occupies no lane',
  JSON.stringify(rowLanes(rootOwned, 0)) === JSON.stringify(['lo', 'ln'])
  && JSON.stringify(rowLanes(rootOwned, 1)) === JSON.stringify(['ln', 'ln']));

t('no charter lands in a lane -> columns dropped entirely (show_cols)',
  laneHdr(render([ch('x', 'r', 'active')], DOMAINS, 'all')).length === 0);

const flat = render([ch('x', 'r', 'active')], [{ ref: 'r', name: 'Root', path: 'D0', parent_ref: null }]);
t('no top-level departments -> lane columns are omitted entirely', laneHdr(flat).length === 0);

/* cycle guard: a damaged registry must not hang the renderer */
const CYC = [
  { ref: 'r', name: 'Root',  path: 'D0', parent_ref: null },
  { ref: 'a', name: 'Alpha', path: 'D1', parent_ref: 'r'  },
  { ref: 'x', name: 'X',     path: 'D9', parent_ref: 'y'  },
  { ref: 'y', name: 'Y',     path: 'D8', parent_ref: 'x'  },
];
let cycOk = true;
try { render([ch('c', 'x', 'active')], CYC, 'all'); } catch (e) { cycOk = false; }
t('parent_ref cycle does not hang or throw', cycOk);

/* ── owner grouping ────────────────────────────────────────────────────── */
h = render([ch('1', 'a', 'active'), ch('2', 'a', 'active'), ch('3', 'b', 'active')], DOMAINS, 'all');
t('repeated owner is hidden VISUALLY but the cell stays in the DOM',
  (h.match(/class="cown"/g) || []).length === 3 && (h.match(/ctxt ohide/g) || []).length === 1);

/* ── the published ROW SHAPE ───────────────────────────────────────────────
   domains_page.py renders a charter row as ONE line -- owner, title, kind,
   status, lanes -- with the purpose only in the title attribute. An earlier
   version of this view rendered the purpose as a visible <div> as well, which
   made every row three lines tall and, because a <th> with a max-width inside
   a width:100% table overflows instead of wrapping, spilled the text across
   the lane columns. These assertions are that bug, pinned. */
h = render([ch('1', 'a', 'active')], DOMAINS, 'all');
t('purpose is a tooltip, NOT a visible block', /title="p"/.test(h) && !/chpurp/.test(h));
t('the row header holds only the title', /<th scope="row"><span class="cht"[^>]*>C 1<\/span><\/th>/.test(h));
h = render([ch('r1', 'r', 'active'), ch('a1', 'a', 'active')], DOMAINS, 'all');
t('a charter owned by the page itself renders as "here", like the generator',
  /<span class="cown-here"[^>]*>here<\/span>/.test(h));
t('other owners render as a bare name, with no D-path chip in the owner cell',
  /<span class="ctxt[^"]*">Alpha<\/span>/.test(h));

/* ── the published chip spelling ───────────────────────────────────────────
   The engine renders a D-path as "D1.D1"; the published page renders the SAME
   ordinals as "D1.1" (domains_page.py dpath_idx). This view is the published
   page, so it shows the published spelling — re-spaced from d.path, never a
   recomputed index. */
const chip = new Function(slice('function dirChip', 'return parts.length < 2')
  + '; return dirChip;')();
t('dirChip: engine "D1.D1" renders as the published "D1.1"', chip('D1.D1') === 'D1.1');
t('dirChip: four levels deep', chip('D1.D1.D1.D11') === 'D1.1.1.11');
t('dirChip: a top-level path is unchanged', chip('D1') === 'D1' && chip('D0') === 'D0');
t('dirChip: missing path stays empty, never "undefined"', chip(undefined) === '');
t('dirChip: ordinals are NEVER recomputed — only the separator changes',
  chip('D3.D6').replace(/[^0-9]/g, '') === 'D3.D6'.replace(/[^0-9]/g, ''));

/* and the lane headers carry that spelling through */
h = render([ch('1', 'a1', 'active', 'project')], DOMAINS, 'all');
t('lane headers use the published chip spelling',
  laneHdr(h).every(x => !/D\d+\.D/.test(x)));

let bad = 0;
for (const [name, ok] of checks) { if (!ok) bad++; console.log((ok ? 'ok   ' : 'FAIL ') + '- ' + name); }
console.log('-'.repeat(64));
console.log(bad === 0
  ? 'charters section: ' + checks.length + ' passed, 0 failed'
  : 'charters section: ' + bad + ' FAILED of ' + checks.length);
process.exit(bad === 0 ? 0 : 1);
