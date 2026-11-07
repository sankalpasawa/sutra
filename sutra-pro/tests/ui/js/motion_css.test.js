"use strict";
// The motion of the style sheets (gap package fluid; docs/notes/GAP3-fluid.md): every transition and animation is on the compositor (transform,
// opacity) or a colour, on the shared scale of easing and durations, and nothing in any sheet says `transition: all` or moves a layout property.
// Run with: node --test tests/ui/js/motion_css.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const CSS_DIR = path.join(__dirname, "..", "..", "..", "sutra_app", "ui", "static", "css");
const ALL = fs.readdirSync(CSS_DIR).filter(f => f.endsWith(".css")).sort();
const FROZEN = new Set(["j2.css"]);                       // J2's own sheet, byte for byte: it only has to be free of the layout properties and `all`
const OURS = ALL.filter(f => !FROZEN.has(f));
const read = name => fs.readFileSync(path.join(CSS_DIR, name), "utf8");
const strip = css => css.replace(/\/\*[\s\S]*?\*\//g, "");

// Properties whose change makes the browser lay out or paint the page again on every frame.
const LAYOUT = new Set(["width", "height", "min-width", "min-height", "max-width", "max-height", "top", "left", "right", "bottom", "inset", "margin", "margin-top",
  "margin-right", "margin-bottom", "margin-left", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left", "font-size", "line-height",
  "border-width", "flex", "flex-basis", "grid-template-columns", "grid-template-rows", "box-shadow", "text-shadow", "filter", "backdrop-filter", "clip-path"]);
// What the Sutra sheets may transition or animate.
const ALLOWED = new Set(["opacity", "transform", "translate", "scale", "rotate", "color", "background-color", "border-color", "outline-color", "fill", "stroke",
  "text-decoration-color", "display", "overlay", "visibility"]);

// the blocks of a sheet: [{head, body}] for every `head { body }` at any depth that has declarations; @keyframes are returned as {keyframes: name, frames: [body]}
function blocks(css) {
  const src = strip(css);
  const out = [];
  function walk(from, to) {
    let i = from;
    while (i < to) {
      const open = src.indexOf("{", i);
      if (open < 0 || open >= to) break;
      const head = src.slice(i, open).trim().replace(/^[;}\s]+/, "");
      let depth = 1;
      let j = open + 1;
      while (j < to && depth > 0) {
        if (src[j] === "{") depth += 1;
        else if (src[j] === "}") depth -= 1;
        j += 1;
      }
      const body = src.slice(open + 1, j - 1);
      if (/^@keyframes\s/.test(head)) {
        const frames = [];
        const inner = body;
        let k = 0;
        while (k < inner.length) {
          const o = inner.indexOf("{", k);
          if (o < 0) break;
          const c = inner.indexOf("}", o);
          frames.push(inner.slice(o + 1, c));
          k = c + 1;
        }
        out.push({keyframes: head.replace(/^@keyframes\s+/, "").trim(), frames});
      } else if (/^@(media|supports)/.test(head)) {
        walk(open + 1, j - 1);
      } else if (head !== "") {
        out.push({head, body});
      }
      i = j;
    }
  }
  walk(0, src.length);
  return out;
}

const decls = body => body.split(";").map(d => d.trim()).filter(Boolean).map(d => {
  const at = d.indexOf(":");
  return at < 0 ? null : [d.slice(0, at).trim().toLowerCase(), d.slice(at + 1).replace(/!important/i, "").trim()];
}).filter(Boolean);

// the properties a `transition` value names (the first word of each comma-separated item, not inside var() or calc())
function transitioned(value) {
  const flat = value.replace(/var\([^)]*\)|calc\((?:[^()]|\([^)]*\))*\)|cubic-bezier\([^)]*\)/g, "X");
  return flat.split(",").map(item => item.trim().split(/\s+/)[0]).filter(Boolean);
}

/* ---------------------------------------------------------------- the rules */
test("1. no sheet says `transition: all` or `transition-property: all`", () => {
  ALL.forEach(file => {
    blocks(read(file)).forEach(b => {
      if (b.keyframes) return;
      decls(b.body).forEach(([prop, value]) => {
        if (prop === "transition") assert.ok(!transitioned(value).includes("all"), `${file}: ${b.head} { transition: ${value} }`);
        if (prop === "transition-property") assert.ok(!/\ball\b/.test(value), `${file}: ${b.head} { transition-property: ${value} }`);
      });
    });
  });
});

test("2. no sheet transitions or animates a layout property (width, height, top, left, margin, padding, box-shadow, filter ...)", () => {
  ALL.forEach(file => {
    blocks(read(file)).forEach(b => {
      if (b.keyframes) {
        b.frames.forEach(frame => decls(frame).forEach(([prop]) => assert.ok(!LAYOUT.has(prop), `${file}: @keyframes ${b.keyframes} animates ${prop}`)));
        return;
      }
      decls(b.body).forEach(([prop, value]) => {
        if (prop === "transition") transitioned(value).forEach(name => assert.ok(!LAYOUT.has(name), `${file}: ${b.head} transitions ${name}`));
        if (prop === "transition-property") value.split(",").map(v => v.trim()).forEach(name => assert.ok(!LAYOUT.has(name), `${file}: ${b.head} transitions ${name}`));
        if (prop === "will-change") value.split(",").map(v => v.trim()).forEach(name => assert.ok(!LAYOUT.has(name), `${file}: ${b.head} will-change ${name}`));
      });
    });
  });
});

