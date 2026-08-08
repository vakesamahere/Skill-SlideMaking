#!/usr/bin/env python3
"""Build synchronized Beamer slides and speaker notes from one LaTeX source."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
DOCUMENTCLASS_RE = re.compile(r"\\documentclass(?:\s*\[[^]]*\])?\s*\{beamer\}")
FORBIDDEN_OVERLAY_COMMANDS = {
    "pause",
    "only",
    "uncover",
    "visible",
    "invisible",
    "onslide",
    "alt",
    "temporal",
    "againframe",
}


class SourceError(ValueError):
    """Raised when the single-source authoring contract is invalid."""


@dataclass(frozen=True)
class Frame:
    slide_id: str
    title: str
    body: str
    options: str
    note: str
    speech: str
    kind: str
    frame_end: int
    has_note: bool
    has_speech: bool
    start: int
    end: int


@dataclass(frozen=True)
class Talk:
    source: str
    frames: tuple[Frame, ...]
    notes_preamble: str
    notes_preamble_span: tuple[int, int] | None


class Scanner:
    """Small brace-aware TeX scanner for the deliberately constrained DSL."""

    def __init__(self, text: str):
        self.text = text
        self.length = len(text)

    def _is_comment(self, pos: int) -> bool:
        if self.text[pos] != "%":
            return False
        backslashes = 0
        cursor = pos - 1
        while cursor >= 0 and self.text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        return backslashes % 2 == 0

    def skip_comment(self, pos: int) -> int:
        newline = self.text.find("\n", pos)
        return self.length if newline < 0 else newline + 1

    def skip_trivia(self, pos: int) -> int:
        while pos < self.length:
            if self.text[pos].isspace():
                pos += 1
            elif self.text[pos] == "%" and self._is_comment(pos):
                pos = self.skip_comment(pos)
            else:
                break
        return pos

    def command(self, pos: int) -> tuple[str, int] | None:
        if pos >= self.length or self.text[pos] != "\\":
            return None
        cursor = pos + 1
        if cursor >= self.length:
            return ("", cursor)
        if self.text[cursor].isalpha() or self.text[cursor] == "@":
            cursor += 1
            while cursor < self.length and (
                self.text[cursor].isalpha() or self.text[cursor] == "@"
            ):
                cursor += 1
            return (self.text[pos + 1 : cursor], cursor)
        return (self.text[cursor], cursor + 1)

    def skip_verb(self, pos: int, command_end: int) -> int:
        cursor = command_end
        if cursor < self.length and self.text[cursor] == "*":
            cursor += 1
        if cursor >= self.length or self.text[cursor].isspace():
            return cursor
        delimiter = self.text[cursor]
        closing = self.text.find(delimiter, cursor + 1)
        if closing < 0:
            raise SourceError(f"unterminated \\verb at character {pos}")
        return closing + 1

    def group(self, pos: int, opener: str = "{", closer: str = "}") -> tuple[str, int]:
        pos = self.skip_trivia(pos)
        if pos >= self.length or self.text[pos] != opener:
            raise SourceError(f"expected {opener!r} at character {pos}")
        start = pos + 1
        depth = 1
        cursor = start
        while cursor < self.length:
            char = self.text[cursor]
            if char == "%" and self._is_comment(cursor):
                cursor = self.skip_comment(cursor)
                continue
            if char == "\\":
                parsed = self.command(cursor)
                assert parsed is not None
                name, command_end = parsed
                if name == "verb":
                    cursor = self.skip_verb(cursor, command_end)
                else:
                    cursor = command_end
                continue
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return self.text[start:cursor], cursor + 1
            cursor += 1
        raise SourceError(f"unterminated {opener}{closer} group starting at {pos}")

    def optional_group(self, pos: int) -> tuple[str, int] | None:
        cursor = self.skip_trivia(pos)
        if cursor >= self.length or self.text[cursor] != "[":
            return None
        return self.group(cursor, "[", "]")

    def environment_name(self, command_end: int) -> tuple[str, int]:
        return self.group(command_end)

    def find_document_bounds(self) -> tuple[int, int]:
        begin_end: int | None = None
        cursor = 0
        while cursor < self.length:
            if self.text[cursor] == "%" and self._is_comment(cursor):
                cursor = self.skip_comment(cursor)
                continue
            parsed = self.command(cursor) if self.text[cursor] == "\\" else None
            if parsed:
                name, command_end = parsed
                if name == "verb":
                    cursor = self.skip_verb(cursor, command_end)
                    continue
                if name in {"begin", "end"}:
                    env, env_end = self.environment_name(command_end)
                    if name == "begin" and env.strip() == "document":
                        if begin_end is not None:
                            raise SourceError("multiple document environments")
                        begin_end = env_end
                    elif name == "end" and env.strip() == "document":
                        if begin_end is None:
                            raise SourceError("document ends before it begins")
                        return begin_end, cursor
                    cursor = env_end
                    continue
                cursor = command_end
                continue
            cursor += 1
        raise SourceError("missing complete \\begin{document} ... \\end{document}")


def _visible_commands(text: str) -> list[str]:
    scanner = Scanner(text)
    commands: list[str] = []
    cursor = 0
    while cursor < scanner.length:
        if text[cursor] == "%" and scanner._is_comment(cursor):
            cursor = scanner.skip_comment(cursor)
            continue
        parsed = scanner.command(cursor) if text[cursor] == "\\" else None
        if parsed:
            name, end = parsed
            if name == "verb":
                cursor = scanner.skip_verb(cursor, end)
            else:
                commands.append(name)
                cursor = end
            continue
        cursor += 1
    return commands


def _validate_no_overlays(frame: Frame) -> None:
    if "allowframebreaks" in frame.options:
        raise SourceError(f"{frame.slide_id}: allowframebreaks is not allowed")
    commands = set(_visible_commands(frame.body))
    forbidden = sorted(commands & FORBIDDEN_OVERLAY_COMMANDS)
    if forbidden:
        raise SourceError(
            f"{frame.slide_id}: overlay command(s) are not allowed: "
            + ", ".join(f"\\{item}" for item in forbidden)
        )
    # This complements command detection for forms such as \item<2->.
    if re.search(r"\\[A-Za-z@]+\s*<\s*(?:\d|[+.-])", frame.body):
        raise SourceError(f"{frame.slide_id}: Beamer overlay specification is not allowed")


def _parse_attachments(
    scanner: Scanner, pos: int, *, strict: bool
) -> tuple[str, str, bool, bool, int]:
    """Read zero, one, or both note/speech commands immediately after a frame."""
    note = ""
    speech = ""
    has_note = False
    has_speech = False
    end = pos
    while True:
        cursor = scanner.skip_trivia(end)
        parsed = scanner.command(cursor)
        if parsed is None or parsed[0] not in {"note", "speech"}:
            break
        name, command_end = parsed
        if name == "note":
            optional = scanner.optional_group(command_end)
            if optional:
                _, command_end = optional
        content, group_end = scanner.group(command_end)
        if name == "note":
            if has_note:
                raise SourceError("duplicate \\note attachment after frame")
            note = content
            has_note = True
        else:
            if has_speech:
                raise SourceError("duplicate \\speech attachment after frame")
            speech = content
            has_speech = True
        end = group_end
    if strict and not (has_note and has_speech):
        missing = []
        if not has_note:
            missing.append("\\note")
        if not has_speech:
            missing.append("\\speech")
        raise SourceError("missing required attachment(s): " + ", ".join(missing))
    return note, speech, has_note, has_speech, end


def _parse_paperframe(
    scanner: Scanner, start: int, begin_command_end: int, *, strict: bool
) -> Frame:
    env, cursor = scanner.environment_name(begin_command_end)
    if env.strip() != "paperframe":
        raise AssertionError("_parse_paperframe called for a different environment")
    optional = scanner.optional_group(cursor)
    if optional:
        options, cursor = optional
    else:
        options = ""
    slide_id, cursor = scanner.group(cursor)
    title, cursor = scanner.group(cursor)
    slide_id = slide_id.strip()
    if not ID_RE.fullmatch(slide_id):
        raise SourceError(f"invalid slide ID {slide_id!r}")

    body_start = cursor
    while cursor < scanner.length:
        if scanner.text[cursor] == "%" and scanner._is_comment(cursor):
            cursor = scanner.skip_comment(cursor)
            continue
        parsed = scanner.command(cursor) if scanner.text[cursor] == "\\" else None
        if not parsed:
            cursor += 1
            continue
        name, command_end = parsed
        if name == "verb":
            cursor = scanner.skip_verb(cursor, command_end)
            continue
        if name in {"begin", "end"}:
            nested_env, env_end = scanner.environment_name(command_end)
            nested_env = nested_env.strip()
            if name == "begin" and nested_env == "paperframe":
                raise SourceError(f"{slide_id}: paperframe environments cannot nest")
            if name == "begin" and nested_env == "frame":
                raise SourceError(
                    f"{slide_id}: raw frame environment cannot appear inside paperframe"
                )
            if name == "end" and nested_env == "paperframe":
                body = scanner.text[body_start:cursor]
                note, speech, has_note, has_speech, attachment_end = _parse_attachments(
                    scanner, env_end, strict=strict
                )
                frame = Frame(
                    slide_id=slide_id,
                    title=title,
                    body=body,
                    options=options.strip(),
                    note=note,
                    speech=speech,
                    kind="paperframe",
                    frame_end=env_end,
                    has_note=has_note,
                    has_speech=has_speech,
                    start=start,
                    end=attachment_end,
                )
                if strict:
                    _validate_no_overlays(frame)
                return frame
            cursor = env_end
            continue
        cursor = command_end
    raise SourceError(f"{slide_id}: missing \\end{{paperframe}}")


def _raw_frame_title(scanner: Scanner, pos: int, body: str) -> str:
    """Extract a conventional frame title when it is easy to do so."""
    optional = scanner.optional_group(pos)
    if optional:
        _, pos = optional
    pos = scanner.skip_trivia(pos)
    if pos < scanner.length and scanner.text[pos] == "{":
        title, _ = scanner.group(pos)
        return title
    match = re.search(r"\\frametitle\s*\{([^{}]*)\}", body)
    return match.group(1) if match else ""


def _parse_raw_frame(
    scanner: Scanner,
    start: int,
    begin_command_end: int,
    *,
    ordinal: int,
    strict: bool,
) -> Frame:
    if strict:
        raise SourceError("raw frame environment found; use paperframe with a stable ID")
    env, cursor = scanner.environment_name(begin_command_end)
    if env.strip() != "frame":
        raise AssertionError("_parse_raw_frame called for a different environment")
    body_start = cursor
    while cursor < scanner.length:
        if scanner.text[cursor] == "%" and scanner._is_comment(cursor):
            cursor = scanner.skip_comment(cursor)
            continue
        parsed = scanner.command(cursor) if scanner.text[cursor] == "\\" else None
        if not parsed:
            cursor += 1
            continue
        name, command_end = parsed
        if name == "verb":
            cursor = scanner.skip_verb(cursor, command_end)
            continue
        if name in {"begin", "end"}:
            nested_env, env_end = scanner.environment_name(command_end)
            nested_env = nested_env.strip()
            if name == "begin" and nested_env in {"frame", "paperframe"}:
                raise SourceError("frame environments cannot nest")
            if name == "end" and nested_env == "frame":
                body = scanner.text[body_start:cursor]
                note, speech, has_note, has_speech, attachment_end = _parse_attachments(
                    scanner, env_end, strict=False
                )
                return Frame(
                    slide_id=f"F{ordinal:03d}",
                    title=_raw_frame_title(scanner, body_start, body),
                    body=body,
                    options="",
                    note=note,
                    speech=speech,
                    kind="frame",
                    frame_end=env_end,
                    has_note=has_note,
                    has_speech=has_speech,
                    start=start,
                    end=attachment_end,
                )
            cursor = env_end
            continue
        cursor = command_end
    raise SourceError(f"F{ordinal:03d}: missing \\end{{frame}}")


def _find_notes_preamble(scanner: Scanner, preamble_end: int) -> tuple[str, tuple[int, int] | None]:
    found: tuple[str, tuple[int, int]] | None = None
    cursor = 0
    while cursor < preamble_end:
        if scanner.text[cursor] == "%" and scanner._is_comment(cursor):
            cursor = scanner.skip_comment(cursor)
            continue
        parsed = scanner.command(cursor) if scanner.text[cursor] == "\\" else None
        if parsed:
            name, end = parsed
            if name == "NotesPreamble":
                if found is not None:
                    raise SourceError("use at most one \\NotesPreamble{...} block")
                content, group_end = scanner.group(end)
                found = (content, (cursor, group_end))
                cursor = group_end
                continue
            cursor = scanner.skip_verb(cursor, end) if name == "verb" else end
            continue
        cursor += 1
    return found if found is not None else ("", None)


def parse_talk(source: str, *, strict: bool = False) -> Talk:
    if not DOCUMENTCLASS_RE.search(source):
        raise SourceError("source must use \\documentclass{beamer}")
    scanner = Scanner(source)
    body_start, body_end = scanner.find_document_bounds()
    notes_preamble, notes_preamble_span = _find_notes_preamble(scanner, body_start)
    frames: list[Frame] = []
    cursor = body_start
    while cursor < body_end:
        if source[cursor] == "%" and scanner._is_comment(cursor):
            cursor = scanner.skip_comment(cursor)
            continue
        parsed = scanner.command(cursor) if source[cursor] == "\\" else None
        if not parsed:
            cursor += 1
            continue
        name, command_end = parsed
        if name == "verb":
            cursor = scanner.skip_verb(cursor, command_end)
            continue
        if name == "begin":
            env, env_end = scanner.environment_name(command_end)
            env = env.strip()
            if env == "paperframe":
                frame = _parse_paperframe(
                    scanner, cursor, command_end, strict=strict
                )
                frames.append(frame)
                cursor = frame.end
                continue
            if env == "frame":
                frame = _parse_raw_frame(
                    scanner,
                    cursor,
                    command_end,
                    ordinal=len(frames) + 1,
                    strict=strict,
                )
                frames.append(frame)
                cursor = frame.end
                continue
            cursor = env_end
            continue
        if name in {"note", "speech"}:
            raise SourceError(f"orphan \\{name} outside a paperframe attachment")
        cursor = command_end

    if not frames:
        raise SourceError("no frame or paperframe environments found")
    seen: set[str] = set()
    for frame in frames:
        if frame.slide_id in seen:
            raise SourceError(f"duplicate slide ID: {frame.slide_id}")
        seen.add(frame.slide_id)
    return Talk(source, tuple(frames), notes_preamble, notes_preamble_span)


def render_slides_tex(talk: Talk) -> str:
    replacements: list[tuple[int, int, str]] = []
    if talk.notes_preamble_span:
        replacements.append((*talk.notes_preamble_span, ""))
    for frame in talk.frames:
        if frame.kind == "frame":
            rendered = talk.source[frame.start : frame.frame_end]
        else:
            option = f"[{frame.options}]" if frame.options else ""
            title = f"{{{frame.title}}}" if frame.title.strip() else ""
            rendered = (
                f"% SLIDE-ID: {frame.slide_id}\n"
                f"\\begin{{frame}}{option}{title}{frame.body}\\end{{frame}}"
            )
        replacements.append((frame.start, frame.end, rendered))
    result = talk.source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def _notes_font_setup() -> str:
    return r"""
