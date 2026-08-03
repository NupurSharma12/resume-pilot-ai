"""Career Conversation (Evidence Recovery) endpoints: `/v1/career-conversation*`.

Wires HTTP requests to `CareerConversationWorkflow` and to the
process-lifetime `ConversationSessionStore` attached to `app.state` (see
`create_app`). Contains no conversation-generation or stop-condition logic
itself — it only translates between the API schema and the
session/workflow, and constructs the workflow's dependencies, exactly as
`analyze.py` does for `ResumeAnalysisWorkflow`. The one structural
difference from `analyze.py`: this feature needs session state that
outlives a single request, so alongside the per-request workflow, each
route also depends on the shared `ConversationSessionStore` singleton.

Logs request-level metadata (`session_id`, elapsed time, turn count,
status, confidence) at INFO/ERROR — never resume/job-description/question/
answer content; see `CareerConversationWorkflow`'s docstring for the same
policy at the orchestration layer.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.api.v1.models.career_conversation import (
    ConversationExchangeResponse,
    ConversationQuestionResponse,
    ConversationSessionResponse,
    StartConversationRequest,
    SubmitConversationAnswerRequest,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.gateways.llm.gateway import LLMGateway
from app.gateways.llm.gemini_gateway import GeminiGateway
from app.gateways.llm.mock_gateway import MockGateway
from app.models.career_conversation import ConversationSessionStatus
from app.models.resume_analysis import (
    HiringRecommendation,
    MatchingProject,
    OverallAssessment,
    ResumeAnalysisResult,
    ResumeImprovement,
    SkillMatch,
)
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.sessions.conversation_session import ConversationSession, ConversationSessionStore
from app.workflows.career_conversation_workflow import CareerConversationWorkflow

logger = get_logger(__name__)

router = APIRouter()


def get_career_conversation_workflow(
    settings: Settings = Depends(get_settings),
) -> CareerConversationWorkflow:
    """Construct a `CareerConversationWorkflow` wired with its current dependencies.

    Mirrors `analyze.py`'s `get_resume_analysis_workflow` exactly: gateway
    selection based on `settings.llm_provider` (obtained via
    `Depends(get_settings)`, `"mock"`/`"gemini"` handled explicitly, any
    other value raising `ValueError`), a new workflow instance per
    request rather than a cached singleton, since both gateways are cheap
    and stateless to construct. See that function's docstring for the
    full reasoning, which applies unchanged here.

    Note for local/dev use: `MockGateway.generate_structured` builds a
    generic, type-driven placeholder for *any* response model (see its
    own docstring) — for `ConversationTurnDecision`, whose optional
    fields have no domain-aware placeholder, that produces
    `should_stop=False` with all four next-turn fields `null`, which
    `CareerConversationWorkflow` correctly rejects as inconsistent. This
    is an inherent consequence of `MockGateway` staying generic and
    domain-blind (a property worth preserving, not special-casing away)
    rather than a bug in either class: exercising this endpoint's happy
    path — locally or in tests — requires `llm_provider="gemini"` or a
    dedicated test double, not the default mock provider.
    """
    if settings.llm_provider == "mock":
        gateway: LLMGateway = MockGateway()
    elif settings.llm_provider == "gemini":
        gateway = GeminiGateway(settings)
    else:
        logger.error("unknown_llm_provider", llm_provider=settings.llm_provider)
        raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r}")

    return CareerConversationWorkflow(
        prompt_builder=CareerConversationPromptBuilder(),
        gateway=gateway,
    )


def get_conversation_session_store(request: Request) -> ConversationSessionStore:
    """Return the process-lifetime `ConversationSessionStore` attached to `app.state`.

    A `Request`-based dependency (not `Depends(get_settings)`-style
    construction) because this store must be the *same* instance across
    every request for the lifetime of the app — it is created once in
    `create_app` and stashed on `app.state`, the same place
    `app.state.settings` already lives.
    """
    return request.app.state.conversation_session_store


def _to_domain_analysis(response: AnalyzeResumeResponse) -> ResumeAnalysisResult:
    """Map the API's `AnalyzeResumeResponse` onto the domain `ResumeAnalysisResult`.

    Written out field by field, mirroring `analyze.py`'s handler (which
    performs the identical mapping in reverse) rather than passing
    `response.model_dump()` straight into `ResumeAnalysisResult(...)`: the
    two shapes are only *coincidentally* identical today, not implicitly
    coupled, so either can change independently later without the other
    silently breaking.
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


