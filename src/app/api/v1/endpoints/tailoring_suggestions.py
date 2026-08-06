"""Interactive Tailoring endpoints: `/v1/tailoring-suggestions*`.

Three endpoints, matching the product's own three-stage split:

- `POST /tailoring-suggestions` -- generate a `SuggestionPlan` (Stages 1-4
  of `TailoringSuggestionWorkflow`), stored server-side under a `plan_id`.
- `POST /tailoring-suggestions/{plan_id}/apply` -- apply a user-approved
  subset of that plan's suggestions (`SuggestionApplier`) and preview the
  result. Never trusts client-supplied suggestion content: every id is
  checked against the plan this backend actually generated.
- `POST /tailoring-suggestions/{plan_id}/export` -- re-derive the same
  final resume (by re-running the applier against the same trusted plan)
  and render it as a downloadable file (`ExportService`). Returns a raw
  file body, not JSON.

Wires HTTP requests to the injected workflow/store/applier/export
collaborators and back, exactly as `tailor_resume.py` (the superseded
pipeline's endpoint) did for `TailoringWorkflow`: no pipeline logic of its
own, only translation and dependency construction.

Logs request-level metadata (lengths, ids, counts, elapsed time,
success/failure) at INFO/ERROR -- never resume/job-description/evidence/
suggestion content.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.api.v1.models.career_conversation import ConversationSessionResponse
from app.api.v1.models.tailoring_suggestions import (
    ApplySuggestionsRequest,
    ApplySuggestionsResponse,
    ExportResumeRequest,
    FinalValidationResponse,
    GenerateSuggestionsRequest,
    GenerateSuggestionsResponse,
    SuggestionResponse,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
from app.export.models import ExportFormat
from app.export.service import ORIGINAL_FORMAT_EXPORT, ExportService, detect_source_format
from app.gateways.llm.factory import build_llm_gateway
from app.models.career_conversation import ConversationExchange
from app.models.resume_analysis import (
    HiringRecommendation,
    MatchingProject,
    OverallAssessment,
    ResumeAnalysisResult,
    ResumeImprovement,
    SkillMatch,
)
from app.models.tailoring_suggestions import TailoringSuggestion
from app.prompts.suggestion_planner_prompt_builder import SuggestionPlannerPromptBuilder
from app.prompts.suggestion_rewrite_prompt_builder import SuggestionRewritePromptBuilder
from app.resume_structure.parser import ResumeStructureParser
from app.sessions.tailoring_plan_store import StoredPlan, TailoringPlanStore
from app.tailoring.applier import (
    ApplyResult,
    SuggestionApplier,
    SuggestionConflictError,
    SuggestionRevalidationFailedError,
    UnknownSuggestionIdError,
)
from app.workflows.tailoring_suggestion_workflow import (
    SuggestionPlanInvalidError,
    TailoringSuggestionWorkflow,
)

logger = get_logger(__name__)

router = APIRouter()

_ALL_EXPORT_FORMATS = list(ExportFormat)


def get_tailoring_suggestion_workflow(
    settings: Settings = Depends(get_settings),
) -> TailoringSuggestionWorkflow:
    """Construct a `TailoringSuggestionWorkflow` wired with its current dependencies.

    Mirrors every other workflow-constructing dependency in this API
    layer (see `tailor_resume.py`'s former `get_tailoring_workflow`): a
    new instance per request, since every collaborator here is cheap and
    stateless to construct.
    """
    return TailoringSuggestionWorkflow(
        structure_parser=ResumeStructureParser(),
        evidence_store_builder=EvidenceStoreBuilder(),
        planner_prompt_builder=SuggestionPlannerPromptBuilder(),
        rewrite_prompt_builder=SuggestionRewritePromptBuilder(),
        gateway=build_llm_gateway(settings),
    )


def get_tailoring_plan_store(request: Request) -> TailoringPlanStore:
    """Return the process-lifetime `TailoringPlanStore` attached to `app.state`.

    Mirrors `career_conversation.py`'s `get_conversation_session_store`
    exactly: a `Request`-based dependency, since this store must be the
    same instance across requests, created once in `create_app`.
    """
    return request.app.state.tailoring_plan_store


def get_suggestion_applier() -> SuggestionApplier:
    """Construct a `SuggestionApplier`. Stateless, so a fresh instance per request is fine."""
    return SuggestionApplier()


def get_export_service() -> ExportService:
    """Construct an `ExportService`. Stateless, so a fresh instance per request is fine."""
    return ExportService()


def _to_domain_analysis(response: AnalyzeResumeResponse) -> ResumeAnalysisResult:
    """Map the API's `AnalyzeResumeResponse` onto the domain `ResumeAnalysisResult`.

    Written out field by field, duplicated from `tailor_resume.py`'s
    (superseded) and `career_conversation.py`'s identical mappers --
    matching this codebase's established per-endpoint independence, not
    an oversight.
    """
    return ResumeAnalysisResult(
        overall_assessment=OverallAssessment(
            overall_score=response.overall_assessment.overall_score,
            hiring_recommendation=HiringRecommendation(
                decision=response.overall_assessment.hiring_recommendation.decision,
                reason=response.overall_assessment.hiring_recommendation.reason,
            ),
            summary=response.overall_assessment.summary,
        ),
        skill_matches=[
            SkillMatch(
                category=skill_match.category,
                score=skill_match.score,
                matched_skills=skill_match.matched_skills,
                missing_skills=skill_match.missing_skills,
            )
            for skill_match in response.skill_matches
        ],
        matching_projects=[
            MatchingProject(
                title=matching_project.title,
                relevance_score=matching_project.relevance_score,
                reason=matching_project.reason,
            )
            for matching_project in response.matching_projects
        ],
        strengths=response.strengths,
        weaknesses=response.weaknesses,
        resume_improvements=[
            ResumeImprovement(
                section=resume_improvement.section,
                recommendation=resume_improvement.recommendation,
                priority=resume_improvement.priority,
            )
            for resume_improvement in response.resume_improvements
        ],
    )


def _to_domain_history(session: ConversationSessionResponse) -> list[ConversationExchange]:
    """Map the API's `ConversationSessionResponse.history` onto domain `ConversationExchange`s."""
    return [
        ConversationExchange(
            topic=exchange.topic,
            question=exchange.question,
            answer=exchange.answer,
            assistant_response=exchange.assistant_response,
        )
        for exchange in session.history
    ]


def _to_suggestion_response(suggestion: TailoringSuggestion) -> SuggestionResponse:
    return SuggestionResponse(
        suggestion_id=suggestion.suggestion_id,
        target_section_id=suggestion.target_section_id,
        target_item_id=suggestion.target_item_id,
        operation=suggestion.operation,
        current_text=suggestion.current_text,
        suggested_text=suggestion.suggested_text,
        reason=suggestion.reason,
        evidence_ids=suggestion.evidence_ids,
        evidence_sources=suggestion.evidence_sources,
        confidence=suggestion.confidence,
        selected_by_default=suggestion.selected_by_default,
        validation_status=suggestion.validation_status,
        validation_issues=suggestion.validation_issues,
    )


def _get_stored_plan_or_404(store: TailoringPlanStore, plan_id: str) -> StoredPlan:
    stored_plan = store.get(plan_id)
    if stored_plan is None:
        raise HTTPException(status_code=404, detail="Tailoring suggestion plan not found.")
    return stored_plan


def _run_applier(
    applier: SuggestionApplier,
    stored_plan: StoredPlan,
    payload: ApplySuggestionsRequest | ExportResumeRequest,
) -> ApplyResult:
    """Run `applier` against `stored_plan`, mapping its typed errors onto HTTP responses.

    Shared by both the apply and export endpoints -- export re-derives
    the same final resume the same way, rather than trusting a
    previously-applied result the client might send back (see
    `ExportResumeRequest`'s docstring).
    """
    try:
        return applier.apply(
            stored_plan.structured_resume,
            stored_plan.plan,
            stored_plan.evidence_store,
            selected_suggestion_ids=payload.selected_suggestion_ids,
            edited_texts=payload.edited_texts,
        )
    except UnknownSuggestionIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SuggestionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SuggestionRevalidationFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tailoring-suggestions", response_model=GenerateSuggestionsResponse)
async def generate_tailoring_suggestions(
    payload: GenerateSuggestionsRequest,
    workflow: TailoringSuggestionWorkflow = Depends(get_tailoring_suggestion_workflow),
    store: TailoringPlanStore = Depends(get_tailoring_plan_store),
    settings: Settings = Depends(get_settings),
) -> GenerateSuggestionsResponse:
    """Run the suggestion-generation pipeline and return a reviewable plan.

    The generated `SuggestionPlan`, the `StructuredResume` it targets,
    and the `EvidenceStore` it was generated from are all stored together
    under the returned `plan_id` (see `TailoringPlanStore`) -- the apply
    and export endpoints re-fetch this same bundle rather than trusting
    anything the client sends back about the plan's own content.
    """
    logger.info(
        "generate_tailoring_suggestions_received",
        resume_length=len(payload.resume),
        job_description_length=len(payload.job_description),
        conversation_turn_count=len(payload.career_conversation.history),
        has_custom_instructions=bool(payload.custom_instructions),
        provider=settings.primary_provider,
    )
    start = time.perf_counter()
    try:
        result = await workflow.generate_suggestions(
            resume=payload.resume,
            job_description=payload.job_description,
            resume_analysis=_to_domain_analysis(payload.resume_analysis),
            conversation_history=_to_domain_history(payload.career_conversation),
            custom_instructions=payload.custom_instructions,
        )
    except SuggestionPlanInvalidError as exc:
        logger.error(
            "generate_tailoring_suggestions_plan_invalid",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(
            "generate_tailoring_suggestions_failed",
            provider=settings.primary_provider,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    store.save(
        StoredPlan(
            plan=result.plan,
            structured_resume=result.structured_resume,
            evidence_store=result.evidence_store,
        )
    )

    source_format = detect_source_format(payload.resume_filename)
    default_export_format = ORIGINAL_FORMAT_EXPORT.get(source_format, ExportFormat.TXT)

    logger.info(
        "generate_tailoring_suggestions_completed",
        plan_id=result.plan.plan_id,
        provider=settings.primary_provider,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        suggestion_count=len(result.plan.suggestions),
    )
    return GenerateSuggestionsResponse(
        plan_id=result.plan.plan_id,
        suggestions=[_to_suggestion_response(s) for s in result.plan.suggestions],
        available_export_formats=_ALL_EXPORT_FORMATS,
        default_export_format=default_export_format,
    )


@router.post("/tailoring-suggestions/{plan_id}/apply", response_model=ApplySuggestionsResponse)
async def apply_tailoring_suggestions(
    plan_id: str,
    payload: ApplySuggestionsRequest,
    applier: SuggestionApplier = Depends(get_suggestion_applier),
    store: TailoringPlanStore = Depends(get_tailoring_plan_store),
) -> ApplySuggestionsResponse:
    """Apply a user-approved subset of `plan_id`'s suggestions and return a preview.

    `404` if `plan_id` is unknown (e.g. the server restarted since it was
    generated -- see `TailoringPlanStore`'s scope limits); `400` for an
    unknown suggestion id; `409` for two selected suggestions that
    conflict; `422` if user-edited text fails revalidation. None of these
    ever destroy a previously successful apply -- this endpoint doesn't
    mutate the stored plan, so a failed apply can simply be retried with
    a different selection.
    """
    logger.info(
        "apply_tailoring_suggestions_received",
        plan_id=plan_id,
        selected_count=len(payload.selected_suggestion_ids),
        edited_count=len(payload.edited_texts),
    )
    start = time.perf_counter()
    stored_plan = _get_stored_plan_or_404(store, plan_id)

    result = _run_applier(applier, stored_plan, payload)

    logger.info(
        "apply_tailoring_suggestions_completed",
        plan_id=plan_id,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        applied_count=len(result.applied_suggestion_ids),
        final_valid=result.final_validation.is_valid,
    )
    return ApplySuggestionsResponse(
        applied_suggestion_ids=result.applied_suggestion_ids,
        final_resume_text=result.final_resume.to_text(),
        final_validation=FinalValidationResponse(
            is_valid=result.final_validation.is_valid,
            messages=result.final_validation.messages,
        ),
    )


@router.post("/tailoring-suggestions/{plan_id}/export")
async def export_final_resume(
    plan_id: str,
    payload: ExportResumeRequest,
    applier: SuggestionApplier = Depends(get_suggestion_applier),
    export_service: ExportService = Depends(get_export_service),
    store: TailoringPlanStore = Depends(get_tailoring_plan_store),
) -> Response:
    """Re-derive the final resume from `plan_id` and return it as a downloadable file.

    Re-runs the same deterministic apply step `apply_tailoring_suggestions`
    would, from the same trusted server-side plan -- the exported file's
    content is never taken from a client-supplied "final resume" blob.
    Returns a raw file body (not JSON): `Content-Type` matches the
    requested format, and `Content-Disposition` carries a sanitized
    filename (see `app.export.service.sanitize_filename_base`) -- no
    filesystem path is ever exposed, and the extension always matches
    `payload.format`, regardless of what `payload.filename_base` contains.
    """
    logger.info(
        "export_final_resume_received",
        plan_id=plan_id,
        format=payload.format.value,
        selected_count=len(payload.selected_suggestion_ids),
    )
    start = time.perf_counter()
    stored_plan = _get_stored_plan_or_404(store, plan_id)

    result = _run_applier(applier, stored_plan, payload)
    exported = export_service.export(result.final_resume, payload.format, payload.filename_base)

    logger.info(
        "export_final_resume_completed",
        plan_id=plan_id,
        format=payload.format.value,
        fidelity=exported.fidelity.value,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        byte_count=len(exported.content),
    )
    return Response(
        content=exported.content,
        media_type=exported.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "X-Export-Fidelity": exported.fidelity.value,
        },
    )