test("3. the Sutra sheets move only transform and opacity (and colours): everything else is a finding", () => {
  OURS.forEach(file => {
    blocks(read(file)).forEach(b => {
      if (b.keyframes) {
        b.frames.forEach(frame => decls(frame).forEach(([prop]) => {
          if (prop === "animation-timing-function") return;
          assert.ok(ALLOWED.has(prop), `${file}: @keyframes ${b.keyframes} animates ${prop}`);
        }));
        return;
      }
      decls(b.body).forEach(([prop, value]) => {
        if (prop === "transition") transitioned(value).forEach(name => assert.ok(name === "none" || ALLOWED.has(name), `${file}: ${b.head} transitions ${name}`));
      });
    });
  });
});

test("4. every duration and easing of the Sutra sheets comes from the shared scale (var(--dur-*), var(--ease-*)); reduced motion sets the durations to 0", () => {
  const css = read("sutra-panel.css");
  ["--ease-out", "--ease-in-out", "--dur-fast", "--dur-base", "--dur-slow"].forEach(token => assert.match(strip(css), new RegExp(token + "\\s*:"), token + " is defined"));
  assert.match(strip(css), /prefers-reduced-motion:\s*reduce\)\s*\{\s*:root\s*\{[^}]*--dur-fast:\s*0ms;[^}]*--dur-base:\s*0ms;[^}]*--dur-slow:\s*0ms/);
  const time = /(?<![\w-])\d*\.?\d+m?s\b/;
  OURS.forEach(file => {
    blocks(read(file)).forEach(b => {
      if (b.keyframes) return;
      decls(b.body).forEach(([prop, value]) => {
        if (prop !== "transition" && prop !== "animation") return;
        if (/^none\b/.test(value) || value.trim() === "none") return;
        const bare = value.replace(/var\([^)]*\)|cubic-bezier\([^)]*\)/g, "X");
        if (b.head.includes("prefers-reduced")) return;
        assert.ok(!time.test(bare.replace(/calc\(X\s*\*\s*\d+\)/g, "X")), `${file}: ${b.head} { ${prop}: ${value} } has a duration of its own`);
        assert.ok(!/\b(ease|ease-in|ease-out|ease-in-out)\b/.test(bare), `${file}: ${b.head} { ${prop}: ${value} } has a keyword easing`);
      });
    });
  });
});

test("5. the checker finds what it is for: `transition: all`, a width keyframe and a raw duration are caught", () => {
  assert.ok(transitioned("all .3s ease").includes("all"));
  assert.ok(transitioned("opacity var(--dur-base) var(--ease-out), all 1s").includes("all"));
  assert.ok(!transitioned("opacity var(--dur-base) var(--ease-out), transform calc(var(--dur-base) * 2) var(--ease-out)").includes("all"));
  assert.deepEqual(transitioned("opacity var(--dur-fast) cubic-bezier(.2,.8,.2,1), width 1s"), ["opacity", "width"]);
  const found = blocks("@keyframes grow { 0% { width: 0; } 100% { width: 10px; } } .a { transition: width .2s; }");
  assert.equal(found.length, 2);
  assert.equal(found[0].keyframes, "grow");
  assert.ok(found[0].frames.some(f => decls(f).some(([p]) => LAYOUT.has(p))));
  assert.ok(/\d+m?s\b/.test("transition: opacity .2s"));
});

test("6. the drawer, the panes and a new line are animated, and the idle drift of J2's maps is off", () => {
  const panel = strip(read("sutra-panel.css"));
  assert.match(panel, /\.agentdrawer:not\(\[hidden\]\)\s*\{\s*animation:\s*drawerin/);
  assert.match(panel, /\.sright \.pane:not\(\[hidden\]\)\s*\{\s*animation:\s*fluidin/);
  assert.match(panel, /\.nmsg-in\s*\{\s*animation:\s*fluidin/);
  assert.match(panel, /\.treesvg \.tnodes>\.tnode,\.consvg \.cnodes>\.cnode,\.mapsvg \.mapnode\s*\{\s*animation:\s*none/);
  assert.match(panel, /\.consvg \.cline\.spoke\s*\{\s*animation:\s*none/);
  // J2's own sheet still has the drift (it is frozen) and the override must come from a sheet the pages load AFTER it
  assert.match(strip(read("j2.css")), /@keyframes mdrift/);
  ["home.html", "console.html", "j2_ui.html"].forEach(page => {
    const html = fs.readFileSync(path.join(CSS_DIR, "..", "..", "pages", page), "utf8");
    const sheets = [...html.matchAll(/<link rel="stylesheet" href="\/ui\/css\/([\w.-]+\.css)"/g)].map(m => m[1]);
    assert.ok(sheets.indexOf("sutra-panel.css") > sheets.indexOf("j2.css"), `${page}: sutra-panel.css comes after j2.css`);
  });
});

test("7. reduced motion stops everything on every Sutra page: the durations are 0 and a universal rule ends any animation that is left", () => {
  const panel = strip(read("sutra-panel.css"));
  assert.match(panel, /prefers-reduced-motion:\s*reduce\)\s*\{\s*\*,\*::before,\*::after\s*\{[^}]*animation-duration:\s*\.01ms\s*!important[^}]*transition-duration:\s*\.01ms\s*!important/);
});
