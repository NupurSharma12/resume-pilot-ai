"""Errors raised by `PersistenceStore` implementations.

A single small family so callers never need to know which concrete
`PersistenceStore` implementation (in-memory today, PostgreSQL later)
produced a given failure — only that a specific integrity rule from the
agreed schema was violated. Mirrors the taxonomy style already used
elsewhere in this codebase (see `app.ingestion.errors`,
`app.tailoring.applier`'s `UnknownSuggestionIdError` et al.).
"""


class PersistenceError(RuntimeError):
    """Base class for all `PersistenceStore` errors. Never raised directly."""


class ResumeNotFoundError(PersistenceError):
    """Raised when a `resume_id` does not reference any stored `Resume`."""


class ResumeVersionNotFoundError(PersistenceError):
    """Raised when a `resume_version_id` does not reference any stored `ResumeVersion`."""


class InvalidResumeVersionSourceError(PersistenceError):
    """Raised when a version's `source` violates the agreed `CHECK` constraint.

    `ResumeVersionSource.ORIGINAL_UPLOAD` may only ever be the first
    version of a resume, and the first version may only ever be
    `ORIGINAL_UPLOAD` — mirroring
    `CHECK((source = 'original_upload') = (version_number = 1))`.
    """


class JobPreparationNotFoundError(PersistenceError):
    """Raised when a `job_preparation_id` does not reference any stored `JobPreparation`."""


class JobPreparationCompletedError(PersistenceError):
    """Raised by `save_job_preparation` when the stored preparation is already completed.

    Once `status` is `JobPreparationStatus.COMPLETED`, a `JobPreparation`
    is read-only history — see the schema review's "history is read-only"
    decision. The one save that *transitions* a preparation into
    `completed` is still allowed (the previously stored record is not yet
    completed at that point); only a save targeting an *already*-completed
    record is rejected.
    """


class InvalidJobPreparationStatusError(PersistenceError):
    """Raised when a save would violate the agreed status/applied-version `CHECK` constraint.

    Mirrors `CHECK(status <> 'completed' OR applied_resume_version_id IS NOT NULL)`:
    a preparation cannot be marked `completed` without an
    `applied_resume_version_id`.
    """
