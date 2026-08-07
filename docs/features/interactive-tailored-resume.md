# Interactive Resume Tailoring

This document describes the Interactive Resume Tailoring feature **as
implemented** — the pipeline, domain model, API contracts, frontend state,
export behavior, and known limitations. It replaces the earlier
whole-section rewrite pipeline described in
[`docs/features/tailoring-engine.md`](tailoring-engine.md) (superseded, kept
for historical context) and supersedes this file's own earlier
vision-only draft.

## Vision, restated as delivered

ResumePilotAI does not rewrite resumes. It proposes small, evidence-backed
edit *suggestions* — one existing bullet at a time — that a candidate
reviews and individually approves before anything about their resume
changes. The AI acts as an editor operating on real, already-established
facts (from the original resume, the prior analysis, and the Career
Conversation transcript), never as an author inventing new ones.

---

## Architecture

```
Resume Text
      │
      ▼
ResumeStructureParser              <- heuristic, no LLM call
      │
      ▼
StructuredResume (sections/items, stable ids)
      │
      ▼
EvidenceStoreBuilder                <- pure aggregation, no LLM call
      │  (per-resume-item evidence + analysis + conversation)
      ▼
Evidence Store
      │
      ▼
Suggestion Planner (LLM, 1 call)    <- decides WHAT/WHY/WHICH evidence, no text yet
      │
      ▼
PlannedEdits (SuggestedEdit[])
      │
      ▼
Suggestion Rewrite Engine (LLM, 1 call per edit)  <- scoped to only that edit's evidence
      │
      ▼
Per-suggestion Validation            <- pure, deterministic, no LLM call
      │
      ▼
SuggestionPlan  ──stored──▶  TailoringPlanStore (in-memory, keyed by plan_id)
      │
      ▼  (user reviews, selects, optionally edits, adds custom instructions)
      │
SuggestionApplier                    <- deterministic, re-derives from the stored plan
      │
      ▼
Final StructuredResume + FinalValidationReport
      │
      ▼
ExportService                        <- TXT / Markdown / DOCX / PDF
```

Three LLM call *kinds* exist in this pipeline, and only two of them run per
suggestion generation request:

1. **Suggestion Planner** — one call per generation request. Given the
   whole Evidence Store and the resume's structure (rendered as an
   id-to-text catalog), decides which existing items should change, how
   (`SuggestionOperation`), why, and which evidence ids justify it. Never
   writes resume prose.
2. **Suggestion Rewrite Engine** — one call *per proposed edit*. Given only
   that edit's approved evidence (never the full catalog), produces the
   actual text.
3. No LLM call happens at apply or export time. `SuggestionApplier` and
   `ExportService` are both pure, deterministic functions of already-
   generated, already-validated data.

This mirrors the superseded whole-section pipeline's two-call-per-change
shape exactly (see `tailoring-engine.md`) — the granularity changed (one
resume *item* instead of one whole *section*), the evidence-scoping
guarantee did not.

---

## Domain model

### `StructuredResume` (`app.models.resume_structure`)

```python
ResumeItem(item_id: str, text: str)
ResumeSection(section_id: str, heading: str, items: list[ResumeItem])
StructuredResume(sections: list[ResumeSection])
```

Built by `ResumeStructureParser` (`app.resume_structure.parser`) — a
heuristic, LLM-free parser: ALL-CAPS lines or an exact match against a
common-heading keyword list become section headings; bullet-prefixed
lines become individual items; consecutive non-bullet lines between blank
lines are joined into one item. Ids are deterministic and stable for as
long as the resume text itself doesn't change (`section-{n}`,
`section-{n}-item-{m}`) — this is what lets a suggestion generated in one
request still resolve correctly when applied in a later request, and lets
the frontend/backend agree on identity without either persisting a shared
mutable copy.

**Known limitation:** this parser cannot recover the original document's
visual structure (columns, tables, font-based section breaks) — only
whatever survived as plain text extraction. A resume with unusual
formatting may be split into sections/items differently than a human
would. See "Known limitations" below.

### `TailoringSuggestion` (`app.models.tailoring_suggestions`)

Every suggestion anchors to one existing `target_item_id` — there is no
"append a brand-new item with no anchor" case in this version; even
insertions are anchored relative to an existing neighbor.

