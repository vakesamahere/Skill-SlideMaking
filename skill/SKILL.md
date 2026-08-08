---
name: latex-paper-slides
description: Create or revise an academic-paper presentation from one LaTeX source that builds synchronized Beamer slides and a page-by-page speaker-notes PDF with each slide thumbnail, private note, and full speech. Use for LaTeX PPT, Beamer, 论文汇报, reading-group or journal-club slides, 逐页备注稿/讲稿, dual-PDF slide-and-notes builds, or incremental r1/r2/r3 revisions. Covers paper classification, contribution/evidence analysis, concise visual slides, concrete technical explanations, stable slide IDs, build validation, timing checks, and rendered visual QA.
---

# LaTeX Paper Slides

Maintain one author-edited `.tex` source and generate two synchronized outputs:

1. `slides.pdf` — concise 16:9 Beamer slides.
2. `speaker_notes.pdf` — one page per slide: slide thumbnail and private `note` in the left column, full `speech` in the right column.

Use the deterministic builder and contract below. Do not create a separate Markdown manuscript.

## Establish the single-source contract

Copy [assets/beamer-template.tex](assets/beamer-template.tex) and [assets/references-template.bib](assets/references-template.bib) into the deliverable folder. Keep figures in `figures/`.

Write every slide as:

```tex
\begin{paperframe}{S03}{Why the problem is hard}
  % normal Beamer content
\end{paperframe}
\note{Short private cue or delivery reminder.}
\speech{Complete spoken explanation for this slide.}
```

Use a stable, unique ID. To insert between `S04` and `S05`, prefer `S04A`; do not renumber unchanged slides. Put exactly one brace-delimited `\note` and `\speech` immediately after each `paperframe`. Nested braces and paragraphs are supported.

Do not use raw `frame`, overlays, `\pause`, incremental-reveal commands, or `allowframebreaks`. One logical frame must compile to one PDF page. The builder rejects violations and compiled page mismatches.

If notes need custom macros, put one `\NotesPreamble{...}` block in the same source preamble. The builder injects it only into the notes build.

Read [references/source-contract.md](references/source-contract.md) before changing the template or debugging a build.

## Understand the paper before drafting

Determine the paper, target duration, audience, language, emphasis, and named baseline. Classify the paper as survey/review, original method, empirical/application, tutorial, benchmark, perspective, or position paper.

Separate authors' contributions from prior work. For a survey, describe the actual contribution—taxonomy, comparison, synthesis, gap analysis, or research agenda—without attributing reviewed algorithms to the survey authors.

Plan slides and speech together. For every frame specify its ID, one takeaway, visual/compact structure, evidence, speech purpose, and estimated time. Make estimates sum to the target duration, normally with a 5–10% delivery buffer.

Use a teaching order: paper identity and question; motivation; prerequisites; taxonomy or method; evidence or representative studies; limitations/open questions; takeaways. Label prerequisite slides **前置知识** when useful.

## Write slides and speech at different densities

Keep one claim per slide. Prefer figures, equations, diagrams, and compact comparisons over paragraphs. Put reasoning and examples in `\speech`, not on the projected slide. Keep citations legible and near claims.

For each technical point, use the smallest helpful subset of: plain definition; exact inputs; operation/decision; output/use; speakable example; practical significance; limitation; transition. Expand abbreviations on first spoken use. Name concrete candidates, states, and decisions instead of saying only that a model “uses history” or “handles variable input.”

Read [references/explanation-patterns.md](references/explanation-patterns.md) while drafting technical speech.

For Chinese or mixed-language work, use XeLaTeX and configure an installed CJK font in the source. Missing-glyph warnings are build failures.

## Revise incrementally

When the user names r3 or another baseline:

1. Copy that baseline forward.
2. Map requested changes to stable IDs and `note`/`speech` blocks.
3. Change only those locations.
4. Preserve all other wording, examples, order, IDs, LaTeX style, and filenames.
5. Keep additions in `speech` when the user says the slide need not change.
6. Compare sources and disclose any necessary adjacent edit.

Never rewrite all speech to standardize tone. Read [references/revision-and-qa.md](references/revision-and-qa.md) for the final checklist.

## Build and validate

Build early and after every material edit:

```bash
python3 /path/to/this-skill/scripts/build_dual_pdf.py talk.tex --output build
```

The command parses the source with a brace-aware scanner, validates IDs and attachments, compiles slides, checks one page per frame, generates the notes document from the same ordered frame objects, compiles it, verifies equal PDF page counts, writes `page_map.json`, and renders PNGs when `pdftoppm` is available.

Inspect every image under `build/review/slides/` and `build/review/speaker_notes/`. Check clipping, overflow, tiny text, contrast, broken CJK glyphs, missing figures, and the first/inserted/last ID bindings. Do not call a draft complete until source validation, both PDF builds, page-count checks, and rendered review pass.

## Deliver

Return at least the editable single-source `.tex`, `slides.pdf`, `speaker_notes.pdf`, bibliography, and used figures. Include a concise change summary for revisions. The generated TeX and page map are diagnostics, not additional author-maintained sources.
