"""Request/response schemas for the Career Conversation endpoints (`/v1/career-conversation*`).

Kept separate from `app.models.career_conversation` (the domain model),
for the same reason `analyze_resume.py` keeps its schemas separate from
`app.models.resume_analysis`: the HTTP contract and the domain model can
then evolve independently. `StartConversationRequest.resume_analysis`
reuses `AnalyzeResumeResponse` directly rather than redefining a third
mirror of the same shape — this is not the domain-model coupling that
separation avoids, since a client starting a conversation is meant to
replay back exactly what `POST /v1/analyze` gave it; nothing about that
relationship has a reason to diverge. `EstimatedImpact`/
`ConversationSessionStatus` are likewise reused directly from the domain
model in response schemas below: they're small, fixed-membership value
enums, not evolving object shapes, so reusing them doesn't create the
kind of coupling this module otherwise avoids.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.models.analyze_resume import AnalyzeResumeResponse
from app.models.career_conversation import ConversationSessionStatus, EstimatedImpact


class StartConversationRequest(BaseModel):
    """Request body for `POST /v1/career-conversation`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resume: str = Field(description="Raw resume text the conversation is grounded in.")
    job_description: str = Field(
        description="Raw job description text the conversation is grounded in."
    )
    resume_analysis: AnalyzeResumeResponse = Field(
        description="The prior resume analysis result, exactly as returned by POST /v1/analyze."
    )


class SubmitConversationAnswerRequest(BaseModel):
    """Request body for `POST /v1/career-conversation/{session_id}/answer`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(description="The candidate's answer to the session's current question.")


class ConversationQuestionResponse(BaseModel):
    """The currently open conversational question, as returned to API callers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str = Field(description="Short label for the evidence gap this question targets.")
    question: str = Field(description="The conversational question posed to the candidate.")
    evidence_goal: str = Field(
        description="What specific evidence this question is trying to recover, and why."
    )
    estimated_impact: EstimatedImpact = Field(
        description="How much recovering this evidence would strengthen the resume's fit."
    )


class ConversationExchangeResponse(BaseModel):
    """One completed topic/question/answer exchange, as returned to API callers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str = Field(description="Short label for the evidence gap this exchange targeted.")
    question: str = Field(description="The conversational question that was asked.")
    answer: str = Field(description="The candidate's answer to that question.")


class ConversationSessionResponse(BaseModel):
    """Response body for all three Career Conversation endpoints: a session's current state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(description="Unique identifier for this conversation session.")
    status: ConversationSessionStatus = Field(description="Current lifecycle state of the session.")
    history: list[ConversationExchangeResponse] = Field(
        description="Completed topic/question/answer exchanges, in the order they occurred."
    )
    current_question: ConversationQuestionResponse | None = Field(
        description="The open question awaiting an answer; null once the session is complete."
    )
    stop_reason: str | None = Field(
        description="Why the session stopped, once complete; null while still in progress."
    )