| Operation | `current_text` | Semantics |
|---|---|---|
| `append` | the item's existing text | `suggested_text` = full resulting text; must contain the original as a substring (enforced by the validator, not just prompted) |
| `update` / `replace` | the item's existing text | `suggested_text` = full resulting text; may reword, unlike `append` |
| `add_emphasis` | the item's existing text | reorders/rewords *existing* claims only, introduces no new claim |
| `remove` | the item's existing text | `suggested_text` is empty; the item is dropped |
| `insert_before` / `insert_after` | `null` | `suggested_text` is a brand-new item's full text, anchored next to `target_item_id` |

`REPLACEMENT_OPERATIONS = {append, update, replace, add_emphasis, remove}`
is what the frontend uses to decide whether to show a "Current vs
Suggested" comparison (these five) or a plain "New addition" (the two
insert operations, where `current_text` is always `null`).

Every `TailoringSuggestion` also carries: `suggestion_id` (stable within
its plan), `reason`, `evidence_ids`/`evidence_sources`, `confidence`
(0–100, model-reported), `selected_by_default` (true only when validation
status is one of the three "supported" statuses *and* confidence ≥ 60),
and `validation_status`/`validation_issues`.

### Evidence model

The original resume is a first-class, per-item citable evidence source —
not a special case. `EvidenceStoreBuilder` (`app.evidence.evidence_store_builder`)
emits one `EvidenceItem` per resume item (`evidence_id = f"resume-{item_id}"`,
`source = EvidenceSource.RESUME`), plus a whole-document fallback item
(`resume-full-text`), analysis-derived items (strengths, matching
projects, matched skills), and one item per completed Career Conversation
turn (`source = EvidenceSource.CONVERSATION`). Weaknesses/improvements are
deliberately *not* evidence (they describe gaps, not facts).

A suggestion's `evidence_ids` may only cite ids the Planner was actually
shown, and the Rewrite Engine's prompt for one suggestion is scoped to
*only* that suggestion's approved evidence
(`evidence_store.catalog_text_for_ids(edit.evidence_ids)`), never the full
catalog — the model is structurally incapable of citing a fact it wasn't
shown for that specific edit, not merely instructed not to. As defense in
depth, `TailoringSuggestionWorkflow` also discards any evidence id the
rewrite call returns that wasn't in the approved set, rather than trusting
it.

### Validation classification (`app.evidence.suggestion_validator`)

| Status | Meaning |
|---|---|
| `supported_by_original_resume` | Every claim-like term in the suggested text is backed by cited evidence, and all of it came from the resume |
| `supported_by_conversation` | Same, but backed by Career Conversation evidence only |
| `supported_by_both` | Backed by a mix of resume and conversation evidence |
| `unsupported` | No evidence cited, an unknown evidence id was cited, or a claim-like term (capitalized/digit-containing/ALL-CAPS, outside a skip-list of ordinary action verbs) has no support in the cited evidence |
| `structurally_invalid` | The operation/target/text combination is internally inconsistent — e.g. an `append` whose text doesn't actually contain the original, a replacement missing `current_text`, or a target item that doesn't exist |
| `conflict` | Never set at generation time — only produced by `SuggestionApplier` at apply time, when two *selected* suggestions collide |

An unchanged, already-true statement from the original resume is never
penalized just because it wasn't repeated in a Career Conversation turn —
`supported_by_original_resume` is a fully valid, non-degraded outcome.

### Custom instructions

Free text the user provides is passed to both the Planner and Rewrite
Engine prompts as **constraints only** ("keep it under two pages," "don't
remove Adobe experience") — the system prompts explicitly instruct that
an instruction can never justify a suggestion the Evidence Store doesn't
support. There is no code path where instruction text is treated as
evidence; a suggestion still needs real, cited `evidence_ids` regardless
of what the instructions say. A malformed instruction can shape *which*
suggestions the Planner proposes, never manufacture unsupported ones — a
Planner output with empty/unknown evidence still fails
`TailoringSuggestionWorkflow._validate_edit_contract` and the whole
generation request fails loudly (`502`) rather than silently accepting an
ungrounded edit.

---

## Deterministic application (`app.tailoring.applier.SuggestionApplier`)

`SuggestionApplier.apply` never calls an LLM. Given the exact
`(StructuredResume, SuggestionPlan, EvidenceStore)` triple a generation
request produced (see "Trust boundary" below):

1. Every selected/edited suggestion id is checked against the plan's own
   ids — an id that doesn't belong raises `UnknownSuggestionIdError` (→
   HTTP `400`).
