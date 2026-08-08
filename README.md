# Skill-SlideMaking

Maintain one LaTeX source for a Beamer deck and its spoken manuscript, then build two synchronized PDFs:

- `slides.pdf` — the projected Beamer deck;
- `speaker_notes.pdf` — one page per slide, with the slide thumbnail and private note on the left and the full speech on the right.

The builder binds every page by a stable slide ID and stops on duplicate or missing IDs, missing notes or speeches, overlays, or any compiled page-count mismatch. Inserting, deleting, or reordering a slide therefore cannot silently shift the manuscript onto the wrong page.

## Quick start

Copy `skill/assets/beamer-template.tex`, edit it, and keep this authoring contract for every slide:

```tex
\begin{paperframe}{S03}{Why this problem is hard}
  % Normal Beamer frame content
\end{paperframe}
\note{A short private reminder, formula cue, or delivery instruction.}
\speech{The complete spoken explanation for this slide.}
```

Frame options are supported before the ID, for example `\begin{paperframe}[plain]{S01}{}`. IDs must be unique and stable; when inserting between `S04` and `S05`, prefer `S04A` instead of renumbering old slides.

Build from the repository root:

```bash
python3 skill/scripts/build_dual_pdf.py path/to/talk.tex --output build
```

The command writes both PDFs, a page-binding manifest, generated TeX used for diagnostics, and rendered PNGs when `pdftoppm` is available. It requires Python 3.10+, `latexmk`, XeLaTeX, and the LaTeX packages used by the source.

## Contract and safety checks

- Use `paperframe`; raw `frame` environments are rejected.
- Put exactly one `\note{...}` and one `\speech{...}` immediately after each `paperframe`.
- Nested braces, equations, paragraphs, and Chinese text are parsed without flattening.
- Overlays and multi-page frames are rejected because one logical slide must produce one PDF page.
- The builder compiles slides first, verifies their page count, then generates the notes PDF with page `n` of `slides.pdf` bound to frame `n`.
- A final manifest records `page`, `id`, and `title`, and both PDFs must have the same number of pages.

For custom commands used only in the manuscript, add one brace-delimited block in the same source preamble:

```tex
\NotesPreamble{
  \newcommand{\solver}{branch-and-cut solver}
}
```

The block is removed from the Beamer build and injected into the notes build. The user still maintains only one content source.

## Tests

Run the complete test suite with:

```bash
python3 -m unittest discover -s tests -v
```

Parser and validation tests have no third-party Python dependency. The integration test performs a real XeLaTeX build when the TeX toolchain is present. GitHub Actions installs the required TeX and CJK font packages and runs the same suite.

No license has been selected yet.
