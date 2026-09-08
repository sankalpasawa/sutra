---
name: writing-llm-md
description: Author or materially edit any .md per the LLM-first standard R1-R10 (metadata block, typed lists, mermaid + edge-list twin, no ASCII art, explicit anchors, claim refs, provenance footer, hub-and-spoke chunking). Enforced by md-standard-gate hook.
---

# writing-llm-md — the LLM-first markdown authoring standard

- **title**: LLM-first markdown authoring standard
- **status**: v1.1 · L1 staging (promote to plugin skill by 2026-09-05)
- **scope**: every .md file authored or MATERIALLY EDITED in Asawa/Sutra repos (artifact-triggered — not just explicit "create a doc" asks)
- **owner**: Sutra core (Claude sessions in asawa-holding)
- **updated**: 2026-08-05
- **source inputs**: founder ruling 2026-08-05 (md files are LLM-first; humans read rendered surfaces) · codex consult (4 P1 + 6 P2 folded) · READABILITY-STANDARD.md (terminal surface, sibling not parent)

## 1. Purpose

Markdown files in these repos are read by LLMs first; humans read them rendered (Obsidian, GitHub). This standard makes every .md maximally parseable, retrievable, and editable by a model — without losing the human render. Sibling standards: `sutra/layer2-operating-system/READABILITY-STANDARD.md` governs TERMINAL output; `core:prd-discipline` governs PRDs; this file governs general markdown.

## 2. The rules

| # | Rule | Why (LLM mechanics) |
|---|---|---|
| R1 | First line after the title: one-sentence purpose. Then a metadata block: title, status, scope, owner, updated, source inputs | retrieval + disambiguation before the model reads the body |
| R2 | Substance lives in NARROW tables and typed lists — one concept per row, no multi-sentence cells; split wide tables by dimension | wide tables and paragraph-cells degrade parsing |
| R3 | Graphs: mermaid fence for orientation PLUS an adjacent textual edge list as source of truth | mermaid is presentation; the edge list is the parseable contract |
| R4 | ASCII art: never in files | forces topology reconstruction from whitespace; breaks under tokenization |
| R5 | Headings default max H3; deeper only in generated reference docs; use typed lists instead of H4+ | stable structure, shallow outline the model can hold |
| R6 | Anchors: explicit `<a id="slug"></a>` (or a stated deterministic slug rule) on any section other docs link to; no heading churn on linked sections without updating inbound links | renderer-generated anchors diverge; links rot silently |
| R7 | Repo-grounded claims carry file:line refs. Claims with no stable source carry a typed label instead: **Decision** / **Assumption** / **Inference** / **Open question** | forced refs on unsourceable claims produce fabrication; labels keep epistemics explicit |
| R8 | Evolving docs mark rule state: **Current rule** / **Historical context** / **Deprecated** / **Migration note** | stale rationale otherwise reads as active policy |
| R9 | Canonical entity names: expand on first use, then never drift to synonyms within a doc family | synonym drift fragments retrieval and reasoning |
| R10 | Provenance footer, machine-scannable (schema in §4) | audit + supersession chain without archaeology |
| R11 | Progressive headings (never jump H1→H3) and exactly ONE H1 per file | unambiguous outline; matches markdownlint MD001/MD025 |
| R12 | Every code fence carries a language tag; `text`/`console`/`json`/`yaml`/`mermaid` are valid — never force a programming language on transcripts/config | parser knows what it is reading; matches LLM-friendly docs practice |

## 3. Chunking — hub-and-spoke

- One decision/domain per file, self-contained: purpose line, scope boundary, dependencies, outbound links.
- Chunk by decision/domain boundary, NOT by length. Do not over-chunk — tiny files create retrieval overhead and lose local coherence.
- Index (hub) files map children WITHOUT duplicating substance; every index row states **"read this when …"** so a model can select context without loading everything.
- Every child links back to its parent index.

## 4. Provenance footer schema

Last section of every doc, compact:

```
provenance: {author: <agent|person>, date: YYYY-MM-DD, inputs: [<sources>], review: <none|codex|dual-lane|founder>, supersedes: <path|none>, confidence: <high|moderate|low>, gaps: [<known gaps>]}
```

## 5. How this fires (three layers)

| Layer | Mechanism | Status |
|---|---|---|
| 1 Deliberate asks | CLAUDE.md NL routing row → `W-md-authoring` (registry audit) + Claude effector applies this standard | live 2026-08-05 |
| 2 Any .md authoring | this checklist applies to EVERY material .md write/edit, routed or not — the artifact is the trigger, not the utterance | live (best-effort, model-side) |
| 3 Enforcement | `holding/hooks/md-standard-gate.sh` (PostToolUse Edit\|Write): HARD exit-2 for NEW untracked .md missing metadata/provenance or containing box art (fence-aware); advisory for tracked files | SHIPPED 2026-08-05 (this repo, L1) |

**Ratchet** (Current rule): new files HARD now; legacy corpus advisory during a migration window; W2 follow-up adds a baseline allowlist — files leaving the baseline must stay clean (codex P1). Do not treat tracked-file warnings as compliance.

## 7. External standards adopted (researched 2026-08-05)

| Source | What we adopt | Status |
|---|---|---|
| CommonMark + GFM | the syntax baseline (tables, fences, task lists) | adopted (implicit before, explicit now) |
| markdownlint MD001/MD025 | progressive headings, single H1 → R11 | adopted |
| LLM-friendly docs practice (Fern et al.) | self-contained sections ("a complete thought that makes sense retrieved independently"), explicit relationships over implied, language-tagged fences → R12, §3 wording | adopted |
| llms.txt (Answer.AI proposal, 2024) | repo-root `/llms.txt` as the hub-of-hubs — **an internal navigation contract**: our real consumer is in-repo Claude sessions, and we make no claim external engines read it (honest status: proposal, no confirmed consumer engines) | adopted, scoped |
| llms-full.txt · `<llms-only>`/`<llms-ignore>` tags | split-audience machinery | NOT adopted — no split audience in internal repos |
| markdownlint MD013 line-length 80 | hard line-length cap | NOT adopted — narrow-table rule (R2) covers the real failure; hard caps fight table rows |

## 6. Author checklist (apply before finishing any .md)

1. Purpose line + metadata block present (R1)
2. No ASCII art; tables narrow; mermaid has its edge-list twin (R2-R4)
3. Anchors explicit on linked sections (R6)
4. Every claim: file:line ref OR typed label (R7)
5. Rule-state markers on anything that changed (R8)
6. Provenance footer (R10)

---

provenance: {author: claude (session 92edec80), date: 2026-08-05, inputs: [founder rulings 2026-08-05, 2x codex consults (gate-log.jsonl), web research (llms.txt guides, markdownlint, Fern LLM-friendly docs)], review: codex, supersedes: v1.0 same path, confidence: high, gaps: [ratchet baseline allowlist pending (W2); promotion to plugin skill pending dogfood]}