2. User-edited text is revalidated through the same
   `evidence.suggestion_validator.validate_suggestion` generation used —
   a result outside the three "supported" statuses raises
   `SuggestionRevalidationFailedError` (→ HTTP `422`) and the edit is
   never applied.
3. **Conflict policy:** two selected suggestions conflict if they'd both
   determine the same physical outcome — either two mutate the same
   target item's own content (any two of `REPLACEMENT_OPERATIONS`), or
   two both insert at the same position relative to the same anchor (two
   `insert_before` on the same item, or two `insert_after`). An
   `insert_before`/`insert_after` does *not* conflict with a mutation of
   its own anchor item — inserting a new bullet after item X while also
   appending to X's own text are independent edits at different physical
   positions. Any conflict raises `SuggestionConflictError` (→ HTTP
   `409`) naming the colliding suggestion ids; nothing is silently
   chosen.
4. **Deterministic order:** suggestions are applied by walking the resume
   in its own original section/item order — never selection order,
   submission order, or confidence order — so the result never depends on
   incidental request ordering.
5. Every item not targeted by a selected suggestion is carried through
   byte-for-byte unchanged.
6. A final structural pass (`_run_final_validation`) checks two
   assembled-result invariants that only make sense post-assembly: no
   untouched item actually changed, and no duplicate bullet text was
   introduced within a section. This is reported, not enforced — it never
   blocks a download, since the user remains in control even of an
   imperfect result.

No new unrestricted LLM call ever rewrites the whole resume after
approval — this was an explicit, hard requirement, not an optimization.

### Trust boundary

