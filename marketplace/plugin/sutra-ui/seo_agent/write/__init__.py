"""write — the write phase: planner, architect, writer, one module per step.

The planner vets the material (gather, select, freeze), the architect shapes it to its format
(shape, enrich, brand_cards, allocate_words, section_keywords, headings), and the writer turns it
into an article (write_body, source_check, blend, wrapper, coherence, readable, sentence_pass,
slop_pass, the links pass in editing/, clean, assemble). tools/write_article.py sequences them. The
source check sits right after the body is written: it judges only the claims the article carries,
one page each, and fixes in place what no page supports.

THE FORMAT IS NOT DECIDED HERE (2026-09-16). It used to be routed by its own step, fmt_router, from
a free-text guess the winners study made. That step is gone: the format is now decided once, by a
person, at the run_research checkpoint (research/winners.route_format, called from
tools/run_research.py), and travels in artifacts/decisions.json. gather.run() reads it from there
through write/_common.decisions(), and every later step reads it off the plan gather built —
carried forward, never re-decided.

Every step is `run(<inputs>) -> dict` and knows nothing about the run folder. The tool saves each
step's output as an artifact (work-<step>.json) so a run that stops resumes where it left off.
"""
