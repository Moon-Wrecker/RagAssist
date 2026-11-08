"""Ingestion job statuses and transitions, checked against the domain's own tables.

``JobStatus`` and ``LEGAL_TRANSITIONS`` are the implementation team's code, so these tests read them
directly. The pipeline the plan describes (queued -> parsing -> chunking -> embedding -> indexing ->
completed, a failure from any stage, and a retry back to queued) must be a subset of the legal table.
"""

from __future__ import annotations

import dataclasses

import pytest
from support.specs import need

PIPELINE = [
    ("queued", "parsing"),
    ("parsing", "chunking"),
    ("chunking", "embedding"),
    ("embedding", "indexing"),
    ("indexing", "completed"),
]
FAILURES = [(stage, "failed") for stage in ("parsing", "chunking", "embedding", "indexing")]
RETRY = [("failed", "queued")]


def job(status: str):  # type: ignore[no-untyped-def]
    return need("knowledge.IngestionJob")(document_id="d1", tenant_id="t1", status=status)


def legal_pairs() -> set[tuple[str, str]]:
    return set(need("knowledge.LEGAL_TRANSITIONS"))


def all_statuses() -> list[str]:
    return [status.value for status in need("knowledge.JobStatus")]


class TestStatusValues:
    def test_the_job_statuses_cover_every_pipeline_stage(self) -> None:
        assert set(all_statuses()) == {
            "queued",
            "parsing",
            "chunking",
            "embedding",
            "indexing",
            "completed",
            "failed",
        }

    def test_a_new_job_starts_queued(self) -> None:
        assert job("queued").status.value == "queued"

    def test_a_job_is_immutable(self) -> None:
        assert dataclasses.is_dataclass(job("queued")) and job("queued").__dataclass_params__.frozen

    def test_a_job_exposes_its_identifier_as_a_string(self) -> None:
        assert isinstance(job("queued").job_id, str) and job("queued").job_id


class TestTransitions:
    @pytest.mark.parametrize(("source", "target"), PIPELINE + FAILURES + RETRY)
    def test_the_pipeline_transitions_are_legal(self, source: str, target: str) -> None:
        assert (source, target) in legal_pairs()

    @pytest.mark.parametrize(("source", "target"), PIPELINE + FAILURES + RETRY)
    def test_a_legal_transition_moves_the_job(self, source: str, target: str) -> None:
        moved = need("knowledge.transition_job")(job(source), target)
        assert moved.status.value == target

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            ("queued", "completed"),
            ("queued", "indexing"),
            ("completed", "parsing"),
            ("completed", "queued"),
            ("failed", "completed"),
            ("parsing", "parsing"),
        ],
    )
    def test_an_illegal_transition_is_refused_and_the_job_is_unchanged(
        self, source: str, target: str
    ) -> None:
        original = job(source)
        with pytest.raises(need("knowledge.InvalidTransition")):
            need("knowledge.transition_job")(original, target)
        assert original.status.value == source

    def test_every_pair_of_statuses_is_either_legal_or_refused(self) -> None:
        transition = need("knowledge.transition_job")
        for source in all_statuses():
            for target in all_statuses():
                if (source, target) in legal_pairs():
                    assert transition(job(source), target).status.value == target
                else:
                    with pytest.raises(need("knowledge.InvalidTransition")):
                        transition(job(source), target)

    def test_completed_is_terminal(self) -> None:
        assert not any(source == "completed" for source, _ in legal_pairs())

    def test_a_transition_returns_a_new_job_and_leaves_the_original(self) -> None:
        original = job("queued")
        moved = need("knowledge.transition_job")(original, "parsing")
        assert moved is not original and original.status.value == "queued"


class TestLegalTableIsConsistentWithTheStatuses:
    def test_every_state_named_in_the_legal_table_is_a_job_status(self) -> None:
        named = {state for pair in legal_pairs() for state in pair}
        assert named <= set(all_statuses()), (
            f"transitions name undefined statuses: {sorted(named - set(all_statuses()))}"
        )
