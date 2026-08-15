"""Thin orchestration: wires the real resume/job-preparation workflow to `PersistenceStore`.

Not a service framework — five plain `async def` functions, one per
durable-write workflow boundary (see docs/persistent-backend-workflow-state.md's
"Phase 3" section), each taking the already-built `PersistenceStore` plus
whatever plain values that boundary produces, and returning the updated
`JobPreparation`. No base class, no generic repository, no business logic
duplicated from the workflows that produce these values — this module only
sequences `PersistenceStore` calls and translates `JobPreparation`'s
read-modify-write shape into one call per boundary. API endpoints
(`app.api.v1.endpoints.*`) call these directly; the LLM workflows
themselves stay entirely unaware that persistence exists, unchanged.

Every function that operates on an *existing* `JobPreparation` takes its
`job_preparation_id` and raises `app.persistence.errors.JobPreparationNotFoundError`
(via `_require_job_preparation`) if it doesn't exist — the same
`PersistenceError` `PersistenceStore.save_job_preparation` itself would
raise, so callers translate it to HTTP exactly once, the same way
`JobPreparationNotFoundError`/`JobPreparationCompletedError` are already
handled at the API layer elsewhere (see `_get_stored_plan_or_404`'s
sibling pattern in `tailoring_suggestions.py`). No new error type is
introduced here.

PLACEHOLDER DATA: neither a `Resume.name` nor a `JobPreparation.job_title`
has any real source in the application today — the frontend collects raw
resume text and a raw job-description blob, never a candidate name or a
target job title (see this module's `_label_from_text`). Both columns are
`NOT NULL` in the frozen schema, so `start_job_preparation` derives a
short, human-readable placeholder from the first non-empty line of the
relevant text when no explicit value is given. This is flagged, not
hidden: it is a real, currently-unclosed gap in the product (there is
nowhere in the UI to enter a job title), not a persistence-layer defect.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.persistence.errors import JobPreparationNotFoundError
from app.persistence.models import JobPreparation, JobPreparationStatus, ResumeVersionSource
from app.persistence.store import PersistenceStore

_MAX_LABEL_LENGTH = 255


def _label_from_text(text: str, *, fallback: str) -> str:
    """Derive a short, human-readable label from `text`'s first non-empty line.

    See this module's docstring ("PLACEHOLDER DATA") for why this exists:
    there is no real candidate-name or job-title source anywhere in the
    application yet. Truncated to fit the `VARCHAR(255)` columns this
    feeds (`resumes.name`, `job_preparations.job_title`) exactly at the
    character boundary, not sentence/word-aware — good enough for a
    placeholder label, not a content-summarization feature.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_MAX_LABEL_LENGTH]
    return fallback


async def _require_job_preparation(
    store: PersistenceStore, job_preparation_id: UUID
) -> JobPreparation:
    """Return the current `JobPreparation` for `job_preparation_id`, or raise if unknown.

    Every other function in this module reads-then-writes through this
    helper, mirroring `PersistenceStore.save_job_preparation`'s own
    documented read-modify-write convention.
    """
    current = await store.get_job_preparation(job_preparation_id)
    if current is None:
        raise JobPreparationNotFoundError(f"No job preparation with id {job_preparation_id!r}.")
    return current


async def start_job_preparation(
    store: PersistenceStore,
    *,
    resume_text: str,
    job_description: str,
    analysis_result: dict,
    job_title: str | None = None,
    company: str | None = None,
    include_in_history: bool = True,
) -> JobPreparation:
    """Boundaries A + B + C: record a new resume upload, job preparation, and its analysis.

    All three happen in this one function because they happen in this
    one request in the real application — `POST /v1/analyze` is the
    first (and, for boundary A/B, only) point resume text and a job
    description arrive at the backend together (see this module's own
    callers). Always creates a brand-new `Resume` — this function never
    attempts to match an uploaded resume against a prior one (by
    filename, content, or anything else): "every unrelated new uploaded
    resume is a new Resume" is a product rule, not a limitation to work
    around here.

    Transitions the freshly created `JobPreparation` from `draft` (set by
    `create_job_preparation`) to `active` in the same call that attaches
    `analysis_result` — `draft` on its own is not otherwise observable by
    any caller of this function.

    `include_in_history` defaults to `True` (every real user flow) and is
    threaded straight through to `create_job_preparation` -- see
    `PersistenceStore.create_job_preparation`'s own docstring for who
    passes `False` and why (only automated E2E tests, via `POST
    /v1/analyze`'s `X-E2E-Test` header).
    """
    resume = await store.create_resume(
        name=_label_from_text(resume_text, fallback="Untitled résumé")
    )
    resume_version = await store.create_resume_version(
        resume.id, content=resume_text, source=ResumeVersionSource.ORIGINAL_UPLOAD
    )
    job_preparation = await store.create_job_preparation(
        source_resume_version_id=resume_version.id,
        job_title=job_title or _label_from_text(job_description, fallback="Untitled role"),
        job_description=job_description,
        company=company,
        include_in_history=include_in_history,
    )
    return await store.save_job_preparation(
        job_preparation.model_copy(
            update={
                "analysis_result": analysis_result,
                "initial_analysis_completed_at": datetime.now(UTC),
                "status": JobPreparationStatus.ACTIVE,
            }
        )
    )


