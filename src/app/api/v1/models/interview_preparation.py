"""Response schema for `POST /v1/job-preparations/{id}/interview-preparation`.

No request body: everything the workflow needs (resume, job description,
role/company, Career Conversation) is already attached to the
`JobPreparation` identified in the URL -- see the endpoint's docstring.
Mirrors `app.models.interview_preparation`'s domain shapes field-for-field,
kept as its own set of types for the same reason `analyze_resume.py`'s
response models are kept separate from `ResumeAnalysisResult` (see that
module's docstring).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemDesignQuestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="A specific, scenario-based system-design question.")
    rationale: str = Field(
        description="Why this question is likely, given the resume and job description."
    )


class CodingQuestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(description="A recognizable problem name or short title.")
    topic: str = Field(description="The underlying pattern/topic.")
    difficulty: str = Field(description="Expected difficulty of this problem.")
    relevance: str = Field(description="Why this problem/pattern is relevant to this role.")


class BehavioralQuestionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="The behavioral question to prepare for.")
    source: str = Field(description="'career_conversation' or 'suggested'.")
    context: str | None = Field(
        description="The candidate's own answer, if source is career_conversation; null otherwise."
    )


class InterviewPreparationResponse(BaseModel):
    """Response body for `POST /v1/job-preparations/{id}/interview-preparation`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_design_questions: list[SystemDesignQuestionResponse] = Field(
        description="Focused system-design questions/topics to prepare for."
    )
    coding_questions: list[CodingQuestionResponse] = Field(
        description="Coding/LeetCode-style problems to prepare for."
    )
    behavioral_questions: list[BehavioralQuestionResponse] = Field(
        description="Behavioral questions, combining Career Conversation exchanges with gap-fills."
    )
    generated_at: datetime = Field(description="When this guide was last generated or enriched.")
    stage: str = Field(
        description=(
            "'initial', 'career_conversation_enriched', or 'tailoring_aligned' -- see "
            "InterviewPreparationStage."
        )
    )
