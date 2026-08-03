"""Domain model: the shape of a Career Conversation (Evidence Recovery) session.

A career conversation is a recruiter-style, turn-by-turn dialogue that
reasons about the single biggest remaining evidence gap between a resume
and a job description, and asks one conversational question at a time to
try to recover it. These models describe the data each turn produces and
the state a session accumulates — they contain no logic for *how* a turn
is generated (that lives in the prompt builder) or *when* a conversation
should stop (that lives in the workflow, per its docstring).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EstimatedImpact(StrEnum):
    """How much recovering a given piece of evidence would strengthen the resume's fit."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConversationSessionStatus(StrEnum):
    """Lifecycle state of a career conversation session."""

    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class ConversationTurnDecision(BaseModel):
    """Structured output the LLM returns for a single conversation turn.

    This is the exact type passed to `LLMGateway.generate_structured` as
    `response_model`, so its fields and descriptions are also what shapes
    the JSON schema Gemini is asked to conform to — see
    `CareerConversationPromptBuilder`.

    `should_stop` and the four "next turn" fields (`topic`,
    `evidence_goal`, `estimated_impact`, `question`) are mutually
    exclusive in a healthy response: stopping means there is no next
    question, continuing means all four are present. This model does not
    enforce that itself (Pydantic has no way to make `str | None` fields
    conditionally required based on a sibling field without a
    `model_validator`, and per the workflow's explicit responsibility,
    that cross-field consistency check belongs to
    `CareerConversationWorkflow`, not silently buried in the model layer —
    see its docstring). This model only validates each field in
    isolation (e.g. `confidence`'s range).

    `assistant_response` is *not* part of that should_stop/question
    invariant, but is only ever meaningful alongside a next question —
    answering a technical/clarifying question the candidate asked back, or
    acknowledging a correction to something assumed earlier, both read
    naturally as a reply that *precedes* the next question, never as a
    substitute for one. The workflow only attaches it to the next
    question when continuing; a value supplied alongside a stop decision
    is intentionally not surfaced anywhere (there is no next question for
    it to precede), so the prompt instructs the model to leave it null
    when stopping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence: int = Field(
        ge=0,
        le=100,
        description=(
            "The model's own confidence (0-100) that enough high-impact evidence has "
            "been recovered to stop the conversation."
        ),
    )
    should_stop: bool = Field(
        description="Whether the model judges the conversation should end after this turn."
    )
    stop_reason: str | None = Field(
        default=None,
        description="Why the conversation should stop, if `should_stop` is true; null otherwise.",
    )
    topic: str | None = Field(
        default=None,
        description=(
            "A short label for the single biggest remaining evidence gap this turn "
            "targets, if continuing; null if stopping."
        ),
    )
    evidence_goal: str | None = Field(
        default=None,
        description=(
            "What specific evidence this question is trying to recover, and why it "
            "matters for this job description, if continuing; null if stopping."
        ),
    )
    estimated_impact: EstimatedImpact | None = Field(
        default=None,
        description=(
            "How much recovering this evidence would strengthen the resume's fit for "
            "this job description, if continuing; null if stopping."
        ),
    )
    question: str | None = Field(
        default=None,
        description=(
            "The single conversational, recruiter-style question to ask next, if "
            "continuing; null if stopping."
        ),
    )
    assistant_response: str | None = Field(
        default=None,
        description=(
            "A brief reply to the candidate's most recent answer — answering a "
            "technical/clarifying question they asked back, or acknowledging a "
            "correction to something assumed earlier — shown before the next question. "
            "Null if stopping, or if the candidate simply answered and no reply is "
            "warranted, which is most turns."
        ),
    )


class ConversationQuestion(BaseModel):
    """The currently open conversational question a session is waiting on an answer for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str = Field(description="Short label for the evidence gap this question targets.")
    question: str = Field(description="The conversational question posed to the candidate.")
    evidence_goal: str = Field(
        description="What specific evidence this question is trying to recover, and why."
    )
    estimated_impact: EstimatedImpact = Field(
        description="How much recovering this evidence would strengthen the resume's fit."
    )
    assistant_response: str | None = Field(
        default=None,
        description=(
            "A reply to the candidate's previous answer — see "
            "ConversationTurnDecision.assistant_response — shown before this question."
        ),
    )


class ConversationExchange(BaseModel):
    """One completed topic/question/answer exchange in a session's history.

    Deliberately narrower than `ConversationQuestion` (no
    `evidence_goal`/`estimated_impact`): once a question has been
    answered, what matters for grounding future turns is what was asked
    and what the candidate said, not the original targeting rationale —
    that rationale did its job when the question was posed.
    `assistant_response` is the exception, kept here too: it's part of
    what was actually said in the conversation (the recruiter's own
    words), not targeting rationale, so it belongs in the transcript same
    as the question and answer do.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str = Field(description="Short label for the evidence gap this exchange targeted.")
    question: str = Field(description="The conversational question that was asked.")
    answer: str = Field(description="The candidate's answer to that question.")
    assistant_response: str | None = Field(
        default=None,
        description="A reply from the recruiter shown before this question, if any.",
    )


class ConversationSessionState(BaseModel):
    """Frozen, public snapshot of a career conversation session's current state.

    Returned by all three Career Conversation endpoints. Deliberately
    distinct from the mutable `ConversationSession` held by
    `ConversationSessionStore` (see `app.sessions.conversation_session`):
    this is a read-only copy handed to callers, so nothing outside the
    workflow can mutate session state by holding a reference to it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(description="Unique identifier for this conversation session.")
    status: ConversationSessionStatus = Field(description="Current lifecycle state of the session.")
    history: list[ConversationExchange] = Field(
        description="Completed topic/question/answer exchanges, in the order they occurred."
    )
    current_question: ConversationQuestion | None = Field(
        description="The open question awaiting an answer; null once the session is complete."
    )
    stop_reason: str | None = Field(
        description="Why the session stopped, once complete; null while still in progress."
    )
