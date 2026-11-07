'use strict';
/* The two pages the window shows before the server's own: "starting" and "could not start" (D118). Plain HTML with no script, loaded as a data
   address, and every piece of text that comes from outside is escaped. The colours are those of the app's own dark and light themes. */

const THEMES = {
  dark: { bg: '#161513', ink: '#ece6dc', muted: '#9a9186', line: '#2e2b27' },
  light: { bg: '#f6f2ec', ink: '#2b2620', muted: '#6b6155', line: '#e6dfd4' },
};

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

function page({ title, heading, message, logo, dark, spinner = false, output = [], footer = '' }) {
  const colours = THEMES[dark ? 'dark' : 'light'];
  const image = logo ? `<img src="${escapeHtml(logo)}" width="96" height="96" alt="">` : '';
  const lines = output.length
    ? `<pre>${output.map((line) => escapeHtml(line)).join('\n')}</pre>`
    : '';
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>${escapeHtml(title)}</title>
<style>
html,body{height:100%;margin:0;background:${colours.bg};color:${colours.ink};font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
body{display:flex;align-items:center;justify-content:center;-webkit-user-select:none;user-select:none}
main{max-width:640px;padding:32px;text-align:center}
img{border-radius:22px;margin-bottom:20px}
h1{font-size:20px;font-weight:600;margin:0 0 8px}
p{margin:0 0 6px;color:${colours.muted}}
pre{margin:16px 0 0;padding:12px 14px;border:1px solid ${colours.line};border-radius:8px;text-align:left;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace;color:${colours.muted};white-space:pre-wrap;word-break:break-word;max-height:240px;overflow:auto;-webkit-user-select:text;user-select:text}
.spin{width:22px;height:22px;margin:18px auto 0;border:2px solid ${colours.line};border-top-color:${colours.muted};border-radius:50%;animation:s 0.9s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body><main>
${image}
<h1>${escapeHtml(heading)}</h1>
<p>${escapeHtml(message)}</p>${footer ? `\n<p>${escapeHtml(footer)}</p>` : ''}
${spinner ? '<div class="spin"></div>' : ''}
${lines}
</main></body></html>`;
}

function splashPage({ logo, dark }) {
  return page({ title: 'Sutra Pro', heading: 'Sutra Pro', message: 'Starting the local server…', logo, dark, spinner: true });
}

function errorPage({ message, output, logFile, logo, dark }) {
  return page({
    title: 'Sutra Pro could not start', heading: 'Sutra Pro could not start', message, logo, dark, output: output || [],
    footer: logFile ? `The full log is ${logFile}` : '',
  });
}

function dataUrl(html) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

module.exports = { splashPage, errorPage, dataUrl, escapeHtml, THEMES };
