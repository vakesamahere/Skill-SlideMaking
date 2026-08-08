from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "skill" / "scripts" / "build_dual_pdf.py"
if not MODULE_PATH.is_file():
    MODULE_PATH = Path("/root/.codex/skills/remote-skills/skill-6a75ff3f5a788191a4294003f0f84725/scripts/build_dual_pdf.py")
SPEC = importlib.util.spec_from_file_location("build_dual_pdf", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def talk_source(frames: str, preamble: str = "") -> str:
    return rf"""\documentclass[aspectratio=169]{{beamer}}
\usepackage{{fontspec}}
\setmainfont{{Latin Modern Sans}}
\setsansfont{{Latin Modern Sans}}
\setbeamertemplate{{navigation symbols}}{{}}
{preamble}
\begin{{document}}
{frames}
\end{{document}}
"""


def frame(slide_id: str, title: str, body: str, note: str, speech: str) -> str:
    return rf"""\begin{{paperframe}}{{{slide_id}}}{{{title}}}
{body}
\end{{paperframe}}
\note{{{note}}}
\speech{{{speech}}}
"""


class ParserTests(unittest.TestCase):
    def test_nested_braces_paragraphs_and_chinese(self) -> None:
        source = talk_source(frame("S01", r"前置知识：$f_{\theta}(x)$", r"\textbf{候选项：} $\{x_i\}$", "提醒：{集合}", r"保留 \verb|{nested}|。"))
        talk = builder.parse_talk(source, strict=True)
        self.assertEqual(talk.frames[0].slide_id, "S01")
        self.assertIn("集合", talk.frames[0].note)
        self.assertIn(r"\verb|{nested}|", talk.frames[0].speech)

    def test_duplicate_explicit_id_fails(self) -> None:
        source = talk_source(frame("S01", "One", "A", "N", "P") + frame("S01", "Two", "B", "N", "P"))
        with self.assertRaisesRegex(builder.SourceError, "duplicate slide ID"):
            builder.parse_talk(source)

    def test_native_frames_allow_incremental_attachments(self) -> None:
        source = talk_source(r"""\begin{frame}{Empty}A\end{frame}
\begin{frame}{Note only}B\end{frame}\note[item]{N}
\begin{frame}{Speech only}C\end{frame}\speech{P}
\frame{\frametitle{Command shorthand}D}\note{NC}
\begin{paperframe}{S04A}{Both}E\end{paperframe}\speech{P2}\note{N2}""")
        talk = builder.parse_talk(source)
        self.assertEqual([f.slide_id for f in talk.frames], ["F001", "F002", "F003", "F004", "S04A"])
        self.assertEqual([(f.has_note, f.has_speech) for f in talk.frames], [(False, False), (True, False), (False, True), (True, False), (True, True)])
        self.assertEqual(talk.frames[1].note, "N")
        self.assertEqual(talk.frames[3].title, "Command shorthand")
        slides = builder.render_slides_tex(talk)
        self.assertIn(r"\begin{frame}{Empty}A\end{frame}", slides)
        self.assertNotIn(r"\speech{P}", slides)

    def test_duplicate_and_orphan_attachments_fail(self) -> None:
        duplicate = talk_source(r"\begin{frame}{One}A\end{frame}\note{N1}\note{N2}")
        with self.assertRaisesRegex(builder.SourceError, r"duplicate \\note"):
            builder.parse_talk(duplicate)
        orphan = talk_source(frame("S01", "One", "A", "N", "P") + r"Top-level text.\speech{extra}")
        with self.assertRaisesRegex(builder.SourceError, r"orphan \\speech"):
            builder.parse_talk(orphan)

    def test_strict_mode_preserves_original_contract(self) -> None:
        raw = talk_source(r"\begin{frame}{Raw}A\end{frame}")
        with self.assertRaisesRegex(builder.SourceError, "raw frame"):
            builder.parse_talk(raw, strict=True)
        missing = talk_source(r"\begin{paperframe}{S01}{One}A\end{paperframe}\note{N}")
        with self.assertRaisesRegex(builder.SourceError, "missing required"):
            builder.parse_talk(missing, strict=True)
        overlay = talk_source(frame("S01", "One", r"A\pause B", "N", "P"))
        with self.assertRaisesRegex(builder.SourceError, "overlay"):
            builder.parse_talk(overlay, strict=True)

    def test_notes_preamble_is_moved_not_compiled_in_slides(self) -> None:
        source = talk_source(frame("S01", "One", "A", "N", r"Use \solver."), preamble=r"\NotesPreamble{\newcommand{\solver}{solver}}")
        talk = builder.parse_talk(source)
        self.assertNotIn(r"\NotesPreamble", builder.render_slides_tex(talk))
        self.assertIn(r"\newcommand{\solver}{solver}", builder.render_notes_tex(talk, Path("slides.pdf")))

    def test_middle_insertion_updates_page_binding(self) -> None:
        inserted = builder.parse_talk(talk_source(frame("S04", "Four", "A", "N4", "P4") + frame("S04A", "Inserted", "X", "NX", "PX") + frame("S05", "Five", "B", "N5", "P5")))
        notes = builder.render_notes_tex(inserted, Path("slides.pdf"))
        s05 = notes.index("S05 — Five")
        page = notes[s05 : notes.index(r"\clearpage", s05)]
        self.assertIn(r"\includegraphics[page=3", page)


@unittest.skipUnless(shutil.which("latexmk") and shutil.which("xelatex") and shutil.which("pdfinfo"), "TeX toolchain is not installed")
class CompileIntegrationTests(unittest.TestCase):
    def test_strict_dual_pdf_build(self) -> None:
        frames = frame("S01", "Opening", "First", "Cue one.", "Speech one.") + frame("S02A", "Inserted", "Middle", "Cue middle.", "Speech middle.") + frame("S03", "End", "Last", "Cue last.", "Speech last.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "talk.tex"
            output = root / "build"
            source.write_text(talk_source(frames), encoding="utf-8")
            manifest = builder.build(source, output, render=False, strict=True)
            self.assertEqual(builder.pdf_page_count(output / "slides.pdf"), 3)
            self.assertEqual(builder.pdf_page_count(output / "speaker_notes.pdf"), 3)
            self.assertEqual([p["id"] for p in manifest["pages"]], ["S01", "S02A", "S03"])

    def test_native_overlay_maps_every_physical_page(self) -> None:
        frames = r"""\begin{frame}{Plain}A\end{frame}
\begin{frame}{Overlay}\begin{itemize}\item<1-> One\item<2-> Two\end{itemize}\end{frame}
\speech{Repeated speech.}"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "talk.tex"
            output = root / "build"
            source.write_text(talk_source(frames), encoding="utf-8")
            manifest = builder.build(source, output, render=False)
            self.assertEqual(builder.pdf_page_count(output / "slides.pdf"), 3)
            self.assertEqual(builder.pdf_page_count(output / "speaker_notes.pdf"), 3)
            self.assertEqual([p["id"] for p in manifest["pages"]], ["F001", "F002", "F002"])
            self.assertEqual([p["frame_output_page"] for p in manifest["pages"]], [1, 1, 2])
            saved = json.loads((output / "page_map.json").read_text())
            self.assertTrue(saved["pages"][1]["has_speech"])
            if shutil.which("pdftotext"):
                text = subprocess.run(["pdftotext", str(output / "speaker_notes.pdf"), "-"], check=True, capture_output=True, text=True).stdout
                self.assertGreaterEqual(text.count("Repeated speech"), 2)


if __name__ == "__main__":
    unittest.main()
