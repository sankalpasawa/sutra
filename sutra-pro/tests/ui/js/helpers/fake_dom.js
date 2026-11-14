"use strict";
// A small DOM for the node tests of the chat view (no jsdom in this repo). It holds what the live view uses: elements, text, fragments, `template.innerHTML`, `innerHTML`, `textContent`,
// classList, dataset, hidden, simple selectors, serialisation, and a count of every element and text node ever created (`doc.created`) so a test can prove "no node was recreated".
// The parser reads the well formed markup the chat renderers write (ChatMarkdown is XML by design); it is not a general HTML parser.

const VOID = new Set(["br", "hr", "img", "input"]);
const ENT = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"};
const unescape = s => s.replace(/&(amp|lt|gt|quot|#39);/g, m => ENT[m]);
const escape = s => s.replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));
const escAttr = s => escape(s).replace(/"/g, "&quot;");

class Node {
  constructor(doc) { this.ownerDocument = doc; this.parentNode = null; this.childNodes = []; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  get nextSibling() { if (!this.parentNode) return null; const k = this.parentNode.childNodes; return k[k.indexOf(this) + 1] || null; }
  get previousSibling() { if (!this.parentNode) return null; const k = this.parentNode.childNodes; return k[k.indexOf(this) - 1] || null; }
  _detach() { if (this.parentNode) { const k = this.parentNode.childNodes; k.splice(k.indexOf(this), 1); this.parentNode = null; } }
  appendChild(n) { return this.insertBefore(n, null); }
  insertBefore(n, ref) {
    if (n instanceof DocumentFragment) { Array.from(n.childNodes).forEach(c => this.insertBefore(c, ref)); return n; }
    n._detach();
    const at = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    this.childNodes.splice(at < 0 ? this.childNodes.length : at, 0, n);
    n.parentNode = this;
    return n;
  }
  removeChild(n) { if (n.parentNode !== this) throw new Error("not a child"); n._detach(); return n; }
  replaceChild(n, old) { this.insertBefore(n, old); old._detach(); return old; }
  remove() { this._detach(); }
  contains(n) { for (let x = n; x; x = x.parentNode) if (x === this) return true; return false; }
  get children() { return this.childNodes.filter(c => c instanceof Element); }
  get firstElementChild() { return this.children[0] || null; }
  get textContent() { return this.childNodes.map(c => c.textContent).join(""); }
  set textContent(v) { this.childNodes.slice().forEach(c => c._detach()); if (v !== "" && v !== null && v !== undefined) this.appendChild(this.ownerDocument.createTextNode(String(v))); }
}

class Text extends Node {
  constructor(doc, data) { super(doc); this.data = data; doc.created += 1; }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
  get nodeType() { return 3; }
}

class DocumentFragment extends Node {}

class ClassList {
  constructor(el) { this.el = el; }
  _list() { return (this.el.attrs.class || "").split(/\s+/).filter(Boolean); }
  _set(l) { if (l.length) this.el.attrs.class = l.join(" "); else delete this.el.attrs.class; }
  add(...c) { const l = this._list(); c.forEach(x => { if (!l.includes(x)) l.push(x); }); this._set(l); }
  remove(...c) { this._set(this._list().filter(x => !c.includes(x))); }
  contains(c) { return this._list().includes(c); }
  toggle(c, force) { const has = this.contains(c); const want = force === undefined ? !has : !!force; if (want) this.add(c); else this.remove(c); return want; }
}

class Element extends Node {
  constructor(doc, tag) {
    super(doc);
    this.tagName = tag.toUpperCase();
    this.attrs = {};
    this.listeners = {};
    this.classList = new ClassList(this);
    const self = this;
    this.dataset = new Proxy({}, {
      get: (t, k) => (typeof k === "string" ? self.attrs["data-" + k.replace(/[A-Z]/g, m => "-" + m.toLowerCase())] : undefined),
      set: (t, k, v) => { self.attrs["data-" + k.replace(/[A-Z]/g, m => "-" + m.toLowerCase())] = String(v); return true; },
      deleteProperty: (t, k) => { delete self.attrs["data-" + k.replace(/[A-Z]/g, m => "-" + m.toLowerCase())]; return true; },
    });
    doc.created += 1;
    doc.elements += 1;
  }
  get nodeType() { return 1; }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = v; }
  get id() { return this.attrs.id || ""; }
  set id(v) { this.attrs.id = v; }
  get hidden() { return "hidden" in this.attrs; }
  set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; }
  get disabled() { return "disabled" in this.attrs; }
  set disabled(v) { if (v) this.attrs.disabled = ""; else delete this.attrs.disabled; }
  get open() { return "open" in this.attrs; }
  set open(v) { if (v) this.attrs.open = ""; else delete this.attrs.open; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  removeEventListener(t, fn) { this.listeners[t] = (this.listeners[t] || []).filter(f => f !== fn); }
  get innerHTML() { return this.childNodes.map(serialize).join(""); }
  set innerHTML(html) { this.childNodes.slice().forEach(c => c._detach()); parse(this.ownerDocument, html).forEach(n => this.appendChild(n)); }
  get outerHTML() { return serialize(this); }
  get content() { return this._content; }
  closest(sel) { for (let x = this; x instanceof Element; x = x.parentNode) if (matches(x, sel)) return x; return null; }
  matches(sel) { return matches(this, sel); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const walk = n => n.children.forEach(c => { if (matches(c, sel)) out.push(c); walk(c); });
    walk(this);
    return out;
  }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView() {}
}

// one compound selector, or a comma list of them: tag, .class, [attr], [attr="v"], any joined together (no combinators)
function matches(el, selector) {
  return selector.split(",").some(sel => matchesChain(el, sel.trim()));
}

// "a b" (descendant) and "a > b" (child) chains of compound selectors, matched from the right
function matchesChain(el, sel) {
  const tokens = sel.replace(/\s*>\s*/g, " > ").split(/\s+/).filter(Boolean);
  if (tokens.length === 1) return matchesCompound(el, tokens[0]);
  const last = tokens.pop();
  if (!matchesCompound(el, last)) return false;
  let node = el;
  while (tokens.length > 0) {
    let want = tokens.pop();
    let child = false;
    if (want === ">") { child = true; want = tokens.pop(); }
    node = node.parentNode;
    if (child) { if (!(node instanceof Element) || !matchesCompound(node, want)) return false; }
    else { while (node instanceof Element && !matchesCompound(node, want)) node = node.parentNode; if (!(node instanceof Element)) return false; }
  }
  return true;
}

function matchesCompound(el, sel) {
  {
    const re = /^([a-zA-Z][\w-]*)?((?:\.[\w-]+|\[[\w-]+(?:="[^"]*")?\]|:not\([^)]*\))*)$/.exec(sel);
    if (!re) return false;
    if (re[1] && el.tagName.toLowerCase() !== re[1].toLowerCase()) return false;
    const parts = re[2].match(/\.[\w-]+|\[[\w-]+(?:="[^"]*")?\]|:not\([^)]*\)/g) || [];
    return parts.every(p => {
      if (p[0] === ".") return el.classList.contains(p.slice(1));
      if (p.startsWith(":not(")) return !matches(el, p.slice(5, -1));
      const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(p);
      return m[2] === undefined ? el.hasAttribute(m[1]) : el.getAttribute(m[1]) === m[2];
    });
  }
}

function serialize(n) {
  if (n instanceof Text) return escape(n.data);
  const tag = n.tagName.toLowerCase();
  const attrs = Object.entries(n.attrs).map(([k, v]) => " " + k + '="' + escAttr(v) + '"').join("");
  if (VOID.has(tag)) return "<" + tag + attrs + "/>";
  return "<" + tag + attrs + ">" + n.childNodes.map(serialize).join("") + "</" + tag + ">";
}

function parse(doc, html) {
  const root = new DocumentFragment(doc);
  const stack = [root];
  const re = /<(\/)?([a-zA-Z][\w-]*)((?:\s+[\w-]+(?:="[^"]*")?)*)\s*(\/)?>|([^<]+)/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) { top.appendChild(doc.createTextNode(unescape(m[5]))); continue; }
    if (m[1]) { stack.pop(); continue; }
    const el = doc.createElement(m[2]);
    (m[3].match(/[\w-]+(?:="[^"]*")?/g) || []).forEach(a => { const i = a.indexOf("="); if (i < 0) el.attrs[a] = ""; else el.attrs[a.slice(0, i)] = unescape(a.slice(i + 2, -1)); });
    top.appendChild(el);
    if (!m[4] && !VOID.has(m[2].toLowerCase())) stack.push(el);
  }
  return root.childNodes.slice();
}

function createDocument() {
  const doc = {created: 0, elements: 0, activeElement: null};
  doc.createElement = tag => {
    const el = new Element(doc, tag);
    if (tag.toLowerCase() === "template") {
      el._content = new DocumentFragment(doc);
      Object.defineProperty(el, "innerHTML", {get: () => el._content.childNodes.map(serialize).join(""), set: html => { el._content.childNodes.slice().forEach(c => c._detach()); parse(doc, html).forEach(n => el._content.appendChild(n)); }});
    }
    return el;
  };
  doc.createTextNode = data => new Text(doc, String(data));
  doc.createDocumentFragment = () => new DocumentFragment(doc);
  doc.body = doc.createElement("body");
  return doc;
}

module.exports = {createDocument, serialize, Element, Text};
