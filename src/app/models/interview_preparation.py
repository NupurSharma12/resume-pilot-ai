"""Domain model: the shape of one generated Interview Preparation guide.

`GeneratedInterviewPreparation` is what the LLM itself produces via one
`LLMGateway.generate_structured` call (see
`app.prompts.interview_preparation_prompt_builder` and
`app.workflows.interview_preparation_workflow`): system-design and coding
questions, plus a small number of *additional* behavioral questions for
gaps the Career Conversation didn't already cover. It deliberately does
not include the full behavioral question set -- the Career Conversation
already recovered recruiter-quality behavioral questions grounded in the
candidate's own answers (see `app.models.career_conversation`), and
re-asking the LLM to regenerate them from scratch would both waste a call
and produce questions with no actual answer behind them.

`InterviewPreparationResult` is the final, persisted shape: the
workflow's own `behavioral_questions` field merges the Career
Conversation's exchanges (each tagged `CAREER_CONVERSATION`) with the
LLM's gap-fill questions (each tagged `SUGGESTED`) -- see the workflow's
docstring for exactly how.

`InterviewPreparationResult.stage` tracks how mature the guide is along
the product's three-stage lifecycle (see
`InterviewPreparationWorkflow`'s docstring for the full state machine):
generated from resume + job description alone (`INITIAL`), then
enriched with the completed Career Conversation (`CAREER_CONVERSATION_ENRICHED`,
behavioral questions only), then aligned with the actually applied
resume (`TAILORING_ALIGNED`, system-design/coding questions only). Each
transition only ever touches the portion of the guide that genuinely
depends on the new context -- see `enrich_with_career_conversation`/
`enrich_with_tailoring`. Defaults to `INITIAL` so a guide persisted by
the previous, single-stage implementation (with no `stage` key at all)
still validates.

`GeneratedTechnicalPreparation` is the structured output for the
tailoring-alignment call specifically: system-design and coding
questions only, deliberately excluding any behavioral field, so that
call can never be tempted to touch behavioral content that has nothing
to do with a resume being tailored.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Difficulty(StrEnum):
    """Coding question difficulty, in the conventional LeetCode sense."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class BehavioralQuestionSource(StrEnum):
    """Where one behavioral question came from."""

    CAREER_CONVERSATION = "career_conversation"
    SUGGESTED = "suggested"


class InterviewPreparationStage(StrEnum):
    """How mature a persisted Interview Preparation guide is."""

    INITIAL = "initial"
    CAREER_CONVERSATION_ENRICHED = "career_conversation_enriched"
    TAILORING_ALIGNED = "tailoring_aligned"


class SystemDesignQuestion(BaseModel):
    """One focused system-design question/topic to prepare for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(
        description=(
            "A specific, scenario-based system-design question, e.g. "
            "'Design a distributed document-analysis service...' -- never a generic "
            "definitional question like 'What is scalability?'."
        )
    )
    rationale: str = Field(
        description="Why this question is likely, given the resume, job description, and seniority."
    )


class CodingQuestion(BaseModel):
    """One coding/LeetCode-style problem to prepare for -- direction, not a full statement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(
        description="A recognizable problem name or short title, e.g. 'Merge Intervals'."
    )
    topic: str = Field(description="The underlying pattern/topic, e.g. 'Sliding Window', 'Graphs'.")
    difficulty: Difficulty = Field(description="Expected difficulty of this problem.")
    relevance: str = Field(
        description="Why this problem/pattern is relevant to this specific role."
    )


class BehavioralQuestion(BaseModel):
    """One behavioral question, grounded in the Career Conversation where possible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="The behavioral question to prepare for.")
    source: BehavioralQuestionSource = Field(
        description="Whether this question came from the Career Conversation or was suggested."
    )
    context: str | None = Field(
        description=(
            "The candidate's own answer from the Career Conversation, if this question's "
            "source is CAREER_CONVERSATION; null for a suggested gap-fill question."
        )
    )


class GeneratedInterviewPreparation(BaseModel):
    """The exact structured output the LLM produces for one Interview Preparation call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_design_questions: list[SystemDesignQuestion] = Field(
        description="A focused, non-generic set of system-design questions/topics."
    )
    coding_questions: list[CodingQuestion] = Field(
        description="Approximately 10-15 relevant coding/LeetCode-style problems."
    )
    additional_behavioral_questions: list[str] = Field(
        description=(
            "A small number of additional behavioral questions covering meaningful gaps the "
            "job description raises that the Career Conversation did not already cover. Empty "
            "if the Career Conversation already covers the role's likely behavioral ground."
        )
    )


class GeneratedTechnicalPreparation(BaseModel):
    """The structured output for the tailoring-alignment call: technical questions only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_design_questions: list[SystemDesignQuestion] = Field(
        description="A focused, non-generic set of system-design questions/topics."
    )
    coding_questions: list[CodingQuestion] = Field(
        description="Approximately 10-15 relevant coding/LeetCode-style problems."
    )


class InterviewPreparationResult(BaseModel):
    """The full, persisted Interview Preparation guide for one `JobPreparation`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system_design_questions: list[SystemDesignQuestion] = Field(
        description="Focused system-design questions/topics to prepare for."
    )
    coding_questions: list[CodingQuestion] = Field(
        description="Coding/LeetCode-style problems to prepare for."
    )
    behavioral_questions: list[BehavioralQuestion] = Field(
        description="Behavioral questions, combining Career Conversation exchanges with gap-fills."
    )
    generated_at: datetime = Field(description="When this guide was last generated or enriched.")
    stage: InterviewPreparationStage = Field(
        default=InterviewPreparationStage.INITIAL,
        description="How mature this guide is -- see this module's docstring for the state machine",
    )
