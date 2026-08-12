"""Unit tests for the SQLAlchemy table metadata in `app.persistence.db.tables`.

Pure metadata inspection -- no database connection, no Docker, no network.
These assert what `Base.metadata` *describes*, which is exactly what
`alembic revision --autogenerate` reads to produce a migration and what
`alembic upgrade` applies -- so a passing suite here is a strong signal
the frozen schema is correctly expressed in Python, without needing a
live PostgreSQL instance. `test_persistence_db_migration_integration.py`
covers the "does this actually work against real PostgreSQL" question
this file deliberately does not.
"""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TIMESTAMP

from app.persistence.db.base import Base
from app.persistence.db.tables import JobPreparationRow, ResumeRow, ResumeVersionRow


def _check_constraint_texts(table) -> list[str]:
    return [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]


class TestTablesRegisterOnSharedMetadata:
    def test_expected_table_names_are_registered(self) -> None:
        assert set(Base.metadata.tables) == {"resumes", "resume_versions", "job_preparations"}

    def test_row_classes_map_to_the_intended_tables(self) -> None:
        assert ResumeRow.__tablename__ == "resumes"
        assert ResumeVersionRow.__tablename__ == "resume_versions"
        assert JobPreparationRow.__tablename__ == "job_preparations"


class TestResumesTable:
    def test_id_is_a_uuid_primary_key(self) -> None:
        table = Base.metadata.tables["resumes"]
        id_column = table.c.id

        assert id_column.primary_key is True
        assert isinstance(id_column.type, PG_UUID)

    def test_name_is_not_null_varchar_255(self) -> None:
        column = Base.metadata.tables["resumes"].c.name
        assert column.nullable is False
        assert column.type.length == 255

    def test_timestamps_are_timestamptz_not_null_with_now_default(self) -> None:
        table = Base.metadata.tables["resumes"]
        for column_name in ("created_at", "updated_at"):
            column = table.c[column_name]
            assert isinstance(column.type, TIMESTAMP)
            assert column.type.timezone is True
            assert column.nullable is False
            assert column.server_default is not None

    def test_updated_at_has_an_onupdate_mechanism_configured(self) -> None:
        column = Base.metadata.tables["resumes"].c.updated_at
        assert column.onupdate is not None


class TestResumeVersionsTable:
    def test_id_is_a_uuid_primary_key(self) -> None:
        column = Base.metadata.tables["resume_versions"].c.id
        assert column.primary_key is True
        assert isinstance(column.type, PG_UUID)

    def test_required_columns_are_not_null(self) -> None:
        table = Base.metadata.tables["resume_versions"]
        for column_name in ("resume_id", "version_number", "content", "source", "created_at"):
            assert table.c[column_name].nullable is False, column_name

    def test_resume_id_foreign_key_uses_on_delete_restrict(self) -> None:
        table = Base.metadata.tables["resume_versions"]
        fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]

        assert len(fks) == 1
        (fk,) = fks
        assert fk.ondelete == "RESTRICT"
        assert list(fk.elements)[0].column.table.name == "resumes"

    def test_unique_constraint_on_resume_id_and_version_number(self) -> None:
        table = Base.metadata.tables["resume_versions"]
        unique_constraints = [c for c in table.constraints if isinstance(c, UniqueConstraint)]

        assert len(unique_constraints) == 1
        column_names = {c.name for c in unique_constraints[0].columns}
        assert column_names == {"resume_id", "version_number"}

    def test_version_number_positive_check_constraint_exists(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["resume_versions"])
        assert any("version_number > 0" in text for text in texts)

    def test_original_upload_is_version_one_check_constraint_exists(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["resume_versions"])
        assert any("original_upload" in text and "version_number = 1" in text for text in texts)

    def test_source_allowed_values_check_constraint_exists(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["resume_versions"])
        matching = [t for t in texts if "source IN" in t]

        assert len(matching) == 1
        assert "original_upload" in matching[0]
        assert "applied" in matching[0]
        # No separate 'tailoring'/'user_edit' values -- see the schema review.
        assert "tailoring" not in matching[0]
        assert "user_edit" not in matching[0]


