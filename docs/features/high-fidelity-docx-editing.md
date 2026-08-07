# High-Fidelity DOCX Editing

## Status

**Core editing engine implemented and tested (`app.document_editing`). Not yet
wired into the HTTP API, upload flow, or export pipeline.** See "Integration
status" below for exactly what that means and why it's a deliberate,
separate stage rather than a partial job.

## Problem

`docs/features/interactive-tailored-resume.md` documents, honestly, that
DOCX export today always regenerates a brand-new document
(`app.export.renderers.DocxResumeRenderer`, labeled
`FormatFidelity.REGENERATED_TEMPLATE`) — the original file's fonts,
colors, spacing, bullets, tables, headers, footers, and layout are never
preserved, because **no original file bytes are retained anywhere past
upload**. The frontend extracts text client-side and discards the file;
the backend only ever sees a plain string.

That fact is the actual prerequisite for this feature, and it isn't
solved by this stage of work. What *is* solved: given original DOCX
bytes (from wherever they eventually come from) and a set of
user-approved edits, produce a new DOCX that is the original document
with **only those specific paragraphs changed** — not rebuilt from
scratch.

## Architecture

```
DOCX bytes ──▶ DocxStructureMapper ──▶ StructuredResume (same shape, same id scheme
                      │                 as ResumeStructureParser produces)
                      │                        │
                      ▼                        ▼
        dict[item_id, DocxParagraphNode]   (existing pipeline: Planner → Rewrite →
        (live handles into the open            Validate → Apply — entirely unchanged)
         python-docx Document)                        │
                      │                                ▼
                      └──────────▶ DocxDocumentEditor.apply(original_bytes, suggestions)
                                              │
                                              ▼
                                     edited DOCX bytes
```

### `app/document_editing/node.py` — `EditableNode`

A format-agnostic protocol: `get_text`, `set_text`, `append_text`,
`insert_before`, `insert_after`, `remove`. This is the extensibility
point the "PDF fidelity should reuse this abstraction" requirement asks
for — a future PDF editing engine implements this same protocol (over
whatever a PDF content stream gives it, most likely individual text-show
operators) without anything in this module, or anything written against
it, needing to change. The operation vocabulary mirrors
`app.models.tailoring_suggestions.SuggestionOperation` exactly, since
this is the execution side of that same vocabulary, not a parallel one.

### `app/document_editing/docx_nodes.py` — `DocxParagraphNode`

The DOCX implementation, wrapping one live `python-docx` `Paragraph`.
This is the only module in the codebase that touches OOXML directly
(`paragraph._p`) — a private-by-convention but standard, widely-used
`python-docx` escape hatch, confined to this one module so the rest of
the codebase never needs to know DOCX/OOXML exists. Every mutation
happens on the paragraph's own live element in the already-open
`Document` — nothing is copied into a new document.

### `app/document_editing/docx_structure_mapper.py` — `DocxStructureMapper`

The DOCX-specific twin of `app.resume_structure.parser.
ResumeStructureParser`, reusing that module's heading/bullet heuristics
(`looks_like_heading`, `BULLET_PREFIXES` — promoted from module-private
to shared, exported names for exactly this reuse) rather than
maintaining two copies that could drift. It does **not** reuse the
text-splitting logic, because a real DOCX paragraph is already exactly
one logical unit — Word wraps text visually, it never splits one bullet
across two `<w:p>` elements — so there's no "join consecutive lines" step
to replicate. This makes DOCX-direct structuring *more* accurate than
text-based structuring: paragraph boundaries come from the document
itself, not from re-inferring them out of a flattened string.

Produces a `StructuredResume` and a `dict[item_id, DocxParagraphNode]`
from **one single walk**, so the two can never disagree about what "item
5" is — a real risk if structure were derived one way for planning and
mapped a different way for editing.

Scope: only top-level body paragraphs (matching
`app.ingestion.extractor.DocxDocumentExtractor`'s existing, documented
scope limit) — table cells, headers, and footers are not mapped, which is
exactly why they're never edited. They're preserved because nothing ever
touches them, not because they're specially protected.

### `app/document_editing/docx_document_editor.py` — `DocxDocumentEditor`

The engine. `apply(original_docx_bytes, suggestions)` opens the original
file, re-derives the node map fresh (never caches one across calls),
mutates exactly the paragraphs named by the suggestions'
`target_item_id`s, and re-saves the same `Document` object. It takes
`list[TailoringSuggestion]` — not a looser edit descriptor — because it's
designed to consume `SuggestionApplier`'s own already-resolved output
directly (selection, revalidation, and conflict-checking already
happened there); this module doesn't re-implement any of that, it only
mirrors `SuggestionApplier`'s exact conflict-category policy defensively,
for callers that use it independently.

## Per-operation fidelity (the actual trade-offs)

| Operation | Technique | Fidelity |
|---|---|---|
| `append` | Add a **new run**, cloned from the last existing run's `<w:rPr>` (font/size/color/bold/...); existing runs are never touched | **Exact** — zero formatting loss on the original text; the addition matches the sentence's trailing style |
| `insert_before` / `insert_after` | Deep-copy the anchor paragraph's whole `<w:p>` element (style, numbering/bullet, indentation all come along automatically), insert as an XML sibling, then apply `set_text` to it | **Exact style match** to its neighbor, since the new paragraph *is* a structural clone |
| `remove` | Delete the paragraph's `<w:p>` element outright | **Exact** — no reflow artifacts; list numbering renumbers the same way Word itself would |
| `update` / `replace` / `add_emphasis` | Keep the **first run's** formatting, set its text to the full new text, delete the remaining runs | **Honest limitation**: a paragraph with genuinely mixed inline formatting (e.g. a bolded company name mid-sentence, plain text around it) collapses to one uniform style for the new text. Whole-paragraph formatting — font, size, color, alignment, list level, indentation — is fully preserved either way, since none of that lives in run-level properties. |

