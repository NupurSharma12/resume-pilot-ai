"""Career Conversation workflow: orchestrates one recruiter-style evidence-recovery turn at a time.

`CareerConversationWorkflow` composes a prompt builder and an
`LLMGateway` — the same two collaborators `ResumeAnalysisWorkflow` uses —
into "build prompt, call the gateway for a structured turn decision,
validate it, apply it to the session." Unlike `ResumeAnalysisWorkflow`,
this workflow's output is not a single final result but incremental
mutation of a `ConversationSession` across many calls, since Evidence
Recovery is inherently a multi-turn conversation rather than a
one-shot analysis.

Failure-safety: a session is only ever mutated *after* a next-turn
decision has been successfully obtained and validated (see
`_request_decision` vs. `_apply_decision`). Concretely, `submit_answer`
does not record the candidate's answer into history before asking the
LLM for the next turn — it builds a *prospective* history (existing
history plus the not-yet-committed answer) purely to construct the
prompt, and only calls `session.record_answer` once the resulting
decision is already in hand. This matters because the previous ordering
(record the answer, *then* ask for the next turn) had a real corruption
window: if the second step raised for any reason (a schema-invalid
response, a should_stop/question contract violation, every provider in
the chain failing), the answer was already gone from `current_question`
and irretrievably absorbed into history, but no replacement question had
been set and the session was never marked complete either — it was left
stuck `in_progress` with `current_question = None`, unrecoverable
through the API (every future answer attempt would 409 with "no open
question," and there was no question left to retry against).
Restructuring so nothing is mutated until the LLM call has already
succeeded closes this completely — a failure now leaves the session
byte-for-byte as it was before the call, so the *existing* question is
still there to retry against exactly as if the failed request had never
happened.

Logs each turn's start/completion at INFO and validation/gateway failures
at ERROR — see `_request_decision`'s docstring. Per the no-content-logging
requirement, this module never logs resume text, job description text,
question text, or answer text; only `session_id`, elapsed time, turn
count, status, and confidence are logged.
"""

import time

from pydantic import ValidationError

from app.core.logging import get_logger
from app.gateways.llm.gateway import LLMGateway
from app.models.career_conversation import (
    ConversationExchange,
    ConversationQuestion,
    ConversationTurnDecision,
)
from app.prompts.career_conversation_prompt_builder import CareerConversationPromptBuilder
from app.sessions.conversation_session import ConversationSession

logger = get_logger(__name__)

# Hard, Python-enforced ceiling on how many questions a single conversation
# can ask, independent of what the LLM itself decides — see this module's
# docstring on `_request_decision` for why the LLM's own judgment is never
# trusted alone to terminate the conversation.
MAX_CONVERSATION_TURNS = 8

# If the LLM reports confidence at or above this threshold, the
# conversation is force-stopped even if it set `should_stop=False` for
# this turn — an independent, Python-side stop trigger layered on top of
# the LLM's own `should_stop` signal, not a replacement for it.
STOP_CONFIDENCE_THRESHOLD = 90


class ConversationTurnInconsistentError(RuntimeError):
    """Raised when a `ConversationTurnDecision` violates the should_stop/question invariant.

    A `ValidationError` from `generate_structured` means the LLM's output
    didn't match `ConversationTurnDecision`'s *schema* (wrong types,
    missing required fields). This is a different failure: the output was
    perfectly valid Pydantic, but violates a *cross-field business rule*
    that no single field's own validation can express — `should_stop=True`
    with a non-null `question`, or `should_stop=False` with any of the
    next-turn fields missing. Modeling it as its own exception (rather
    than reusing `ValidationError` or a bare `ValueError`) makes this
    specific contract violation identifiable to callers and log readers,
    distinct from a schema mismatch. Raised from `_request_decision`,
    before any session mutation — see this module's docstring.
    """