`TailoringPlanStore` (`app.sessions.tailoring_plan_store`, in-memory,
process-lifetime, mirrors `ConversationSessionStore`'s exact pattern)
stores a `StoredPlan` — the `SuggestionPlan` *and* the exact
`StructuredResume`/`EvidenceStore` it was generated against — keyed by
`plan_id`. The apply and export endpoints never trust client-supplied
suggestion content: they look up the plan by id and re-derive everything
from what the backend actually generated and validated. A client can only
ever influence *which* ids are selected and *what* edited text to
revalidate — never inject arbitrary "evidence" or resume content directly.

**Scope limit:** like `ConversationSessionStore`, this is in-memory,
single-process, with no expiry — a plan is lost on server restart or if a
different worker process handles a later request. A real store (Redis, a
database) is required before this runs behind multiple workers or needs
to survive a restart. Not addressed in this version (out of scope — no
database persistence was a hard scope boundary for this feature).

---

## API contracts

Three endpoints under `/v1/tailoring-suggestions`, replacing the
superseded `POST /v1/tailor-resume`:

### `POST /v1/tailoring-suggestions` — generate a plan

Request (`GenerateSuggestionsRequest`): `resume`, `job_description`,
`resume_analysis` (reuses `AnalyzeResumeResponse`), `career_conversation`
(reuses `ConversationSessionResponse`), `custom_instructions` (optional),
`resume_filename` (optional — used *only* to compute
`default_export_format`, never to read file content).

Response (`GenerateSuggestionsResponse`): `plan_id`, `suggestions`
(`SuggestionResponse[]`), `available_export_formats`,
`default_export_format`.

Failure modes: `502` if the Planner's own output violates its contract
(empty/unknown evidence, unknown target item — see
`SuggestionPlanInvalidError`); a bare `500` for any other pipeline
failure (schema-validation failure, provider error), matching every other
endpoint's `except Exception: log; raise` convention.

### `POST /v1/tailoring-suggestions/{plan_id}/apply` — apply a selection

Request (`ApplySuggestionsRequest`): `selected_suggestion_ids`,
`edited_texts` (keyed by `suggestion_id`, only meaningful for a selected
id).

Response (`ApplySuggestionsResponse`): `applied_suggestion_ids`,
`final_resume_text` (plain-text render, for preview), `final_validation`
(`is_valid`, `messages`).

Failure modes: `404` unknown `plan_id`; `400` unknown suggestion id;
`409` conflicting selections; `422` a user edit failed revalidation.

### `POST /v1/tailoring-suggestions/{plan_id}/export` — download a file

Request (`ExportResumeRequest`): same selection/edit shape as apply, plus
`format` (`txt`/`markdown`/`docx`/`pdf`) and an optional `filename_base`
(sanitized server-side; the extension always comes from `format`, never
from client input).

Response: a raw file body — `Content-Type` matches the format,
`Content-Disposition: attachment; filename="..."` carries a sanitized
filename (`[A-Za-z0-9_-]` only, no path separators, capped length,
falls back to `Tailored_Resume` if nothing safe remains), and a custom
`X-Export-Fidelity` header carries `exact_original` / `approximate_style`
/ `regenerated_template` (see "Export behavior" below). Both
`Content-Disposition` and `X-Export-Fidelity` are added to the CORS
middleware's `expose_headers` (`app.app.create_app`) — without this, a
cross-origin `fetch()` from the frontend's dev origin can see the raw
HTTP response but `response.headers.get(...)` returns `null` for both,
since browsers only expose a small safelist of response headers to JS by
default. **This was a real bug caught during manual HTTP smoke testing**
(curl saw the headers fine; a browser-equivalent request wouldn't have) —
fixed in `create_app`, with a regression test in
`tests/test_tailoring_suggestions_api.py`.

Re-derives the final resume itself via the same `SuggestionApplier` call
apply uses — never trusts a client-supplied "final resume" blob for
export content, for the same trust-boundary reason as apply.

---

## Frontend

### State (`ResumeSessionProvider` / `resumeSessionTypes.ts`)

Extended, not replaced — no second state mechanism, no direct
`sessionStorage` access outside `resumeSessionStorage.ts`. New persisted
fields: `tailoringPlan`, `tailoringPlanStatus` (`idle`/`error` persisted;
`generating` normalizes to `idle`, same pattern as `AnalysisStatus`),
`tailoringSelections` (`string[]` of suggestion ids),
`tailoringCustomInstructions`, `tailoringEditedTexts` (`Record<string,
string>`, only entries for suggestions the user actually edited),
`finalTailoredResume` (`{finalResumeText, appliedSuggestionIds}` —
compact, not the full structured resume), `tailoringValidationReport`,
`tailoringAvailableExportFormats`, `tailoringSourceFormat`.
`RESUME_SESSION_VERSION` was bumped (1 → 2); a session persisted by a
prior build fails the new envelope check and is discarded cleanly, the
same graceful path already used for any other malformed session.

**Never stored:** raw uploaded file bytes (never were), exported binary
content (PDF/DOCX bytes stay in-memory only, as a `Blob`, for exactly as
long as the download takes), object URLs (created and revoked
synchronously around one download, never persisted). `finalTailoredResume`
stores only the rendered text and which suggestion ids produced it —
the backend can always re-derive the full structured resume
deterministically from the stored plan, so the frontend doesn't need a
second copy of it.

`finalTailoredResume` is set only on a successful apply and is never
cleared by a later failed apply/export — the same "last successful result
survives a later failure" contract the superseded `tailoredResumeResult`
had, now also covering export failures specifically.

### API client (`lib/tailoringSuggestionsApi.ts`)

Typed request/response functions for all three endpoints.
`TailoringApiErrorCause` (`not_found` / `unknown_suggestion` / `conflict`
/ `revalidation_failed` / `unknown`) is derived from the response status
and attached via `ApiError`'s standard `cause` option — the same
convention `careerConversationApi.ts` already used for 404/409. Export
parses `Content-Disposition` for a filename (regex on the quoted value,
falls back to `Tailored_Resume`) and `X-Export-Fidelity` for the fidelity
label, and **only ever calls `.blob()` after checking `response.ok`** — an
error response is always JSON (`{"detail": ...}`); reading that as a blob
and offering it for download would hand the user a corrupted file
containing an error message instead of surfacing the real failure.
`downloadExportedFile` creates an object URL, triggers a synthetic
anchor click, and revokes the URL in a `finally` block so it's cleaned up
even if the click itself throws.

### `TailoredResumePage` — five stages, one page

No stage is a separate route; all five render conditionally in one page
based on shared state, so a refresh at any point re-derives the correct
stage with zero network calls:

1. **Generate Tailoring Plan** — gated on completed analysis *and* a
   *completed* Career Conversation (not just an active session id — the
   old gate only checked session existence; the new one checks
   `careerConversationStatus === 'complete'`). Explains nothing changes
   yet. No auto-generation on mount or on refresh — `generate` only ever
   runs from the button's own click handler.
2. **Review Suggestions** — one `TailoringSuggestionCard` per suggestion:
   operation label (Append/Insert/Update/Replace/Remove/Add emphasis),
   target section, Current-vs-Suggested (for `REPLACEMENT_OPERATIONS`) or
   "New addition" (for insertions), reason, evidence source chips,
   validation-status badge, an independent checkbox. Select all/Clear
   all/selected count. An **Edit** action is offered per suggestion
   (backed by the apply endpoint's real revalidation support — not a
   fake/local-only edit): edited text is tracked separately from the
   original, marked with an "Edited" badge, and **Reset** restores the
   model-generated text.
3. **Custom Instructions** — a free-text field ("Anything else you want
   to change?"), persisted, applied to the *next* generate/regenerate
   call.
4. **Apply Selected Changes** — disabled with zero selections. Sends
   `plan_id`, selected ids, and `edited_texts` (only for selected,
   edited suggestions). A `422` revalidation failure is parsed for the
   named suggestion id and shown inline on that suggestion's card where
   possible, otherwise as a banner — the plan and selections are never
   reset by a failed apply. A later failed apply never clears a
   previously successful `finalTailoredResume`.
5. **Preview and Download** — a plain-text ATS-friendly preview, an
   applied-vs-not-included summary (every suggestion in the plan is
   accounted for one way or the other), the final validation report, and
   `TailoringDownloadPanel`: only formats the backend actually reported
   as available, the default format visually marked, and fixed, honest
   per-format fidelity copy ("Plain text" / "Markdown" / "Regenerated
   DOCX" / "Regenerated PDF" — never implying original styling survived).
   A failed export shows an inline error next to the download controls
   without touching the preview above it.

### CTA lifecycle (`TailoredResumeBanner`, `ConversationCompleteCard`)

Both read `careerConversationStatus`/`tailoringPlan`/`finalTailoredResume`
from `ResumeSessionProvider` — never page-local flags — so their labels
can't drift from what clicking them leads to, and stay correct across a
refresh: *conversation incomplete* → disabled "Complete Career
Conversation first"; *complete, no plan* → "Generate Tailoring Plan";
*plan exists, nothing applied* → "Review Suggestions"; *final resume
exists* → "View Tailored Resume". `Sidebar`'s "Tailored Resume" nav item
gating (on `resumeAnalysis` existing) was unchanged — no new gate was
needed there.

---

## Export behavior and fidelity

No original file bytes are retained anywhere past upload — the frontend
extracts text client-side (`pdfjs-dist`/`mammoth`) and only ever persists
`{text, fileName}`; the backend's `app.ingestion` extractors exist but are
unwired dead code (confirmed by grep during this feature's investigation:
nothing calls them). Every export is therefore built from
`StructuredResume` content, never from a stored original document.

| Format | Fidelity | Why |
|---|---|---|
| TXT | `approximate_style` | Content-faithful re-render (`StructuredResume.to_text()`); exact original whitespace/line breaks are not guaranteed to match |
| Markdown | `approximate_style` | Same content-faithfulness; rendered as clean `##`/`-` Markdown regardless of the original file's exact Markdown syntax |
| DOCX | `regenerated_template` | Always a freshly generated `python-docx` document in a clean style — the original file's fonts/colors/layout were never retained to reproduce. A high-fidelity, edit-in-place engine exists (`app.document_editing`, see [`docs/features/high-fidelity-docx-editing.md`](high-fidelity-docx-editing.md)) but is not yet wired into this export path — see that doc's "Integration status" for exactly what's still needed (original bytes never reach the backend today). |
| PDF | `regenerated_template` | Always a freshly generated `reportlab` document — never a reproduction of any original PDF's layout, per this feature's explicit requirement not to overclaim PDF preservation |

`exact_original` is a defined value in `FormatFidelity` but is never
produced by this version — reaching it would require retaining and
round-tripping actual source bytes, which is out of scope (see "Future
enhancements").

`default_export_format` is computed from the uploaded filename's
extension only (`app.export.service.detect_source_format` /
`ORIGINAL_FORMAT_EXPORT`): `.txt` → `txt`, `.md`/`.markdown` → `markdown`,
`.docx` → `docx`; a `.pdf` upload (or an unrecognized/missing filename)
defaults to `txt`, deliberately never to `pdf` — a regenerated PDF should
never be pre-selected as if it were "the original format."

---

## Security and privacy considerations

- **Evidence trust boundary**: covered above — the backend never accepts
  client-supplied evidence or suggestion content as authoritative for
  apply/export; only ids are trusted, and only against what the server
  itself generated.
- **Filename sanitization**: `sanitize_filename_base` strips everything
  outside `[A-Za-z0-9_-]`, caps length, and falls back to a fixed default
  — verified against a path-traversal-shaped input
  (`"../../etc/passwd; rm -rf"` → `"etc_passwd_rm_-rf"`) in both unit and
  HTTP-level tests. No filesystem path is ever exposed in a response
  header.
- **No content in logs**: every new module follows the existing
  structured-logging convention — counts, ids, statuses, elapsed times —
  never resume/evidence/suggestion/job-description text.
- **CORS**: `expose_headers` was widened for `Content-Disposition`/
  `X-Export-Fidelity` specifically (see above); `allow_origins` is
  otherwise unchanged from the existing app-wide CORS configuration.

---

## Known limitations

- **Heuristic resume parsing.** `ResumeStructureParser` cannot recover
  columns, tables, or purely font-based section breaks — only what
  survives plain-text extraction. Uploads with unconventional formatting
  may produce different section/item boundaries than a human would draw.
- **In-memory plan store.** A generated plan does not survive a backend
  restart or move between worker processes (see "Trust boundary" above).
- **No PDF/DOCX exact-layout preservation reachable from export yet.** A
  DOCX edit-in-place engine exists (see
  [`docs/features/high-fidelity-docx-editing.md`](high-fidelity-docx-editing.md))
  but isn't wired into the upload/generate/export flow — DOCX export
  still always regenerates from scratch today. PDF has no equivalent
  engine at all yet.
- **Coarse conflict policy.** Two suggestions are treated as conflicting
  whenever they'd mutate the same item or insert at the same anchor
  position, even in cases a more advanced merge algorithm could
  theoretically reconcile (e.g. two independent `append`s to the same
  line). This is a deliberate safety-over-flexibility tradeoff — see
  `SuggestionApplier`'s module docstring — not an oversight.
- **Markdown headings from a Markdown upload aren't semantically parsed.**
  The parser's heading heuristic (ALL CAPS or a common-heading keyword
  match) doesn't understand `#`/`##` Markdown syntax, so a Markdown
  résumé's `## Skills` may be treated as ordinary item text rather than a
  detected heading, depending on capitalization. Content is preserved
  either way; section boundaries may not match author intent exactly.
- **No suggestion regeneration for a single item.** "Regenerate" replaces
  the *whole* plan (a fresh Planner + Rewrite Engine pass); there is no
  narrower "just retry this one suggestion" action in this version.

## Future enhancements

- Real plan persistence (Redis/database) so plans survive restarts and
  multi-worker deployments.
- Retained, round-trippable original file bytes for genuine
  `exact_original`/`approximate_style` fidelity on DOCX — the editing
  engine to consume them already exists (see
  [`docs/features/high-fidelity-docx-editing.md`](high-fidelity-docx-editing.md));
  what's missing is the upload/storage plumbing to get bytes to it. PDF
  layout preservation is a substantially harder problem and would need
  its own design.
- Resume version history across multiple tailoring sessions (explicitly
  out of scope for this feature — see `ROADMAP.md`'s "Multiple Resume
  Versions" item, same open item the superseded pipeline's docs already
  named).
- A narrower "regenerate this one suggestion" action, rather than a full
  plan regeneration.
- The Interview Preparation Engine described in this document's earlier
  vision draft — explicitly out of scope for this feature.