def _to_session_response(session: ConversationSession) -> ConversationSessionResponse:
    """Map a live `ConversationSession` onto the frozen `ConversationSessionResponse`."""
    current_question = session.current_question
    return ConversationSessionResponse(
        session_id=session.session_id,
        status=session.status,
        history=[
            ConversationExchangeResponse(
                topic=exchange.topic,
                question=exchange.question,
                answer=exchange.answer,
            )
            for exchange in session.history
        ],
        current_question=(
            ConversationQuestionResponse(
                topic=current_question.topic,
                question=current_question.question,
                evidence_goal=current_question.evidence_goal,
                estimated_impact=current_question.estimated_impact,
            )
            if current_question is not None
            else None
        ),
        stop_reason=session.stop_reason,
    )


def _get_session_or_404(store: ConversationSessionStore, session_id: str) -> ConversationSession:
    """Look up `session_id` in `store`, raising `404` if it doesn't (or no longer) exist."""
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Career conversation session not found.")
    return session


@router.post("/career-conversation", response_model=ConversationSessionResponse)
async def start_career_conversation(
    payload: StartConversationRequest,
    workflow: CareerConversationWorkflow = Depends(get_career_conversation_workflow),
    store: ConversationSessionStore = Depends(get_conversation_session_store),
) -> ConversationSessionResponse:
    """Create a new Career Conversation session and return its first question.

    Grounds the new session in `payload.resume_analysis` translated to the
    domain model (`_to_domain_analysis`), then runs exactly one
    conversation turn via the workflow before returning — the same
    request that creates a session also returns its opening question, so
    callers never see a session with no question and no stop reason.
    """
    logger.info("career_conversation_start_received")
    start = time.perf_counter()

    resume_analysis = _to_domain_analysis(payload.resume_analysis)
    session = ConversationSession.new(
        resume=payload.resume,
        job_description=payload.job_description,
        resume_analysis=resume_analysis,
    )
    try:
        await workflow.start_conversation(session)
    except Exception as exc:
        logger.error(
            "career_conversation_start_failed",
            session_id=session.session_id,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    store.save(session)

    logger.info(
        "career_conversation_start_completed",
        session_id=session.session_id,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        turn_count=session.turn_count,
        status=session.status,
        confidence=session.last_confidence,
    )
    return _to_session_response(session)


@router.post("/career-conversation/{session_id}/answer", response_model=ConversationSessionResponse)
async def submit_career_conversation_answer(
    session_id: str,
    payload: SubmitConversationAnswerRequest,
    workflow: CareerConversationWorkflow = Depends(get_career_conversation_workflow),
    store: ConversationSessionStore = Depends(get_conversation_session_store),
) -> ConversationSessionResponse:
    """Record an answer to a session's current question and return the next turn (or completion).

    `404` if `session_id` is unknown; `409` if the session has already
    completed (there is no open question to answer) — both are client
    errors caught before the workflow is ever invoked, not conditions the
    workflow itself needs to handle. The per-session lock guards against a
    concurrent duplicate submission for the same session interleaving two
    turns; see `ConversationSession`'s docstring.
    """
    logger.info("career_conversation_answer_received", session_id=session_id)
    start = time.perf_counter()

    session = _get_session_or_404(store, session_id)
    if session.status == ConversationSessionStatus.COMPLETE:
        raise HTTPException(
            status_code=409, detail="This career conversation session has already completed."
        )

    async with session.lock:
        try:
            await workflow.submit_answer(session, payload.answer)
        except Exception as exc:
            logger.error(
                "career_conversation_answer_failed",
                session_id=session_id,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        store.save(session)

    logger.info(
        "career_conversation_answer_completed",
        session_id=session_id,
        elapsed_ms=(time.perf_counter() - start) * 1000,
        turn_count=session.turn_count,
        status=session.status,
        confidence=session.last_confidence,
    )
    return _to_session_response(session)


@router.get("/career-conversation/{session_id}", response_model=ConversationSessionResponse)
async def get_career_conversation(
    session_id: str,
    store: ConversationSessionStore = Depends(get_conversation_session_store),
) -> ConversationSessionResponse:
    """Return a session's current state, unchanged — for refresh/reload-safety.

    Pure read: makes no LLM call and does not mutate the session, so it
    is safe to call repeatedly (e.g. after a client reload) without
    affecting the conversation's progress.
    """
    session = _get_session_or_404(store, session_id)
    logger.info(
        "career_conversation_get",
        session_id=session_id,
        turn_count=session.turn_count,
        status=session.status,
    )
    return _to_session_response(session)