class CareerConversationWorkflow:
    """Orchestrates Career Conversation turns by composing a prompt builder and gateway.

    Both collaborators are supplied by the caller (constructor injection),
    exactly matching `ResumeAnalysisWorkflow`'s pattern: this class
    depends on `CareerConversationPromptBuilder` and the `LLMGateway`
    abstraction, but owns none of their implementation details.

    This workflow does not depend on `ConversationSessionStore` — it
    receives and mutates a `ConversationSession` object directly and
    leaves the caller (the endpoint) responsible for persisting it. That
    keeps this class focused purely on turn orchestration and the
    should-we-stop decision, with no knowledge of *how* or *whether*
    sessions are stored.
    """

    def __init__(
        self,
        prompt_builder: CareerConversationPromptBuilder,
        gateway: LLMGateway,
    ) -> None:
        """Store the two injected collaborators for use by `start_conversation`/`submit_answer`."""
        self._prompt_builder = prompt_builder
        self._gateway = gateway

    async def start_conversation(self, session: ConversationSession) -> ConversationSession:
        """Generate the first turn for a freshly created, empty session.

        `session` is expected to have no history and no open question yet
        (the caller constructs it via `ConversationSession.new` and this
        is the first thing called on it). Returns the same `session`
        object, mutated in place, for the caller to persist. If the LLM
        call fails, `session` is left exactly as it was passed in (empty,
        unsaved) — the caller's own construction, not anything this
        method did, so there's nothing to roll back.
        """
        start = time.perf_counter()
        decision = await self._request_decision(session, pending_answer=None)
        self._apply_decision(session, decision)
        self._log_turn_completed(session, start)
        return session

    async def submit_answer(self, session: ConversationSession, answer: str) -> ConversationSession:
        """Record an answer to the session's open question, then generate the next turn.

        The answer is only committed to `session.history` (via
        `session.record_answer`) *after* the next turn's decision has
        already been successfully requested and validated — see this
        module's docstring for why: a failure partway through must never
        leave `answer` recorded with no corresponding new question, or
        vice versa. `_request_decision` builds its prompt from a
        *prospective* history (the real history plus this not-yet-recorded
        answer) precisely so it can be called before committing anything.

        The hard turn cap is checked before requesting a decision (using
        `session.turn_count + 1`, i.e. what the turn count *would become*
        once this answer is recorded) so a conversation that's about to
        hit the cap force-completes without spending an LLM call on a
        turn that will never be asked — cheaper and faster, and this
        branch commits the answer immediately since nothing here can fail
        (no I/O, no LLM call).
        """
        if session.current_question is None:
            raise ValueError("No open question to answer.")

        start = time.perf_counter()
        if session.turn_count + 1 >= MAX_CONVERSATION_TURNS:
            session.record_answer(answer)
            session.complete(
                reason=f"Reached the maximum of {MAX_CONVERSATION_TURNS} conversation turns."
            )
            self._log_turn_completed(session, start)
            return session

        decision = await self._request_decision(session, pending_answer=answer)
        # Only reached once `_request_decision` has already succeeded --
        # everything from here on is pure, in-memory mutation that cannot
        # itself fail, so there is no window where a failure could leave
        # the answer recorded without a resulting question (or vice versa).
        session.record_answer(answer)
        self._apply_decision(session, decision)
        self._log_turn_completed(session, start)
        return session

    async def _request_decision(
        self, session: ConversationSession, *, pending_answer: str | None
    ) -> ConversationTurnDecision:
        """Request one turn decision from the LLM. Never mutates `session`.

        When `pending_answer` is given (the `submit_answer` case), the
        prompt is built from `session.history` *plus* one synthetic
        exchange representing the answer being submitted right now — the
        LLM needs to see it to decide the next turn, but it is not
        written into `session.history` here; only the caller, once this
        call has returned successfully, decides whether/how to commit it
        (see `submit_answer`). `pending_answer=None` is the
        `start_conversation` case: no prior question to fold in, history
        is empty by construction.

        Raises `ValidationError` (schema mismatch) or
        `ConversationTurnInconsistentError` (should_stop/question
        contract violation) on a bad decision, or whatever the gateway
        itself raises on a provider failure (e.g.
        `GatewayChainExhaustedError`) — all before touching `session`.

        No prompt text, resume/job-description content, question text, or
        answer text is ever logged — only `session_id`, elapsed time, and
        the error message on failure (a short, provider-agnostic
        classification string — see `GatewayError`'s docstring — never
        provider response bodies or request content).
        """
        logger.info("career_conversation_turn_started", session_id=session.session_id)
        start = time.perf_counter()

        history = session.history
        if pending_answer is not None:
            assert session.current_question is not None
            history = [
                *session.history,
                ConversationExchange(
                    topic=session.current_question.topic,
                    question=session.current_question.question,
                    answer=pending_answer,
                    assistant_response=session.current_question.assistant_response,
                ),
            ]

        request = self._prompt_builder.build(
            resume=session.resume,
            job_description=session.job_description,
            resume_analysis=session.resume_analysis,
            history=history,
        )
        try:
            decision = await self._gateway.generate_structured(request, ConversationTurnDecision)
        except ValidationError as exc:
            logger.error(
                "career_conversation_turn_validation_failed",
                session_id=session.session_id,
                elapsed_ms=(time.perf_counter() - start) * 1000,
                error=str(exc),
            )
            raise

        self._validate_decision(decision)
        return decision

    @staticmethod
    def _apply_decision(session: ConversationSession, decision: ConversationTurnDecision) -> None:
        """Apply an already-validated decision to `session`.

        Pure, in-memory mutation only — no I/O, nothing that can raise
        for a reason related to the decision's content (the only
        exceptions possible here are the `assert`s below, which
        `_validate_decision` has already made unreachable). Always called
        after `_request_decision` has already succeeded, never before.
        """
        session.last_confidence = decision.confidence
        should_stop = decision.should_stop or decision.confidence >= STOP_CONFIDENCE_THRESHOLD
        if should_stop:
            reason = decision.stop_reason or (
                f"Reached the confidence threshold ({decision.confidence} >= "
                f"{STOP_CONFIDENCE_THRESHOLD})."
            )
            session.complete(reason=reason)
        else:
            # `_validate_decision` has already guaranteed these four fields
            # are non-null when `decision.should_stop` is False.
            assert decision.topic is not None
            assert decision.evidence_goal is not None
            assert decision.estimated_impact is not None
            assert decision.question is not None
            session.set_current_question(
                ConversationQuestion(
                    topic=decision.topic,
                    question=decision.question,
                    evidence_goal=decision.evidence_goal,
                    estimated_impact=decision.estimated_impact,
                    assistant_response=decision.assistant_response,
                )
            )

    @staticmethod
    def _log_turn_completed(session: ConversationSession, start: float) -> None:
        logger.info(
            "career_conversation_turn_completed",
            session_id=session.session_id,
            elapsed_ms=(time.perf_counter() - start) * 1000,
            turn_count=session.turn_count,
            status=session.status,
            confidence=session.last_confidence,
        )

    @staticmethod
    def _validate_decision(decision: ConversationTurnDecision) -> None:
        """Enforce the should_stop/question invariant Gemini's output must satisfy.

        Checked explicitly here, in the workflow, rather than as a
        `model_validator` on `ConversationTurnDecision` itself — see that
        model's docstring for why this cross-field business rule belongs
        to this layer rather than the model layer.
        """
        if decision.should_stop:
            if decision.question is not None:
                raise ConversationTurnInconsistentError(
                    "should_stop is true but question is not null."
                )
        else:
            missing = [
                name
                for name, value in (
                    ("topic", decision.topic),
                    ("evidence_goal", decision.evidence_goal),
                    ("estimated_impact", decision.estimated_impact),
                    ("question", decision.question),
                )
                if value is None
            ]
            if missing:
                raise ConversationTurnInconsistentError(
                    f"should_stop is false but required field(s) are null: {', '.join(missing)}."
                )
