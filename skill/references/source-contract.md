# Single-source compatibility contract

## Compatibility mode (default)

Accept an unchanged native Beamer frame:

```tex
\begin{frame}[optional frame options]{frame title}
  Beamer body, including overlays or allowframebreaks
\end{frame}
```

Allow zero, one, or both manuscript attachments immediately after it:

```tex
\note{private reminder}
\speech{full spoken manuscript}
```

Allow the two commands in either order. Treat a missing attachment as empty. Support Beamer's optional `\note[item]{...}` argument. Strip attached manuscript commands from the generated slides source, so the original deck does not need to define `\speech`.

Assign native frames order-based IDs (`F001`, `F002`, ...). These IDs are diagnostic rather than stable across insertions. Preserve binding within the current build by reading Beamer's `.nav` frame-page spans after compilation. When overlays or `allowframebreaks` produce multiple physical pages, create one notes page for each physical slide page and repeat the logical frame's note/speech.

Allow native `frame` and `paperframe` environments in the same source.

## Stable-ID authoring

Prefer `paperframe` for new decks and incremental r1/r2/r3 revisions:

```tex
\begin{paperframe}[optional frame options]{stable-ID}{frame title}
  Beamer body
\end{paperframe}
\note{private reminder}
\speech{full spoken manuscript}
```

Whitespace and comments may appear between the frame and attachments. The builder supports nested braces, escaped braces, `\verb`, paragraphs, equations, and Unicode text within brace-delimited fields.

IDs match `[A-Za-z][A-Za-z0-9_.-]*`. Treat them as identity, not page numbers. Insert `S04A` between `S04` and `S05`; only create a full renumbering when explicitly requested.

## Strict mode

Run the builder with `--strict` to require the original final-delivery invariants:

- every logical frame is a `paperframe` with a valid, unique stable ID;
- both `\note` and `\speech` are written explicitly, though either may contain `{}`;
- overlays, overlay specifications, `\pause`, and `allowframebreaks` are rejected;
- every logical frame produces exactly one slide PDF page.

Both modes fail for malformed frame syntax, duplicate explicit IDs, orphaned or duplicate attachments, an incomplete physical page map, unequal output PDF page counts, or missing-glyph warnings.

## Why binding cannot drift

The builder creates one ordered `Frame` object containing body, ID, title, note, and speech. It compiles the slides, reads the physical page span emitted by Beamer for every frame, then emits each notes page from the exact physical slide page and its owning `Frame` object. This supports both a one-page strict frame and a compatibility frame that expands to several output pages.

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
