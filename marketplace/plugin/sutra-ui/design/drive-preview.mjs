/* Drives design/app-preview.html the way the founder will: clicks every control
   and asserts the DOM actually changed. A control that "looks clickable" but
   moves nothing is the exact failure this run exists to catch. */
/* Run it:
     cd sutra-ui && python3 -m http.server 8777 &
     node design/drive-preview.mjs
   Needs playwright and a local Google Chrome (channel:"chrome"), so no browser
   download is required. PLAYWRIGHT may point at an install elsewhere, and
   PREVIEW_SHOTS at where the screenshots should land. */
let pw = null;
for (const spec of ["playwright", process.env.PLAYWRIGHT].filter(Boolean)) {
  try { const m = await import(spec); pw = m.default ?? m; break; } catch {}
}
if (!pw) {
  console.error("playwright not found — npm i -D playwright, " +
                "or PLAYWRIGHT=/abs/path/to/playwright/index.js node design/drive-preview.mjs");
  process.exit(2);
}
const { chromium } = pw;

const URL = process.env.PREVIEW_URL || "http://127.0.0.1:8777/design/app-preview.html";
const OUT = process.env.PREVIEW_SHOTS || ".";

let pass = 0, fail = 0;
const check = (name, ok, detail = "") => {
  if (ok) { pass++; console.log(`  ok   ${name}`); }
  else    { fail++; console.log(`  FAIL ${name} ${detail}`); }
};

const b = await chromium.launch({ channel: "chrome" });
const page = await b.newPage({ viewport: { width: 1440, height: 900 } });
const errs = [];
page.on("pageerror", e => errs.push(String(e)));
/* favicon.ico is requested by the browser, not by the page — ignore it */
page.on("requestfailed", r => { if (!/favicon/.test(r.url())) errs.push("net: " + r.url()); });
page.on("response", r => {
  if (r.status() >= 400 && !/favicon/.test(r.url())) errs.push(`http ${r.status()}: ${r.url()}`);
});
/* "Failed to load resource" carries no URL in the console message; the response
   listener above already reports those WITH the URL, so counting the console
   copy too would just double-count. Verified: the only 404 is /favicon.ico,
   which the browser requests on its own, and panel.css fetches nothing (0 url()). */
page.on("console", m => {
  if (m.type() === "error" && !/Failed to load resource/.test(m.text()))
    errs.push("console: " + m.text());
});
await page.goto(URL, { waitUntil: "networkidle" });

console.log("\n1 · initial state");
check("no page errors on boot", errs.length === 0, errs.join(" | "));
check("menu starts closed", await page.locator("#metaPop").isHidden());
check("agent fold starts closed", await page.locator("#agList").isHidden());
check("pane header hidden while expanded",
  await page.locator("#chatPane .ph").isHidden());
check("composer reachable (the layout invariant)",
  await page.locator(".pc textarea").isVisible());
await page.screenshot({ path: `${OUT}/i1-initial.png` });

console.log("\n2 · the composer menu");
await page.click("#metaTrigger");
check("menu opens", await page.locator("#metaPop").isVisible());
check("trigger reports expanded",
  (await page.getAttribute("#metaTrigger", "aria-expanded")) === "true");
const rows = await page.locator(".mrow .mk").allTextContents();
check("menu carries every relocated control",
  JSON.stringify(rows) === JSON.stringify(["Folder","Permissions","Model","Usage","Routing","Fold","Close"]),
  JSON.stringify(rows));
await page.screenshot({ path: `${OUT}/i2-menu.png` });

await page.click(".pb");                      // click away
check("click-away closes the menu", await page.locator("#metaPop").isHidden());

await page.click("#metaTrigger");
await page.keyboard.press("Escape");
check("Escape closes the menu", await page.locator("#metaPop").isHidden());

console.log("\n3 · drill into a running agent from inside the turn");
await page.click('.gv-agents button.trow[data-ag="lens"]');
check("subagent fold opened", await page.locator("#agList").isVisible());
check("the clicked agent is the selected one",
  (await page.getAttribute('.agrow[data-ag="lens"]', "aria-pressed")) === "true");
