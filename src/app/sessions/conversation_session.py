"""Mutable, in-process session state for Career Conversation, plus its store.

Every other stateful thing in this codebase is constructed fresh per
request (see `analyze.py`'s `get_resume_analysis_workflow` docstring on
why). A conversation session is the first exception: it must persist
across the `start -> answer -> answer -> ...` request sequence, so it
needs a single, process-lifetime store rather than per-request
construction. That store is attached once to `app.state` in
`create_app` (mirroring `app.state.settings`) and injected via a FastAPI
dependency, exactly like `get_settings`.

No persistence, no eviction, no cross-process sharing: sessions live only
in this process's memory and are lost on restart. That is an explicit
Sprint-1 scope boundary (see the Career Conversation implementation plan),
not an oversight — a real store (Redis, a database) is required before
this can run behind multiple worker processes or survive a restart.
"""

import asyncio
import uuid
from uuid import UUID

from app.core.logging import get_logger
from app.models.career_conversation import (
    ConversationExchange,
    ConversationQuestion,
    ConversationSessionState,
    ConversationSessionStatus,
)
from app.models.resume_analysis import ResumeAnalysisResult

logger = get_logger(__name__)


class ConversationSession:
    """Live, mutable state for one Career Conversation session.

    Holds the resume/job-description/analysis context every turn's prompt
    is grounded in, plus the growing exchange history — mutated in place
    by `CareerConversationWorkflow` as the conversation progresses. Kept
    distinct from `ConversationSessionState` (see
    `app.models.career_conversation`): that is the frozen, public snapshot
    handed to API callers; this is the private, mutable object the store
    holds, so nothing outside the workflow can mutate a session merely by
    holding a reference to a response it received.

    `last_confidence` is tracked but deliberately not part of
    `ConversationSessionState` — the Career Conversation session's public
    fields (per its spec) are `session_id`, history, current
    topic/question, status, and stop reason; confidence is an internal
    signal used to decide whether to stop (see the workflow) and to log,
    not a field callers are meant to consume.

    A per-session `asyncio.Lock` guards the mutate-then-persist sequence
    in `CareerConversationWorkflow` against a double-submit (e.g. a
    retried or double-clicked "answer" request) interleaving two
    in-flight turns for the same session and corrupting its history.
    """

    def __init__(
        self,
        session_id: str,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        job_preparation_id: UUID | None = None,
    ) -> None:
        self.session_id = session_id
        self.resume = resume
        self.job_description = job_description
        self.resume_analysis = resume_analysis
        # The durable JobPreparation this session's eventual completed
        # history should be recorded against, if the client that started
        # it supplied one (see app.orchestration.job_preparation_persistence
        # and StartConversationRequest.job_preparation_id) -- optional,
        # and never re-sent by the client on /answer since it's carried
        # here instead, the same way job_description already is.
        self.job_preparation_id = job_preparation_id
        self.history: list[ConversationExchange] = []
        self.current_question: ConversationQuestion | None = None
        self.status = ConversationSessionStatus.IN_PROGRESS
        self.stop_reason: str | None = None
        self.last_confidence: int | None = None
        self.lock = asyncio.Lock()

    @classmethod
    def new(
        cls,
        resume: str,
        job_description: str,
        resume_analysis: ResumeAnalysisResult,
        job_preparation_id: UUID | None = None,
    ) -> "ConversationSession":
        """Construct a fresh, in-progress session with a newly generated ID."""
        return cls(
            session_id=str(uuid.uuid4()),
            resume=resume,
            job_description=job_description,
            resume_analysis=resume_analysis,
            job_preparation_id=job_preparation_id,
        )

    @property
    def turn_count(self) -> int:
        """Number of completed topic/question/answer exchanges so far."""
        return len(self.history)

    def set_current_question(self, question: ConversationQuestion) -> None:
        """Open a new question, awaiting an answer.

        Logs every mutation of `current_question` (this method,
        `record_answer`, and `complete`) at INFO with `session_id`,
        `turn_count`, and only a *boolean* signal of what changed — never
        the topic, question, or answer text, per the no-content-logging
        policy — so the exact sequence of sets/clears is traceable from
        logs alone when diagnosing a concurrency issue like the one this
        logging was added for (see `submit_career_conversation_answer`'s
        docstring).
        """
        logger.info(
            "current_question_set",
            session_id=self.session_id,
            turn_count=self.turn_count,
            replaced_open_question=self.current_question is not None,
        )
        self.current_question = question

    def record_answer(self, answer: str) -> None:
        """Move the current open question, plus `answer`, into history.

        Raises `ValueError` if there is no open question to answer. This
        should be unreachable from a well-formed, single request — the
        endpoint checks `current_question is not None` *inside* its
        per-session lock immediately before calling this — but a second,
        concurrent request for the same session (e.g. a client retry
        racing an original request that's still being processed) can
        still reach here if that endpoint-level guard is ever weakened or
        bypassed, so this stays as a last-resort invariant rather than
        being removed now that the endpoint also guards against it.
        """
        if self.current_question is None:
            logger.error(
                "record_answer_rejected_no_open_question",
                session_id=self.session_id,
                turn_count=self.turn_count,
                status=self.status,
            )
            raise ValueError("No open question to answer.")
        logger.info(
            "current_question_cleared_by_answer",
            session_id=self.session_id,
            turn_count=self.turn_count,
        )
        self.history.append(
            ConversationExchange(
                topic=self.current_question.topic,
                question=self.current_question.question,
                answer=answer,
                assistant_response=self.current_question.assistant_response,
            )
        )
        self.current_question = None

    def complete(self, reason: str) -> None:
        """Mark the session complete with the given reason, closing any open question."""
        logger.info(
            "current_question_cleared_by_completion",
            session_id=self.session_id,
            turn_count=self.turn_count,
            had_open_question=self.current_question is not None,
        )
        self.status = ConversationSessionStatus.COMPLETE
        self.stop_reason = reason
        self.current_question = None

    def to_state(self) -> ConversationSessionState:
        """Build the frozen, public snapshot of this session's current state."""
        return ConversationSessionState(
            session_id=self.session_id,
            status=self.status,
            history=list(self.history),
            current_question=self.current_question,
            stop_reason=self.stop_reason,
        )


class ConversationSessionStore:
    """In-memory, single-process registry of active Career Conversation sessions.

    A plain `dict` keyed by `session_id`. See this module's docstring for
    why this exists as a process-lifetime singleton rather than
    per-request state, and for the explicit no-persistence scope boundary.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ConversationSession] = {}

    def save(self, session: ConversationSession) -> None:
        """Store (or overwrite) `session` under its own `session_id`."""
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> ConversationSession | None:
        """Return the session for `session_id`, or `None` if it doesn't exist (or never did)."""
        return self._sessions.get(session_id)