\IfFontExistsTF{Noto Sans CJK SC}{
  \setmainfont{Noto Sans CJK SC}
  \setsansfont{Noto Sans CJK SC}
}{
  \setmainfont{Latin Modern Roman}
  \setsansfont{Latin Modern Sans}
}
"""


def render_notes_tex(
    talk: Talk,
    slides_pdf: Path,
    page_bindings: list[tuple[int, Frame, int, int]] | None = None,
) -> str:
    pages: list[str] = []
    pdf_path = str(slides_pdf.resolve()).replace("\\", "/")
    if page_bindings is None:
        page_bindings = [
            (page, frame, 1, 1) for page, frame in enumerate(talk.frames, 1)
        ]
    for page, frame, logical_page, logical_pages in page_bindings:
        page_suffix = (
            f" (output {logical_page}/{logical_pages})" if logical_pages > 1 else ""
        )
        pages.append(
            rf"""
\thispagestyle{{empty}}
\noindent{{\sffamily\bfseries\large {frame.slide_id}{page_suffix} — {frame.title}}}\par
\vspace{{0.6em}}
\noindent
\begin{{minipage}}[t][0.90\textheight][t]{{0.35\textwidth}}
  \vspace{{0pt}}
  \includegraphics[page={page},width=\linewidth]{{\detokenize{{{pdf_path}}}}}
  \vspace{{0.8em}}

  {{\sffamily\bfseries Note}}\par
  \vspace{{0.25em}}
  {{\small {frame.note}}}
