"""First business endpoint: `POST /v1/analyze`.

Wires an HTTP request to `ResumeAnalysisWorkflow` and back. Contains no
business logic itself — it only translates between the API schema and the
workflow's inputs/outputs, and constructs the workflow's dependencies. The
gateway is a provider chain built by `build_llm_gateway` from
`RESUMEPILOT_PRIMARY_PROVIDER`/`_SECONDARY_PROVIDER`/`_TERTIARY_PROVIDER`
(see `gateways/llm/factory.py`) — this endpoint has no gateway-selection
logic of its own beyond calling that one shared function.

Logs request-level metadata (lengths, provider, elapsed time,
success/failure) at INFO/ERROR — never resume/job-description content or
the generated analysis; see `analyze_resume`'s docstring.
"""

import time

from fastapi import APIRouter, Depends

from app.api.v1.models.analyze_resume import (
    AnalyzeResumeRequest,
    AnalyzeResumeResponse,
    HiringRecommendationResponse,
    MatchingProjectResponse,
    OverallAssessmentResponse,
    ResumeImprovementResponse,
    SkillMatchResponse,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.gateways.llm.factory import build_llm_gateway
from app.orchestration.job_preparation_persistence import start_job_preparation
from app.persistence.dependencies import get_persistence_store
from app.persistence.store import PersistenceStore
from app.prompts.resume_analysis_prompt_builder import ResumeAnalysisPromptBuilder
from app.workflows.resume_analysis_workflow import ResumeAnalysisWorkflow

logger = get_logger(__name__)

router = APIRouter()


def get_resume_analysis_workflow(
    settings: Settings = Depends(get_settings),
) -> ResumeAnalysisWorkflow:
    """Construct a `ResumeAnalysisWorkflow` wired with its current dependencies.

    A FastAPI dependency-provider function, not a module-level singleton or
    logic inside the route handler: this is the one place that decides
    *which* prompt builder and gateway the workflow uses for this
    endpoint. `ResumeAnalysisPromptBuilder` is still fixed (it's still a
    placeholder itself, and this task doesn't touch it). There is no
    longer a parser to wire in: `ResumeAnalysisWorkflow` now gets a
    validated `ResumeAnalysisResult` directly from the gateway's
    `generate_structured`, so `ResumeAnalysisResponseParser` has nothing
    left to do here (it still exists, just unused by this workflow).

    The gateway itself — which provider(s), in what order, with what
    fallback behavior — is entirely `build_llm_gateway`'s decision (see
    `gateways/llm/factory.py`): this function's only job is to obtain
    `settings` via `Depends(get_settings)` (keeping this function's only
    source of configuration consistent with how the rest of the app reads
    settings, and straightforward to override in tests via FastAPI's
    dependency-override mechanism) and hand it off. Provider selection,
    chain ordering, and "what counts as an unrecognized provider name"
    all now live in exactly one place shared by every workflow, not
    duplicated per endpoint.

    A new gateway chain (and workflow) instance is constructed per call
    rather than cached, since every gateway is cheap and stateless to
    construct — there is no cost or correctness reason to share instances
    across requests, and per-call construction keeps this function simple.
    """
    return ResumeAnalysisWorkflow(
        prompt_builder=ResumeAnalysisPromptBuilder(),
        gateway=build_llm_gateway(settings),
    )


@router.post("/analyze", response_model=AnalyzeResumeResponse)
async def analyze_resume(
    payload: AnalyzeResumeRequest,
    workflow: ResumeAnalysisWorkflow = Depends(get_resume_analysis_workflow),
    settings: Settings = Depends(get_settings),
    persistence_store: PersistenceStore = Depends(get_persistence_store),
) -> AnalyzeResumeResponse:
    """Analyze a resume against a job description and return the result.

    The handler does exactly two things: call the injected workflow, and
    map its `ResumeAnalysisResult` onto the API's `AnalyzeResumeResponse`
    shape. The mapping is written out field by field (including each
    nested object) rather than passing the domain model's dumped fields
    straight through, so that the API schema and the domain model are only
    *coincidentally* identical right now, not implicitly coupled — either
    can gain, rename, or drop a field later without the other silently
    breaking.

    Logs request-received and request-completed/-failed events with
    `provider` and `elapsed_ms`. `settings` is an added dependency
    (alongside `workflow`) purely so `settings.primary_provider` is available
    to log — it plays no role in the response. Only `len(payload.resume)`/
    `len(payload.job_description)` are logged, never the text itself; the
    generated `result` is never logged either, per the no-content-logging
    requirement. On failure, the caught exception is logged once here (a
    request-level summary distinct from any lower-layer log of the same
    failure — see `ResumeAnalysisWorkflow`/`GeminiGateway`) and re-raised
    unchanged via a bare `raise`, so FastAPI's default error handling — and
    therefore the resulting HTTP response — is completely unaffected.
    """
    logger.info(
        "analyze_request_received",
        resume_length=len(payload.resume),
        job_description_length=len(payload.job_description),
        provider=settings.primary_provider,
    )
    start = time.perf_counter()
    try:
        result = await workflow.analyze(
            resume=payload.resume,
            job_description=payload.job_description,
        )
    except Exception as exc:
        logger.error(
            "analyze_request_failed",
            provider=settings.primary_provider,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    # Durable history (see docs/persistent-backend-workflow-state.md):
    # every analyze call records a brand-new Resume + ResumeVersion(1,
    # original_upload) + JobPreparation, never merged with any prior
    # upload -- see start_job_preparation's own docstring. Deliberately
    # not wrapped in the same try/except as the workflow call above: a
    # persistence failure here is a distinct failure mode (this app's
    # durable store, not the LLM provider chain) and is logged under its
    # own event name before propagating unchanged, exactly like the
    # workflow failure path above -- see this project's error-handling
    # convention (no broad `except Exception`, no swallowed failures).
    try:
        job_preparation = await start_job_preparation(
            persistence_store,
            resume_text=payload.resume,
            job_description=payload.job_description,
            analysis_result=result.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.error(
            "analyze_persistence_failed",
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    logger.info(
        "analyze_request_completed",
        provider=settings.primary_provider,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        job_preparation_id=str(job_preparation.id),
    )
    return AnalyzeResumeResponse(
        overall_assessment=OverallAssessmentResponse(
            overall_score=result.overall_assessment.overall_score,
            hiring_recommendation=HiringRecommendationResponse(
                decision=result.overall_assessment.hiring_recommendation.decision,
                reason=result.overall_assessment.hiring_recommendation.reason,
            ),
            summary=result.overall_assessment.summary,
        ),
        skill_matches=[
            SkillMatchResponse(
                category=skill_match.category,
                score=skill_match.score,
                matched_skills=skill_match.matched_skills,
                missing_skills=skill_match.missing_skills,
            )
            for skill_match in result.skill_matches
        ],
        matching_projects=[
            MatchingProjectResponse(
                title=matching_project.title,
                relevance_score=matching_project.relevance_score,
                reason=matching_project.reason,
            )
            for matching_project in result.matching_projects
        ],
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        resume_improvements=[
            ResumeImprovementResponse(
                section=resume_improvement.section,
                recommendation=resume_improvement.recommendation,
                priority=resume_improvement.priority,
            )
            for resume_improvement in result.resume_improvements
        ],
        job_preparation_id=job_preparation.id,
    )
