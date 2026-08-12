"""Interview Preparation endpoint: `POST /v1/job-preparations/{id}/interview-preparation`.

No request body: this endpoint loads everything it needs (resume, job
description, role/company, Career Conversation, tailoring decisions) from
the already-persisted `JobPreparation` identified in the URL, exactly the
way the History endpoints already read from it
(`job_preparation_history.py`). One endpoint serves the entire three-stage
Interview Preparation lifecycle (see
`app.workflows.interview_preparation_workflow`'s docstring for the full
state machine this implements) rather than one endpoint per stage --
every call inspects what's already persisted (does an
`interview_preparation` guide already exist? has the Career Conversation
completed? has a tailored resume been applied?) and performs exactly the
incremental work that context newly justifies:

- No guide yet: one full `generate()` call grounded in whatever context
  currently exists (resume + job description alone, immediately after
  Resume Analysis; already richer if Interview Preparation happens to be
  opened for the first time only after Career Conversation/tailoring have
  already completed -- see `_initial_stage_for`).
- A guide exists, still `INITIAL`, and the Career Conversation has since
  completed: fold it in deterministically, zero LLM calls (Stage 2).
- A tailored resume has since been applied (regardless of the guide's
  current stage -- an explicit "Generate"/"Update" click after a *new*
  apply should reflect the resume as it now stands): one LLM call scoped
  to technical questions only (Stage 3).

Always persists via `record_interview_preparation` against the same
`job_preparation_id` -- this never creates a second `JobPreparation` and
never introduces a new checkpoint/table.
"""

