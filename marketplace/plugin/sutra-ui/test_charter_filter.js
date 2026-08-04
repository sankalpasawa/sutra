/* Proves the charter filter bar behaves like domains_page.py build_site():
   - hidden when there is only ONE distinct status (a filter that cannot filter)
   - shown with all + each status when statuses vary
   - default selection is "active" when any charter is active, else "all"
   Extracts the REAL dirCharterSection from the shipped panel.html. */
const fs = require('fs');
const PANEL = '/Users/tchandrakar/Desktop/development/sutra/marketplace/plugin/sutra-ui/static/panel.html';
const html = fs.readFileSync(PANEL, 'utf8');
const script = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

const escSrc = script.match(/const esc = [\s\S]*?\n/)[0];
const start = script.indexOf('function dirCharterSection');
const end = script.indexOf('\n}', script.indexOf('return `<section class="chsec"><h2 class="chh">Charters</h2>${fil}')) + 2;
const fnSrc = script.slice(start, end);

function run(charters, dirSt) {
  const S = { dirQ: '', dirSt: dirSt || null };
  const CHARTERS = charters;
  const f = new Function('S', 'CHARTERS', escSrc + fnSrc + '; return dirCharterSection;')(S, CHARTERS);
  const byRef = new Map([
    ['d0', { name: 'Root', path: 'D0' }],
    ['d1', { name: 'Scratchpad', path: 'D1' }],
  ]);
  return f(byRef);
}

const oneStatus = [
  { id: 'C-1', title: 'Root Charter', purpose: 'p', domain_ref: 'd0', kind: 'standing', status: 'active' },
  { id: 'C-2', title: 'Scratchpad Charter', purpose: 'p', domain_ref: 'd1', kind: 'standing', status: 'active' },
];
const manyStatus = oneStatus.concat([
  { id: 'C-3', title: 'Shipped Thing', purpose: 'p', domain_ref: 'd1', kind: 'project', status: 'shipped' },
  { id: 'C-4', title: 'Paused Thing', purpose: 'p', domain_ref: 'd1', kind: 'project', status: 'paused' },
  { id: 'C-5', title: 'Old Thing', purpose: 'p', domain_ref: 'd0', kind: 'project', status: 'retired' },
]);

const rowsIn = h => (h.match(/<tr class="chtr/g) || []).length;
const btnsIn = h => [...h.matchAll(/data-chst="([^"]+)"[^>]*aria-pressed="([^"]+)"/g)].map(m => m[1] + ':' + m[2]);

const checks = [];
let a = run(oneStatus);
checks.push(['1 distinct status -> filter bar HIDDEN (generator rule)', !/class="chfil"/.test(a)]);
checks.push(['1 distinct status -> both rows still shown', rowsIn(a) === 2]);

let b = run(manyStatus);
checks.push(['4 statuses -> filter bar SHOWN', /class="chfil"/.test(b)]);
checks.push(['buttons are all + each status, sorted', JSON.stringify(btnsIn(b).map(x => x.split(':')[0]))
  === JSON.stringify(['all', 'active', 'paused', 'retired', 'shipped'])]);
checks.push(['default selection is "active"', btnsIn(b).includes('active:true')]);
checks.push(['default shows ONLY the 2 active rows', rowsIn(b) === 2]);

let c = run(manyStatus, 'all');
checks.push(['filter "all" shows every row', rowsIn(c) === 5]);
let d = run(manyStatus, 'shipped');
checks.push(['filter "shipped" shows 1 row', rowsIn(d) === 1]);
checks.push(['filter "shipped" marks only shipped pressed', btnsIn(d).includes('shipped:true')
  && !btnsIn(d).includes('active:true')]);

const noActive = manyStatus.filter(x => x.status !== 'active');
let e = run(noActive);
checks.push(['no active charters -> default falls back to "all"', /data-deffil="all"/.test(e) && rowsIn(e) === 3]);

let f2 = run(manyStatus, 'retired');
checks.push(['owner column present on every row', (f2.match(/class="cown"/g) || []).length === rowsIn(f2)]);

let g = run([]);
checks.push(['no charters -> "none yet"', /class="chempty"/.test(g)]);

let bad = 0;
for (const [name, ok] of checks) { if (!ok) bad++; console.log((ok ? 'ok   ' : 'FAIL ') + '- ' + name); }
console.log('-'.repeat(60));
console.log(bad === 0 ? 'RESULT: all ' + checks.length + ' filter behaviours match the generator'
                      : 'RESULT: ' + bad + ' FAILURE(S)');
process.exit(bad === 0 ? 0 : 1);
