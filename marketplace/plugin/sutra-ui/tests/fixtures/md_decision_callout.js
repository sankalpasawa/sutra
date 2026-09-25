// Driver for test_md_decision_callout.py. Loads esc/MD_*/mdHtml out of
// static/js/02-helpers.js (a browser file with no module system) by slicing the
// pure segment, then checks the DECISION callout branch. Prints one line per
// check and exits 1 on any failure.
const fs = require("fs");
const path = require("path");
const helpers = path.resolve(__dirname, "..", "..", "static", "js", "02-helpers.js");
const src = fs.readFileSync(helpers, "utf8");
const start = src.indexOf("const esc = ");
const end = src.indexOf("/* ══════════════════════ rail");
if (start < 0 || end < 0) throw new Error("could not slice mdHtml out of 02-helpers.js");
const mdHtml = new Function(src.slice(start, end) + "\nreturn mdHtml;")();

let fails = 0;
const check = (name, cond, got) => {
  if (cond) console.log("ok   " + name);
  else { fails++; console.log("FAIL " + name + "\n   got: " + got); }
};

const fenced = [
  "Two gotchas to design around.", "", "```",
  "┌──────────────────────────────────────────────┐",
  "│ DECISION: build the delta lane on top of the │",
  "│ existing updater, not by replacing it.       │",
  "└──────────────────────────────────────────────┘",
  "```", "", "| Phase | Effort |", "|---|---|", "| 0 | hours |",
].join("\n");
const h1 = mdHtml(fenced);
check("fenced DECISION box becomes a callout", /class="md-callout md-callout-decision"/.test(h1), h1);
check("callout carries the Decision label", /md-callout-k">Decision</.test(h1), h1);
check("box-drawing characters are gone", !/[┌│└─┐┘]/.test(h1), h1);
check("body is one sentence without the DECISION: prefix",
  /md-callout-b">build the delta lane on top of the existing updater, not by replacing it\.</.test(h1), h1);
check("no <pre> for the decision", !/md-pre/.test(h1), h1);
check("the table after it still renders", /md-t/.test(h1), h1);
check("callout is not wrapped in a <p>", !/<p class="md-p"><div class="md-callout/.test(h1), h1);

const h2 = mdHtml("```js\nconst x = 1;\n```");
check("ordinary fenced code is still <pre>", /md-pre/.test(h2) && !/md-callout/.test(h2), h2);

const h3 = mdHtml("```\n+----------------+\n| DECISION: ship it now. |\n+----------------+\n```");
check("an ascii +--- box also becomes a callout", /md-callout-decision/.test(h3) && /ship it now\./.test(h3), h3);

const h4 = mdHtml("Intro line.\n\n┌────────────┐\n│ DECISION: keep the updater. │\n└────────────┘\n\nAfter.");
check("unfenced box lines become a callout", /md-callout-decision/.test(h4) && /keep the updater\./.test(h4) && !/[┌│└]/.test(h4), h4);
check("prose around an unfenced box survives", /Intro line\./.test(h4) && /After\./.test(h4), h4);

const h5 = mdHtml("```\nDECISION: no box at all, just the label.\n```");
check("a bare fenced DECISION: line is a callout too", /md-callout-decision/.test(h5), h5);

const h6 = mdHtml("```\n│ DECISION: use **postgres** for v1. │\n```");
check("inline markdown inside the decision renders", /<strong>postgres<\/strong>/.test(h6), h6);

const h7 = mdHtml("```\n│ NOTE: this is a note. │\n```");
check("a non-DECISION box stays as code", /md-pre/.test(h7) && !/md-callout/.test(h7), h7);

const h8 = mdHtml("```\n│ DECISION: <script>alert(1)</script> │\n```");
check("html inside a decision stays escaped", !/<script>/.test(h8) && /&lt;script&gt;/.test(h8), h8);

const h9 = mdHtml("+ one\n+ two");
check("a plus-bulleted list is still a list", /<ul class="md-l"><li>one<\/li>/.test(h9), h9);

const h10 = mdHtml("| FLOW: direction\n| DEPTH: 3/5");
check("pipe-prefixed governance rows are untouched", /<p class="md-p">\| FLOW/.test(h10) && !/md-callout/.test(h10), h10);

const h11 = mdHtml("```\n│ DECISION: keep it. │\n│ Order: a → b. │\n```");
check("a two-line decision joins into one body", /md-callout-b">keep it\. Order: a → b\.</.test(h11), h11);

console.log(fails ? fails + " check(s) failed" : "all checks passed");
process.exit(fails ? 1 : 0);