This table is the answer to "is the output visually identical except for
the approved edits": **yes, unconditionally, for `append`/`insert`/
`remove`; yes for `update`/`replace`/`add_emphasis` on a single-run
paragraph (the common case — one bullet, one style); not quite for a
`update`-type edit to a paragraph with deliberately mixed inline
formatting**, which is called out here rather than glossed over.

`compute_append_delta` (in `docx_document_editor.py`) recovers just the
newly-added portion of an `append` suggestion's `suggested_text` (which
is always the item's *full* resulting text, per this pipeline's existing
contract) — and deliberately preserves whatever separator punctuation the
model produced (e.g. the `, ` in `"Python"` → `"Python, TypeScript"`),
unlike the frontend's display-only equivalent
(`suggestionPresentation.ts`'s `computeAppendedDelta`), which trims
leading punctuation because it's presenting the delta on its own, never
concatenating it back onto real document text.

## Why not rebuild the document?

`DocxResumeRenderer` (the existing export path) always creates a fresh
`Document()` and adds every heading/paragraph back from `StructuredResume`
data — by definition, this loses everything not represented in that
data: exact fonts, colors, custom styles, tables, headers, footers, page
breaks, hyperlinks. `DocxDocumentEditor` never does this. It opens the
original `python-docx.Document`, mutates specific existing paragraph
objects in place, and saves the *same* object — so anything it doesn't
touch (which is almost the whole document, for a handful of approved
edits) round-trips through `python-docx`'s own OOXML serialization
unchanged.

## Extensibility for PDF

The `EditableNode` protocol is the seam. A future PDF fidelity engine
would need its own structure mapper (PDF has no equivalent of "a
paragraph" as a first-class editable object — this would likely mean
locating and replacing specific text-show operators within a content
stream, a meaningfully harder problem given PDF's layout model) and its
own node implementation, but `DocxDocumentEditor`'s *shape* — resolve
`target_item_id` to a node, dispatch on operation, mutate in place —
generalizes directly. Nothing in `node.py` is DOCX-specific.

## Integration status (what's deliberately not done yet)

This stage delivers a fully tested, standalone Python module. It is
**not** reachable from any HTTP endpoint, and the following remain
explicitly open, coordinated frontend+backend work:

1. **Original DOCX bytes don't reach the backend at all today.** The
   upload flow (`ResumeInput` → client-side extraction → `resume: str`
   sent to `/v1/tailoring-suggestions`) would need to also send the raw
   file — a real product/privacy decision (raw file storage, even
   in-memory, is a different data-retention posture than "text only,"
   and should be a deliberate choice, not a side effect of this change).
2. **Where those bytes would live server-side.** Mirroring
   `TailoringPlanStore`'s in-memory, process-lifetime pattern is the
   natural fit, but needs its own component (e.g. a `DocumentBytesStore`
   keyed alongside the plan) rather than overloading the existing store.
3. **Suggestion generation would need to use `DocxStructureMapper`
   instead of `ResumeStructureParser` whenever the source is DOCX**, so
   `target_item_id`s generated during planning are guaranteed to resolve
   against the same document at export time. This is a conditional branch
   in whatever endpoint builds the `StructuredResume` for generation, not
   a change to the Planner/Rewrite/Validate pipeline itself.
4. **A new export path** (`ExportFormat.DOCX` when the source was DOCX)
   that calls `DocxDocumentEditor.apply` instead of `DocxResumeRenderer`,
   and labels the result `FormatFidelity.APPROXIMATE_STYLE` (not
   `EXACT_ORIGINAL` — see the `update`/`replace` caveat above — and not
   `REGENERATED_TEMPLATE`, since it demonstrably isn't).

## Tests

`tests/test_docx_structure_mapper.py` (8), `tests/test_docx_nodes.py` (8),
`tests/test_docx_document_editor.py` (12) — 28 tests total, against a
shared fixture builder (`tests/document_editing_fixtures.py`) producing a
formatting-rich sample DOCX (distinct fonts/sizes/colors/bold/italic per
paragraph, a bulleted list, a table, a header, and a footer), so
assertions can verify both "the edited paragraph has the right formatting"
and "everything else — including the table, header, and footer — is
provably untouched," not just "the text changed."

## Known limitations

- Mixed inline formatting within one paragraph doesn't survive an
  `update`/`replace`/`add_emphasis` edit to that paragraph exactly (see
  the fidelity table above).
- Table cells, headers, and footers are preserved but not individually
  editable in this version (matches the existing DOCX extractor's scope).
- Not yet reachable via any API — see "Integration status."
- `DocxDocumentEditor` re-parses the document on every `apply` call
  (no caching across calls) — the right choice for correctness (always
  mutating a fresh, known-consistent node map) but means repeated calls
  against the same bytes re-do the mapping walk each time; not a concern
  at expected resume-sized documents and edit-batch sizes.

## Future enhancements

- Wire the four integration-status items above once the product/privacy
  decision to retain original file bytes is made explicitly.
- A PDF fidelity engine implementing the same `EditableNode` protocol.
- Table-cell-level editing, if a future suggestion type ever needs to
  target tabular resume content (e.g. a skills matrix).
