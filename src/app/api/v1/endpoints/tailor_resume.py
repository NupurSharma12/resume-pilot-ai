"""Tailoring Engine endpoint: `POST /v1/tailor-resume`.

Wires an HTTP request to `TailoringWorkflow` and back, exactly as
`analyze.py` does for `ResumeAnalysisWorkflow`: no pipeline logic of its
own, only translation between the API schema and the workflow's
inputs/outputs, and construction of the workflow's dependencies.

Logs request-level metadata (lengths, provider, elapsed time,
success/failure, and validation-report counts) at INFO/ERROR — never
resume/job-description/evidence/plan/bullet content; see
`TailoringWorkflow`'s docstring for the same policy one layer down.
"""

import time

from fastapi import APIRouter, Depends

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.api.v1.models.career_conversation import ConversationSessionResponse
from app.api.v1.models.tailor_resume import (
    PlannedChangeResponse,
    RejectedBulletResponse,
    TailoredBulletResponse,
    TailoredResumeResponse,
    TailoredSectionResponse,
    TailoringPlanResponse,
    TailorResumeRequest,
    TailorResumeResponse,
    ValidationReportResponse,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.evidence.evidence_store_builder import EvidenceStoreBuilder
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
from app.prompts.resume_rewrite_prompt_builder import ResumeRewritePromptBuilder
from app.prompts.tailoring_planner_prompt_builder import TailoringPlannerPromptBuilder
from app.workflows.tailoring_workflow import TailoringResult, TailoringWorkflow

logger = get_logger(__name__)

router = APIRouter()


def get_tailoring_workflow(settings: Settings = Depends(get_settings)) -> TailoringWorkflow:
    """Construct a `TailoringWorkflow` wired with its current dependencies.

    Mirrors `analyze.py`'s `get_resume_analysis_workflow` and
    `career_conversation.py`'s `get_career_conversation_workflow` exactly:
    the gateway is a provider chain built by `build_llm_gateway` from
    `settings`, and a new workflow instance is constructed per request
    rather than cached, since every collaborator here is cheap and
    stateless to construct.
    """
    return TailoringWorkflow(
        evidence_store_builder=EvidenceStoreBuilder(),
        planner_prompt_builder=TailoringPlannerPromptBuilder(),
        rewrite_prompt_builder=ResumeRewritePromptBuilder(),
        gateway=build_llm_gateway(settings),
    )


def _to_domain_analysis(response: AnalyzeResumeResponse) -> ResumeAnalysisResult:
    """Map the API's `AnalyzeResumeResponse` onto the domain `ResumeAnalysisResult`.

    Written out field by field, matching `career_conversation.py`'s
    `_to_domain_analysis` (duplicated here rather than imported from that
    module — see this module's docstring on why the API/domain split
    stays independent per endpoint, not just per feature).
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
    """Map the API's `ConversationSessionResponse.history` onto domain `ConversationExchange`s.

    Only `history` (completed exchanges) is used — `current_question`,
    if any, has no answer yet and so is not usable evidence.
    """
    return [
        ConversationExchange(
            topic=exchange.topic,
            question=exchange.question,
            answer=exchange.answer,
            assistant_response=exchange.assistant_response,
        )
        for exchange in session.history
    ]


def _to_response(result: TailoringResult) -> TailorResumeResponse:
    """Map the workflow's `TailoringResult` onto the API's `TailorResumeResponse`.

    Written out field by field, matching every other endpoint's mapping
    convention. `result.evidence_store` is deliberately not mapped to
    anything here — see `tailor_resume.py`'s module docstring on why it
    stays internal.
    """
    return TailorResumeResponse(
        tailored_resume=TailoredResumeResponse(
            sections=[
                TailoredSectionResponse(
                    heading=section.heading,
                    bullets=[
                        TailoredBulletResponse(
                            text=bullet.text,
                            supporting_evidence_ids=bullet.supporting_evidence_ids,
                        )
                        for bullet in section.bullets
                    ],
                )
                for section in result.tailored_resume.sections
            ]
        ),
        tailoring_plan=TailoringPlanResponse(
            changes=[
                PlannedChangeResponse(
                    section=change.section,
                    action=change.action,
                    reason=change.reason,
                    evidence_ids=change.evidence_ids,
                )
                for change in result.tailoring_plan.changes
            ]
        ),
        validation_report=ValidationReportResponse(
            total_bullets=result.validation_report.total_bullets,
            accepted_count=result.validation_report.accepted_count,
            rejected_count=result.validation_report.rejected_count,
            rejected_bullets=[
                RejectedBulletResponse(
                    section=rejected.section, text=rejected.text, reason=rejected.reason
                )
                for rejected in result.validation_report.rejected_bullets
            ],
            passed=result.validation_report.passed,
        ),
    )


@router.post("/tailor-resume", response_model=TailorResumeResponse)
async def tailor_resume(
    payload: TailorResumeRequest,
    workflow: TailoringWorkflow = Depends(get_tailoring_workflow),
    settings: Settings = Depends(get_settings),
) -> TailorResumeResponse:
    """Run the Tailoring Engine pipeline and return the resume, plan, and validation report.

    The handler does exactly three things: translate the request's API
    models into domain inputs, call the injected workflow, and map its
    `TailoringResult` onto the API's `TailorResumeResponse` shape — the
    same three-step shape `analyze_resume`/`start_career_conversation`
    already follow. On failure, the caught exception is logged once here
    and re-raised unchanged via a bare `raise`, so FastAPI's default error
    handling is completely unaffected — matching both existing endpoints.
    """
    logger.info(
        "tailor_resume_request_received",
        resume_length=len(payload.resume),
        job_description_length=len(payload.job_description),
        conversation_turn_count=len(payload.career_conversation.history),
        provider=settings.primary_provider,
    )
    start = time.perf_counter()
    try:
        result = await workflow.tailor(
            resume=payload.resume,
            job_description=payload.job_description,
            resume_analysis=_to_domain_analysis(payload.resume_analysis),
            conversation_history=_to_domain_history(payload.career_conversation),
        )
    except Exception as exc:
        logger.error(
            "tailor_resume_request_failed",
            provider=settings.primary_provider,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    logger.info(
        "tailor_resume_request_completed",
        provider=settings.primary_provider,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        change_count=len(result.tailoring_plan.changes),
        accepted_bullet_count=result.validation_report.accepted_count,
        rejected_bullet_count=result.validation_report.rejected_count,
    )
    return _to_response(result)
