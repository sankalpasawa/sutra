# Building a chat app

| Field | Value |
|---|---|
| **status** | apps frameworks kit, chat profile |
| **updated** | 2026-09-12 |

A chat app is a conversation that opens with an opening message the builder wrote. The message is the whole app; there is no hidden prompt. The folder already exists when you read this: the record `APP.md` and the manifest `module.json`, whose `surface.instructions` will hold the opening message.

## Steps

1. Read `APP.md` first. Its first line is a stamp; never edit that line.
2. Ask one question at a time, in this order, and wait for each answer:
   who opens this chat and what they are trying to get done, and what they do today without it; one use, start to finish, and the smallest real thing someone will bring to it; what information it works with, where it lives, and which folder the chat may read and write; anything it must never do on its own (run commands, install things, send messages) and what it should say when the information is missing or wrong; who it is talking to and what it must never say; what in the opening message tells them tomorrow that it worked.
3. Then send ONE message with the rest filled in, for the builder to correct: the name and one line, who keeps it and the review date, what it replaces, the department it is filed under, and the opening message itself in full. Ask at the end whether it names a real borrower or account, and whether anyone besides the builder will use it.
4. Write the opening message to the person who will read it: one line saying what it does, a short list of what it never does, then one question. Under 4000 characters. No keys, no account numbers. Every command it may run goes in the Backend row of `APP.md`, word for word.
5. Put the opening message into `module.json` `surface.instructions`; set `name` and `tagline`; set `surface.cwd` only to a real folder inside the builder's home, or leave it out. Fill every row of `APP.md`. Create `data-policy.json` only if this chat calls a desktop service: one entry per call with the call, why it is needed, what could go wrong, and the check that covers it. If it calls nothing, do not create that file. Change nothing else in `module.json`.
6. Run the check before you say done:

```text
python3 <kit>/check.py <folder> --kind chat
```

   Fix every must-fix result; tell the builder the suggestions rather than hiding them.
7. Report the first words someone will see and the check result. Plain words, no headings, no status lines. Say "app", never the internal word.

## Rules for a chat

| Rule | Why |
|---|---|
| The opening message is the first thing a person reads | there is no hidden prompt |
| One line saying what it does, at most eight short rules, one closing ask, under 4000 characters | a first message, not a manual |
| No key, password, token or account number in it | it is visible to everyone who opens the chat |
| The folder it may use is a real folder inside the home directory | outside it the desktop silently substitutes its default |
| It never orders a command the builder did not write down in the record | what it may run is listed word for word |
| A desktop service call is written down in `data-policy.json` with why, what could go wrong, and the check that covers it | the file is the allowlist |

## What "done" means

The must-fix results are green: the record is complete, the name and line are set, no system jargon, the manifest matches the folder, only allowed files are present, the caps hold, the stamp agrees, no secret anywhere, a real folder if one is named, and the service allowlist present exactly when it is needed.

---
provenance: part of the Sutra apps frameworks kit; the checks and rules of record are in `../angles/*.rules.md`.
