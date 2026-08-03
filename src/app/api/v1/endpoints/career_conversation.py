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
from app.gateways.llm.factory import build_llm_gateway
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

    Mirrors `analyze.py`'s `get_resume_analysis_workflow` exactly: the
    gateway is a provider chain built by `build_llm_gateway` from
    `settings` (obtained via `Depends(get_settings)`), a new workflow
    instance per request rather than a cached singleton, since every
    gateway is cheap and stateless to construct. See that function's
    docstring for the full reasoning, which applies unchanged here.

    Note for local/dev use: `MockGateway.generate_structured` builds a
    generic, type-driven placeholder for *any* response model (see its
    own docstring) — for `ConversationTurnDecision`, whose optional
    fields have no domain-aware placeholder, that produces
    `should_stop=False` with all four next-turn fields `null`, which
    `CareerConversationWorkflow` correctly rejects as inconsistent. This
    is an inherent consequence of `MockGateway` staying generic and
    domain-blind (a property worth preserving, not special-casing away)
    rather than a bug in either class: exercising this endpoint's happy
    path — locally or in tests — requires a real provider ahead of
    `"mock"` in the chain, or a dedicated test double, not `"mock"` alone.
    """
    return CareerConversationWorkflow(
        prompt_builder=CareerConversationPromptBuilder(),
        gateway=build_llm_gateway(settings),
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
                assistant_response=exchange.assistant_response,
            )
            for exchange in session.history
        ],
        current_question=(
            ConversationQuestionResponse(
                topic=current_question.topic,
                question=current_question.question,
                evidence_goal=current_question.evidence_goal,
                estimated_impact=current_question.estimated_impact,
                assistant_response=current_question.assistant_response,
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

    `404` if `session_id` is unknown; `409` if the session has no open
    question to answer — either because it already completed, or because
    a *concurrent* request for the same session got there first (e.g. a
    client retry racing an original request that's still being processed
    — the original request isn't necessarily slow or stuck, just still
    in flight when the client, having given up waiting, retries).

    The status is checked twice, not once: once before acquiring
    `session.lock` (a fast path — avoids lock contention and an LLM call
    for the common case of a client retrying against an
    already-known-complete session), and once more *inside* the lock,
    immediately before calling the workflow. That second check is the one
    that actually matters for correctness: two concurrent requests can
    both pass the first check (neither has completed the session yet),
    then both queue on the lock. Without the in-lock recheck, the second
    request to acquire the lock would call the workflow against a session
    the first request just finished mutating — e.g. `current_question` is
    now `None` because the first request's turn completed the session —
    and `ConversationSession.record_answer` would raise `ValueError`,
    surfacing as an unhandled 500 instead of a clean 409. This was a real,
    reproduced bug, not a hypothetical one; see the Career Conversation
    race-condition investigation.
    """
    logger.info("career_conversation_answer_received", session_id=session_id)
    start = time.perf_counter()

    session = _get_session_or_404(store, session_id)
    if session.status == ConversationSessionStatus.COMPLETE:
        raise HTTPException(
            status_code=409, detail="This career conversation session has already completed."
        )

    async with session.lock:
        if session.status == ConversationSessionStatus.COMPLETE or session.current_question is None:
            raise HTTPException(
                status_code=409,
                detail="This career conversation session has no open question to answer.",
            )
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