class TestJobPreparationsTable:
    def test_id_is_a_uuid_primary_key(self) -> None:
        column = Base.metadata.tables["job_preparations"].c.id
        assert column.primary_key is True
        assert isinstance(column.type, PG_UUID)

    def test_required_columns_are_not_null(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        for column_name in (
            "source_resume_version_id",
            "job_title",
            "job_description",
            "status",
            "created_at",
            "updated_at",
        ):
            assert table.c[column_name].nullable is False, column_name

    def test_applied_resume_version_id_and_company_are_nullable(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        assert table.c.applied_resume_version_id.nullable is True
        assert table.c.company.nullable is True

    def test_jsonb_columns_are_jsonb(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        for column_name in (
            "analysis_result",
            "career_conversation",
            "tailoring_plan",
            "post_apply_analysis",
            "interview_preparation",
        ):
            assert isinstance(table.c[column_name].type, JSONB), column_name

    def test_both_resume_version_foreign_keys_use_on_delete_restrict(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        fks = {
            list(fk.elements)[0].parent.name: fk
            for fk in table.constraints
            if isinstance(fk, ForeignKeyConstraint)
        }

        assert set(fks) == {"source_resume_version_id", "applied_resume_version_id"}
        for fk in fks.values():
            assert fk.ondelete == "RESTRICT"
            assert list(fk.elements)[0].column.table.name == "resume_versions"

    def test_status_allowed_values_check_constraint_exists(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["job_preparations"])
        matching = [t for t in texts if "status IN" in t]

        assert len(matching) == 1
        for value in ("draft", "active", "completed"):
            assert value in matching[0]

    def test_completed_requires_applied_version_check_constraint_exists(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["job_preparations"])
        assert any(
            "completed" in text and "applied_resume_version_id IS NOT NULL" in text
            for text in texts
        )

    def test_both_indexes_exist(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        indexed_columns = {
            tuple(c.name for c in index.columns)
            for index in table.indexes
            if isinstance(index, Index)
        }

        assert ("source_resume_version_id",) in indexed_columns
        assert ("applied_resume_version_id",) in indexed_columns

    def test_timestamps_are_timestamptz_not_null_with_now_default(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        for column_name in ("created_at", "updated_at"):
            column = table.c[column_name]
            assert isinstance(column.type, TIMESTAMP)
            assert column.type.timezone is True
            assert column.nullable is False
            assert column.server_default is not None

    def test_updated_at_has_an_onupdate_mechanism_configured(self) -> None:
        column = Base.metadata.tables["job_preparations"].c.updated_at
        assert column.onupdate is not None

    def test_checkpoint_completion_timestamps_are_nullable_timestamptz(self) -> None:
        table = Base.metadata.tables["job_preparations"]
        for column_name in (
            "initial_analysis_completed_at",
            "career_conversation_completed_at",
            "tailoring_plan_completed_at",
            "applied_at",
            "post_apply_analysis_completed_at",
        ):
            column = table.c[column_name]
            assert isinstance(column.type, TIMESTAMP), column_name
            assert column.type.timezone is True, column_name
            assert column.nullable is True, column_name
            # Unlike created_at/updated_at, a checkpoint timestamp has no
            # server_default -- it is only ever set explicitly, by the
            # orchestration layer, in the same write as its payload/FK.
            assert column.server_default is None, column_name

    def test_checkpoint_consistency_check_constraints_exist(self) -> None:
        texts = _check_constraint_texts(Base.metadata.tables["job_preparations"])
        expected = [
            ("analysis_result IS NOT NULL", "initial_analysis_completed_at IS NOT NULL"),
            (
                "career_conversation IS NOT NULL",
                "career_conversation_completed_at IS NOT NULL",
            ),
            ("tailoring_plan IS NOT NULL", "tailoring_plan_completed_at IS NOT NULL"),
            ("applied_resume_version_id IS NOT NULL", "applied_at IS NOT NULL"),
            (
                "post_apply_analysis IS NOT NULL",
                "post_apply_analysis_completed_at IS NOT NULL",
            ),
        ]
        for payload_clause, timestamp_clause in expected:
            assert any(payload_clause in text and timestamp_clause in text for text in texts), (
                payload_clause,
                timestamp_clause,
            )