import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.models.interview_preparation import (
    BehavioralQuestionResponse,
    CodingQuestionResponse,
    InterviewPreparationResponse,
    SystemDesignQuestionResponse,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.gateways.llm.factory import build_llm_gateway
from app.models.career_conversation import ConversationExchange
from app.models.interview_preparation import InterviewPreparationResult, InterviewPreparationStage
from app.orchestration.job_preparation_persistence import record_interview_preparation
from app.persistence.dependencies import get_persistence_store
from app.persistence.errors import JobPreparationCompletedError, JobPreparationNotFoundError
from app.persistence.store import PersistenceStore
from app.prompts.interview_preparation_prompt_builder import InterviewPreparationPromptBuilder
from app.workflows.interview_preparation_workflow import InterviewPreparationWorkflow

logger = get_logger(__name__)

router = APIRouter()


def get_interview_preparation_workflow(
    settings: Settings = Depends(get_settings),
) -> InterviewPreparationWorkflow:
    """Construct an `InterviewPreparationWorkflow`, mirroring `analyze.py`'s own provider."""
    return InterviewPreparationWorkflow(
        prompt_builder=InterviewPreparationPromptBuilder(),
        gateway=build_llm_gateway(settings),
    )


def _career_conversation_exchanges(career_conversation: dict | None) -> list[ConversationExchange]:
    """Extract the completed Career Conversation's exchanges, or an empty list if none exist yet.

    `career_conversation` is `JobPreparation.career_conversation` -- the
    exact `ConversationSessionResponse.model_dump(mode="json")` payload
    `record_career_conversation` stores (see `career_conversation.py`'s
    `_persist_if_complete`), so `history` is always a list of
    `{topic, question, answer, assistant_response}` dicts when present.
    """
    if not career_conversation:
        return []
    return [
        ConversationExchange(
            topic=exchange["topic"],
            question=exchange["question"],
            answer=exchange["answer"],
            assistant_response=exchange.get("assistant_response"),
        )
        for exchange in career_conversation.get("history", [])
    ]


def _tailoring_summary(tailoring_plan: dict | None) -> str:
    """Best-effort digest of why the applied resume changed, for Stage 3's prompt.

    `tailoring_plan` is `JobPreparation.tailoring_plan` --
    `{'generated_plan': {'suggestions': [...]}, 'selection':
    {'selected_suggestion_ids': [...], ...}}` (see
    `record_generated_tailoring_plan`/`record_applied_tailoring_selection`).
    Only the *selected* suggestions' `reason` text is included -- an
    unselected suggestion was never part of what the candidate actually
    submitted. Returns an empty string (not an error) for any missing or
    unexpected shape -- this is a grounding nicety for the prompt, not a
    contract either side depends on; `enrich_with_tailoring` already has
    the applied resume text itself as its primary grounding either way.
    """
    if not tailoring_plan:
        return ""
    generated_plan = tailoring_plan.get("generated_plan") or {}
    suggestions = generated_plan.get("suggestions") or []
    selection = tailoring_plan.get("selection") or {}
    selected_ids = set(selection.get("selected_suggestion_ids") or [])
    if not selected_ids:
        return ""
    reasons = [
        suggestion["reason"]
        for suggestion in suggestions
        if suggestion.get("suggestion_id") in selected_ids and suggestion.get("reason")
    ]
    return "\n".join(f"- {reason}" for reason in reasons)


def _initial_stage_for(
    *, career_conversation_exchanges: list[ConversationExchange], has_tailoring: bool
) -> InterviewPreparationStage:
    """The stage a brand-new guide lands at, given whatever context already exists.

    Only relevant for the very first `generate()` call for a given
    `JobPreparation` -- if Interview Preparation is opened for the first
    time only after Career Conversation and/or tailoring have already
    completed, that one call is already grounded in the richest available
    context (see `generate_interview_preparation`'s docstring), so there
    is nothing left to enrich incrementally.
    """
    if has_tailoring:
        return InterviewPreparationStage.TAILORING_ALIGNED
    if career_conversation_exchanges:
        return InterviewPreparationStage.CAREER_CONVERSATION_ENRICHED
    return InterviewPreparationStage.INITIAL


def _to_response(result: InterviewPreparationResult) -> InterviewPreparationResponse:
    return InterviewPreparationResponse(
        system_design_questions=[
            SystemDesignQuestionResponse(question=q.question, rationale=q.rationale)
            for q in result.system_design_questions
        ],
        coding_questions=[
            CodingQuestionResponse(
                title=q.title,
                topic=q.topic,
                difficulty=q.difficulty.value,
                relevance=q.relevance,
            )
            for q in result.coding_questions
        ],
        behavioral_questions=[
            BehavioralQuestionResponse(
                question=q.question, source=q.source.value, context=q.context
            )
            for q in result.behavioral_questions
        ],
        generated_at=result.generated_at,
        stage=result.stage.value,
    )


@router.post(
    "/job-preparations/{job_preparation_id}/interview-preparation",
    response_model=InterviewPreparationResponse,
)
async def generate_interview_preparation(
    job_preparation_id: UUID,
    workflow: InterviewPreparationWorkflow = Depends(get_interview_preparation_workflow),
    store: PersistenceStore = Depends(get_persistence_store),
) -> InterviewPreparationResponse:
    """Generate, enrich, or re-align the Interview Preparation guide for `job_preparation_id`.

    `404` if `job_preparation_id` is unknown. `409` if the preparation is
    already `completed` (read-only history -- see
    `PersistenceStore.save_job_preparation`'s docstring). See this
    module's own docstring for the full three-stage state machine; the
    short version: preserves whatever the guide already has that the
    newly available context has no bearing on, and only spends an LLM
    call on the portion that genuinely needs one.
    """
    job_preparation = await store.get_job_preparation(job_preparation_id)
    if job_preparation is None:
        raise HTTPException(status_code=404, detail="Job preparation not found.")

    resume_version_id = (
        job_preparation.applied_resume_version_id or job_preparation.source_resume_version_id
    )
    resume_version = await store.get_resume_version(resume_version_id)
    assert resume_version is not None  # every JobPreparation's resume versions always exist

    career_conversation_exchanges = _career_conversation_exchanges(
        job_preparation.career_conversation
    )
    has_tailoring = job_preparation.applied_resume_version_id is not None
    has_existing_guide = job_preparation.interview_preparation is not None

    logger.info(
        "generate_interview_preparation_received",
        job_preparation_id=str(job_preparation_id),
        has_existing_guide=has_existing_guide,
        has_career_conversation=bool(career_conversation_exchanges),
        has_tailoring=has_tailoring,
    )
    start = time.perf_counter()
    try:
        if not has_existing_guide:
            # Stage 1 (or a later stage's context, already available on
            # this very first call -- see `_initial_stage_for`): one full
            # generation call, already grounded in the applied resume
            # when one exists (`resume_version_id` above prefers it), so
            # there is no need to *also* run Stage 3's dedicated
            # technical-realignment call immediately afterward.
            result = await workflow.generate(
                resume=resume_version.content,
                job_description=job_preparation.job_description,
                job_title=job_preparation.job_title,
                company=job_preparation.company,
                career_conversation_exchanges=career_conversation_exchanges,
            )
            result = result.model_copy(
                update={
                    "stage": _initial_stage_for(
                        career_conversation_exchanges=career_conversation_exchanges,
                        has_tailoring=has_tailoring,
                    )
                }
            )
        else:
            result = InterviewPreparationResult.model_validate(
                job_preparation.interview_preparation
            )
            if career_conversation_exchanges and result.stage == InterviewPreparationStage.INITIAL:
                result = workflow.enrich_with_career_conversation(
                    result, career_conversation_exchanges
                )
            if has_tailoring:
                result = await workflow.enrich_with_tailoring(
                    result,
                    resume=resume_version.content,
                    job_description=job_preparation.job_description,
                    job_title=job_preparation.job_title,
                    company=job_preparation.company,
                    tailoring_summary=_tailoring_summary(job_preparation.tailoring_plan),
                )
    except Exception as exc:
        logger.error(
            "generate_interview_preparation_failed",
            job_preparation_id=str(job_preparation_id),
            elapsed_ms=(time.perf_counter() - start) * 1000,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    try:
        await record_interview_preparation(
            store, job_preparation_id, result.model_dump(mode="json")
        )
    except JobPreparationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobPreparationCompletedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info(
        "generate_interview_preparation_completed",
        job_preparation_id=str(job_preparation_id),
        elapsed_ms=(time.perf_counter() - start) * 1000,
        stage=result.stage.value,
        system_design_count=len(result.system_design_questions),
        coding_count=len(result.coding_questions),
        behavioral_count=len(result.behavioral_questions),
    )
    return _to_response(result)
