"""Unit tests for `InMemoryPersistenceStore` -- the default `PersistenceStore` backend."""

from uuid import uuid4

import pytest

from app.persistence.errors import (
    InvalidJobPreparationStatusError,
    InvalidResumeVersionSourceError,
    JobPreparationCompletedError,
    JobPreparationNotFoundError,
    ResumeNotFoundError,
    ResumeVersionNotFoundError,
)
from app.persistence.memory_store import InMemoryPersistenceStore
from app.persistence.models import JobPreparationStatus, ResumeVersionSource
from app.persistence.store import PersistenceStore


@pytest.fixture
def store() -> InMemoryPersistenceStore:
    return InMemoryPersistenceStore()


def test_satisfies_the_persistence_store_protocol(store: InMemoryPersistenceStore) -> None:
    assert isinstance(store, PersistenceStore)


class TestResumes:
    def test_create_then_get_round_trips(self, store: InMemoryPersistenceStore) -> None:
        resume = store.create_resume(name="Alice's resume")

        fetched = store.get_resume(resume.id)

        assert fetched == resume
        assert fetched.name == "Alice's resume"

    def test_get_unknown_resume_returns_none(self, store: InMemoryPersistenceStore) -> None:
        assert store.get_resume(uuid4()) is None

    def test_two_uploads_of_the_same_name_are_two_distinct_resumes(
        self, store: InMemoryPersistenceStore
    ) -> None:
        # Rule: an uploaded resume never re-identifies an existing one --
        # not even by matching name -- so `create_resume` must never
        # dedupe or merge, only ever create a new row.
        first = store.create_resume(name="Resume.pdf")
        second = store.create_resume(name="Resume.pdf")

        assert first.id != second.id