async def record_career_conversation(
    store: PersistenceStore, job_preparation_id: UUID, career_conversation: dict
) -> JobPreparation:
    """Boundary D: persist the completed Career Conversation session's durable copy.

    Called only once the session has actually reached `COMPLETE` (see
    `career_conversation.py`'s `submit_career_conversation_answer`) — an
    in-progress session stays in `ConversationSessionStore` only, exactly
    as before; this function is never called mid-conversation.
    """
    current = await _require_job_preparation(store, job_preparation_id)
    return await store.save_job_preparation(
        current.model_copy(
            update={
                "career_conversation": career_conversation,
                "career_conversation_completed_at": datetime.now(UTC),
            }
        )
    )


async def record_generated_tailoring_plan(
    store: PersistenceStore, job_preparation_id: UUID, generated_plan: dict
) -> JobPreparation:
    """Boundary E (first half): persist the freshly generated candidate suggestion plan.

    `selection` starts `None` — the user hasn't chosen anything yet; see
    `record_applied_tailoring_selection` for where it's filled in. The
    two are deliberately separate calls, since they happen at separate,
    independent workflow boundaries (generate vs. apply).
    """
    current = await _require_job_preparation(store, job_preparation_id)
    return await store.save_job_preparation(
        current.model_copy(
            update={
                "tailoring_plan": {"generated_plan": generated_plan, "selection": None},
                "tailoring_plan_completed_at": datetime.now(UTC),
            }
        )
    )


async def record_applied_tailoring_selection(
    store: PersistenceStore,
    job_preparation_id: UUID,
    *,
    applied_resume_text: str,
    selected_suggestion_ids: list[str],
    edited_texts: dict[str, str],
) -> JobPreparation:
    """Boundary E (second half) + F: record the user's choices and the one applied version.

    The "Tailored Resume" checkpoint. Delegates entirely to
    `PersistenceStore.apply_resume_version` rather than a
    create-then-save sequence here: creating the new `ResumeVersion`
    (`source=applied` — the current application's one blended `/apply`
    result, never a separate tailoring-only/user-edit-only pair, see
    `ResumeVersionSource`'s docstring) and updating
    `applied_resume_version_id`/`applied_at`/`tailoring_plan.selection`
    must succeed or fail together -- see the Job Preparation Checkpoints
    design review's atomicity analysis for why this is the one boundary
    that needs store-level atomicity rather than two independent
    orchestration-level calls. `generated_plan` is preserved by the store
    method; only `selection` changes here.

    Each call to this function (e.g. each phase of a phased apply, or a
    later re-apply after more suggestions are picked) creates its own new
    `ResumeVersion` and moves `applied_resume_version_id` to point at it
    — there is no de-duplication against a repeated/retried call with an
    identical selection (see this module's own docstring and the Phase 3
    report's "idempotency" section for why that is a deliberate,
    documented non-goal here, not an oversight).
    """
    return await store.apply_resume_version(
        job_preparation_id,
        content=applied_resume_text,
        selected_suggestion_ids=selected_suggestion_ids,
        edited_texts=edited_texts,
    )


async def record_interview_preparation(
    store: PersistenceStore, job_preparation_id: UUID, interview_preparation: dict
) -> JobPreparation:
    """Persist the generated Interview Preparation guide.

    Deliberately no dedicated checkpoint timestamp (unlike boundaries D-G
    above) -- Interview Preparation is represented entirely by
    `interview_preparation` itself being non-null, per this milestone's
    explicit scope decision, mirroring `JobPreparation.interview_preparation`'s
    own docstring.
    """
    current = await _require_job_preparation(store, job_preparation_id)
    return await store.save_job_preparation(
        current.model_copy(update={"interview_preparation": interview_preparation})
    )


async def record_post_apply_analysis(
    store: PersistenceStore,
    job_preparation_id: UUID,
    *,
    analysis: dict,
    comparison: dict,
) -> JobPreparation:
    """Boundary G: persist the combined post-apply analysis + comparison.

    One JSONB field, deliberately combined (see `JobPreparation.post_apply_analysis`'s
    docstring) rather than a separate comparison table -- `reanalyzed_at`
    is stamped here, at persistence time, not taken from any caller input.
    """
    current = await _require_job_preparation(store, job_preparation_id)
    now = datetime.now(UTC)
    return await store.save_job_preparation(
        current.model_copy(
            update={
                "post_apply_analysis": {
                    "analysis": analysis,
                    "comparison": comparison,
                    "reanalyzed_at": now.isoformat(),
                },
                "post_apply_analysis_completed_at": now,
            }
        )
    )


async def delete_job_preparation(
    store: PersistenceStore, job_preparation_id: UUID
) -> JobPreparation:
    """The user-facing "Delete" action in History: soft-deletes one preparation.

    Thin pass-through to `PersistenceStore.soft_delete_job_preparation` --
    unlike every other function in this module, this doesn't read-then-
    `save_job_preparation`, since soft-delete is its own atomic store
    operation (see that method's docstring for why: it needs its own
    row-level lock, the same reasoning `apply_resume_version` already
    uses). Kept here anyway, rather than called directly from the API
    layer, so every durable write against `JobPreparation` -- including
    this one -- still goes through exactly one module, matching this
    file's own docstring ("API endpoints call these directly; the LLM
    workflows themselves stay entirely unaware that persistence exists").
    Raises `JobPreparationNotFoundError` if `job_preparation_id` was never
    created; idempotent for an already-deleted preparation (see the store
    method's docstring).
    """
    return await store.soft_delete_job_preparation(job_preparation_id)
