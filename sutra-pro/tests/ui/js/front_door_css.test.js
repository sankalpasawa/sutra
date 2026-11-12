"use strict";
// sutra-front.css (Home's front door): its studio tokens are j2.css's own values, every colour is a token, and in both themes its text keeps 4.5:1
// and its meaningful lines 3:1 on the studio's three surfaces (--s-bg, --s-surface, --s-surface2). contrast.test.js does the same for the other
// Sutra sheets against J2's --bg/--panel/--panel2; the front door sits on the studio's surfaces instead.
// Run with: node --test tests/ui/js/front_door_css.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const CSS_DIR = path.join(__dirname, "..", "..", "..", "sutra_app", "ui", "static", "css");
const read = name => fs.readFileSync(path.join(CSS_DIR, name), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const FRONT = read("sutra-front.css");
const SURFACES = ["--s-bg", "--s-surface", "--s-surface2"];
const DECORATIVE = new Set(["--s-line", "--s-line2"]);        // hairlines between things, like J2's --line

// The declarations of the rules whose selector is exactly `sel` (top level only).
function block(css, sel) {
  const out = {};
  const re = new RegExp(sel.replace(/[[\]()=]/g, "\\$&") + "\\s*\\{([^}]*)\\}", "g");
  let m;
  while ((m = re.exec(css))) m[1].split(";").forEach(d => { const i = d.indexOf(":"); if (i > 0) out[d.slice(0, i).trim()] = d.slice(i + 1).trim(); });
  return out;
}

function j2Sets() {
  const css = read("j2.css");
  const dark = {};
  const light = {};
  const darkBody = /:root\{color-scheme:dark;([^}]*)\}/.exec(css)[1];
  const lightBody = /:root\[data-theme=light\]\{color-scheme:light;([^}]*)\}/.exec(css)[1];
  for (const [body, into] of [[darkBody, dark], [lightBody, light]]) body.split(";").forEach(d => { const i = d.indexOf(":"); if (i > 0 && d.trim().startsWith("--s-")) into[d.slice(0, i).trim()] = d.slice(i + 1).trim(); });
  return {dark, light};
}

const FRONT_SETS = {dark: block(FRONT, ":root"), light: block(FRONT, ":root[data-theme=light]")};
const J2 = j2Sets();

function rgb(v) {
  const t = String(v).trim().toLowerCase();
  let m = /^#([0-9a-f]{3})$/.exec(t);
  if (m) return [...m[1]].map(c => parseInt(c + c, 16));
  m = /^#([0-9a-f]{6})$/.exec(t);
  if (m) return [0, 2, 4].map(k => parseInt(m[1].slice(k, k + 2), 16));
  m = /^rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*\/\s*([\d.]+)\s*\)$/.exec(t);
  if (m && Number(m[4]) === 1) return [1, 2, 3].map(k => Number(m[k]));
  return null;                                                                           // a translucent colour: not judged as a solid one
}
const lum = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const colourOf = (word, set) => { const m = /^var\((--[\w-]+)\)$/.exec(word); return m && set[m[1]] ? rgb(set[m[1]]) : null; };

// Every rule of the sheet outside the two token blocks, with its colour declarations.
function rules() {
  const out = [];
  const body = FRONT.replace(/@media[^{]*\{/g, "").replace(/@keyframes[^{]*\{[^}]*\{[^}]*\}\s*\}/g, "");
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(body))) {
    const sel = m[1].trim();
    if (sel === ":root" || sel === ":root[data-theme=light]") continue;
    const decls = m[2].split(";").map(d => { const i = d.indexOf(":"); return i > 0 ? [d.slice(0, i).trim(), d.slice(i + 1).trim()] : null; }).filter(Boolean);
    out.push({sel, decls});
  }
  return out;
}
const firstVar = v => (/var\(--s-[\w-]+\)/.exec(v) || [""])[0];

test("the studio tokens of sutra-front.css are j2.css's own values, in both themes", () => {
  for (const theme of ["dark", "light"]) {
    const mine = FRONT_SETS[theme];
    assert.ok(Object.keys(mine).length >= 15, theme + ": the sheet defines its tokens");
    for (const [k, v] of Object.entries(mine)) assert.equal(v, J2[theme][k], `${theme} ${k}`);
  }
});

test("no literal colour outside the two token blocks; every colour of a rule is a --s- token", () => {
  for (const {sel, decls} of rules()) {
    for (const [p, v] of decls) {
      assert.doesNotMatch(v, /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/, `${sel} { ${p}: ${v} }`);
      if (/color|background|border|outline|box-shadow/.test(p) && /var\(/.test(v)) assert.match(v, /var\(--(s-|dur-|ease-)/, `${sel} { ${p} }`);
    }
  }
});

for (const theme of ["dark", "light"]) {
  test(`${theme}: text keeps 4.5:1 on the studio's surfaces, a rule with its own background keeps 4.5:1 on it, lines keep 3:1`, () => {
    const set = FRONT_SETS[theme];
    const bad = [];
    let texts = 0;
    for (const {sel, decls} of rules()) {
      const fg = decls.filter(([p]) => p === "color").map(([, v]) => firstVar(v)).pop();
      const bg = decls.filter(([p]) => p === "background" || p === "background-color").map(([, v]) => firstVar(v)).pop();
      if (fg) {
        texts += 1;
        const a = colourOf(fg, set);
        const own = bg ? colourOf(bg, set) : null;
        if (a && own) { if (ratio(a, own) < 4.5) bad.push(`${sel}: ${fg} on ${bg} = ${ratio(a, own).toFixed(2)}`); }
        else if (a) SURFACES.forEach(s => { const r = ratio(a, rgb(set[s])); if (r < 4.5) bad.push(`${sel}: ${fg} on ${s} = ${r.toFixed(2)}`); });
      }
      decls.filter(([p]) => /^(border(-color)?|outline(-color)?)$/.test(p)).forEach(([, v]) => {
        const word = firstVar(v);
        const name = (/--[\w-]+/.exec(word) || [""])[0];
        const c = word && !DECORATIVE.has(name) ? colourOf(word, set) : null;
        if (c) SURFACES.forEach(s => { const r = ratio(c, rgb(set[s])); if (r < 3) bad.push(`${sel}: line ${word} on ${s} = ${r.toFixed(2)}`); });
      });
    }
    assert.ok(texts >= 10, "the sheet sets many text colours");
    assert.deepEqual(bad, []);
  });
}
