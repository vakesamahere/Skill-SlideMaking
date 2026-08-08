# Skill-SlideMaking

Maintain one LaTeX source for a Beamer deck and its spoken manuscript, then build two synchronized PDFs:

- `slides.pdf` — the projected Beamer deck;
- `speaker_notes.pdf` — one page per physical slide output, with the slide thumbnail and private note on the left and the full speech on the right.

The default builder is backward-compatible with ordinary Beamer. Existing `frame` environments and `\frame{...}` shorthand remain unchanged, and `\note` or `\speech` can be added gradually. A strict mode preserves the stable-ID final-delivery contract.

## Existing Beamer deck

Keep native frames and attach zero, one, or both manuscript fields immediately afterward:

```tex
\begin{frame}{Why this problem is hard}
  % Existing Beamer content, including overlays
\end{frame}
\speech{The complete spoken explanation for this slide.}
```

Missing attachments become empty areas in the notes PDF. `\note` and `\speech` may appear in either order. Native overlays, `\pause`, and `allowframebreaks` are supported: every physical slide output gets its own notes page, with the logical frame's manuscript repeated where needed.

Build from the repository root:

```bash
python3 skill/scripts/build_dual_pdf.py path/to/talk.tex --output build
```

Native frames receive diagnostic IDs such as `F001`. These remain correctly bound within a build but change when earlier native frames are inserted or deleted.

## Stable-ID authoring and strict mode

For a new deck or cross-version r1/r2/r3 maintenance, prefer:

```tex
\begin{paperframe}{S03}{Why this problem is hard}
  % Normal Beamer frame content
\end{paperframe}
\note{A short private reminder.}
\speech{The complete spoken explanation.}
```

IDs must be unique and stable. Insert `S04A` between `S04` and `S05` rather than renumbering unchanged slides.

Run the stronger final-delivery checks with:

```bash
python3 skill/scripts/build_dual_pdf.py path/to/talk.tex --output build --strict
```

Strict mode requires every frame to use `paperframe`, both attachments to be explicit, and every logical frame to produce exactly one PDF page. It rejects overlays and multi-page frames.

The builder writes both PDFs, generated TeX for diagnostics, `page_map.json` with physical-to-logical page bindings, and rendered PNGs when `pdftoppm` is available. It requires Python 3.10+, `latexmk`, XeLaTeX, and the LaTeX packages used by the source.

## Notes-only setup

For commands used only in the manuscript, add one block in the source preamble:

```tex
\NotesPreamble{
  \newcommand{\solver}{branch-and-cut solver}
}
```

The block is removed from the Beamer build and injected into the notes build.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The suite tests parser behavior, strict-mode regressions, real XeLaTeX dual-PDF builds, and native overlay page mapping. GitHub Actions installs the TeX toolchain and runs the same suite.

No license has been selected yet.
