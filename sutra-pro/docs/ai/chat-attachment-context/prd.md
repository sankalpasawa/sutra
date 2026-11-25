# PRD: A file attached to a chat reaches the model, or the owner is told why not
_Status: Proposed · Date: 2026-11-25 · Product: Sutra Pro 0.8.2 · Branch: fix/chat-attachment-context · Architecture: ./architecture.md_

## 1. Problem
The owner attaches a file to a chat, sends, and the model answers as if no file existed. Nothing on screen says the file was left out.

Investigation (see architecture.md section 2) found that the server path for a file that is attached and uploaded works: the file's content reaches the Claude or Codex invocation. The file is lost earlier or later, and always silently:

| # | Where the file is lost | What the owner sees |
|---|---|---|
| L1 | The page refuses a file by type or size. No chip is made; a one-line note is set and cleared by the next action | Send works; the model gets no file |
| L2 | An upload fails (server refuses the kind, a network error). The chip says "not attached" but Send is not blocked, and a send drops the chip with the rest | Send works; the model gets no file |
| L3 | The owner is in "Tell the team" (the default). The attach button is not drawn there; chips attached earlier stay in memory but are hidden, and the team route ignores them | A message goes to the team with no file, no warning |
| L4 | Types people actually attach are refused: Word, Excel, PowerPoint, RTF, notebooks, most source languages, non-UTF-8 text (Excel CSV) | A refusal sentence (L1/L2 then hide it) |
| L5 | A later turn that starts a new model session (the owner changes the working folder, switches provider, or the session is lost) is rebuilt from the stored transcript, which holds only "(attached: notes.txt)" | The model "forgets" a file it read two messages ago |

## 2. Users
| User | Need |
|---|---|
| Owner (non-technical, one machine) | Drop a file in, ask about it, trust the answer is about that file |
| Owner on Claude | PDFs and images read natively |
| Owner on Codex | Images and text; a PDF is refused with a sentence |

## 3. Goals and non-goals
| Goals | Non-goals |
|---|---|
| G1 An attached file is either read by the model or the send is refused with a sentence naming the file and the reason | No cloud storage, no upload to any service other than the chosen provider's CLI |
| G2 The owner can see what the model received (name, kind, how much of it) | No OCR, no image-to-text, no new model calls to summarise a file |
| G3 Common office and text types work (Word, extra source and data types, non-UTF-8 text) | No Excel/PowerPoint parsing in this fix (Word only, via the dependency already shipped) |
| G4 A file stays in context for the later turns of the chat, including after a new model session | No change to the 20 MB, 10 files and 40,000-character inline limits |
| G5 No behaviour change for a chat with no file | No change to the team route's own semantics or to project work |
| | No PDF text extraction for Codex (needs a new dependency); the refusal sentence stays |

## 4. Requirements
Each has an acceptance criterion (AC) that a test can fail on. Ids are used in architecture.md section 8.

| Id | Requirement | Acceptance criterion |
|---|---|---|
| FR-1 | A file the page refuses (type, size, empty, over 10 files) appears as a chip marked "not attached: <reason>" and stays until the owner removes it | Add `a.exe`: a failed chip with the sentence exists after the next keystroke and after another file is added |
| FR-2 | Send is disabled while any chip is failed or uploading, with the reason on the button's title and in the note | Failed chip present: `button()` is disabled and `send()` returns `{ok:false}` with a sentence; no POST is made |
| FR-3 | In "Tell the team" a file cannot be lost: attaching switches to the model (as now) and the file bar stays visible in both modes; sending to the team while a ready or failed chip exists is refused with "Files go only to the model. Remove them, or ask the model." | With a ready chip and mode `team`: team send makes no POST and returns the sentence; the chips are drawn |
| FR-4 | The server answers `POST /api/chats/{sid}/direct` with `files`: for each attachment `{name, kind, sent, chars, cut}` where `sent` is `text`, `image`, `pdf` or `refused` | Post a 50,000-char text file: response `files[0].cut` is true and `chars` is 40000 |
| FR-5 | After the turn is accepted the page shows what the model received under the owner's line ("Read: notes.txt (all 12,000 characters)", "Read: big.csv (first 40,000 of 90,000 characters)", "Sent as an image: shot.png") | Page test with the 202 body: the line text is rendered, escaped |
| FR-6 | `.docx` is accepted and delivered as text (paragraphs, tables as tab-separated rows), kind `text`, same 40,000 cut | Upload a fixture docx: `deliver` text contains its paragraph and a table cell |
| FR-7 | More text types are accepted: .c .h .cpp .hpp .cs .php .swift .kt .scala .lua .r .tex .rtf-free types, .jsonl .ipynb .tf .gradle .properties .conf .cfg .bat .ps1 and named files Makefile, Dockerfile, README, LICENSE. `.env`, key and secret-bearing names stay refused | Upload each: accepted. `.env`, `id_rsa`, `credentials.json` refused with the same sentence |
| FR-8 | Text that is not UTF-8 is accepted when it decodes as UTF-16 (BOM) or Windows-1252 and holds no NUL byte outside UTF-16; the model gets it decoded | Upload cp1252 CSV with "caf\xe9": delivered text has "café" |
| FR-9 | A file the owner attached stays readable by later turns: when a new model session is built (folder change, provider switch, lost session) the carry-over holds each earlier attachment's text, bounded by the carry-over budget | Turn 1 attaches `notes.txt`; change the folder; turn 2 asks about it: the prompt of turn 2 contains the file's text |
| FR-10 | A file that cannot be delivered (PDF to Codex; stored file gone) refuses the whole send before any process starts, naming the file; the owner's line is not stored as sent and the typed text stays in the box | Codex chat with a PDF: 4xx with the file name; no owner line is stored; box text kept |
| FR-11 | An image or PDF the chosen provider cannot take is refused by the same rule (FR-10), judged by the provider that will actually run, including after a router fallback | Router falls back claude to codex with a PDF attached: refusal with the name, not a silent drop |
| FR-12 | Files are local only: stored under `<data>/attachments`, sent only to the CLI of the chosen provider, never logged by content, never inside a project folder | Static test: attachment text is absent from `calls.jsonl`, logs and the egress audit row (which holds sizes only) |
| FR-13 | The chat's record keeps what was attached with the owner's line, so a reload shows the same receipt | Reload a chat: the receipt line is drawn from stored data |

