"""write — the write phase: planner, architect, writer, one module per step.

The planner vets the material (gather, select, freeze), the architect shapes it to its format
(fmt_router, shape, enrich, brand_cards, allocate_words, section_keywords, headings), and the writer
turns it into an article (write_body, source_check, blend, wrapper, coherence, readable,
sentence_pass, slop_pass, the links pass in editing/, clean, assemble). tools/write_article.py
sequences them. The source check sits right after the body is written: it judges only the claims
the article carries, one page each, and fixes in place what no page supports.

Every step is `run(<inputs>) -> dict` and knows nothing about the run folder. The tool saves each
step's output as an artifact (work-<step>.json) so a run that stops resumes where it left off.
"""
