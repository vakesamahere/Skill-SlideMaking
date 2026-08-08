# Single-source contract

## Authoring grammar

Each logical page is one `paperframe` followed by one `note` and one `speech`:

```tex
\begin{paperframe}[optional frame options]{stable-ID}{frame title}
  Beamer body
\end{paperframe}
\note{private reminder}
\speech{full spoken manuscript}
```

Whitespace and comments may appear between the three constructs. The order is fixed. The builder supports nested braces, escaped braces, `\verb`, paragraphs, equations, and Unicode text within the brace-delimited fields.

IDs match `[A-Za-z][A-Za-z0-9_.-]*`. Treat them as identity, not page numbers. Insert `S04A` between `S04` and `S05`; only create a full renumbering when explicitly requested.

## Why binding cannot drift

The builder creates one ordered `Frame` object per `paperframe`. That object contains the ID, title, body, note, and speech. It first emits and compiles Beamer frames in object order. After verifying that the slides PDF has exactly one page per object, it emits notes page `n` with page `n` of that exact slides PDF and the note/speech from object `n`.

The build fails before delivery for:

- duplicate or invalid IDs;
- raw Beamer `frame` environments;
- missing, reordered, or orphaned note/speech commands;
- overlay commands/specifications or `allowframebreaks`;
- slide PDF page count different from object count;
- notes PDF page count different from slide count;
- missing-glyph warnings.

## Notes-only setup

Use at most one preamble block:

```tex
\NotesPreamble{
  \newcommand{\solver}{branch-and-cut solver}
}
```

The builder removes this block from generated Beamer source and inserts its content into generated article source. Use it for macros referenced only by `note` or `speech`. Common math, graphics, TikZ, table, color, and font packages are already loaded in the notes document.

## Diagnostics

The author maintains only the input `.tex`. Generated `slides.generated.tex` and `speaker_notes.generated.tex` are retained for compiler diagnostics. `page_map.json` records source hash and page-to-ID/title bindings. Rendered PNGs under `review/` are the visual QA surface.
