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
        source = talk_source(
            frame(
                "S01",
                r"前置知识：$f_{\theta}(x)$",
                r"\begin{block}{输入集合}\textbf{候选项：} $\{x_i\}_{i=1}^{n}$\end{block}",
                "提醒：先解释{候选集合}。",
                "第一段说明输入。\n\n第二段说明输出，并保留 \\verb|{nested}| 示例。",
            )
        )
        talk = builder.parse_talk(source)
        self.assertEqual(talk.frames[0].slide_id, "S01")
        self.assertIn("候选集合", talk.frames[0].note)
        self.assertIn(r"\verb|{nested}|", talk.frames[0].speech)
        self.assertIn(r"f_{\theta}", talk.frames[0].title)

    def test_duplicate_id_fails(self) -> None:
        source = talk_source(
            frame("S01", "One", "A", "N", "P")
            + frame("S01", "Two", "B", "N", "P")
        )
        with self.assertRaisesRegex(builder.SourceError, "duplicate slide ID"):
            builder.parse_talk(source)

    def test_missing_or_extra_attachments_fail(self) -> None:
        missing = talk_source(
            r"\begin{paperframe}{S01}{One}A\end{paperframe}\note{N}"
        )
        with self.assertRaisesRegex(builder.SourceError, r"expected \\speech"):
            builder.parse_talk(missing)
        orphan = talk_source(frame("S01", "One", "A", "N", "P") + r"\note{extra}")
        with self.assertRaisesRegex(builder.SourceError, r"orphan \\note"):
            builder.parse_talk(orphan)

    def test_overlay_and_raw_frame_fail(self) -> None:
        overlay = talk_source(frame("S01", "One", r"A\pause B", "N", "P"))
        with self.assertRaisesRegex(builder.SourceError, "overlay"):
            builder.parse_talk(overlay)
        raw = talk_source(r"\begin{frame}{Oops}A\end{frame}")
        with self.assertRaisesRegex(builder.SourceError, "raw frame"):
            builder.parse_talk(raw)

    def test_notes_preamble_is_moved_not_compiled_in_slides(self) -> None:
        source = talk_source(
            frame("S01", "One", "A", "N", r"Use \solver."),
            preamble=r"\NotesPreamble{\newcommand{\solver}{solver}}",
        )
        talk = builder.parse_talk(source)
        slides = builder.render_slides_tex(talk)
        notes = builder.render_notes_tex(talk, Path("slides.pdf"))
        self.assertNotIn(r"\NotesPreamble", slides)
        self.assertIn(r"\newcommand{\solver}{solver}", notes)

    def test_middle_insertion_updates_page_binding(self) -> None:
        base = builder.parse_talk(
            talk_source(
                frame("S04", "Four", "A", "N4", "P4")
                + frame("S05", "Five", "B", "N5", "P5")
            )
        )
        inserted = builder.parse_talk(
            talk_source(
                frame("S04", "Four", "A", "N4", "P4")
                + frame("S04A", "Inserted", "X", "NX", "PX")
                + frame("S05", "Five", "B", "N5", "P5")
            )
        )
        base_notes = builder.render_notes_tex(base, Path("slides.pdf"))
        inserted_notes = builder.render_notes_tex(inserted, Path("slides.pdf"))
        self.assertIn(r"\includegraphics[page=2", base_notes)
        self.assertIn("S05 — Five", base_notes)
        inserted_s05 = inserted_notes.index("S05 — Five")
        s05_page = inserted_notes[inserted_s05 : inserted_notes.index(r"\clearpage", inserted_s05)]
        self.assertIn(r"\includegraphics[page=3", s05_page)
        self.assertIn("S04A — Inserted", inserted_notes)


@unittest.skipUnless(
    shutil.which("latexmk") and shutil.which("xelatex") and shutil.which("pdfinfo"),
    "TeX toolchain is not installed",
)
class CompileIntegrationTests(unittest.TestCase):
    def test_real_dual_pdf_build_and_text_binding(self) -> None:
        frames = (
            frame("S01", "Opening", r"\centering First slide", "Cue one.", "Speech one.")
            + frame("S02A", "Inserted result", r"\centering Middle slide", "Cue middle.", "Speech middle.")
            + frame("S03", "Conclusion", r"\centering Last slide", "Cue last.", "Speech last.")
        )
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            source = project / "talk.tex"
            output = project / "build"
            source.write_text(talk_source(frames), encoding="utf-8")
            manifest = builder.build(source, output, render=False)
            self.assertEqual(builder.pdf_page_count(output / "slides.pdf"), 3)
            self.assertEqual(builder.pdf_page_count(output / "speaker_notes.pdf"), 3)
            self.assertEqual([p["id"] for p in manifest["pages"]], ["S01", "S02A", "S03"])
            saved = json.loads((output / "page_map.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["pages"][1]["title"], "Inserted result")
            if shutil.which("pdftotext"):
                text = subprocess.run(
                    ["pdftotext", str(output / "speaker_notes.pdf"), "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                for value in ("S01", "Opening", "Cue one", "Speech one", "S02A", "Speech middle", "S03"):
                    self.assertIn(value, text)


if __name__ == "__main__":
    unittest.main()
