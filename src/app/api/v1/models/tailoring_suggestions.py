"""Request/response schemas for the Interactive Tailoring endpoints.

Three endpoints, three request/response pairs, matching the product's own
three-stage split (generate -> apply -> export) rather than the single
`/v1/tailor-resume` request/response of the superseded whole-section
pipeline (see `docs/features/tailoring-engine.md`'s "superseded" note).

`SuggestionResponse`/`FinalValidationResponse` mirror their domain
counterparts (`app.models.tailoring_suggestions.TailoringSuggestion`,
`app.tailoring.applier.FinalValidationReport`) field by field, matching
this codebase's established API/domain split (see `tailor_resume.py`'s
former `_to_response`) rather than exposing domain models directly.
`SuggestionOperation`/`SuggestionValidationStatus`/`ExportFormat` are
reused directly from their domain/export modules, the same way
`TailoringAction` was reused by the superseded pipeline's API models — a
small, fixed-membership value enum, not an evolving object shape.

Export itself (`POST .../export`) has no response model here: it returns
a raw file body with a `Content-Disposition` header, not JSON — see
`app.api.v1.endpoints.tailoring_suggestions.export_final_resume`.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.api.v1.models.career_conversation import ConversationSessionResponse
from app.export.models import ExportFormat
from app.models.tailoring_suggestions import SuggestionOperation, SuggestionValidationStatus


class GenerateSuggestionsRequest(BaseModel):
    """Request body for `POST /v1/tailoring-suggestions`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume: str = Field(description="Raw resume text to generate suggestions for.")
    job_description: str = Field(description="Raw job description text to tailor towards.")
    resume_analysis: AnalyzeResumeResponse = Field(
        description="The prior resume analysis result, exactly as returned by POST /v1/analyze."
    )
    career_conversation: ConversationSessionResponse = Field(
        description=(
            "The Career Conversation session's current state. Its history (which may be "
            "empty) becomes additional evidence suggestions can cite."
        )
    )
    custom_instructions: str | None = Field(
        default=None,
        description=(
            "Free-text constraints on which suggestions to propose or avoid, e.g. 'keep "
            "the resume under two pages.' Never a source of new facts -- an instruction can "
            "never justify a suggestion that isn't grounded in real evidence."
        ),
    )
    resume_filename: str | None = Field(
        default=None,
        description=(
            "The originally uploaded file's name, if any. Used only to determine which "
            "export format counts as 'the original format' for the default download "
            "option -- never used to look up or re-read any file content, since no "
            "original file bytes are retained after upload."
        ),
    )


class SuggestionResponse(BaseModel):
    """One evidence-backed edit suggestion, ready for user review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suggestion_id: str = Field(description="Stable identifier within this suggestion plan.")
    target_section_id: str = Field(description="The id of the resume section this targets.")
    target_item_id: str = Field(description="The id of the existing resume item this anchors to.")
    operation: SuggestionOperation = Field(description="The exact kind of edit proposed.")
    current_text: str | None = Field(
        description="The existing item's text, for a true replacement; null for insertions."
    )
    suggested_text: str = Field(description="The proposed text (full resulting text).")
    reason: str = Field(description="Why this change would improve fit for the job description.")
    evidence_ids: list[str] = Field(description="Evidence Store ids this suggestion is based on.")
    evidence_sources: list[str] = Field(
        description="Human-readable labels for evidence_ids (e.g. 'Conversation Turn 2')."
    )
    confidence: int = Field(description="The model's own confidence in this edit, 0-100.")
    selected_by_default: bool = Field(
        description="Whether this suggestion should start pre-selected in the review UI."
    )
    validation_status: SuggestionValidationStatus = Field(
        description="How this suggestion's text relates to its cited evidence."
    )
    validation_issues: list[str] = Field(
        description="Human-readable reasons behind validation_status, if not cleanly supported."
    )
    conflicts_with: list[str] = Field(
        description=(
            "suggestion_ids of other suggestions in this plan that are mutually exclusive with "
            "this one (selecting more than one from the same group is rejected at apply time). "
            "Empty if this suggestion has no conflicts."
        )
    )


class GenerateSuggestionsResponse(BaseModel):
    """Response body for `POST /v1/tailoring-suggestions`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str = Field(
        description=(
            "Stable identifier for this plan. Required by the apply and export endpoints -- "
            "they verify every selected suggestion id against the plan stored server-side "
            "under this id, never trusting suggestion content the client sends back."
        )
    )
    suggestions: list[SuggestionResponse] = Field(
        description="Every proposed suggestion, in the order they should be considered."
    )
    available_export_formats: list[ExportFormat] = Field(
        description="Every format the final resume can be exported as, once applied."
    )
    default_export_format: ExportFormat = Field(
        description=(
            "The format that best matches the originally uploaded file's format, where "
            "technically supported -- the review UI's suggested default download choice."
        )
    )


class ApplySuggestionsRequest(BaseModel):
    """Request body for `POST /v1/tailoring-suggestions/{plan_id}/apply`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_suggestion_ids: list[str] = Field(
        description="Which suggestions (by id, from this plan) the user approved."
    )
    edited_texts: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "User-edited replacement text, keyed by suggestion_id, for any selected "
            "suggestion whose proposed text the user changed before approving. Only "
            "suggestion ids already present in selected_suggestion_ids may appear here; "
            "edited text is always revalidated before being applied, never trusted as-is."
        ),
    )


class FinalValidationResponse(BaseModel):
    """A summary check over the assembled final resume, after all edits are applied."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool = Field(description="True iff no structural issues were found.")
    messages: list[str] = Field(description="Actionable descriptions of any issues found.")


class ApplySuggestionsResponse(BaseModel):
    """Response body for `POST /v1/tailoring-suggestions/{plan_id}/apply`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    applied_suggestion_ids: list[str] = Field(
        description="The suggestions that were actually applied, in deterministic apply order."
    )
    final_resume_text: str = Field(
        description="The resulting resume, rendered as plain text, for preview."
    )
    final_validation: FinalValidationResponse = Field(
        description="Structural validation results for the assembled final resume."
    )


class ExportResumeRequest(BaseModel):
    """Request body for `POST /v1/tailoring-suggestions/{plan_id}/export`.

    Mirrors `ApplySuggestionsRequest` exactly, rather than accepting a
    previously-applied final resume from the client: the export endpoint
    re-derives the final resume itself, from the same trusted plan and
    the same deterministic `SuggestionApplier`, so a downloaded file can
    never contain content the backend didn't itself validate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_suggestion_ids: list[str] = Field(
        description="Which suggestions (by id, from this plan) the user approved."
    )
    edited_texts: dict[str, str] = Field(
        default_factory=dict, description="User-edited replacement text, keyed by suggestion_id."
    )
    format: ExportFormat = Field(description="Which file format to export the final resume as.")
    filename_base: str | None = Field(
        default=None,
        description=(
            "A candidate name for the downloaded file, e.g. a filename stem derived from "
            "the candidate's name and target role. Sanitized server-side before use; the "
            "file extension is always derived from format, never taken from this value."
        ),
    )