class TestResumeVersions:
    def test_first_version_is_original_upload_numbered_one(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume = store.create_resume(name="Alice's resume")

        version = store.create_resume_version(
            resume.id, content="Original text", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )

        assert version.version_number == 1
        assert version.resume_id == resume.id
        assert version.source == ResumeVersionSource.ORIGINAL_UPLOAD

    def test_version_numbers_increment_sequentially_per_resume(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume = store.create_resume(name="Alice's resume")
        v1 = store.create_resume_version(
            resume.id, content="v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )
        v2 = store.create_resume_version(
            resume.id, content="v2", source=ResumeVersionSource.APPLIED
        )
        v3 = store.create_resume_version(
            resume.id, content="v3", source=ResumeVersionSource.APPLIED
        )

        assert [v1.version_number, v2.version_number, v3.version_number] == [1, 2, 3]

    def test_version_numbering_is_independent_per_resume(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume_a = store.create_resume(name="A")
        resume_b = store.create_resume(name="B")
        store.create_resume_version(
            resume_a.id, content="a-v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )

        b_v1 = store.create_resume_version(
            resume_b.id, content="b-v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )

        assert b_v1.version_number == 1

    def test_create_version_for_unknown_resume_raises(
        self, store: InMemoryPersistenceStore
    ) -> None:
        with pytest.raises(ResumeNotFoundError):
            store.create_resume_version(
                uuid4(), content="text", source=ResumeVersionSource.ORIGINAL_UPLOAD
            )

    def test_second_version_cannot_be_original_upload(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume = store.create_resume(name="Alice's resume")
        store.create_resume_version(
            resume.id, content="v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )

        with pytest.raises(InvalidResumeVersionSourceError):
            store.create_resume_version(
                resume.id, content="v2", source=ResumeVersionSource.ORIGINAL_UPLOAD
            )

    def test_first_version_cannot_be_applied(self, store: InMemoryPersistenceStore) -> None:
        resume = store.create_resume(name="Alice's resume")

        with pytest.raises(InvalidResumeVersionSourceError):
            store.create_resume_version(resume.id, content="v1", source=ResumeVersionSource.APPLIED)

    def test_get_unknown_version_returns_none(self, store: InMemoryPersistenceStore) -> None:
        assert store.get_resume_version(uuid4()) is None

    def test_list_versions_is_ordered_and_scoped_to_its_resume(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume_a = store.create_resume(name="A")
        resume_b = store.create_resume(name="B")
        a_v1 = store.create_resume_version(
            resume_a.id, content="a-v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )
        a_v2 = store.create_resume_version(
            resume_a.id, content="a-v2", source=ResumeVersionSource.APPLIED
        )
        store.create_resume_version(
            resume_b.id, content="b-v1", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )

        versions = store.list_resume_versions(resume_a.id)

        assert [v.id for v in versions] == [a_v1.id, a_v2.id]

    def test_list_versions_for_unknown_resume_returns_empty_list(
        self, store: InMemoryPersistenceStore
    ) -> None:
        assert store.list_resume_versions(uuid4()) == []


class TestJobPreparations:
    def _source_version_id(self, store: InMemoryPersistenceStore) -> object:
        resume = store.create_resume(name="Alice's resume")
        version = store.create_resume_version(
            resume.id, content="Original text", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )
        return version.id

    def test_create_starts_in_draft_with_no_applied_version(
        self, store: InMemoryPersistenceStore
    ) -> None:
        source_version_id = self._source_version_id(store)

        preparation = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
            company="Acme",
        )

        assert preparation.status == JobPreparationStatus.DRAFT
        assert preparation.applied_resume_version_id is None
        assert preparation.analysis_result is None
        assert preparation.tailoring_plan is None
        assert preparation.company == "Acme"

    def test_create_for_unknown_source_version_raises(
        self, store: InMemoryPersistenceStore
    ) -> None:
        with pytest.raises(ResumeVersionNotFoundError):
            store.create_job_preparation(
                source_resume_version_id=uuid4(),
                job_title="Backend Engineer",
                job_description="Build things.",
            )

    def test_get_unknown_preparation_returns_none(self, store: InMemoryPersistenceStore) -> None:
        assert store.get_job_preparation(uuid4()) is None

    def test_save_updates_workflow_fields_and_round_trips(
        self, store: InMemoryPersistenceStore
    ) -> None:
        source_version_id = self._source_version_id(store)
        preparation = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )

        updated = store.save_job_preparation(
            preparation.model_copy(
                update={
                    "status": JobPreparationStatus.ACTIVE,
                    "analysis_result": {"overall_assessment": {"overall_score": 72}},
                }
            )
        )

        assert updated.status == JobPreparationStatus.ACTIVE
        assert updated.analysis_result == {"overall_assessment": {"overall_score": 72}}
        assert store.get_job_preparation(preparation.id) == updated

    def test_save_bumps_updated_at(self, store: InMemoryPersistenceStore) -> None:
        source_version_id = self._source_version_id(store)
        preparation = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )

        updated = store.save_job_preparation(
            preparation.model_copy(update={"status": JobPreparationStatus.ACTIVE})
        )

        assert updated.updated_at >= preparation.updated_at

    def test_save_for_never_created_preparation_raises(
        self, store: InMemoryPersistenceStore
    ) -> None:
        source_version_id = self._source_version_id(store)
        phantom = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
        ).model_copy(update={"id": uuid4()})

        with pytest.raises(JobPreparationNotFoundError):
            store.save_job_preparation(phantom)

    def test_completed_requires_an_applied_resume_version(
        self, store: InMemoryPersistenceStore
    ) -> None:
        source_version_id = self._source_version_id(store)
        preparation = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )

        with pytest.raises(InvalidJobPreparationStatusError):
            store.save_job_preparation(
                preparation.model_copy(update={"status": JobPreparationStatus.COMPLETED})
            )

    def test_applied_resume_version_id_must_reference_a_real_version(
        self, store: InMemoryPersistenceStore
    ) -> None:
        source_version_id = self._source_version_id(store)
        preparation = store.create_job_preparation(
            source_resume_version_id=source_version_id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )

        with pytest.raises(ResumeVersionNotFoundError):
            store.save_job_preparation(
                preparation.model_copy(update={"applied_resume_version_id": uuid4()})
            )

    def test_completing_a_preparation_succeeds_with_a_real_applied_version(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume = store.create_resume(name="Alice's resume")
        original = store.create_resume_version(
            resume.id, content="Original text", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )
        applied = store.create_resume_version(
            resume.id, content="Tailored text", source=ResumeVersionSource.APPLIED
        )
        preparation = store.create_job_preparation(
            source_resume_version_id=original.id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )

        completed = store.save_job_preparation(
            preparation.model_copy(
                update={
                    "status": JobPreparationStatus.COMPLETED,
                    "applied_resume_version_id": applied.id,
                }
            )
        )

        assert completed.status == JobPreparationStatus.COMPLETED
        assert completed.applied_resume_version_id == applied.id

    def test_completed_preparation_cannot_be_saved_again(
        self, store: InMemoryPersistenceStore
    ) -> None:
        resume = store.create_resume(name="Alice's resume")
        original = store.create_resume_version(
            resume.id, content="Original text", source=ResumeVersionSource.ORIGINAL_UPLOAD
        )
        applied = store.create_resume_version(
            resume.id, content="Tailored text", source=ResumeVersionSource.APPLIED
        )
        preparation = store.create_job_preparation(
            source_resume_version_id=original.id,
            job_title="Backend Engineer",
            job_description="Build things.",
        )
        completed = store.save_job_preparation(
            preparation.model_copy(
                update={
                    "status": JobPreparationStatus.COMPLETED,
                    "applied_resume_version_id": applied.id,
                }
            )
        )

        with pytest.raises(JobPreparationCompletedError):
            store.save_job_preparation(
                completed.model_copy(update={"job_title": "Senior Backend Engineer"})
            )

        # The rejected write must not have partially applied either.
        assert store.get_job_preparation(preparation.id).job_title == "Backend Engineer"


class TestIsolation:
    def test_two_store_instances_never_share_state(self) -> None:
        store_a = InMemoryPersistenceStore()
        store_b = InMemoryPersistenceStore()

        resume = store_a.create_resume(name="Alice's resume")

        assert store_b.get_resume(resume.id) is None
        assert store_a.get_resume(resume.id) == resume
