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

from app.models.career_conversation import (
    ConversationExchange,
    ConversationQuestion,
    ConversationSessionState,
    ConversationSessionStatus,
)
from app.models.resume_analysis import ResumeAnalysisResult


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
    ) -> None:
        self.session_id = session_id
        self.resume = resume
        self.job_description = job_description
        self.resume_analysis = resume_analysis
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
    ) -> "ConversationSession":
        """Construct a fresh, in-progress session with a newly generated ID."""
        return cls(
            session_id=str(uuid.uuid4()),
            resume=resume,
            job_description=job_description,
            resume_analysis=resume_analysis,
        )

    @property
    def turn_count(self) -> int:
        """Number of completed topic/question/answer exchanges so far."""
        return len(self.history)

    def set_current_question(self, question: ConversationQuestion) -> None:
        """Open a new question, awaiting an answer."""
        self.current_question = question

    def record_answer(self, answer: str) -> None:
        """Move the current open question, plus `answer`, into history.

        Raises `ValueError` if there is no open question to answer — a
        programming error in the caller (the workflow), not a condition
        that should ever reach here from a well-formed request, since the
        endpoint rejects answers against a session with no open question
        (already complete) before calling the workflow.
        """
        if self.current_question is None:
            raise ValueError("No open question to answer.")
        self.history.append(
            ConversationExchange(
                topic=self.current_question.topic,
                question=self.current_question.question,
                answer=answer,
            )
        )
        self.current_question = None

    def complete(self, reason: str) -> None:
        """Mark the session complete with the given reason, closing any open question."""
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
