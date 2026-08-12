"""SQLAlchemy ORM tables for the three frozen PostgreSQL tables.

Field-for-field, constraint-for-constraint the agreed schema from the
Persistence phase's schema review -- see `app.persistence.models` for the
equivalent Pydantic shapes `PostgresPersistenceStore`
(`app.persistence.postgres_store`) maps these rows onto. Named with a `Row` suffix
(`ResumeRow`, not `Resume`) specifically to stay visually distinct from
those Pydantic models at every import site -- this module is the ORM
mapping only, nothing here is returned to application code today.

No relationships (`relationship()`) are declared: nothing in this phase
queries across these tables in Python, only via the three explicit foreign
keys at the SQL level. Adding ORM relationships now would be speculative
for the queries a not-yet-built `PostgresPersistenceStore` will actually
need.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

from app.persistence.db.base import Base


class ResumeRow(Base):
    """`resumes`: logical resume identity. No person/user identity -- see the schema review."""

    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    # `onupdate` is SQLAlchemy-level, not a database trigger: it adds a
    # fresh `func.now()` to the SET clause of any UPDATE this app issues
    # through the ORM/Core for this row. The simplest mechanism that
    # satisfies "updated_at must have a reliable update mechanism"
    # without introducing trigger infrastructure.
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ResumeVersionRow(Base):
    """`resume_versions`: immutable versions of a resume's content."""

    __tablename__ = "resume_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # V1 allowed values: 'original_upload', 'applied' -- see
    # ck_resume_versions_source_allowed_values below. No separate
    # 'tailoring'/'user_edit' values: the current application's one
    # /apply call produces one blended version, which may include both
    # LLM-generated and user-edited text (see the schema review).
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "resume_id", "version_number", name="uq_resume_versions_resume_id_version_number"
        ),
        # `name=` here is the *logical* constraint name only -- Base's
        # naming convention (db/base.py) combines it with the table name
        # to produce the final `ck_resume_versions_...` name seen in the
        # migration/database. A CHECK constraint's SQL text has no
        # column to infer a name from, so SQLAlchemy requires this name
        # to be given explicitly; see NAMING_CONVENTION's "ck" entry.
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint(
            "(source = 'original_upload') = (version_number = 1)",
            name="original_upload_is_version_one",
        ),
        CheckConstraint(
            "source IN ('original_upload', 'applied')",
            name="source_allowed_values",
        ),
    )


class JobPreparationRow(Base):
    """`job_preparations`: the persisted state of one resume + JD preparation journey."""

    __tablename__ = "job_preparations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_resume_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("resume_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    applied_resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="RESTRICT"), nullable=True
    )
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Each mirrors the equivalent field on app.persistence.models.JobPreparation
    # exactly -- see that module's docstring for the two composite JSONB
    # shapes agreed for tailoring_plan/post_apply_analysis.
    #
    # `none_as_null=True` is load-bearing, not cosmetic: SQLAlchemy's JSON/
    # JSONB type defaults to encoding a Python `None` as the JSON literal
    # `null` (a real, non-NULL JSONB value equal to `'null'::jsonb`), not
    # SQL `NULL` -- a well-known SQLAlchemy gotcha. Without this flag, a
    # freshly created JobPreparation (every payload column still logically
    # "not set yet") would store `'null'::jsonb` in each column, which
    # `IS NOT NULL` (used by the checkpoint-consistency CHECK constraints
    # below, and by any future JSONB-column existence query) would
    # incorrectly treat as *present*. `none_as_null=True` makes Python
    # `None` persist as true SQL `NULL`, matching what "no payload yet"
    # actually means -- Python-level reads are unaffected either way
    # (asyncpg decodes both SQL NULL and JSON null back to Python `None`).
    analysis_result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    career_conversation: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    tailoring_plan: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    post_apply_analysis: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    interview_preparation: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    # Five independent checkpoint-completion timestamps -- see
    # app.persistence.models.JobPreparation's docstring for why five, not
    # four, and why each is always written in the same UPDATE as its
    # paired column above. The CHECK constraints below (mirroring
    # ck_job_preparations_completed_requires_applied_version's existing
    # style) enforce at the database level that a timestamp and its
    # payload/FK can never disagree -- see this table's __table_args__.
    initial_analysis_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    career_conversation_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    tailoring_plan_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    post_apply_analysis_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # V1 allowed values: 'draft', 'active', 'completed' -- see
    # ck_job_preparations_status_allowed_values below.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        # See ResumeVersionRow's __table_args__ for why `name=` is the
        # logical suffix only, not the fully qualified constraint name.
        CheckConstraint(
            "status <> 'completed' OR applied_resume_version_id IS NOT NULL",
            name="completed_requires_applied_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'completed')",
            name="status_allowed_values",
        ),
        # Checkpoint consistency: a completion timestamp exists if and
        # only if its corresponding durable payload/FK does. See
        # app.persistence.models.JobPreparation's docstring.
        CheckConstraint(
            "(analysis_result IS NOT NULL) = (initial_analysis_completed_at IS NOT NULL)",
            name="initial_analysis_checkpoint_consistent",
        ),
        CheckConstraint(
            "(career_conversation IS NOT NULL) = (career_conversation_completed_at IS NOT NULL)",
            name="career_conversation_checkpoint_consistent",
        ),
        CheckConstraint(
            "(tailoring_plan IS NOT NULL) = (tailoring_plan_completed_at IS NOT NULL)",
            name="tailoring_plan_checkpoint_consistent",
        ),
        CheckConstraint(
            "(applied_resume_version_id IS NOT NULL) = (applied_at IS NOT NULL)",
            name="applied_checkpoint_consistent",
        ),
        CheckConstraint(
            "(post_apply_analysis IS NOT NULL) = (post_apply_analysis_completed_at IS NOT NULL)",
            name="post_apply_analysis_checkpoint_consistent",
        ),
        Index("ix_job_preparations_source_resume_version_id", "source_resume_version_id"),
        Index("ix_job_preparations_applied_resume_version_id", "applied_resume_version_id"),
    )