const det = await page.locator("#agDetail").innerText();
check("its transcript rendered", det.includes("migrate the lens engine"), det.slice(0, 60));
check("steps rendered", (await page.locator("#agDetail .agstep").count()) === 2);
/* the roster line and the transcript below it must not contradict each other */
const rowSum = await page.locator('.agrow[data-ag="lens"] .agm').innerText();
const detSum = await page.locator("#agDetail .agdmeta").innerText();
check("row summary agrees with the transcript",
  rowSum.startsWith("2 steps") && detSum.startsWith("2 steps"), `${rowSum} vs ${detSum}`);
await page.screenshot({ path: `${OUT}/i3-agent-lens.png` });

console.log("\n4 · the failed agent tells you why it failed");
await page.click('.gv-agents button.trow[data-ag="cynefin"]');
const bad = await page.locator("#agDetail").innerText();
check("failure is legible", bad.includes("cynefin.bats:14"), bad.slice(0, 60));
await page.screenshot({ path: `${OUT}/i4-agent-failed.png` });

console.log("\n5 · governance chip + thinking log");
await page.click(".turn:nth-child(1) .gv-chip");
check("chip expands",
  await page.locator(".turn:nth-child(1) .gv").evaluate(e => e.classList.contains("gv-open")));
await page.click(".gv-thinkbtn");
check("thinking log closes on click",
  !(await page.locator(".gv-openlog").count()));
await page.click(".gv-thinkbtn");
check("thinking log reopens", (await page.locator(".gv-openlog").count()) === 1);
await page.screenshot({ path: `${OUT}/i5-governance.png` });

console.log("\n6 · fold — the regression codex caught");
await page.click(".pgrip");
check("pane collapses",
  await page.locator("#chatPane").evaluate(e => e.classList.contains("collapsed")));
check("collapsed strip is NOT blank — the header returns",
  await page.locator("#chatPane .ph h3").isVisible());
check("and it offers the way back",
  await page.locator("#chatPane .pfold").isVisible());
/* 38px content + the pane's 1px borders — the shipped strip width, unchanged */
const w = await page.locator("#chatPane").evaluate(e => e.getBoundingClientRect().width);
check("collapsed to the shipped strip width", w >= 38 && w <= 42, `got ${w}`);
/* the shipped-app bug this preview surfaced: .agents is a sibling of .pb and is
   NOT in panel.css's collapsed hide-list, so it used to spill into the strip */
check("the subagent fold does not spill into the strip",
  await page.locator("#agFold").isHidden());
await page.screenshot({ path: `${OUT}/i6-collapsed.png` });
await page.click("#chatPane .pfold");
check("unfolds again",
  !(await page.locator("#chatPane").evaluate(e => e.classList.contains("collapsed"))));

console.log("\n7 · send a turn — the chip must start EMPTY, then latch");
await page.fill(".pc textarea", "Regenerate the cynefin golden fixture.");
await page.keyboard.press("Enter");
await page.waitForTimeout(300);
const early = await page.locator(".turn:last-child .gv-chip").innerText();
check("chip is unlatched while the turn streams",
  early.includes("routing…") && !early.includes("Engine Library"), early.replace(/\n/g, " "));
await page.waitForTimeout(1200);
const latched = await page.locator(".turn:last-child .gv-chip").innerText();
check("chip latches once governance parsed",
  latched.includes("Engine Library") && latched.includes("D2"), latched.replace(/\n/g, " "));
await page.waitForTimeout(1600);
check("turn settles as answered",
  (await page.locator(".turn:last-child .a").innerText()).includes("answered"));
await page.screenshot({ path: `${OUT}/i7-new-turn.png` });

console.log("\n8 · light theme + reduced motion");
await page.click("#thm");
check("theme flips",
  (await page.getAttribute("html", "data-theme")) === "light");
await page.screenshot({ path: `${OUT}/i8-light.png` });
await page.click("#thm");

const rm = await b.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const p2 = await rm.newPage();
await p2.goto(URL, { waitUntil: "networkidle" });
const anim = await p2.locator(".trow.run .tstate").first()
  .evaluate(e => getComputedStyle(e).animationName);
check("run spinner respects prefers-reduced-motion", anim === "none", `animation-name=${anim}`);
await p2.screenshot({ path: `${OUT}/i9-reduced-motion.png` });

console.log("\n9 · page errors across the whole run");
check("still no JS errors", errs.length === 0, errs.join(" | "));

await b.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
