# Backend

| Field | Value |
|---|---|
| **status** | apps frameworks kit, backend angle |
| **updated** | 2026-09-12 |

Fix where the data comes from, what the app may touch, and what it may never do on its own. It differs by kind.

## What you will be asked

- What information does it work with, and where does that live?
- Chat: which folder may this chat read and write?
- Chat: anything it must never do on its own: run commands, install things, send messages?
- Link: which screen should this open?
- At the end, page and chat: does any of it name a real borrower, account or loan number?

## What it produces

The Backend row of the record. A chat that calls one of the desktop's own services also gets a small `data-policy.json` naming each call; a page never does.

## Rules in plain words

| Rule | Applies to | Why |
|---|---|---|
| A page has no network: nothing it tries to fetch, load or send goes anywhere | page | the page runs sealed inside the desktop; the check names the call so the silence is not mistaken for success |
| A page's data lives inside `index.html` | page | files next to it are not served while it runs |
| Images and fonts are embedded as data | page | nothing external loads |
| Only a chat can use a desktop service, and each call is written down with why, what could go wrong, and which check covers it | chat | the file is the allowlist |
| The opening message never carries a key, password, token or account number | chat | it is the first thing a person reads |
| The chat's folder is a real folder inside your home | chat | outside it the desktop silently substitutes its default |
| The message never orders a command you did not write down in the record | chat | what the chat may run is listed word for word |
| A link opens one live screen of the desktop and nothing else | link | never a web address, never the terminal |
| Nothing leaves this machine unless you switch sharing on | all | sharing is off by default |
| Before an app is handed to someone else, the record says whether the data is real, masked, made-up or aggregate | page, chat | so nobody ships a real borrower's row by accident |

## What "done" checks here

Page: no network call and nothing referenced outside the file. Chat: a real folder, and the service allowlist present exactly when it is needed. Link: a live screen and nothing else. All kinds: no secret anywhere in the folder.

---
provenance: part of the Sutra apps frameworks kit; the rules of record with their sources are in `backend.rules.md` next to this file.