\end{{minipage}}\hfill
\begin{{minipage}}[t][0.90\textheight][t]{{0.61\textwidth}}
  \vspace{{0pt}}
  {{\sffamily\bfseries Speech}}\par
  \vspace{{0.35em}}
  {frame.speech}
\end{{minipage}}
\clearpage
"""
        )
    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=12mm]{{geometry}}
\usepackage{{iftex}}
\ifXeTeX\else
  \PackageError{{speaker-notes}}{{Compile with XeLaTeX}}{{Use the supplied builder}}
\fi
\usepackage{{fontspec}}
{_notes_font_setup()}
\usepackage{{amsmath,amssymb,booktabs,graphicx,tikz,xcolor}}
\usepackage{{microtype}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.55em}}
\raggedbottom
{talk.notes_preamble}
\begin{{document}}
{''.join(pages)}
\end{{document}}
"""


def pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except ImportError:
        if not shutil.which("pdfinfo"):
            raise RuntimeError("need pypdf or pdfinfo to verify PDF page counts")
        result = subprocess.run(
            ["pdfinfo", str(path)], check=True, capture_output=True, text=True
        )
        match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
        if not match:
            raise RuntimeError(f"could not read page count from {path}")
        return int(match.group(1))


def _compile(tex_path: Path, output_dir: Path, jobname: str, cwd: Path) -> Path:
    if not shutil.which("latexmk") or not shutil.which("xelatex"):
        raise RuntimeError("latexmk and xelatex are required")
    command = [
        "latexmk",
        "-xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-outdir={output_dir.resolve()}",
        f"-jobname={jobname}",
        str(tex_path.resolve()),
    ]
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
        raise RuntimeError(f"{jobname} compilation failed:\n{tail}")
    log_path = output_dir / f"{jobname}.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    if "Missing character:" in log:
        lines = [line for line in log.splitlines() if "Missing character:" in line][:8]
        raise RuntimeError(
            f"{jobname} has missing glyphs; install/configure an appropriate font:\n"
            + "\n".join(lines)
        )
    pdf = output_dir / f"{jobname}.pdf"
    if not pdf.is_file():
        raise RuntimeError(f"compiler did not create {pdf}")
    return pdf


