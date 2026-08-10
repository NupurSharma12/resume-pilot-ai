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
    analysis_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    career_conversation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tailoring_plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    post_apply_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interview_preparation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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
        Index("ix_job_preparations_source_resume_version_id", "source_resume_version_id"),
        Index("ix_job_preparations_applied_resume_version_id", "applied_resume_version_id"),
    )
