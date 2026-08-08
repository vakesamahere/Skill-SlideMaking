# Revision and QA

## Incremental revision

Resolve the named baseline, map requests to stable IDs, edit only those frames and attached blocks, preserve all other source, and compare the result with the baseline. Disclose any minimal adjacent change forced by the edit.

## Content

- Classify the paper and separate authors' work from cited prior work.
- Put prerequisites before first use and describe conceptual hierarchies correctly.
- Give a concrete example for each major abstract method claim.
- Expand abbreviations, narrate input-to-output processes, and state practical meaning and limits.
- Trace claims to evidence or label inference.
- Include a speaking-time cue per frame and verify the total.

## Slides and notes

- One takeaway and one PDF page per frame.
- Unique stable ID and exactly one note/speech pair.
- No overlays, clipping, overflow, overlap, tiny labels, broken glyphs, or missing figures.
- Natural spoken prose instead of an abstract copied from the paper.
- Notes are short private cues; speech contains the complete explanation and transition.

## Final artifacts

- Run the dual-PDF builder successfully.
- Inspect `page_map.json` and equal PDF page counts.
- Review every rendered slide and notes page, especially first, inserted, and last pages.
- Confirm a revision differs from its baseline only where requested.