def _render_pdf(pdf: Path, destination: Path) -> None:
    if not shutil.which("pdftoppm"):
        return
    destination.mkdir(parents=True, exist_ok=True)
    prefix = destination / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", "120", str(pdf), str(prefix)], check=True
    )


def _page_bindings(
    talk: Talk, output_dir: Path, slide_pages: int, *, strict: bool
) -> list[tuple[int, Frame, int, int]]:
    """Map each physical Beamer output page back to its logical source frame."""
    nav_path = output_dir / "slides.nav"
    spans: list[tuple[int, int]] = []
    if nav_path.is_file():
        nav = nav_path.read_text(encoding="utf-8", errors="replace")
        spans = [
            (int(start), int(end))
            for start, end in re.findall(
                r"\\beamer@framepages\s*\{(\d+)\}\{(\d+)\}", nav
            )
        ]
    if len(spans) != len(talk.frames):
        if slide_pages == len(talk.frames):
            spans = [(page, page) for page in range(1, slide_pages + 1)]
        else:
            raise RuntimeError(
                "could not map Beamer output pages to source frames; "
                f"found {len(spans)} frame spans for {len(talk.frames)} frames"
            )
    bindings: list[tuple[int, Frame, int, int]] = []
    for frame, (start, end) in zip(talk.frames, spans):
        if end < start:
            raise RuntimeError(f"invalid Beamer page span for {frame.slide_id}: {start}-{end}")
        count = end - start + 1
        if strict and count != 1:
            raise RuntimeError(
                f"{frame.slide_id} produced {count} PDF pages in strict mode"
            )
        for logical_page, page in enumerate(range(start, end + 1), 1):
            bindings.append((page, frame, logical_page, count))
    physical_pages = [item[0] for item in bindings]
    if physical_pages != list(range(1, slide_pages + 1)):
        raise RuntimeError(
            "Beamer frame-page map does not cover slides.pdf exactly: "
            f"{physical_pages!r} vs 1..{slide_pages}"
        )
    return bindings