## 5. File types and limits
| Kind | Types | Provider | Limit |
|---|---|---|---|
| image | png, jpeg, gif, webp (by signature) | Claude, Codex | 20 MB |
| pdf | by signature | Claude only; Codex refused with a sentence | 20 MB |
| text | the extension list (FR-7), plus .docx extracted, UTF-8, UTF-16 BOM or cp1252 | both | 20 MB stored; first 40,000 characters read, the cut said in the prompt and on the page |
| per message | 10 files; message text 8,000 characters | | unchanged |

## 6. Failure UX (the sentences)
| Case | Sentence | Where |
|---|---|---|
| Type not taken | "<name>: only images, PDFs, Word and text files can be attached." | failed chip |
| Over size | "<name> is over 20 MB." | failed chip |
| Empty | "<name> is empty." | failed chip |
| Upload failed | "<name>: it could not be sent. Remove it and try again." | failed chip |
| Send with a failed chip | "Remove the file that was not attached, or it will not be read." | note, button disabled |
| Team send with files | "Files go only to the model. Remove them, or ask the model." | note |
| PDF on Codex | "codex cannot take a PDF: <name>. Choose Claude for this chat to send it." (exists) | banner, text kept |
| Cut text | "Read the first 40,000 of N characters of <name>." | receipt under the owner's line |

## 7. Privacy
Local only. A file is stored once under `<data>/attachments/<sha256>.<ext>` with mode 0600, never in a project folder, and reaches only the CLI of the provider the owner chose (the same trust boundary as the message text). Content passes the existing egress scrub before the send (credential shapes replaced). No content in logs, `calls.jsonl`, or the egress audit row (sizes and shape counts only). File text is fenced and labelled as data, never as instructions (exists). Deleting a chat does not delete a shared stored file in this change (stored once per content); a follow-up owns retention.

## 8. Non-functional
| Id | Requirement |
|---|---|
| NFR-1 | Backward compatible: `/direct` request unchanged; the response gains `files`; a client that ignores it works |
| NFR-2 | A chat with no file runs the same code and produces the same prompt as today (golden: byte-equal) |
| NFR-3 | docx extraction runs on a worker thread, is bounded to the 20 MB file and 40,000 output characters, and a malformed docx is a refusal sentence, never a 500 |
| NFR-4 | No new dependency (python-docx is already in pyproject) |
| NFR-5 | The UI package keeps its import boundary; all strings escaped |

## 9. Open questions
| Id | Question | Default if unanswered |
|---|---|---|
| OQ-1 | Reproduce on the owner's machine: which mode, which file type? The code review explains L1 to L5 but cannot tell which one was hit | Fix all five |
| OQ-2 | FR-9 stores attachment text in carry-over only; should the owner's line meta hold the ids? | Yes: ids in line meta, text read from the store at carry-over time |
| OQ-3 | Excel and PowerPoint | Out of scope now; ask for a decision after FR-6 ships |
