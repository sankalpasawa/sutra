"use strict";
// sutra-front.css (Home's front door): its light tokens are the studio palette, every colour is a token, and in both themes its text keeps 4.5:1
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

const FRONT_SETS = {dark: block(FRONT, ":root"), light: block(FRONT, ":root[data-theme=light]")};

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

// The studio palette (the design reference's tokens): the light theme of the front door is exactly these, so Home and the team studio read as
// one product. Dark defines the same names.
const PALETTE = {"--s-bg": "#F3F1EC", "--s-surface": "#FFFFFF", "--s-ink": "#1F2421", "--s-muted": "#686C66", "--s-line": "#E2DED5",
  "--s-accent": "#3D5A80", "--s-good": "#3E8E5E", "--s-ask": "#D9822B"};
test("the light tokens of sutra-front.css are the studio palette, and dark defines the same names", () => {
  for (const [k, v] of Object.entries(PALETTE)) assert.equal(String(FRONT_SETS.light[k]).toUpperCase(), v, `light ${k}`);
  const light = Object.keys(FRONT_SETS.light).filter(k => k.startsWith("--s-"));
  assert.ok(light.length >= 15, "the sheet defines its tokens");
  for (const k of light) assert.ok(k in FRONT_SETS.dark, `dark ${k}`);
  assert.match(FRONT_SETS.dark["--s-display"] || "", /^"Bricolage Grotesque"/);
  assert.match(FRONT_SETS.dark["--s-body"] || "", /^"Figtree"/);
});

test("the two faces are served from this origin (the page works offline)", () => {
  const faces = [...FRONT.matchAll(/@font-face\s*\{([^}]*)\}/g)].map(m => m[1]);
  assert.equal(faces.length, 2);
  for (const f of faces) {
    const url = /url\("([^"]+)"\)/.exec(f)[1];
    assert.match(url, /^\/ui\/vendor\/fonts\/[\w-]+\.woff2$/);
    assert.ok(fs.existsSync(path.join(CSS_DIR, "..", url.replace(/^\/ui\//, ""))), url);
  }
});

test("on Home the purple of the frozen sheet is gone: J2's accent tokens take the studio's navy", () => {
  const home = block(FRONT, "body.home");
  for (const k of ["--accent", "--vio", "--purple", "--identity"]) assert.equal(home[k], "var(--s-accent)", k);
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