def build(
    source_path: Path,
    output_dir: Path,
    render: bool = True,
    *,
    strict: bool = False,
) -> dict[str, object]:
    source_path = source_path.resolve()
    output_dir = output_dir.resolve()
    source = source_path.read_text(encoding="utf-8")
    talk = parse_talk(source, strict=strict)
    output_dir.mkdir(parents=True, exist_ok=True)

    slides_tex = output_dir / "slides.generated.tex"
    slides_tex.write_text(render_slides_tex(talk), encoding="utf-8")
    slides_pdf = _compile(slides_tex, output_dir, "slides", source_path.parent)
    slide_pages = pdf_page_count(slides_pdf)
    page_bindings = _page_bindings(talk, output_dir, slide_pages, strict=strict)

    notes_tex = output_dir / "speaker_notes.generated.tex"
    notes_tex.write_text(
        render_notes_tex(talk, slides_pdf, page_bindings), encoding="utf-8"
    )
    notes_pdf = _compile(notes_tex, output_dir, "speaker_notes", source_path.parent)
    note_pages = pdf_page_count(notes_pdf)
    if note_pages != slide_pages:
        raise RuntimeError(
            f"speaker_notes.pdf has {note_pages} pages but slides.pdf has {slide_pages}; "
            "shorten overflowing note/speech content"
        )

    manifest = {
        "source": str(source_path),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "slides_pdf": str(slides_pdf),
        "speaker_notes_pdf": str(notes_pdf),
        "pages": [
            {
                "page": page,
                "id": frame.slide_id,
                "title": frame.title.strip(),
                "frame_output_page": logical_page,
                "frame_output_pages": logical_pages,
                "has_note": frame.has_note,
                "has_speech": frame.has_speech,
            }
            for page, frame, logical_page, logical_pages in page_bindings
        ],
    }
    (output_dir / "page_map.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if render:
        _render_pdf(slides_pdf, output_dir / "review" / "slides")
        _render_pdf(notes_pdf, output_dir / "review" / "speaker_notes")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="single-source Beamer .tex file")
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="require paperframe IDs, explicit note/speech, and one PDF page per frame",
    )
    args = parser.parse_args(argv)
    try:
        talk = parse_talk(args.source.read_text(encoding="utf-8"), strict=args.strict)
        if args.validate_only:
            print(f"OK: {len(talk.frames)} synchronized frames")
            return 0
        manifest = build(
            args.source, args.output, render=not args.no_render, strict=args.strict
        )
        print(
            f"OK: built {len(manifest['pages'])} synchronized pages\n"
            f"  {manifest['slides_pdf']}\n  {manifest['speaker_notes_pdf']}"
        )
        return 0
    except (OSError, SourceError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
